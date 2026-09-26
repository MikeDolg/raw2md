"""Rules that fix a GFM table's own grid.

Only mechanical repairs live here: collapse a bodyless table, lay out a
one-column contents table, reunite a table cut by a page break, fold a page
printed several columns up, drop an empty column, recut swallowed and crushed
cells, split a paragraph glued onto the header, sink a stray separator, give a
pipe block its delimiter, and lay every block out. A table too damaged to
repair stays for the reporting pass. Cell math belongs to the math rules.

`open_math_html_cells` fixes no grid: it opens an HTML table cell around a
formula, so it works on the text inside a protected zone.
"""

from __future__ import annotations

import re
from itertools import pairwise

from raw2md.cleaning.headings import contents_zones
from raw2md.cleaning.math import unescape_math_pipes
from raw2md.keywords import Keywords
from raw2md.mdtext.lines import ATX_HEADING_RE, is_table_separator
from raw2md.mdtext.math_spans import math_span_ranges
from raw2md.mdtext.pages import page_mark_number
from raw2md.mdtext.tables import (
    CELL_BREAK_RE,
    ColumnForms,
    cell_values,
    crushed_run_placements,
    has_cell_separator,
    rebuild_table_row,
    table_cells,
    table_column_forms,
    value_signature,
)
from raw2md.mdtext.zones import Segment, html_table_lines

_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")

# A section number or a page of a contents entry: arabic, roman, or per
# chapter (`5-40`). Never a title.
_ENTRY_MARK_RE = re.compile(r"(?:\d+(?:[.\-]\d+)*\.?|[ivxlcdm]+\.?)\Z", re.IGNORECASE)

# A number with optional decimals and thousands separators; tells a cell that
# swallowed its neighbour from one that holds several words.
_VALUE_TOKEN_RE = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:[.,]\d+)?")


def split_glued_table_header(seg_list: list[Segment]) -> list[Segment]:
    """Split prose text a converter glued onto a table's header line.

    The cut at the first pipe must leave exactly the separator's width, which
    proves it hit the row boundary. A body row must confirm the width too:
    `A | B` over `---` is a setext heading. Only the header line is a
    candidate.
    """
    out: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected or "|" not in line or not line.strip():
            out.append(seg_list[idx])
            idx += 1
            continue
        next_idx = idx + 1
        if next_idx >= count:
            out.append(seg_list[idx])
            idx += 1
            continue
        sep_line, sep_protected = seg_list[next_idx]
        if sep_protected or not is_table_separator(sep_line.strip()):
            out.append(seg_list[idx])
            idx += 1
            continue
        width = len(table_cells(sep_line))
        if not _a_body_row_confirms_width(seg_list, next_idx + 1, width):
            out.append(seg_list[idx])
            idx += 1
            continue
        split = _split_glued_header(line, width)
        if split is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        paragraph, header = split
        out.append((paragraph, False))
        out.append(("", False))
        out.append((header, False))
        idx += 1
    return out


def _a_body_row_confirms_width(seg_list: list[Segment], start: int, width: int) -> bool:
    """True when a row from `start` on, before the table ends, has `width` cells."""
    count = len(seg_list)
    confirmed = False
    idx = start
    while idx < count:
        line, protected = seg_list[idx]
        if protected or "|" not in line or not line.strip():
            break
        if len(table_cells(line)) == width:
            confirmed = True
        idx += 1
    return confirmed


def _split_glued_header(line: str, width: int) -> tuple[str, str] | None:
    """The `(paragraph, header)` split for `line`, or None if it does not apply.

    The line must count more cells than the separator: a one-column row can
    carry a single trailing pipe.
    """
    if len(table_cells(line)) <= width:
        return None
    m = _UNESCAPED_PIPE_RE.search(line)
    if m is None:
        return None
    pipe_pos = m.start()
    prose = line[:pipe_pos].strip()
    if not prose:
        return None
    indent = line[: len(line) - len(line.lstrip())]
    header = indent + line[pipe_pos:]
    if len(table_cells(header)) != width:
        return None
    return f"{indent}{prose}", header


# A one-column cycle reads like one title spanning every column.
_COLUMN_CYCLE_MIN_REPEATS = 2
_COLUMN_CYCLE_MIN_WIDTH = 2


def fold_repeated_column_cycle(seg_list: list[Segment]) -> list[Segment]:
    """Fold a table printed several columns of records up to one cycle's width.

    A header repeating a cycle of its titles is the whole signal; the
    narrowest cycle wins. Parts stack whole, since such a page is read down
    one column and on to the next. Guards: every row has the header's width,
    the cycle spans at least two columns, and it names columns rather than
    values. Blank rows at the tail of the fold go. The order between two
    printed pages cannot be recovered.
    """
    out: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        folded = _folded_column_cycle(seg_list, idx)
        if folded is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        rows, end = folded
        out.extend(rows)
        idx = end
    return out


