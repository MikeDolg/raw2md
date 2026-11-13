"""A paragraph without continuation ends without a space."""

from __future__ import annotations

import pytest

from ._helpers import Loader


def _convert(engine: Loader, html: str) -> str:
    renderer = engine("marker.renderers.markdown").MarkdownRenderer()
    return str(renderer.md_cls.convert(html))


@pytest.mark.parametrize("kind", ["Caption", "Text", "Equation"])
def test_last_italic_span_leaves_no_space(engine: Loader, kind: str) -> None:
    html = f"<p block-type='{kind}'>See <i>Tab. 3 </i></p><p block-type='Text'>Next</p>"

    assert "See *Tab. 3*\n\nNext" in _convert(engine, html)


def test_continued_paragraph_keeps_its_space(engine: Loader) -> None:
    html = (
        "<p block-type='Text' class='has-continuation'>The valve opens when</p>"
        "<p block-type='Text'>the pressure rises.</p>"
    )

    assert "The valve opens when the pressure rises." in _convert(engine, html)
