"""Tests for the inspection pass: the request, retries, errors, trace."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from raw2md.llm.base import (
    DocumentTooLargeError,
    EmptyReason,
    MediaPart,
    RateLimitError,
    Reply,
)
from raw2md.llm.inspection.common import InspectionReplyError, InspectOperation
from raw2md.llm.inspection.coordinator import inspect
from raw2md.llm.trace import LlmTrace

from ._helpers import (
    MARKER_BODY,
    SOURCE,
    FakeProvider,
    SchemaProvider,
    edits_reply,
    make_op,
    make_schema_op,
    sent_media,
    sent_text,
)

# --- request shape ---------------------------------------------------------


def test_source_and_numbered_body_are_sent() -> None:
    op = make_op(edits_reply())
    inspect(MARKER_BODY, SOURCE, op)
    assert sent_media(op) == [SOURCE]
    text = sent_text(op)
    assert "1.1: # Heading" in text
    assert "1.3: Here the [unreadable] word is lost." in text


def test_the_provider_is_asked_for_a_schema_constrained_reply() -> None:
    from raw2md.llm.inspection.reply import RESPONSE_SCHEMA

    op = make_schema_op(edits_reply())
    inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, SchemaProvider)
    _, _, schema = provider.calls[0]
    assert schema == RESPONSE_SCHEMA


def test_a_provider_without_a_schema_contract_gets_the_plain_request() -> None:
    # `FakeProvider` implements `generate` alone, and the base `generate_reply`
    # drops the schema on its way there.
    op = make_op(edits_reply())
    inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    assert len(provider.calls) == 1


# --- retry on an unusable reply ---------------------------------------------


def test_unusable_reply_is_retried_once_and_recovers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        [
            "this is not JSON at all {",
            edits_reply(
                {
                    "page": 1,
                    "line": 3,
                    "old": "Here the [unreadable] word is lost.",
                    "new": "Here the clear word is back.",
                }
            ),
        ]
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    assert len(provider.calls) == 2
    assert result.applied == 1
    assert "Here the clear word is back." in result.body
    assert not any(
        record.levelname == "WARNING" and "reply unusable" in record.message
        for record in caplog.records
    )
    assert any(
        record.levelname == "INFO" and "retrying once" in record.message
        for record in caplog.records
    )


def test_second_unusable_reply_raises(caplog: pytest.LogCaptureFixture) -> None:
    op = make_op(["not JSON at all {", "still not JSON at all {"])
    with (
        caplog.at_level("INFO", logger="raw2md"),
        pytest.raises(InspectionReplyError),
    ):
        inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    assert len(provider.calls) == 2
    assert any(
        record.levelname == "WARNING" and "retry too" in record.message
        for record in caplog.records
    )


# --- an empty reply is retried, not read as "nothing to fix" ---------------


def test_empty_reply_is_retried_once_and_recovers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        [
            "",
            edits_reply(
                {
                    "page": 1,
                    "line": 3,
                    "old": "Here the [unreadable] word is lost.",
                    "new": "Here the clear word is back.",
                }
            ),
        ]
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    assert len(provider.calls) == 2
    assert result.applied == 1
    assert "Here the clear word is back." in result.body
    assert not any(
        record.levelname == "WARNING" and "reply unusable" in record.message
        for record in caplog.records
    )
    assert any(
        record.levelname == "INFO"
        and "retrying once" in record.message
        and "empty reply" in record.message
        for record in caplog.records
    )


def test_second_empty_reply_raises(caplog: pytest.LogCaptureFixture) -> None:
    op = make_op(["", ""])
    with (
        caplog.at_level("INFO", logger="raw2md"),
        pytest.raises(InspectionReplyError),
    ):
        inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    assert len(provider.calls) == 2
    assert any(
        record.levelname == "WARNING" and "retry too" in record.message
        for record in caplog.records
    )


def test_blocked_empty_reply_is_not_retried(caplog: pytest.LogCaptureFixture) -> None:
    op = make_schema_op(Reply("", EmptyReason.BLOCKED))
    with (
        caplog.at_level("WARNING", logger="raw2md"),
        pytest.raises(InspectionReplyError),
    ):
        inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, SchemaProvider)
    assert len(provider.calls) == 1
    assert any(
        "not retrying" in record.message and "blocked" in record.message
        for record in caplog.records
    )


def test_truncated_empty_reply_is_not_retried() -> None:
    op = make_schema_op(Reply("", EmptyReason.TRUNCATED))
    with pytest.raises(InspectionReplyError):
        inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, SchemaProvider)
    assert len(provider.calls) == 1


def test_no_text_empty_reply_is_still_retried() -> None:
    op = make_schema_op(
        [
            Reply("", EmptyReason.NO_TEXT),
            Reply(
                edits_reply(
                    {
                        "page": 1,
                        "line": 3,
                        "old": "Here the [unreadable] word is lost.",
                        "new": "Here the clear word is back.",
                    }
                )
            ),
        ]
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    provider = op.provider
    assert isinstance(provider, SchemaProvider)
    assert len(provider.calls) == 2
    assert result.applied == 1


# --- provider errors propagate ---------------------------------------------


def test_rate_limit_propagates() -> None:
    op = make_op(RateLimitError("429"))
    with pytest.raises(RateLimitError):
        inspect(MARKER_BODY, SOURCE, op)


def test_document_too_large_propagates() -> None:
    op = make_op(DocumentTooLargeError("over the limit"))
    with pytest.raises(DocumentTooLargeError):
        inspect(MARKER_BODY, SOURCE, op)


# --- debug trace -----------------------------------------------------------


def test_trace_keeps_the_unusable_reply_and_the_retry(tmp_path: Path) -> None:
    op = make_op(
        [
            "not JSON at all {",
            edits_reply({"page": 1, "line": 3, "flag": "hyphenation"}),
        ]
    )
    trace = LlmTrace(tmp_path)

    inspect(MARKER_BODY, SOURCE, op, trace=trace)

    text = (tmp_path / "llm" / "inspection.txt").read_text(encoding="utf-8")
    assert "attempt 1" in text
    assert "attempt 2" in text
    assert "not JSON at all {" in text
    assert "1.3: Here the [unreadable] word is lost." in text


def test_trace_names_each_chunk(tmp_path: Path) -> None:
    # A stub source would fall back to one whole-source request.
    doc = pymupdf.open()
    try:
        doc.new_page()
        doc.new_page()
        source = MediaPart(doc.tobytes(), "application/pdf")
    finally:
        doc.close()
    body = "\n".join(["First page line.", "Second page line.", ""])
    pages = ((0, 1), (1, 2))
    op = InspectOperation(
        provider=FakeProvider(edits_reply()),
        prompt="INSPECT",
        model_key="fake",
        pages_per_request=1,
    )
    trace = LlmTrace(tmp_path)

    inspect(body, source, op, pages, trace=trace)

    text = (tmp_path / "llm" / "inspection.txt").read_text(encoding="utf-8")
    assert "### chunk 1/2" in text
    assert "### chunk 2/2" in text
