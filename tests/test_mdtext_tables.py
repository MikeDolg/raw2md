"""The number form that the table rules of the engine and the cleaning share."""

from __future__ import annotations

import pytest

from raw2md.mdtext.tables import is_number_value, table_column_values


@pytest.mark.parametrize(
    "text",
    [
        "12",
        "-1,250.50",
        ".690",
        "(12.4)",
        "15 %",
        "15%",
        "12 g",
        "40 mm",
        "9.81 m/s2",
        "$ 120",
        "€5",
        chr(0x2212) + "3.2",
        "17" + chr(0x2009) + "440",
        "±0.5",
        "20 °C",
    ],
)
def test_a_number_with_its_sign_and_unit_is_a_number(text: str) -> None:
    assert is_number_value(text)


@pytest.mark.parametrize(
    "text", ["", "abc", "see note", "12-14", "1/2", "**12**", "(12.4", "n/a", "."]
)
def test_text_and_ranges_are_not_numbers(text: str) -> None:
    assert not is_number_value(text)


@pytest.mark.parametrize("text", ["-", "/", "*", "_"])
def test_a_placeholder_counts_only_with_its_flag(text: str) -> None:
    assert not is_number_value(text)
    assert is_number_value(text, placeholder=True)


def test_a_column_value_flattens_its_breaks_and_padding() -> None:
    rows = ["| Pin |  12<br>14  |", "| Bolt | |", "| Nut | 9 |", "| a | b | c |"]

    assert table_column_values(rows, 2) == (
        frozenset({"Pin", "Nut"}),
        frozenset({"12 14", "9"}),
    )


def test_a_repeated_header_is_no_column_value() -> None:
    rows = ["| Item | Count |", "| Pin | 4 |"]

    assert table_column_values(rows, 2, header="| item |  COUNT |") == (
        frozenset({"Pin"}),
        frozenset({"4"}),
    )
