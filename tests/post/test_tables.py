"""Tests for the table route: the row-indexed reply and its row verdicts."""

from __future__ import annotations

import pytest

from raw2md.llm.post.common import PostOperation
from raw2md.llm.post.coordinator import post_process

from ._helpers import (
    BROKEN_TABLE_ZONE,
    ROW_FIX,
    SchemaProvider,
    call_count,
    join_blocks,
    make_op,
    reason_text,
    rows_reply,
    sent_text,
    wide_zone,
)

# --- table zones: the whole table, a row-indexed reply -----------------------


def test_a_repaired_row_is_written_back_into_the_table() -> None:
    op = make_op([ROW_FIX])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_rows, result.refused_rows) == (1, 0)
    assert "| x |  |" in result.body


def test_the_row_list_is_asked_for_through_the_provider_interface() -> None:
    from raw2md.llm.post.tables import _ROWS_SCHEMA

    provider = SchemaProvider([ROW_FIX])
    op = PostOperation(provider=provider, prompt="FIX", model_key="fake")
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert provider.schemas == [_ROWS_SCHEMA]
    assert result.repaired_rows == 1


def test_a_table_cut_across_blocks_is_gathered_into_one_zone() -> None:
    # A page break leaves the lower rows without a header or a separator.
    first = ["| A | B |", "| --- | --- |", "| 1 | 2 |"]
    second = ["| 3 |"]
    op = make_op([rows_reply((4, "| 3 |  |"))])
    result = post_process(join_blocks(first, second), op)
    assert call_count(op) == 1
    assert "1: | A | B |" in sent_text(op)
    assert "4: | 3 |" in sent_text(op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| 3 |  |" in result.body


def test_a_second_table_below_is_not_pulled_into_the_zone() -> None:
    # Each table declares its own width.
    first = ["| A | B |", "| --- | --- |", "| 1 | 2 |"]
    second = [
        "| C | D | E |",
        "| --- | --- | --- |",
        "| 3 | 4 |",
    ]
    op = make_op([rows_reply((3, "| 3 | 4 |  |"))])
    result = post_process(join_blocks(first, second), op)
    assert "| A | B |" not in sent_text(op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| 3 | 4 |  |" in result.body


def test_prose_under_the_table_ends_the_zone() -> None:
    op = make_op([ROW_FIX])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE, ["A paragraph below it."]), op)
    assert "A paragraph below it." not in sent_text(op)
    assert "A paragraph below it." in result.body


def test_a_row_outside_the_zone_is_refused() -> None:
    outside = rows_reply((9, "| x |  |"))
    op = make_op([outside, outside])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_rows, result.refused_rows) == (0, 2)
    assert "row 9 is not a row of this zone" in reason_text(op)
    assert "| x |" in result.body


def test_the_separator_row_is_not_open_to_rewriting() -> None:
    # The separator is the yardstick of every other row.
    wide = rows_reply((2, "| --- | --- | --- |"))
    op = make_op([wide, wide])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| --- | --- | --- |" not in result.body
    assert "separator row" in reason_text(op)


def test_a_row_off_the_declared_width_is_refused() -> None:
    off = rows_reply((3, "| x |  |  |"))
    op = make_op([off, off])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| x |" in result.body
    # A refusal is not an echo, so it takes the one retry.
    assert call_count(op) == 2
    assert "3 cells, not the 2" in reason_text(op)


def test_a_bad_row_is_refused_while_the_others_are_applied() -> None:
    zone = [
        "| A | B |",
        "| --- | --- |",
        "| x |",
        "| y |",
    ]
    op = make_op([rows_reply((3, "| x |  |"), (4, "| z |  |"))])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 1  # a landed row needs no retry
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_rows, result.refused_rows) == (1, 1)
    assert "| x |  |" in result.body
    assert "| y |" in result.body


def test_a_row_whose_markup_shows_nothing_wrong_is_refused() -> None:
    # Post never sees the source page, so a sound row has nothing to repair from.
    zone = [
        "| A | B |",
        "| --- | --- |",
        "| 1 | 2 |",
        "| x |",
    ]
    shifted = rows_reply((3, "|  | 1 2 |"))
    op = make_op([shifted, shifted])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_rows, result.refused_rows) == (0, 2)
    assert "| 1 | 2 |" in result.body
    assert "markup shows the grid wrong" in reason_text(op)


