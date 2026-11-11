"""A paragraph cut by a page, a column, or a figure reads as one paragraph."""

from __future__ import annotations

from typing import Any

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


def test_item_letter_is_no_continuation(engine: Loader) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [("Table 4. Belt properties", (50, 700, 300, 718))])
    pages.text(1, [("b) Elongation as a decimal:", (50, 60, 400, 78))])

    assert _paragraphs(_join(engine, pages)) == [
        "Table 4. Belt properties",
        "b) Elongation as a decimal:",
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


def _cjk_pages(engine: Loader, last_line_end: float) -> _Pages:
    pages = _Pages(engine, 2)
    pages.text(
        0,
        [
            (_HAN * 10, (50, 680, 550, 698)),
            (_HAN * 10, (50, 701, last_line_end, 719)),
        ],
    )
    pages.text(1, [(_HAN_TAIL * 5, (50, 60, 300, 78))])
    return pages


def test_cjk_paragraph_joins_by_geometry(engine: Loader) -> None:
    pages = _cjk_pages(engine, 550)

    paragraphs = _paragraphs(_join(engine, pages))

    assert len(paragraphs) == 1
    assert paragraphs[0].endswith(_HAN * 10 + _HAN_TAIL * 5)


def test_cjk_block_read_as_a_whole_joins_by_its_detector_lines(
    engine: Loader,
) -> None:
    pages = _Pages(engine, 2)
    pages.text(0, [(_HAN * 20, (50, 680, 550, 719))])
    pages.pages[0].children[0].detected_line_polygons = [
        pages.box((50, 680, 550, 698)),
        pages.box((50, 701, 550, 719)),
    ]
    pages.text(1, [(_HAN_TAIL * 5, (50, 60, 300, 78))])

    assert _join(engine, pages) == _HAN * 20 + _HAN_TAIL * 5


def test_cjk_paragraph_with_a_short_last_line_stays_apart(engine: Loader) -> None:
    pages = _cjk_pages(engine, 300)

    assert len(_paragraphs(_join(engine, pages))) == 2