def _folded_column_cycle(
    seg_list: list[Segment], idx: int
) -> tuple[list[Segment], int] | None:
    """The rows the block at `idx` folds into, and the index it ends at.

    Page marks move below the rows: a line without a pipe ends a table.
    """
    line, protected = seg_list[idx]
    if protected or "|" not in line or not line.strip():
        return None
    sep_idx = idx + 1
    if sep_idx >= len(seg_list):
        return None
    sep_line, sep_protected = seg_list[sep_idx]
    if sep_protected or not is_table_separator(sep_line.strip()):
        return None
    scanned = _cycle_block_rows(seg_list, sep_idx + 1)
    if scanned is None:
        return None
    rows, page_marks, end = scanned
    sep_cells = table_cells(sep_line)
    header_cells = table_cells(line)
    width = len(sep_cells)
    if (
        not rows
        or len(header_cells) != width
        or any(len(cells) != width for _, cells in rows)
    ):
        return None
    cycle = _column_cycle([cell.strip() for cell in header_cells])
    if cycle is None:
        return None
    folded = [
        (row_line, cells[part * cycle : (part + 1) * cycle])
        for part in range(width // cycle)
        for row_line, cells in rows
    ]
    while folded and not any(cell.strip() for cell in folded[-1][1]):
        folded.pop()
    if not folded:
        return None
    laid_out: list[Segment] = [
        (rebuild_table_row(line, header_cells[:cycle]), False),
        (rebuild_table_row(sep_line, sep_cells[:cycle]), False),
    ]
    laid_out.extend(
        (rebuild_table_row(row_line, cells), False) for row_line, cells in folded
    )
    laid_out.extend(page_marks)
    return laid_out, end


def _cycle_block_rows(
    seg_list: list[Segment], start: int
) -> tuple[list[tuple[str, list[str]]], list[Segment], int] | None:
    """The block's rows with their cells, its page marks, and where it ends.

    None on a second separator, which the bodyless collapse reads.
    """
    rows: list[tuple[str, list[str]]] = []
    marks: list[Segment] = []
    count = len(seg_list)
    idx = start
    while idx < count:
        row_line, row_protected = seg_list[idx]
        if not row_protected and page_mark_number(row_line) is not None:
            marks.append(seg_list[idx])
            idx += 1
            continue
        if row_protected or "|" not in row_line or not row_line.strip():
            break
        if is_table_separator(row_line.strip()):
            return None
        rows.append((row_line, table_cells(row_line)))
        idx += 1
    return rows, marks, idx


def _column_cycle(names: list[str]) -> int | None:
    """The width of the cycle of titles `names` repeats, or None.

    A wider cycle holds the cells the narrowest was refused for, so it is not
    tried.
    """
    period = _column_period(names)
    if period is None or period < _COLUMN_CYCLE_MIN_WIDTH:
        return None
    titles = [name for name in names[:period] if name]
    if not titles or any(_VALUE_TOKEN_RE.fullmatch(name) for name in titles):
        return None
    return period


def _column_period(names: list[str]) -> int | None:
    """The narrowest cycle `names` is whole copies of, or None when it is none."""
    width = len(names)
    for size in range(1, width // _COLUMN_CYCLE_MIN_REPEATS + 1):
        if width % size:
            continue
        if all(names[col] == names[col % size] for col in range(size, width)):
            return size
    return None


def reunite_split_tables(seg_list: list[Segment]) -> list[Segment]:
    """Glue back a table a page break cut into a table and its continuation.

    The reprinted header attests the cut: both headers match cell for cell
    over separators of one width, with only blank lines and page marks
    between, and the continuation has a row. Its header and separator go; no
    cell moves. A page mark moves below the table, since a line without a
    pipe ends a table.
    """
    out: list[Segment] = []
    pending_marks: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        line, _ = seg_list[idx]
        if not line.strip():
            out.append(seg_list[idx])
            idx += 1
            continue
        # A held mark goes above the first line of the block after the table.
        out.extend(pending_marks)
        pending_marks.clear()
        block = _table_block(seg_list, idx)
        if block is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        sep_idx, body_end = block
        out.extend(seg_list[idx:body_end])
        width = len(table_cells(seg_list[sep_idx][0]))
        header_cells = _stripped_cells(line)
        confirmed = _width_confirmed(seg_list, idx, sep_idx, body_end, width)
        idx = body_end
        while confirmed:
            joined = _split_continuation(seg_list, idx, width, header_cells)
            if joined is None:
                break
            body_start, idx, marks = joined
            out.extend(seg_list[body_start:idx])
            pending_marks.extend(marks)
    out.extend(pending_marks)
    return out


def _table_block(seg_list: list[Segment], idx: int) -> tuple[int, int] | None:
    """`(separator index, body end)` of the table opening at `idx`, or None."""
    count = len(seg_list)
    line, protected = seg_list[idx]
    if protected or "|" not in line or not line.strip():
        return None
    sep_idx = idx + 1
    if sep_idx >= count:
        return None
    sep_line, sep_protected = seg_list[sep_idx]
    if sep_protected or not is_table_separator(sep_line.strip()):
        return None
    body_end = sep_idx + 1
    while body_end < count:
        body_line, body_protected = seg_list[body_end]
        if body_protected or "|" not in body_line or not body_line.strip():
            break
        body_end += 1
    return sep_idx, body_end


def _width_confirmed(
    seg_list: list[Segment], header: int, sep_idx: int, body_end: int, width: int
) -> bool:
    """True when a row of the block carries the separator's own cell count.

    A pipe line over a bare underline is a setext heading.
    """
    return any(
        len(table_cells(seg_list[row][0])) == width
        for row in range(header, body_end)
        if row != sep_idx
    )


def _stripped_cells(line: str) -> list[str]:
    """The row's cell texts without padding, which differs between reprints."""
    return [cell.strip() for cell in table_cells(line)]


def _split_continuation(
    seg_list: list[Segment], start: int, width: int, header_cells: list[str]
) -> tuple[int, int, list[Segment]] | None:
    """`(body start, body end, page marks in the cut)` of the continuation, or None."""
    marks: list[Segment] = []
    count = len(seg_list)
    idx = start
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            return None
        if not line.strip():
            idx += 1
            continue
        if page_mark_number(line) is None:
            break
        marks.append(seg_list[idx])
        idx += 1
    if idx >= count:
        return None
    block = _table_block(seg_list, idx)
    if block is None:
        return None
    sep_idx, body_end = block
    if len(table_cells(seg_list[sep_idx][0])) != width:
        return None
    if _stripped_cells(seg_list[idx][0]) != header_cells:
        return None
    if body_end == sep_idx + 1:
        return None
    return sep_idx + 1, body_end, marks


# Number, title, page. The title's leading letter tells an entry from a
# range of dimensions (`12.0 - 455.0`).
_CONTENTS_ENTRY_RE = re.compile(r"^\d+(?:\.\d+)*\s+[^\W\d_].*\d\s*$")

# A dotted number marks a real contents hierarchy.
_DOTTED_NUMBER_RE = re.compile(r"\d+\.\d+")

# Two characters at least, so the dot closing a section number stays.
_CONTENTS_LEADER_RUN_RE = re.compile(r"(?:[.·…_][ \t]*){2,}")

# Three lines hold an enumeration; one or two are a coincidence.
_CONTENTS_ENTRY_SHARE = 0.6
_CONTENTS_MIN_LINES = 3


def decompose_contents_table(seg_list: list[Segment]) -> list[Segment]:
    """Lay a one-column table that is really the document's contents back out.

    One column is no grid. Each cell becomes lines, split at `<br>`, with dot
    leaders squeezed. The first line and `_CONTENTS_ENTRY_SHARE` of all lines
    must be contents entries, at least one with a dotted number; a column of
    plain phrases stays.
    """
    out: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        block = _one_column_table(seg_list, idx)
        if block is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        body_end, row_indices = block
        lines = _contents_lines(seg_list, [idx, *row_indices])
        if lines is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        out.extend((text, False) for text in lines)
        idx = body_end
    return out


def _one_column_table(
    seg_list: list[Segment], idx: int
) -> tuple[int, list[int]] | None:
    """`(block end, data-row indices)` of a one-column table opening at `idx`."""
    line, protected = seg_list[idx]
    if protected or "|" not in line or not line.strip():
        return None
    sep_idx = idx + 1
    if sep_idx >= len(seg_list):
        return None
    sep_line, sep_protected = seg_list[sep_idx]
    if (
        sep_protected
        or not is_table_separator(sep_line.strip())
        or len(table_cells(sep_line)) != 1
    ):
        return None
    rows: list[int] = []
    cur = sep_idx + 1
    while cur < len(seg_list):
        row_line, row_protected = seg_list[cur]
        if row_protected or "|" not in row_line or not row_line.strip():
            break
        if not is_table_separator(row_line.strip()):
            rows.append(cur)
        cur += 1
    return cur, rows


def _contents_lines(seg_list: list[Segment], indices: list[int]) -> list[str] | None:
    """The lines to lay a one-column block out as, or None where it is not contents."""
    pieces: list[str] = []
    for i in indices:
        cells = table_cells(seg_list[i][0])
        if len(cells) != 1:
            return None
        for piece in CELL_BREAK_RE.split(cells[0]):
            text = " ".join(_CONTENTS_LEADER_RUN_RE.sub(" ", piece).split())
            if text:
                pieces.append(text)
    if len(pieces) < _CONTENTS_MIN_LINES or not _CONTENTS_ENTRY_RE.match(pieces[0]):
        return None
    entries = [piece for piece in pieces if _CONTENTS_ENTRY_RE.match(piece)]
    if len(entries) < _CONTENTS_ENTRY_SHARE * len(pieces):
        return None
    if not any(_DOTTED_NUMBER_RE.search(entry) for entry in entries):
        return None
    return pieces


def join_contents_entry_breaks(
    seg_list: list[Segment], keywords: Keywords
) -> list[Segment]:
    """Read a printed contents entry through the in-cell breaks it wraps at.

    A narrow contents column gets a `<br>` per printed line. Inside a contents
    zone a cell is one entry, so each break becomes a space. The zone is the
    whole guard: elsewhere a break may divide stacked values. The zone is the
    strict one, closing at the first heading past the contents. A row whose
    cell stacks several whole entries (`_stacks_entries`) stays.
    """
    zones = contents_zones(seg_list, keywords)
    if not zones:
        return seg_list
    out = list(seg_list)
    for start, end in zones:
        for idx in _zone_table_rows(out, start, end):
            line, protected = out[idx]
            cells = table_cells(line)
            if not any(CELL_BREAK_RE.search(cell) for cell in cells):
                continue
            if _stacks_entries(cells):
                continue
            out[idx] = (
                rebuild_table_row(line, [_join_cell_breaks(cell) for cell in cells]),
                protected,
            )
    return out


def _zone_table_rows(seg_list: list[Segment], start: int, end: int) -> list[int]:
    """Data-row indices of every pipe table with a separator in `[start, end)`.

    Separator rows and heading rows are left out.
    """
    rows: list[int] = []
    idx = start
    while idx < end:
        line, protected = seg_list[idx]
        if protected or "|" not in line or not line.strip():
            idx += 1
            continue
        block_start = idx
        while (
            idx < end
            and not seg_list[idx][1]
            and "|" in seg_list[idx][0]
            and seg_list[idx][0].strip()
        ):
            idx += 1
        block = range(block_start, idx)
        if any(is_table_separator(seg_list[i][0].strip()) for i in block):
            rows.extend(
                i
                for i in block
                if not is_table_separator(seg_list[i][0].strip())
                and ATX_HEADING_RE.match(seg_list[i][0]) is None
            )
    return rows


def _stacks_entries(cells: list[str]) -> bool:
    """True when a cell breaks into entry marks only, one entry per mark.

    A wrapped title breaks into words instead.
    """
    for cell in cells:
        pieces = [piece.strip() for piece in CELL_BREAK_RE.split(cell) if piece.strip()]
        if len(pieces) > 1 and all(_ENTRY_MARK_RE.match(piece) for piece in pieces):
            return True
    return False


def _join_cell_breaks(cell: str) -> str:
    """`cell` with every in-cell break turned to a space, its own padding kept."""
    if not CELL_BREAK_RE.search(cell):
        return cell
    lead = cell[: len(cell) - len(cell.lstrip())]
    trail = cell[len(cell.rstrip()) :]
    return f"{lead}{' '.join(CELL_BREAK_RE.sub(' ', cell).split())}{trail}"


# A record's leading number (`7`, `6.1.3`, `II.`); a wrapped title tail has
# none.
_ENTRY_NUMBER_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+)\.?(?:\s|\Z)", re.IGNORECASE
)


