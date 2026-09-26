"""Gemini API provider: vision and text via the google-genai SDK.

The SDK is imported lazily and `available()` reports its absence. Media rides
inline while the whole request fits the model's byte limit, and goes through
the File API otherwise: uploaded, referenced by URI, deleted after the reply.
The route is settled before the request is sent.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from importlib.util import find_spec
from typing import Any, ClassVar

from raw2md.llm.base import (
    AuthError,
    Availability,
    ConnectionDroppedError,
    DocumentTooLargeError,
    EmptyReason,
    MediaPart,
    Part,
    Provider,
    ProviderError,
    RateLimitError,
    Reply,
    TextPart,
    TransientError,
    inline_media_bytes,
)

_logger = logging.getLogger("raw2md")

_SDK_MODULE = "google.genai"

# The SDK's error text is what reliably carries the quota signal.
_RATE_LIMIT_MARKERS = (
    "429",
    "quota",
    "resource_exhausted",
    "resourceexhausted",
    "rate limit",
    "rate_limit",
)

_AUTH_ERROR_CODES = frozenset({401, 403})

# A bad key comes back as a 400, indistinguishable by code from any other bad
# request; only this wording names a refused key.
_AUTH_ERROR_MARKERS = (
    "api_key_invalid",
    "api key not valid",
    "api key expired",
)

_TRANSIENT_CODES = frozenset({500, 502, 503, 504})

# For an error with no numeric code; the free tier returns `503 UNAVAILABLE`
# and `overloaded`.
_TRANSIENT_MARKERS = (
    "500",
    "502",
    "503",
    "504",
    "unavailable",
    "overloaded",
    "internal error",
    "deadline exceeded",
)

# A 429's `RetryInfo.retryDelay`, such as "31.6s"; the SDK has no typed field
# for it, only the error text.
_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")

# All mean the same for a caller: an identical request is refused again.
_BLOCKED_FINISH_REASONS = frozenset(
    {
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
    }
)

# Empty text with this reason means the whole output budget went to reasoning.
_TRUNCATED_FINISH_REASON = "MAX_TOKENS"

_FILE_ACTIVE = "ACTIVE"
_FILE_FAILED = "FAILED"

# The weight of a URI reference in a request, set far above the real one.
_URI_REFERENCE_BYTES = 512

# A source PDF of a few dozen megabytes turns usable in seconds; the ceiling
# keeps a stuck upload from blocking the batch.
_UPLOAD_READY_TIMEOUT_S = 120.0
_UPLOAD_POLL_INTERVAL_S = 2.0


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _monotonic() -> float:
    return time.monotonic()


class GeminiApiProvider(Provider):
    """Vision and text generation through the google-genai SDK."""

    # 5 minutes covers a vision request over a whole source PDF; set by hand,
    # not measured.
    _REQUEST_TIMEOUT_MS: int = 300_000

    # The key probe runs before every run and in `doctor`; a stalled network
    # must not hold either for the generation timeout. Set by hand.
    _PROBE_TIMEOUT_MS: int = 10_000

    # Google documents the free-tier daily quota resetting at midnight Pacific.
    DEFAULT_RPD_RESET_ZONE: ClassVar[str] = "America/Los_Angeles"

    def available(self) -> Availability:
        if not _sdk_installed():
            return Availability(False, "google-genai is not installed")
        key_env = self._model.key_env
        if not key_env or not os.environ.get(key_env):
            return Availability(False, f"key variable {key_env} is not set")
        return self._probe_key()

    def _probe_key(self) -> Availability:
        """Probe the key with a free `models.list` call; a refused key blocks the run.

        A network failure or a 5xx leaves the decision to the run's own
        requests: a run started offline should not fail here over a stage that
        may not need the LLM at all.
        """
        try:
            # The SDK closes a client once it is collected, so a client that is
            # not bound to a name is closed before `list` sends its request.
            client = self._create_client(timeout_ms=self._PROBE_TIMEOUT_MS)
            client.models.list()
        except Exception as exc:  # noqa: BLE001 -- SDK boundary: a readiness check must not crash on it
            if isinstance(_translate(exc), AuthError):
                return Availability(False, str(exc))
            return Availability(True)
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        return self.generate_reply(prompt, parts).text

    def generate_reply(
        self,
        prompt: str,
        parts: Sequence[Part] = (),
        *,
        response_schema: Mapping[str, Any] | None = None,
    ) -> Reply:
        # The route is settled before throttling, so a request no route can
        # carry spends no rpm slot. A retry re-uploads: each attempt stands
        # alone.
        upload_media = self._plan_media(prompt, parts)
        return self._send(
            lambda: self._request(
                prompt,
                parts,
                upload_media=upload_media,
                response_schema=response_schema,
            )
        )

    def _request(
        self,
        prompt: str,
        parts: Sequence[Part],
        *,
        upload_media: bool = False,
        response_schema: Mapping[str, Any] | None = None,
    ) -> Reply:
        client = self._create_client()
        try:
            with self._referenced_media(client, parts, upload_media) as uploads:
                # After the upload, so a failed upload spends no daily budget.
                self._reserve_rpd()
                response = client.models.generate_content(
                    model=self._model.model,
                    contents=_build_contents(prompt, parts, uploads),
                    config=self._generation_config(response_schema),
                )
        except ProviderError:
            # Already typed (a refused upload); keep its reason.
            raise
        except Exception as exc:
            # SDK boundary: every failure is translated into the typed family.
            raise _translate(exc) from exc
        text: str | None = getattr(response, "text", None)
        if text:
            return Reply(text)
        # An empty reply is no SDK error; its reason lives in the response.
        reason, detail = _empty_reason(response)
        _logger.warning(
            "llm: %s returned an empty reply (%s)", self._model.model, detail
        )
        return Reply("", reason)

    def _plan_media(self, prompt: str, parts: Sequence[Part]) -> bool:
        """Whether this request's media has to be uploaded instead of inlined.

        Inline stays the default: an upload costs a round trip and leaves a
        copy with the provider. A request whose text alone is over the limit is
        refused here, since the API would answer it with a bare 400.
        """
        limit = self.request_byte_limit
        text_bytes = len(prompt.encode("utf-8")) + sum(
            len(part.text.encode("utf-8"))
            for part in parts
            if isinstance(part, TextPart)
        )
        media = [part for part in parts if isinstance(part, MediaPart)]
        inline_bytes = text_bytes + sum(inline_media_bytes(len(m.data)) for m in media)
        if inline_bytes <= limit:
            return False
        referenced_bytes = text_bytes + _URI_REFERENCE_BYTES * len(media)
        if referenced_bytes > limit:
            raise DocumentTooLargeError(
                f"request is {referenced_bytes} bytes without its media, "
                f"over the {limit}-byte limit"
            )
        _logger.info(
            "llm: request is %d bytes inline, over the %d-byte limit; "
            "sending %d media part(s) through the file api",
            inline_bytes,
            limit,
            len(media),
        )
        return True

    @contextmanager
    def _referenced_media(
        self, client: Any, parts: Sequence[Part], upload_media: bool
    ) -> Iterator[Mapping[int, Any]]:
        """Upload the media parts, yield the references, then delete them.

        Keyed by position, so two identical attachments stay two references. A
        file joins the cleanup list the moment it exists, before the wait for
        it to turn usable: a refused file is left behind too.
        """
        if not upload_media:
            yield {}
            return
        references: dict[int, Any] = {}
        created: list[Any] = []
        try:
            for position, part in enumerate(parts):
                if isinstance(part, MediaPart):
                    file = self._upload(client, part)
                    created.append(file)
                    references[position] = self._await_active(client, file)
            yield references
        finally:
            for file in created:
                _delete_uploaded(client, file)

    def _upload(self, client: Any, part: MediaPart) -> Any:
        """Upload one media part and return the stored file, not yet usable."""
        from google import genai

        _logger.info(
            "llm: uploading %d bytes of %s through the file api",
            len(part.data),
            part.mime_type,
        )
        return client.files.upload(
            file=io.BytesIO(part.data),
            config=genai.types.UploadFileConfig(mime_type=part.mime_type),
        )

    def _await_active(self, client: Any, file: Any) -> Any:
        """Poll an uploaded file until the provider reports it usable.

        A file referenced before it is processed is refused as an invalid
        argument. A refused file is a `ProviderError`, since the same bytes
        would be refused again; a timeout is transient, so a retry re-uploads.
        """
        deadline = _monotonic() + _UPLOAD_READY_TIMEOUT_S
        while True:
            state = _enum_name(getattr(file, "state", None))
            if state == _FILE_ACTIVE:
                return file
            name = getattr(file, "name", None) or "?"
            if state == _FILE_FAILED:
                raise ProviderError(
                    f"uploaded file {name} was refused: {_file_error(file)}"
                )
            if _monotonic() >= deadline:
                raise TransientError(
                    f"uploaded file {name} is still {state or 'unreported'} after "
                    f"{_UPLOAD_READY_TIMEOUT_S:.0f}s"
                )
            _sleep(_UPLOAD_POLL_INTERVAL_S)
            file = client.files.get(name=name)

    def _generation_config(self, response_schema: Mapping[str, Any] | None) -> Any:
        """Build the request config: a reply shape and a temperature, if stated.

        No temperature is forced: below the provider's default a model tends to
        loop on a hard task. `response_json_schema` is plain JSON Schema, which
        takes constructs the SDK's own `Schema` type does not; the field is
        ignored without `response_mime_type`.
        """
        from google import genai

        config: dict[str, Any] = {}
        if self._model.temperature is not None:
            config["temperature"] = self._model.temperature
        if response_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = dict(response_schema)
        return genai.types.GenerateContentConfig(**config)

    def _create_client(self, timeout_ms: int = _REQUEST_TIMEOUT_MS) -> Any:
        """Build the genai client with a request timeout; a seam for tests."""
        from google import genai

        key_env = self._model.key_env
        api_key = os.environ.get(key_env) if key_env else None
        if not api_key:
            raise ProviderError(f"key variable {key_env} is not set")
        http_options = genai.types.HttpOptions(timeout=timeout_ms)
        return genai.Client(api_key=api_key, http_options=http_options)


def _sdk_installed() -> bool:
    # find_spec raises when the `google` namespace itself is absent.
    try:
        return find_spec(_SDK_MODULE) is not None
    except ImportError:
        return False


def _build_contents(
    prompt: str, parts: Sequence[Part], uploads: Mapping[int, Any]
) -> list[Any]:
    """Assemble the request contents; a media part not in `uploads` rides inline."""
    contents: list[Any] = [prompt]
    for position, part in enumerate(parts):
        if isinstance(part, MediaPart):
            from google import genai

            uploaded = uploads.get(position)
            if uploaded is None:
                contents.append(
                    genai.types.Part.from_bytes(
                        data=part.data, mime_type=part.mime_type
                    )
                )
            else:
                contents.append(
                    genai.types.Part.from_uri(
                        file_uri=uploaded.uri,
                        mime_type=getattr(uploaded, "mime_type", None)
                        or part.mime_type,
                    )
                )
        else:
            contents.append(part.text)
    return contents


def _delete_uploaded(client: Any, file: Any) -> None:
    """Delete an uploaded file; a failure is logged, the provider expires it."""
    name = getattr(file, "name", None)
    if not name:
        return
    try:
        client.files.delete(name=name)
    except Exception as exc:  # noqa: BLE001 -- SDK boundary: cleanup must not lose the reply
        _logger.warning("llm: could not delete the uploaded file %s: %s", name, exc)


def _file_error(file: Any) -> str:
    message = getattr(getattr(file, "error", None), "message", None)
    return str(message) if message else "no reason reported"


def _translate(exc: Exception) -> ProviderError:
    """Map an SDK failure onto the typed provider family."""
    if _is_auth_error(exc):
        return AuthError(str(exc))
    if _is_rate_limit(exc):
        return RateLimitError(str(exc), retry_after=_retry_delay_seconds(exc))
    if _is_dropped_connection(exc):
        return ConnectionDroppedError(str(exc))
    if _is_transient(exc):
        return TransientError(str(exc))
    return ProviderError(str(exc))


def _empty_reason(response: Any) -> tuple[EmptyReason, str]:
    """Classify why `response` carries no text, with a detail line for the log.

    `prompt_feedback` holds a refused request, the first candidate's
    `finish_reason` a refused or cut reply; anything else is silence with no
    stated cause, which a repeat may break.
    """
    block = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
    if block:
        return EmptyReason.BLOCKED, f"prompt blocked: {_enum_name(block)}"
    candidates = getattr(response, "candidates", None) or ()
    if not candidates:
        return EmptyReason.NO_TEXT, "no candidates in the reply"
    finish = _enum_name(getattr(candidates[0], "finish_reason", None))
    if finish in _BLOCKED_FINISH_REASONS:
        return EmptyReason.BLOCKED, f"finish_reason {finish}"
    if finish == _TRUNCATED_FINISH_REASON:
        return EmptyReason.TRUNCATED, f"finish_reason {finish}"
    return EmptyReason.NO_TEXT, f"finish_reason {finish or 'unreported'}"


def _enum_name(value: Any) -> str:
    """The bare name of an SDK enum value or plain string, or "" when absent."""
    if value is None:
        return ""
    name = getattr(value, "name", None)
    text = str(name if name is not None else value)
    return text.rsplit(".", 1)[-1].upper()


def _is_auth_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in _AUTH_ERROR_CODES:
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _AUTH_ERROR_MARKERS)


def _is_rate_limit(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _RATE_LIMIT_MARKERS)


def _is_transient(exc: Exception) -> bool:
    # Checked after `_is_rate_limit`, so a 429 never reaches here.
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in _TRANSIENT_CODES:
        return True
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def _is_dropped_connection(exc: Exception) -> bool:
    """Whether `exc` is a transport failure raised before any HTTP response.

    It carries no status code, so it is told apart by type. Narrower than
    `OSError` on purpose: the rpd state-file write can raise a local `OSError`
    that is no dropped connection.
    """
    import httpx

    return isinstance(exc, (httpx.TransportError, ConnectionError, TimeoutError))


def _retry_delay_seconds(exc: Exception) -> float | None:
    match = _RETRY_DELAY_RE.search(str(exc))
    return float(match.group(1)) if match else None
