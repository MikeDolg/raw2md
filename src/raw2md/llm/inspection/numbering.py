"""Recount a chunk's reply that answered in a numbering of its own."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from raw2md.llm.chunking import Chunk, PageIndex
from raw2md.llm.inspection.addressing import (
    ADDRESS_OVERSHOOT_SLACK,
    DisplayUnit,
    fragment_spans,
    matches,
    matches_unit,
    place_quote,
    resolve_address,
    strip_declared_address_prefix,
    wide_drift_anchor,
)
from raw2md.llm.inspection.common import InspectionReplyError, SemanticEdit
from raw2md.llm.inspection.masking import quotes_the_mask

_logger = logging.getLogger("raw2md")


# One reading of a declared `(page, line)`: a body line index, or None.
_Resolve = Callable[[int | None, int], int | None]


@dataclass(frozen=True)
class ChunkFrame:
    """One chunk and the body its reply's addresses have to land in.

    It travels with the request, since a reply in a numbering of its own is
    only recognizable against the chunk it answered.
    """

    chunk: Chunk
    lines: list[str]
    index: PageIndex
    units: dict[int, DisplayUnit]


def _own_page_numbers(frame: ChunkFrame) -> _Resolve:
    """Read a reply's page numbers as a count of the chunk's own pages from one."""

    def resolve(page: int | None, line: int) -> int | None:
        if page is None or page < 1:
            return None
        position = frame.chunk.first_position + page - 1
        if position > frame.chunk.last_position:
            return None
        return frame.index.locate(
            frame.index.numbers[position], line, slack=ADDRESS_OVERSHOOT_SLACK
        )

    return resolve


def _running_line_count(frame: ChunkFrame) -> _Resolve:
    """Read a reply's line numbers as one count running through the chunk."""

    def resolve(page: int | None, line: int) -> int | None:  # noqa: ARG001 -- the _Resolve interface; a running count ignores the page
        if line < 1:
            return None
        line_index = frame.chunk.start + line - 1
        return line_index if line_index < frame.chunk.end else None

    return resolve


# The numberings of its own a chunk's reply has been seen to answer in. A
# reading is adopted for the whole reply or not at all.
_HYPOTHESES: tuple[tuple[str, Callable[[ChunkFrame], _Resolve]], ...] = (
    ("pages counted from one inside the chunk", _own_page_numbers),
    ("lines counted through the chunk", _running_line_count),
)


def realigned(
    edits: tuple[list[SemanticEdit], list[str]],
    frame: ChunkFrame | None,
    what: str,
) -> tuple[list[SemanticEdit], list[str]]:
    """Recount a chunk's addresses when the reply answered in its own numbering.

    A reading is adopted only when a majority of the reply's own quotes stand
    at the lines it computes; the addresses as written are measured first. A
    reply confirming nothing, with no reading to explain it, is unusable. An
    edit quoting a placeholder cannot stand in the body, so it is not counted.
    """
    semantic, flags = edits
    countable = [edit for edit in semantic if not quotes_the_mask(edit)]
    if frame is None or not countable:
        return semantic, flags
    held = _confirmed_nearby(countable, frame)
    if held * 2 > len(countable):
        return semantic, flags
    for reading, build in _HYPOTHESES:
        resolve = build(frame)
        confirmed = _confirmed_at_address(countable, resolve, frame)
        if confirmed * 2 > len(countable):
            _logger.info(
                "inspection: %s answered with %s; recounting its addresses "
                "(%d of %d quotes confirm the recount, %d the addresses as sent)",
                what,
                reading,
                confirmed,
                len(countable),
                held,
            )
            return _readdressed(semantic, frame, resolve), flags
    if held:
        return semantic, flags
    raise InspectionReplyError(
        f"none of the {len(countable)} edits' quotes stands at the address it "
        "names, and no recount of the chunk's own numbering explains them"
    )


def _quote_confirms(frame: ChunkFrame, line_index: int, old: str) -> bool:
    """True when `old` names the line at `line_index` outright.

    The shapes `apply_edits` accepts: the line whole, a formula cut across
    lines, or a fragment standing on the line exactly once.
    """
    unit = frame.units.get(line_index)
    if unit is not None and matches_unit(frame.lines, unit, old):
        return True
    line = frame.lines[line_index]
    return matches(line, old) or len(fragment_spans(line, old)) == 1


def _confirmed_nearby(semantic: list[SemanticEdit], frame: ChunkFrame) -> int:
    """How many quotes find their line under the addresses the reply wrote.

    Read as generously as `apply_edits` reads them, drift window included.
    """
    confirmed = 0
    for edit in semantic:
        old = strip_declared_address_prefix(edit.old, edit.page, edit.line)
        if not old.strip():
            continue
        addressed = resolve_address(frame.index, edit.page, edit.line)
        if addressed is not None and _quote_confirms(frame, addressed, old):
            confirmed += 1
            continue
        anchor = addressed
        if anchor is None and frame.index.mapped:
            anchor = wide_drift_anchor(frame.index, edit.page, edit.line)
        if anchor is None:
            continue
        if place_quote(frame.lines, addressed, anchor, old, edit.new)[0] is not None:
            confirmed += 1
    return confirmed


def _confirmed_at_address(
    semantic: list[SemanticEdit], resolve: _Resolve, frame: ChunkFrame
) -> int:
    """How many quotes stand exactly at the line one reading of the addresses names.

    No window: with one, a wrong reading would collect neighbours and pass.
    """
    confirmed = 0
    for edit in semantic:
        line_index = resolve(edit.page, edit.line)
        if line_index is None:
            continue
        if _confirming_quote(frame, line_index, edit) is not None:
            confirmed += 1
    return confirmed


def _confirming_quote(
    frame: ChunkFrame, line_index: int, edit: SemanticEdit
) -> str | None:
    """The reading of `edit.old` that the line at `line_index` confirms, or None.

    A body line can itself open like an echoed address, so the quote is tried
    as it came and then without the echo.
    """
    if not edit.old.strip():
        return None
    if _quote_confirms(frame, line_index, edit.old):
        return edit.old
    stripped = strip_declared_address_prefix(edit.old, edit.page, edit.line)
    if stripped == edit.old or not stripped.strip():
        return None
    return stripped if _quote_confirms(frame, line_index, stripped) else None


def _readdressed(
    semantic: list[SemanticEdit],
    frame: ChunkFrame,
    resolve: _Resolve,
) -> list[SemanticEdit]:
    """Rewrite the reply's addresses into the ones the body itself uses.

    An echoed address is dropped from the quote now: against the new address
    it would no longer read as an echo. An entry placed nowhere keeps its
    address and counts as a miss.
    """
    moved_semantic: list[SemanticEdit] = []
    for edit in semantic:
        line_index = resolve(edit.page, edit.line)
        if line_index is None:
            moved_semantic.append(edit)
            continue
        page, line = frame.index.address(line_index)
        quote = _confirming_quote(frame, line_index, edit)
        moved_semantic.append(
            replace(edit, page=page, line=line, old=quote or edit.old)
        )
    return moved_semantic
