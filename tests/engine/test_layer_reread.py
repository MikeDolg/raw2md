"""The re-read of marked layer lines on scan pages, and its rules."""

from __future__ import annotations

import re
import types
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from ._helpers import Loader, engine_copy


@pytest.fixture
def ocr(engine_loader: Loader) -> types.ModuleType:
    return engine_loader("marker.builders.ocr")


@pytest.fixture
def engine_loader() -> Iterator[Loader]:
    with engine_copy() as load:
        yield load


def test_caret_marks_a_line(ocr: types.ModuleType) -> None:
    assert ocr.has_layer_mark("## ^ ^Jnstal1ati0n Gu1de^")


def test_replacement_char_marks_a_line(ocr: types.ModuleType) -> None:
    assert ocr.has_layer_mark(f"Setup {chr(0xFFFD)} guide")


def test_clean_line_is_not_marked(ocr: types.ModuleType) -> None:
    assert not ocr.has_layer_mark("Installation Guide 3.4-5")


def test_center_inside_a_block(ocr: types.ModuleType) -> None:
    blocks = [[0.0, 0.0, 100.0, 100.0]]
    assert ocr.bbox_center_in_blocks([40.0, 40.0, 60.0, 50.0], blocks)


def test_center_outside_with_edge_overlap(ocr: types.ModuleType) -> None:
    blocks = [[0.0, 0.0, 100.0, 100.0]]
    assert not ocr.bbox_center_in_blocks([90.0, 40.0, 130.0, 50.0], blocks)


def test_center_without_blocks(ocr: types.ModuleType) -> None:
    assert not ocr.bbox_center_in_blocks([0.0, 0.0, 10.0, 10.0], [])


def test_excluded_blocks_name_the_issue_types(ocr: types.ModuleType) -> None:
    names = {block.name for block in ocr.REREAD_EXCLUDED_BLOCKS}
    assert names == {"Picture", "Figure", "Table", "Form", "TableOfContents"}


@pytest.mark.parametrize(
    ("length", "limit"),
    [
        (0, 64),
        (5, 64),
        (6, 128),
        (26, 128),
        (27, 256),
        (69, 256),
        (70, 512),
        (154, 512),
        (155, 512),
        (2000, 512),
    ],
)
def test_token_limit_steps(ocr: types.ModuleType, length: int, limit: int) -> None:
    assert ocr.reread_token_limit("x" * length) == limit


