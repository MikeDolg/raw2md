"""A line end joins a word at a hyphen, and it keeps a dash."""

from __future__ import annotations

import pytest

from ._helpers import Loader


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("the rod -", "the rod "),
        ("the rod¬", "the rod"),
        ("the rod —", "the rod —"),
        ("the rod—", "the rod—"),
    ],
)
def test_only_a_hyphen_is_removed_before_a_lowercase_line(
    engine: Loader, line: str, expected: str
) -> None:
    strip = engine("marker.schema.text.line").strip_trailing_hyphens
    assert strip(line, "and the plate", line) == expected
