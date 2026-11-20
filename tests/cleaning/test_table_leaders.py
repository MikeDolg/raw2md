"""Dot leaders leave a table cell, and the symbols inside a value stay."""

from __future__ import annotations

import pytest

from raw2md.cleaning import drop_cell_leaders
from raw2md.mdtext.zones import segments


def _row(cell: str) -> str:
    text = f"| Item | Value |\n|---|---|\n| a | {cell} |\n"
    result = drop_cell_leaders(segments(text))
    return result[2][0].split("|")[2].strip()


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1...10", "1...10"),
        ("-.25", "-.25"),
        ("6--8 mm", "6--8 mm"),
        ("Name ........", "Name"),
        ("Name . . . . 5", "Name 5"),
        ("---- 4", "---- 4"),
        ("12 ____", "12"),
        ("Item......7", "Item7"),
        ("Item . . . . 7", "Item 7"),
        (r"12 \_\_\_\_", "12"),
        (r"1\_\_5", r"1\_\_5"),
        ("Name ....<br>Other", "Name<br>Other"),
        ("....<br>Other", "Other"),
        ("Brig.-Gen. Smith", "Brig.-Gen. Smith"),
        ("Etc... Smith", "Etc... Smith"),
        ("Maj.-Gen.. C.", "Maj.-Gen.. C."),
        ("Item . . 7", "Item 7"),
        (". .", ""),
        ("$a --b$ . . .", "$a --b$"),
        ("<!-- -->", "<!-- -->"),
        ("1 ... 2", "1 ... 2"),
        ("1 ........ 2", "1 2"),
        ("No. 2 . . . 64", "No. 2 64"),
        ("0 ... 90", "0 ... 90"),
        ("a. … b", "a. … b"),
        ("Name …… 5", "Name 5"),
    ],
)
def test_leaders_are_removed_only_between_values(cell: str, expected: str) -> None:
    assert _row(cell) == expected


def test_the_separator_row_and_an_html_table_stay() -> None:
    table = "<table><tr><td>a ....</td></tr></table>\n"
    text = f"| A | B |\n|---|---|\n| x | y |\n\n{table}"
    result = drop_cell_leaders(segments(text))
    assert result == segments(text)


def test_the_pass_is_idempotent() -> None:
    text = "| A | B |\n|---|---|\n| x ....5 | y . . . |\n"
    once = drop_cell_leaders(segments(text))
    assert drop_cell_leaders(once) == once
