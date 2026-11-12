"""An equation block keeps its text: a paragraph, a run of formulas, or a line."""

from __future__ import annotations

from typing import Any

import pytest

from ._helpers import Loader


def _processor(engine: Loader) -> Any:
    return engine("marker.processors.equation").EquationProcessor(None)


def _markdown(engine: Loader, html: str) -> str:
    renderer = engine("marker.renderers.markdown")
    markdownify = renderer.Markdownify(
        paginate_output=False,
        page_separator="-" * 48,
        heading_style="ATX",
        bullets="-",
        escape_misc=False,
        escape_underscores=True,
        escape_asterisks=True,
        escape_dollars=True,
        sub_symbol="<sub>",
        sup_symbol="<sup>",
        inline_math_delimiters=("$", "$"),
        block_math_delimiters=("$$", "$$"),
        html_tables_in_markdown=False,
    )
    block = f"<p block-type='Equation'>{html}</p>"
    return str(renderer.cleanup_text(markdownify.convert(block)))


def _lines(engine: Loader, prediction: str) -> list[str]:
    html = _processor(engine).fix_latex(prediction)
    return _markdown(engine, html).split("\n")


def test_text_without_math_stays_a_paragraph(engine: Loader) -> None:
    html = _processor(engine).fix_latex("<b>Answer.</b> The rod<br>is at rest.")
    assert "<math" not in html
    assert _markdown(engine, html) == "**Answer.** The rod is at rest."


def test_text_without_math_stays_escaped(engine: Loader) -> None:
    html = _processor(engine).fix_latex("Load &lt; 5 kN &amp; more")
    assert html == "Load &lt; 5 kN &amp; more"


def test_empty_prediction_gives_no_html(engine: Loader) -> None:
    assert _processor(engine).fix_latex("  ") == ""


def test_formulas_with_a_comma_are_display_formulas(engine: Loader) -> None:
    lines = _lines(engine, "<math>x = 1</math>, <math>y = 2</math>.")
    assert lines == ["$$x = 1$$", ",", "$$y = 2$$", "."]


def test_number_follows_its_formula(engine: Loader) -> None:
    lines = _lines(engine, "<math>a = b</math> (1) <math>c = d</math> (2.3)")
    assert lines == ["$$a = b$$", "(1)", "$$c = d$$", "(2.3)"]


def test_words_make_a_line_with_inline_math(engine: Loader) -> None:
    prediction = 'Answer <math display="block">x = 1</math> m; <math>y = 2</math> s.'
    html = _processor(engine).fix_latex(prediction)
    assert 'display="block"' not in html
    words = _markdown(engine, html).split()
    assert words == ["Answer", "$x", "=", "1$", "m;", "$y", "=", "2$", "s."]


def test_line_that_ends_in_math_ends_without_a_space(engine: Loader) -> None:
    html = _processor(engine).fix_latex("Rest at <math>t = 0</math>")
    html += "</p><p block-type='Text'>Next"
    assert _markdown(engine, html).endswith("$t = 0$\n\nNext")


@pytest.mark.parametrize("word", ["kgf", chr(0x0434) + chr(0x0430)])
def test_a_word_of_any_script_makes_a_line(engine: Loader, word: str) -> None:
    html = _processor(engine).fix_latex(f"<math>a</math> {word} <math>b</math>")
    assert "display" not in html


def test_single_letter_outside_math_keeps_formulas(engine: Loader) -> None:
    html = _processor(engine).fix_latex("<math>a = 1</math> x <math>b = 2</math>")
    assert html.count('display="block"') == 2


def test_math_keeps_a_command_that_opens_with_n(engine: Loader) -> None:
    html = _processor(engine).fix_latex(r"<math>\nabla f = 0\n</math>")
    assert html == r'<math display="block">\nabla f = 0</math>'


def test_text_layer_wins_over_text_without_math(engine: Loader) -> None:
    processor = _processor(engine)
    assert processor.block_html("Rest is 5 N.", "Rest is 5 N.\n") == ""
    assert processor.block_html("Rest is 5 N.", "") == "Rest is 5 N."
    assert processor.block_html("<math>x</math>", "x\n") == (
        '<math display="block">x</math>'
    )
