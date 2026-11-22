"""OpenRouter API provider: vision and text through the openrouter SDK.

Every request goes through `chat.send` with its media inline as base64 data
URLs: an image as an `image_url` part, a PDF as a `file` part that the model
reads itself. An image longer than `image_long_side` pixels shrinks first.
OpenRouter has no upload route for a model request, so a request over the byte
limit is refused before it is sent. Three request preferences are fixed and
have no settings key: the native PDF engine, no provider that stores data, and
only the endpoints that take every sent parameter.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from importlib.util import find_spec
from typing import Any

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
    shrink_image,
)
from raw2md.settings import ModelConfig

_logger = logging.getLogger("raw2md")

_SDK_MODULE = "openrouter"

_PDF_MIME = "application/pdf"
_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
_PDF_FILENAME = "document.pdf"

# Some endpoints of one model refuse an image over 5 MB of base64, and a page
# rich in photographs, drawn at 200 dpi, weighs up to twice that as PNG. At
# 2000 px such a page passes every endpoint, and print stays legible.
DEFAULT_IMAGE_LONG_SIDE: int = 2000

# Without the plugin, OpenRouter parses a PDF to text for a model that reads no
# files, and the page image is lost; with `native`, such a model refuses.
_PLUGINS: tuple[Mapping[str, Any], ...] = (
    {"id": "file-parser", "pdf": {"engine": "native"}},
)

# `data_collection` keeps the document off every provider that stores data;
# `require_parameters` keeps a request with a schema off an endpoint without
# structured outputs, which is a property of the endpoint, not of the model.
_PROVIDER_PREFERENCES: Mapping[str, Any] = {
    "data_collection": "deny",
    "require_parameters": True,
}

_SCHEMA_NAME = "reply"

_UNAUTHORIZED = 401
_PAYMENT_REQUIRED = 402
_FORBIDDEN = 403
_REQUEST_TIMEOUT = 408
_PAYLOAD_TOO_LARGE = 413
_TOO_MANY_REQUESTS = 429
_SERVER_ERROR_MIN = 500
_OK = 200

# A request the model or a filter around it declined: an identical request is
# declined again, and the next document may pass, so it is no error.
_BLOCKED_ERROR_TYPES = frozenset({"content_policy_violation", "refusal"})

# A 402 for this cause is transient: the running and recently finished
# requests fill a budget that frees itself, and `Retry-After` says when.
_IN_FLIGHT_REASON = "in_flight_budget_exhausted"
_IN_FLIGHT_LIMIT_SOURCE = "openrouter_in_flight_budget"

# A generation that failed after OpenRouter sent its 200; any text is partial.
_ERROR_FINISH_REASON = "error"
_TRUNCATED_FINISH_REASON = "length"
_BLOCKED_FINISH_REASON = "content_filter"
_COMPLETE_FINISH_REASON = "stop"


@dataclass(frozen=True)
class _Refusal:
    """A declined request, answered as an empty reply rather than raised."""

    detail: str


class OpenRouterApiProvider(Provider):
    """Vision and text generation through the OpenRouter Chat Completions API."""

    # 5 minutes covers a vision request over a whole source PDF; set by hand,
    # not measured.
    _REQUEST_TIMEOUT_MS: int = 300_000

    # The key probe runs before every run and in `doctor`; a stalled network
    # must not hold either for the generation timeout. Set by hand.
    _PROBE_TIMEOUT_MS: int = 10_000

    def __init__(self, model: ModelConfig) -> None:
        super().__init__(model)
        # One client for the run: building one loads two TLS contexts, close
        # to a second each, and a kept client reuses its connections.
        self._client: Any = None
        # The SDK drops the `error` of a choice, so a response hook keeps it
        # for the request that the same thread has in flight.
        self._seen = threading.local()

    def available(self) -> Availability:
        if not _sdk_installed():
            return Availability(False, "openrouter is not installed")
        key_env = self._model.key_env
        if not key_env or not os.environ.get(key_env):
            return Availability(False, f"key variable {key_env} is not set")
        return self._probe_key()

    def _probe_key(self) -> Availability:
        """Probe the key with the free `GET /api/v1/key`; a refused key blocks the run.

        A network failure or a 5xx leaves the decision to the run's own
        requests, as for any other key provider.
        """
        try:
            self._sdk_client().api_keys.get_current_key_metadata(
                timeout_ms=self._PROBE_TIMEOUT_MS
            )
        except _sdk_failures() as exc:
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
        # Built and measured before throttling, so a request that cannot be
        # sent spends no rpm slot.
        messages = self._build_messages(prompt, parts)
        options = self._request_options(response_schema)
        return self._send(lambda: self._request(messages, options))

    def _build_messages(
        self, prompt: str, parts: Sequence[Part]
    ) -> list[dict[str, Any]]:
        """One user message: the prompt, then the parts in order.

        Shrinks an image longer than `image_long_side`. Refuses a media type
        the API has no part for, and a request still over the byte limit: no
        upload route takes it instead.
        """
        long_side = self._model.image_long_side or DEFAULT_IMAGE_LONG_SIDE
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        size = len(prompt.encode("utf-8"))
        for part in parts:
            if isinstance(part, TextPart):
                content.append({"type": "text", "text": part.text})
                size += len(part.text.encode("utf-8"))
                continue
            sent = (
                shrink_image(part, long_side)
                if part.mime_type in _IMAGE_MIMES
                else part
            )
            content.append(_media_content(sent))
            size += inline_media_bytes(len(sent.data))
        limit = self.request_byte_limit
        if size > limit:
            raise DocumentTooLargeError(
                f"request is {size} bytes with its media inline, "
                f"over the {limit}-byte limit"
            )
        return [{"role": "user", "content": content}]

    def _request_options(
        self, response_schema: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """The fixed preferences, the reply schema, and a temperature, if stated.

        No temperature is forced: below the provider's default a model tends
        to loop on a hard task.
        """
        options: dict[str, Any] = {
            "model": self._model.model,
            "plugins": [dict(plugin) for plugin in _PLUGINS],
            "provider": dict(_PROVIDER_PREFERENCES),
        }
        if self._model.temperature is not None:
            options["temperature"] = self._model.temperature
        if response_schema is not None:
            options["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": _SCHEMA_NAME,
                    "schema": dict(response_schema),
                    "strict": True,
                },
            }
        return options

    def _request(
        self, messages: list[dict[str, Any]], options: Mapping[str, Any]
    ) -> Reply:
        self._reserve_rpd()
        client = self._sdk_client()
        self._seen.choice_error = None
        try:
            result = client.chat.send(messages=messages, **options)
        except _sdk_failures() as exc:
            outcome = _translate(exc)
            if isinstance(outcome, _Refusal):
                return self._empty(EmptyReason.BLOCKED, outcome.detail)
            raise outcome from exc
        return self._read_result(result)

    def _read_result(self, result: Any) -> Reply:
        """Take the text of the first choice, or the reason it has none."""
        served = getattr(result, "model", None) or self._model.model
        _log_usage(served, getattr(result, "usage", None))
        choices = getattr(result, "choices", None) or ()
        if not choices:
            raise ProviderError(f"{served} replied with no choices and no error")
        choice = choices[0]
        finish = str(getattr(choice, "finish_reason", None) or "")
        if finish == _ERROR_FINISH_REASON:
            return self._failed_generation(served)
        message = getattr(choice, "message", None)
        text = _message_text(getattr(message, "content", None))
        if text.strip():
            if finish not in ("", _COMPLETE_FINISH_REASON):
                _logger.warning(
                    "llm: %s returned a reply cut short (finish_reason %s)",
                    served,
                    finish,
                )
            return Reply(text)
        refusal = getattr(message, "refusal", None)
        if finish == _BLOCKED_FINISH_REASON or (isinstance(refusal, str) and refusal):
            return self._empty(EmptyReason.BLOCKED, f"finish_reason {finish}")
        if finish == _TRUNCATED_FINISH_REASON:
            return self._empty(EmptyReason.TRUNCATED, f"finish_reason {finish}")
        return self._empty(
            EmptyReason.NO_TEXT, f"finish_reason {finish or 'unreported'}"
        )

    def _failed_generation(self, served: str) -> Reply:
        """Map the error a choice carried, or retry a failure that names none."""
        seen = getattr(self._seen, "choice_error", None)
        if seen is None:
            raise TransientError(f"{served} failed while it generated the reply")
        error, headers = seen
        outcome = _from_status(_OK, json.dumps({"error": error}), headers, served)
        if isinstance(outcome, _Refusal):
            return self._empty(EmptyReason.BLOCKED, outcome.detail)
        raise outcome

    def _keep_choice_error(self, response: Any) -> None:
        """Response hook: note the `error` of the first choice of a 200 reply."""
        if response.status_code != _OK:
            return
        response.read()
        try:
            decoded = json.loads(response.content)
        except json.JSONDecodeError:
            return
        choices = decoded.get("choices") if isinstance(decoded, Mapping) else None
        first = choices[0] if isinstance(choices, list) and choices else None
        error = first.get("error") if isinstance(first, Mapping) else None
        if isinstance(error, Mapping):
            self._seen.choice_error = (error, response.headers)

    def _empty(self, reason: EmptyReason, detail: str) -> Reply:
        _logger.warning(
            "llm: %s returned an empty reply (%s)", self._model.model, detail
        )
        return Reply("", reason)

    def _sdk_client(self) -> Any:
        if self._client is None:
            client = self._create_client()
            client.sdk_configuration.client.event_hooks["response"].append(
                self._keep_choice_error
            )
            self._client = client
        return self._client

    def _create_client(self) -> Any:
        """Build the SDK client with a timeout and no retry of its own; a test seam.

        The shared loop of `Provider._send` owns the retry: the SDK's own
        retries a 5xx for up to an hour, out of reach of the rpm and rpd counts.
        """
        from openrouter import OpenRouter

        key_env = self._model.key_env
        api_key = os.environ.get(key_env) if key_env else None
        if not api_key:
            raise ProviderError(f"key variable {key_env} is not set")
        return OpenRouter(
            api_key=api_key, retry_config=None, timeout_ms=self._REQUEST_TIMEOUT_MS
        )


def _sdk_installed() -> bool:
    return find_spec(_SDK_MODULE) is not None


def _sdk_failures() -> tuple[type[Exception], ...]:
    """The failures a request can raise: an HTTP error or no response at all."""
    import httpx
    from openrouter import errors

    return (
        errors.OpenRouterError,
        errors.NoResponseError,
        httpx.TransportError,
        ConnectionError,
        TimeoutError,
    )


def _media_content(part: MediaPart) -> dict[str, Any]:
    encoded = base64.b64encode(part.data).decode("ascii")
    url = f"data:{part.mime_type};base64,{encoded}"
    if part.mime_type == _PDF_MIME:
        return {"type": "file", "file": {"filename": _PDF_FILENAME, "file_data": url}}
    if part.mime_type in _IMAGE_MIMES:
        return {"type": "image_url", "image_url": {"url": url}}
    raise ProviderError(
        f"openrouter takes PDF, PNG, JPEG, GIF, and WebP, not {part.mime_type}"
    )


def _message_text(content: Any) -> str:
    """The text of a reply message: a plain string or a list of content items."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    pieces = [getattr(item, "text", None) for item in content]
    return "".join(piece for piece in pieces if isinstance(piece, str))