def test_accepts_clean_text(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("## Installation Guide")


@pytest.mark.parametrize("text", ["", "   "])
def test_rejects_empty_text(ocr: types.ModuleType, text: str) -> None:
    assert not ocr.accept_reread(text)


@pytest.mark.parametrize("text", ["Guide ^ here", f"Guide {chr(0xFFFD)} here"])
def test_rejects_mark_outside_math(ocr: types.ModuleType, text: str) -> None:
    assert not ocr.accept_reread(text)


def test_accepts_caret_inside_math(ocr: types.ModuleType) -> None:
    text = 'Power <math display="inline">x^2 + y^3</math> of two'
    assert ocr.accept_reread(text)


def test_rejects_caret_after_math(ocr: types.ModuleType) -> None:
    text = "Power <math>x^2</math> then ^"
    assert not ocr.accept_reread(text)


def test_rejects_repeat_of_five(ocr: types.ModuleType) -> None:
    assert not ocr.accept_reread("Total " + "abc" * 5)


def test_accepts_repeat_of_four(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("Total " + "abc" * 4)


def test_accepts_short_group_repeated(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("Rule " + "ab" * 8)


def test_rejects_empty_group_inside_math(ocr: types.ModuleType) -> None:
    assert not ocr.accept_reread("Value <math>x_{}</math>")


def test_accepts_empty_group_outside_math(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("Set {} is empty")


_PAGE = (600.0, 800.0)
_MARKED = "## ^ ^Jnstal1ati0n Gu1de^"
_LONG_MARKED = "Step two: ^onnect the cab1e to the p0rt and t^rn the key"


class _Model:
    """Returns the reading set for the top edge of each polygon, in order."""

    def __init__(self, recognition: types.ModuleType, readings: dict[int, str]):
        self.recognition = recognition
        self.readings = readings
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> list[Any]:
        self.calls.append(kwargs)
        return [
            self.recognition.OCRResult(
                text_lines=[self._line(polygon) for polygon in page_polygons],
                image_bbox=[0, 0, *_PAGE],
            )
            for page_polygons in kwargs["polygons"]
        ]

    def _line(self, polygon: list[list[int]]) -> Any:
        text = self.readings[polygon[0][1]]
        corners = [[float(x), float(y)] for x, y in polygon]
        chars = [
            self.recognition.TextChar(text=part, polygon=corners)
            for part in re.findall(r"</?b>|[^<]+", text)
        ]
        return self.recognition.TextLine(text=text, polygon=corners, chars=chars)


class _Builder:
    """Builds pages of layer lines and runs the OCR builder on them."""

    def __init__(self, engine: Loader) -> None:
        self.engine = engine
        self.schema = engine("marker.schema")
        self.pages: list[Any] = []

    def box(self, box: tuple[float, float, float, float]) -> Any:
        return self.engine("marker.schema.polygon").PolygonBox.from_bbox(list(box))

    def page(self, method: str = "pdftext") -> Any:
        page = self.engine("marker.schema.groups.page").PageGroup(
            polygon=self.box((0.0, 0.0, *_PAGE)),
            page_id=len(self.pages),
            text_extraction_method=method,
            highres_image=Image.new("RGB", (int(_PAGE[0]), int(_PAGE[1]))),
        )
        self.pages.append(page)
        return page

    def block(
        self, page: Any, name: str, box: tuple[float, float, float, float]
    ) -> Any:
        block_type = getattr(self.schema.BlockTypes, name)
        block_class = self.engine("marker.schema.registry").get_block_class(block_type)
        block = page.add_full_block(
            block_class(polygon=self.box(box), page_id=page.page_id)
        )
        page.add_structure(block)
        return block

    def line(self, page: Any, block: Any, top: int, text: str) -> Any:
        box = (40.0, float(top), 560.0, float(top + 18))
        line = page.add_full_block(
            self.engine("marker.schema.text.line").Line(
                polygon=self.box(box),
                page_id=page.page_id,
                text_extraction_method="pdftext",
            )
        )
        block.add_structure(line)
        span = page.add_full_block(
            self.engine("marker.schema.text.span").Span(
                polygon=self.box(box),
                page_id=page.page_id,
                text=text,
                font="Invented",
                font_weight=400,
                font_size=12,
                minimum_position=0,
                maximum_position=len(text),
                formats=["plain"],
                text_extraction_method="pdftext",
            )
        )
        line.add_structure(span)
        return line

    def text_page(self, texts: dict[int, str], method: str = "pdftext") -> Any:
        page = self.page(method)
        block = self.block(page, "Text", (40.0, 100.0, 560.0, 700.0))
        for top, text in texts.items():
            self.line(page, block, top, text)
        return page

    def run(self, readings: dict[int, str], scan_pages: set[int]) -> _Model:
        document = self.engine("marker.schema.document").Document(
            filepath="invented.pdf", pages=self.pages
        )
        model = _Model(self.engine("surya.recognition"), readings)
        provider = SimpleNamespace(
            scan_pages=scan_pages,
            get_page_bbox=lambda page_id: self.box((0.0, 0.0, *_PAGE)),
        )
        builder = self.engine("marker.builders.ocr").OcrBuilder(
            recognition_model=model, config={"recognition_batch_size": 1}
        )
        builder(document, provider)
        self.document = document
        return model

    def text(self, line: Any) -> str:
        text: str = line.raw_text(self.document)
        return text


def _first_line(page: Any, builder: _Builder) -> Any:
    lines: list[Any] = page.contained_blocks(
        builder.document, [builder.schema.BlockTypes.Line]
    )
    return lines[0]


def test_accepted_reading_replaces_the_line(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.text_page({120: _MARKED})

    builder.run({120: "## Installation Guide"}, {0})

    line = _first_line(page, builder)
    assert builder.text(line) == "## Installation Guide\n"
    assert line.text_extraction_method == "surya"


def test_page_keeps_the_layer_method(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.text_page({120: _MARKED})

    builder.run({120: "## Installation Guide"}, {0})

    assert page.text_extraction_method == "pdftext"


def test_rejected_reading_keeps_the_layer(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.text_page({120: _MARKED})

    model = builder.run({120: "## Insta^lation Guide"}, {0})

    line = _first_line(page, builder)
    assert len(model.calls) == 1
    assert builder.text(line) == _MARKED
    assert line.text_extraction_method == "pdftext"


def test_reading_of_tags_alone_keeps_the_layer(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.text_page({120: _MARKED})

    builder.run({120: "<b></b>"}, {0})

    line = _first_line(page, builder)
    assert builder.text(line) == _MARKED
    assert line.text_extraction_method == "pdftext"


def test_reading_of_blanks_in_tags_keeps_the_layer(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.text_page({120: _MARKED})

    builder.run({120: "<b> </b>"}, {0})

    line = _first_line(page, builder)
    assert builder.text(line) == _MARKED
    assert line.text_extraction_method == "pdftext"


def test_line_with_character_blocks_is_read(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.text_page({120: _MARKED})
    span = page.contained_blocks(
        builder.engine("marker.schema.document").Document(
            filepath="invented.pdf", pages=builder.pages
        ),
        [builder.schema.BlockTypes.Span],
    )[0]
    char = page.add_full_block(
        builder.engine("marker.schema.text.char").Char(
            polygon=span.polygon, page_id=page.page_id, text="#", idx=0
        )
    )
    span.add_structure(char)

    model = builder.run({120: "## Installation Guide"}, {0})

    assert len(model.calls) == 1
    assert builder.text(_first_line(page, builder)) == "## Installation Guide\n"


def test_only_marked_lines_go_to_the_model(engine: Loader) -> None:
    builder = _Builder(engine)
    builder.text_page({120: "A clean invented line", 160: _MARKED})

    model = builder.run({160: "## Installation Guide"}, {0})

    line_polygon = [[40, 160], [560, 160], [560, 178], [40, 178]]
    assert [call["polygons"] for call in model.calls] == [[[line_polygon]]]


def test_page_off_the_scan_set_goes_nowhere(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.text_page({120: _MARKED})

    model = builder.run({}, set())

    assert model.calls == []
    assert builder.text(_first_line(page, builder)) == _MARKED


def test_page_read_by_the_model_goes_nowhere(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.page("surya")
    builder.line(
        page, builder.block(page, "Equation", (40.0, 100.0, 560.0, 200.0)), 120, _MARKED
    )

    model = builder.run({}, {0})

    assert model.calls == []


@pytest.mark.parametrize(
    "name", ["Picture", "Figure", "Table", "Form", "TableOfContents"]
)
def test_line_in_an_excluded_block_goes_nowhere(engine: Loader, name: str) -> None:
    builder = _Builder(engine)
    page = builder.page()
    text = builder.block(page, "Text", (40.0, 100.0, 560.0, 700.0))
    builder.line(page, text, 120, _MARKED)
    builder.block(page, name, (0.0, 100.0, 600.0, 150.0))

    model = builder.run({}, {0})

    assert model.calls == []


def test_line_in_an_equation_is_read(engine: Loader) -> None:
    builder = _Builder(engine)
    page = builder.page()
    equation = builder.block(page, "Equation", (40.0, 100.0, 560.0, 200.0))
    builder.line(page, equation, 120, _MARKED)

    model = builder.run({120: "## Installation Guide"}, {0})

    assert len(model.calls) == 1


def test_one_call_for_each_token_limit(engine: Loader) -> None:
    builder = _Builder(engine)
    builder.text_page({120: _LONG_MARKED, 160: _MARKED})
    builder.text_page({200: _MARKED})

    model = builder.run(
        {120: "Step two", 160: "## Installation Guide", 200: "## Setup Guide"},
        {0, 1},
    )

    assert [call["max_tokens"] for call in model.calls] == [128, 256]
    assert [len(call["images"]) for call in model.calls] == [2, 1]
    assert [len(polygons) for polygons in model.calls[0]["polygons"]] == [1, 1]


def test_readings_return_to_their_lines(engine: Loader) -> None:
    builder = _Builder(engine)
    first = builder.text_page({120: _LONG_MARKED, 160: _MARKED})
    second = builder.text_page({200: _MARKED})

    builder.run(
        {120: "Step two", 160: "## Installation Guide", 200: "## Setup Guide"},
        {0, 1},
    )

    line_type = builder.schema.BlockTypes.Line
    texts = [
        builder.text(line)
        for page in (first, second)
        for line in page.contained_blocks(builder.document, [line_type])
    ]
    assert texts == ["Step two\n", "## Installation Guide\n", "## Setup Guide\n"]
