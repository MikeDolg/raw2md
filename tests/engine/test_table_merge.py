"""A table that a page break cuts in two joins into one table.

The second part joins when it opens its page right after the first part
closes the previous page, the columns agree, and its first row repeats the
header of the first part or holds data. A part with a header of its own stays
a table of its own.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from PIL import Image

from ._helpers import Loader

_PAGE = [0.0, 0.0, 600.0, 800.0]
_ROW = 20.0
# The left edge of each column; a column ends where the next one starts.
_COLUMNS = [50.0, 200.0, 350.0, 500.0]
_RIGHT = 550.0

Rows = list[list[str]]


def _table(rows: Rows, header: bool = True, columns: list[int] | None = None) -> Any:
    """A table part; `columns` picks the columns of `_COLUMNS` that it holds."""
    return SimpleNamespace(kind="table", rows=rows, header=header, columns=columns)


def _block(kind: str) -> Any:
    return SimpleNamespace(kind=kind)


def _box(engine: Loader, box: list[float]) -> Any:
    return engine("marker.schema.polygon").PolygonBox.from_bbox(box)


def _add(page: Any, block: Any) -> Any:
    block.page_id = page.page_id
    page.add_full_block(block)
    page.add_structure(block)
    return block


def _add_table(engine: Loader, page: Any, spec: Any) -> None:
    blocks = engine("marker.schema.blocks")
    table = _add(
        page,
        blocks.Table(polygon=_box(engine, [50, 100, 550, 600]), page_id=page.page_id),
    )
    edges = [*_COLUMNS, _RIGHT]
    picked = spec.columns or list(range(len(spec.rows[0])))
    for row_id, row in enumerate(spec.rows):
        top = 100 + row_id * _ROW
        for col_id, text in enumerate(row):
            column = picked[col_id]
            cell = blocks.TableCell(
                polygon=_box(engine, [edges[column], top, edges[column + 1], top + 18]),
                text_lines=[text] if text else [],
                rowspan=1,
                colspan=1,
                row_id=row_id,
                col_id=col_id,
                is_header=row_id == 0,
                header_row=row_id == 0 and spec.header,
                page_id=page.page_id,
            )
            page.add_full_block(cell)
            table.add_structure(cell)


def _document(engine: Loader, pages: list[list[Any]]) -> Any:
    blocks = engine("marker.schema.blocks")
    page_class = engine("marker.schema.groups.page").PageGroup
    built = []
    for page_id, specs in enumerate(pages):
        page = page_class(polygon=_box(engine, _PAGE), page_id=page_id, structure=[])
        page.lowres_image = Image.new("RGB", (600, 800), "white")
        page.highres_image = Image.new("RGB", (600, 800), "white")
        for spec in specs:
            if spec.kind == "table":
                _add_table(engine, page, spec)
            elif spec.kind == "text":
                _add(page, blocks.Text(polygon=_box(engine, [50, 650, 550, 700])))
            elif spec.kind == "footer":
                _add(page, blocks.PageFooter(polygon=_box(engine, [50, 760, 550, 790])))
            elif spec.kind == "header":
                _add(page, blocks.PageHeader(polygon=_box(engine, [50, 10, 550, 40])))
        built.append(page)
    return engine("marker.schema.document").Document(
        filepath="invented.pdf", pages=built
    )


def _tables(engine: Loader, pages: list[list[Any]]) -> list[Rows]:
    """The tables of the document after the join, each as rows of cell texts."""
    document = _document(engine, pages)
    engine("marker.processors.table_merge").TableMergeProcessor({})(document)
    tables = []
    for block in document.contained_blocks([engine("marker.schema").BlockTypes.Table]):
        cells = block.contained_blocks(document)
        width = max(cell.col_id + cell.colspan for cell in cells)
        height = max(cell.row_id + cell.rowspan for cell in cells)
        grid = [["?"] * width for _ in range(height)]
        for cell in cells:
            grid[cell.row_id][cell.col_id] = " ".join(cell.text_lines)
        tables.append(grid)
    return tables


_DATA = [["Name", "Value"], ["Mass", "2 kg"], ["Length", "3 m"]]


def test_part_with_a_header_of_its_own_stays_apart(engine: Loader) -> None:
    first = _table([["Property", "Value"], ["Width", "40 mm"], ["Weight", "0.3 kg"]])
    second = _table([["Description", "Order number"], ["Base module", "4XA 100-2"]])

    assert _tables(engine, [[first], [second]]) == [first.rows, second.rows]


def test_part_that_opens_with_data_joins(engine: Loader) -> None:
    second = _table([["Depth", "5 cm"], ["Area", "1 m2"]], header=False)

    assert _tables(engine, [[_table(_DATA)], [second]]) == [_DATA + second.rows]


def test_repeated_header_joins_and_goes(engine: Loader) -> None:
    second = _table([["Name", "Value"], ["Depth", "5 cm"]])

    assert _tables(engine, [[_table(_DATA)], [second]]) == [[*_DATA, ["Depth", "5 cm"]]]


def test_repeated_header_read_as_data_goes(engine: Loader) -> None:
    second = _table([["Name", "Value"], ["Depth", "5 cm"]], header=False)

    assert _tables(engine, [[_table(_DATA)], [second]]) == [[*_DATA, ["Depth", "5 cm"]]]


def test_running_header_and_footer_between_parts_join(engine: Loader) -> None:
    second = _table([["Depth", "5 cm"]], header=False)
    pages = [[_table(_DATA), _block("footer")], [_block("header"), second]]

    assert _tables(engine, pages) == [[*_DATA, ["Depth", "5 cm"]]]


def test_text_between_parts_keeps_them_apart(engine: Loader) -> None:
    second = _table([["Depth", "5 cm"]], header=False)
    pages = [[_table(_DATA), _block("text")], [second]]

    assert _tables(engine, pages) == [_DATA, second.rows]


def test_column_less_found_by_position_joins_with_an_empty_cell(
    engine: Loader,
) -> None:
    first = _table([["Name", "Unit", "Value"], ["Mass", "kg", "2"]])
    second = _table([["Length", "3"]], header=False, columns=[0, 2])

    assert _tables(engine, [[first], [second]]) == [
        [["Name", "Unit", "Value"], ["Mass", "kg", "2"], ["Length", "", "3"]]
    ]


def test_two_columns_less_stay_apart(engine: Loader) -> None:
    first = _table([["Name", "Unit", "Low", "High"], ["Mass", "kg", "1", "2"]])
    second = _table([["Length", "3"]], header=False)

    assert _tables(engine, [[first], [second]]) == [first.rows, second.rows]


def test_table_over_three_pages_joins_as_a_chain(engine: Loader) -> None:
    second = _table([["Name", "Value"], ["Depth", "5 cm"]])
    third = _table([["Area", "1 m2"]], header=False)
    pages = [[_table(_DATA)], [second], [third]]

    assert _tables(engine, pages) == [[*_DATA, ["Depth", "5 cm"], ["Area", "1 m2"]]]


def test_split_rows_keep_the_header_row_of_the_model(engine: Loader) -> None:
    schema = engine("surya.table_rec.schema")
    processor = engine("marker.processors.table").TableProcessor
    instance = object.__new__(processor)
    instance.row_split_threshold = 0.5

    def cell(row_id: int, col_id: int, lines: int) -> Any:
        return schema.TableCell(
            polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
            row_id=row_id,
            col_id=col_id,
            colspan=1,
            rowspan=1,
            within_row_id=col_id,
            cell_id=row_id * 2 + col_id,
            is_header=row_id == 0,
            text_lines=[{"text": "x"}] * lines,
        )

    cells = [cell(0, 0, 2), cell(0, 1, 2), cell(1, 0, 2), cell(1, 1, 2)]
    table = SimpleNamespace(cells=cells)
    header_rows = [{1}]

    processor.split_combined_rows(instance, [table], header_rows)

    assert header_rows == [{2}]


def test_records_set_side_by_side_stay_apart(engine: Loader) -> None:
    first = _table([["Name", "Value", "Name", "Value"], ["Mass", "2", "Area", "4"]])
    second = _table([["Length", "3", "Depth", "5"]], header=False)

    assert _tables(engine, [[first], [second]]) == [first.rows, second.rows]
