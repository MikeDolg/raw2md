"""A table that a page break or a column break cuts in two joins into one table.

The second part joins when it opens its page right after the first part
closes the previous page, or opens the next column right after the first part
ends its column, the columns agree, and its first row repeats the header of
the first part or holds data. A first row that the table model flags as a
header holds data when its cells have the forms of the columns of the first
part, or when it holds only a label and the next row that fills another column
holds data. A part with a header of its own stays a table of its own.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from ._helpers import Loader

_PAGE = [0.0, 0.0, 600.0, 800.0]
_ROW = 20.0
# The left edge of each column; a column ends where the next one starts.
_COLUMNS = [50.0, 200.0, 350.0, 500.0]
_RIGHT = 550.0

Rows = list[list[str]]
SpanRows = list[list[str | None]]


def _table(
    rows: Rows | SpanRows,
    header: bool | int = True,
    columns: list[int] | None = None,
    spans: dict[tuple[int, int], int] | None = None,
    edges: list[float] | None = None,
    top: float = 100.0,
    colspans: dict[tuple[int, int], int] | None = None,
) -> Any:
    """A table part.

    `header` counts the header rows, `columns` picks the columns of `edges`,
    `spans` and `colspans` give the spans of a cell, and a covered cell is
    `None`. `edges` are the left column edges and the right table edge.
    """
    return SimpleNamespace(
        kind="table",
        rows=rows,
        header=int(header),
        columns=columns,
        spans=spans or {},
        colspans=colspans or {},
        edges=edges or [*_COLUMNS, _RIGHT],
        top=top,
    )


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
    edges = spec.edges
    box = [edges[0], spec.top, edges[-1], spec.top + 500]
    table = _add(page, blocks.Table(polygon=_box(engine, box), page_id=page.page_id))
    picked = spec.columns or list(range(len(spec.rows[0])))
    for row_id, row in enumerate(spec.rows):
        top = spec.top + row_id * _ROW
        for col_id, text in enumerate(row):
            if text is None:
                continue
            column = picked[col_id]
            colspan = spec.colspans.get((row_id, col_id), 1)
            right = edges[column + colspan]
            cell = blocks.TableCell(
                polygon=_box(engine, [edges[column], top, right, top + 18]),
                text_lines=[text] if text else [],
                rowspan=spec.spans.get((row_id, col_id), 1),
                colspan=colspan,
                row_id=row_id,
                col_id=col_id,
                is_header=row_id == 0,
                header_row=row_id < spec.header,
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


def test_equal_data_rows_after_the_header_are_records(engine: Loader) -> None:
    first = _table([["Name", "Value"], ["Mass", "2"]])
    second = _table([["Name", "Value"], ["Mass", "2"], ["Area", "4"]])

    assert _tables(engine, [[first], [second]]) == [
        [["Name", "Value"], ["Mass", "2"], ["Mass", "2"], ["Area", "4"]]
    ]


def test_headers_that_differ_in_a_later_row_stay_apart(engine: Loader) -> None:
    first = _table([["Name", "Value"], ["Unit", "kg"], ["Mass", "2"]], header=2)
    second = _table([["Name", "Value"], ["Unit", "lb"], ["Area", "4"]], header=2)

    assert _tables(engine, [[first], [second]]) == [first.rows, second.rows]


def test_two_row_header_repeated_in_full_joins(engine: Loader) -> None:
    first = _table([["Name", "Value"], ["Unit", "kg"], ["Mass", "2"]], header=2)
    second = _table([["Name", "Value"], ["Unit", "kg"], ["Area", "4"]], header=2)

    assert _tables(engine, [[first], [second]]) == [[*first.rows, ["Area", "4"]]]


def test_span_across_the_cut_keeps_the_parts_apart(engine: Loader) -> None:
    rows: SpanRows = [["", ""], [None, "42"]]
    second = _table(rows, header=False, spans={(0, 0): 2})

    assert _tables(engine, [[_table(_DATA)], [second]]) == [
        _DATA,
        [["", ""], ["?", "42"]],
    ]


# Two columns of a page, each with the left edges of three table columns and
# the right edge of the table.
_LEFT = [30.0, 110.0, 190.0, 270.0]
_RIGHT_COLUMN = [330.0, 410.0, 490.0, 570.0]
_PARTS = [["Part", "Size", "Weight"], ["AB-100", "M4", "12 g"]]
_NEXT = [["AB-200", "M6", "20 g"], ["AB-300", "M8", "31 g"]]


def test_table_cut_by_a_column_joins(engine: Loader) -> None:
    first = _table(_PARTS, edges=_LEFT)
    second = _table(_NEXT, header=False, edges=_RIGHT_COLUMN)

    assert _tables(engine, [[first, second]]) == [_PARTS + _NEXT]


@pytest.mark.parametrize(
    ("edges", "top"),
    [(_RIGHT_COLUMN, 300.0), (_LEFT, 400.0)],
    ids=["lower-in-the-next-column", "under-the-first"],
)
def test_tables_without_a_column_break_stay_apart(
    engine: Loader, edges: list[float], top: float
) -> None:
    first = _table(_PARTS, edges=_LEFT)
    second = _table(_NEXT, header=False, edges=edges, top=top)

    assert _tables(engine, [[first, second]]) == [_PARTS, _NEXT]


def test_column_parts_with_other_column_widths_stay_apart(engine: Loader) -> None:
    first = _table(_PARTS, edges=[30.0, 70.0, 110.0, 270.0])
    second = _table(_NEXT, header=False, edges=[330.0, 490.0, 530.0, 570.0])

    assert _tables(engine, [[first, second]]) == [_PARTS, _NEXT]


def test_column_part_with_a_header_of_its_own_stays_apart(engine: Loader) -> None:
    first = _table(_PARTS, edges=_LEFT)
    rows = [["Item", "Code", "Mass"], ["CD-1", "X", "5 g"]]
    second = _table(rows, edges=_RIGHT_COLUMN)

    assert _tables(engine, [[first, second]]) == [_PARTS, rows]


def test_text_between_column_parts_keeps_them_apart(engine: Loader) -> None:
    first = _table(_PARTS, edges=_LEFT)
    second = _table(_NEXT, header=False, edges=_RIGHT_COLUMN)

    assert _tables(engine, [[first, _block("text"), second]]) == [_PARTS, _NEXT]


def test_table_over_three_columns_joins_as_a_chain(engine: Loader) -> None:
    narrow = [[20.0, 60.0, 100.0, 140.0], [220.0, 260.0, 300.0, 340.0]]
    first = _table(_PARTS, edges=narrow[0])
    second = _table(_NEXT[:1], header=False, edges=narrow[1])
    third = _table(_NEXT[1:], header=False, edges=[420.0, 460.0, 500.0, 540.0])

    assert _tables(engine, [[first, second, third]]) == [_PARTS + _NEXT]


def test_column_part_with_a_column_less_joins_with_an_empty_cell(
    engine: Loader,
) -> None:
    first = _table(_PARTS, edges=_LEFT)
    second = _table(
        [["AB-200", "20 g"]], header=False, columns=[0, 2], edges=_RIGHT_COLUMN
    )
    pages = [[first, second]]

    assert _tables(engine, pages) == [[*_PARTS, ["AB-200", "", "20 g"]]]


_FUNDS = [["Fund", "Currency", "Value"], ["Alpha Income", "EUR", "104.20"]]
_MORE_FUNDS = [["Beta Growth", "EUR", "98.75"], ["Gamma Bond", "EUR", "101.10"]]


def test_flagged_first_row_with_the_forms_of_the_columns_is_data(
    engine: Loader,
) -> None:
    pages = [[_table(_FUNDS)], [_table(_MORE_FUNDS)]]
    document = _document(engine, pages)
    engine("marker.processors.table_merge").TableMergeProcessor({})(document)
    blocks = document.contained_blocks([engine("marker.schema").BlockTypes.Table])

    assert _tables(engine, pages) == [_FUNDS + _MORE_FUNDS]
    assert [
        cell.row_id for cell in blocks[0].contained_blocks(document) if cell.is_header
    ] == [0, 0, 0]


def test_flagged_row_of_words_over_numbers_stays_a_header(engine: Loader) -> None:
    rows = [["Bond", "Rate", "Term"], ["Delta Bond", "2.5%", "10"]]
    first = _table([["Fund", "Rate", "Term"], ["Alpha Bond", "3.1%", "5"]])

    assert _tables(engine, [[first], [_table(rows)]]) == [first.rows, rows]


def test_flagged_row_with_an_empty_cell_and_a_number_is_data(engine: Loader) -> None:
    second = _table([["", "5 cm"], ["Area", "1 m2"]])

    assert _tables(engine, [[_table(_DATA)], [second]]) == [_DATA + second.rows]


def test_flagged_row_over_text_columns_only_stays_a_header(engine: Loader) -> None:
    first = _table([["Name", "City"], ["Alpha", "Lyon"], ["Beta", "Graz"]])
    second = _table([["Gamma", "Porto"], ["Delta", "Turin"]])

    assert _tables(engine, [[first], [second]]) == [first.rows, second.rows]


def test_flagged_row_with_the_same_code_is_data(engine: Loader) -> None:
    first = _table([["Item", "Code"], ["Pin", "RT-4"], ["Bolt", "RT-4"]])
    second = _table([["Nut", "RT-4"], ["Washer", "RT-4"]])

    assert _tables(engine, [[first], [second]]) == [first.rows + second.rows]


def test_flagged_row_with_another_code_stays_a_header(engine: Loader) -> None:
    first = _table([["Item", "Code"], ["Pin", "RT-4"], ["Bolt", "RT-4"]])
    second = _table([["Nut", "RT-5"], ["Washer", "RT-5"]])

    assert _tables(engine, [[first], [second]]) == [first.rows, second.rows]


def test_flagged_first_row_at_a_column_break_is_data(engine: Loader) -> None:
    first = _table(_PARTS, edges=_LEFT)
    second = _table(_NEXT, edges=_RIGHT_COLUMN)

    assert _tables(engine, [[first, second]]) == [_PARTS + _NEXT]


_ASSETS = [["Item", "2023", "2022"], ["Cash", "1 200.5", "1 150.0"]]
_CURRENT = [
    ["Current assets", "", ""],
    ["Receivables", "830.2", "-"],
    ["Inventory", "412.0", "398.7"],
]


def test_flagged_label_row_over_a_data_row_is_data(engine: Loader) -> None:
    second = _table(_CURRENT, header=2)
    pages = [[_table(_ASSETS)], [second]]
    document = _document(engine, pages)
    engine("marker.processors.table_merge").TableMergeProcessor({})(document)
    blocks = document.contained_blocks([engine("marker.schema").BlockTypes.Table])

    assert _tables(engine, pages) == [_ASSETS + _CURRENT]
    assert [
        cell.row_id for cell in blocks[0].contained_blocks(document) if cell.header_row
    ] == [0, 0, 0]


def test_flagged_label_row_over_a_row_of_words_stays_a_header(engine: Loader) -> None:
    rows = [["Current assets", "", ""], ["Account", "Year", "Prior"], *_CURRENT[1:]]

    assert _tables(engine, [[_table(_ASSETS)], [_table(rows)]]) == [_ASSETS, rows]


def test_flagged_label_row_alone_stays_a_header(engine: Loader) -> None:
    rows = [["Current assets", "", ""]]

    assert _tables(engine, [[_table(_ASSETS)], [_table(rows)]]) == [_ASSETS, rows]


def test_flagged_row_of_words_over_placeholders_stays_a_header(engine: Loader) -> None:
    first = _table([*_ASSETS, ["Loans", "-", "310.4"]])
    rows = [["Account", "Year", "Prior"], ["Bonds", "92.1", "-"]]

    assert _tables(engine, [[first], [_table(rows)]]) == [first.rows, rows]


def test_flagged_row_with_a_cell_over_columns_is_data(engine: Loader) -> None:
    first = _table(
        [["Item", "Unit", "Count"], ["Pin", "pcs", "4"], ["Bolt", "pcs", "6"]]
    )
    rows: SpanRows = [["Total of all parts", None, "10"], ["Nut", "pcs", "8"]]
    second = _table(rows, colspans={(0, 0): 2})

    assert _tables(engine, [[first], [second]]) == [
        [*first.rows, ["Total of all parts", "?", "10"], ["Nut", "pcs", "8"]]
    ]


@pytest.mark.parametrize(
    ("values", "cell"),
    [(["4", "-", "7"], "5"), (["4", "6", "7"], "-"), (["4", "/", "7"], "*")],
    ids=["in-the-column", "in-the-row", "both"],
)
def test_flagged_row_with_a_placeholder_is_data(
    engine: Loader, values: list[str], cell: str
) -> None:
    first = _table(
        [
            ["Item", "Count"],
            *[[f"Part {index}", value] for index, value in enumerate(values)],
        ]
    )
    second = _table([["Nut", cell], ["Washer", "9"]])

    assert _tables(engine, [[first], [second]]) == [first.rows + second.rows]


def test_column_of_placeholders_alone_holds_no_numbers(engine: Loader) -> None:
    first = _table([["Item", "Note"], ["Pin", "-"], ["Bolt", "_"]])
    second = _table([["Nut", "5"], ["Washer", "9"]])

    assert _tables(engine, [[first], [second]]) == [first.rows, second.rows]


@pytest.mark.parametrize(
    ("values", "joined"),
    [
        (["12", "15", "17", "19", "see note"], True),
        (["12", "15", "17", "see note", "none"], False),
        (["12", "see note"], False),
    ],
    ids=["four-of-five", "three-of-five", "one-of-two"],
)
def test_column_with_most_values_numbers_holds_numbers(
    engine: Loader, values: list[str], joined: bool
) -> None:
    first = _table(
        [
            ["Item", "Count"],
            *[[f"Part {index}", value] for index, value in enumerate(values)],
        ]
    )
    second = _table([["Nut", "20"], ["Washer", "22"]])
    tables = [first.rows + second.rows] if joined else [first.rows, second.rows]

    assert _tables(engine, [[first], [second]]) == tables