def test_a_row_that_rewrites_a_value_is_refused() -> None:
    changed = rows_reply((3, "| w |  |"))
    op = make_op([changed, changed])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| w |" not in result.body
    assert "values it was not given" in reason_text(op)


def test_a_zone_whose_only_defect_is_a_slid_value_is_not_sent() -> None:
    # A slid value keeps the width and crushes nothing, so the markup cannot show it.
    zone = [
        "| A | B |",
        "| --- | --- |",
        "|  | 1.5 |",
    ]
    op = make_op([])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 0
    assert (result.repaired, result.reverted) == (0, 0)
    assert "|  | 1.5 |" in result.body


def test_a_row_that_dropped_a_value_is_refused() -> None:
    zone = [
        "| A | B | C |",
        "| --- | --- | --- |",
        "| 1.5<br>2.5<br>3.5 |  |  |",
        "| 1.0 | 2.0 | 3.0 |",
    ]
    truncated = rows_reply((3, "| 1.5 | 2.5 |  |"))
    op = make_op([truncated, truncated])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| 1.5<br>2.5<br>3.5 |  |  |" in result.body
    assert "values it was not given" in reason_text(op)


def test_a_wrapped_cell_taken_apart_across_the_row_is_refused() -> None:
    # No empty column beside the break: one cell wrapped over two lines.
    zone = [
        "| A | B | C |",
        "| --- | --- | --- |",
        "| Ra<br>[mm] | 1.5 |",
    ]
    torn = rows_reply((3, "| [mm] | Ra | 1.5 |"))
    op = make_op([torn, torn])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| Ra<br>[mm] | 1.5 |" in result.body
    assert "values it was not given" in reason_text(op)


def test_a_wrapped_cell_moved_whole_is_applied() -> None:
    zone = [
        "| A | B | C |",
        "| --- | --- | --- |",
        "| Ra<br>[mm] | 1.5 |",
    ]
    op = make_op([rows_reply((3, "|  | Ra<br>[mm] | 1.5 |"))])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "|  | Ra<br>[mm] | 1.5 |" in result.body


def test_an_empty_cell_that_gained_a_value_is_refused() -> None:
    invented = rows_reply((3, "| x | y |"))
    op = make_op([invented, invented])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| y |" not in result.body
    assert "values it was not given" in reason_text(op)


def test_a_row_that_rewrites_a_formula_is_refused() -> None:
    zone = [
        "| A | B |",
        "| --- | --- |",
        "| $a+b$ |",
    ]
    changed = rows_reply((3, "| $a-b$ |  |"))
    op = make_op([changed, changed])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "$a+b$" in result.body
    assert "formula" in reason_text(op)


def test_a_stack_spread_across_its_cells_is_applied() -> None:
    # Every value sits in one cell, split by in-cell line breaks.
    zone = [
        "| A | B |",
        "| --- | --- |",
        "| 1.5<br>2.5 |  |",
        "| 1.0 | 2.0 |",
    ]
    op = make_op([rows_reply((3, "| 1.5 | 2.5 |"))])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| 1.5 | 2.5 |" in result.body


def test_a_run_spread_out_of_a_stacked_row_is_applied() -> None:
    # One cell of a merged row carries two values on each line of its stack.
    zone = [
        "| Code | Bore | Cross | Width |",
        "| --- | --- | --- | --- |",
        "| 7-112<br>7-113 | 31.75 4.10<br>33.20 4.10 |  | 6.5<br>6.5 |",
        "| 7-111 | 31.75 | 4.10 | 6.5 |",
    ]
    spread = "| 7-112<br>7-113 | 31.75<br>33.20 | 4.10<br>4.10 | 6.5<br>6.5 |"
    op = make_op([rows_reply((3, spread))])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert spread in result.body


def test_a_stacked_row_states_how_far_its_run_reaches() -> None:
    # The measure is the run width in columns, not the value count.
    zone = [
        "| Code | Bore | Cross | Width |",
        "| --- | --- | --- | --- |",
        "| 7-112<br>7-113 | 31.75 4.10<br>33.20 4.10 |  | 6.5<br>6.5 |",
        "| 7-111 | 31.75 | 4.10 | 6.5 |",
    ]
    spread = "| 7-112<br>7-113 | 31.75<br>33.20 | 4.10<br>4.10 | 6.5<br>6.5 |"
    op = make_op([rows_reply((3, spread))])
    post_process(join_blocks(zone), op)
    assert "row 3 (2 values crushed into one cell)" in _open_rows_line(op)


