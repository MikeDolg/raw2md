"""A link inside the document leaves no anchor, and a web link stays."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fpdf import FPDF

from ._helpers import Loader

_LINE = "See section two and the site here."
_INNER = "section two"
_WEB = "the site"
_URL = "https://example.com/"


def _linked_pdf(path: Path, *, goto_action: bool) -> None:
    """Write a page with an inner link and a web link, and a target page."""
    pdf = FPDF(unit="pt", format="A4")
    pdf.add_page()
    pdf.set_font("helvetica", size=10)
    pdf.text(100, 100, _LINE)

    def link(text: str, target: int | str) -> None:
        start = pdf.get_string_width(_LINE[: _LINE.index(text)])
        pdf.link(100 + start, 90, pdf.get_string_width(text), 12, target)

    link(_INNER, pdf.add_link(page=2))
    link(_WEB, _URL)
    pdf.add_page()
    pdf.text(100, 100, "Section two")
    data = bytes(pdf.output())
    if goto_action:
        # The same target as a GoTo action instead of a destination.
        data, count = re.subn(rb"/Dest (\[[^\]]*\])", rb"/A <</S /GoTo /D \1>>", data)
        assert count == 1
    path.write_bytes(data)


def _spans(engine: Loader, path: Path) -> list[dict[str, Any]]:
    pages = engine("pdftext.extraction").dictionary_output(str(path))
    return [
        span
        for block in pages[0]["blocks"]
        for line in block["lines"]
        for span in line["spans"]
    ]


@pytest.mark.parametrize("goto_action", [False, True])
def test_inner_link_is_dropped(
    engine: Loader, tmp_path: Path, goto_action: bool
) -> None:
    path = tmp_path / "links.pdf"
    _linked_pdf(path, goto_action=goto_action)
    spans = _spans(engine, path)
    assert [(s["text"], s["url"]) for s in spans] == [
        ("See section two and ", ""),
        (_WEB, _URL),
        (" here.", ""),
    ]


def test_span_id_leaves_no_anchor(engine: Loader) -> None:
    renderer = engine("marker.renderers.markdown").MarkdownRenderer()
    html = "<p><span id='page-1-0'></span>Intro <span id='x'>text</span></p>"
    assert str(renderer.md_cls.convert(html)).strip() == "Intro text"
