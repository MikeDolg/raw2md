"""A column of dollar signs joins the value beside it and leaves the table."""

from __future__ import annotations

from raw2md.cleaning import join_dollar_columns
from raw2md.mdtext.zones import segments


def _run(text: str) -> list[str]:
    return [line for line, _ in join_dollar_columns(segments(text))]


def test_the_sign_precedes_the_next_value_and_the_column_goes() -> None:
    text = "| Item |  | Price |\n|---|---|---|\n| a | \\$ | 120 |\n| b | \\$ | 45 |\n"
    assert _run(text) == [
        "| Item | Price |",
        "|---|---|",
        "| a | \\$120 |",
        "| b | \\$45 |",
    ]


def test_an_empty_cell_beside_the_value_keeps_the_row_without_a_sign() -> None:
    text = "| A |  | B |\n|---|---|---|\n| a | $ | 1 |\n| b |  | 2 |\n"
    assert _run(text) == [
        "| A | B |",
        "|---|---|",
        "| a | $1 |",
        "| b | 2 |",
    ]


def test_the_last_column_stays() -> None:
    text = "| A | B |\n|---|---|\n| a | $ |\n| b | $ |\n"
    assert _run(text) == text.splitlines()


def test_a_header_only_table_stays() -> None:
    text = "| $ | B |\n|---|---|\n"
    assert _run(text) == text.splitlines()


def test_a_column_with_other_text_stays() -> None:
    text = "| A | B |\n|---|---|\n| $ | 1 |\n| x | 2 |\n"
    assert _run(text) == text.splitlines()


def test_a_sign_beside_an_empty_cell_stays() -> None:
    text = "| A | B |\n|---|---|\n| $ | 1 |\n| $ |  |\n"
    assert _run(text) == text.splitlines()


def test_a_row_off_the_header_width_stays() -> None:
    text = "| A | B | C |\n|---|---|---|\n| $ | 1 |\n| $ | 2 | 3 |\n"
    assert _run(text) == text.splitlines()


def test_an_html_table_stays() -> None:
    text = "<table><tr><td>$</td><td>1</td></tr><tr><td>$</td><td>2</td></tr></table>\n"
    assert join_dollar_columns(segments(text)) == segments(text)


def test_the_pass_is_idempotent() -> None:
    text = "| A |  | B |\n|---|---|---|\n| a | $ | 1 |\n| b | $ | 2 |\n"
    once = join_dollar_columns(segments(text))
    assert join_dollar_columns(once) == once


def test_an_empty_column_leaves_with_no_sign_to_move() -> None:
    text = "| A |  | B |\n|---|---|---|\n| a |  | 1 |\n| b |  | 2 |\n"
    assert _run(text) == [
        "| A | B |",
        "|---|---|",
        "| a | 1 |",
        "| b | 2 |",
    ]


def test_an_empty_last_column_stays() -> None:
    text = "| A | B |\n|---|---|\n| a |  |\n| b |  |\n"
    assert _run(text) == text.splitlines()
