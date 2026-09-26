"""Tests for the LLM provider layer: factory, capabilities, errors."""

from __future__ import annotations

import builtins
import itertools
import json
import logging
import subprocess
import sys
import weakref
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

from raw2md.llm import (
    AuthError,
    ClaudeCliProvider,
    ConnectionDroppedError,
    DailyQuotaExceededError,
    DocumentTooLargeError,
    GeminiApiProvider,
    MediaPart,
    Provider,
    ProviderError,
    RateLimitError,
    TextPart,
    TransientError,
    build_provider,
)
from raw2md.llm.base import (
    DEFAULT_MAX_REQUEST_BYTES,
    Availability,
    EmptyReason,
    stops_sending,
)
from raw2md.llm.claude import DEFAULT_CLAUDE_TIMEOUT_S
from raw2md.paths import rpd_file
from raw2md.settings import ModelConfig


def api_model(
    key_env: str | None = "GOOGLE_API_KEY",
    rpm: int | None = None,
    rpd: int | None = None,
    rpd_reset_zone: str | None = None,
    max_request_bytes: int | None = None,
    temperature: float | None = None,
) -> ModelConfig:
    return ModelConfig(
        access="api",
        model="gemini-2.5-flash",
        key_env=key_env,
        command=None,
        rpm=rpm,
        tpm=None,
        rpd=rpd,
        rpd_reset_zone=rpd_reset_zone,
        max_request_bytes=max_request_bytes,
        temperature=temperature,
    )


def cli_model(
    command: str | None = "claude", cli_timeout_s: int | None = None
) -> ModelConfig:
    return ModelConfig(
        access="cli",
        model="claude-sonnet-4-6",
        key_env=None,
        command=command,
        rpm=None,
        tpm=None,
        rpd=None,
        cli_timeout_s=cli_timeout_s,
    )


# --- Factory and capability matrix -----------------------------------------


def test_build_provider_dispatches_by_access() -> None:
    assert isinstance(build_provider(api_model()), GeminiApiProvider)
    assert isinstance(build_provider(cli_model()), ClaudeCliProvider)


def test_build_provider_unknown_access_raises() -> None:
    rogue = ModelConfig(
        access="grpc",
        model="m",
        key_env=None,
        command=None,
        rpm=None,
        tpm=None,
        rpd=None,
    )
    with pytest.raises(ValueError, match="unknown access type"):
        build_provider(rogue)


def test_supports_vision_matches_access() -> None:
    assert build_provider(api_model()).supports_vision is True
    assert build_provider(cli_model()).supports_vision is False


def test_runtime_errors_map_to_llm_exit() -> None:
    # The pipeline maps ProviderError to exit code 5.
    assert issubclass(RateLimitError, ProviderError)
    assert issubclass(DocumentTooLargeError, ProviderError)
    assert issubclass(DailyQuotaExceededError, RateLimitError)
    assert issubclass(AuthError, ProviderError)


def test_stops_sending_covers_a_spent_budget_and_a_refused_access() -> None:
    assert stops_sending(RateLimitError("429"))
    assert stops_sending(DailyQuotaExceededError("m", 1))
    assert stops_sending(AuthError("bad key"))
    assert not stops_sending(TransientError("503"))
    assert not stops_sending(DocumentTooLargeError("over the limit"))
    assert not stops_sending(ProviderError("other"))


# --- Refused access ----------------------------------------------------------


class _SendingProvider(Provider):
    """Provider whose metered call raises queued errors through `_send`."""

    def __init__(self, model: ModelConfig, outcomes: Sequence[str | Exception]) -> None:
        super().__init__(model)
        self._outcomes = list(outcomes)
        self.requests = 0

    def available(self) -> Any:
        raise NotImplementedError

    def generate(self, prompt: str, parts: Sequence[Any] = ()) -> str:
        return self._send(self._request)

    def _request(self) -> str:
        self.requests += 1
        self._reserve_rpd()
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_auth_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    provider = _SendingProvider(cli_model(), [AuthError("bad key"), "ok"])
    with pytest.raises(AuthError):
        provider.generate("prompt")
    assert provider.requests == 1


def test_auth_error_is_raised_again_without_a_request(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    # The refusal outlives the call: the next one neither sends nor spends rpd.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    model = ModelConfig(
        access="cli",
        model="claude-sonnet-4-6",
        key_env=None,
        command="claude",
        rpm=None,
        tpm=None,
        rpd=5,
    )
    provider = _SendingProvider(model, [AuthError("not logged in"), "ok"])
    with pytest.raises(AuthError):
        provider.generate("prompt")
    throttled: list[None] = []
    monkeypatch.setattr(provider, "_throttle", lambda: throttled.append(None))

    with pytest.raises(AuthError, match="not logged in"):
        provider.generate("prompt")

    assert provider.requests == 1
    assert throttled == []
    counts = json.loads(rpd_file().read_text(encoding="utf-8"))["counts"]
    assert counts["claude-sonnet-4-6"]["count"] == 1


# --- Gemini availability ---------------------------------------------------


def _gemini_available(
    monkeypatch: pytest.MonkeyPatch, models: _FakeModels
) -> Availability:
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    provider = build_provider(api_model())
    monkeypatch.setattr(
        provider, "_create_client", lambda **kwargs: _FakeClient(models)
    )
    return provider.available()


def test_gemini_available_with_sdk_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    availability = _gemini_available(monkeypatch, _FakeModels())
    assert availability.ok is True
    assert availability.reason is None


def test_gemini_unavailable_without_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    availability = build_provider(api_model()).available()
    assert availability.ok is False
    assert "google-genai" in (availability.reason or "")