def test_a_table_is_sent_on_its_own_damage() -> None:
    zone = ["| A | B |", "| --- | --- |", "| x |"]
    op = make_op([rows_reply((3, "| x |  |"))])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 1
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| x |  |" in result.body


def test_a_run_crushed_mid_row_is_opened_and_spread() -> None:
    zone = [
        "| Code | Size | Mass | Note |",
        "| --- | --- | --- | --- |",
        "| 7-140 88.40 4.10 |  |  | ring |",
        "| 7-141 | 89.15 | 4.25 | ring |",
    ]
    op = make_op([rows_reply((3, "| 7-140 | 88.40 | 4.10 | ring |"))])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| 7-140 | 88.40 | 4.10 | ring |" in result.body


def test_a_run_is_opened_where_no_row_of_the_zone_kept_its_grid() -> None:
    # No row keeps its grid, so the columns are unknown.
    zone = [
        "| Code | Size | Mass |",
        "| --- | --- | --- |",
        "| 7-140 88.40 4.10 |  |  |",
        "| 7-141 89.15 4.25 |  |  |",
    ]
    reply = rows_reply((3, "| 7-140 | 88.40 | 4.10 |"), (4, "| 7-141 | 89.15 | 4.25 |"))
    result = post_process(join_blocks(zone), make_op([reply]))
    assert (result.repaired, result.repaired_rows) == (1, 2)
    assert "| 7-141 | 89.15 | 4.25 |" in result.body


# A run of three values crushed into the first cell, beside two empty columns.
CRUSHED_RUN_ZONE = [
    "| Code | Size | Mass | Note |",
    "| --- | --- | --- | --- |",
    "| 7-140 88.40 4.10 |  |  | ring |",
    "| 7-141 | 89.15 | 4.25 | ring |",
]