def join_wrapped_contents_entries(
    seg_list: list[Segment], keywords: Keywords
) -> list[Segment]:
    """Join a contents entry the converter wrapped onto a second table row.

    The wrapped row has no number and opens deeper than any record, so the
    outline reading would drop the whole table. The top row ends without a
    page; the tail row ends on one, opens further right, has no number, and
    shares exactly the title column with the top. The rows merge column by
    column. Only inside the strict contents zone.
    """
    zones = contents_zones(seg_list, keywords)
    if not zones:
        return seg_list
    out = list(seg_list)
    joined: set[int] = set()
    for start, end in zones:
        for top, tail in pairwise(_zone_table_rows(out, start, end)):
            # Adjacent rows of one table; two tables are two printed pages.
            if tail != top + 1 or top in joined:
                continue
            top_cells = [cell.strip() for cell in table_cells(out[top][0])]
            tail_cells = [cell.strip() for cell in table_cells(out[tail][0])]
            if not _wraps_the_entry_above(top_cells, tail_cells):
                continue
            line, protected = out[top]
            out[top] = (
                rebuild_table_row(line, _joined_entry(top_cells, tail_cells)),
                protected,
            )
            joined.add(tail)
    if not joined:
        return seg_list
    return [segment for idx, segment in enumerate(out) if idx not in joined]


def _wraps_the_entry_above(top: list[str], tail: list[str]) -> bool:
    """True when `tail` is the second printed line of the entry `top` opens."""
    if len(top) != len(tail) or len(top) < 2:
        return False
    top_filled = [col for col, text in enumerate(top) if text]
    tail_filled = [col for col, text in enumerate(tail) if text]
    if not top_filled or not tail_filled:
        return False
    if tail_filled[0] <= top_filled[0]:
        return False
    if _ends_on_an_entry_mark(top) or not _ends_on_an_entry_mark(tail):
        return False
    if _ENTRY_NUMBER_RE.match(tail[tail_filled[0]]):
        return False
    return set(top_filled) & set(tail_filled) == {tail_filled[0]}


def _ends_on_an_entry_mark(cells: list[str]) -> bool:
    """True when the row's last filled cell is the page an entry points at."""
    filled = [text for text in cells if text]
    return bool(filled) and _ENTRY_MARK_RE.match(filled[-1]) is not None


def _joined_entry(top: list[str], tail: list[str]) -> list[str]:
    """The one row the two lines of a wrapped entry state together."""
    return [
        f" {above} {below} " if above and below else f" {above or below} "
        for above, below in zip(top, tail, strict=True)
    ]


# Fewer rows agree by chance; a table crushed into one cell runs to dozens.
_PERIODIC_STACK_MIN_ROWS = 4


