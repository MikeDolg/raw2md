"""The values of table columns with a narrow gap land in their own cells.

A text line that crosses cells stays whole: it is often a header that spans
columns the table model did not merge.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fpdf import FPDF

from ._helpers import Loader

# A4 in points, rendered at the resolution of the table images.
_PAGE_WIDTH, _PAGE_HEIGHT = 595.28, 841.89
_SCALE = 192 / 72
_IMAGE_SIZE = [round(_PAGE_WIDTH * _SCALE), round(_PAGE_HEIGHT * _SCALE)]
_FONT_SIZE = 10
_ROWS = [["1,001.0", "2,001.1", "3,001.2"], ["4,001.3", "5,001.4", "6,001.5"]]
_HEADER = [["Outer", "ring", "size"]]


def _table_pdf(
    path: Path, gap: float, rows: list[list[str]] = _ROWS
) -> list[list[float]]:
    """Write a table without rules and return the cell boxes on the image."""
    pdf = FPDF(unit="pt", format="A4")
    pdf.add_page()
    pdf.set_font("helvetica", size=_FONT_SIZE)
    cells = []
    for row, values in enumerate(rows):
        x, y = 100.0, 100.0 + row * 14
        for value in values:
            pdf.text(x, y, value)
            width = pdf.get_string_width(value)
            box = [x - gap / 2, y - 12, x + width + gap / 2, y + 2]
            cells.append([v * _SCALE for v in box])
            x += width + gap
    pdf.output(str(path))
    return cells


def _cell_texts(engine: Loader, path: Path, cells: list[list[float]]) -> list[str]:
    table_text = engine("pdftext.extraction").table_output(
        str(path),
        [{"tables": [[0, 0, *_IMAGE_SIZE]], "img_size": _IMAGE_SIZE}],
    )[0][0]
    table = SimpleNamespace(
        cells=[SimpleNamespace(bbox=c, text_lines=None) for c in cells]
    )
    processor = engine("marker.processors.table").TableProcessor
    processor.assign_text_to_cells(
        object.__new__(processor),
        [table],
        [{"ocr_block": False, "table_text_lines": table_text}],
    )
    return [
        " ".join(t["text"].strip() for t in c.text_lines or []) for c in table.cells
    ]


@pytest.mark.parametrize("gap", [3.0, 12.0])
def test_each_value_lands_in_its_cell(
    engine: Loader, tmp_path: Path, gap: float
) -> None:
    path = tmp_path / "table.pdf"
    cells = _table_pdf(path, gap)
    assert _cell_texts(engine, path, cells) == [v for row in _ROWS for v in row]


def test_run_inside_one_cell_stays_whole(engine: Loader, tmp_path: Path) -> None:
    path = tmp_path / "table.pdf"
    cells = _table_pdf(path, 3.0)
    rows = [
        [
            min(c[0] for c in cells[i : i + 3]),
            cells[i][1],
            max(c[2] for c in cells[i : i + 3]),
            cells[i][3],
        ]
        for i in (0, 3)
    ]
    assert _cell_texts(engine, path, rows) == [" ".join(row) for row in _ROWS]


def test_text_across_cells_stays_whole(engine: Loader, tmp_path: Path) -> None:
    path = tmp_path / "table.pdf"
    cells = _table_pdf(path, 3.0, _HEADER)
    texts = _cell_texts(engine, path, cells)
    assert sorted(texts) == ["", "", "Outer ring size"]


def _page(engine: Loader, gaps: list[float]) -> dict[str, Any]:
    bbox = engine("pdftext.schema").Bbox
    chars, x = [], 50.0
    for gap in gaps:
        chars.append({"char": "8", "bbox": bbox([x, 100.0, x + 5.0, 110.0])})
        x += 5.0 + gap
    span = {"chars": chars}
    return {"blocks": [{"lines": [{"spans": [span]}]}], "rotation": 0, "width": 600}


def test_gap_threshold_measures_the_gap_along_the_line(engine: Loader) -> None:
    tables = engine("pdftext.tables")
    page = _page(engine, [9.0] * 150)
    threshold = tables.get_dynamic_gap_thresh(page, _IMAGE_SIZE)
    assert threshold == pytest.approx(9.0 / 600)
