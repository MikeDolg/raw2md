"""The lines of a table cell: a wrapped value joins, a new value stays apart.

A line wraps onto the next one when the first word of the next line would
not fit into the space left on it, and the next line follows at the leading
of a paragraph. The text width of a column is its widest line, so the rule
holds for any alignment.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ._helpers import Loader

_CHAR = 5.0
_HEIGHT = 10.0


def _line(
    text: str, row: int, right: float | None = None, gap: float = 2.0
) -> dict[str, Any]:
    """A text line of the text layer, `_CHAR` wide for each character."""
    width = len(text.rstrip("\x02")) * _CHAR
    x0 = 0.0 if right is None else right - width
    y0 = row * (_HEIGHT + gap)
    return {"text": text, "bbox": [x0, y0, x0 + width, y0 + _HEIGHT]}


def _cell(
    lines: list[dict[str, Any]], col_id: int = 0, row_id: int = 0, width: float = 400
) -> SimpleNamespace:
    return SimpleNamespace(
        text_lines=lines,
        col_id=col_id,
        colspan=1,
        row_id=row_id,
        bbox=[0.0, 0.0, width, 100.0],
    )


def _texts(engine: Loader, cells: list[SimpleNamespace]) -> list[list[str]]:
    processor = engine("marker.processors.table").TableProcessor
    instance = object.__new__(processor)
    widths = processor.column_text_widths(cells)
    return [
        list(instance.finalize_cell_text(c, widths.get((c.col_id, c.colspan))))
        for c in cells
    ]


def test_wrapped_name_joins_with_a_space(engine: Loader) -> None:
    header = _cell([_line("Compound description", 0)])
    name = _cell(
        [_line("Nitrile rubber for low", 1), _line("temperatures", 2)], row_id=1
    )
    assert _texts(engine, [header, name])[1] == ["Nitrile rubber for low temperatures"]


def test_short_values_stay_apart(engine: Loader) -> None:
    header = _cell([_line("Order number", 0)])
    sizes = _cell([_line("2-327", 1), _line("2-328", 2)], row_id=1)
    assert _texts(engine, [header, sizes])[1] == ["2-327", "2-328"]


def test_hyphen_before_lowercase_goes(engine: Loader) -> None:
    header = _cell([_line("Material", 0)])
    name = _cell([_line("Fluoro-", 1), _line("carbon", 2)], row_id=1)
    assert _texts(engine, [header, name])[1] == ["Fluorocarbon"]


def test_hyphen_before_digit_stays(engine: Loader) -> None:
    header = _cell([_line("Standard", 0)])
    name = _cell([_line("Standard ISO-", 1), _line("3601 sizes", 2)], row_id=1)
    assert _texts(engine, [header, name])[1] == ["Standard ISO-3601 sizes"]


def test_hyphen_mark_of_the_text_layer_joins_the_word(engine: Loader) -> None:
    header = _cell([_line("Material", 0)])
    name = _cell([_line("Fluoro\x02", 1), _line("carbon", 2)], row_id=1)
    assert _texts(engine, [header, name])[1] == ["Fluorocarbon"]


def test_rows_merged_into_one_cell_stay_apart(engine: Loader) -> None:
    header = _cell([_line("Order", 0, gap=5.0)])
    sizes = _cell([_line("2-327", 1, gap=5.0), _line("2-328", 2, gap=5.0)], row_id=1)
    assert _texts(engine, [header, sizes])[1] == ["2-327", "2-328"]


def test_bullet_opens_a_new_value(engine: Loader) -> None:
    header = _cell([_line("Compounds", 0)])
    items = _cell([_line("• N0674-70", 1), _line("• N0741-75", 2)], row_id=1)
    assert _texts(engine, [header, items])[1] == ["• N0674-70", "• N0741-75"]


def test_right_aligned_column_reads_the_same(engine: Loader) -> None:
    right = 200.0
    header = _cell([_line("Compound description", 0, right)])
    name = _cell(
        [_line("Nitrile rubber for low", 1, right), _line("temperatures", 2, right)],
        row_id=1,
    )
    sizes = _cell([_line("2-327", 3, right), _line("2-328", 4, right)], row_id=2)
    assert _texts(engine, [header, name, sizes])[1:] == [
        ["Nitrile rubber for low temperatures"],
        ["2-327", "2-328"],
    ]


def test_columns_measure_their_own_width(engine: Loader) -> None:
    wide = _cell([_line("A rather long description", 0)], col_id=0)
    sizes = _cell([_line("2-327", 0), _line("2-328", 1)], col_id=1)
    assert _texts(engine, [wide, sizes])[1] == ["2-327 2-328"]


def test_row_label_over_the_next_columns_keeps_the_column_narrow(
    engine: Loader,
) -> None:
    label = _cell([_line("Hydrogenated nitrile rubber", 0)], width=60)
    name = _cell([_line("Compound", 1), _line("code", 2)], row_id=1, width=60)
    assert _texts(engine, [label, name])[1] == ["Compound code"]


def test_line_in_another_column_of_a_merged_cell_stays_apart(engine: Loader) -> None:
    header = _cell([_line("Size", 0)])
    left = _line("Inner diameter", 1)
    right = {"text": "2-425", "bbox": [200.0, 24.0, 225.0, 34.0]}
    assert _texts(engine, [header, _cell([left, right], row_id=1)])[1] == [
        "Inner diameter",
        "2-425",
    ]


def test_pieces_of_one_line_stay_apart(engine: Loader) -> None:
    header = _cell([_line("A rather long description", 0)])
    left = _line("Item", 1)
    right = {"text": "7", "bbox": [100.0, 12.0, 100.0 + _CHAR, 22.0]}
    assert _texts(engine, [header, _cell([left, right], row_id=1)])[1] == [
        "Item",
        "7",
    ]


def test_cell_without_line_boxes_stays_as_it_is(engine: Loader) -> None:
    cell = _cell([{"text": "Nitrile rubber for low"}, {"text": "temperatures"}])
    assert _texts(engine, [cell])[0] == ["Nitrile rubber for low", "temperatures"]