def recut_periodic_stack(seg_list: list[Segment]) -> list[Segment]:
    """Lay a table crushed whole into one header cell back out into its rows.

    The period is the header's width, not searched for: cut at it, every
    column must carry one value form (`value_signature`). A remainder takes
    the tail of the first row, where a units row leaves the name cell empty;
    if the tail alignment agrees too, the recut is refused. Only a table with
    no data row and exactly one stacked cell beside named titles.
    """
    out: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        recut = _recut_crushed_table(seg_list, idx)
        if recut is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        rows, end = recut
        out.extend(rows)
        idx = end
    return out


def _recut_crushed_table(
    seg_list: list[Segment], idx: int
) -> tuple[list[Segment], int] | None:
    """The rows a table crushed into one cell at `idx` lays out into, and its end.

    Page marks inside the table move below the rows.
    """
    line, protected = seg_list[idx]
    if protected or "|" not in line or not line.strip():
        return None
    sep_idx = idx + 1
    if sep_idx >= len(seg_list):
        return None
    sep_line, sep_protected = seg_list[sep_idx]
    if sep_protected or not is_table_separator(sep_line.strip()):
        return None
    header_cells = table_cells(line)
    if len(header_cells) != len(table_cells(sep_line)):
        return None
    stacked = [
        col for col, cell in enumerate(header_cells) if CELL_BREAK_RE.search(cell)
    ]
    if len(stacked) != 1:
        return None
    stack_col = stacked[0]
    titles = [cell for col, cell in enumerate(header_cells) if col != stack_col]
    if len(titles) < 2 or not all(title.strip() for title in titles):
        return None
    tail = _bodyless_table_tail(seg_list, sep_idx + 1)
    if tail is None:
        return None
    end, page_marks = tail
    rows = _periodic_stack_rows(header_cells[stack_col], len(titles))
    if rows is None:
        return None
    laid_out: list[Segment] = [
        (rebuild_table_row(line, titles), False),
        (_drop_table_cell(sep_line, stack_col), False),
    ]
    laid_out.extend(
        (rebuild_table_row(line, [f" {value} " for value in row]), False)
        for row in rows
    )
    laid_out.extend(page_marks)
    return laid_out, end


def _bodyless_table_tail(
    seg_list: list[Segment], start: int
) -> tuple[int, list[Segment]] | None:
    """Where a table with no data row ends, and its page marks; None on a data row.

    Repeated separators go with the grid.
    """
    count = len(seg_list)
    page_marks: list[Segment] = []
    idx = start
    while idx < count:
        row_line, row_protected = seg_list[idx]
        if not row_protected and page_mark_number(row_line) is not None:
            page_marks.append(seg_list[idx])
            idx += 1
            continue
        if row_protected or "|" not in row_line or not row_line.strip():
            break
        if not is_table_separator(row_line.strip()):
            return None
        idx += 1
    return idx, page_marks


def _periodic_stack_rows(cell: str, width: int) -> list[list[str]] | None:
    """The `width`-wide rows a crushed stack lays out into, or None."""
    pieces = [piece.strip() for piece in CELL_BREAK_RE.split(cell)]
    lead = len(pieces) % width
    body = pieces[lead:]
    if len(body) < width * _PERIODIC_STACK_MIN_ROWS:
        return None
    if not _stack_columns_agree(body, width):
        return None
    if lead and _stack_columns_agree(pieces[: len(pieces) - lead], width):
        # Both alignments agree, and nothing says which one the page printed.
        return None
    rows = [[""] * (width - lead) + pieces[:lead]] if lead else []
    rows.extend(body[start : start + width] for start in range(0, len(body), width))
    return rows


def _stack_columns_agree(body: list[str], width: int) -> bool:
    """True when every position of `body` holds one value signature at `width`."""
    forms: list[set[str]] = [set() for _ in range(width)]
    for offset, piece in enumerate(body):
        forms[offset % width].add(value_signature(piece))
    return all(len(column) == 1 for column in forms)


def drop_bodyless_table(seg_list: list[Segment]) -> list[Segment]:
    """Collapse a table whose separator opens onto no data row into its header text.

    With no row, the header is a mis-split line and the values sit below as
    prose. The header's cell count must match the separator's, or it may be
    a setext heading. A header of blank cells stays for the missing-header
    finding. Page marks are stepped over. Pipe escapes in math are undone:
    off the row, `\\|` is a norm operator.
    """
    out: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected or "|" not in line or not line.strip():
            out.append(seg_list[idx])
            idx += 1
            continue
        sep_idx = idx + 1
        if sep_idx >= count:
            out.append(seg_list[idx])
            idx += 1
            continue
        sep_line, sep_protected = seg_list[sep_idx]
        if sep_protected or not is_table_separator(sep_line.strip()):
            out.append(seg_list[idx])
            idx += 1
            continue
        header_cells = table_cells(line)
        if len(header_cells) != len(table_cells(sep_line)):
            out.append(seg_list[idx])
            idx += 1
            continue
        prose = " ".join(cell.strip() for cell in header_cells if cell.strip())
        if not prose:
            out.append(seg_list[idx])
            idx += 1
            continue
        row_idx = sep_idx + 1
        skipped: list[Segment] = []
        has_data = False
        while row_idx < count:
            row_line, row_protected = seg_list[row_idx]
            if not row_protected and page_mark_number(row_line) is not None:
                skipped.append(seg_list[row_idx])
                row_idx += 1
                continue
            if row_protected or "|" not in row_line or not row_line.strip():
                break
            if not is_table_separator(row_line.strip()):
                has_data = True
                break
            row_idx += 1
        if has_data:
            out.append(seg_list[idx])
            idx += 1
            continue
        indent = line[: len(line) - len(line.lstrip())]
        out.append((f"{indent}{unescape_math_pipes(prose)}", False))
        out.extend(skipped)
        idx = row_idx
    return out


def drop_empty_table_columns(seg_list: list[Segment]) -> list[Segment]:
    """Remove a table column empty in the header and in every body row.

    Only a table whose every row has the header's width: off it, a column
    index means nothing.
    """
    result = list(seg_list)
    count = len(result)
    idx = 0
    while idx < count:
        line, protected = result[idx]
        if protected or "|" not in line or not line.strip():
            idx += 1
            continue
        sep_idx = idx + 1
        if sep_idx >= count:
            idx += 1
            continue
        sep_line, sep_protected = result[sep_idx]
        if sep_protected or not is_table_separator(sep_line.strip()):
            idx += 1
            continue
        header_cells = table_cells(line)
        width = len(header_cells)
        well_formed = len(table_cells(sep_line)) == width
        body_rows: list[list[str]] = []
        body_end = sep_idx + 1
        while body_end < count:
            body_line, body_protected = result[body_end]
            if body_protected or "|" not in body_line or not body_line.strip():
                break
            cells = table_cells(body_line)
            if len(cells) != width:
                well_formed = False
            body_rows.append(cells)
            body_end += 1
        if well_formed:
            empty_cols = [
                col
                for col in range(width)
                if not header_cells[col].strip()
                and all(not row[col].strip() for row in body_rows)
            ]
            if 0 < len(empty_cols) < width:
                for col in reversed(empty_cols):
                    for row_idx in range(idx, body_end):
                        row_line, row_protected = result[row_idx]
                        result[row_idx] = (
                            _drop_table_cell(row_line, col),
                            row_protected,
                        )
        idx = body_end
    return result


