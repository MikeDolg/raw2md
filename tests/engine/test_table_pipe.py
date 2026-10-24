"""A vertical bar inside a table cell is escaped and keeps its place."""

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
    table = BeautifulSoup(html, "html.parser").find("table")
    return str(markdownify.convert_table(table, "", []))


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("<math>|x|</math>", r"$\|x\|$"),
        (r"<math>\|x\|</math>", r"$\|x\|$"),
        ("a | b", r"a \| b"),
    ],
)
def test_pipe_in_a_cell_is_escaped(engine: Loader, cell: str, expected: str) -> None:
    html = f"<table><tr><td>{cell}</td><td>y</td></tr></table>"
    rows = [line for line in _render(engine, html).splitlines() if line]
    assert expected in rows[0]
    assert rows[0].replace(expected, "").count("|") == 3
