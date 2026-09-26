"""Chunk planning for inspection of a large source; it sends no request.

A whole book does not fit one request, by tokens or by bytes. A chunk is a run
of whole source pages with the body lines they produced, read off the page
marks rather than guessed, and an edit is addressed by page and line within
the page. A refused chunk can be cut once more (`halve`) at a page boundary,
so every address in it keeps its meaning. A body with no marks is one page.
"""

from __future__ import annotations

import logging
import math
import time
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from raw2md.engines import pymupdf
from raw2md.llm.base import inline_media_bytes

_logger = logging.getLogger("raw2md")

# Token counts are estimates that err high, so a chunk planned under the budget
# stays under it. The API bills a PDF page as a fixed-size image.
_TOKENS_PER_PAGE = 258
# Latin prose runs about 4 characters per token; Cyrillic technical text with
# formulas is denser, so the divisor sits below the worst case seen.
_CHARS_PER_TOKEN = 3
# The per-chunk context note is some 330 bytes, rounded up.
_NOTE_TOKENS = 100
_NOTE_BYTES = 512

# Half of the usable `tpm`, so two chunks fit a minute. The bounds keep an odd
# declared rate from giving hundreds of tiny chunks or one past the context.
_CHUNK_SHARE = 0.5
_MIN_CHUNK_TOKENS = 20_000
_MAX_CHUNK_TOKENS = 150_000
# With no declared rate there is no pacing, so the request stays moderate.
DEFAULT_CHUNK_TOKENS = 100_000

# The provider bills about 6% more than this estimator predicts, and a margin
# of 0.8 still overshot; `TokenPacer` charges the reply's tokens as well.
_TPM_SAFETY = 0.7

# Eight pages fit a budget of any usual size; a narrow budget cuts the window
# down to a single page. `pages_per_request` in settings.json overrides it.
DEFAULT_PAGES_PER_REQUEST = 8

# A page's bytes are estimated from the document's average page. In a
# scan-heavy book a page range weighed up to about 2.5 times that average.
_PAGE_BYTES_SAFETY = 3


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _monotonic() -> float:
    return time.monotonic()


@dataclass(frozen=True)
class Chunk:
    """One inspection request: a run of source pages and the body they produced.

    `start`/`end` are body line indices (`end` exclusive); `first_page` and
    `last_page` are 0-based source pages, inclusive and clamped to the source.
    `first_position`/`last_position` are the same pages in the `PageIndex`,
    which `halve` cuts by. `tokens` is the estimated request size.
    """

    start: int
    end: int
    first_page: int
    last_page: int
    first_position: int
    last_position: int
    tokens: int


@dataclass(frozen=True)
class _Limits:
    """The ceilings one chunk has to stay under, resolved once per file.

    `overhead` is what every request pays before a page: the prompt and the
    chunk note. `page_bytes` is one source page inside a request, encoded.
    """

    budget: int
    overhead: int
    overhead_bytes: int
    pages: int
    max_bytes: int
    page_bytes: int


class PageIndex:
    """Which source page each body line came from, and the reverse.

    Built from pairs of (body line index, 1-based source page). A page with no
    lines keeps an empty range: dropping it would shift every later address.
    A body with no map is one page, and `mapped` is False, because that page
    says nothing about where the source's pages are.
    """

    def __init__(self, pages: Sequence[tuple[int, int]], line_count: int) -> None:
        self._line_count = line_count
        self._mapped = bool(pages)
        self._numbers: tuple[int, ...]
        self._starts: tuple[int, ...]
        if not pages:
            self._numbers = (1,)
            self._starts = (0,)
        else:
            # Lines above the first mark belong to the first page.
            self._numbers = tuple(page for _, page in pages)
            self._starts = (0, *(line for line, _ in pages[1:]))

    @property
    def numbers(self) -> tuple[int, ...]:
        """The 1-based source page numbers, in body order."""
        return self._numbers

    @property
    def mapped(self) -> bool:
        """True when the index was built from real page marks."""
        return self._mapped

    def bounds(self, position: int) -> tuple[int, int]:
        """Body line range ``[start, end)`` of the page at `position` in the index."""
        start = self._starts[position]
        end = (
            self._starts[position + 1]
            if position + 1 < len(self._starts)
            else self._line_count
        )
        return start, max(start, end)

    def address(self, line: int) -> tuple[int, int]:
        """The (page number, 1-based line within that page) address of `line`."""
        position = max(0, bisect_right(self._starts, line) - 1)
        return self._numbers[position], line - self._starts[position] + 1

    def locate(self, page: int, line_in_page: int, *, slack: int = 0) -> int | None:
        """The body line index addressed by (page, line), or None when there is none.

        `slack` admits an address a line or two past the page's end, where the
        text runs onto the next page; the text at that line still has to
        confirm the edit. A page with no lines gets no slack: the lines it would
        reach belong to a page that was addressable anyway.
        """
        if line_in_page < 1 or not self._line_count:
            return None
        try:
            position = self._numbers.index(page)
        except ValueError:
            return None
        start, end = self.bounds(position)
        line = start + line_in_page - 1
        if line < end:
            return line
        if start < end and line < end + slack:
            return min(line, self._line_count - 1)
        return None


