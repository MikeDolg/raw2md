"""Tests for the OpenRouter provider, through the real SDK over a fake transport."""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
from collections.abc import Callable
from email.utils import format_datetime
from typing import Any

import httpx
import pytest
from openrouter import OpenRouter

from raw2md.llm import (
    AuthError,
    ConnectionDroppedError,
    DocumentTooLargeError,
    MediaPart,
    OpenRouterApiProvider,
    ProviderError,
    RateLimitError,
    TextPart,
    TransientError,
    build_provider,
)
from raw2md.llm.base import EmptyReason
from raw2md.llm.openrouter import _retry_after
from raw2md.settings import ModelConfig

_MODEL = "vendor/model-small"

Handler = Callable[[httpx.Request], httpx.Response]


def or_model(
    max_request_bytes: int | None = None, temperature: float | None = None
) -> ModelConfig:
    return ModelConfig(
        access="openrouter_api",
        model=_MODEL,
        key_env="OPENROUTER_API_KEY",
        command=None,
        rpm=None,
        tpm=None,
        rpd=None,
        max_request_bytes=max_request_bytes,
        temperature=temperature,
    )


class _Wire:
    """A provider whose SDK client talks to `handler` instead of the network."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        handler: Handler,
        model: ModelConfig | None = None,
    ) -> None:
        self.requests: list[httpx.Request] = []
        self.provider = OpenRouterApiProvider(model or or_model())

        def record(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        def create_client() -> OpenRouter:
            # A supplied async client too: the SDK would build one with a TLS
            # context, close to a second per client.
            transport = httpx.MockTransport(record)
            return OpenRouter(
                api_key="test-key",
                client=httpx.Client(transport=transport),
                async_client=httpx.AsyncClient(transport=transport),
                retry_config=None,
                timeout_ms=OpenRouterApiProvider._REQUEST_TIMEOUT_MS,
            )

        monkeypatch.setattr(self.provider, "_create_client", create_client)
        monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)

    def body(self, index: int = 0) -> dict[str, Any]:
        decoded: dict[str, Any] = json.loads(self.requests[index].content)
        return decoded


def _result(
    content: Any = "reply text",
    finish: str | None = "stop",
    model: str = _MODEL,
    **message: Any,
) -> dict[str, Any]:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "system_fingerprint": None,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content, **message},
            }
        ],
    }


def _ok(payload: dict[str, Any]) -> Handler:
    return lambda request: httpx.Response(200, json=payload)


def _error(
    status: int,
    metadata: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    http_status: int | None = None,
) -> httpx.Response:
    error: dict[str, Any] = {"code": status, "message": "declined"}
    if metadata is not None:
        error["metadata"] = metadata
    return httpx.Response(
        http_status or status, json={"error": error}, headers=headers or {}
    )


def _sequence(*responses: httpx.Response) -> Handler:
    queue = list(responses)
    return lambda request: queue.pop(0) if len(queue) > 1 else queue[0]


# --- Factory -----------------------------------------------------------------


def test_build_provider_maps_the_openrouter_access() -> None:
    provider = build_provider(or_model())
    assert isinstance(provider, OpenRouterApiProvider)
    assert provider.supports_vision is True


# --- Request body ------------------------------------------------------------


def test_request_carries_the_parts_in_order_as_data_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, _ok(_result()))
    png, pdf = b"\x89PNG fake", b"%PDF-1.7 fake"
    reply = wire.provider.generate_reply(
        "the prompt",
        [
            TextPart("zone"),
            MediaPart(png, "image/png"),
            MediaPart(pdf, "application/pdf"),
        ],
    )
    assert reply.text == "reply text"
    body = wire.body()
    assert wire.requests[0].url.path.endswith("/chat/completions")
    assert body["model"] == _MODEL
    content = body["messages"][0]["content"]
    assert body["messages"][0]["role"] == "user"
    assert [item["type"] for item in content] == ["text", "text", "image_url", "file"]
    assert content[0]["text"] == "the prompt"
    assert content[1]["text"] == "zone"
    png_url = "data:image/png;base64," + base64.b64encode(png).decode()
    assert content[2]["image_url"]["url"] == png_url
    pdf_url = "data:application/pdf;base64," + base64.b64encode(pdf).decode()
    assert content[3]["file"]["file_data"] == pdf_url


def test_every_request_fixes_the_plugin_and_the_provider_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, _ok(_result()))
    wire.provider.generate("prompt")
    body = wire.body()
    assert body["plugins"] == [{"id": "file-parser", "pdf": {"engine": "native"}}]
    assert body["provider"] == {"data_collection": "deny", "require_parameters": True}
    assert "response_format" not in body
    assert "temperature" not in body


def test_a_schema_goes_as_a_strict_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, _ok(_result('{"edits": []}')))
    schema = {"type": "object", "properties": {"edits": {"type": "array"}}}
    wire.provider.generate_reply("prompt", response_schema=schema)
    response_format = wire.body()["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] == schema
    assert response_format["json_schema"]["name"]


def test_a_stated_temperature_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    wire = _Wire(monkeypatch, _ok(_result()), or_model(temperature=0.0))
    wire.provider.generate("prompt")
    assert wire.body()["temperature"] == 0.0


def test_a_request_over_the_byte_limit_is_refused_before_it_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, _ok(_result()), or_model(max_request_bytes=1000))
    with pytest.raises(DocumentTooLargeError, match="1000-byte limit"):
        wire.provider.generate("prompt", [MediaPart(b"x" * 900, "application/pdf")])
    assert wire.requests == []


def test_the_byte_limit_counts_the_media_as_base64(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 600 raw bytes weigh 800 once encoded; the prompt adds 6.
    wire = _Wire(monkeypatch, _ok(_result()), or_model(max_request_bytes=806))
    wire.provider.generate("prompt", [MediaPart(b"x" * 600, "image/png")])
    assert len(wire.requests) == 1


def test_an_unknown_media_type_is_refused_before_it_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, _ok(_result()))
    with pytest.raises(ProviderError, match="image/tiff"):
        wire.provider.generate("prompt", [MediaPart(b"II*", "image/tiff")])
    assert wire.requests == []


# --- Replies -----------------------------------------------------------------


def test_a_reply_of_content_items_joins_their_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = [{"type": "text", "text": "first "}, {"type": "text", "text": "second"}]
    wire = _Wire(monkeypatch, _ok(_result(items)))
    assert wire.provider.generate("prompt") == "first second"


def test_usage_goes_to_the_log_with_the_model_of_the_reply(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _result(model="vendor/model-small-20260101")
    payload["usage"] = {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "total_tokens": 1500,
        "cost": 0.00027,
        "prompt_tokens_details": {"cached_tokens": 100},
        "completion_tokens_details": {"reasoning_tokens": 120},
    }
    wire = _Wire(monkeypatch, _ok(payload))
    with caplog.at_level(logging.INFO, logger="raw2md"):
        wire.provider.generate("prompt")
    line = next(r.getMessage() for r in caplog.records if "input tokens" in r.message)
    assert line == (
        "llm: vendor/model-small-20260101 used 1200 input tokens (100 cached), "
        "300 output tokens (120 reasoning), cost 0.00027 USD"
    )


def test_a_reply_cut_short_keeps_its_text_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    wire = _Wire(monkeypatch, _ok(_result("partial", finish="length")))
    with caplog.at_level(logging.WARNING, logger="raw2md"):
        assert wire.provider.generate("prompt") == "partial"
    assert "cut short (finish_reason length)" in caplog.text


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (_result("", finish="length"), EmptyReason.TRUNCATED),
        (_result(None, finish="content_filter"), EmptyReason.BLOCKED),
        (_result(None, finish="stop", refusal="I cannot help."), EmptyReason.BLOCKED),
        (_result("  ", finish="stop"), EmptyReason.NO_TEXT),
        (_result(None, finish=None), EmptyReason.NO_TEXT),
    ],
)
def test_an_empty_reply_takes_its_reason_from_the_finish(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any], reason: EmptyReason
) -> None:
    wire = _Wire(monkeypatch, _ok(payload))
    reply = wire.provider.generate_reply("prompt")
    assert reply.text == ""
    assert reply.empty_reason is reason
    assert len(wire.requests) == 1


def test_a_generation_failed_after_the_200_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = httpx.Response(200, json=_result("partial", finish="error"))
    wire = _Wire(monkeypatch, _sequence(failed, httpx.Response(200, json=_result())))
    assert wire.provider.generate("prompt") == "reply text"
    assert len(wire.requests) == 2


def _choice_error(status: int, metadata: dict[str, Any]) -> Handler:
    payload = _result("", finish="error")
    payload["choices"][0]["error"] = {
        "code": status,
        "message": "declined",
        "metadata": metadata,
    }
    return _ok(payload)


def test_a_choice_error_for_policy_is_a_blocked_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _choice_error(403, {"error_type": "content_policy_violation"})
    wire = _Wire(monkeypatch, handler)
    reply = wire.provider.generate_reply("prompt")
    assert reply.empty_reason is EmptyReason.BLOCKED
    assert len(wire.requests) == 1


def test_a_choice_error_for_rate_limit_is_a_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, _choice_error(429, {}))
    with pytest.raises(RateLimitError):
        wire.provider.generate("prompt")


def test_a_choice_error_does_not_leak_into_the_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(
        monkeypatch,
        _sequence(
            httpx.Response(200, json=_result("", finish="error")),
            httpx.Response(200, json=_result()),
        ),
    )
    assert wire.provider.generate("prompt") == "reply text"
    wire.provider._seen.choice_error = ("stale", {})
    assert wire.provider.generate("prompt") == "reply text"


def test_a_generation_that_keeps_failing_raises_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, _ok(_result("partial", finish="error")))
    with pytest.raises(TransientError):
        wire.provider.generate("prompt")
    assert len(wire.requests) == 3


def test_a_reply_without_choices_is_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _result()
    payload["choices"] = []
    wire = _Wire(monkeypatch, _ok(payload))
    with pytest.raises(ProviderError, match="no choices"):
        wire.provider.generate("prompt")
    assert len(wire.requests) == 1


def test_a_200_body_without_choices_or_error_is_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, lambda request: httpx.Response(200, json={"id": "x"}))
    with pytest.raises(ProviderError, match="holds no error") as info:
        wire.provider.generate("prompt")
    assert type(info.value) is ProviderError


# --- Error mapping -----------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "error_type", "attempts"),
    [
        (_error(401), AuthError, 1),
        (_error(403, {"error_type": "permission_denied"}), AuthError, 1),
        (_error(403, {"limit_source": "openrouter_key_limit"}), AuthError, 1),
        (_error(402), AuthError, 1),
        (_error(402, {"limit_source": "openrouter_credits"}), AuthError, 1),
        (_error(429), RateLimitError, 3),
        (_error(408), TransientError, 3),
        (_error(500, {"error_type": "server"}), TransientError, 3),
        (_error(502), TransientError, 3),
        (_error(503), TransientError, 3),
        (_error(504), TransientError, 3),
        (_error(413), DocumentTooLargeError, 1),
        (_error(400, {"error_type": "invalid_request"}), ProviderError, 1),
    ],
)
def test_an_error_status_maps_onto_the_typed_family(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
    error_type: type[ProviderError],
    attempts: int,
) -> None:
    wire = _Wire(monkeypatch, lambda request: response)
    with pytest.raises(ProviderError) as info:
        wire.provider.generate("prompt")
    assert type(info.value) is error_type
    assert len(wire.requests) == attempts


def test_a_200_body_with_only_an_error_maps_by_its_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limited = _error(429, {"error_type": "rate_limit_exceeded"}, http_status=200)
    wire = _Wire(monkeypatch, lambda request: rate_limited)
    with pytest.raises(RateLimitError):
        wire.provider.generate("prompt")
    assert len(wire.requests) == 3


def test_a_200_body_with_a_provider_failure_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = _error(502, {"error_type": "provider_unavailable"}, http_status=200)
    wire = _Wire(monkeypatch, _sequence(upstream, httpx.Response(200, json=_result())))
    assert wire.provider.generate("prompt") == "reply text"


def test_a_rate_limit_carries_the_retry_after_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, lambda request: _error(429, headers={"Retry-After": "7"}))
    with pytest.raises(RateLimitError) as info:
        wire.provider.generate("prompt")
    assert info.value.retry_after == 7.0


def test_a_spent_in_flight_budget_is_a_rate_limit_with_its_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = {
        "reason": "in_flight_budget_exhausted",
        "limit_source": "openrouter_in_flight_budget",
    }
    response = _error(402, metadata, headers={"Retry-After": "9"})
    wire = _Wire(monkeypatch, lambda request: response)
    with pytest.raises(RateLimitError) as info:
        wire.provider.generate("prompt")
    assert info.value.retry_after == 9.0
    assert len(wire.requests) == 3


def test_a_refused_access_is_kept_for_the_rest_of_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = _Wire(monkeypatch, lambda request: _error(402))
    for _ in range(2):
        with pytest.raises(AuthError):
            wire.provider.generate("prompt")
    assert len(wire.requests) == 1


@pytest.mark.parametrize("error_type", ["content_policy_violation", "refusal"])
@pytest.mark.parametrize("http_status", [403, 200])
def test_a_policy_refusal_is_an_empty_blocked_reply(
    monkeypatch: pytest.MonkeyPatch, error_type: str, http_status: int
) -> None:
    response = _error(403, {"error_type": error_type}, http_status=http_status)
    wire = _Wire(monkeypatch, lambda request: response)
    reply = wire.provider.generate_reply("prompt")
    assert reply.text == ""
    assert reply.empty_reason is EmptyReason.BLOCKED
    assert len(wire.requests) == 1


def test_a_transport_failure_is_a_dropped_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    wire = _Wire(monkeypatch, refuse)
    with pytest.raises(ConnectionDroppedError):
        wire.provider.generate("prompt")
    assert len(wire.requests) == 6


def test_a_dropped_connection_is_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[None] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(None)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json=_result())

    wire = _Wire(monkeypatch, flaky)
    assert wire.provider.generate("prompt") == "reply text"


def test_retry_after_reads_an_http_date() -> None:
    later = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=30)
    wait = _retry_after(
        httpx.Headers({"Retry-After": format_datetime(later, usegmt=True)})
    )
    assert wait is not None
    assert 25.0 <= wait <= 30.0


@pytest.mark.parametrize("value", ["", "soon"])
def test_retry_after_without_a_readable_value_is_none(value: str) -> None:
    assert _retry_after(httpx.Headers({"Retry-After": value})) is None


def test_retry_after_in_the_past_is_zero() -> None:
    earlier = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
    headers = httpx.Headers({"Retry-After": format_datetime(earlier, usegmt=True)})
    assert _retry_after(headers) == 0.0


# --- Readiness probe ---------------------------------------------------------


def _probe(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> tuple[_Wire, bool]:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    wire = _Wire(monkeypatch, handler)
    return wire, wire.provider.available().ok


def test_the_probe_reads_the_key_endpoint_with_a_short_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"data": {"label": "k", "limit": None, "usage": 0}}
    wire, ok = _probe(monkeypatch, _ok(payload))
    assert ok is True
    assert wire.requests[0].method == "GET"
    assert wire.requests[0].url.path.endswith("/key")
    timeout = wire.requests[0].extensions["timeout"]["read"]
    assert timeout == OpenRouterApiProvider._PROBE_TIMEOUT_MS / 1000


def test_a_refused_key_fails_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    _, ok = _probe(monkeypatch, lambda request: _error(401))
    assert ok is False


@pytest.mark.parametrize("status", [500, 503])
def test_a_server_failure_decides_nothing(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _, ok = _probe(monkeypatch, lambda request: _error(status))
    assert ok is True


def test_a_network_failure_decides_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    _, ok = _probe(monkeypatch, refuse)
    assert ok is True


def test_unavailable_without_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    availability = OpenRouterApiProvider(or_model()).available()
    assert availability.ok is False
    assert availability.reason == "key variable OPENROUTER_API_KEY is not set"


def test_unavailable_without_the_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.openrouter.find_spec", lambda name: None)
    availability = OpenRouterApiProvider(or_model()).available()
    assert availability.ok is False
    assert availability.reason == "openrouter is not installed"


# --- Client ------------------------------------------------------------------


def test_the_client_has_a_timeout_and_no_retry_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[dict[str, Any]] = []

    def fake_client(**kwargs: Any) -> object:
        built.append(kwargs)
        return object()

    monkeypatch.setattr("openrouter.OpenRouter", fake_client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    OpenRouterApiProvider(or_model())._create_client()
    assert built == [
        {
            "api_key": "test-key",
            "retry_config": None,
            "timeout_ms": OpenRouterApiProvider._REQUEST_TIMEOUT_MS,
        }
    ]


def test_one_client_serves_the_probe_and_every_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[None] = []
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    wire = _Wire(monkeypatch, _ok(_result()))
    create = wire.provider._create_client

    def counting_create() -> Any:
        built.append(None)
        return create()

    monkeypatch.setattr(wire.provider, "_create_client", counting_create)
    wire.provider.available()
    wire.provider.generate("prompt")
    wire.provider.generate("prompt")
    assert len(built) == 1
    timeout = wire.requests[-1].extensions["timeout"]["read"]
    assert timeout == OpenRouterApiProvider._REQUEST_TIMEOUT_MS / 1000


def test_the_client_needs_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        OpenRouterApiProvider(or_model())._create_client()
