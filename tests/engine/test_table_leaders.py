"""Dot leaders leave a table cell, and the symbols inside a value stay."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ._helpers import Loader


def _finalize(engine: Loader, text: str) -> list[str]:
    processor = engine("marker.processors.table").TableProcessor
    cell = SimpleNamespace(text_lines=[{"text": text}])
    return list(processor.finalize_cell_text(object.__new__(processor), cell))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1...10", "1...10"),
        ("-.25", "-.25"),
        ("6--8 mm", "6--8 mm"),
        ("Name ........", "Name"),
        ("Name . . . . 5", "Name 5"),
        ("--- 4", " 4"),
        ("12 ___", "12"),
        ("Item......7", "Item7"),
        ("Item . . . 7", "Item 7"),
    ],
)
def test_leaders_are_removed_only_between_values(
    engine: Loader, text: str, expected: str
) -> None:
    assert _finalize(engine, text) == [expected]
