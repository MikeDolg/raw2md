"""A backslash at the end of math does not escape the closing delimiter."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from ._helpers import Loader


def _render(engine: Loader, html: str) -> str:
    markdownify = engine("marker.renderers.markdown").Markdownify(
        paginate_output=False,
        page_separator="-" * 48,
        inline_math_delimiters=("$", "$"),
        block_math_delimiters=("$$", "$$"),
        html_tables_in_markdown=False,
    )
    math = BeautifulSoup(html, "html.parser").find("math")
    assert math is not None
    return str(markdownify.convert_math(math, math.text, []))


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (r"<math>E = mc^2 \ </math>", r" $E = mc^2 \ $ "),
        (r"<math>x \\ </math>", r" $x \\$ "),
        (r"<math>x^2 </math>", " $x^2$ "),
        (r'<math display="block">a \ </math>', "\n$$a \\ $$\n"),
    ],
)
def test_trailing_backslash(engine: Loader, html: str, expected: str) -> None:
    assert _render(engine, html) == expected
