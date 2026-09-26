"""Tests for chunked inspection of a large source.

A fake provider and a tiny real PDF drive `inspect`; the budget is passed per
operation, so a small fixture stands in for a book.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pymupdf
import pytest

from raw2md.llm.base import (
    DEFAULT_MAX_REQUEST_BYTES,
    AuthError,
    Availability,
    ConnectionDroppedError,
    MediaPart,
    Part,
    Provider,
    RateLimitError,
    TextPart,
    inline_media_bytes,
)
from raw2md.llm.chunking import (
    DEFAULT_CHUNK_TOKENS,
    DEFAULT_PAGES_PER_REQUEST,
    PageIndex,
    TokenPacer,
    chunk_budget,
)
from raw2md.llm.inspection.common import InspectionReplyError, InspectOperation
from raw2md.llm.inspection.coordinator import inspect
from raw2md.settings import ModelConfig

_MODEL = ModelConfig(
    access="api",
    model="fake",
    key_env="FAKE_KEY",
    command=None,
    rpm=None,
    tpm=None,
    rpd=None,
)

_PAGES = 12
_LINES_PER_PAGE = 10
_EMPTY_REPLY = '{"edits": []}'

# A dozen pages fit one request by tokens, so only the page window splits them.
_WIDE_BUDGET = 20_000


class ChunkProvider(Provider):
    """Provider recording every request; replies are queued per call."""

    def __init__(self, replies: Sequence[str | Exception]) -> None:
        super().__init__(_MODEL)
        self._replies = list(replies)
        self.calls: list[tuple[Part, ...]] = []

    def available(self) -> Availability:
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        self.calls.append(tuple(parts))
        reply = self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_op(
    replies: Sequence[str | Exception],
    *,
    budget: int = _WIDE_BUDGET,
    tpm: int | None = None,
    prompt: str = "INSPECT",
    pages_per_request: int = DEFAULT_PAGES_PER_REQUEST,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
) -> InspectOperation:
    return InspectOperation(
        provider=ChunkProvider(replies),
        prompt=prompt,
        model_key="fake",
        token_budget=budget,
        tpm=tpm,
        pages_per_request=pages_per_request,
        max_request_bytes=max_request_bytes,
    )


def calls_of(op: InspectOperation) -> list[tuple[Part, ...]]:
    provider = op.provider
    assert isinstance(provider, ChunkProvider)
    return provider.calls


def media_of(parts: Sequence[Part]) -> MediaPart:
    media = [part for part in parts if isinstance(part, MediaPart)]
    assert len(media) == 1
    return media[0]


def region_of(parts: Sequence[Part]) -> str:
    """The addressed-body part of a request (the last text part sent)."""
    texts = [part.text for part in parts if isinstance(part, TextPart)]
    return texts[-1]


def request_bytes(parts: Sequence[Part], prompt: str) -> int:
    """What the request weighs on the wire, media inlined and encoded."""
    return len(prompt.encode("utf-8")) + sum(
        inline_media_bytes(len(part.data))
        if isinstance(part, MediaPart)
        else len(part.text.encode("utf-8"))
        for part in parts
    )


def page_count(data: bytes) -> int:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return int(doc.page_count)


def text_of(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(str(page.get_text("text")) for page in doc)


def make_pdf(pages: int, *, stamped: bool = False) -> MediaPart:
    """A PDF of `pages` blank pages, each optionally stamped with its number."""
    doc = pymupdf.open()
    try:
        for index in range(pages):
            page = doc.new_page()
            if stamped:
                page.insert_text((72, 72), f"stamped page {index + 1}")
        return MediaPart(bytes(doc.tobytes()), "application/pdf")
    finally:
        doc.close()


def make_body(
    pages: int = _PAGES, *, lines_per_page: int = _LINES_PER_PAGE
) -> tuple[str, tuple[tuple[int, int], ...]]:
    """A body of `pages` pages plus the page map the pipeline would hand over."""
    lines: list[str] = []
    page_map: list[tuple[int, int]] = []
    for page in range(1, pages + 1):
        page_map.append((len(lines), page))
        lines.extend(
            f"Page {page} line {index} of a converted document with real words."
            for index in range(lines_per_page)
        )
    return "\n".join(lines) + "\n", tuple(page_map)


# A display formula cut into one damaged span per line: the pieces share one
# address and one quote, which no single body line holds.
_FORMULA_PIECES = (
    r"$$R = \frac{1}{2}\left[\left(\begin{aligned} w_{z}\right)^2$$",
    r"$$+ \left(u_{z}\right)^2\right]$$",
)
# The pieces balance together, though neither balances alone.
_REPAIRED_PIECES = (
    r"$$R = \frac{1}{2}\left[\left(w_{z}\right)^2$$",
    _FORMULA_PIECES[1],
)


def make_formula_body() -> tuple[str, tuple[tuple[int, int], ...]]:
    """A body whose ninth page opens with a formula the recognition cut in two."""
    lines: list[str] = []
    page_map: list[tuple[int, int]] = []
    for page in range(1, _PAGES + 1):
        page_map.append((len(lines), page))
        if page == 9:
            lines.extend([_FORMULA_PIECES[0], "", _FORMULA_PIECES[1], ""])
        lines.extend(
            f"Page {page} line {index} of a converted document with real words."
            for index in range(_LINES_PER_PAGE)
        )
    return "\n".join(lines) + "\n", tuple(page_map)


def pages_in(region: str) -> list[int]:
    """The page numbers the addresses of a region name, in order of appearance."""
    seen: list[int] = []
    for line in region.split("\n"):
        page = int(line.split(".", 1)[0])
        if not seen or seen[-1] != page:
            seen.append(page)
    return seen


def _edit_reply(page: int, line: int, old: str, new: str) -> str:
    return json.dumps({"edits": [{"page": page, "line": line, "old": old, "new": new}]})


def _reply(entries: Sequence[dict[str, object]]) -> str:
    return json.dumps({"edits": list(entries)})


def _repairs(
    lines: Sequence[str], targets: Sequence[int], page: int, first_line: int
) -> tuple[list[dict[str, object]], list[str]]:
    """Edits quoting `targets` word for word, addressed from (`page`, `first_line`).

    The replacement keeps the line's numbers, which the edit guard holds.
    """
    fixed = [lines[index].replace("converted", "repaired") for index in targets]
    entries: list[dict[str, object]] = [
        {
            "page": page,
            "line": first_line + position,
            "old": lines[index],
            "new": fixed[position],
        }
        for position, index in enumerate(targets)
    ]
    return entries, fixed


def test_short_document_stays_a_single_request() -> None:
    op = make_op([_EMPTY_REPLY])
    source = make_pdf(2)
    body, pages = make_body(2)

    inspect(body, source, op, pages)

    calls = calls_of(op)
    assert len(calls) == 1
    # The whole source goes out, with no chunk note beside it.
    assert media_of(calls[0]).data == source.data
    assert len([p for p in calls[0] if isinstance(p, TextPart)]) == 1


def test_unreadable_source_falls_back_to_one_request() -> None:
    op = make_op([_EMPTY_REPLY])
    source = MediaPart(b"not a pdf at all", "application/pdf")
    body, pages = make_body()

    inspect(body, source, op, pages)

    calls = calls_of(op)
    assert len(calls) == 1
    assert media_of(calls[0]).data == source.data


def test_a_document_past_the_page_window_is_split() -> None:
    # The document fits the token budget; the page window splits it.
    op = make_op([_EMPTY_REPLY])
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    calls = calls_of(op)
    assert len(calls) > 1
    for parts in calls:
        assert page_count(media_of(parts).data) <= 8
        note = next(p for p in parts if isinstance(p, TextPart))
        assert "part" in note.text


def test_a_byte_ceiling_narrows_the_page_window() -> None:
    # Inline media hits the byte ceiling while tokens and pages still fit.
    ceiling = 3600
    op = make_op([_EMPTY_REPLY], max_request_bytes=ceiling)
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    calls = calls_of(op)
    # The page window alone would have made two requests.
    assert len(calls) > 2
    for parts in calls:
        assert page_count(media_of(parts).data) < DEFAULT_PAGES_PER_REQUEST
        assert request_bytes(parts, op.prompt) <= ceiling


def test_a_source_over_the_ceiling_is_chunked() -> None:
    # Only the byte ceiling splits these two pages.
    source = make_pdf(2)
    op = make_op([_EMPTY_REPLY], max_request_bytes=len(source.data))
    body, pages = make_body(2)

    inspect(body, source, op, pages)

    assert len(calls_of(op)) == 2


def test_the_prompt_counts_against_the_ceiling() -> None:
    # The guard weighs the prompt too, so the plan must.
    source = make_pdf(2)
    body, pages = make_body(2)
    prompt = "INSPECT " * 625
    ceiling = len(source.data) + len(body.encode("utf-8")) + 2000
    op = make_op([_EMPTY_REPLY], prompt=prompt, max_request_bytes=ceiling)

    inspect(body, source, op, pages)

    assert len(calls_of(op)) == 2


def test_a_page_ceiling_from_settings_narrows_the_window() -> None:
    op = make_op([_EMPTY_REPLY], pages_per_request=3)
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    calls = calls_of(op)
    assert len(calls) == _PAGES // 3
    for parts in calls:
        assert page_count(media_of(parts).data) == 3


def test_a_chunk_carries_exactly_the_pages_of_its_text() -> None:
    op = make_op([_EMPTY_REPLY])
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES, stamped=True), op, pages)

    for parts in calls_of(op):
        sent = text_of(media_of(parts).data)
        named = pages_in(region_of(parts))
        for page in named:
            assert f"stamped page {page}" in sent
        # The cut is the pages, not a padded guess.
        assert page_count(media_of(parts).data) == len(named)


def test_line_numbers_restart_on_every_page() -> None:
    op = make_op([_EMPTY_REPLY])
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    sent = "\n".join(region_of(parts) for parts in calls_of(op))
    assert "1.1: Page 1 line 0" in sent
    # Each page restarts its line count at 1.
    assert "2.1: Page 2 line 0" in sent
    assert f"{_PAGES}.{_LINES_PER_PAGE}: Page {_PAGES} line 9" in sent


def test_regions_cover_the_body_without_gaps_or_overlap() -> None:
    op = make_op([_EMPTY_REPLY])
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    sent = "\n".join(region_of(parts) for parts in calls_of(op))
    lines = body.rstrip("\n").split("\n")
    expected = "\n".join(
        f"{index // _LINES_PER_PAGE + 1}.{index % _LINES_PER_PAGE + 1}: {line}"
        for index, line in enumerate(lines)
    )
    assert sent == expected


def test_edits_from_several_chunks_merge_by_page_address() -> None:
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    early, late = 2, len(lines) - 2
    # The replacements keep the line's numbers, which the edit guard holds.
    fixed_early = lines[early].replace("converted", "repaired")
    fixed_late = lines[late].replace("converted", "repaired")
    replies = [
        _edit_reply(1, early + 1, lines[early], fixed_early),
        _edit_reply(_PAGES, _LINES_PER_PAGE - 1, lines[late], fixed_late),
        _EMPTY_REPLY,
    ]
    op = make_op(replies)

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) > 1
    assert result.applied == 2
    out = result.body.split("\n")
    assert out[early] == fixed_early
    assert out[late] == fixed_late


def test_an_address_on_the_last_page_of_a_long_document_still_lands() -> None:
    # The model counts one page at a time, so the last page of a long document
    # is addressed as reliably as the first.
    body, pages = make_body(60)
    lines = body.rstrip("\n").split("\n")
    target = len(lines) - 3
    fixed = lines[target].replace("converted", "repaired")
    replies = [_EMPTY_REPLY] * 7 + [_edit_reply(60, 8, lines[target], fixed)]
    op = make_op(replies)

    result = inspect(body, make_pdf(60), op, pages)

    assert result.applied == 1
    assert result.body.split("\n")[target] == fixed


def test_a_narrow_budget_cuts_the_window_below_the_page_limit() -> None:
    op = make_op([_EMPTY_REPLY], budget=1500)
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    calls = calls_of(op)
    assert len(calls) > 2
    assert all(page_count(media_of(parts).data) < 8 for parts in calls)


def test_a_single_page_over_the_budget_is_sent_alone() -> None:
    # A page cannot be divided without losing its addressing.
    op = make_op([_EMPTY_REPLY], budget=400)
    body, pages = make_body(3, lines_per_page=40)

    inspect(body, make_pdf(3), op, pages)

    calls = calls_of(op)
    assert len(calls) == 3
    assert all(page_count(media_of(parts).data) == 1 for parts in calls)


def test_a_spent_budget_ends_the_pass_with_the_edits_before_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A spent budget ends the pass, but the edits of the chunks already paid
    # for are applied.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    first, second = 2, 4 * _LINES_PER_PAGE + 1
    fixed_first = lines[first].replace("converted", "repaired")
    fixed_second = lines[second].replace("converted", "repaired")
    op = make_op(
        [
            _edit_reply(1, first + 1, lines[first], fixed_first),
            _edit_reply(5, 2, lines[second], fixed_second),
            RateLimitError("quota exhausted"),
        ],
        pages_per_request=4,
    )

    with caplog.at_level("WARNING", logger="raw2md"):
        result = inspect(body, make_pdf(_PAGES), op, pages)

    # A spent budget refuses halves too, so the chunk is not halved.
    assert len(calls_of(op)) == 3
    assert result.applied == 2
    out = result.body.split("\n")
    assert out[first] == fixed_first
    assert out[second] == fixed_second
    # The caller records a partial pass and an LLM error.
    assert isinstance(result.failure, RateLimitError)
    assert (result.chunks, result.skipped_chunks) == (3, 1)
    # The log counts coverage, not the failed request.
    ended = [r for r in caplog.records if "spent budget" in r.message]
    assert [r.levelname for r in ended] == ["ERROR"]
    assert "1 of 3 chunks left without a full pass" in ended[0].message


def test_a_refused_access_ends_the_pass_without_halving() -> None:
    body, pages = make_body()
    op = make_op(
        [_EMPTY_REPLY, AuthError("bad key")],
        pages_per_request=4,
    )

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) == 2
    assert isinstance(result.failure, AuthError)
    assert (result.chunks, result.skipped_chunks) == (3, 2)


def test_a_failed_first_chunk_fails_the_whole_inspection() -> None:
    # Nothing completed, so the failure is the pass's own.
    op = make_op([RateLimitError("quota exhausted")])
    body, pages = make_body()

    with pytest.raises(RateLimitError):
        inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) == 1


def test_a_refused_chunk_is_sent_in_halves_then_left_behind(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # An empty reply says nothing about the next chunk: the chunk is halved,
    # given up, and the pass goes on.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    last = 8 * _LINES_PER_PAGE + 1
    fixed = lines[last].replace("converted", "repaired")
    op = make_op(
        [
            _EMPTY_REPLY,  # chunk 1
            "",  # chunk 2, and its retry
            "",
            "",  # chunk 2 half 1, and its retry
            "",
            "",  # chunk 2 half 2, and its retry
            "",
            _edit_reply(9, 2, lines[last], fixed),  # chunk 3
        ],
        pages_per_request=4,
    )

    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, make_pdf(_PAGES), op, pages)

    calls = calls_of(op)
    assert len(calls) == 8
    assert pages_in(region_of(calls[3])) == [5, 6]
    assert pages_in(region_of(calls[5])) == [7, 8]
    assert result.applied == 1
    assert result.body.split("\n")[last] == fixed
    # Nothing refused the run, so only coverage is lost.
    assert result.failure is None
    assert (result.chunks, result.skipped_chunks) == (3, 1)
    # The caller names the file once when the pass ends, so every rung here
    # stays at INFO.
    assert not any(record.levelname == "WARNING" for record in caplog.records)
    messages = [r.message for r in caplog.records]
    assert any("chunk 2/3 left without a full pass, going on" in m for m in messages)


def test_a_provider_failure_keeps_the_run_an_error_though_the_pass_goes_on() -> None:
    # A dropped connection costs this chunk only, but the run answers for it.
    op = make_op(
        [_EMPTY_REPLY, ConnectionDroppedError("connection reset"), _EMPTY_REPLY],
        pages_per_request=4,
    )
    body, pages = make_body()

    result = inspect(body, make_pdf(_PAGES), op, pages)

    # A provider failure does not depend on the cut, so there is no halving.
    assert len(calls_of(op)) == 3
    assert isinstance(result.failure, ConnectionDroppedError)
    assert (result.chunks, result.skipped_chunks) == (3, 1)


def test_the_edits_of_a_surviving_half_are_applied() -> None:
    # The half that answered is kept.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    inside = 4 * _LINES_PER_PAGE + 1
    fixed = lines[inside].replace("converted", "repaired")
    op = make_op(
        [
            _EMPTY_REPLY,  # chunk 1
            "not JSON at all {",  # chunk 2, and its retry
            "still not JSON at all {",
            _edit_reply(5, 2, lines[inside], fixed),  # chunk 2 half 1
            "",  # chunk 2 half 2, and its retry
            "",
            _EMPTY_REPLY,  # chunk 3
        ],
        pages_per_request=4,
    )

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) == 7
    assert result.applied == 1
    assert result.body.split("\n")[inside] == fixed
    # Half the chunk was never answered, so it is not counted done.
    assert result.failure is None
    assert (result.chunks, result.skipped_chunks) == (3, 1)


def test_a_chunk_both_halves_answer_leaves_the_pass_complete(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A chunk answered in two halves was inspected whole.
    op = make_op(
        [_EMPTY_REPLY, "", "", _EMPTY_REPLY, _EMPTY_REPLY, _EMPTY_REPLY],
        pages_per_request=4,
    )
    body, pages = make_body()

    with caplog.at_level("WARNING", logger="raw2md"):
        result = inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) == 6
    assert result.failure is None
    assert (result.chunks, result.skipped_chunks) == (3, 0)
    # The halving closed the rung, so nothing reaches WARNING.
    assert not caplog.records


def test_a_single_page_chunk_is_given_up_without_halving() -> None:
    # A one-page chunk has no cut left to try.
    op = make_op([_EMPTY_REPLY, "", "", _EMPTY_REPLY], pages_per_request=1)
    body, pages = make_body()

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) == _PAGES + 1
    assert result.failure is None
    assert (result.chunks, result.skipped_chunks) == (_PAGES, 1)


def test_a_completed_pass_carries_no_failure() -> None:
    op = make_op([_EMPTY_REPLY], pages_per_request=4)
    body, pages = make_body()

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) == 3
    assert result.failure is None
    assert (result.chunks, result.skipped_chunks) == (3, 0)


# ---------------------------------------------------------------------------
# on_chunk progress callback
# ---------------------------------------------------------------------------


def test_on_chunk_reports_every_chunk_of_the_plan() -> None:
    op = make_op([_EMPTY_REPLY, _EMPTY_REPLY, _EMPTY_REPLY], pages_per_request=4)
    body, pages = make_body()
    seen: list[tuple[int, int]] = []

    inspect(
        body, make_pdf(_PAGES), op, pages, on_chunk=lambda n, t: seen.append((n, t))
    )

    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_on_chunk_not_called_for_a_single_request_pass() -> None:
    op = make_op([_EMPTY_REPLY])
    source = make_pdf(2)
    body, pages = make_body(2)
    seen: list[tuple[int, int]] = []

    inspect(body, source, op, pages, on_chunk=lambda n, t: seen.append((n, t)))

    assert seen == []


def test_on_chunk_count_is_not_broken_by_a_halved_chunk() -> None:
    # A halved chunk is still counted once.
    op = make_op(
        [
            _EMPTY_REPLY,  # chunk 1
            "",  # chunk 2, and its retry
            "",
            "",  # chunk 2 half 1, and its retry
            "",
            "",  # chunk 2 half 2, and its retry
            "",
            _EMPTY_REPLY,  # chunk 3
        ],
        pages_per_request=4,
    )
    body, pages = make_body()
    seen: list[tuple[int, int]] = []

    inspect(
        body, make_pdf(_PAGES), op, pages, on_chunk=lambda n, t: seen.append((n, t))
    )

    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_on_chunk_count_is_not_broken_by_a_spent_budget_skip() -> None:
    # The refused chunk is reported before its request, so the count matches
    # the plan.
    body, pages = make_body()
    op = make_op(
        [_EMPTY_REPLY, _EMPTY_REPLY, RateLimitError("quota exhausted")],
        pages_per_request=4,
    )
    seen: list[tuple[int, int]] = []

    inspect(
        body, make_pdf(_PAGES), op, pages, on_chunk=lambda n, t: seen.append((n, t))
    )

    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_on_chunk_reports_the_first_chunk_even_when_it_fails() -> None:
    # Twelve pages over an 8-page window make two chunks.
    op = make_op([RateLimitError("quota exhausted")])
    body, pages = make_body()
    seen: list[tuple[int, int]] = []

    with pytest.raises(RateLimitError):
        inspect(
            body, make_pdf(_PAGES), op, pages, on_chunk=lambda n, t: seen.append((n, t))
        )

    assert seen == [(1, 2)]


def test_chunk_retries_once_on_unusable_reply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body, pages = make_body()
    source = make_pdf(_PAGES)
    baseline = make_op([_EMPTY_REPLY])
    inspect(body, source, baseline, pages)
    chunk_count = len(calls_of(baseline))
    assert chunk_count > 1

    op = make_op(["not JSON at all {", _EMPTY_REPLY])
    with caplog.at_level("INFO", logger="raw2md"):
        inspect(body, source, op, pages)

    # One retry recovers the first chunk, so the record is INFO.
    assert len(calls_of(op)) == chunk_count + 1
    assert any(
        record.levelname == "INFO" and "retrying once" in record.message
        for record in caplog.records
    )


def test_chunk_second_unusable_reply_raises() -> None:
    op = make_op(["not JSON at all {", "still not JSON at all {"])
    body, pages = make_body()

    with pytest.raises(InspectionReplyError):
        inspect(body, make_pdf(_PAGES), op, pages)

    # Two attempts, then two per half; nothing came back, so the pass fails
    # before chunk two.
    assert len(calls_of(op)) == 6


def test_a_chunk_that_numbered_its_own_pages_is_recounted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The model numbers pages 9-12 as its own pages 1-4.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    targets = [80, 81, 82]
    entries, fixed = _repairs(lines, targets, page=1, first_line=1)
    op = make_op([_EMPTY_REPLY, _reply(entries)])

    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, make_pdf(_PAGES), op, pages)

    assert result.applied == 3
    out = result.body.split("\n")
    assert [out[index] for index in targets] == fixed
    assert any(
        "pages counted from one inside the chunk" in record.message
        for record in caplog.records
    )


def test_a_recounted_quote_keeps_no_echo_of_the_address_it_came_with(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The echoed address at the head of a quote goes while the recount still
    # knows it.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    targets = [80, 81, 82]
    entries, fixed = _repairs(lines, targets, page=1, first_line=1)
    for position, entry in enumerate(entries):
        entry["old"] = f"1.{1 + position}: {entry['old']}"
    op = make_op([_EMPTY_REPLY, _reply(entries)])

    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, make_pdf(_PAGES), op, pages)

    assert result.applied == 3
    out = result.body.split("\n")
    assert [out[index] for index in targets] == fixed


def test_a_recounted_quote_keeps_body_text_shaped_like_an_address() -> None:
    # The line itself opens with address-shaped text; only the body tells it
    # from an echo.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    lines[80] = "1.1: Overview of a converted document with real words."
    body = "\n".join(lines) + "\n"
    fixed = lines[80].replace("converted", "repaired")
    op = make_op([_EMPTY_REPLY, _edit_reply(1, 1, lines[80], fixed)])

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert result.applied == 1
    assert result.body.split("\n")[80] == fixed


def test_a_chunk_that_counted_lines_through_itself_is_recounted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The model counts the fragment's lines from first to last.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    targets = [60, 61, 62]
    entries, fixed = _repairs(lines, targets, page=1, first_line=61)
    op = make_op([_reply(entries), _EMPTY_REPLY])

    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, make_pdf(_PAGES), op, pages)

    assert result.applied == 3
    out = result.body.split("\n")
    assert [out[index] for index in targets] == fixed
    assert any(
        "lines counted through the chunk" in record.message for record in caplog.records
    )


def test_a_recount_that_confirms_nothing_sends_the_chunk_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No numbering places the quotes, so the request is sent once more.
    body, pages = make_body()
    source = make_pdf(_PAGES)
    baseline = make_op([_EMPTY_REPLY])
    inspect(body, source, baseline, pages)
    chunk_count = len(calls_of(baseline))

    entries: list[dict[str, object]] = [
        {
            "page": 1,
            "line": 61 + position,
            "old": f"A line of text this document never carried, {position}.",
            "new": f"A line of text this document never carried, {position}!",
        }
        for position in range(3)
    ]
    op = make_op([_reply(entries), _EMPTY_REPLY])

    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, source, op, pages)

    assert len(calls_of(op)) == chunk_count + 1
    assert result.applied == 0
    # The retry recovers, so the record is INFO.
    assert any(
        record.levelname == "INFO"
        and "no recount of the chunk's own numbering explains them" in record.message
        for record in caplog.records
    )


def test_a_chunk_that_kept_its_addressing_is_left_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # One missed quote is a slip, not a lost numbering, so nothing is
    # recounted.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    entries, fixed = _repairs(lines, [80, 81], page=9, first_line=1)
    entries.append(
        {
            "page": 9,
            "line": 3,
            "old": "A quote this page never carried at all.",
            "new": "A quote this page never carried at all!",
        }
    )
    op = make_op([_EMPTY_REPLY, _reply(entries)])

    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, make_pdf(_PAGES), op, pages)

    assert (result.applied, result.skipped) == (2, 1)
    assert result.body.split("\n")[80:82] == fixed
    assert not any(
        "recounting its addresses" in record.message for record in caplog.records
    )


def test_a_recount_leaves_the_flags_of_the_reply_alone() -> None:
    # Flag addresses are not read, so a recount leaves flags as counted.
    body, pages = make_body()
    lines = body.rstrip("\n").split("\n")
    entries, fixed = _repairs(lines, [80, 81, 82], page=1, first_line=1)
    entries.append({"page": 1, "line": 1, "flag": "broken-table"})
    op = make_op([_EMPTY_REPLY, _reply(entries)])

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert (result.applied, result.format_flags) == (3, 1)
    assert result.body.split("\n")[80:83] == fixed


def test_a_reply_repairing_only_a_cut_up_formula_is_not_refused() -> None:
    # The quote spans the pieces; read line by line it would confirm nothing.
    body, pages = make_formula_body()
    repaired = "\n".join(_REPAIRED_PIECES)
    op = make_op(
        [_EMPTY_REPLY, _edit_reply(9, 1, "\n".join(_FORMULA_PIECES), repaired)],
    )

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) == 2
    assert (result.applied, result.failure) == (1, None)
    assert repaired in result.body


def test_a_reply_of_flags_alone_is_never_refused() -> None:
    # A flag confirms no address, so it offers no evidence either way.
    body, pages = make_body()
    reply = _reply([{"page": 1, "line": 1, "flag": "broken-table"}])
    op = make_op([reply, _EMPTY_REPLY])

    result = inspect(body, make_pdf(_PAGES), op, pages)

    assert result.failure is None
    assert (result.chunks, result.skipped_chunks) == (2, 0)


def test_chunk_retry_is_paced_against_the_declared_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []
    clock = [0.0]

    def advance(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr("raw2md.llm.chunking._monotonic", lambda: clock[0])
    monkeypatch.setattr("raw2md.llm.chunking._sleep", advance)
    op = make_op(["not JSON at all {", _EMPTY_REPLY], tpm=60_000)
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    calls = calls_of(op)
    assert len(calls) > 2
    # The retry is paced too.
    assert len(slept) == len(calls) - 1
    assert all(pause > 0 for pause in slept)


def test_chunk_requests_are_paced_against_the_declared_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []
    clock = [0.0]

    def advance(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr("raw2md.llm.chunking._monotonic", lambda: clock[0])
    monkeypatch.setattr("raw2md.llm.chunking._sleep", advance)
    op = make_op([_EMPTY_REPLY], tpm=60_000)
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) > 1
    assert len(slept) == len(calls_of(op)) - 1
    assert all(pause > 0 for pause in slept)


def test_a_larger_reply_widens_the_pause_before_the_next_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def paced_run(pad_chars: int) -> float:
        slept: list[float] = []
        clock = [0.0]

        def advance(seconds: float) -> None:
            slept.append(seconds)
            clock[0] += seconds

        monkeypatch.setattr("raw2md.llm.chunking._monotonic", lambda: clock[0])
        monkeypatch.setattr("raw2md.llm.chunking._sleep", advance)
        first_reply = json.dumps({"edits": [], "pad": "x" * pad_chars})
        op = make_op([first_reply, _EMPTY_REPLY, _EMPTY_REPLY], tpm=60_000)
        body, pages = make_body()

        inspect(body, make_pdf(_PAGES), op, pages)

        assert len(slept) >= 1
        # The second pause is charged the first reply's cost.
        return slept[0]

    small_pause = paced_run(0)
    large_pause = paced_run(20_000)

    assert large_pause > small_pause


def test_no_declared_rate_means_no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("raw2md.llm.chunking._sleep", slept.append)
    op = make_op([_EMPTY_REPLY], tpm=None)
    body, pages = make_body()

    inspect(body, make_pdf(_PAGES), op, pages)

    assert len(calls_of(op)) > 1
    assert slept == []


def test_token_pacer_charges_each_request_against_the_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []
    clock = [0.0]
    monkeypatch.setattr("raw2md.llm.chunking._monotonic", lambda: clock[0])
    monkeypatch.setattr("raw2md.llm.chunking._sleep", slept.append)
    # 70% of 100000 tpm is 1166.67 tokens per second, so 3000 tokens cost ~2.57s.
    pacer = TokenPacer(100_000)

    pacer.before_request(3000)
    pacer.before_request(3000)

    assert slept == [pytest.approx(3000 / (100_000 * 0.7 / 60))]


def test_token_pacer_charges_a_reply_before_the_next_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []
    clock = [0.0]
    monkeypatch.setattr("raw2md.llm.chunking._monotonic", lambda: clock[0])
    monkeypatch.setattr("raw2md.llm.chunking._sleep", slept.append)
    pacer = TokenPacer(100_000)
    rate = 100_000 * 0.7 / 60

    pacer.before_request(3000)
    pacer.after_response(1500)
    pacer.before_request(3000)

    assert slept == [pytest.approx((3000 + 1500) / rate)]


def test_token_pacer_after_response_is_a_no_op_without_a_declared_rate() -> None:
    pacer = TokenPacer(None)

    pacer.after_response(5000)  # must not raise, and before_request stays a no-op
    pacer.before_request(5000)


def test_chunk_budget_follows_the_declared_rate() -> None:
    assert chunk_budget(None) == DEFAULT_CHUNK_TOKENS
    assert chunk_budget(250_000) == int(250_000 * 0.7 * 0.5)
    # Both ends of the declared rate are bounded.
    assert chunk_budget(1_000) == 20_000
    assert chunk_budget(10_000_000) == 150_000


def test_page_index_addresses_a_line_by_page_and_position() -> None:
    index = PageIndex(((0, 1), (10, 2), (20, 3)), line_count=30)

    assert index.address(0) == (1, 1)
    assert index.address(9) == (1, 10)
    assert index.address(10) == (2, 1)
    assert index.address(29) == (3, 10)


def test_page_index_locates_an_address_back_to_its_line() -> None:
    index = PageIndex(((0, 1), (10, 2), (20, 3)), line_count=30)

    assert index.locate(1, 1) == 0
    assert index.locate(2, 3) == 12
    # A missing page, and a line past the page's last one.
    assert index.locate(9, 1) is None
    assert index.locate(2, 11) is None
    assert index.locate(2, 0) is None


def test_page_index_tolerates_an_address_just_past_a_page_end() -> None:
    index = PageIndex(((0, 1), (10, 2)), line_count=20)

    # One line over the page's end is a miscount, not a wrong page.
    assert index.locate(1, 11, slack=2) == 10
    assert index.locate(1, 14, slack=2) is None
    # The overshoot never runs past the body's last line.
    assert index.locate(2, 11, slack=2) == 19


def test_page_index_keeps_a_page_that_produced_no_lines() -> None:
    # A blank page still counts, or every later page would shift.
    index = PageIndex(((0, 1), (5, 2), (5, 3)), line_count=10)

    assert index.numbers == (1, 2, 3)
    assert index.locate(2, 1) is None
    # An empty page has no lines to overshoot.
    assert index.locate(2, 1, slack=2) is None
    assert index.address(5) == (3, 1)


def test_page_index_without_a_map_is_one_page() -> None:
    index = PageIndex((), line_count=40)

    assert index.numbers == (1,)
    assert index.mapped is False
    assert index.address(0) == (1, 1)
    assert index.address(39) == (1, 40)
    assert index.locate(1, 40) == 39


def test_an_unmarked_body_is_sent_whole_however_large(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Without marks there is nothing to cut on, so the request goes out whole
    # and the provider decides.
    op = make_op([_EMPTY_REPLY], budget=400)
    body, _ = make_body()

    with caplog.at_level("WARNING", logger="raw2md"):
        inspect(body, make_pdf(_PAGES), op, ())

    calls = calls_of(op)
    assert len(calls) == 1
    assert page_count(media_of(calls[0]).data) == _PAGES
    assert any("no page marks" in record.message for record in caplog.records)
