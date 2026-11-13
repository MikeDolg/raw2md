"""A picture that repeats at one place in the band of a running header is hidden."""

from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from ._helpers import Loader

_Box = tuple[float, float, float, float]

_PAGE: _Box = (0.0, 0.0, 600.0, 800.0)
_TOP_LOGO: _Box = (40.0, 20.0, 160.0, 70.0)
_BOTTOM_LOGO: _Box = (40.0, 750.0, 160.0, 790.0)
_CHART: _Box = (100.0, 300.0, 500.0, 500.0)
# A shift of 15 points is 0.025 of the page width, more than the tolerance.
_SHIFT = 15.0


def _box(engine: Loader, box: _Box) -> Any:
    return engine("marker.schema.polygon").PolygonBox.from_bbox(list(box))


def _document(engine: Loader, pictures: list[list[_Box]]) -> Any:
    """A document with one page for each list of picture frames."""
    page_class = engine("marker.schema.groups.page").PageGroup
    picture_class = engine("marker.schema.blocks").Picture
    pages = []
    for page_id, frames in enumerate(pictures):
        page = page_class(polygon=_box(engine, _PAGE), page_id=page_id, structure=[])
        page.lowres_image = Image.new("RGB", (600, 800), "white")
        page.highres_image = Image.new("RGB", (600, 800), "white")
        for frame in frames:
            block = page.add_full_block(
                picture_class(polygon=_box(engine, frame), page_id=page_id)
            )
            page.add_structure(block)
        pages.append(page)
    return engine("marker.schema.document").Document(
        filepath="invented.pdf", pages=pages
    )


def _hidden(engine: Loader, pictures: list[list[_Box]]) -> list[list[bool]]:
    document = _document(engine, pictures)
    engine("marker.processors.image_furniture").ImageFurnitureProcessor({})(document)
    return [
        [block.ignore_for_output for block in page.children] for page in document.pages
    ]


def _shifted(box: _Box, steps: int) -> _Box:
    x0, y0, x1, y1 = box
    return (x0 + steps * _SHIFT, y0, x1 + steps * _SHIFT, y1)


@pytest.mark.parametrize("logo", [_TOP_LOGO, _BOTTOM_LOGO])
def test_logo_on_three_pages_is_hidden(engine: Loader, logo: _Box) -> None:
    pictures = [[logo, _CHART], [_CHART, logo], [logo]]

    assert _hidden(engine, pictures) == [[True, False], [False, True], [True]]


def test_logo_on_two_pages_stays(engine: Loader) -> None:
    pictures = [[_TOP_LOGO], [_TOP_LOGO], [_CHART]]

    assert _hidden(engine, pictures) == [[False], [False], [False]]


def test_frames_in_the_middle_of_the_page_stay(engine: Loader) -> None:
    pictures = [[_CHART] for _ in range(4)]

    assert _hidden(engine, pictures) == [[False]] * 4


def test_frames_shifted_more_than_the_tolerance_stay(engine: Loader) -> None:
    pictures = [[_shifted(_TOP_LOGO, steps)] for steps in range(4)]

    assert _hidden(engine, pictures) == [[False]] * 4


def test_frame_across_the_band_edge_stays(engine: Loader) -> None:
    # The bottom edge lies at 0.2 of the page height, below the top band.
    tall_logo = (40.0, 20.0, 160.0, 160.0)
    pictures = [[tall_logo] for _ in range(3)]

    assert _hidden(engine, pictures) == [[False]] * 3


def test_hidden_logo_has_no_image_and_no_reference(engine: Loader) -> None:
    document = _document(engine, [[_TOP_LOGO, _CHART] for _ in range(3)])
    engine("marker.processors.image_furniture").ImageFurnitureProcessor({})(document)

    output = engine("marker.renderers.markdown").MarkdownRenderer()(document)

    charts = {f"_page_{page}_Picture_1.jpeg" for page in range(3)}
    assert set(output.images) == charts
    assert output.markdown.count("![](") == 3
    assert all(f"![]({name})" in output.markdown for name in charts)
    assert all(len(page.children) == 2 for page in document.pages)