def test_a_row_still_carrying_the_cells_a_spread_run_left_is_squeezed() -> None:
    # The run is spread, but the empty cells beside it stay.
    op = make_op([rows_reply((3, "| 7-140 | 88.40 | 4.10 |  |  | ring |"))])
    result = post_process(join_blocks(CRUSHED_RUN_ZONE), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| 7-140 | 88.40 | 4.10 | ring |" in result.body


def test_a_crushed_run_spread_out_of_order_is_refused() -> None:
    # The multiset and the width hold; only the order changed.
    swapped = rows_reply((3, "| 7-140 | 4.10 | 88.40 | ring |"))
    op = make_op([swapped, swapped])
    result = post_process(join_blocks(CRUSHED_RUN_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| 7-140 88.40 4.10 |  |  | ring |" in result.body
    assert "another order" in reason_text(op)


def test_a_reply_that_moves_the_stack_to_another_cell_is_refused() -> None:
    moved = rows_reply((3, "|  | 7-140 88.40 4.10 |  | ring |"))
    op = make_op([moved, moved])
    result = post_process(join_blocks(CRUSHED_RUN_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "| 7-140 88.40 4.10 |  |  | ring |" in result.body


def test_a_reply_row_short_of_the_width_in_filled_cells_is_refused() -> None:
    # One column is really blank, so the reply cannot guess which cell stays empty.
    zone = [
        "| Code | Size | Mass | Note |",
        "| --- | --- | --- | --- |",
        "| 7-140 88.40 |  |  | ring |",
        "| 7-141 | 89.15 | 4.25 | ring |",
    ]
    short = rows_reply((3, "| 7-140 | 88.40 |  |  | ring |"))
    op = make_op([short, short])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (0, 0)
    assert "5 cells, not the 4" in reason_text(op)
    assert "| 7-140 88.40 |  |  | ring |" in result.body


def test_a_reply_row_whose_filled_cells_outrun_the_width_is_refused() -> None:
    over = rows_reply((3, "| 7-140 | 88.40 | 4.10 | ring | spare |"))
    op = make_op([over, over])
    result = post_process(join_blocks(CRUSHED_RUN_ZONE), op)
    assert (result.repaired, result.repaired_rows) == (0, 0)
    assert "5 cells, not the 4" in reason_text(op)


def test_a_squeezed_row_is_still_judged_on_its_values() -> None:
    rewritten = rows_reply((3, "| 7-140 | 88.40 | 4.11 |  |  | ring |"))
    op = make_op([rewritten, rewritten])
    result = post_process(join_blocks(CRUSHED_RUN_ZONE), op)
    assert (result.repaired, result.repaired_rows) == (0, 0)
    assert "values it was not given" in reason_text(op)
    assert "4.11" not in result.body


def test_a_squeezed_row_that_still_stacks_its_values_is_refused() -> None:
    stacked = rows_reply((3, "| 7-140<br>88.40 | 4.10 | ring | spare |  |"))
    op = make_op([stacked, stacked])
    result = post_process(join_blocks(CRUSHED_RUN_ZONE), op)
    assert (result.repaired, result.repaired_rows) == (0, 0)
    assert "| 7-140 88.40 4.10 |  |  | ring |" in result.body


def test_a_squeezed_row_is_still_judged_on_its_formulas() -> None:
    zone = [
        "| Term | Value | Note |",
        "| --- | --- | --- |",
        "| $x^2$ 1.5 note |",
    ]
    rewritten = rows_reply((3, "| $x^3$ | 1.5 | note |  |"))
    op = make_op([rewritten, rewritten])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (0, 0)
    assert "formula's content changed" in reason_text(op)
    assert "$x^3$" not in result.body


def test_a_reply_row_at_the_declared_width_keeps_its_empty_cells() -> None:
    # Closing an empty cell in a full-width row would shift every value beside it.
    zone = ["| A | B | C |", "| --- | --- | --- |", "| x |"]
    op = make_op([rows_reply((3, "| x |  |  |"))])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| x |  |  |" in result.body


def _open_rows_line(op: PostOperation, call: int = 0) -> str:
    """The request line naming which rows are open to repair."""
    return next(
        row
        for row in sent_text(op, call).splitlines()
        if row.startswith("Rows open to repair:")
    )


def test_the_request_names_open_rows_and_the_measure_of_each() -> None:
    zone = [
        "| Code | Size | Mass | Note |",
        "| --- | --- | --- | --- |",
        "| 7-140 88.40 4.10 |  |  | ring |",
        "| x |",
        "| 7-141 | 89.15 | 4.25 | ring |",
    ]
    op = make_op([rows_reply((3, "| 7-140 | 88.40 | 4.10 | ring |"))])
    post_process(join_blocks(zone), op)
    text = sent_text(op)
    assert "The separator row declares 4 cells" in text
    assert "goes out of the row with it" in text
    line = _open_rows_line(op)
    assert "row 3 (3 values crushed into one cell)" in line
    assert "row 4 (holds 1 cells, not the 4)" in line


def test_the_open_rows_note_leaves_a_sound_row_out() -> None:
    zone = [
        "| A | B |",
        "| --- | --- |",
        "| 1 | 2 |",
        "| x |",
    ]
    op = make_op([rows_reply((4, "| x |  |"))])
    post_process(join_blocks(zone), op)
    line = _open_rows_line(op)
    assert "row 4" in line
    assert "row 3" not in line


# A value wrapped onto its own line; post cannot mend it, so it is named closed.
CONTINUATION_ZONE = [
    "| Name | Value | Note |",
    "| --- | --- | --- |",
    "| alpha | 1.5 | first |",
    "|  | overflow |  |",
    "| gamma |",
]


def test_a_continuation_row_is_named_closed_in_the_request() -> None:
    op = make_op([rows_reply((5, "| gamma |  |  |"))])
    post_process(join_blocks(CONTINUATION_ZONE), op)
    text = sent_text(op)
    assert "Leave rows 4 exactly as they stand" in text
    assert "4" not in _open_rows_line(op)


def test_a_reply_that_edits_a_continuation_row_is_refused() -> None:
    merged = rows_reply((4, "| alpha | 1.5 | first overflow |"))
    op = make_op([merged, merged])
    result = post_process(join_blocks(CONTINUATION_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "continuation row" in reason_text(op)
    assert "|  | overflow |  |" in result.body


def test_a_table_whose_only_oddity_is_a_continuation_row_is_not_sent() -> None:
    zone = [
        "| Name | Value | Note |",
        "| --- | --- | --- |",
        "| alpha | 1.5 | first |",
        "|  | overflow |  |",
    ]
    op = make_op([])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 0
    assert result.body == join_blocks(zone)


# One contents entry crushed into the last column, split at every printed line.
CONTENTS_ZONE = [
    "|   |     | Contents                                     |",
    "|---|-----|----------------------------------------------|",
    "|   |     | 6.3.2<br>Grid-Based<br>Versus<br>Blends<br>73 |",
]


def test_a_contents_entry_crushed_whole_is_split_into_number_and_title() -> None:
    # The one boundary the entry states is between the number and the title.
    op = make_op([rows_reply((3, "|  | 6.3.2 | Grid-Based Versus Blends 73 |"))])
    result = post_process(join_blocks(CONTENTS_ZONE), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "|  | 6.3.2 | Grid-Based Versus Blends 73 |" in result.body


def test_the_words_of_a_contents_title_are_not_spread_across_columns() -> None:
    scattered = rows_reply((3, "| 6.3.2 | Grid-Based | Versus Blends 73 |"))
    op = make_op([scattered, scattered])
    result = post_process(join_blocks(CONTENTS_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "values it was not given" in reason_text(op)


def test_a_contents_entry_repaired_with_its_breaks_kept_is_accepted() -> None:
    # A reply may keep the title breaks as `<br>`.
    kept = "|  | 6.3.2 | Grid-Based<br>Versus<br>Blends<br>73 |"
    op = make_op([rows_reply((3, kept))])
    result = post_process(join_blocks(CONTENTS_ZONE), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert kept in result.body


def test_a_contents_entry_repaired_with_a_changed_word_is_refused() -> None:
    changed = rows_reply((3, "|  | 6.3.2 | Grid-Based<br>Versus<br>Blending<br>73 |"))
    op = make_op([changed, changed])
    result = post_process(join_blocks(CONTENTS_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "values it was not given" in reason_text(op)
    assert "Blending" not in result.body


def test_a_contents_entry_repaired_with_its_values_swapped_is_refused() -> None:
    swapped = rows_reply((3, "|  | Grid-Based<br>Versus<br>Blends<br>73 | 6.3.2 |"))
    op = make_op([swapped, swapped])
    result = post_process(join_blocks(CONTENTS_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "another order" in reason_text(op)


def test_a_wrapped_value_beside_a_blank_column_is_no_contents_entry() -> None:
    # Not a page number at the end, so the stack is a wrapped value.
    zone = [
        "| Build | Note |",
        "| --- | --- |",
        "|  | 1.2.3<br>beta<br>release |",
        "|  | 1.2<br>beta<br>3 |",
    ]
    op = make_op([])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 0
    assert "|  | 1.2.3<br>beta<br>release |" in result.body
    assert "|  | 1.2<br>beta<br>3 |" in result.body


def test_a_run_matching_its_blank_columns_keeps_the_column_reading() -> None:
    zone = [
        "| Item | A | B |",
        "| --- | --- | --- |",
        "| 5.1.3<br>Frames<br>72 |  |  |",
        "| 5.1.4 | Joints | 73 |",
    ]
    op = make_op([rows_reply((3, "| 5.1.3 | Frames | 72 |"))])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| 5.1.3 | Frames | 72 |" in result.body


def test_a_cell_holding_wrapped_prose_is_not_opened() -> None:
    zone = [
        "| Term | A | B | C |",
        "| --- | --- | --- | --- |",
        "| the pressure of the gas |  |  |  |",
    ]
    op = make_op([])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 0
    assert (result.repaired, result.reverted) == (0, 0)
    assert "| the pressure of the gas |  |  |  |" in result.body


def test_a_stack_only_rearranged_inside_its_cell_is_refused() -> None:
    zone = [
        "| A | B |",
        "| --- | --- |",
        "| 1.5<br>2.5 |  |",
        "| 1.0 | 2.0 |",
    ]
    stacked = rows_reply((3, "|  | 1.5<br>2.5 |"))
    op = make_op([stacked, stacked])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "stacked inside one cell" in reason_text(op)


def _long_sound_table() -> list[str]:
    """A grid of sound rows with one row that lost a cell, flagged."""
    sound_rows = [f"| {number} | {'ok ' * 20} |" for number in range(1, 121)]
    return [
        "| A | B |",
        "| --- | --- |",
        *sound_rows,
        "| x |",
    ]


def test_a_long_sound_table_with_one_damaged_row_is_still_sent() -> None:
    # The reply budget counts only the open rows.
    op = make_op([rows_reply((123, "| x |  |"))])
    result = post_process(join_blocks(_long_sound_table()), op)
    assert call_count(op) == 1
    assert "| 60 |" in sent_text(op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| x |  |" in result.body


def test_a_table_too_large_to_send_whole_shows_its_open_rows_alone() -> None:
    op = make_op([rows_reply((123, "| x |  |"))], max_request_bytes=2000)
    result = post_process(join_blocks(_long_sound_table()), op)
    assert call_count(op) == 1
    assert "| 60 |" not in sent_text(op)
    assert (result.repaired, result.repaired_rows) == (1, 1)
    assert "| x |  |" in result.body
    assert "| 60 | " in result.body


def test_a_reply_that_is_not_the_row_list_reverts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The second prose reply in a row stays a WARNING.
    markdown = "\n".join(["| A | B |", "| --- | --- |", "| x |  |"])
    op = make_op([markdown, markdown])
    with caplog.at_level("INFO", logger="raw2md"):
        result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted, result.unchanged) == (0, 1, 0)
    assert "JSON row list" in reason_text(op)
    assert any(
        record.levelname == "WARNING" and "retry too" in record.message
        for record in caplog.records
    )


def test_a_reply_that_is_not_the_row_list_is_retried_once_and_recovers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    markdown = "\n".join(["| A | B |", "| --- | --- |", "| x |  |"])
    op = make_op([markdown, ROW_FIX])
    with caplog.at_level("INFO", logger="raw2md"):
        result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert call_count(op) == 2
    assert not any(record.levelname == "WARNING" for record in caplog.records)
    assert any(
        record.levelname == "INFO" and "retrying once" in record.message
        for record in caplog.records
    )


def test_a_reply_naming_no_changed_row_is_a_terminal_echo() -> None:
    op = make_op(['{"rows": []}'])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted, result.unchanged) == (0, 1, 1)
    assert (result.repaired_rows, result.refused_rows) == (0, 0)
    assert call_count(op) == 1


def test_a_fenced_row_list_is_still_read() -> None:
    op = make_op([f"```json\n{ROW_FIX}\n```"])
    result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.repaired_rows) == (1, 1)


def test_a_wide_table_is_split_into_parts_gathered_into_one_zone() -> None:
    zone, fixed = wide_zone()
    # Every part reply names every repairable row; a part applies only its own.
    everything = rows_reply(*[(number, fixed) for number in range(3, 9)])
    op = make_op([everything] * 6)
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 3
    assert (result.repaired, result.reverted) == (1, 0)  # one zone, gathered back
    assert result.repaired_rows == 6
    assert result.body.count(fixed) == 6


def test_each_part_of_a_split_table_carries_the_header_and_delimiter() -> None:
    zone, fixed = wide_zone()
    everything = rows_reply(*[(number, fixed) for number in range(3, 9)])
    op = make_op([everything] * 6)
    post_process(join_blocks(zone), op)
    parts = [sent_text(op, call) for call in range(call_count(op))]
    assert len(parts) == 3
    for part in parts:
        assert "1: | A | B |" in part
        assert "2: | --- | --- |" in part
        assert "covers rows" in part
    assert sum("3: |" in part for part in parts) == 1
    assert sum("7: |" in part for part in parts) == 1


def test_a_split_table_that_reverts_one_part_still_delivers_the_others() -> None:
    zone, fixed = wide_zone()
    good = rows_reply(*[(number, fixed) for number in range(3, 9)])
    # The middle part answers with prose twice and reverts.
    op = make_op([good, "no table here", "no table here", good])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.repaired_rows == 4


def test_a_split_part_ignores_an_echoed_header_or_delimiter_row() -> None:
    zone, fixed = wide_zone()
    first = rows_reply(
        (1, "| A | B |"),
        (2, "| --- | --- |"),
        (3, fixed),
        (4, fixed),
    )
    rest = rows_reply(*[(number, fixed) for number in range(3, 9)])
    op = make_op([first, rest, rest])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_rows, result.refused_rows) == (6, 0)


def test_a_truncated_table_reply_is_named_apart_from_an_unreadable_one(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cut = '{"rows": [{"row": 3, "text": "| x'
    op = make_op([cut, cut])
    with caplog.at_level("INFO", logger="raw2md"):
        result = post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert call_count(op) == 2
    assert any(
        "cut off before the row list closed" in record.message
        for record in caplog.records
    )
    assert not any("not a row list" in record.message for record in caplog.records)


def test_an_unreadable_table_reply_is_still_named_not_a_row_list(
    caplog: pytest.LogCaptureFixture,
) -> None:
    prose = "Here is the fixed table:\n\n| A | B |\n| --- | --- |\n| x |  |"
    op = make_op([prose, prose])
    with caplog.at_level("INFO", logger="raw2md"):
        post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert any("not a row list" in record.message for record in caplog.records)
    assert not any("cut off" in record.message for record in caplog.records)
