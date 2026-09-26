"""LLM provider layer behind a common interface.

A provider is one access route to a model: an HTTP API (`api`) or a local CLI
(`cli`). This module holds the interface, the request parts, the reply, the
typed runtime errors, and the shared throttle and retry. A runtime failure maps
to exit code 5; a missing dependency, key, or command is a startup condition
(exit code 3) that `available()` reports.
"""

from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, TypeVar

from raw2md.llm.rpd import has_room, reserve_request
from raw2md.settings import ModelConfig, access_has_vision

_logger = logging.getLogger("raw2md")

# A free-tier run routinely sees a single 429/503 that clears on a repeat. The
# first retry waits `_BACKOFF_BASE_S`, doubling after.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_S = 2.0

# A dropped connection can take the better part of a minute to recover, where
# a 429/503 clears in seconds. Price: an outage spends up to this many rpd slots
# on one call.
_CONNECTION_MAX_ATTEMPTS = 6
_CONNECTION_BACKOFF_BASE_S = 4.0

# Spacing at exactly 60/rpm lets a sliding 60-second window hold rpm+1
# requests. A margin of a tenth still overshot: the provider counts more
# requests than this side sends, so the margin is a fifth.
_RPM_SAFETY = 0.8

# Gemini rejects an inline `generateContent` request above 20 MB. A model with
# another ceiling declares `max_request_bytes` in settings.json; the chunk
# planner bounds a request by the same number.
DEFAULT_MAX_REQUEST_BYTES = 20 * 1024 * 1024

_ReplyT = TypeVar("_ReplyT")


def inline_media_bytes(raw: int) -> int:
    """What `raw` bytes of media weigh inside a request, once base64-encoded.

    The provider's limit applies to the request as sent, not to the file.
    """
    return math.ceil(raw / 3) * 4


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _monotonic() -> float:
    return time.monotonic()


class ProviderError(Exception):
    """Base for a runtime LLM failure; maps to exit code 5."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        # Server-declared wait in seconds, such as a 429's `retryDelay`.
        self.retry_after = retry_after


class RateLimitError(ProviderError):
    """A model is unavailable because its rate or quota limit is exhausted."""


class DailyQuotaExceededError(RateLimitError):
    """The model's declared `rpd` (requests per day) is already spent today.

    Raised before a request is built and never retried: a backoff does not
    clear a budget that resets only at the next day boundary.
    """

    def __init__(self, model: str, limit: int) -> None:
        super().__init__(f"model '{model}' has reached its daily limit of {limit}")


class TransientError(ProviderError):
    """A transient provider failure (a 5xx or overload) worth a bounded retry."""


class ConnectionDroppedError(TransientError):
    """A transport failure with no HTTP response: a refused or reset connection,
    or a timeout. Retried on a longer, slower budget.
    """


class DocumentTooLargeError(ProviderError):
    """A request exceeds the model's size limit; the operation is skipped."""


class AuthError(ProviderError):
    """The provider refuses access itself: a bad key or a CLI without a login.

    Never retried, and the provider remembers it: every later request of the
    run meets the same refusal, so it is raised again without being sent.
    """


# An oversize request or a refused access fails identically on a repeat, so
# neither is retried.
_RETRYABLE = (RateLimitError, TransientError)


def stops_sending(exc: Exception) -> bool:
    """Whether `exc` refuses every request still to come, not only this one.

    A spent limit or a refused access answers the next request the same way,
    so an operation stops sending. Every other failure is about the request
    that met it.
    """
    return isinstance(exc, (RateLimitError, AuthError))


def run_answers_for(exc: Exception) -> bool:
    """Whether the run itself failed, or only this file's coverage suffered.

    An oversize request is a deliberate skip that leaves the result standing.
    Any other provider failure is infrastructure, and the run stays an LLM
    error however much the operation delivered.
    """
    return isinstance(exc, ProviderError) and not isinstance(exc, DocumentTooLargeError)


def _retry_budget(exc: ProviderError) -> tuple[int, float]:
    if isinstance(exc, ConnectionDroppedError):
        return _CONNECTION_MAX_ATTEMPTS, _CONNECTION_BACKOFF_BASE_S
    return _MAX_ATTEMPTS, _BACKOFF_BASE_S


@dataclass(frozen=True)
class Availability:
    """Result of a provider readiness check; `reason` is printable when not `ok`."""

    ok: bool
    reason: str | None = None


@dataclass(frozen=True)
class TextPart:
    """A text fragment of a request (the marked zones, the current md, ...)."""

    text: str


@dataclass(frozen=True)
class MediaPart:
    """A binary attachment with its MIME type (a page image, the source PDF)."""

    data: bytes
    mime_type: str


Part = TextPart | MediaPart


class EmptyReason(Enum):
    """Why a reply came back without text, as far as the provider can tell."""

    BLOCKED = "blocked"
    TRUNCATED = "truncated"
    NO_TEXT = "no_text"


# A blocked or truncated reply repeats on an identical request, so a retry
# only spends quota; a reply with no text may differ on a second attempt.
FINAL_EMPTY_REASONS = frozenset({EmptyReason.BLOCKED, EmptyReason.TRUNCATED})