def _drop_table_cell(line: str, col: int) -> str:
    """Remove the `col`-th GFM cell from a table row, keeping its indent and pipes."""
    cells = table_cells(line)
    del cells[col]
    return rebuild_table_row(line, cells)


def recut_swallowed_cells(seg_list: list[Segment]) -> list[Segment]:
    """Cut a cell holding several values back over the empty cells beside it.

    `| 1,000.0 1,027.3 |    |` keeps the row width, so no finding reports it.
    The blank span must be exactly one short of the value count; any other
    count leaves a choice. Every row has one width, and a target column holds
    a value somewhere or is blank under a named header. Body rows only.
    """
    result = list(seg_list)
    count = len(result)
    idx = 0
    while idx < count:
        line, protected = result[idx]
        if protected or "|" not in line or not line.strip():
            idx += 1
            continue
        sep_idx = idx + 1
        if sep_idx >= count:
            idx += 1
            continue
        sep_line, sep_protected = result[sep_idx]
        if sep_protected or not is_table_separator(sep_line.strip()):
            idx += 1
            continue
        header_cells = table_cells(line)
        width = len(table_cells(sep_line))
        body_rows: list[tuple[int, list[str]]] = []
        body_end = sep_idx + 1
        while body_end < count:
            body_line, body_protected = result[body_end]
            if body_protected or "|" not in body_line or not body_line.strip():
                break
            body_rows.append((body_end, table_cells(body_line)))
            body_end += 1
        if len(header_cells) == width and all(
            len(cells) == width for _, cells in body_rows
        ):
            attested = _value_columns(header_cells, [cells for _, cells in body_rows])
            for row_idx, cells in body_rows:
                recut = _recut_row(cells, attested)
                if recut is not None:
                    row_line, row_protected = result[row_idx]
                    result[row_idx] = (
                        rebuild_table_row(row_line, recut),
                        row_protected,
                    )
        idx = body_end
    return result


def _value_columns(header_cells: list[str], rows: list[list[str]]) -> list[bool]:
    """Per column: whether values may land in it, read off the table as found."""
    return [
        any(_VALUE_TOKEN_RE.fullmatch(row[col].strip()) for row in rows)
        or (
            bool(header_cells[col].strip())
            and all(not row[col].strip() for row in rows)
        )
        for col in range(len(header_cells))
    ]


def _recut_row(cells: list[str], attested: list[bool]) -> list[str] | None:
    """The row's cells with every swallowed run spread out, or None if none is.

    A recut can settle the next run's arithmetic, so rounds repeat; each fills
    a blank cell, which bounds them by the row width.
    """
    recut = list(cells)
    changed = False
    while True:
        round_cells = _recut_round(recut, attested)
        if round_cells is None:
            return recut if changed else None
        recut = round_cells
        changed = True


def _recut_round(cells: list[str], attested: list[bool]) -> list[str] | None:
    """One round of the recut: every run the row places without a choice."""
    runs = [
        (col, _blank_span(cells, col), values)
        for col, values in (
            (col, _swallowed_values(cell)) for col, cell in enumerate(cells)
        )
        if values is not None
    ]
    placeable = [
        (col, span, values)
        for col, span, values in runs
        if span[1] - span[0] + 1 == len(values)
    ]
    recut = list(cells)
    changed = False
    for col, (start, end), values in placeable:
        # Two runs reaching for one blank cell are both left: the row does not
        # say which the source printed.
        if any(
            other != col and start <= other_end and other_start <= end
            for other, (other_start, other_end), _ in placeable
        ):
            continue
        if not all(
            attested[target] for target in range(start, end + 1) if target != col
        ):
            continue
        for offset, value in enumerate(values):
            recut[start + offset] = f" {value} "
        changed = True
    return recut if changed else None


def _swallowed_values(cell: str) -> list[str] | None:
    """The cell's values when its whole text is a run of them, else None."""
    values = cell.split()
    if len(values) < 2 or not all(_VALUE_TOKEN_RE.fullmatch(v) for v in values):
        return None
    return values


def _blank_span(cells: list[str], col: int) -> tuple[int, int]:
    """The widest run of cells around `col` whose every other cell is blank."""
    start = col
    while start > 0 and not cells[start - 1].strip():
        start -= 1
    end = col
    while end + 1 < len(cells) and not cells[end + 1].strip():
        end += 1
    return start, end


def spread_crushed_runs(seg_list: list[Segment]) -> list[Segment]:
    """Lay a crushed run back over the columns the table's own forms name for it.

    Where the row leaves a choice of blank cells, the column forms
    (`table_column_forms`) must admit exactly one arrangement; two leave the
    row for a stage with the page. The row's values must be unchanged
    (`cell_values`). A cell with an in-cell break stays: which printed line a
    value stood on is the page's to say. Body rows of full width only.
    """
    result = list(seg_list)
    count = len(result)
    idx = 0
    while idx < count:
        line, protected = result[idx]
        if protected or "|" not in line or not line.strip():
            idx += 1
            continue
        sep_idx = idx + 1
        if sep_idx >= count:
            idx += 1
            continue
        sep_line, sep_protected = result[sep_idx]
        if sep_protected or not is_table_separator(sep_line.strip()):
            idx += 1
            continue
        width = len(table_cells(sep_line))
        body_rows: list[int] = []
        body_end = sep_idx + 1
        while body_end < count:
            body_line, body_protected = result[body_end]
            if body_protected or "|" not in body_line or not body_line.strip():
                break
            body_rows.append(body_end)
            body_end += 1
        if len(table_cells(line)) == width:
            forms = table_column_forms(
                (result[row][0] for row in body_rows), width, line
            )
            for row in body_rows:
                row_line, row_protected = result[row]
                spread = _spread_crushed_row(row_line, width, forms)
                if spread is not None:
                    result[row] = (spread, row_protected)
        idx = body_end
    return result


