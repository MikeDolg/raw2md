"""Acceptance pass: the deterministic re-reading of what inspection wrote.

Inspection writes against the source page, not against the cleaned text, so
the lines it wrote are read once more before post and the verdict. The pass
reads only those lines and never reverts an edit. Three readings, in order:
strip the per-line noise the cleaner removes, count the table rows an edit
left off their grid, and mend a pipe block an edit wrote with no delimiter
row. The mend goes last: it inserts a line, and `TouchedLines` indexes the
body as it arrived.
"""

from __future__ import annotations

from dataclasses import dataclass

from raw2md.cleaning import mend_pipe_block_missing_delimiter, strip_line_noise
from raw2md.mdtext.lines import is_table_separator
from raw2md.mdtext.pages import page_mark_number
from raw2md.mdtext.tables import broken_table_details
from raw2md.mdtext.zones import Segment, block_bounds, segments


@dataclass(frozen=True)
class TouchedLines:
    """Line indices of the body the inspection step itself wrote.

    `edited` holds every line a substitution produced, counted the way
    `zones.segments` counts the body inspection returned.
    """

    edited: frozenset[int] = frozenset()


@dataclass(frozen=True)
class AcceptResult:
    """Outcome of one acceptance pass over a body.

    `stripped` and `mended` rewrote the body; `flagged` counts the broken
    table rows the edits left, which are reported only.
    """

    body: str
    stripped: int
    flagged: int
    mended: int

    @property
    def changed(self) -> bool:
        """True when the pass rewrote the body at all."""
        return bool(self.stripped or self.mended)


def accept(body: str, touched: TouchedLines) -> AcceptResult:
    """Re-read the lines inspection wrote and return the body it should leave.

    A line no edit wrote stays exactly as the cleaner produced it.
    """
    if not touched.edited:
        return AcceptResult(body, 0, 0, 0)

    seg_list = segments(body)
    lines = [line for line, _ in seg_list]
    protected = [is_protected for _, is_protected in seg_list]

    stripped = _strip_edited_lines(lines, protected, touched.edited)
    flagged = _rows_off_the_grid(lines, protected, touched.edited)
    mended = _mend_delimiterless_blocks(lines, protected, touched.edited)

    if not stripped and not mended:
        return AcceptResult(body, 0, len(flagged), 0)
    rebuilt = "\n".join(lines)
    return AcceptResult(
        body=f"{rebuilt}\n" if rebuilt else "",
        stripped=stripped,
        flagged=len(flagged),
        mended=mended,
    )


def _strip_edited_lines(
    lines: list[str], protected: list[bool], edited: frozenset[int]
) -> int:
    """Strip the cleaner's per-line noise from each edited line, in place.

    Protection is read off the body as it now stands: a multi-line replacement
    can open a fence.
    """
    stripped = 0
    for idx in edited:
        if protected[idx]:
            continue
        fixed = strip_line_noise(lines[idx])
        if fixed != lines[idx]:
            lines[idx] = fixed
            stripped += 1
    return stripped


def _rows_off_the_grid(
    lines: list[str], protected: list[bool], edited: frozenset[int]
) -> dict[int, str]:
    """Row index -> what is broken about it, for the rows an edit left off a grid.

    Read over the whole body, since a row is measured against a separator
    several lines above it, then narrowed to the blocks an edit touched. One
    row per block: the defect is the table's.
    """
    if not edited:
        return {}
    seg_list = list(zip(lines, protected, strict=True))
    flagged: dict[int, str] = {}
    for idx, detail in sorted(broken_table_details(seg_list).items()):
        start, end = block_bounds(lines, protected, idx)
        block = range(start, end)
        if not any(line_index in edited for line_index in block):
            continue
        if any(line_index in flagged for line_index in block):
            continue
        flagged[idx] = detail
    return flagged


def _mend_delimiterless_blocks(
    lines: list[str], protected: list[bool], edited: frozenset[int]
) -> int:
    """Give its delimiter row to each pipe block an edit wrote without one.

    Rewrites `lines` and `protected` in place; returns the blocks repaired.
    Top down, so a block can join onto one mended just above it. A repair moves
    nothing outside its slice and every later span lies below it, so a span
    stays right once shifted by the repairs above.
    """
    mended = 0
    offset = 0
    for start, end in _edited_blocks(lines, protected, edited):
        block_start, block_end = start + offset, end + offset
        slice_start = _joinable_table_start(lines, protected, block_start)
        before: list[Segment] = list(
            zip(
                lines[slice_start:block_end],
                protected[slice_start:block_end],
                strict=True,
            )
        )
        after = mend_pipe_block_missing_delimiter(before)
        if after == before:
            continue
        lines[slice_start:block_end] = [line for line, _ in after]
        protected[slice_start:block_end] = [flag for _, flag in after]
        offset += len(after) - len(before)
        mended += 1
    return mended


def _edited_blocks(
    lines: list[str], protected: list[bool], edited: frozenset[int]
) -> list[tuple[int, int]]:
    """The `[start, end)` spans of the blocks an edit wrote in, top down, once each.

    A blank line is skipped: `block_bounds` reads it as the blocks above and
    below together, which would hand the rule a block no edit wrote.
    """
    spans: list[tuple[int, int]] = []
    for idx in sorted(edited):
        if not lines[idx].strip():
            continue
        if spans and spans[-1][0] <= idx < spans[-1][1]:
            continue
        spans.append(block_bounds(lines, protected, idx))
    return spans


def _joinable_table_start(lines: list[str], protected: list[bool], start: int) -> int:
    """Where the slice given to the mending rule opens, for a block at `start`.

    Only the table above tells the rule whether to join the block on or give
    it a header of its own, so the slice opens at that table, across a blank
    line and a page mark. A block above with no delimiter row is not taken in:
    there is no width to join to.
    """
    idx = start - 1
    while (
        idx >= 0
        and not protected[idx]
        and (not lines[idx].strip() or page_mark_number(lines[idx]) is not None)
    ):
        idx -= 1
    if idx < 0 or protected[idx]:
        return start
    above_start, above_end = block_bounds(lines, protected, idx)
    if not any(
        is_table_separator(lines[above].strip())
        for above in range(above_start, above_end)
    ):
        return start
    return above_start
