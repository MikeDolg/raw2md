"""The grid of a GFM table: cells, width, and lost column boundaries.

Two readings of a damaged table: a row off the separator's width, and a grid
lost at the right width, where a row's values crushed into one cell.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from raw2md.mdtext.lines import is_table_separator
from raw2md.mdtext.pages import page_mark_number
from raw2md.mdtext.zones import Segment, mask_inline_code


def table_cells(line: str) -> list[str]:
    """Split a GFM table row into its cell texts, dropping the outer border pipes."""
    inner = line.strip()
    inner = inner.removeprefix("|")
    inner = inner.removesuffix("|")
    return re.split(r"(?<!\\)\|", inner)


def _table_cells(line: str) -> int:
    """Number of GFM table cells in `line`, dropping the outer border pipes."""
    return len(table_cells(line))


def rebuild_table_row(line: str, cells: list[str]) -> str:
    """Write `cells` back into `line`'s row, keeping its indent and border pipes."""
    indent = line[: len(line) - len(line.lstrip())]
    stripped = line.strip()
    has_lead = stripped.startswith("|")
    has_trail = stripped.endswith("|")
    rebuilt = "|".join(cells)
    return f"{indent}{'|' if has_lead else ''}{rebuilt}{'|' if has_trail else ''}"


# `\|` is a printed pipe inside a cell.
CELL_SEPARATOR_RE = re.compile(r"(?<!\\)\|")

# A converter crushing source lines into one cell writes one per line.
CELL_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def has_cell_separator(line: str) -> bool:
    """True when `line` carries an unescaped pipe outside inline code."""
    return bool(CELL_SEPARATOR_RE.search(mask_inline_code(line)))


def detect_broken_tables(seg_list: list[Segment]) -> dict[int, tuple[int, int]]:
    """Row index -> (table width, row cells) for rows that miss the width.

    The width is the separator's cell count, not the header's: a paragraph
    glued onto the header would otherwise flag every body row. Some row must
    carry that count, or the block is a setext heading.
    """
    flagged: dict[int, tuple[int, int]] = {}
    count = len(seg_list)
    idx = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected or "|" not in line or not line.strip():
            idx += 1
            continue
        separator = idx + 1
        if separator >= count:
            break
        sep_line, sep_protected = seg_list[separator]
        if sep_protected or not is_table_separator(sep_line.strip()):
            idx += 1
            continue
        width = _table_cells(sep_line)
        header_cells = _table_cells(line)
        body_rows: list[tuple[int, int]] = []
        body = separator + 1
        while body < count:
            body_line, body_protected = seg_list[body]
            if body_protected or "|" not in body_line or not body_line.strip():
                break
            body_rows.append((body, _table_cells(body_line)))
            body += 1
        if header_cells == width or any(cells == width for _, cells in body_rows):
            if header_cells != width:
                flagged[idx] = (width, header_cells)
            flagged.update(
                (row, (width, cells)) for row, cells in body_rows if cells != width
            )
        idx = body
    return flagged


def detect_collapsed_grids(seg_list: list[Segment]) -> dict[int, str]:
    """Row index -> finding detail, for a table whose grid is lost, not off width.

    A lost grid keeps the width, so `detect_broken_tables` misses it. Two
    shapes: a row whose values crushed into one cell (`_crushed_row_stack`),
    and a header that is missing or empty, which GFM renders as no table.
    Some row must carry the delimiter's cell count.
    """
    flagged: dict[int, str] = {}
    count = len(seg_list)
    idx = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected or "|" not in line or not is_table_separator(line.strip()):
            idx += 1
            continue
        width = _table_cells(line)
        body_end = idx + 1
        while body_end < count:
            body_line, body_protected = seg_list[body_end]
            if body_protected or "|" not in body_line or not body_line.strip():
                break
            body_end += 1
        header = _table_header_row(seg_list, idx)
        rows = list(range(idx + 1, body_end))
        if header is not None:
            rows.insert(0, header)
        if any(_table_cells(seg_list[row][0]) == width for row in rows):
            flagged.update(_grid_loss(seg_list, idx, header, rows, width))
        idx = body_end
    return flagged