def _spread_crushed_row(line: str, width: int, forms: ColumnForms) -> str | None:
    """The row with every placed run laid out, or None; overlapping runs refuse."""
    cells = table_cells(line)
    if len(cells) != width:
        return None
    placements = [
        (index, start, values)
        for index, (start, values) in crushed_run_placements(line, forms).items()
        if not CELL_BREAK_RE.search(cells[index])
    ]
    if not placements:
        return None
    spread = list(cells)
    for index, start, values in placements:
        span = range(start, start + len(values))
        if any(column != index and spread[column].strip() for column in span):
            return None
        for column, value in zip(span, values, strict=True):
            spread[column] = f" {value} "
    rebuilt = rebuild_table_row(line, spread)
    return rebuilt if cell_values(rebuilt) == cell_values(line) else None


def keep_table_delimiter_under_header(seg_list: list[Segment]) -> list[Segment]:
    """Sink a table separator a dropped header row left as a block's first line.

    A postcondition, since several passes drop a junk header row. The first
    row below of the separator's width becomes the header; page marks ride
    above it. Guards: the separator has a pipe of its own, unlike a setext
    underline, and a row of its width exists below it.
    """
    out: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        sunk = _sunk_leading_separator(seg_list, idx)
        if sunk is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        rows, end = sunk
        out.extend(rows)
        idx = end
    return out


def _sunk_leading_separator(
    seg_list: list[Segment], idx: int
) -> tuple[list[Segment], int] | None:
    """The lines the block at `idx` becomes once its separator sinks, and its end."""
    line, protected = seg_list[idx]
    core = line.strip()
    if protected or not is_table_separator(core) or not has_cell_separator(line):
        return None
    if not _separator_opens_block(seg_list, idx):
        return None
    row_idx = _first_row_below(seg_list, idx + 1, len(table_cells(line)))
    if row_idx is None:
        return None
    laid_out = list(seg_list[idx + 1 : row_idx + 1])
    laid_out.append(seg_list[idx])
    return laid_out, row_idx + 1


def _separator_opens_block(seg_list: list[Segment], idx: int) -> bool:
    """True when nothing above `idx` reads as a table row, page marks aside."""
    cur = idx - 1
    while cur >= 0:
        line, protected = seg_list[cur]
        if not protected and page_mark_number(line) is not None:
            cur -= 1
            continue
        return protected or "|" not in line or not line.strip()
    return True


def _first_row_below(seg_list: list[Segment], start: int, width: int) -> int | None:
    """Index of the first table row at `start` on, if it has `width` cells.

    Page marks are stepped over; any other line ends the search with None.
    """
    count = len(seg_list)
    idx = start
    while idx < count:
        line, protected = seg_list[idx]
        if not protected and page_mark_number(line) is not None:
            idx += 1
            continue
        core = line.strip()
        if protected or "|" not in line or not core or is_table_separator(core):
            return None
        return idx if len(table_cells(line)) == width else None
    return None


# One row agrees with itself and one column repeats trivially.
_DELIMITERLESS_MIN_ROWS = 2
_DELIMITERLESS_MIN_WIDTH = 2


def mend_pipe_block_missing_delimiter(seg_list: list[Segment]) -> list[Segment]:
    """Repair a block of pipe rows that reaches this point with no delimiter row.

    No renderer reads such a block as a table. The equal cell count down the
    block is the only evidence, so it needs `_DELIMITERLESS_MIN_ROWS` rows and
    `_DELIMITERLESS_MIN_WIDTH` columns. Where the table above declares this
    width, the block joins it, and page marks move below. Otherwise the first
    row becomes the header over a plain delimiter. A cell edge inside math
    refuses the block.
    """
    out: list[Segment] = []
    count = len(seg_list)
    idx = 0
    while idx < count:
        table_end = _pass_through_table_end(seg_list, idx)
        if table_end is not None:
            out.extend(seg_list[idx:table_end])
            idx = table_end
            continue
        block = _delimiterless_block(seg_list, idx)
        if block is None:
            out.append(seg_list[idx])
            idx += 1
            continue
        end, rows, marks = block
        width = len(table_cells(seg_list[rows[0]][0]))
        if _trailing_table_width(out) == width:
            gap_marks = _pop_trailing_gap(out)
            out.extend(seg_list[row] for row in rows)
            out.extend(gap_marks)
        else:
            header_line = seg_list[rows[0]][0]
            out.append(seg_list[rows[0]])
            out.append((rebuild_table_row(header_line, ["---"] * width), False))
            out.extend(seg_list[row] for row in rows[1:])
        out.extend(marks)
        idx = end
    return out


def _pass_through_table_end(seg_list: list[Segment], idx: int) -> int | None:
    """End index of the well-formed table opening at `idx`, or None otherwise.

    Such a table passes through whole: its body rows read alone would look
    like an orphan block.
    """
    grid = _table_grid(seg_list, idx)
    if grid is None:
        return None
    _, rows = grid
    return rows[-1] + 1


def _delimiterless_block(
    seg_list: list[Segment], idx: int
) -> tuple[int, list[int], list[Segment]] | None:
    """`(block end, row indices, page marks)` of a delimiter-less block at `idx`.

    `idx` must open the block, and a delimiter row inside it refuses the
    block. A pipe inside inline code divides no cell: prose quoting a shell
    pipeline on two lines would otherwise become a table.
    """
    if not _separator_opens_block(seg_list, idx):
        return None
    line, protected = seg_list[idx]
    core = line.strip()
    if (
        protected
        or not has_cell_separator(line)
        or not core
        or is_table_separator(core)
    ):
        return None
    rows = [idx]
    marks: list[Segment] = []
    cur = idx + 1
    count = len(seg_list)
    while cur < count:
        row_line, row_protected = seg_list[cur]
        if not row_protected and page_mark_number(row_line) is not None:
            marks.append(seg_list[cur])
            cur += 1
            continue
        if row_protected or not has_cell_separator(row_line) or not row_line.strip():
            break
        if is_table_separator(row_line.strip()):
            return None
        rows.append(cur)
        cur += 1
    if len(rows) < _DELIMITERLESS_MIN_ROWS:
        return None
    width = len(table_cells(seg_list[rows[0]][0]))
    if width < _DELIMITERLESS_MIN_WIDTH or any(
        len(table_cells(seg_list[row][0])) != width for row in rows[1:]
    ):
        return None
    if any(_cell_edge_inside_math(seg_list[row][0]) for row in rows):
        return None
    return cur, rows, marks


def _trailing_table_width(out: list[Segment]) -> int | None:
    """Column width of the table `out` ends on, past blanks and page marks."""
    idx = len(out) - 1
    while idx >= 0:
        line, protected = out[idx]
        if not protected and (not line.strip() or page_mark_number(line) is not None):
            idx -= 1
            continue
        break
    if idx < 0:
        return None
    line, protected = out[idx]
    if protected or "|" not in line or is_table_separator(line.strip()):
        return None
    width = len(table_cells(line))
    while idx >= 0:
        line, protected = out[idx]
        core = line.strip()
        if protected or "|" not in line or not core:
            return None
        if is_table_separator(core):
            matches = has_cell_separator(line) and len(table_cells(line)) == width
            return width if matches else None
        if len(table_cells(line)) != width:
            return None
        idx -= 1
    return None


