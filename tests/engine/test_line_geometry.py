"""A block keeps the frames of its detector lines when OCR reads it as a whole."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any

from PIL import Image

from ._helpers import Loader

_PAGE = (600.0, 800.0)
_BLOCK = (50.0, 100.0, 550.0, 160.0)
_LINES = [
    (50.0, 100.0, 550.0, 118.0),
    (50.0, 121.0, 550.0, 139.0),
    (50.0, 142.0, 300.0, 160.0),
]
_TEXT = "An invented paragraph that the model read as one line"


def _box(engine: Loader, box: tuple[float, float, float, float]) -> Any:
    return engine("marker.schema.polygon").PolygonBox.from_bbox(list(box))


def _corners(polygons: list[Any]) -> list[tuple[float, ...]]:
    return [tuple(polygon.bbox) for polygon in polygons]


def _page_with_block(engine: Loader) -> tuple[Any, Any, list[Any]]:
    schema: ModuleType = engine("marker.schema")
    page = engine("marker.schema.groups.page").PageGroup(
        polygon=_box(engine, (0.0, 0.0, *_PAGE)), page_id=0
    )
    block = page.add_full_block(
        engine("marker.schema.blocks").Text(
            polygon=_box(engine, _BLOCK), page_id=0, block_type=schema.BlockTypes.Text
        )
    )
    line_class = engine("marker.schema.text.line").Line
    lines = []
    for box in _LINES:
        line = page.add_full_block(line_class(polygon=_box(engine, box), page_id=0))
        block.add_structure(line)
        lines.append(line)
    return page, block, lines


def _ocr(engine: Loader, page: Any, block_ids: list[Any], texts: list[str]) -> None:
    """Run the OCR builder with a model that returns `texts`, one per id."""
    recognition = engine("surya.recognition")
    corners = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    text_lines = [
        recognition.TextLine(
            text=text,
            polygon=corners,
            chars=[recognition.TextChar(text=text, polygon=corners)],
        )
        for text in texts
    ]
    result = recognition.OCRResult(text_lines=text_lines, image_bbox=[0, 0, *_PAGE])
    builder = engine("marker.builders.ocr").OcrBuilder(
        recognition_model=lambda **kwargs: [result],
        config={"recognition_batch_size": 1},
    )
    image = Image.new("RGB", (int(_PAGE[0]), int(_PAGE[1])))
    builder.ocr_extraction(
        SimpleNamespace(pages=[page]),
        [page],
        [image],
        [[corners for _ in block_ids]],
        [block_ids],
        [["" for _ in block_ids]],
    )


def test_block_mode_keeps_the_detector_frames(engine: Loader) -> None:
    page, block, _ = _page_with_block(engine)

    _ocr(engine, page, [block.id], [_TEXT])

    assert _corners(block.line_polygons(page)) == _LINES
    assert len(block.structure) == 1


def test_block_mode_keeps_the_text_of_the_model(engine: Loader) -> None:
    page, block, _ = _page_with_block(engine)

    _ocr(engine, page, [block.id], [_TEXT])

    assert block.raw_text(page) == _TEXT + "\n"


def test_line_mode_gives_the_frames_of_the_lines(engine: Loader) -> None:
    page, block, lines = _page_with_block(engine)
    texts = ["An invented", "paragraph read", "line by line"]

    _ocr(engine, page, [line.id for line in lines], texts)

    assert block.detected_line_polygons is None
    assert _corners(block.line_polygons(page)) == _LINES
    assert block.raw_text(page) == "".join(text + "\n" for text in texts)


def test_line_height_counts_the_detector_frames(engine: Loader) -> None:
    page, block, _ = _page_with_block(engine)
    expected = (_BLOCK[3] - _BLOCK[1]) / len(_LINES)

    _ocr(engine, page, [block.id], [_TEXT])

    assert block.line_height(page) == expected


def test_line_height_of_a_block_in_line_mode(engine: Loader) -> None:
    page, block, lines = _page_with_block(engine)
    expected = (_BLOCK[3] - _BLOCK[1]) / len(_LINES)

    _ocr(engine, page, [line.id for line in lines], ["a", "b", "c"])

    assert block.line_height(page) == expected


def test_line_height_without_lines_is_zero(engine: Loader) -> None:
    schema: ModuleType = engine("marker.schema")
    page = engine("marker.schema.groups.page").PageGroup(
        polygon=_box(engine, (0.0, 0.0, *_PAGE)), page_id=0
    )
    block = page.add_full_block(
        engine("marker.schema.blocks").Text(
            polygon=_box(engine, _BLOCK), page_id=0, block_type=schema.BlockTypes.Text
        )
    )

    assert block.line_height(page) == 0
