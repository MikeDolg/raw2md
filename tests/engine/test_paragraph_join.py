"""A paragraph cut by a page, a column, or a figure reads as one paragraph."""

from __future__ import annotations

from typing import Any

import pytest
from PIL import Image

from ._helpers import Loader

_PAGE = (600.0, 800.0)
_HAN = chr(0x516C) + chr(0x53F8)
_HAN_TAIL = chr(0x6D4B) + chr(0x8BD5)

Box = tuple[float, float, float, float]


class _Pages:
    """Builds a document of invented pages, block by block."""

    def __init__(self, engine: Loader, count: int) -> None:
        self.engine = engine
        self.schema = engine("marker.schema")
        page_class = engine("marker.schema.groups.page").PageGroup
        self.pages = []
        for page_id in range(count):
            page = page_class(
                polygon=self.box((0.0, 0.0, *_PAGE)), page_id=page_id, structure=[]
            )
            page.lowres_image = Image.new("RGB", (600, 800), "white")
            page.highres_image = Image.new("RGB", (600, 800), "white")
            self.pages.append(page)

    def box(self, box: Box) -> Any:
        return self.engine("marker.schema.polygon").PolygonBox.from_bbox(list(box))

    def block(self, page_id: int, kind: str, box: Box) -> Any:
        page = self.pages[page_id]
        block_type = self.schema.BlockTypes[kind]
        block_class = self.engine("marker.schema.registry").get_block_class(block_type)
        block = page.add_full_block(
            block_class(polygon=self.box(box), page_id=page_id, block_type=block_type)
        )
        page.add_structure(block)
        return block

    def lines(self, block: Any, lines: list[tuple[str, Box]]) -> Any:
        page = self.pages[block.page_id]
        line_class = self.engine("marker.schema.text.line").Line
        span_class = self.engine("marker.schema.text.span").Span
        for text, box in lines:
            line = page.add_full_block(
                line_class(polygon=self.box(box), page_id=block.page_id)
            )
            span = page.add_full_block(
                span_class(
                    text=text + "\n",
                    formats=["plain"],
                    polygon=self.box(box),
                    page_id=block.page_id,
                    font="Unknown",
                    font_weight=0,
                    font_size=0,
                    minimum_position=0,
                    maximum_position=0,
                )
            )
            line.add_structure(span)
            block.add_structure(line)
        return block

    def text(
        self, page_id: int, lines: list[tuple[str, Box]], kind: str = "Text"
    ) -> Any:
        x0 = min(box[0] for _, box in lines)
        y0 = min(box[1] for _, box in lines)
        x1 = max(box[2] for _, box in lines)
        y1 = max(box[3] for _, box in lines)
        return self.lines(self.block(page_id, kind, (x0, y0, x1, y1)), lines)

    def document(self) -> Any:
        return self.engine("marker.schema.document").Document(
            filepath="invented.pdf", pages=self.pages
        )


def _join(engine: Loader, pages: _Pages, *, paginate: bool = False) -> str:
    document = pages.document()
    engine("marker.processors.text").TextProcessor({})(document)
    renderer = engine("marker.renderers.markdown").MarkdownRenderer(
        {"paginate_output": paginate, "page_separator": "-" * 8}
    )
    return str(renderer(document).markdown).strip()


def _paragraphs(markdown: str) -> list[str]:
    return [part.strip() for part in markdown.split("\n\n") if part.strip()]


def _cut_by_a_figure(engine: Loader, second_line: str) -> _Pages:
    pages = _Pages(engine, 2)
    pages.text(
        0,
        [
            ("Each pump of the invented plant has one valve.", (50, 500, 550, 518)),
            ("The valve opens when the pressure in the", (50, 521, 300, 539)),
        ],
    )
    pages.block(0, "Picture", (50, 560, 550, 720))
    pages.text(0, [("Fig. 3. Pump circuit", (50, 730, 250, 748))], kind="Caption")
    pages.text(1, [(second_line, (50, 60, 400, 78))])
    return pages


def test_paragraph_cut_by_a_figure_and_a_page_reads_as_one(engine: Loader) -> None:
    pages = _cut_by_a_figure(engine, "chamber exceeds the spring force.")

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0] == (
        "Each pump of the invented plant has one valve. The valve opens when "
        "the pressure in the chamber exceeds the spring force."
    )
    assert paragraphs[1].startswith("![](")
    assert paragraphs[2] == "Fig. 3. Pump circuit"
    assert len(paragraphs) == 3