def _pop_trailing_gap(out: list[Segment]) -> list[Segment]:
    """Pop the blank lines and page marks `out` ends on; return the marks."""
    marks: list[Segment] = []
    while (
        out
        and not out[-1][1]
        and (not out[-1][0].strip() or page_mark_number(out[-1][0]) is not None)
    ):
        line, protected = out.pop()
        if line.strip():
            marks.append((line, protected))
    marks.reverse()
    return marks


# Aligned cells read better while a row fits a screen; past it the padding
# is scrolled through and billed by the character.
_TABLE_WIDTH_CEILING = 120

# A delimiter cell needs one dash beside its colons.
_MIN_COLUMN_WIDTH = 1

# `---`, or `:-:` with colons.
_COMPACT_DELIMITER_WIDTH = 3


def lay_out_table_blocks(seg_list: list[Segment]) -> list[Segment]:
    """Write every table block out in the layout its own width asks for.

    Converter padding is billed: the chunk planner sizes a request by text
    length. A block stays aligned while its widest row fits
    `_TABLE_WIDTH_CEILING`, and is written compact past it. Cell text and
    alignment colons are kept. Only a well-formed grid (`_table_grid`); a cell
    edge inside math refuses the block.
    """
    result = list(seg_list)
    count = len(result)
    idx = 0
    while idx < count:
        line, protected = result[idx]
        if protected or "|" not in line or not line.strip():
            idx += 1
            continue
        # A refused block is refused whole, not re-read from its second half.
        end = _block_end(result, idx)
        grid = _table_grid(result, idx)
        if grid is not None:
            sep_idx, rows = grid
            for row_idx, written in _block_layout(result, sep_idx, rows) or []:
                result[row_idx] = (written, False)
        idx = end
    return result


def _block_end(seg_list: list[Segment], idx: int) -> int:
    """Where the run of table rows opening at `idx` ends, page marks stepped over."""
    cur = idx
    count = len(seg_list)
    while cur < count:
        cur = _past_page_marks(seg_list, cur)
        if cur >= count:
            break
        line, protected = seg_list[cur]
        if protected or "|" not in line or not line.strip():
            break
        cur += 1
    return cur


def _table_grid(seg_list: list[Segment], idx: int) -> tuple[int, list[int]] | None:
    """`(delimiter index, row indices)` of the well-formed grid at `idx`, or None.

    Header, one delimiter row with a pipe of its own, at least one body row,
    every row of one width. Page marks are stepped over.
    """
    line, protected = seg_list[idx]
    core = line.strip()
    if protected or "|" not in line or not core or is_table_separator(core):
        return None
    sep_idx = _past_page_marks(seg_list, idx + 1)
    if sep_idx >= len(seg_list):
        return None
    sep_line, sep_protected = seg_list[sep_idx]
    if sep_protected or not is_table_separator(sep_line.strip()):
        return None
    if not has_cell_separator(sep_line):
        return None
    rows = [idx]
    cur = sep_idx + 1
    count = len(seg_list)
    while cur < count:
        cur = _past_page_marks(seg_list, cur)
        if cur >= count:
            break
        row_line, row_protected = seg_list[cur]
        if row_protected or "|" not in row_line or not row_line.strip():
            break
        if is_table_separator(row_line.strip()):
            return None
        rows.append(cur)
        cur += 1
    width = len(table_cells(sep_line))
    if len(rows) < 2 or any(
        len(table_cells(seg_list[row][0])) != width for row in rows
    ):
        return None
    return sep_idx, rows


def _past_page_marks(seg_list: list[Segment], start: int) -> int:
    """The first index from `start` on that is not a page mark."""
    idx = start
    while idx < len(seg_list):
        line, protected = seg_list[idx]
        if protected or page_mark_number(line) is None:
            return idx
        idx += 1
    return idx


def _block_layout(
    seg_list: list[Segment], sep_idx: int, rows: list[int]
) -> list[tuple[int, str]] | None:
    """The lines the block is written out as, by index; borders stay as found."""
    sep_line = seg_list[sep_idx][0]
    lines = [sep_line, *(seg_list[row][0] for row in rows)]
    if any(_cell_edge_inside_math(line) for line in lines):
        return None
    texts = [[cell.strip() for cell in table_cells(seg_list[row][0])] for row in rows]
    alignments = _column_alignments(sep_line)
    widths = [
        max(_MIN_COLUMN_WIDTH, *(len(row[col]) for row in texts))
        for col in range(len(alignments))
    ]
    padded = _written_out(seg_list, sep_idx, rows, texts, alignments, widths)
    if max(len(line) for _, line in padded) <= _TABLE_WIDTH_CEILING:
        return padded
    return _written_out(seg_list, sep_idx, rows, texts, alignments, None)


def _written_out(
    seg_list: list[Segment],
    sep_idx: int,
    rows: list[int],
    texts: list[list[str]],
    alignments: list[tuple[bool, bool]],
    widths: list[int] | None,
) -> list[tuple[int, str]]:
    """The block's lines in one layout: aligned to `widths`, or compact without."""
    sep_line = seg_list[sep_idx][0]
    dashes = [
        _delimiter_cell(alignment, len(head) + _column_width(widths, col) + len(tail))
        for col, (alignment, (head, tail)) in enumerate(
            zip(alignments, _edge_pads(sep_line, len(alignments)), strict=True)
        )
    ]
    written = [(sep_idx, rebuild_table_row(sep_line, dashes))]
    for row, cells in zip(rows, texts, strict=True):
        line = seg_list[row][0]
        laid_out: list[str] = []
        for col, ((head, tail), text) in enumerate(
            zip(_edge_pads(line, len(cells)), cells, strict=True)
        ):
            # With no border pipe, padding would only add trailing whitespace.
            open_end = col == len(cells) - 1 and not tail
            body = text if open_end else text.ljust(_column_width(widths, col))
            laid_out.append(f"{head}{body}{tail}")
        written.append((row, rebuild_table_row(line, laid_out)))
    return written


def _column_width(widths: list[int] | None, col: int) -> int:
    """How wide the column is written: its own width, or the floor when compact."""
    return _MIN_COLUMN_WIDTH if widths is None else widths[col]


def _edge_pads(line: str, columns: int) -> list[tuple[str, str]]:
    """The space pair each column of `line` is written with; none at an open edge."""
    stripped = line.strip()
    lead = " " if stripped.startswith("|") else ""
    trail = " " if _ends_on_a_border(stripped) else ""
    return [
        (lead if col == 0 else " ", trail if col == columns - 1 else " ")
        for col in range(columns)
    ]