@dataclass(frozen=True)
class Reply:
    """A model reply with the reason it is empty, when the provider knows one.

    `empty_reason` is None for a reply with text too, so read it only after
    finding `text` empty.
    """

    text: str
    empty_reason: EmptyReason | None = None


def empty_reason_label(reason: EmptyReason | None) -> str:
    """The log word for an empty-reply reason; providers may report none."""
    return reason.value if reason is not None else "reason unreported"


class Provider(ABC):
    """One LLM access route behind a common interface."""

    # The `rpd` reset zone for a model that declares none. A concrete provider
    # overrides it with its vendor's zone; UTC is no claim about any vendor.
    DEFAULT_RPD_RESET_ZONE: ClassVar[str] = "UTC"

    def __init__(self, model: ModelConfig) -> None:
        self._model = model
        # A provider is built once per run, so the rpm pause spans the batch.
        self._last_request_at: float | None = None
        # The same holds for a refused access: it stops the whole batch.
        self._auth_failure: AuthError | None = None

    @property
    def supports_vision(self) -> bool:
        """Whether the provider can accept `MediaPart` inputs."""
        return access_has_vision(self._model.access)

    @property
    def request_byte_limit(self) -> int:
        """Largest request this model accepts, in bytes."""
        return self._model.max_request_bytes or DEFAULT_MAX_REQUEST_BYTES

    @property
    def _rpd_zone(self) -> str:
        """IANA zone of this model's `rpd` day boundary."""
        return self._model.rpd_reset_zone or self.DEFAULT_RPD_RESET_ZONE

    @abstractmethod
    def available(self) -> Availability:
        """Whether the provider's dependency, key, and command are usable."""

    @abstractmethod
    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        """Send `prompt` plus `parts` and return the model's text reply.

        Raises `RateLimitError` on quota exhaustion, `DocumentTooLargeError`
        over the size limit, `AuthError` on a refused access, and
        `ProviderError` on any other failure. The network call goes through
        `_send`.
        """

    def generate_reply(
        self,
        prompt: str,
        parts: Sequence[Part] = (),
        *,
        response_schema: Mapping[str, Any] | None = None,  # noqa: ARG002 -- the default has no schema contract
    ) -> Reply:
        """Send a request and return the reply with its empty-reply reason.

        `response_schema` is a JSON Schema the reply should follow. A provider
        that can constrain its output to it does so; any other sends the plain
        request, so the caller decodes the reply tolerantly either way. The
        default wraps `generate`, ignores the schema, and reports no reason.
        """
        return Reply(self.generate(prompt, parts))

    def _send(self, request: Callable[[], _ReplyT]) -> _ReplyT:
        """Refuse a spent daily budget, throttle by rpm, then run `request` with retry.

        Every attempt, a retry included, passes the rpd check and the rpm
        throttle, so retries count against the declared rate. Backoff stretches
        to the server's `retry_after` when that is longer, so the retries do not
        land in the quota window the provider asked to wait out. The last error
        propagates unchanged.

        A refused access is raised again ahead of the rpd check and the
        throttle, so a request that cannot pass spends neither.
        """
        if self._auth_failure is not None:
            raise self._auth_failure
        attempt = 0
        while True:
            attempt += 1
            self._refuse_if_rpd_exhausted()
            self._throttle()
            try:
                return request()
            except AuthError as exc:
                self._auth_failure = exc
                raise
            except _RETRYABLE as exc:
                max_attempts, backoff_base = _retry_budget(exc)
                if attempt >= max_attempts:
                    raise
                delay = backoff_base * 2 ** (attempt - 1)
                if exc.retry_after is not None and exc.retry_after > delay:
                    delay = exc.retry_after
                _logger.info(
                    "llm: %s on attempt %d/%d, retrying in %.0fs",
                    type(exc).__name__,
                    attempt,
                    max_attempts,
                    delay,
                )
                _sleep(delay)

    def _throttle(self) -> None:
        """Pause so consecutive requests stay at least 60/(rpm * _RPM_SAFETY) apart."""
        rpm = self._model.rpm
        if not rpm or rpm <= 0:
            return
        min_interval = 60.0 / (rpm * _RPM_SAFETY)
        if self._last_request_at is not None:
            wait = min_interval - (_monotonic() - self._last_request_at)
            if wait > 0:
                _sleep(wait)
        self._last_request_at = _monotonic()

    def _refuse_if_rpd_exhausted(self) -> None:
        """Refuse outright once today's `rpd` budget is spent; records nothing."""
        rpd = self._model.rpd
        if rpd and rpd > 0 and not has_room(self._model.model, rpd, self._rpd_zone):
            raise DailyQuotaExceededError(self._model.model, rpd)

    def _reserve_rpd(self) -> None:
        """Commit one request against the model's `rpd`, or refuse it outright.

        A concrete provider calls it right before its metered call, not from
        `_send`, so a failed upload is not counted. The count lives on disk,
        so a restart sees what today already spent.
        """
        rpd = self._model.rpd
        if not rpd or rpd <= 0:
            return
        if not reserve_request(self._model.model, rpd, self._rpd_zone):
            raise DailyQuotaExceededError(self._model.model, rpd)
