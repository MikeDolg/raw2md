"""The Markdown output keeps the HTML that the renderer converted."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ._helpers import Loader


def test_output_holds_converted_html(
    engine: Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = engine("marker.renderers.markdown")
    html = "<h2>Title</h2><p>Body text</p>"
    document = SimpleNamespace(render=lambda config: object())
    monkeypatch.setattr(
        module.MarkdownRenderer, "extract_html", lambda *args: (html, {})
    )
    monkeypatch.setattr(
        module.MarkdownRenderer, "generate_document_metadata", lambda *args: {}
    )

    output = module.MarkdownRenderer()(document)

    assert output.html == html
    assert output.markdown == "## Title\n\nBody text"
