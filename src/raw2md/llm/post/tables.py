"""Table route: a table whose markup states its own damage, sent as a row list.

Each row is judged alone, so a reply lands the rows it got right and the zone
reverts only when none did. Rows too wide for one reply go in parts.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from raw2md.llm.base import Part, ProviderError, TextPart
from raw2md.llm.edit_guard import table_values_kept
from raw2md.llm.post.common import (
    ENTRY_REPLY_OVERHEAD,
    LIST_WRAPPER_CHARS,
    MAX_REPLY_CHARS,
    REPLY_REASON_LIMIT,
    TRACE_OP,
    PostOperation,
    ZoneOutcome,
    block_end,
    log_unparsed_reply,
    normalized_zone,
    parse_text_edits,
    retry_note,
    schema_reply,
)
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.lines import is_table_separator
from raw2md.mdtext.math_spans import math_spans
from raw2md.mdtext.tables import (
    ColumnForms,
    cell_values,
    crushed_stack_size,
    has_cell_separator,
    rebuild_table_row,
    row_holds_a_crushed_stack,
    table_cells,
    table_column_forms,
)
from raw2md.mdtext.zones import Segment

TABLE_ZONE_NAME = "broken-table"


# Restates the reply shape: an older prompts.yaml still describes the
# whole-zone reply.
_TABLE_ZONE_LABEL = (
    'Table zone to repair. Every row carries its own index as "N: ". Repair '
    "the rows named open below and leave every other row exactly as it "
    "stands. Reply with the JSON row "
    'list -- {"rows": [{"row": N, "text": "<the repaired row>"}]} -- naming '
    "only the rows you change, each written whole with its pipes and without "
    "its index prefix. Do not reply with Markdown.\n"
)

# The wrapper matches the label, so a constrained reply and a free-text one
# decode the same way.
_ROWS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "row": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["row", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rows"],
}


_TABLE_REPLY_REASON = "the reply was not the JSON row list this zone asks for"
_TABLE_NO_EDIT_REASON = "the reply named no row that differs from the row it was given"


@dataclass(frozen=True)
class TableZone:
    """One whole table, gathered across the blocks a page break cut it into.

    `lines` keep the blank gaps. `rows` maps a 1-based row index, as the
    request prints it, to a position in `lines`. Only `repairable` rows are
    open to repair; `continuation` rows are named closed. `forms` are the
    column value shapes of the sound rows.
    """

    start: int
    end: int
    lines: list[str]
    rows: dict[int, int]
    separator: int
    width: int
    repairable: frozenset[int]
    continuation: frozenset[int]
    forms: ColumnForms


def table_zone(seg_list: list[Segment], index: int) -> TableZone | None:
    """The table the block at `index` belongs to, or None when it is not one.

    Gathered across page-break gaps, so a broken row several blocks down gets
    the header and the delimiter row. The span is a table only when some row
    has the delimiter row's cell count, as the cleaner reads it.
    """
    end = _table_span_end(seg_list, index)
    if end is None:
        return None
    lines = [seg_list[k][0] for k in range(index, end)]
    rows: dict[int, int] = {}
    separator: int | None = None
    width = 0
    for position, line in enumerate(lines):
        if not line.strip():
            continue
        rows[len(rows) + 1] = position
        if separator is None and is_table_separator(line.strip()):
            separator = position
            width = len(table_cells(line))
    if separator is None:
        return None
    if not any(
        len(table_cells(lines[position])) == width
        for position in rows.values()
        if position != separator
    ):
        return None
    header = max(
        (position for position in rows.values() if position < separator),
        default=None,
    )
    forms = table_column_forms(
        (
            lines[position]
            for position in rows.values()
            if position not in (separator, header)
        ),
        width,
        None if header is None else lines[header],
    )
    return TableZone(
        start=index,
        end=end,
        lines=lines,
        rows=rows,
        separator=separator,
        width=width,
        repairable=frozenset(
            number
            for number, position in rows.items()
            if position != separator
            and _row_needs_repair(lines[position], width, forms)
        ),
        continuation=frozenset(
            number
            for number, position in rows.items()
            if position != separator
            and _row_is_continuation(lines[position], width, forms)
        ),
        forms=forms,
    )


def _row_needs_repair(line: str, width: int, forms: ColumnForms) -> bool:
    """True when the row itself shows the grid is wrong on it.

    Off the declared width, or a crushed stack against the table's own column
    shapes. A value slid into the next column shows nothing here; only the
    source page shows it.
    """
    return len(table_cells(line)) != width or row_holds_a_crushed_stack(line, forms)


def _row_is_continuation(line: str, width: int, forms: ColumnForms) -> bool:
    """True when the row is one wrapped value a converter left on its own line.

    Sound as markup, but the model keeps proposing to merge it upward, which
    the row protocol cannot express; the request names it closed.
    """
    cells = table_cells(line)
    if width < 2 or len(cells) != width:
        return False
    if sum(1 for cell in cells if cell.strip()) != 1:
        return False
    return not row_holds_a_crushed_stack(line, forms)


def _table_span_end(seg_list: list[Segment], start: int) -> int | None:
    """Index past the last line of the table opening at `start`, or None."""
    if not _is_table_block(seg_list, start, block_end(seg_list, start)):
        return None
    end = block_end(seg_list, start)
    while True:
        gap = end
        while gap < len(seg_list):
            line, protected = seg_list[gap]
            if protected or line.strip():
                break
            gap += 1
        if gap == end or gap >= len(seg_list) or seg_list[gap][1]:
            return end
        next_end = block_end(seg_list, gap)
        if not _is_table_continuation(seg_list, gap, next_end):
            return end
        end = next_end


def _is_table_block(seg_list: list[Segment], start: int, end: int) -> bool:
    content = [seg_list[k][0] for k in range(start, end)]
    return bool(content) and all(has_cell_separator(line) for line in content)


def _is_table_continuation(seg_list: list[Segment], start: int, end: int) -> bool:
    """True when the block at `start` carries rows of a table already open.

    A block with a delimiter row of its own opens a new table; the cleaner has
    already folded a reprinted header back.
    """
    if not _is_table_block(seg_list, start, end):
        return False
    lines = [seg_list[k][0] for k in range(start, end)]
    return not any(is_table_separator(line.strip()) for line in lines)


def process_table_zone(
    zone: TableZone,
    op: PostOperation,
    *,
    trace: LlmTrace | None = None,
    what: str = "zone",
) -> ZoneOutcome:
    """Repair one table zone from a row-indexed reply.

    Rows too wide for one reply go in parts, each with the header and the
    delimiter row; a table too long for one request sends its open rows only.
    Each row is judged alone, and the zone reverts only when no row landed.
    """
    parts_rows = _reply_parts(zone)
    split = len(parts_rows) > 1
    focused = split or not _whole_zone_fits(zone, op)
    lines = list(zone.lines)
    accepted = 0
    refused = 0
    unchanged = True
    failure: ProviderError | None = None
    for index, focus in enumerate(parts_rows, start=1):
        label = f"{what} part {index}/{len(parts_rows)}" if split else what
        part = _repair_part(
            zone,
            lines,
            focus if focused else None,
            op,
            trace=trace,
            what=label,
        )
        refused += part.refused
        if part.failure is not None:
            # The rows earlier parts repaired stand.
            failure = part.failure
            break
        lines = part.lines
        accepted += part.accepted
        if not part.unchanged:
            unchanged = False
    if accepted:
        return ZoneOutcome(
            lines,
            True,
            repaired_rows=accepted,
            refused_rows=refused,
            failure=failure,
        )
    return ZoneOutcome(
        zone.lines,
        False,
        refused_rows=refused,
        unchanged=unchanged,
        failure=failure,
    )


@dataclass(frozen=True)
class _PartOutcome:
    """What one part of a table zone came back as, for the zone to sum up."""

    lines: list[str]
    accepted: int
    refused: int
    unchanged: bool
    failure: ProviderError | None = None


def _repair_part(
    zone: TableZone,
    base_lines: list[str],
    focus: frozenset[int] | None,
    op: PostOperation,
    *,
    trace: LlmTrace | None = None,
    what: str = "zone",
) -> _PartOutcome:
    """Run one table request -- the whole zone, or the rows of one part of it.

    A reply naming a row outside `focus` is passed over in silence.
    """
    request = TextPart(_table_request(zone, focus))
    parts: list[Part] = [request]
    refused = 0
    unchanged = False
    for attempt in (1, 2):  # the initial attempt plus one retry
        try:
            reply = schema_reply(op, parts, _ROWS_SCHEMA)
        except ProviderError as exc:
            # Rows an earlier attempt turned down were judged, not lost.
            return _PartOutcome(base_lines, 0, refused, unchanged, failure=exc)
        if trace is not None:
            trace.record(TRACE_OP, what, parts, reply.text, attempt=attempt)
        edits = parse_text_edits(reply.text, "rows", "row")
        if edits is None:
            log_unparsed_reply(reply, what, attempt=attempt, listing="row list")
        verdict = _repaired_table(zone, edits, base_lines, focus)
        refused += verdict.refused
        if verdict.lines is not None:
            return _PartOutcome(verdict.lines, verdict.accepted, refused, False)
        assert verdict.reason is not None  # every rejection branch sets one
        unchanged = verdict.unchanged
        if unchanged:
            break  # an echo is terminal: a retry note has nothing to correct
        parts = [request, TextPart(retry_note(verdict.reason))]
    return _PartOutcome(base_lines, 0, refused, unchanged)


def _reply_parts(zone: TableZone) -> list[frozenset[int]]:
    """The zone's repairable rows split so each part's worst-case reply fits.

    A row wider than the budget alone still forms its own part.
    """
    parts: list[list[int]] = []
    current: list[int] = []
    size = LIST_WRAPPER_CHARS
    for number in sorted(zone.repairable):
        cost = ENTRY_REPLY_OVERHEAD + len(zone.lines[zone.rows[number]])
        if current and size + cost > MAX_REPLY_CHARS:
            parts.append(current)
            current = []
            size = LIST_WRAPPER_CHARS
        current.append(number)
        size += cost
    if current:
        parts.append(current)
    return [frozenset(part) for part in parts]


def _whole_zone_fits(zone: TableZone, op: PostOperation) -> bool:
    """True when the zone's every row fits one request beside the prompt.

    The reply budget does not bound what a request sends: hundreds of sound
    rows beside one damaged row draw a one-row reply.
    """
    request = _table_request(zone)
    sent = len(op.prompt.encode("utf-8")) + len(request.encode("utf-8"))
    return sent <= op.provider.request_byte_limit


def _row_damage(zone: TableZone, number: int) -> str:
    """How the request states one open row's damage, in the guard's own measures.

    Without the numbers the model under-spread stacks and guessed widths.
    """
    line = zone.lines[zone.rows[number]]
    measures: list[str] = []
    held = len(table_cells(line))
    if held != zone.width:
        measures.append(f"holds {held} cells, not the {zone.width}")
    size = crushed_stack_size(line, zone.forms)
    if size is not None:
        measures.append(f"{size} values crushed into one cell")
    return f"row {number} ({'; '.join(measures)})"


def _open_rows_note(zone: TableZone, focus: frozenset[int] | None) -> str:
    """The lines naming which rows are open to repair, and the measure of each.

    For the whole zone the continuation rows are named closed too.
    """
    open_rows = sorted(focus if focus is not None else zone.repairable)
    listed = "; ".join(_row_damage(zone, number) for number in open_rows)
    note = (
        f"The separator row declares {zone.width} cells; every repaired row "
        f"holds exactly {zone.width}. A run of values crushed into one cell "
        "spreads into the empty cells beside it rather than into cells of its "
        "own, so a cell that run leaves empty goes out of the row with it. "
        "The values stay in the order the row already holds them, left to "
        "right: a repair puts back the boundaries between them and moves none "
        "of them past another.\n"
        f"Rows open to repair: {listed}.\n"
    )
    if focus is None and zone.continuation:
        rows = ", ".join(str(number) for number in sorted(zone.continuation))
        note += (
            f"Leave rows {rows} exactly as they stand: each is one wrapped "
            "value on a line of its own, holds the width already, and cannot "
            "be merged here.\n"
        )
    return note


def _table_request(zone: TableZone, focus: frozenset[int] | None = None) -> str:
    """The table as the model sees it: every row behind its own index.

    Page-break gaps are dropped. With `focus`, only the header, the delimiter
    row, and those rows are shown, since the reply repeats every row shown.
    """
    numbers = {position: number for number, position in zone.rows.items()}
    if focus is None:
        shown = [
            line if position not in numbers else f"{numbers[position]}: {line}"
            for position, line in enumerate(zone.lines)
            if line.strip()
        ]
        return _TABLE_ZONE_LABEL + _open_rows_note(zone, None) + "\n".join(shown)
    keep = _focus_positions(zone, focus)
    shown = [
        f"{numbers[position]}: {zone.lines[position]}"
        if position in numbers
        else zone.lines[position]
        for position in sorted(keep)
        if zone.lines[position].strip()
    ]
    return (
        _TABLE_ZONE_LABEL
        + _focus_note(sorted(focus))
        + _open_rows_note(zone, focus)
        + "\n".join(shown)
    )


def _focus_positions(zone: TableZone, focus: frozenset[int]) -> set[int]:
    """The `zone.lines` positions one part shows: header, delimiter, focus rows."""
    keep = {zone.separator}
    header = _header_position(zone)
    if header is not None:
        keep.add(header)
    for number in focus:
        position = zone.rows[number]
        keep.add(position)
    return keep


def _header_position(zone: TableZone) -> int | None:
    above = [position for position in zone.rows.values() if position < zone.separator]
    return max(above) if above else None


def _focus_note(rows: list[int]) -> str:
    """The line telling a narrowed part which rows it -- and its reply -- may cover."""
    listed = ", ".join(str(number) for number in rows)
    return (
        f"This request covers rows {listed} only: they are part of a larger "
        "table, and the rows not shown here are left out of this request. "
        "Reply with the JSON row list for these rows alone.\n"
    )


@dataclass(frozen=True)
class _TableVerdict:
    """The verdict on one table reply: `lines` when a row was accepted.

    `unchanged` marks a reply naming no changed row: this route's echo.
    """

    lines: list[str] | None
    reason: str | None
    accepted: int = 0
    refused: int = 0
    unchanged: bool = False


def _repaired_table(
    zone: TableZone,
    edits: dict[int, str] | None,
    base_lines: list[str],
    focus: frozenset[int] | None,
) -> _TableVerdict:
    """Apply onto `base_lines` the row edits a reply names that the rules accept.

    `base_lines` carry the earlier parts' edits. An unchanged row and a row
    outside `focus` are passed over in silence. A row is squeezed, then judged,
    and written in the form it was judged in.
    """
    if edits is None:
        return _TableVerdict(None, _TABLE_REPLY_REASON)
    lines = list(base_lines)
    repaired = 0
    reasons: list[str] = []
    for number in sorted(edits):
        if focus is not None and number not in focus:
            continue
        position = zone.rows.get(number)
        if position is None:
            reasons.append(f"row {number} is not a row of this zone")
            continue
        if position == zone.separator:
            reasons.append(
                f"row {number} is the separator row, which declares the table's "
                "width and must be left as it stands"
            )
            continue
        if number in zone.continuation:
            reasons.append(
                f"row {number} is a continuation row, named closed in the "
                "request: it carries one wrapped value on a line of its own, "
                "holds the width already, and cannot be merged here"
            )
            continue
        if number not in zone.repairable:
            reasons.append(
                f"row {number} holds the width its separator declares and "
                "crushes no run of values into one cell; only a row whose own "
                "markup shows the grid wrong is open to repair"
            )
            continue
        original = zone.lines[position]
        candidate = edits[number]
        if normalized_zone([candidate]) == normalized_zone([original]):
            continue
        candidate = _squeezed_row(candidate, zone.width)
        reason = _row_rejection(original, candidate, zone.width, zone.forms)
        if reason is not None:
            reasons.append(f"row {number}: {reason}")
            continue
        lines[position] = candidate
        repaired += 1
    if not repaired:
        reason = (
            "; ".join(reasons[:REPLY_REASON_LIMIT])
            if reasons
            else _TABLE_NO_EDIT_REASON
        )
        return _TableVerdict(None, reason, refused=len(reasons), unchanged=not reasons)
    return _TableVerdict(lines, None, accepted=repaired, refused=len(reasons))


def _squeezed_row(candidate: str, width: int) -> str:
    """`candidate` rebuilt from its filled cells when they are the declared width.

    A model spreading a crushed run leaves the run's old cells empty, so a
    sound repair comes back too wide. A row already at the width keeps its
    empty cells: those are columns the table leaves blank.
    """
    cells = table_cells(candidate)
    if len(cells) == width:
        return candidate
    filled = [cell for cell in cells if cell.strip()]
    if len(filled) != width:
        return candidate
    return rebuild_table_row(candidate, filled)


def _row_rejection(
    original: str, candidate: str, width: int, forms: ColumnForms
) -> str | None:
    """Why the zone will not take `candidate` for its row, or None when it will.

    The row holds the width, no crushed stack, its formulas, and its values in
    order; only the grid moves.
    """
    if "\n" in candidate or "\r" in candidate:
        return "a row is one line, and this one carries a line break"
    if not has_cell_separator(candidate):
        return "it is not a table row"
    cells = len(table_cells(candidate))
    if cells != width:
        return f"it holds {cells} cells, not the {width} the separator row declares"
    # The column forms tell a lost boundary from a value with a space (`1 000`).
    if row_holds_a_crushed_stack(candidate, forms):
        return "its values are still stacked inside one cell"
    if Counter(math_spans(candidate)) != Counter(math_spans(original)):
        return "a formula's content changed; math spans must match the original exactly"
    if not table_values_kept(original, candidate):
        # An order-only mismatch is named as one, or the retry has nothing to
        # correct and repeats the permutation.
        if Counter(cell_values(candidate)) == Counter(cell_values(original)):
            return (
                "the row carries its values in another order; a repair puts "
                "back the boundaries between them and moves none of them past "
                "another"
            )
        return (
            "the row carries values it was not given; a repair moves a value "
            "into the cell it belongs to and changes none of them"
        )
    return None