def test_gemini_unavailable_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    availability = build_provider(api_model()).available()
    assert availability.ok is False
    assert "GOOGLE_API_KEY" in (availability.reason or "")


def test_gemini_unavailable_on_a_refused_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # A probe that meets the same refusal a request would gets caught here,
    # before conversion starts.
    error = RuntimeError(
        "400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key."
    )
    availability = _gemini_available(monkeypatch, _FakeModels(list_error=error))
    assert availability.ok is False
    assert "API key not valid" in (availability.reason or "")


def test_gemini_available_despite_a_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The probe cannot tell a real outage from a bad key by failing, so it
    # leaves the call to the run's own requests.
    error = RuntimeError("503 UNAVAILABLE")
    availability = _gemini_available(monkeypatch, _FakeModels(list_error=error))
    assert availability.ok is True


class _ClosingModels:
    def __init__(self, owner: weakref.ref[Any]) -> None:
        self._owner = owner

    def list(self) -> None:
        if self._owner() is None:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        raise RuntimeError("400 INVALID_ARGUMENT. API key not valid.")


class _ClosingClient:
    """Closes once collected, as the SDK client does."""

    def __init__(self) -> None:
        self.models = _ClosingModels(weakref.ref(self))


def test_gemini_probe_keeps_the_client_alive_for_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A client dropped before `list` sends its request fails as closed, which
    # reads as no refusal and passes a refused key.
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    provider = build_provider(api_model())
    monkeypatch.setattr(provider, "_create_client", lambda **kwargs: _ClosingClient())

    availability = provider.available()

    assert availability.ok is False
    assert "API key not valid" in (availability.reason or "")


def test_gemini_available_despite_a_dropped_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ConnectionResetError("Connection reset by peer")
    availability = _gemini_available(monkeypatch, _FakeModels(list_error=error))
    assert availability.ok is True


def test_gemini_create_client_sets_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A client without a timeout lets a hung call block the batch; this patches
    # the real `google.genai.Client` constructor.
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("google.genai.Client", FakeClient)
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    provider = GeminiApiProvider(api_model())

    provider._create_client()

    http_options = captured["http_options"]
    assert http_options.timeout == GeminiApiProvider._REQUEST_TIMEOUT_MS


def test_gemini_key_probe_uses_a_short_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A stalled network must not hold a run start or `doctor` for the
    # generation timeout.
    timeouts: list[int] = []

    def fake_create_client(timeout_ms: int = 0) -> _FakeClient:
        timeouts.append(timeout_ms)
        return _FakeClient(_FakeModels())

    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    provider = build_provider(api_model())
    monkeypatch.setattr(provider, "_create_client", fake_create_client)

    assert provider.available().ok is True
    assert timeouts == [GeminiApiProvider._PROBE_TIMEOUT_MS]
    assert GeminiApiProvider._PROBE_TIMEOUT_MS < GeminiApiProvider._REQUEST_TIMEOUT_MS


# --- Gemini generate -------------------------------------------------------


class _FakeCandidate:
    def __init__(self, finish_reason: Any) -> None:
        self.finish_reason = finish_reason


class _FakeFeedback:
    def __init__(self, block_reason: Any) -> None:
        self.block_reason = block_reason


class _FakeResponse:
    def __init__(
        self,
        text: str | None,
        *,
        candidates: Sequence[_FakeCandidate] | None = None,
        prompt_feedback: _FakeFeedback | None = None,
    ) -> None:
        self.text = text
        self.candidates = list(candidates) if candidates is not None else []
        self.prompt_feedback = prompt_feedback