def broken_table_details(seg_list: list[Segment]) -> dict[int, str]:
    """Row index -> what is broken about it, over both readings of a table.

    One detail per row; the measured width reading wins.
    """
    details = {
        idx: f"expected={width} got={cells}"
        for idx, (width, cells) in detect_broken_tables(seg_list).items()
    }
    for idx, detail in detect_collapsed_grids(seg_list).items():
        details.setdefault(idx, detail)
    return details


def _table_header_row(seg_list: list[Segment], separator: int) -> int | None:
    """Index of the row a delimiter row reads its column titles off, or None.

    Page marks are stepped over, so they cannot change a decision.
    """
    idx = separator - 1
    while idx >= 0:
        line, protected = seg_list[idx]
        if protected:
            return None
        if page_mark_number(line) is None:
            return idx if line.strip() and "|" in line else None
        idx -= 1
    return None


def _grid_loss(
    seg_list: list[Segment],
    separator: int,
    header: int | None,
    rows: list[int],
    width: int,
) -> dict[int, str]:
    """The details of one table's grid losses, keyed by the row that shows each.

    A missing header is reported on the delimiter row. A row keeps its first
    detail.
    """
    flagged: dict[int, str] = {}
    if header is None:
        flagged[separator] = "header=missing"
    elif not any(cell.strip() for cell in table_cells(seg_list[header][0])):
        flagged[header] = "header=empty"
    forms = table_column_forms(
        (seg_list[row][0] for row in rows if row != header),
        width,
        None if header is None else seg_list[header][0],
    )
    for row in rows:
        pieces = _crushed_row_stack(table_cells(seg_list[row][0]), forms)
        if pieces is not None:
            flagged.setdefault(row, f"collapsed={pieces} width={width}")
    return flagged


# One value with no space inside; a wrapped sentence fails it.
_CRUSHED_PIECE_RE = re.compile(
    r"^[\w.,\-+/×%()°'\"]+$"  # noqa: RUF001 -- the printed dimension sign
)


def _crushed_cell_rows(cell: str, *, sole: bool) -> list[list[str]]:
    """The printed rows one cell holds, each as the values it runs together.

    `<br>` ends a printed row; a space is a lost boundary. Lines with several
    values each must agree on the count: one boundary was lost, not one per
    line. Lines with one value each are a column's own content, unless the
    cell is `sole` in its row. Every piece must read as a value, and outside
    a sole cell must hold a digit: `Speed` over `rpm` is a stacked title. A
    number with group spaces (`17 440`) is no run.
    """
    stack = [piece.strip() for piece in CELL_BREAK_RE.split(cell)]
    stack = [piece for piece in stack if piece]
    if len(stack) > 1:
        rows = [line.split() for line in stack]
        if max(len(row) for row in rows) > 1:
            if len({len(row) for row in rows}) > 1 or not _rows_read_as_values(rows):
                return []
            return _run_rows(rows)
        if not sole or not all(_CRUSHED_PIECE_RE.match(piece) for piece in stack):
            return []
        return [stack]
    words = cell.split()
    if len(words) > 1 and _rows_read_as_values([words]):
        return _run_rows([words])
    return []


def _run_rows(rows: list[list[str]]) -> list[list[str]]:
    """`rows` as the run they read as, or nothing where they read as one number."""
    return [] if all(_reads_as_a_grouped_number(row) for row in rows) else rows


def _reads_as_a_grouped_number(pieces: list[str]) -> bool:
    """True when the pieces are one number the page typeset with group spaces.

    `17 440`, `1 250 000`. Neither the row nor the table tells it from two
    integer columns run together. Price: two such columns that did lose
    their boundary are not reported.
    """
    return (
        len(pieces) > 1
        and all(piece.isdigit() for piece in pieces)
        and len(pieces[0]) <= 3
        and all(len(piece) == 3 for piece in pieces[1:])
    )


def _rows_read_as_values(rows: list[list[str]]) -> bool:
    """True when every piece of every row is a value rather than a word of prose."""
    return all(
        _CRUSHED_PIECE_RE.match(piece) is not None and _holds_a_digit(piece)
        for row in rows
        for piece in row
    )