def _translate(exc: Exception) -> ProviderError | _Refusal:
    """Map an SDK failure onto the typed provider family, or onto a refusal."""
    from openrouter import errors

    if isinstance(exc, errors.OpenRouterError):
        return _from_status(exc.status_code, exc.body, exc.headers, str(exc))
    # Every other failure of `_sdk_failures` came before any HTTP response.
    return ConnectionDroppedError(str(exc) or type(exc).__name__)


def _from_status(
    status: int, body: str, headers: Mapping[str, str], message: str
) -> ProviderError | _Refusal:
    """Map a status and its `error` object; a 200 body can hold only the object.

    The object's `code` is the status that counts: on a 200 it names the
    failure the HTTP status could not carry.
    """
    error = _error_object(body)
    if error is None and status == _OK:
        return ProviderError(
            f"reply could not be read, and it holds no error: {message}"
        )
    error = error or {}
    code = error.get("code")
    if isinstance(code, int):
        status = code
    metadata = error.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    error_type = metadata.get("error_type")
    detail = f"{status} {error.get('message') or message}"
    if error_type:
        detail = f"{detail} ({error_type})"
    retry_after = _retry_after(headers)
    if error_type in _BLOCKED_ERROR_TYPES:
        return _Refusal(detail)
    if status in (_UNAUTHORIZED, _FORBIDDEN):
        return AuthError(detail)
    if status == _PAYMENT_REQUIRED:
        if _in_flight_budget(metadata):
            return RateLimitError(detail, retry_after=retry_after)
        return AuthError(detail)
    if status == _TOO_MANY_REQUESTS:
        return RateLimitError(detail, retry_after=retry_after)
    if status == _PAYLOAD_TOO_LARGE:
        return DocumentTooLargeError(detail)
    if status == _REQUEST_TIMEOUT or status >= _SERVER_ERROR_MIN:
        return TransientError(detail, retry_after=retry_after)
    return ProviderError(detail)


