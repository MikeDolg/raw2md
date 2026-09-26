"""Tests for the acceptance pass over what inspection wrote.

The pass is deterministic and reads only the body and the touched lines.
"""

from __future__ import annotations

from raw2md.llm.acceptance import TouchedLines, accept

# The soft hyphen a typeset break leaves in a text layer, spelled out because
# it is invisible.
SOFT_HYPHEN = "­"


def test_a_soft_hyphen_an_edit_wrote_is_stripped() -> None:
    body = f"The pump sra{SOFT_HYPHEN}ba{SOFT_HYPHEN}tyvaet under load.\n"

    result = accept(body, TouchedLines(edited=frozenset({0})))

    assert result.body == "The pump srabatyvaet under load.\n"
    assert (result.stripped, result.flagged) == (1, 0)
    assert result.changed


def test_trailing_space_of_an_edited_line_goes_with_it() -> None:
    body = "The pump runs.   \n"

    result = accept(body, TouchedLines(edited=frozenset({0})))

    assert result.body == "The pump runs.\n"
    assert result.stripped == 1


def test_a_line_no_edit_touched_keeps_its_characters() -> None:
    body = f"Line one has a soft{SOFT_HYPHEN}hyphen.\nLine two was edited.\n"

    result = accept(body, TouchedLines(edited=frozenset({1})))

    # The pass answers only for what inspection wrote.
    assert result.body == body
    assert not result.changed


def test_an_edited_line_inside_a_fence_is_left_verbatim() -> None:
    body = f"```\ncode with a soft{SOFT_HYPHEN}hyphen\n```\n"

    result = accept(body, TouchedLines(edited=frozenset({1})))

    # A replacement can open a fence, and a line inside one is verbatim.
    assert result.body == body
    assert result.stripped == 0


def test_a_line_the_cleaner_left_alone_stays_as_it_stands() -> None:
    body = "A comment line.\nThe pressure is measured hourly.\n"

    result = accept(body, TouchedLines(edited=frozenset({1})))

    assert result.body == body
    assert not result.changed


def test_a_row_an_edit_left_off_its_width_is_reported() -> None:
    body = "| Seal | Width | Depth |\n|---|---|---|\n| A | 3.5 | 1.0 |\n| B | 4.0 |\n"

    result = accept(body, TouchedLines(edited=frozenset({3})))

    assert result.body == body
    assert (result.flagged, result.stripped) == (1, 0)


def test_a_row_an_edit_crushed_into_one_cell_is_reported() -> None:
    # Only the grid reading sees this row.
    body = (
        "| Seal | Width | Depth |\n"
        "|---|---|---|\n"
        "| A | 3.5 | 1.0 |\n"
        "|  |  | B<br>4.0<br>1.5 |\n"
    )

    result = accept(body, TouchedLines(edited=frozenset({3})))

    assert result.body == body
    assert (result.flagged, result.stripped) == (1, 0)


def test_a_row_off_its_width_in_an_untouched_block_is_left_alone() -> None:
    body = (
        "| Seal | Width | Depth |\n"
        "|---|---|---|\n"
        "| A | 3.5 | 1.0 |\n"
        "| B | 4.0 |\n"
        "\n"
        "The seal is measured cold.\n"
    )

    result = accept(body, TouchedLines(edited=frozenset({5})))

    # That table is the cleaning stage's verdict.
    assert result.body == body
    assert result.flagged == 0


def test_one_count_for_two_rows_off_the_same_width() -> None:
    body = "| Seal | Width | Depth |\n|---|---|---|\n| A | 3.5 |\n| B | 4.0 |\n"

    result = accept(body, TouchedLines(edited=frozenset({2, 3})))

    # The defect counts once per table.
    assert result.body == body
    assert result.flagged == 1