def _ends_on_a_border(stripped: str) -> bool:
    """True when the pipe `stripped` ends on is the border, not an escaped pipe.

    Padding before an escaped pipe would unescape it and add a column.
    """
    if not stripped.endswith("|"):
        return False
    escapes = len(stripped[:-1]) - len(stripped[:-1].rstrip("\\"))
    return escapes % 2 == 0


def _cell_edge_inside_math(line: str) -> bool:
    """True when an unescaped pipe of `line` stands inside one of its math spans."""
    spans = math_span_ranges(line)
    return any(
        start <= edge.start() < end
        for edge in _UNESCAPED_PIPE_RE.finditer(line)
        for start, end in spans
    )


def _column_alignments(sep_line: str) -> list[tuple[bool, bool]]:
    """Per column of the delimiter row: whether it is pinned left, and right."""
    return [
        (cell.strip().startswith(":"), cell.strip().endswith(":"))
        for cell in table_cells(sep_line)
    ]


def _delimiter_cell(alignment: tuple[bool, bool], width: int) -> str:
    """One delimiter cell `width` wide with its colons, never without a dash."""
    left, right = alignment
    dashes = max(1, width - left - right)
    return f"{':' if left else ''}{'-' * dashes}{':' if right else ''}"


# The office route opens a cell tag at a line start and closes it at an end.
_CELL_OPEN_RE = re.compile(r"^(\s*)(<t[hd]\b[^>]*>)(.*)$", re.IGNORECASE)
_CELL_CLOSE_RE = re.compile(r"</t[hd]>\s*$", re.IGNORECASE)

_CELL_PARAGRAPH_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)

# A formula the route could not render as HTML, kept with its delimiters.
_MATH_SPAN_RE = re.compile(
    r'<span class="math (?:inline|display)">(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)

# A cell tag inside a cell: a swallowed neighbour or a nested grid.
_NESTED_CELL_RE = re.compile(r"</?(?:table|thead|tbody|tr|th|td)\b", re.IGNORECASE)

# Markdown has no cell to hold a list or a picture.
_CELL_STRUCTURE_RE = re.compile(r"<(?:ul|ol|li|dl|dt|dd|img)\b", re.IGNORECASE)

# A line start that markdown reads as a block. A marker needs whitespace
# after it, so a signed value (`-0,109`) stays a paragraph.
_MARKDOWN_BLOCK_RE = re.compile(
    r"(?:[-+*]|#{1,6}|\d+[.)])(?:\s|$)|[|>]|`{3,}|~{3,}|(?:-+|=+|\*{3,}|_{3,})$"
)

# A paired delimiter counts from its second occurrence; a single one stays
# a literal character.
_PAIRED_INLINE_CHARS = "*_`~"


def open_math_html_cells(text: str) -> str:
    """Open an HTML table cell around the formula markdown would not read.

    Markdown reads no inline markup inside an HTML block, so `$x$` stays
    literal. Blank lines around the cell content, freed of `<p>`, make it
    markdown while the table tags stay HTML. Only a cell with a delimited
    formula; a cell with a list, a picture, or a nested grid, or content
    markdown would misread, stays. Runs on text, last of all.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    in_table = html_table_lines(text)
    out: list[str] = []
    index = 0
    while index < len(lines):
        opened = _opened_cell(lines, in_table, index) if in_table[index] else None
        if opened is None:
            out.append(lines[index])
            index += 1
            continue
        cell_lines, end = opened
        out.extend(cell_lines)
        index = end + 1
    body = "\n".join(out)
    return f"{body}\n" if text.endswith("\n") else body


def _opened_cell(
    lines: list[str], in_table: list[bool], start: int
) -> tuple[list[str], int] | None:
    """The cell opening at `start` laid out as markdown, and its last line."""
    match = _CELL_OPEN_RE.match(lines[start])
    if match is None:
        return None
    indent, open_tag, head = match.groups()
    end = start
    parts = [head]
    while _CELL_CLOSE_RE.search(parts[-1]) is None:
        end += 1
        if end >= len(lines) or not in_table[end]:
            return None
        parts.append(lines[end])
    chunk = "\n".join(parts)
    close = _CELL_CLOSE_RE.search(chunk)
    if close is None:
        return None
    content = chunk[: close.start()]
    paragraphs = _cell_paragraphs(content)
    if paragraphs is None:
        return None
    cell_lines = [f"{indent}{open_tag}"]
    for paragraph in paragraphs:
        cell_lines.append("")
        cell_lines.extend(paragraph)
    cell_lines.extend(["", f"{indent}{close.group(0).strip()}"])
    return cell_lines, end


def _cell_paragraphs(content: str) -> list[list[str]] | None:
    """The cell's paragraphs as markdown lines, or None when it stays HTML."""
    if _NESTED_CELL_RE.search(content) or _CELL_STRUCTURE_RE.search(content):
        return None
    if not any("$" in span.group(1) for span in _MATH_SPAN_RE.finditer(content)):
        return None
    blocks = _paragraph_blocks(content)
    if blocks is None:
        return None
    paragraphs: list[list[str]] = []
    for block in blocks:
        # The delimiters carry the mode for the renderer; the class goes.
        opened = _MATH_SPAN_RE.sub(_unwrap_math_span, block)
        stripped = [line.strip() for line in opened.split("\n")]
        if not all(stripped):
            return None
        if any(_reads_as_markdown(line) for line in stripped):
            return None
        paragraphs.append(stripped)
    return paragraphs or None


def _reads_as_markdown(line: str) -> bool:
    """Whether markdown would read `line` as anything but its text, math aside."""
    if _MARKDOWN_BLOCK_RE.match(line):
        return True
    prose = _outside_math(line)
    if "\\" in prose or ("[" in prose and "]" in prose):
        return True
    return any(prose.count(char) > 1 for char in _PAIRED_INLINE_CHARS)


def _outside_math(line: str) -> str:
    """`line` with every math span cut out, leaving the text around them."""
    pieces: list[str] = []
    last = 0
    for start, end in math_span_ranges(line):
        pieces.append(line[last:start])
        last = end
    pieces.append(line[last:])
    return "".join(pieces)


def _paragraph_blocks(content: str) -> list[str] | None:
    """The cell's `<p>` blocks, or its one bare block; None for any other shape."""
    wrapped = list(_CELL_PARAGRAPH_RE.finditer(content))
    if not wrapped:
        return None if "<p" in content.lower() else [content]
    position = 0
    for block in wrapped:
        if content[position : block.start()].strip():
            return None
        position = block.end()
    if content[position:].strip():
        return None
    return [block.group(1) for block in wrapped]


def _unwrap_math_span(span: re.Match[str]) -> str:
    """The span's own delimiters where it holds them, else the span as it is."""
    content = span.group(1)
    return content if "$" in content else span.group(0)