class _FakeModels:
    """Fake `client.models`.

    `response`/`error` repeat one outcome; `outcomes` plays a sequence.
    `calls` records every attempt.
    """

    def __init__(
        self,
        *,
        response: _FakeResponse | None = None,
        error: Exception | None = None,
        outcomes: Sequence[_FakeResponse | Exception] | None = None,
        list_error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self._outcomes: builtins.list[_FakeResponse | Exception] | None = (
            list(outcomes) if outcomes is not None else None
        )
        self._list_error = list_error
        self.calls: builtins.list[tuple[str, builtins.list[Any], Any]] = []

    def list(self) -> Sequence[Any]:
        # Qualified as `builtins.list` in this class's other annotations: the
        # method below shadows the bare name for the type checker.
        if self._list_error is not None:
            raise self._list_error
        return []

    def generate_content(
        self, *, model: str, contents: builtins.list[Any], config: Any = None
    ) -> _FakeResponse:
        self.calls.append((model, contents, config))
        if self._outcomes is not None:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class _FakeFileError:
    """Fake `File.error`: the provider's stated reason for refusing a file."""

    def __init__(self, message: str) -> None:
        self.message = message


class _FakeFile:
    """Fake `types.File`: what an upload returns and `files.get` refreshes."""

    def __init__(
        self,
        name: str = "files/abc",
        *,
        uri: str = "https://generativelanguage.googleapis.com/v1beta/files/abc",
        mime_type: str = "application/pdf",
        state: str = "ACTIVE",
        error: Any = None,
    ) -> None:
        self.name = name
        self.uri = uri
        self.mime_type = mime_type
        self.state = state
        self.error = error


class _FakeFiles:
    """Fake `client.files`.

    `states` plays one state per `upload`/`get` call, the last repeating.
    `uploads` and `deleted` record what happened.
    """

    def __init__(
        self,
        *,
        states: Sequence[str] = ("ACTIVE",),
        error: Any = None,
        upload_error: Exception | None = None,
        delete_error: Exception | None = None,
    ) -> None:
        self._states = list(states)
        self._error = error
        self._upload_error = upload_error
        self._delete_error = delete_error
        self.uploads: list[tuple[bytes, str | None]] = []
        self.gets: list[str] = []
        self.deleted: list[str] = []

    def _next_state(self) -> str:
        return self._states.pop(0) if len(self._states) > 1 else self._states[0]

    def upload(self, *, file: Any, config: Any) -> _FakeFile:
        if self._upload_error is not None:
            raise self._upload_error
        self.uploads.append((file.read(), getattr(config, "mime_type", None)))
        return _FakeFile(state=self._next_state(), error=self._error)

    def get(self, *, name: str) -> _FakeFile:
        self.gets.append(name)
        return _FakeFile(name=name, state=self._next_state(), error=self._error)

    def delete(self, *, name: str) -> None:
        if self._delete_error is not None:
            raise self._delete_error
        self.deleted.append(name)


class _FakeClient:
    def __init__(self, models: _FakeModels, files: _FakeFiles | None = None) -> None:
        self.models = models
        self.files = files if files is not None else _FakeFiles()


def _gemini_with_client(
    monkeypatch: pytest.MonkeyPatch,
    models: _FakeModels,
    *,
    files: _FakeFiles | None = None,
    max_request_bytes: int | None = None,
    temperature: float | None = None,
) -> GeminiApiProvider:
    provider = GeminiApiProvider(
        api_model(max_request_bytes=max_request_bytes, temperature=temperature)
    )
    client = _FakeClient(models, files)
    monkeypatch.setattr(provider, "_create_client", lambda: client)
    return provider


def test_gemini_generate_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    models = _FakeModels(response=_FakeResponse("recognized"))
    provider = _gemini_with_client(monkeypatch, models)
    assert provider.generate("prompt", [TextPart("body")]) == "recognized"
    model_name, contents, config = models.calls[0]
    assert model_name == "gemini-2.5-flash"
    assert contents == ["prompt", "body"]
    assert config.temperature is None


def test_gemini_generate_empty_text_is_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    models = _FakeModels(response=_FakeResponse(None))
    provider = _gemini_with_client(monkeypatch, models)
    assert provider.generate("prompt") == ""


# --- Gemini structured output -----------------------------------------------


def test_generate_reply_with_schema_requests_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A caller that knows its shape asks the model's decoder to guarantee it.
    schema = {"type": "array", "items": {"type": "string"}}
    models = _FakeModels(response=_FakeResponse("[]"))
    provider = _gemini_with_client(monkeypatch, models)

    provider.generate_reply("prompt", [TextPart("body")], response_schema=schema)

    _, _, config = models.calls[0]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema
    assert config.temperature is None


# --- Gemini sampling temperature -------------------------------------------


def test_no_temperature_is_sent_when_the_model_states_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The provider advises against overriding its default for these models.
    models = _FakeModels(response=_FakeResponse("recognized"))
    provider = _gemini_with_client(monkeypatch, models)

    provider.generate_reply("prompt", [TextPart("body")])

    _, _, config = models.calls[0]
    assert config.temperature is None


def test_temperature_comes_from_the_model_when_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(response=_FakeResponse("recognized"))
    provider = _gemini_with_client(monkeypatch, models, temperature=0.7)

    provider.generate_reply("prompt", [TextPart("body")])

    _, _, config = models.calls[0]
    assert config.temperature == 0.7


def test_temperature_zero_is_kept_not_read_as_unstated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Zero is falsy, so `if temperature` would drop it.
    models = _FakeModels(response=_FakeResponse("recognized"))
    provider = _gemini_with_client(monkeypatch, models, temperature=0.0)

    provider.generate_reply("prompt", [TextPart("body")])

    _, _, config = models.calls[0]
    assert config.temperature == 0.0


# --- Gemini empty-reply reasons --------------------------------------------


def test_gemini_empty_reply_reports_a_prompt_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(
        response=_FakeResponse("", prompt_feedback=_FakeFeedback("SAFETY"))
    )
    provider = _gemini_with_client(monkeypatch, models)

    reply = provider.generate_reply("prompt")

    assert reply.text == ""
    assert reply.empty_reason is EmptyReason.BLOCKED


def test_gemini_empty_reply_reports_a_token_limit_cut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The SDK's enum renders as `FinishReason.NAME`.
    class _FinishReason:
        name = "MAX_TOKENS"

        def __str__(self) -> str:
            return "FinishReason.MAX_TOKENS"

    models = _FakeModels(
        response=_FakeResponse("", candidates=[_FakeCandidate(_FinishReason())])
    )
    provider = _gemini_with_client(monkeypatch, models)

    assert provider.generate_reply("prompt").empty_reason is EmptyReason.TRUNCATED


def test_gemini_empty_reply_reports_a_safety_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(
        response=_FakeResponse("", candidates=[_FakeCandidate("SAFETY")])
    )
    provider = _gemini_with_client(monkeypatch, models)

    assert provider.generate_reply("prompt").empty_reason is EmptyReason.BLOCKED


def test_gemini_empty_reply_without_a_stated_cause_is_no_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(
        response=_FakeResponse("", candidates=[_FakeCandidate("STOP")])
    )
    provider = _gemini_with_client(monkeypatch, models)

    assert provider.generate_reply("prompt").empty_reason is EmptyReason.NO_TEXT


def test_gemini_empty_reply_reason_reaches_the_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    models = _FakeModels(
        response=_FakeResponse("", candidates=[_FakeCandidate("MAX_TOKENS")])
    )
    provider = _gemini_with_client(monkeypatch, models)

    with caplog.at_level(logging.WARNING, logger="raw2md"):
        provider.generate_reply("prompt")

    assert "empty reply" in caplog.text
    assert "MAX_TOKENS" in caplog.text


def test_provider_reply_defaults_to_no_reason() -> None:
    # A silent provider still answers `generate_reply`.
    class _SilentProvider(Provider):
        def available(self) -> Any:
            raise NotImplementedError

        def generate(self, prompt: str, parts: Sequence[Any] = ()) -> str:
            return ""

    reply = _SilentProvider(cli_model()).generate_reply("prompt")

    assert reply.text == ""
    assert reply.empty_reason is None


def test_gemini_generate_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(error=RuntimeError("429 RESOURCE_EXHAUSTED"))
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(RateLimitError):
        provider.generate("prompt")
    assert len(models.calls) == 3


def test_gemini_generate_other_error_is_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(error=RuntimeError("boom"))
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(ProviderError) as exc_info:
        provider.generate("prompt")
    assert not isinstance(exc_info.value, RateLimitError)
    assert len(models.calls) == 1


class _CodedError(RuntimeError):
    """An SDK error carrying a `code`, as `google.genai.errors.APIError` does."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def test_gemini_generate_auth_error_by_status_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(error=_CodedError(403, "PERMISSION_DENIED"))
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(AuthError):
        provider.generate("prompt")
    assert len(models.calls) == 1


def test_gemini_generate_auth_error_by_invalid_key_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(
        error=RuntimeError(
            "400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key."
        )
    )
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(AuthError):
        provider.generate("prompt")
    assert len(models.calls) == 1


def test_gemini_generate_auth_error_by_expired_key_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _FakeModels(
        error=RuntimeError("API key expired. Please renew the API key.")
    )
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(AuthError):
        provider.generate("prompt")


def test_gemini_generate_auth_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(
        outcomes=[_CodedError(401, "UNAUTHENTICATED"), _FakeResponse("ok")]
    )
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(AuthError):
        provider.generate("prompt")
    assert len(models.calls) == 1


def test_gemini_generate_retries_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(
        outcomes=[RuntimeError("429 RESOURCE_EXHAUSTED"), _FakeResponse("recognized")]
    )
    provider = _gemini_with_client(monkeypatch, models)
    assert provider.generate("prompt") == "recognized"
    assert len(models.calls) == 2


def test_gemini_generate_retries_transient_5xx_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(
        outcomes=[RuntimeError("503 UNAVAILABLE"), _FakeResponse("recognized")]
    )
    provider = _gemini_with_client(monkeypatch, models)
    assert provider.generate("prompt") == "recognized"
    assert len(models.calls) == 2


def test_gemini_generate_transient_exhausts_to_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A persistent 5xx ends as a TransientError, apart from a rate limit.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(error=RuntimeError("503 UNAVAILABLE"))
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(TransientError):
        provider.generate("prompt")
    assert len(models.calls) == 3


def test_gemini_generate_retries_a_dropped_socket_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A socket failure has no status text, so its type identifies it.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(
        outcomes=[
            ConnectionResetError("Connection reset by peer"),
            _FakeResponse("recognized"),
        ]
    )
    provider = _gemini_with_client(monkeypatch, models)
    assert provider.generate("prompt") == "recognized"
    assert len(models.calls) == 2


def test_gemini_generate_retries_an_httpx_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # httpx raises this when a connection drops mid-request.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(
        outcomes=[
            httpx.ConnectError("All connection attempts failed"),
            _FakeResponse("recognized"),
        ]
    )
    provider = _gemini_with_client(monkeypatch, models)
    assert provider.generate("prompt") == "recognized"
    assert len(models.calls) == 2


def test_gemini_dropped_connection_exhausts_to_the_same_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A lost connection ends like an exhausted 5xx: the typed error propagates.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(error=ConnectionResetError("Connection reset by peer"))
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(ConnectionDroppedError):
        provider.generate("prompt")
    assert len(models.calls) == 6


def test_gemini_dropped_connection_backoff_grows_into_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An outage clears slower than an overload, so the wait keeps doubling up
    # to a minute.
    sleeps: list[float] = []
    monkeypatch.setattr("raw2md.llm.base._sleep", sleeps.append)
    models = _FakeModels(error=ConnectionResetError("Connection reset by peer"))
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(ConnectionDroppedError):
        provider.generate("prompt")
    assert sleeps == [4.0, 8.0, 16.0, 32.0, 64.0]


def test_gemini_local_os_error_is_not_a_dropped_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The rpd state write raises inside the same try; a local error is no
    # dropped connection.
    models = _FakeModels(error=PermissionError("Permission denied"))
    provider = _gemini_with_client(monkeypatch, models)
    with pytest.raises(ProviderError) as exc_info:
        provider.generate("prompt")
    assert not isinstance(exc_info.value, ConnectionDroppedError)
    assert len(models.calls) == 1


# rpm 15 with the 0.8 margin: 60/(15*0.8) = 5.0s, not a bare 4.0s.
_RPM_15_INTERVAL_S = 60.0 / (15 * 0.8)


def test_gemini_throttles_by_rpm(monkeypatch: pytest.MonkeyPatch) -> None:
    # No elapsed time, so the full margined interval.
    sleeps: list[float] = []
    clock = iter([100.0, 100.0, 104.0])
    monkeypatch.setattr("raw2md.llm.base._sleep", sleeps.append)
    monkeypatch.setattr("raw2md.llm.base._monotonic", lambda: next(clock))
    models = _FakeModels(response=_FakeResponse("ok"))
    provider = GeminiApiProvider(api_model(rpm=15))
    monkeypatch.setattr(provider, "_create_client", lambda: _FakeClient(models))

    provider.generate("prompt")
    provider.generate("prompt")

    assert sleeps == [pytest.approx(_RPM_15_INTERVAL_S)]


def test_gemini_throttles_retry_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    # A 2s backoff leaves the rest of the interval as throttle.
    sleeps: list[float] = []
    clock = iter([100.0, 102.0, 104.0])
    monkeypatch.setattr("raw2md.llm.base._sleep", sleeps.append)
    monkeypatch.setattr("raw2md.llm.base._monotonic", lambda: next(clock))
    models = _FakeModels(
        outcomes=[RuntimeError("503 UNAVAILABLE"), _FakeResponse("ok")]
    )
    provider = GeminiApiProvider(api_model(rpm=15))
    monkeypatch.setattr(provider, "_create_client", lambda: _FakeClient(models))

    assert provider.generate("prompt") == "ok"
    assert sleeps == [2.0, pytest.approx(_RPM_15_INTERVAL_S - 2.0)]
    assert len(models.calls) == 2


def test_gemini_rpm_throttle_keeps_sliding_window_under_declared_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A bare 60/rpm spacing lets one extra request into a sliding 60s window.
    now = [0.0]
    monkeypatch.setattr("raw2md.llm.base._monotonic", lambda: now[0])

    def fake_sleep(seconds: float) -> None:
        now[0] += seconds

    monkeypatch.setattr("raw2md.llm.base._sleep", fake_sleep)
    models = _FakeModels(response=_FakeResponse("ok"))
    provider = GeminiApiProvider(api_model(rpm=15))
    monkeypatch.setattr(provider, "_create_client", lambda: _FakeClient(models))

    timestamps: list[float] = []
    for _ in range(60):
        provider.generate("prompt")
        timestamps.append(now[0])

    max_in_any_window = max(
        sum(1 for t in timestamps if start <= t < start + 60.0) for start in timestamps
    )
    assert max_in_any_window <= 15


# --- Gemini rpd (daily quota) -----------------------------------------------


def test_gemini_rpd_zone_defaults_to_the_provider_reset_zone() -> None:
    # The free-tier quota resets at midnight Pacific time.
    provider = GeminiApiProvider(api_model())
    assert provider._rpd_zone == "America/Los_Angeles"


def test_gemini_rpd_zone_honors_a_declared_zone() -> None:
    provider = GeminiApiProvider(api_model(rpd_reset_zone="UTC"))
    assert provider._rpd_zone == "UTC"


def test_gemini_daily_quota_stops_before_sending(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    # A spent budget refuses before the network, not with a provider 429.
    models = _FakeModels(response=_FakeResponse("ok"))
    provider = GeminiApiProvider(api_model(rpd=1))
    monkeypatch.setattr(provider, "_create_client", lambda: _FakeClient(models))

    assert provider.generate("prompt") == "ok"
    with pytest.raises(DailyQuotaExceededError, match="daily limit"):
        provider.generate("prompt")

    assert len(models.calls) == 1  # the refused attempt never reached the network


def test_gemini_daily_quota_survives_a_fresh_provider(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    # The count lives on disk, so a new provider sees earlier spending.
    models = _FakeModels(response=_FakeResponse("ok"))
    first = GeminiApiProvider(api_model(rpd=1))
    monkeypatch.setattr(first, "_create_client", lambda: _FakeClient(models))
    first.generate("prompt")

    second = GeminiApiProvider(api_model(rpd=1))
    monkeypatch.setattr(second, "_create_client", lambda: _FakeClient(models))
    with pytest.raises(DailyQuotaExceededError):
        second.generate("prompt")


def test_gemini_daily_quota_does_not_leak_between_models(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    models = _FakeModels(response=_FakeResponse("ok"))
    exhausted = GeminiApiProvider(api_model(rpd=1))
    monkeypatch.setattr(exhausted, "_create_client", lambda: _FakeClient(models))
    exhausted.generate("prompt")
    with pytest.raises(DailyQuotaExceededError):
        exhausted.generate("prompt")

    other = ModelConfig(
        access="api",
        model="gemini-other",
        key_env="GOOGLE_API_KEY",
        command=None,
        rpm=None,
        tpm=None,
        rpd=1,
    )
    fresh = GeminiApiProvider(other)
    monkeypatch.setattr(fresh, "_create_client", lambda: _FakeClient(models))
    assert fresh.generate("prompt") == "ok"


def test_gemini_no_rpd_declared_is_never_capped(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    # Without `rpd` there is no cap and no state file.
    models = _FakeModels(response=_FakeResponse("ok"))
    provider = _gemini_with_client(monkeypatch, models)

    for _ in range(3):
        assert provider.generate("prompt") == "ok"

    assert not rpd_file().exists()


def test_gemini_upload_failure_does_not_spend_rpd(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    # The metered call was never made, so no slot is spent.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    provider = GeminiApiProvider(api_model(rpd=5, max_request_bytes=1000))
    client = _FakeClient(
        _FakeModels(response=_FakeResponse("ok")),
        _FakeFiles(upload_error=RuntimeError("429 RESOURCE_EXHAUSTED")),
    )
    monkeypatch.setattr(provider, "_create_client", lambda: client)

    with pytest.raises(RateLimitError):
        provider.generate("p", [MediaPart(b"\0" * 900, "application/pdf")])

    assert not rpd_file().exists()


def test_gemini_retry_counts_against_rpd(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    # A retry is a real request and spends a slot.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    models = _FakeModels(
        outcomes=[RuntimeError("503 UNAVAILABLE"), _FakeResponse("ok")]
    )
    provider = GeminiApiProvider(api_model(rpd=5))
    monkeypatch.setattr(provider, "_create_client", lambda: _FakeClient(models))

    assert provider.generate("prompt") == "ok"

    counts = json.loads(rpd_file().read_text(encoding="utf-8"))["counts"]
    assert counts["gemini-2.5-flash"]["count"] == 2


def test_gemini_retry_honors_server_retry_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A longer RetryInfo delay wins over the fixed backoff.
    sleeps: list[float] = []
    monkeypatch.setattr("raw2md.llm.base._sleep", sleeps.append)
    models = _FakeModels(
        outcomes=[
            RuntimeError(
                "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, "
                "'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
                "'retryDelay': '31.6s'}]}}"
            ),
            _FakeResponse("ok"),
        ]
    )
    provider = _gemini_with_client(monkeypatch, models)

    assert provider.generate("prompt") == "ok"

    assert sleeps == [pytest.approx(31.6)]


def test_gemini_retry_without_retry_delay_uses_fixed_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("raw2md.llm.base._sleep", sleeps.append)
    models = _FakeModels(
        outcomes=[RuntimeError("429 RESOURCE_EXHAUSTED"), _FakeResponse("ok")]
    )
    provider = _gemini_with_client(monkeypatch, models)

    assert provider.generate("prompt") == "ok"

    assert sleeps == [2.0]


def test_gemini_generate_too_large() -> None:
    # Text over the ceiling has no route left; no client is built.
    provider = GeminiApiProvider(api_model(max_request_bytes=8))
    with pytest.raises(DocumentTooLargeError):
        provider.generate("prompt", [TextPart("0123456789")])


def test_gemini_default_limit_is_the_inline_ceiling() -> None:
    provider = GeminiApiProvider(api_model())
    assert provider.request_byte_limit == DEFAULT_MAX_REQUEST_BYTES
    with pytest.raises(DocumentTooLargeError):
        provider.generate("prompt", [TextPart("x" * (DEFAULT_MAX_REQUEST_BYTES + 1))])


def test_settings_byte_limit_overrides_the_default() -> None:
    # The guard and the chunk planner read the ceiling off the provider.
    provider = GeminiApiProvider(api_model(max_request_bytes=1024))
    assert provider.request_byte_limit == 1024


# --- Gemini media route ----------------------------------------------------


def test_media_counts_at_its_encoded_size(monkeypatch: pytest.MonkeyPatch) -> None:
    # 800 bytes fit 1000 as a file but not as base64, so the media uploads.
    files = _FakeFiles()
    provider = _gemini_with_client(
        monkeypatch,
        _FakeModels(response=_FakeResponse("ok")),
        files=files,
        max_request_bytes=1000,
    )

    assert provider.generate("prompt", [MediaPart(b"\0" * 800, "application/pdf")])

    assert len(files.uploads) == 1


def test_media_that_fits_stays_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    # Under the ceiling the bytes ride inline and nothing is uploaded.
    files = _FakeFiles()
    models = _FakeModels(response=_FakeResponse("ok"))
    provider = _gemini_with_client(
        monkeypatch, models, files=files, max_request_bytes=1000
    )

    provider.generate("prompt", [MediaPart(b"\0" * 600, "image/png")])

    assert files.uploads == []
    _, contents, _ = models.calls[0]
    assert contents[1].inline_data is not None


def test_oversize_media_travels_by_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    # A URI is sent, and the upload is deleted after the reply.
    files = _FakeFiles()
    models = _FakeModels(response=_FakeResponse("ok"))
    provider = _gemini_with_client(
        monkeypatch, models, files=files, max_request_bytes=1000
    )

    provider.generate("prompt", [MediaPart(b"\0" * 900, "application/pdf")])

    assert files.uploads == [(b"\0" * 900, "application/pdf")]
    _, contents, _ = models.calls[0]
    file_data = contents[1].file_data
    assert file_data.file_uri.endswith("files/abc")
    assert file_data.mime_type == "application/pdf"
    assert files.deleted == ["files/abc"]


def test_upload_waits_for_processing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Referencing a file still processing gets a 400.
    monkeypatch.setattr("raw2md.llm.gemini._sleep", lambda seconds: None)
    files = _FakeFiles(states=["PROCESSING", "PROCESSING", "ACTIVE"])
    provider = _gemini_with_client(
        monkeypatch,
        _FakeModels(response=_FakeResponse("ok")),
        files=files,
        max_request_bytes=1000,
    )

    assert provider.generate("p", [MediaPart(b"\0" * 900, "application/pdf")]) == "ok"

    assert files.gets == ["files/abc", "files/abc"]


def test_upload_stuck_in_processing_is_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A file that never turns usable is transient: the retry uploads again.
    monkeypatch.setattr("raw2md.llm.gemini._sleep", lambda seconds: None)
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    # Each attempt reads the clock twice.
    clock = itertools.cycle([0.0, 1e6])
    monkeypatch.setattr("raw2md.llm.gemini._monotonic", lambda: next(clock))
    provider = _gemini_with_client(
        monkeypatch,
        _FakeModels(response=_FakeResponse("ok")),
        files=_FakeFiles(states=["PROCESSING"]),
        max_request_bytes=1000,
    )

    with pytest.raises(TransientError):
        provider.generate("p", [MediaPart(b"\0" * 900, "application/pdf")])


def test_refused_upload_is_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # The same bytes fail again, so no retry; the copy is still cleaned up.
    files = _FakeFiles(states=["FAILED"], error=_FakeFileError("unsupported"))
    provider = _gemini_with_client(
        monkeypatch,
        _FakeModels(response=_FakeResponse("ok")),
        files=files,
        max_request_bytes=1000,
    )

    with pytest.raises(ProviderError, match="unsupported"):
        provider.generate("p", [MediaPart(b"\0" * 900, "application/pdf")])

    assert files.deleted == ["files/abc"]


def test_uploaded_file_is_deleted_after_a_failed_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    files = _FakeFiles()
    provider = _gemini_with_client(
        monkeypatch,
        _FakeModels(error=RuntimeError("boom")),
        files=files,
        max_request_bytes=1000,
    )

    with pytest.raises(ProviderError):
        provider.generate("p", [MediaPart(b"\0" * 900, "application/pdf")])

    assert files.deleted == ["files/abc"]


def test_failed_delete_keeps_the_reply(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Losing the reply over a cleanup error would waste the upload.
    files = _FakeFiles(delete_error=RuntimeError("gone"))
    provider = _gemini_with_client(
        monkeypatch,
        _FakeModels(response=_FakeResponse("ok")),
        files=files,
        max_request_bytes=1000,
    )

    with caplog.at_level(logging.WARNING, logger="raw2md"):
        assert provider.generate("p", [MediaPart(b"\0" * 900, "application/pdf")]) == (
            "ok"
        )

    assert "could not delete" in caplog.text


def test_upload_failure_is_classified(monkeypatch: pytest.MonkeyPatch) -> None:
    # Upload failures join the same typed family.
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    provider = _gemini_with_client(
        monkeypatch,
        _FakeModels(response=_FakeResponse("ok")),
        files=_FakeFiles(upload_error=RuntimeError("429 RESOURCE_EXHAUSTED")),
        max_request_bytes=1000,
    )

    with pytest.raises(RateLimitError):
        provider.generate("p", [MediaPart(b"\0" * 900, "application/pdf")])


# --- Claude availability ---------------------------------------------------


def _fake_auth_status(stdout: str) -> Any:
    def fake(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        return _fake_completed(0, stdout=stdout)

    return fake


def test_claude_available_with_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: "/usr/bin/claude")
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout",
        _fake_auth_status(json.dumps({"loggedIn": True})),
    )
    assert build_provider(cli_model()).available().ok is True


def test_claude_unavailable_without_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: None)
    availability = build_provider(cli_model("ghost")).available()
    assert availability.ok is False
    assert "ghost" in (availability.reason or "")


def test_claude_unavailable_when_not_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    # A probe that meets the same refusal a request would gets caught here,
    # before conversion starts.
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: "/usr/bin/claude")
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout",
        _fake_auth_status(json.dumps({"loggedIn": False})),
    )
    availability = build_provider(cli_model()).available()
    assert availability.ok is False
    assert "not logged in" in (availability.reason or "")


def test_claude_available_despite_a_probe_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The probe cannot tell a real outage from a bad login by failing, so it
    # leaves the call to the run's own requests.
    def fake(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: "/usr/bin/claude")
    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake)
    assert build_provider(cli_model()).available().ok is True


def test_claude_available_despite_unparsable_probe_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: "/usr/bin/claude")
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout", _fake_auth_status("not json")
    )
    assert build_provider(cli_model()).available().ok is True


# --- Claude generate -------------------------------------------------------


def _fake_completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_claude_generate_returns_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_with_timeout(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["input"] = input_text
        return _fake_completed(0, stdout="fixed text")

    # The bare name has no .cmd extension, so no cmd.exe wrapping.
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake_run_with_timeout)
    provider = ClaudeCliProvider(cli_model())
    result = provider.generate("instructions", [TextPart("zone")])
    assert result == "fixed text"
    assert captured["argv"] == ["claude", "-p", "--model", "claude-sonnet-4-6"]
    assert "instructions" in captured["input"]
    assert "zone" in captured["input"]


def test_claude_generate_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    calls: list[list[str]] = []

    def fake_run_with_timeout(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _fake_completed(1, stderr="rate limit exceeded")

    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake_run_with_timeout)
    with pytest.raises(RateLimitError):
        ClaudeCliProvider(cli_model()).generate("prompt")
    assert len(calls) == 3


def test_claude_generate_auth_error_uses_stdout_when_stderr_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A refused login prints to stdout, not stderr, unlike every other CLI
    # failure this provider maps.
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout",
        lambda argv, input_text, timeout: _fake_completed(
            1, stdout="Not logged in · Please run /login"
        ),
    )
    with pytest.raises(AuthError, match="Not logged in"):
        ClaudeCliProvider(cli_model()).generate("prompt")


def test_claude_generate_auth_error_in_stdout_despite_a_stderr_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout",
        lambda argv, input_text, timeout: _fake_completed(
            1,
            stdout="Not logged in · Please run /login",
            stderr="Warning: a newer version is available",
        ),
    )
    with pytest.raises(AuthError, match="Not logged in"):
        ClaudeCliProvider(cli_model()).generate("prompt")


def test_claude_generate_auth_error_from_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout",
        lambda argv, input_text, timeout: _fake_completed(
            1, stderr="please run /login to continue"
        ),
    )
    with pytest.raises(AuthError):
        ClaudeCliProvider(cli_model()).generate("prompt")


def test_claude_not_throttled_without_rpm(monkeypatch: pytest.MonkeyPatch) -> None:
    # The default CLI model declares no rpm.
    sleeps: list[float] = []
    monkeypatch.setattr("raw2md.llm.base._sleep", sleeps.append)
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout",
        lambda argv, input_text, timeout: _fake_completed(0, stdout="ok"),
    )
    provider = ClaudeCliProvider(cli_model())
    provider.generate("prompt")
    provider.generate("prompt")
    assert sleeps == []


def test_claude_generate_error_is_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr(
        "raw2md.llm.claude._run_with_timeout",
        lambda argv, input_text, timeout: _fake_completed(2, stderr="boom"),
    )
    with pytest.raises(ProviderError) as exc_info:
        ClaudeCliProvider(cli_model()).generate("prompt")
    assert not isinstance(exc_info.value, RateLimitError)


def test_claude_generate_rejects_media() -> None:
    with pytest.raises(ValueError, match="no vision"):
        ClaudeCliProvider(cli_model()).generate("p", [MediaPart(b"x", "image/png")])


def test_claude_generate_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_with_timeout(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("no such command")

    # Without a match _resolve_command keeps the bare name.
    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: None)
    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake_run_with_timeout)
    with pytest.raises(ProviderError):
        ClaudeCliProvider(cli_model()).generate("prompt")


def test_claude_generate_timeout_is_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_with_timeout(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake_run_with_timeout)
    with pytest.raises(ProviderError, match="timed out") as exc_info:
        ClaudeCliProvider(cli_model()).generate("prompt")
    assert not isinstance(exc_info.value, RateLimitError)


def test_claude_uses_default_timeout_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Without `cli_timeout_s` the 120s fallback holds.
    captured: dict[str, float] = {}

    def fake_run_with_timeout(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        captured["timeout"] = timeout
        return _fake_completed(0, stdout="ok")

    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake_run_with_timeout)
    ClaudeCliProvider(cli_model()).generate("prompt")
    assert captured["timeout"] == DEFAULT_CLAUDE_TIMEOUT_S


def test_claude_uses_configured_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, float] = {}

    def fake_run_with_timeout(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        captured["timeout"] = timeout
        return _fake_completed(0, stdout="ok")

    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake_run_with_timeout)
    ClaudeCliProvider(cli_model(cli_timeout_s=600)).generate("prompt")
    assert captured["timeout"] == 600


def test_claude_timeout_message_names_the_configured_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_with_timeout(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr("raw2md.llm.claude.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr("raw2md.llm.claude._run_with_timeout", fake_run_with_timeout)
    with pytest.raises(ProviderError, match="timed out after 600s"):
        ClaudeCliProvider(cli_model(cli_timeout_s=600)).generate("prompt")


# --- _resolve_command -------------------------------------------------------


def test_resolve_command_wraps_ps1_with_powershell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from raw2md.llm.claude import _resolve_command

    monkeypatch.setattr("raw2md.llm.claude.sys.platform", "win32")
    monkeypatch.setattr(
        "raw2md.llm.claude.shutil.which", lambda cmd: r"C:\tools\claude.ps1"
    )

    assert _resolve_command("claude") == [
        "powershell",
        "-File",
        r"C:\tools\claude.ps1",
    ]


def test_resolve_command_wraps_cmd_with_cmd_exe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # .cmd/.bat get the cmd.exe wrapper.
    from raw2md.llm.claude import _resolve_command

    monkeypatch.setattr("raw2md.llm.claude.sys.platform", "win32")
    monkeypatch.setattr(
        "raw2md.llm.claude.shutil.which", lambda cmd: r"C:\tools\claude.cmd"
    )

    assert _resolve_command("claude") == ["cmd.exe", "/c", r"C:\tools\claude.cmd"]


def test_resolve_command_ps1_unwrapped_off_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The wrapper is a Windows-only CreateProcess workaround.
    from raw2md.llm.claude import _resolve_command

    monkeypatch.setattr("raw2md.llm.claude.sys.platform", "linux")
    monkeypatch.setattr(
        "raw2md.llm.claude.shutil.which", lambda cmd: "/opt/tools/claude.ps1"
    )

    assert _resolve_command("claude") == ["/opt/tools/claude.ps1"]


# --- Claude process-tree kill on timeout -----------------------------------


def test_run_with_timeout_kills_tree_when_process_hangs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A timeout kills only the immediate process, not a cmd.exe wrapper's
    # tree.
    from raw2md.llm.claude import _run_with_timeout

    class _FakeProcess:
        pid = 4321
        returncode = 0

        def communicate(
            self,
            input: str | None = None,  # noqa: A002 -- matches subprocess.Popen.communicate's own parameter name
            timeout: float | None = None,
        ) -> tuple[str, str]:
            raise subprocess.TimeoutExpired(["claude"], timeout or 0)

        def wait(self) -> None:
            pass

    killed: list[int] = []
    monkeypatch.setattr("raw2md.llm.claude._spawn", lambda argv: _FakeProcess())
    monkeypatch.setattr("raw2md.llm.claude._kill_tree", killed.append)

    with pytest.raises(subprocess.TimeoutExpired):
        _run_with_timeout(["claude"], "input", 5)

    assert killed == [4321]


def test_kill_tree_uses_taskkill_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    from raw2md.llm.claude import _kill_tree

    calls: list[list[str]] = []
    monkeypatch.setattr("raw2md.llm.claude.sys.platform", "win32")
    monkeypatch.setattr(
        "raw2md.llm.claude.subprocess.run",
        lambda cmd, **kwargs: calls.append(cmd),
    )

    _kill_tree(4321)

    assert calls == [["taskkill", "/F", "/T", "/PID", "4321"]]


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="os.killpg and signal.SIGKILL are POSIX-only",
)
def test_kill_tree_uses_killpg_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mirrors the skip marker, so mypy on Windows treats SIGKILL as unreachable.
    if sys.platform == "win32":
        return
    import signal

    from raw2md.llm.claude import _kill_tree

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "raw2md.llm.claude.os.killpg", lambda pid, sig: calls.append((pid, sig))
    )

    _kill_tree(4321)

    assert calls == [(4321, signal.SIGKILL)]


def test_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        Provider(api_model())  # type: ignore[abstract]