def _run_columns(rows: list[list[str]]) -> list[str]:
    """The run's value per column, stacks joined by spaces as `cell_values` reads."""
    return [" ".join(row[index] for row in rows) for index in range(len(rows[0]))]


def _holds_a_digit(piece: str) -> bool:
    return any(char.isdigit() for char in piece)


# Multi-level only (`4.2.5`): a bare integer is an ordinary value.
_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)+\.?$")


def _contents_entry_pieces(pieces: list[str]) -> list[str]:
    """`pieces` reread as a contents entry: its number, then its title.

    A crushed title breaks at every printed line, so its pieces outnumber the
    columns. The title, trailing page included, is glued back. Witnesses: a
    multi-level section number first, a bare page last, a digit-free word
    between, and at least two pieces between. Empty otherwise.
    """
    if len(pieces) < 4 or not _SECTION_NUMBER_RE.match(pieces[0]):
        return []
    if not pieces[-1].isdigit():
        return []
    title = pieces[1:]
    if all(_holds_a_digit(piece) for piece in title):
        return []
    return [pieces[0], " ".join(title)]


# Digit runs become `9`, letter runs `A`: `100.97` and `5.33` share a form.
_SIGNATURE_RUN_RE = re.compile(r"\d+|[^\W\d_]+")

# Per column; an empty set is a column no row showed.
ColumnForms = tuple[frozenset[str], ...]


def value_signature(value: str) -> str:
    """The shape of one value, its in-cell breaks and padding flattened out.

    A column's values differ; what its rows agree on is their spelling.
    """
    flat = " ".join(CELL_BREAK_RE.sub(" ", value).split())
    return _SIGNATURE_RUN_RE.sub(
        lambda run: "9" if run.group().isdigit() else "A", flat
    )


def table_column_forms(
    rows: Iterable[str], width: int, header: str | None = None
) -> ColumnForms:
    """The forms each column of a table carries, read off the rows that show it.

    Only full-width rows with no empty cell witness. The caller leaves the
    header out; its repeats on later pages are dropped here, or a crushed
    copy would fit the title forms. All-empty means the columns are unknown.
    """
    header_key = _header_row_key(header, width) if header is not None else None
    forms: list[set[str]] = [set() for _ in range(width)]
    for row in rows:
        cells = table_cells(row)
        if len(cells) != width or not all(cell.strip() for cell in cells):
            continue
        if header_key is not None and _header_row_key(row, width) == header_key:
            continue
        for index, cell in enumerate(cells):
            forms[index].add(value_signature(cell))
    return tuple(frozenset(column) for column in forms)


def _header_row_key(row: str, width: int) -> tuple[str, ...] | None:
    """The cells of `row` as a case- and space-folded key, or None off `width`."""
    cells = table_cells(row)
    if len(cells) != width:
        return None
    return tuple(" ".join(cell.split()).casefold() for cell in cells)


def _run_column_starts(
    rows: list[list[str]], first: int, room: int, forms: ColumnForms
) -> tuple[int, ...]:
    """Every column the run can begin at with its pieces in columns of their forms.

    Each piece must match its target column's forms; otherwise the row is a
    repeated header or a units row. Every offset in the room is tried, and
    every printed row of the run takes the same offset. All placements are
    returned: a repair needs exactly one, a report any.
    """
    signatures = [[value_signature(piece) for piece in row] for row in rows]
    width = len(signatures[0])
    starts: list[int] = []
    for offset in range(room - width + 1):
        start = first + offset
        if start < 0 or start + width > len(forms):
            continue
        if all(
            signature in forms[start + step]
            for row in signatures
            for step, signature in enumerate(row)
        ):
            starts.append(start)
    return tuple(starts)


@dataclass(frozen=True)
class _CrushedRun:
    """One cell's crushed run: the columns it holds, and where they go back.

    `starts` is empty without column forms and for a contents entry.
    """

    pieces: list[str]
    starts: tuple[int, ...]


