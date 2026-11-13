"""A detector line goes to a picture only when it lies mostly inside its frame."""

from __future__ import annotations

from typing import Any

import pytest

from ._helpers import Loader

_Box = tuple[float, float, float, float]

_PAGE: _Box = (0.0, 0.0, 600.0, 800.0)
_PICTURE: _Box = (100.0, 100.0, 400.0, 300.0)
# A text block right of the chart's lower corner, under the line beside it.
_TEXT_BLOCK: _Box = (450.0, 305.0, 600.0, 400.0)
# A quarter of this line overlaps the chart; a smaller part overlaps the text.
_LINE_BESIDE: _Box = (250.0, 285.0, 550.0, 315.0)
_LINE_IN_CHART: _Box = (150.0, 200.0, 250.0, 215.0)
# Two thirds of this label lie inside the chart, the rest sticks out.
_LABEL_ON_EDGE: _Box = (360.0, 288.0, 410.0, 302.0)
# A wide line whose center is the center of a small picture.
_SMALL_PICTURE: _Box = (200.0, 200.0, 300.0, 300.0)
_WIDE_LINE_SAME_CENTER: _Box = (100.0, 240.0, 400.0, 260.0)


def _box(engine: Loader, box: _Box) -> Any:
    return engine("marker.schema.polygon").PolygonBox.from_bbox(list(box))


def _page(engine: Loader) -> Any:
    return engine("marker.schema.groups.page").PageGroup(
        polygon=_box(engine, _PAGE), page_id=0
    )


def _add(engine: Loader, page: Any, kind: str, box: _Box) -> Any:
    block_class = getattr(engine("marker.schema.blocks"), kind)
    block = page.add_full_block(block_class(polygon=_box(engine, box), page_id=0))
    page.add_structure(block)
    return block


def _line(engine: Loader, box: _Box) -> Any:
    line_class = engine("marker.schema.text.line").Line
    return engine("marker.providers").ProviderOutput(
        line=line_class(polygon=_box(engine, box), page_id=0), spans=[]
    )


def _lines_of(page: Any, block: Any) -> list[tuple[float, ...]]:
    return [tuple(line.polygon.bbox) for line in block.structure_blocks(page)]


@pytest.mark.parametrize("kind", ["Picture", "Figure"])
def test_line_beside_a_chart_goes_to_the_text(engine: Loader, kind: str) -> None:
    page = _page(engine)
    picture = _add(engine, page, kind, _PICTURE)
    text = _add(engine, page, "Text", _TEXT_BLOCK)

    page.merge_blocks([_line(engine, _LINE_BESIDE)], "pdftext")

    assert _lines_of(page, text) == [_LINE_BESIDE]
    assert _lines_of(page, picture) == []
    assert tuple(picture.polygon.bbox) == _PICTURE


def test_line_inside_a_chart_stays_with_it(engine: Loader) -> None:
    page = _page(engine)
    picture = _add(engine, page, "Picture", _PICTURE)
    _add(engine, page, "Text", _TEXT_BLOCK)

    page.merge_blocks(
        [_line(engine, _LINE_IN_CHART), _line(engine, _LABEL_ON_EDGE)], "pdftext"
    )

    assert _lines_of(page, picture) == [_LINE_IN_CHART, _LABEL_ON_EDGE]
    assert tuple(picture.polygon.bbox) == _PICTURE


def test_line_sharing_the_center_of_a_lone_picture_makes_a_new_block(
    engine: Loader,
) -> None:
    page = _page(engine)
    picture = _add(engine, page, "Picture", _SMALL_PICTURE)

    page.merge_blocks([_line(engine, _WIDE_LINE_SAME_CENTER)], "pdftext")

    new_blocks = [block for block in page.children if block.source == "heuristics"]
    assert len(new_blocks) == 1
    assert _lines_of(page, new_blocks[0]) == [_WIDE_LINE_SAME_CENTER]
    assert _lines_of(page, picture) == []


def test_line_without_a_text_block_makes_a_new_one(engine: Loader) -> None:
    page = _page(engine)
    picture = _add(engine, page, "Picture", _PICTURE)

    page.merge_blocks([_line(engine, _LINE_BESIDE)], "pdftext")

    new_blocks = [block for block in page.children if block.source == "heuristics"]
    assert len(new_blocks) == 1
    assert new_blocks[0].block_type == engine("marker.schema").BlockTypes.Text
    assert _lines_of(page, new_blocks[0]) == [_LINE_BESIDE]
    assert _lines_of(page, picture) == []
    assert tuple(picture.polygon.bbox) == _PICTURE
