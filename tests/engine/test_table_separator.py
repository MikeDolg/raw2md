"""A table gets exactly one separator line under its first row."""

from __future__ import annotations

import pytest

from ._helpers import Loader
from .test_table_pipe import _render


@pytest.mark.parametrize("rows", [1, 2, 3])
def test_one_separator_line(engine: Loader, rows: int) -> None:
    body = "<tr><td>a</td><td>b</td></tr>" * rows
    lines = [
        line for line in _render(engine, f"<table>{body}</table>").splitlines() if line
    ]
    assert len(lines) == rows + 1
    assert lines[1].replace("-", "").replace("|", "") == ""
    assert sum(1 for line in lines if set(line) <= {"|", "-"}) == 1