def _crushed_row_runs(
    cells: list[str], forms: ColumnForms | None = None
) -> dict[int, _CrushedRun]:
    """The run of columns every cell of this row crushed into itself.

    A run is a cell with N column values beside at least N-1 empty cells on
    either side. Read per cell, since a crush is usually partial. Values that
    outnumber the cells drop the row. A run too wide for its room may still
    read as a contents entry. With `forms`, every piece must fit its column.
    Empty `forms` mean unknown columns and read as None; otherwise the defect
    would vanish once every row of a block lost its grid.
    """
    if forms is not None and not any(forms):
        forms = None
    runs: dict[int, _CrushedRun] = {}
    if len(cells) < 2:
        return runs
    sole = sum(1 for cell in cells if cell.strip()) == 1
    for index, cell in enumerate(cells):
        rows = _crushed_cell_rows(cell, sole=sole)
        if not rows:
            continue
        pieces = _run_columns(rows)
        left = 0
        probe = index - 1
        while probe >= 0 and not cells[probe].strip():
            left += 1
            probe -= 1
        right = 0
        probe = index + 1
        while probe < len(cells) and not cells[probe].strip():
            right += 1
            probe += 1
        room = 1 + left + right
        if room < len(pieces):
            entry = _contents_entry_pieces(pieces)
            if entry and room >= len(entry):
                runs[index] = _CrushedRun(entry, ())
            continue
        starts = (
            () if forms is None else _run_column_starts(rows, index - left, room, forms)
        )
        if forms is not None and not starts:
            continue
        runs[index] = _CrushedRun(pieces, starts)
    if not runs:
        return runs
    values = sum(len(run.pieces) for run in runs.values())
    values += sum(
        1 for index, cell in enumerate(cells) if index not in runs and cell.strip()
    )
    return runs if values <= len(cells) else {}


def _crushed_row_cells(
    cells: list[str], forms: ColumnForms | None = None
) -> dict[int, list[str]]:
    """The pieces of every cell this row crushed a run of columns into."""
    return {index: run.pieces for index, run in _crushed_row_runs(cells, forms).items()}


def crushed_run_placements(
    line: str, forms: ColumnForms
) -> dict[int, tuple[int, list[str]]]:
    """Cell index -> the one place its table puts that cell's crushed run.

    Only a single admitted arrangement counts, and it must cover the run's own
    cell: merged text stays inside the columns it merged.
    """
    placements: dict[int, tuple[int, list[str]]] = {}
    for index, run in _crushed_row_runs(table_cells(line), forms).items():
        if len(run.starts) != 1:
            continue
        start = run.starts[0]
        if start <= index < start + len(run.pieces):
            placements[index] = (start, run.pieces)
    return placements


def _crushed_row_stack(
    cells: list[str], forms: ColumnForms | None = None
) -> int | None:
    """How many columns the row crushed into its cells, or None when none."""
    crushed = _crushed_row_cells(cells, forms)
    if not crushed:
        return None
    return sum(len(pieces) for pieces in crushed.values())


def cell_values(line: str) -> list[str]:
    """The non-empty values of a table row, in the order the row holds them.

    Grid is set aside: pipes, padding, empty cells, and a crushed run, whose
    columns count as separate values, so a repair that spreads the run keeps
    them. Elsewhere an in-cell break is wrapped content, joined by a space
    whether written as `<br>` or not.
    """
    cells = table_cells(line)
    crushed = _crushed_row_cells(cells)
    values: list[str] = []
    for index, cell in enumerate(cells):
        spread = crushed.get(index)
        if spread is not None:
            values.extend(spread)
            continue
        pieces = [" ".join(piece.split()) for piece in CELL_BREAK_RE.split(cell)]
        pieces = [piece for piece in pieces if piece]
        if pieces:
            values.append(" ".join(pieces))
    return values


def row_holds_a_crushed_stack(line: str, forms: ColumnForms | None = None) -> bool:
    """True when the row's values are stacked in one cell instead of spread out.

    The per-row half of `detect_collapsed_grids`, for a single rebuilt row.
    """
    return _crushed_row_stack(table_cells(line), forms) is not None


def crushed_stack_size(line: str, forms: ColumnForms | None = None) -> int | None:
    """How many columns the row crushed into one cell, or None when none.

    A repair request states it, so the model does not guess the run's reach.
    """
    return _crushed_row_stack(table_cells(line), forms)