def _error_object(body: str) -> Mapping[str, Any] | None:
    try:
        decoded = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None
    error = decoded.get("error") if isinstance(decoded, Mapping) else None
    return error if isinstance(error, Mapping) else None


def _in_flight_budget(metadata: Mapping[str, Any]) -> bool:
    return (
        metadata.get("reason") == _IN_FLIGHT_REASON
        or metadata.get("limit_source") == _IN_FLIGHT_LIMIT_SOURCE
    )


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """`Retry-After` in seconds, given as a number or as an HTTP date."""
    value = headers.get("retry-after")
    if not value:
        return None
    if value.strip().replace(".", "", 1).isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    return max(0.0, (when - dt.datetime.now(dt.UTC)).total_seconds())


def _log_usage(model: str, usage: Any) -> None:
    """Log the tokens and the cost of one request from the reply's `usage`."""
    if usage is None:
        return
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    completion_details = getattr(usage, "completion_tokens_details", None)
    cost = getattr(usage, "cost", None)
    _logger.info(
        "llm: %s used %s input tokens (%s cached), %s output tokens "
        "(%s reasoning), cost %s USD",
        model,
        _count(getattr(usage, "prompt_tokens", None)),
        _count(getattr(prompt_details, "cached_tokens", None)),
        _count(getattr(usage, "completion_tokens", None)),
        _count(getattr(completion_details, "reasoning_tokens", None)),
        cost if isinstance(cost, int | float) else "unreported",
    )


def _count(value: Any) -> int:
    # The SDK marks an absent field with a falsy sentinel, not None.
    return value if isinstance(value, int) else 0
