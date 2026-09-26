"""Fold a docx table a pipe table can state into one, before the writer runs.

pandoc's gfm writer falls back to raw HTML for a table whose cell spans, holds
more than one block, or holds a line break. Word writes every cell as a
paragraph, so plain text tables come out as `<table>` markup, a zone the table
rules of the pipeline skip. The fold runs on the JSON tree between the reader
and the writer and turns each cell into one inline run, with `<br>` where a
printed line ended.

A table with a spanning cell, a cell holding a list, quote, or table, or a
bare `|` the writer prints verbatim stays whole: a pipe row reads that bar as
a cell border.
"""

from __future__ import annotations

from typing import Any

# What a cell may hold and still be one run of text.
_INLINE_BLOCKS = frozenset({"Plain", "Para"})

# Where a printed line ended inside a cell. A `LineBreak` node would send the
# writer back to HTML, so the break travels as markup instead.
_CELL_BREAK_HTML = "<br>"

# The writer escapes a bare `|` in cell text only, so a bar inside one of
# these reaches the row as a cell border. Display math is absent: cleaning
# escapes its bars on a pipe row.
_VERBATIM_INLINES = frozenset({"Code", "RawInline"})

# A link and an image write their target verbatim too.
_TARGET_INLINES = frozenset({"Link", "Image"})


def flatten_table_cells(doc: dict[str, Any]) -> None:
    """Fold the cells of every foldable table of `doc`, in place."""
    _walk(doc.get("blocks"))


def _walk(node: Any) -> None:
    """Visit every table that does not sit inside another table."""
    if isinstance(node, dict):
        if node.get("t") == "Table":
            _visit_table(node.get("c"))
            return
        _walk(node.get("c"))
        return
    if isinstance(node, list):
        for item in node:
            _walk(item)


def _visit_table(content: Any) -> None:
    cells = _table_cells(content)
    if cells is None or not all(_holds_one_run(cell) for cell in cells):
        return
    if any(_holds_a_bare_pipe(cell[4]) for cell in cells):
        return
    for cell in cells:
        _flatten_cell(cell)


def _table_cells(content: Any) -> list[Any] | None:
    """Every cell of the table, or None when the tree is not the known shape.

    An unknown shape (a later pandoc) skips the fold instead of failing the
    conversion.
    """
    if not isinstance(content, list) or len(content) != 6:
        return None
    _attr, _caption, _colspecs, head, bodies, foot = content
    if not isinstance(bodies, list):
        return None
    # A body carries its own head rows ahead of the rows themselves.
    row_lists = [_part(head, 1), _part(foot, 1)]
    for body in bodies:
        row_lists += [_part(body, 2), _part(body, 3)]

    cells: list[Any] = []
    for rows in row_lists:
        if rows is None:
            return None
        for row in rows:
            row_cells = _part(row, 1)
            if row_cells is None:
                return None
            cells += row_cells
    return cells


def _part(node: Any, index: int) -> list[Any] | None:
    """The list at `index` of an AST tuple, or None when it is not one."""
    if not isinstance(node, list) or len(node) <= index:
        return None
    part = node[index]
    return part if isinstance(part, list) else None


def _holds_one_run(cell: Any) -> bool:
    """True when this cell occupies one row and one column and holds text."""
    if not isinstance(cell, list) or len(cell) != 5:
        return False
    _attr, _align, row_span, col_span, blocks = cell
    if row_span != 1 or col_span != 1 or not isinstance(blocks, list):
        return False
    return all(
        isinstance(block, dict) and block.get("t") in _INLINE_BLOCKS for block in blocks
    )


def _flatten_cell(cell: list[Any]) -> None:
    """Fold the cell's paragraphs into one run, a break between each pair.

    An empty paragraph is a spacer and adds no break.
    """
    inlines: list[Any] = []
    for block in cell[4]:
        run = _inline_run(block)
        if not run:
            continue
        if inlines:
            inlines.append(_cell_break())
        inlines += run
    cell[4] = [{"t": "Plain", "c": inlines}] if inlines else []


def _inline_run(block: dict[str, Any]) -> list[Any]:
    content = block.get("c")
    if not isinstance(content, list):
        return []
    _replace_line_breaks(content)
    return content


def _replace_line_breaks(node: Any) -> None:
    """Rewrite every line break under `node` as the in-cell break markup.

    A nested break (in emphasis, a link, a footnote) also sends the writer to
    HTML, so the rewrite walks the whole subtree.
    """
    if isinstance(node, dict):
        _replace_line_breaks(node.get("c"))
        return
    if not isinstance(node, list):
        return
    for index, item in enumerate(node):
        if isinstance(item, dict) and item.get("t") == "LineBreak":
            node[index] = _cell_break()
        else:
            _replace_line_breaks(item)


def _cell_break() -> dict[str, Any]:
    return {"t": "RawInline", "c": ["html", _CELL_BREAK_HTML]}


def _holds_a_bare_pipe(node: Any) -> bool:
    """True when `node` carries a `|` the pipe writer would print verbatim."""
    if isinstance(node, list):
        return any(_holds_a_bare_pipe(item) for item in node)
    if not isinstance(node, dict):
        return False
    kind = node.get("t")
    content = node.get("c")
    if kind in _VERBATIM_INLINES:
        return _has_pipe(_at(content, 1))
    if kind == "Math":
        # `\left|` inside `$...$` is the shape at stake; the display form is
        # the one the cleaning rules escape on the row.
        return _at(content, 0) == {"t": "InlineMath"} and _has_pipe(_at(content, 1))
    if kind in _TARGET_INLINES:
        target = _at(content, 2)
        if isinstance(target, list) and any(_has_pipe(item) for item in target):
            return True
        return _holds_a_bare_pipe(_at(content, 1))
    return _holds_a_bare_pipe(content)


def _at(content: Any, index: int) -> Any:
    """The item at `index` of an AST tuple, or None when it is not there."""
    if isinstance(content, list) and len(content) > index:
        return content[index]
    return None


def _has_pipe(value: Any) -> bool:
    return isinstance(value, str) and "|" in value
