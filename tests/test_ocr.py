"""Tests for the LLM-OCR operation: per-page recognition and body assembly."""

from __future__ import annotations

import io
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from PIL import Image

from raw2md.llm.base import (
    Availability,
    EmptyReason,
    MediaPart,
    Part,
    Provider,
    RateLimitError,
    Reply,
)
from raw2md.llm.ocr import OcrOperation, recognize
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.pages import lost_page_marker, page_mark, split_page_marks
from raw2md.prompts import default_prompts
from raw2md.settings import ModelConfig

_FAKE_MODEL = ModelConfig(
    access="api",
    model="fake",
    key_env="FAKE_KEY",
    command=None,
    rpm=None,
    tpm=None,
    rpd=None,
)


class RecordingProvider(Provider):
    """Vision provider returning one queued reply per call, recording the parts."""

    def __init__(self, replies: Sequence[str | Exception]) -> None:
        super().__init__(_FAKE_MODEL)
        self._replies = list(replies)
        self.parts: list[Sequence[Part]] = []

    def available(self) -> Availability:
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        self.parts.append(parts)
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class ReplyProvider(Provider):
    """Vision provider returning one queued `Reply` per call, with its reason."""

    def __init__(self, replies: Sequence[Reply]) -> None:
        super().__init__(_FAKE_MODEL)
        self._replies = list(replies)
        self.calls = 0

    def available(self) -> Availability:
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        return self.generate_reply(prompt, parts).text

    def generate_reply(
        self,
        prompt: str,
        parts: Sequence[Part] = (),
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> Reply:
        self.calls += 1
        return self._replies.pop(0)


def _op(provider: Provider) -> OcrOperation:
    return OcrOperation(provider=provider, prompt="OCR", model_key="fake")


def _page(*, ink: bool) -> bytes:
    """A page raster: white, with a printed patch on it when `ink` is set."""
    img = Image.new("L", (100, 140), color=255)
    if ink:
        img.paste(0, (10, 10, 40, 30))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def test_recognize_joins_pages_in_order() -> None:
    provider = RecordingProvider(["# Page one", "Page two text."])

    result = recognize([b"png-1", b"png-2"], _op(provider))

    assert result.pages == 2
    assert result.body == "# Page one\n\nPage two text.\n"


def test_recognize_sends_each_page_as_a_png_media_part() -> None:
    provider = RecordingProvider(["a", "b"])

    recognize([b"png-1", b"png-2"], _op(provider))

    assert len(provider.parts) == 2
    for raster, parts in zip((b"png-1", b"png-2"), provider.parts, strict=True):
        assert len(parts) == 1
        part = parts[0]
        assert isinstance(part, MediaPart)
        assert part.mime_type == "image/png"
        assert part.data == raster


def test_recognize_strips_a_code_fence_wrapper() -> None:
    fenced = "```markdown\n# Heading\n\nPage text.\n```"
    provider = RecordingProvider([fenced])

    result = recognize([b"png"], _op(provider))

    assert result.body == "# Heading\n\nPage text.\n"


def test_recognize_skips_a_blank_page_without_retrying() -> None:
    provider = RecordingProvider(["First page.", "   ", "Third page."])

    result = recognize(
        [_page(ink=True), _page(ink=False), _page(ink=True)], _op(provider)
    )

    # An empty reply over a blank page is correct, so no retry.
    assert result.pages == 3
    assert result.body == "First page.\n\nThird page.\n"
    assert len(provider.parts) == 3
    assert (result.empty_replies, result.recovered, result.lost_pages) == (1, 0, 0)


def test_recognize_retries_an_empty_reply_and_recovers() -> None:
    provider = RecordingProvider(["", "Page text."])

    result = recognize([_page(ink=True)], _op(provider))

    assert result.body == "Page text.\n"
    assert len(provider.parts) == 2
    assert (result.empty_replies, result.recovered, result.lost_pages) == (1, 1, 0)


def test_recognize_marks_a_page_lost_after_the_retries() -> None:
    provider = RecordingProvider(["First page.", "", "", "", "Third page."])

    result = recognize([_page(ink=True)] * 3, _op(provider))

    # Two retries, then a marker naming the page to convert again.
    assert len(provider.parts) == 5
    assert result.body == f"First page.\n\n{lost_page_marker(2)}\n\nThird page.\n"
    assert (result.empty_replies, result.recovered, result.lost_pages) == (1, 0, 1)


@pytest.mark.parametrize("reason", [EmptyReason.BLOCKED, EmptyReason.TRUNCATED])
def test_recognize_does_not_retry_a_reason_a_repeat_reproduces(
    reason: EmptyReason,
) -> None:
    provider = ReplyProvider([Reply("", reason)])

    result = recognize([_page(ink=True)], _op(provider))

    assert provider.calls == 1
    assert result.body == f"{lost_page_marker(1)}\n"
    assert (result.empty_replies, result.recovered, result.lost_pages) == (1, 0, 1)


def test_recognize_treats_an_unreadable_raster_as_content() -> None:
    # When the ink test cannot read the raster, the page is retried and
    # reported.
    provider = RecordingProvider(["", "", ""])

    result = recognize([b"not-a-png"], _op(provider))

    assert len(provider.parts) == 3
    assert result.lost_pages == 1


def test_recognize_logs_the_empty_reply_reason_and_the_loss(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = ReplyProvider([Reply("", EmptyReason.NO_TEXT)] * 3)

    with caplog.at_level(logging.INFO, logger="raw2md"):
        recognize([_page(ink=True)], _op(provider))

    assert EmptyReason.NO_TEXT.value in caplog.text
    assert "lost" in caplog.text


def test_recognize_with_no_pages_yields_empty_body() -> None:
    provider = RecordingProvider([])

    result = recognize([], _op(provider))

    assert result.pages == 0
    assert result.body == ""


def test_recognize_with_default_prompt_preserves_a_caption() -> None:
    # Under the real prompt a caption line passes through unchanged.
    provider = RecordingProvider(["Fig. 1. General view of the gearbox."])
    op = OcrOperation(
        provider=provider, prompt=default_prompts().ocr.default, model_key="fake"
    )

    result = recognize([_page(ink=True)], op)

    assert result.body == "Fig. 1. General view of the gearbox.\n"


def test_recognize_propagates_provider_error() -> None:
    provider = RecordingProvider([RateLimitError("429 exhausted")])

    with pytest.raises(RateLimitError):
        recognize([b"png"], _op(provider))


def test_recognize_marks_each_page_under_mark_pages() -> None:
    provider = RecordingProvider(["# Page one", "Page two text."])

    result = recognize([b"png-1", b"png-2"], _op(provider), mark_pages=True)

    body, pages = split_page_marks(result.body)
    assert body == "# Page one\n\nPage two text.\n"
    assert pages == ((0, 1), (2, 2))


def test_recognize_leaves_pages_unmarked_by_default() -> None:
    # Marks are inspection's addressing; without it none are written.
    provider = RecordingProvider(["# Page one", "Page two text."])

    result = recognize([b"png-1", b"png-2"], _op(provider))

    assert page_mark(1) not in result.body


def test_recognize_gives_a_blank_page_no_lines_of_its_own() -> None:
    provider = RecordingProvider(["First page.", "   ", "Third page."])

    result = recognize(
        [_page(ink=True), _page(ink=False), _page(ink=True)],
        _op(provider),
        mark_pages=True,
    )

    body, pages = split_page_marks(result.body)
    assert body == "First page.\n\nThird page.\n"
    # The blank page keeps its number and shares the next page's line.
    assert pages == ((0, 1), (2, 2), (2, 3))


def test_recognize_leaves_a_trailing_blank_page_unmarked() -> None:
    # Page numbers are written out, so leaving the page out shifts nothing.
    provider = RecordingProvider(["First page.", "   "])

    result = recognize(
        [_page(ink=True), _page(ink=False)], _op(provider), mark_pages=True
    )

    assert split_page_marks(result.body) == ("First page.\n", ((0, 1),))


def test_trace_keeps_every_attempt_of_a_page(tmp_path: Path) -> None:
    # The trace shows both answers, which the counters only tally.
    provider = ReplyProvider([Reply("", EmptyReason.NO_TEXT), Reply("# Page one")])
    trace = LlmTrace(tmp_path)

    result = recognize([_page(ink=True)], _op(provider), trace=trace)

    assert result.recovered == 1
    text = (tmp_path / "llm" / "ocr.txt").read_text(encoding="utf-8")
    assert "### page 1  attempt 1" in text
    assert "-- reply (0 chars) --" in text
    assert "### page 1  attempt 2" in text
    assert "# Page one" in text
    assert "media: image/png" in text


def test_trace_records_each_page(tmp_path: Path) -> None:
    provider = RecordingProvider(["# Page one", "Page two text."])
    trace = LlmTrace(tmp_path)

    recognize([b"png-1", b"png-2"], _op(provider), trace=trace)

    text = (tmp_path / "llm" / "ocr.txt").read_text(encoding="utf-8")
    assert "### page 1  attempt 1" in text
    assert "### page 2  attempt 1" in text
