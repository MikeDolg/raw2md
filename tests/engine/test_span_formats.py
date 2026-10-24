"""A span applies every one of its formats, with math innermost."""

from __future__ import annotations

import pytest

from ._helpers import Loader


def _span_html(engine: Loader, text: str, formats: list[str]) -> str:
    span_class = engine("marker.schema.text.span").Span
    polygon = engine("marker.schema.polygon").PolygonBox.from_bbox([0, 0, 10, 10])
    span = span_class(
        text=text,
        formats=formats,
        polygon=polygon,
        font="Unknown",
        font_weight=0,
        font_size=0,
        minimum_position=0,
        maximum_position=0,
    )
    return str(span.assemble_html(None, [], [], None))


def _markdown(engine: Loader, html: str) -> str:
    renderers = engine("marker.renderers")
    html = renderers.BaseRenderer.merge_consecutive_tags(html, "b")
    html = renderers.BaseRenderer.merge_consecutive_tags(html, "i")
    renderer = engine("marker.renderers.markdown").MarkdownRenderer()
    markdown = str(renderer.md_cls.convert(f"<p>Let {html} be.</p>"))
    # The converter pads inline math with spaces, and the test ignores them.
    return " ".join(markdown.split())


@pytest.mark.parametrize(
    ("text", "formats", "html", "markdown"),
    [
        (
            "x^{2}+1",
            ["plain", "bold", "math"],
            "<b><math display='inline'>x^{2}+1</math></b>",
            "**$x^{2}+1$**",
        ),
        ("word", ["plain", "bold", "italic"], "<b><i>word</i></b>", "***word***"),
        (
            "x^{2}",
            ["italic", "math"],
            "<i><math display='inline'>x^{2}</math></i>",
            "*$x^{2}$*",
        ),
        (
            "x^{2}",
            ["bold", "italic", "math"],
            "<b><i><math display='inline'>x^{2}</math></i></b>",
            "***$x^{2}$***",
        ),
        ("word", ["plain", "bold"], "<b>word</b>", "**word**"),
        ("word", ["italic"], "<i>word</i>", "*word*"),
        ("x^{2}", ["math"], "<math display='inline'>x^{2}</math>", "$x^{2}$"),
    ],
)
def test_span_keeps_every_format(
    engine: Loader, text: str, formats: list[str], html: str, markdown: str
) -> None:
    assembled = _span_html(engine, text, formats)
    assert assembled == html
    assert markdown in _markdown(engine, assembled)


def test_bold_text_and_bold_math_form_one_run(engine: Loader) -> None:
    html = _span_html(engine, "Bound ", ["plain", "bold"]) + _span_html(
        engine, "x^{2}", ["plain", "bold", "math"]
    )
    assert "**Bound $x^{2}$**" in _markdown(engine, html)