class TokenPacer:
    """Spaces chunk requests so their token rate stays under the declared `tpm`.

    Each request is charged up front and the next one waits out that cost.
    With no declared `tpm` pacing is off. It overlaps the provider's `rpm`
    throttle rather than stacking on it.
    """

    def __init__(self, tpm: int | None) -> None:
        self._rate = tpm * _TPM_SAFETY / 60.0 if tpm and tpm > 0 else None
        self._next_allowed_at: float | None = None

    def before_request(self, tokens: int) -> None:
        """Wait out the previous request's token cost, then charge this one."""
        if self._rate is None:
            return
        now = _monotonic()
        if self._next_allowed_at is not None:
            wait = self._next_allowed_at - now
            if wait > 0:
                _logger.info("inspection: pacing %.0fs to stay under tpm", wait)
                _sleep(wait)
                now = _monotonic()
        self._next_allowed_at = now + tokens / self._rate

    def after_response(self, tokens: int) -> None:
        """Charge a reply's tokens, billed against the same per-minute budget."""
        if self._rate is None or self._next_allowed_at is None:
            return
        self._next_allowed_at += tokens / self._rate


def chunk_budget(tpm: int | None) -> int:
    """Token ceiling for one inspection request, derived from the model's `tpm`."""
    if not tpm or tpm <= 0:
        return DEFAULT_CHUNK_TOKENS
    usable = int(tpm * _TPM_SAFETY * _CHUNK_SHARE)
    return max(_MIN_CHUNK_TOKENS, min(_MAX_CHUNK_TOKENS, usable))


def estimate_tokens(text: str) -> int:
    """Estimated token cost of a text part."""
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def plan(
    numbered: list[str],
    source: bytes,
    index: PageIndex,
    *,
    budget: int,
    prompt_tokens: int,
    prompt_bytes: int,
    pages_per_chunk: int,
    max_bytes: int,
) -> list[Chunk] | None:
    """Plan the inspection requests for one file, or None for one request.

    `numbered` is the text as the request shows it, page-scoped addresses and
    masking included, so every ceiling weighs what is sent. The narrowest of
    three ceilings governs: tokens, the page window, and bytes. None also comes
    back for an unreadable source and for a body with no page marks: a chunk on
    the stand-in page would hide the rest of the source from the model.
    """
    page_count = _page_count(source)
    if page_count is None or not numbered:
        return None

    costs = [estimate_tokens(line) + 1 for line in numbered]  # +1 for the newline
    byte_costs = [len(line.encode("utf-8")) + 1 for line in numbered]
    total = prompt_tokens + sum(costs) + _page_tokens(page_count)
    # The whole source's size is exact, so the single-request check needs no
    # estimate.
    total_bytes = prompt_bytes + inline_media_bytes(len(source)) + sum(byte_costs)
    if (
        total <= budget
        and len(index.numbers) <= pages_per_chunk
        and total_bytes <= max_bytes
    ):
        return None
    if not index.mapped:
        _logger.warning(
            "inspection: body carries no page marks; sending the whole source "
            "in one request (~%d tokens against a %d budget, %d bytes against "
            "a %d limit)",
            total,
            budget,
            total_bytes,
            max_bytes,
        )
        return None

    limits = _Limits(
        budget=budget,
        overhead=prompt_tokens + _NOTE_TOKENS,
        overhead_bytes=prompt_bytes + _NOTE_BYTES,
        pages=pages_per_chunk,
        max_bytes=max_bytes,
        page_bytes=inline_media_bytes(math.ceil(len(source) / page_count))
        * _PAGE_BYTES_SAFETY,
    )
    chunks = _cut(index, costs, byte_costs, page_count, limits)
    _logger.info(
        "inspection: ~%d tokens and %d bytes over %d pages against a %d budget "
        "and a %d-byte limit; split into %d requests",
        total,
        total_bytes,
        len(index.numbers),
        budget,
        max_bytes,
        len(chunks),
    )
    return chunks