def test_a_pipe_block_an_edit_wrote_gets_its_delimiter_row() -> None:
    # A crushed page rebuilt as rows with no delimiter row above them.
    body = "| Seal | Width |\n| A | 3.5 |\n| B | 4.0 |\n"

    result = accept(body, TouchedLines(edited=frozenset({0, 1, 2})))

    assert result.body == "| Seal | Width |\n|---|---|\n| A | 3.5 |\n| B | 4.0 |\n"
    assert (result.mended, result.stripped) == (1, 0)
    assert result.changed


def test_a_pipe_block_an_edit_wrote_joins_the_table_above_it() -> None:
    body = "| Seal | Width |\n|---|---|\n| A | 3.5 |\n\n| B | 4.0 |\n| C | 4.5 |\n"

    result = accept(body, TouchedLines(edited=frozenset({4, 5})))

    # A table above at the block's width takes the rows as its continuation.
    assert result.body == (
        "| Seal | Width |\n|---|---|\n| A | 3.5 |\n| B | 4.0 |\n| C | 4.5 |\n"
    )
    assert result.mended == 1


def test_a_delimiterless_block_no_edit_touched_is_left_alone() -> None:
    body = "| A | 3.5 |\n| B | 4.0 |\n\nThe seal is measured cold.\n"

    result = accept(body, TouchedLines(edited=frozenset({3})))

    assert result.body == body
    assert result.mended == 0


def test_a_delimiterless_block_above_an_edited_one_is_left_alone() -> None:
    body = "| A | 3.5 |\n| B | 4.0 |\n\n| C | 4.5 |\n| D | 5.0 |\n"

    result = accept(body, TouchedLines(edited=frozenset({3, 4})))

    # The block above declares no width, so it is not repaired on the way.
    assert result.body == (
        "| A | 3.5 |\n| B | 4.0 |\n\n| C | 4.5 |\n|---|---|\n| D | 5.0 |\n"
    )
    assert result.mended == 1


def test_a_delimiterless_block_below_an_edited_blank_line_is_left_alone() -> None:
    body = "| A | 3.5 |\n| B | 4.0 |\n\n| C | 4.5 |\n| D | 5.0 |\n"

    result = accept(body, TouchedLines(edited=frozenset({0, 1, 2})))

    # A blank line closing a replacement belongs to no block.
    assert result.body == (
        "| A | 3.5 |\n|---|---|\n| B | 4.0 |\n\n| C | 4.5 |\n| D | 5.0 |\n"
    )
    assert result.mended == 1


def test_two_edited_blocks_are_mended_after_the_indices_they_shift() -> None:
    body = (
        "| Seal | Width |\n"
        "| A | 3.5 |\n"
        "\n"
        "The seal is measured cold.\n"
        "\n"
        "| Bore | Depth |\n"
        "| B | 4.0 |\n"
    )

    result = accept(body, TouchedLines(edited=frozenset({0, 1, 5, 6})))

    # The first insertion shifts the lines below it.
    assert result.body == (
        "| Seal | Width |\n"
        "|---|---|\n"
        "| A | 3.5 |\n"
        "\n"
        "The seal is measured cold.\n"
        "\n"
        "| Bore | Depth |\n"
        "|---|---|\n"
        "| B | 4.0 |\n"
    )
    assert result.mended == 2


def test_a_strip_and_a_mend_meet_on_one_block() -> None:
    body = f"| Se{SOFT_HYPHEN}al | Width |\n| A | 3.5 |\n"

    result = accept(body, TouchedLines(edited=frozenset({0, 1})))

    # The mend runs on lines the strip already rewrote.
    assert result.body == "| Seal | Width |\n|---|---|\n| A | 3.5 |\n"
    assert (result.stripped, result.mended) == (1, 1)


def test_a_body_with_nothing_touched_comes_back_as_it_arrived() -> None:
    body = (
        f"A whole sen{SOFT_HYPHEN}tence.\n"
        "\n"
        "| Seal | Width | Depth |\n"
        "|---|---|---|\n"
        "| B | 4.0 |\n"
    )

    result = accept(body, TouchedLines())

    assert result.body == body
    assert not result.changed
