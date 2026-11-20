"""A heading keeps its bold markup; the cleaning stage removes it."""

from __future__ import annotations

import pytest

from ._helpers import Loader


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<h2><b>1.2 Foo</b></h2>", "## **1.2 Foo**"),
        ("<h3><b>1.2 </b><i>x</i></h3>", "### **1.2** *x*"),
        ("<h2><b><i>Name</i></b></h2>", "## ***Name***"),
        ("<h1><strong>Title</strong></h1>", "# **Title**"),
        ("<h2>Plain <b>part</b> of it</h2>", "## Plain **part** of it"),
    ],
)
def test_heading_keeps_bold(engine: Loader, html: str, expected: str) -> None:
    renderer = engine("marker.renderers.markdown").MarkdownRenderer()
    markdown = str(renderer.md_cls.convert(html))
    assert markdown.strip() == expected