def halve(
    chunk: Chunk, index: PageIndex, numbered: Sequence[str]
) -> tuple[Chunk, Chunk] | None:
    """Cut `chunk` in two at a page boundary, or None when it holds one page.

    Each half carries its parent's request overhead, read back out of the
    parent's estimate so the two cannot drift apart.
    """
    first, last = chunk.first_position, chunk.last_position
    if first == last:
        return None
    middle = first + (last - first + 1) // 2
    overhead = (
        chunk.tokens
        - _line_tokens(numbered, chunk.start, chunk.end)
        - _page_tokens(chunk.last_page - chunk.first_page + 1)
    )
    return (
        _half(chunk, index, numbered, first, middle - 1, overhead),
        _half(chunk, index, numbered, middle, last, overhead),
    )


def _half(
    parent: Chunk,
    index: PageIndex,
    numbered: Sequence[str],
    first: int,
    last: int,
    overhead: int,
) -> Chunk:
    """One half of `parent`, its source pages held inside the parent's range."""
    start = index.bounds(first)[0]
    end = index.bounds(last)[1]
    first_page = _held_inside(index.numbers[first] - 1, parent)
    last_page = max(_held_inside(index.numbers[last] - 1, parent), first_page)
    return Chunk(
        start=start,
        end=end,
        first_page=first_page,
        last_page=last_page,
        first_position=first,
        last_position=last,
        tokens=overhead
        + _line_tokens(numbered, start, end)
        + _page_tokens(last_page - first_page + 1),
    )


def _held_inside(page: int, parent: Chunk) -> int:
    return min(max(page, parent.first_page), parent.last_page)


def _line_tokens(numbered: Sequence[str], start: int, end: int) -> int:
    """Estimated tokens of the body lines `[start, end)`, newline included."""
    return sum(estimate_tokens(line) + 1 for line in numbered[start:end])


def _page_count(source: bytes) -> int | None:
    """Page count of the source PDF, or None when it cannot be read."""
    try:
        count = pymupdf.count_pages_bytes(source)
    except (RuntimeError, ValueError, OSError) as exc:
        _logger.warning("inspection: cannot read source pages, sending whole: %s", exc)
        return None
    return count if count > 0 else None


def _page_tokens(pages: int) -> int:
    return pages * _TOKENS_PER_PAGE


def _cut(
    index: PageIndex,
    costs: list[int],
    byte_costs: list[int],
    page_count: int,
    limits: _Limits,
) -> list[Chunk]:
    """Group consecutive pages greedily into chunks under every limit.

    A single page over a limit cannot be divided, so it is sent alone.
    """
    chunks: list[Chunk] = []
    total_pages = len(index.numbers)
    position = 0
    while position < total_pages:
        start, _ = index.bounds(position)
        end = start
        md_tokens = 0
        md_bytes = 0
        last = position
        for offset in range(limits.pages):
            if position + offset >= total_pages:
                break
            page_start, page_end = index.bounds(position + offset)
            page_tokens = sum(costs[page_start:page_end])
            page_bytes = sum(byte_costs[page_start:page_end])
            pages_so_far = offset + 1
            tokens = (
                limits.overhead + md_tokens + page_tokens + _page_tokens(pages_so_far)
            )
            request_bytes = (
                limits.overhead_bytes
                + md_bytes
                + page_bytes
                + limits.page_bytes * pages_so_far
            )
            if offset > 0 and (
                tokens > limits.budget or request_bytes > limits.max_bytes
            ):
                break
            md_tokens += page_tokens
            md_bytes += page_bytes
            end = page_end
            last = position + offset
        first_page, last_page = _source_pages(index, position, last, page_count)
        chunks.append(
            Chunk(
                start=start,
                end=end,
                first_page=first_page,
                last_page=last_page,
                first_position=position,
                last_position=last,
                tokens=limits.overhead
                + md_tokens
                + _page_tokens(last_page - first_page + 1),
            )
        )
        position = last + 1
    return chunks


def _source_pages(
    index: PageIndex, first: int, last: int, page_count: int
) -> tuple[int, int]:
    """The 0-based source page range a chunk's pages cut out of the document.

    A mark past the source's last page means body and source disagree.
    Clamping costs a missed defect; an out-of-range cut would fail the request.
    """
    first_page = min(max(index.numbers[first] - 1, 0), page_count - 1)
    last_page = min(max(index.numbers[last] - 1, first_page), page_count - 1)
    return first_page, last_page
