"""Tests for the `--debug` LLM trace: entry shape, media note, write failure."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from raw2md.llm.base import MediaPart, TextPart
from raw2md.llm.trace import LlmTrace


def test_no_request_leaves_no_file(tmp_path: Path) -> None:
    LlmTrace(tmp_path)

    # An empty file would read as a pass that returned nothing.
    assert not (tmp_path / "llm").exists()


def test_record_keeps_the_request_and_the_raw_reply(tmp_path: Path) -> None:
    trace = LlmTrace(tmp_path)

    trace.record(
        "inspection", "chunk 1/2", [TextPart("12.1: Nu = 0.023")], '{"edits": []}'
    )

    text = (tmp_path / "llm" / "inspection.txt").read_text(encoding="utf-8")
    assert "### chunk 1/2  attempt 1" in text
    assert "-- request (1 part) --" in text
    assert "12.1: Nu = 0.023" in text
    assert "-- reply (13 chars) --" in text
    assert '{"edits": []}' in text


def test_reply_is_kept_exactly_as_it_arrived(tmp_path: Path) -> None:
    trace = LlmTrace(tmp_path)
    # The trace shows the fence the parser then strips.
    fenced = '```json\n{"edits": []}\n```'

    trace.record("inspection", "request", [TextPart("1.1: text")], fenced)

    text = (tmp_path / "llm" / "inspection.txt").read_text(encoding="utf-8")
    assert fenced in text


def test_media_is_named_but_never_written(tmp_path: Path) -> None:
    trace = LlmTrace(tmp_path)
    raster = b"\x89PNG" + b"x" * 2044

    trace.record("ocr", "page 3", [MediaPart(raster, "image/png")], "# Page three")

    text = (tmp_path / "llm" / "ocr.txt").read_text(encoding="utf-8")
    assert "-- request (1 part; media: image/png, 2.0 KB) --" in text
    # A raster or a source PDF weighs megabytes and is on hand already.
    assert "xxxx" not in text


def test_empty_reply_is_recorded_as_such(tmp_path: Path) -> None:
    trace = LlmTrace(tmp_path)

    trace.record("ocr", "page 7", [MediaPart(b"png", "image/png")], "")

    text = (tmp_path / "llm" / "ocr.txt").read_text(encoding="utf-8")
    assert "-- reply (0 chars) --" in text


def test_attempts_append_in_order(tmp_path: Path) -> None:
    trace = LlmTrace(tmp_path)

    trace.record("post", "zone 1 (hyphenation)", [TextPart("exam-")], "no")
    trace.record(
        "post",
        "zone 1 (hyphenation)",
        [TextPart("exam-"), TextPart("Your previous reply was rejected")],
        "example",
        attempt=2,
    )

    text = (tmp_path / "llm" / "post.txt").read_text(encoding="utf-8")
    assert text.index("attempt 1") < text.index("attempt 2")
    # The trace shows what the second attempt was told.
    assert "-- request (2 parts) --" in text
    assert "Your previous reply was rejected" in text


def test_each_operation_keeps_its_own_file(tmp_path: Path) -> None:
    trace = LlmTrace(tmp_path)

    trace.record("inspection", "request", [TextPart("a")], "one")
    trace.record("post", "zone 1 (broken-table)", [TextPart("b")], "two")

    names = sorted(path.name for path in (tmp_path / "llm").iterdir())
    assert names == ["inspection.txt", "post.txt"]


def test_write_failure_is_reported_once_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    # A file where the trace folder belongs makes every write fail.
    (tmp_path / "llm").write_text("not a folder", encoding="utf-8")
    trace = LlmTrace(tmp_path)

    trace.record("post", "zone 1 (broken-table)", [TextPart("a")], "one")
    trace.record("post", "zone 2 (broken-table)", [TextPart("b")], "two")

    # A trace failure costs one warning, not the paid-for result.
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "trace" in warnings[0].getMessage()