def test_sentence_end_and_capital_keep_two_paragraphs(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(
        0,
        [
            ("Each pump of the invented plant has one valve. The", (50, 500, 550, 518)),
            ("valve opens when the pressure rises.", (50, 521, 300, 539)),
        ],
    )
    pages.block(0, "Picture", (50, 560, 550, 720))
    pages.text(1, [("The spring closes it again.", (50, 60, 400, 78))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0].endswith("pressure rises.")
    assert paragraphs[1].startswith("![](")
    assert paragraphs[2] == "The spring closes it again."


def test_section_header_between_the_halves_stops_the_join(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pressure in the", (50, 700, 550, 718))])
    pages.text(1, [("Pump circuit", (50, 40, 200, 58))], kind="SectionHeader")
    pages.text(1, [("chamber exceeds the spring force.", (50, 70, 400, 88))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs == [
        "The valve opens when the pressure in the",
        "## Pump circuit",
        "chamber exceeds the spring force.",
    ]


def test_single_line_with_text_evidence_joins_across_a_page(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pressure in the", (50, 700, 300, 718))])
    pages.text(1, [("chamber exceeds the spring force.", (50, 600, 400, 618))])

    assert _join(engine, pages) == (
        "The valve opens when the pressure in the chamber exceeds the spring force."
    )


def test_hyphenated_word_joins_across_a_page(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pres-", (50, 700, 300, 718))])
    pages.text(1, [("sure in the chamber rises.", (50, 60, 400, 78))])

    assert (
        _join(engine, pages)
        == "The valve opens when the pressure in the chamber rises."
    )


def test_paginated_join_keeps_both_halves_before_the_page_break(
    engine: Loader,
) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pres-", (50, 700, 300, 718))])
    pages.text(1, [("sure in the chamber rises.", (50, 60, 400, 78))])
    pages.text(1, [("The spring closes it again.", (50, 90, 400, 108))])

    assert _paragraphs(_join(engine, pages, paginate=True)) == [
        "{0}--------",
        "The valve opens when the pressure in the chamber rises.",
        "{1}--------",
        "The spring closes it again.",
    ]


def test_single_line_without_text_evidence_stays_apart(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pressure in the", (50, 700, 550, 718))])
    pages.text(1, [("Chamber pressure exceeds the spring force.", (50, 60, 400, 78))])

    assert _paragraphs(_join(engine, pages)) == [
        "The valve opens when the pressure in the",
        "Chamber pressure exceeds the spring force.",
    ]


def test_indented_second_half_stays_apart(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pressure in the", (50, 700, 550, 718))])
    pages.text(
        1,
        [
            ("chamber exceeds the spring force, and", (80, 60, 550, 78)),
            ("the pump stops.", (50, 81, 200, 99)),
        ],
    )

    assert len(_paragraphs(_join(engine, pages))) == 2


@pytest.mark.parametrize("shift", [0.0, 0.25, 0.5, 0.75])
def test_frame_step_with_text_evidence_joins_wherever_the_block_stands(
    engine: Loader, shift: float
) -> None:
    pages = _Pages(engine, 2)
    pages.text(
        0,
        [
            (
                "The pump starts when the pressure in the tank falls below the",
                (112, 700, 550, 718),
            )
        ],
    )
    pages.text(
        1,
        [
            ("set value, and it stops when the tank", (112.75 + shift, 60, 550, 78)),
            ("is full.", (112 + shift, 81, 200, 99)),
        ],
    )

    assert _join(engine, pages) == (
        "The pump starts when the pressure in the tank falls below the set value, "
        "and it stops when the tank is full."
    )


def test_indent_of_a_few_percent_of_the_width_stays_apart(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pressure in the", (50, 700, 350, 718))])
    pages.text(
        1,
        [
            ("chamber exceeds the spring force, and", (59, 60, 350, 78)),
            ("the pump stops.", (50, 81, 200, 99)),
        ],
    )

    assert len(_paragraphs(_join(engine, pages))) == 2


@pytest.mark.parametrize(("offset", "count"), [(0.0, 1), (0.75, 2)])
def test_any_offset_without_text_evidence_is_an_indent(
    engine: Loader, offset: float, count: int
) -> None:
    pages = _Pages(engine, 2)
    pages.text(
        0,
        [
            ("The valve opens when the pressure in the", (50, 680, 550, 698)),
            ("chamber exceeds the force of the spring", (50, 701, 550, 719)),
        ],
    )
    pages.text(
        1,
        [
            ("Then the pump stops, and the valve", (50.25 + offset, 60, 550, 78)),
            ("closes again.", (50.25, 81, 200, 99)),
        ],
    )

    assert len(_paragraphs(_join(engine, pages))) == count


_STACK_FIRST: list[tuple[str, Box]] = [
    ("The valve opens when the signal reaches the", (50, 100, 550, 118)),
    ("controller, and it closes after", (50, 121, 300, 139)),
]
_STACK_SECOND = "a delay that the user sets in the menu."


def test_two_stacked_blocks_of_one_paragraph_read_as_one(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, _STACK_FIRST)
    pages.text(0, [(_STACK_SECOND, (50, 142, 400, 160))])

    assert _join(engine, pages) == (
        "The valve opens when the signal reaches the controller, and it closes "
        "after a delay that the user sets in the menu."
    )


def test_stacked_blocks_with_a_gap_of_a_line_stay_apart(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, _STACK_FIRST)
    pages.text(0, [(_STACK_SECOND, (50, 150, 400, 168))])

    assert len(_paragraphs(_join(engine, pages))) == 2


def test_stacked_blocks_without_text_evidence_stay_apart(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(
        0,
        [
            ("The valve opens when the signal reaches the", (50, 100, 550, 118)),
            ("controller, and it closes after a delay.", (50, 121, 550, 139)),
        ],
    )
    pages.text(0, [("The user sets the delay in the menu.", (50, 142, 400, 160))])

    assert len(_paragraphs(_join(engine, pages))) == 2


def test_indented_stacked_block_stays_apart(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, _STACK_FIRST)
    pages.text(
        0,
        [
            ("a delay that the user sets in the menu, and", (80, 142, 550, 160)),
            ("the pump stops.", (50, 163, 200, 181)),
        ],
    )

    assert len(_paragraphs(_join(engine, pages))) == 2


def test_stacked_blocks_with_a_small_overlap_stay_apart(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(
        0,
        [
            ("The valve opens when the signal", (50, 100, 300, 118)),
            ("reaches the controller, and it", (50, 121, 300, 139)),
        ],
    )
    pages.text(0, [("closes after a delay that the user sets.", (200, 142, 500, 160))])

    assert len(_paragraphs(_join(engine, pages))) == 2


def test_block_between_stacked_blocks_keeps_them_apart(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, _STACK_FIRST)
    ignored = pages.text(0, [("Running note without a stop", (560, 121, 590, 139))])
    ignored.ignore_for_output = True
    pages.text(0, [(_STACK_SECOND, (50, 142, 400, 160))])

    assert len(_paragraphs(_join(engine, pages))) == 2


@pytest.mark.parametrize(
    "item",
    [
        "2. valve according to claim 1, wherein the spring is steel.",
        "b) the pump stops when the tank is full.",
    ],
)
def test_stacked_block_that_opens_an_item_stays_apart(
    engine: Loader, item: str
) -> None:
    pages = _Pages(engine, 1)
    pages.text(
        0,
        [
            ("1. Valve with a spring and a seat, wherein the", (50, 100, 550, 118)),
            ("spring presses the seat against the", (50, 121, 300, 139)),
        ],
    )
    pages.text(0, [("housing", (50, 142, 120, 160))])
    pages.text(0, [(item, (50, 163, 500, 181))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[-1] == item
    assert len(paragraphs) == 2


def test_figure_in_one_column_cuts_the_paragraph(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, [("The valve opens when the pressure in the", (50, 100, 300, 118))])
    pages.block(0, "Picture", (50, 130, 550, 300))
    pages.text(0, [("chamber exceeds the spring force.", (50, 320, 400, 338))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0] == (
        "The valve opens when the pressure in the chamber exceeds the spring force."
    )
    assert paragraphs[1].startswith("![](")


def test_paragraph_over_three_pages_keeps_its_figures_after_it(
    engine: Loader,
) -> None:
    pages = _Pages(engine, 3)
    pages.text(0, [("The valve opens when the pressure in", (50, 700, 300, 718))])
    pages.block(0, "Picture", (50, 730, 550, 790))
    pages.text(1, [("the chamber exceeds the force of", (50, 60, 300, 78))])
    pages.text(1, [("Fig. 3. Pump circuit", (50, 760, 250, 778))], kind="Caption")
    pages.text(2, [("the spring, and the pump stops.", (50, 60, 400, 78))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0] == (
        "The valve opens when the pressure in the chamber exceeds the force of "
        "the spring, and the pump stops."
    )
    assert paragraphs[1].startswith("![](")
    assert paragraphs[2] == "Fig. 3. Pump circuit"
    assert len(paragraphs) == 3


# A first half that ends in a digit gives no text evidence, so the line
# frames decide.
_HAN_DIGIT_END = _HAN * 9 + "12"


def _cjk_pages(engine: Loader, last_line_end: float) -> _Pages:
    pages = _Pages(engine, 2)
    pages.text(
        0,
        [
            (_HAN * 10, (50, 680, 550, 698)),
            (_HAN_DIGIT_END, (50, 701, last_line_end, 719)),
        ],
    )
    pages.text(1, [(_HAN_TAIL * 5, (50, 60, 300, 78))])
    return pages


def test_cjk_paragraph_joins_by_geometry(engine: Loader) -> None:
    pages = _cjk_pages(engine, 550)

    paragraphs = _paragraphs(_join(engine, pages))

    assert len(paragraphs) == 1
    assert paragraphs[0].endswith(f"{_HAN_DIGIT_END} {_HAN_TAIL * 5}")


def test_cjk_block_read_as_a_whole_joins_by_its_detector_lines(
    engine: Loader,
) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [(_HAN * 10 + _HAN_DIGIT_END, (50, 680, 550, 719))])
    pages.pages[0].children[0].detected_line_polygons = [
        pages.box((50, 680, 550, 698)),
        pages.box((50, 701, 550, 719)),
    ]
    pages.text(1, [(_HAN_TAIL * 5, (50, 60, 300, 78))])

    assert _join(engine, pages) == f"{_HAN * 10}{_HAN_DIGIT_END} {_HAN_TAIL * 5}"


def test_cjk_paragraph_with_a_short_last_line_stays_apart(engine: Loader) -> None:
    pages = _cjk_pages(engine, 300)

    assert len(_paragraphs(_join(engine, pages))) == 2


def test_ignored_text_block_does_not_undo_a_join(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pressure in the", (50, 600, 300, 618))])
    pages.block(0, "Picture", (50, 630, 550, 700))
    ignored = pages.text(0, [("Running note without a stop", (50, 710, 300, 728))])
    ignored.ignore_for_output = True
    pages.text(1, [("chamber exceeds the spring force.", (50, 60, 400, 78))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0] == (
        "The valve opens when the pressure in the chamber exceeds the spring force."
    )
    assert paragraphs[1].startswith("![](")


def test_label_read_as_text_is_no_half(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("The valve opens when the pressure in the", (50, 600, 300, 618))])
    pages.text(0, [("Fig. 14", (50, 700, 120, 718))])
    pages.text(1, [("chamber exceeds the spring force.", (50, 60, 400, 78))])

    assert "Fig. 14" in _paragraphs(_join(engine, pages))


def test_label_with_a_formula_is_no_half(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("Probl. 2.43 \\theta > \\phi", (50, 700, 200, 718))])
    pages.text(1, [("the tension of the cable.", (50, 60, 400, 78))])

    assert len(_paragraphs(_join(engine, pages))) == 2


def test_sentence_that_opens_with_a_label_joins(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("Fig. 2 shows how the valve opens when the", (50, 700, 300, 718))])
    pages.text(1, [("chamber exceeds the spring force.", (50, 60, 400, 78))])

    assert _join(engine, pages) == (
        "Fig. 2 shows how the valve opens when the chamber exceeds the spring force."
    )


def test_repeated_footer_is_stepped_over(engine: Loader) -> None:
    footer = "Notes of an invented course (no rights reserved)"
    pages = _Pages(engine, 3)
    pages.text(0, [("The valve opens when the pressure in the", (50, 600, 300, 618))])
    pages.text(0, [(footer, (50, 760, 400, 778))])
    pages.text(1, [("chamber exceeds the spring force.", (50, 60, 400, 78))])
    pages.text(1, [(footer, (50, 760, 400, 778))])
    pages.text(2, [("The spring closes it again.", (50, 60, 400, 78))])
    pages.text(2, [(footer, (50, 760, 400, 778))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0] == (
        "The valve opens when the pressure in the chamber exceeds the spring force."
    )
    assert paragraphs.count(footer) == 3


_HAN_RUNNING = (_HAN_TAIL + _HAN) * 3


def test_running_line_without_spaces_is_stepped_over(engine: Loader) -> None:
    pages = _Pages(engine, 3)
    pages.text(
        0,
        [
            (_HAN * 10, (50, 680, 550, 698)),
            (_HAN * 10, (50, 701, 550, 719)),
        ],
    )
    for page_id in (1, 2):
        pages.text(page_id, [(_HAN_RUNNING, (50, 20, 300, 38))])
    pages.text(0, [(_HAN_RUNNING, (50, 760, 300, 778))])
    pages.text(1, [(_HAN_TAIL * 5, (50, 60, 300, 78))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0].endswith(_HAN * 10 + _HAN_TAIL * 5)
    assert paragraphs[1:] == [_HAN_RUNNING] * 3


@pytest.mark.parametrize(
    ("text", "page_count", "repeats"),
    [
        (_HAN_RUNNING[:11], 3, True),
        (_HAN_RUNNING[:10], 3, False),
        ("Part 3 notes", 3, True),
        ("Pump data:", 3, False),
        (_HAN_RUNNING, 2, False),
    ],
)
def test_repeated_text_needs_three_words_or_eleven_letters_on_three_pages(
    engine: Loader, text: str, page_count: int, repeats: bool
) -> None:
    pages = _Pages(engine, page_count)
    for page_id in range(page_count):
        pages.text(page_id, [(text, (50, 760, 300, 778))])
    processor = engine("marker.processors.text").TextProcessor({})

    assert (text in processor.find_repeated_texts(pages.document())) is repeats


def test_german_closing_quote_ends_the_sentence(engine: Loader) -> None:
    opening = chr(0x201E)
    closing = chr(0x201C)
    pages = _Pages(engine, 2)
    pages.text(0, [(f"He said {opening}Stop.{closing}", (50, 700, 300, 718))])
    pages.text(1, [("ebay is a name.", (50, 600, 400, 618))])

    assert len(_paragraphs(_join(engine, pages))) == 2


_FULLWIDTH_COMMA = chr(0xFF0C)
_PUMP_FIRST = f"每台水泵都有一个阀门。该泵在水箱压力低于设定值时启动{_FULLWIDTH_COMMA}"
_PUMP_SECOND = f"并在水箱满时停止{_FULLWIDTH_COMMA}然后等待下一个信号。"


def _caseless_pair(engine: Loader, first: str, second: str) -> _Pages:
    pages = _Pages(engine, 2)
    pages.text(0, [(first, (50, 700, 550, 718))])
    pages.text(1, [(second, (50, 60, 400, 78))])
    return pages


def test_caseless_paragraph_cut_by_a_page_reads_as_one(engine: Loader) -> None:
    pages = _caseless_pair(engine, _PUMP_FIRST, _PUMP_SECOND)

    assert _join(engine, pages) == _PUMP_FIRST + _PUMP_SECOND


def test_caseless_paragraph_cut_by_a_column_reads_as_one(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, [(_PUMP_FIRST, (50, 700, 290, 718))])
    pages.text(0, [(_PUMP_SECOND, (310, 60, 550, 78))])

    assert _join(engine, pages) == _PUMP_FIRST + _PUMP_SECOND


def test_caseless_stacked_blocks_stay_apart(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, [(_PUMP_FIRST, (50, 100, 550, 118))])
    pages.text(0, [(_PUMP_SECOND, (50, 121, 400, 139))])

    assert len(_paragraphs(_join(engine, pages))) == 2


def test_caseless_paragraph_cut_by_a_figure_stays_apart(engine: Loader) -> None:
    pages = _Pages(engine, 1)
    pages.text(0, [(_PUMP_FIRST, (50, 100, 550, 118))])
    pages.block(0, "Picture", (50, 130, 550, 300))
    pages.text(0, [(_PUMP_SECOND, (50, 320, 400, 338))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert _PUMP_FIRST in paragraphs
    assert _PUMP_SECOND in paragraphs


@pytest.mark.parametrize(("offset", "count"), [(1.0, 1), (20.0, 2)])
def test_caseless_second_half_keeps_the_indent_tolerance(
    engine: Loader, offset: float, count: int
) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [(_PUMP_FIRST, (50, 700, 550, 718))])
    pages.text(
        1,
        [
            ("并在水箱满时停止" + _FULLWIDTH_COMMA, (50 + offset, 60, 550, 78)),
            ("然后等待下一个信号。", (50, 81, 300, 99)),
        ],
    )

    assert len(_paragraphs(_join(engine, pages))) == count


def test_caseless_running_line_between_the_halves_is_no_half(
    engine: Loader,
) -> None:
    running = "水泵维护手册第三版内部资料仅供培训人员使用"
    pages = _Pages(engine, 3)
    pages.text(0, [(_PUMP_FIRST, (50, 600, 550, 618))])
    pages.text(0, [(running, (50, 760, 400, 778))])
    pages.text(1, [(running, (50, 20, 400, 38))])
    pages.text(1, [(_PUMP_SECOND, (50, 60, 400, 78))])
    pages.text(2, [(running, (50, 20, 400, 38))])

    paragraphs = _paragraphs(_join(engine, pages))

    assert paragraphs[0] == _PUMP_FIRST + _PUMP_SECOND
    assert paragraphs[1:] == [running] * 3
