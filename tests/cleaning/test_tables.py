"""Tests for the table rules.

`cleaning.tables` repairs only what the grid itself proves. A table too damaged
to repair is reported, which marks the boundary of the mechanical repairs.
"""

from __future__ import annotations

from collections import Counter

from raw2md.cleaner import CleanOptions, clean, clean_in_place, clean_with_report
from raw2md.cleaning import printed_outline
from raw2md.keywords import default_keywords
from raw2md.mdtext.lines import is_table_separator
from raw2md.mdtext.pages import page_mark
from raw2md.mdtext.zones import segments

from ._helpers import laid_out_table

KEYWORDS = default_keywords()


def _reported(text: str, options: CleanOptions | None = None) -> str:
    """The findings of one clean, one `kind detail` per line."""
    result = clean_with_report(text, options)
    return "\n".join(f"{f.kind} {f.detail}".rstrip() for f in result.findings)


# ---- in-place fix: a table with no data row -----------------------------------

# The header and a repeated separator, with no body under either.
_BODYLESS_TABLE = (
    "| Unit K   | R/KR ( | Link | age |\n"
    "|----------|--------|------|-----|\n"
    "|----------|--------|------|-----|\n"
)


def test_bodyless_table_behind_a_duplicate_separator_is_collapsed() -> None:
    assert clean_in_place(_BODYLESS_TABLE) == "Unit K R/KR ( Link age\n"


def test_bodyless_table_with_a_single_separator_is_collapsed() -> None:
    text = "| A | B |\n|---|---|\n"
    assert clean_in_place(text) == "A B\n"


def test_bodyless_table_with_a_blank_cell_omits_it_from_the_text() -> None:
    text = "| A |  | C |\n|---|---|---|\n"
    assert clean_in_place(text) == "A C\n"


def test_table_with_one_data_row_is_not_touched() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    assert clean_in_place(text) == text


def test_setext_heading_shaped_bodyless_line_is_not_collapsed() -> None:
    # Two header cells against one delimiter cell: a setext heading.
    text = "A | B\n---\n\nFollowing paragraph.\n"
    assert clean_in_place(text) == text


def test_bodyless_table_collapse_keeps_row_indentation() -> None:
    text = "  | A | B |\n  |---|---|\n"
    assert clean_in_place(text) == "  A B\n"


def test_bodyless_table_collapse_inside_fence_is_not_touched() -> None:
    text = "```\n| A | B |\n|---|---|\n```\n"
    assert clean_in_place(text) == text


def test_bodyless_table_collapse_leaves_no_anchor() -> None:
    assert "broken-table" not in _reported(_BODYLESS_TABLE)


def test_bodyless_table_collapse_is_idempotent() -> None:
    once = clean_in_place(_BODYLESS_TABLE)
    assert clean_in_place(once) == once


def test_bodyless_collapse_gives_a_span_the_bars_it_was_printed_with() -> None:
    # Off the row, an escaped bar is the norm operator, not a modulus.
    text = "| $$\\left| x \\right|$$ | (3) |\n|----|----|\n"
    assert clean_in_place(text) == "$$\\left| x \\right| \\tag{3}$$\n"


def test_a_table_that_keeps_its_body_keeps_its_math_pipes_escaped() -> None:
    text = "| $$\\left| x \\right|$$ | b |\n|----|----|\n| 1 | 2 |\n"
    assert clean_in_place(text) == (
        "| $$\\left\\| x \\right\\|$$ | b |\n"
        "|------------------------|---|\n"
        "| 1                      | 2 |\n"
    )


def test_bodyless_collapse_leaves_a_pipe_outside_a_span_escaped() -> None:
    text = "| a \\| b | c |\n|----|----|\n"
    assert clean_in_place(text) == "a \\| b c\n"


# ---- postcondition: a separator left as a block's first line -----------------


def test_a_block_that_lost_a_junk_asterisk_header_renders_again() -> None:
    # The junk-line pass drops the asterisk band where the header stood.
    text = (
        "Intro paragraph.\n\n"
        "| *** | *** | *** |\n"
        "|---|---|---|\n"
        "| gas | 1.0 | 2.0 |\n"
        "| oil | 3.0 | 4.0 |\n"
    )
    assert clean_in_place(text).splitlines() == [
        "Intro paragraph.",
        "",
        "| gas | 1.0 | 2.0 |",
        "|-----|-----|-----|",
        "| oil | 3.0 | 4.0 |",
    ]


def test_a_block_that_lost_a_bullet_glyph_header_renders_again() -> None:
    text = "Intro paragraph.\n\n| • | • |\n|---|---|\n| a | b |\n| c | d |\n"
    assert clean_in_place(text).splitlines()[2:] == [
        "| a | b |",
        "|---|---|",
        "| c | d |",
    ]


def test_a_block_that_is_the_separator_alone_is_not_touched() -> None:
    text = "Intro paragraph.\n\n| --- | --- |\n\nNext paragraph.\n"
    assert clean_in_place(text) == text


def test_a_healthy_table_keeps_its_separator_second() -> None:
    text = "| H1 | H2 |\n|----|----|\n| a  | b  |\n| c  | d  |\n"
    assert clean_in_place(text) == text


def test_a_bare_thematic_break_over_a_piped_line_is_not_a_table() -> None:
    text = "Intro paragraph.\n\n---\nprose | with a pipe\n"
    assert clean_in_place(text) == text


def test_a_separator_first_row_off_the_width_is_left_alone() -> None:
    text = "Intro paragraph.\n\n|---|---|\n| a | b | c |\n"
    assert clean_in_place(text) == text


def test_sinking_a_separator_moves_no_cell() -> None:
    text = "Intro.\n\n|----------|----------|\n|   1.00   |   2.00   |\n"
    assert clean_in_place(text) == (
        "Intro.\n\n|   1.00   |   2.00   |\n|----------|----------|\n"
    )


def test_sinking_a_separator_is_idempotent() -> None:
    text = "Intro paragraph.\n\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_a_sunk_separator_leaves_no_collapsed_grid_anchor() -> None:
    text = "Intro paragraph.\n\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    assert "broken-table" not in _reported(text)


def test_a_page_mark_below_a_sunk_separator_rides_above_the_new_header() -> None:
    text = f"Intro paragraph.\n\n|---|---|\n{page_mark(4)}\n| 1 | 2 |\n| 3 | 4 |\n"
    assert clean_in_place(text).splitlines()[2:] == [
        page_mark(4),
        "| 1 | 2 |",
        "|---|---|",
        "| 3 | 4 |",
    ]


# ---- postcondition: a pipe block with no delimiter row -----------------------


def test_a_delimiterless_block_is_joined_to_the_table_above_it() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n| 5 | 6 |\n"
    assert (
        clean_in_place(text)
        == "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n"
    )


def test_a_page_mark_in_the_join_rides_below_the_joined_table() -> None:
    text = f"| A | B |\n|---|---|\n| 1 | 2 |\n\n{page_mark(5)}\n| 3 | 4 |\n| 5 | 6 |\n"
    assert clean_in_place(text) == (
        f"| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n{page_mark(5)}\n"
    )


def test_joining_a_delimiterless_block_is_idempotent() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n| 5 | 6 |\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_a_standalone_delimiterless_block_is_given_its_own_delimiter() -> None:
    text = "Intro paragraph.\n\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n"
    assert clean_in_place(text) == (
        "Intro paragraph.\n\n| 1 | 2 | 3 |\n|---|---|---|\n| 4 | 5 | 6 |\n"
    )


def test_giving_a_delimiterless_block_its_own_delimiter_is_idempotent() -> None:
    text = "Intro paragraph.\n\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_a_page_mark_inside_a_standalone_block_rides_below_it() -> None:
    text = f"Intro paragraph.\n\n| 1 | 2 |\n{page_mark(3)}\n| 4 | 5 |\n"
    assert clean_in_place(text) == (
        f"Intro paragraph.\n\n| 1 | 2 |\n|---|---|\n| 4 | 5 |\n{page_mark(3)}\n"
    )


def test_a_block_matching_a_different_width_is_not_joined() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 | 5 |\n| 6 | 7 | 8 |\n"
    assert clean_in_place(text) == (
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "| 3 | 4 | 5 |\n|---|---|---|\n| 6 | 7 | 8 |\n"
    )


def test_a_lone_delimiterless_row_is_left_alone() -> None:
    text = "Intro paragraph.\n\n| 1 | 2 |\n"
    assert clean_in_place(text) == text


def test_a_one_column_delimiterless_block_is_left_alone() -> None:
    text = "Intro paragraph.\n\n| 1 |\n| 2 |\n| 3 |\n"
    assert clean_in_place(text) == text


def test_a_delimiterless_block_off_its_own_width_is_left_alone() -> None:
    text = "Intro paragraph.\n\n| 1 | 2 |\n| 3 | 4 | 5 |\n"
    assert clean_in_place(text) == text


def test_a_delimiterless_block_with_a_math_pipe_is_left_alone() -> None:
    text = "Intro paragraph.\n\n| $a | b$ |\n| c | d |\n"
    assert clean_in_place(text) == text


def test_prose_whose_only_pipes_are_inside_code_is_left_alone() -> None:
    text = (
        "Intro paragraph.\n\n"
        "Run `ls | wc` to count them.\n"
        "Run `ps | wc` to count those.\n"
    )
    assert clean_in_place(text) == text


def test_a_block_carrying_its_own_delimiter_is_not_mended() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    assert clean_in_place(text) == text


# ---- postcondition: the layout of a table block ------------------------------

# Aligned to this note, every row runs past the ceiling.
_WIDE_NOTE = (
    "Coolant is harder to flush out of a narrow slot, so the slot width is set "
    "by the nozzle that has to clear it afterwards"
)


def test_a_block_inside_the_ceiling_is_written_aligned() -> None:
    text = (
        "| Code | Description       | Mass |\n"
        "|---|---|---|\n"
        "| A-1 | Base plate | 3.20 |\n"
        "| A-2 | Cross bar holder | 12.40 |\n"
    )
    assert clean_in_place(text) == (
        "| Code | Description      | Mass  |\n"
        "|------|------------------|-------|\n"
        "| A-1  | Base plate       | 3.20  |\n"
        "| A-2  | Cross bar holder | 12.40 |\n"
    )


def test_a_block_past_the_ceiling_is_written_compactly() -> None:
    text = (
        f"| Code | {'Note'.ljust(len(_WIDE_NOTE))} | Mass |\n"
        f"|------|{'-' * (len(_WIDE_NOTE) + 2)}|------|\n"
        f"| A-1  | {_WIDE_NOTE} | 3.20 |\n"
        f"| A-2  | {'Trimmed by hand'.ljust(len(_WIDE_NOTE))} | 3.40 |\n"
    )
    assert clean_in_place(text) == (
        "| Code | Note | Mass |\n"
        "|---|---|---|\n"
        f"| A-1 | {_WIDE_NOTE} | 3.20 |\n"
        "| A-2 | Trimmed by hand | 3.40 |\n"
    )


def test_alignment_colons_survive_the_aligned_layout() -> None:
    text = "| Month | Taken | Done |\n|:---|---:|:---:|\n| January | 1240 | 1198 |\n"
    assert clean_in_place(text) == (
        "| Month   | Taken | Done |\n"
        "|:--------|------:|:----:|\n"
        "| January | 1240  | 1198 |\n"
    )


def test_alignment_colons_survive_the_compact_layout() -> None:
    text = (
        f"| Code | {'Note'.ljust(len(_WIDE_NOTE))} | Mass |\n"
        f"|:-----|{':' + '-' * len(_WIDE_NOTE) + ':'}|-----:|\n"
        f"| A-1  | {_WIDE_NOTE} | 3.20 |\n"
    )
    assert clean_in_place(text).splitlines()[1] == "|:--|:-:|--:|"


def test_a_cell_edge_inside_a_math_span_leaves_the_block_alone() -> None:
    text = "| Rate | Value |\n|---|---|\n| $a | b$ | 1 |\n| c | 2 |\n"
    assert clean_in_place(text) == text


def test_a_row_ending_on_an_escaped_pipe_keeps_the_pipe_in_its_cell() -> None:
    # Padding up to the escaped pipe would turn it into a cell edge.
    text = "Code | Symbol\n--- | ---\nA-1 | \\|\nA-2 | phi\n"
    assert clean_in_place(text) == (
        "Code | Symbol\n-----|-------\nA-1  | \\|\nA-2  | phi\n"
    )


def test_a_second_delimiter_row_leaves_the_block_alone() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 22 |\n|---|---|\n| 333 | 4 |\n"
    assert clean_in_place(text) == text


def test_the_layout_keeps_every_cell_byte_for_byte() -> None:
    text = (
        "| Code | Description       | Mass |\n"
        "|---|---|---|\n"
        "| A-1 | Base plate | 3.20 |\n"
        "| A-2 | Cross bar holder | 12.40 |\n"
    )
    assert _row_cells(clean_in_place(text)) == _row_cells(text)


def test_laying_a_block_out_is_idempotent() -> None:
    text = (
        f"| Code | Note | Mass |\n"
        f"|---|---|---|\n"
        f"| A-1 | {_WIDE_NOTE} | 3.20 |\n"
        "| A-2 | short | 3.40 |\n"
    )
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- in-place fix: a table crushed whole into one cell ------------------------


def _crushed_catalogue(rows: int, *, lead: tuple[str, ...] = ()) -> str:
    """A catalogue whose whole body stands in one cell of its header row.

    The titles keep their cells and the body runs together behind `<br>`. `lead` is
    what a units row leaves at the head of the stack once its empty name cell drops.
    """
    pieces = list(lead)
    for step in range(rows):
        pieces += [f"4-{315 + step}", f"{213.58 + step * 3.17:.2f}", "5.81"]
    stack = "<br>".join(pieces)
    return (
        f"| {stack} | Series no. | Shaft diameter | Sleeve length |\n"
        "|---|---|---|---|\n"
    )


def test_a_periodic_stack_is_recut_into_its_table() -> None:
    # 110 pieces over three columns: 36 whole rows plus two leading pieces.
    text = _crushed_catalogue(36, lead=("d", "d2"))
    out = clean_in_place(text).splitlines()
    assert out[0] == "| Series no. | Shaft diameter | Sleeve length |"
    assert out[2] == "|            | d              | d2            |"
    assert out[3] == "| 4-315      | 213.58         | 5.81          |"
    assert out[-1] == "| 4-350      | 324.53         | 5.81          |"
    assert len(out) == 2 + 1 + 36


def test_the_recut_keeps_every_value_in_its_own_order() -> None:
    text = _crushed_catalogue(36, lead=("d", "d2"))
    stack = text.split("|")[1].strip().split("<br>")
    out = clean_in_place(text).splitlines()
    values = [
        cell.strip()
        for line in out[2:]
        for cell in line.strip("|").split("|")
        if cell.strip()
    ]
    assert values == stack


def test_a_recut_table_is_not_collapsed_into_prose() -> None:
    # Without the recut, the bodyless collapse would join the header into prose.
    out = clean_in_place(_crushed_catalogue(36, lead=("d", "d2")))
    assert "<br>" not in out
    assert all(line.strip().startswith("|") for line in out.splitlines())


def test_the_recut_is_idempotent() -> None:
    once = clean_in_place(_crushed_catalogue(36, lead=("d", "d2")))
    assert clean_in_place(once) == once


def test_a_stack_periodic_at_another_width_is_left_alone() -> None:
    # Four values to a row against three titles.
    pieces: list[str] = []
    for step in range(12):
        pieces += [f"4-{315 + step}", f"{213.58 + step:.2f}", "5.81", "ring"]
    text = (
        f"| {'<br>'.join(pieces)} | Series no. | Shaft diameter | Sleeve length |\n"
        "|---|---|---|---|\n"
    )
    assert "| 4-315 |" not in clean_in_place(text)


def test_a_repeated_header_does_not_witness_the_columns() -> None:
    # A reprinted header counted as a witness would spread the title form.
    text = (
        "| Code | Length | Mass |\n"
        "|---|---|---|\n"
        "| A-1 | 12.5 | 3.20 |\n"
        "| A-2 | 13.5 | 3.40 |\n"
        "| Code | Length | Mass |\n"
        "| Code<br>Length<br>Mass |  |  |\n"
    )
    assert "broken-table" not in _reported(text)


def test_an_ambiguous_partial_stack_is_left_alone() -> None:
    # Dropping the odd value from the head or the tail gives two periodic stacks.
    pieces = [f"{100 + step}.5" for step in range(10)]
    text = (
        f"| {'<br>'.join(pieces)} | Shaft diameter | Sleeve length | Width |\n"
        "|---|---|---|---|\n"
    )
    assert "| 100.5 |" not in clean_in_place(text)


def test_a_position_holding_two_forms_is_left_alone() -> None:
    pieces: list[str] = []
    for step in range(12):
        pieces += [
            f"4-{315 + step}",
            f"{213.58 + step:.2f}",
            "5.81" if step % 2 else "Q-55",
        ]
    text = (
        f"| {'<br>'.join(pieces)} | Series no. | Shaft diameter | Sleeve length |\n"
        "|---|---|---|---|\n"
    )
    assert "| 4-315 |" not in clean_in_place(text)


def test_a_short_stack_states_no_period() -> None:
    text = (
        "| 12.0<br>0.31<br>14.0<br>0.44<br>16.0<br>0.55 | Bore | Mass |\n"
        "|---|---|---|\n"
    )
    assert "| 12.0 | 0.31 |" not in clean_in_place(text)


def test_a_crushed_table_with_a_data_row_of_its_own_is_left_alone() -> None:
    text = _crushed_catalogue(36) + "| 4-351 | 318.44 | 5.81 | 4.52 |\n"
    assert clean_in_place(text) == text


def test_a_stack_beside_a_blank_title_is_left_alone() -> None:
    pieces: list[str] = []
    for step in range(24):
        pieces += [f"4-{315 + step}", f"{213.58 + step:.2f}"]
    text = f"| {'<br>'.join(pieces)} | Size tolerances |  |\n|---|---|---|\n"
    assert "| 4-315 |" not in clean_in_place(text)


def test_a_stack_alone_in_its_row_is_left_alone() -> None:
    pieces: list[str] = []
    for step in range(24):
        pieces += [f"4-{315 + step}", f"{213.58 + step:.2f}"]
    text = f"| {'<br>'.join(pieces)} |\n|---|\n"
    assert "| 4-315 |" not in clean_in_place(text)


def test_a_page_mark_inside_a_crushed_table_moves_below_its_rows() -> None:
    text = _crushed_catalogue(36, lead=("d", "d2")) + f"{page_mark(51)}\n"
    out = clean_in_place(text).splitlines()
    assert out[-1] == page_mark(51)
    assert out[-2] == "| 4-350      | 324.53         | 5.81          |"


# ---- in-place fix: a cell that swallowed its neighbour -----------------------

# One lost separator: the `Flange Dia.` value stands inside `Hub Dia.`.
_SWALLOWED_CELL_TABLE = (
    "| Hub Dia. | Flange Dia. | Flange Width |\n"
    "|---|---|---|\n"
    "| 940.0 | 971.6 | 9.5 |\n"
    "| 1,000.0 1,031.6 |  | 9.5 |\n"
)


def test_swallowed_cell_is_recut() -> None:
    assert clean_in_place(_SWALLOWED_CELL_TABLE) == (
        "| Hub Dia. | Flange Dia. | Flange Width |\n"
        "|----------|-------------|--------------|\n"
        "| 940.0    | 971.6       | 9.5          |\n"
        "| 1,000.0  | 1,031.6     | 9.5          |\n"
    )


def test_swallowed_cell_is_recut_into_the_blank_before_it() -> None:
    text = (
        "| Hub Dia. | Flange Dia. | Flange Width |\n"
        "|---|---|---|\n"
        "| 940.0 | 971.6 | 9.5 |\n"
        "|  | 1,000.0 1,031.6 | 9.5 |\n"
    )
    assert clean_in_place(text) == (
        "| Hub Dia. | Flange Dia. | Flange Width |\n"
        "|----------|-------------|--------------|\n"
        "| 940.0    | 971.6       | 9.5          |\n"
        "| 1,000.0  | 1,031.6     | 9.5          |\n"
    )


def test_swallowed_cell_recut_spans_three_columns() -> None:
    text = (
        "| A | B | C | D |\n"
        "|---|---|---|---|\n"
        "| 1 | 2 | 3 | 4 |\n"
        "| 10 20 30 |  |  | 40 |\n"
    )
    assert clean_in_place(text) == (
        "| A  | B  | C  | D  |\n"
        "|----|----|----|----|\n"
        "| 1  | 2  | 3  | 4  |\n"
        "| 10 | 20 | 30 | 40 |\n"
    )


def test_two_swallowed_cells_in_one_row_are_both_recut() -> None:
    text = (
        "| A | B | C | D | E | F |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | 2 | 3 | 4 | 5 | 6 |\n"
        "| 10 20 |  | 30 | 40 50 |  | 60 |\n"
    )
    assert clean_in_place(text) == (
        "| A  | B  | C  | D  | E  | F  |\n"
        "|----|----|----|----|----|----|\n"
        "| 1  | 2  | 3  | 4  | 5  | 6  |\n"
        "| 10 | 20 | 30 | 40 | 50 | 60 |\n"
    )


def test_two_runs_reaching_for_one_blank_cell_are_left_alone() -> None:
    text = (
        "| A     | B | C     |\n"
        "|-------|---|-------|\n"
        "| 1     | 2 | 3     |\n"
        "| 10 20 |   | 30 40 |\n"
    )
    assert clean_in_place(text) == text


def test_a_run_too_wide_to_place_blocks_no_other() -> None:
    # `30 40 50` fits no reading, so it blocks neither blank cell.
    text = (
        "| A | B | C | D | E |\n"
        "|---|---|---|---|---|\n"
        "| 1 | 2 | 3 | 4 | 5 |\n"
        "| 10 20 |  | 30 40 50 |  |  |\n"
    )
    assert clean_in_place(text) == (
        "| A  | B  | C  | D  | E  |\n"
        "|----|----|----|----|----|\n"
        "| 1  | 2  | 3  | 4  | 5  |\n"
        "| 10 | 20 | 30 | 40 | 50 |\n"
    )


def test_more_values_than_blank_cells_is_left_alone() -> None:
    text = (
        "| A        | B | C  |\n"
        "|----------|---|----|\n"
        "| 1        | 2 | 3  |\n"
        "| 10 20 30 |   | 40 |\n"
    )
    assert clean_in_place(text) == text


def test_fewer_values_than_blank_cells_is_left_alone() -> None:
    text = (
        "| A     | B | C | D  |\n"
        "|-------|---|---|----|\n"
        "| 1     | 2 | 3 | 4  |\n"
        "| 10 20 |   |   | 40 |\n"
    )
    assert clean_in_place(text) == text


def test_swallowed_values_do_not_cross_a_cell_holding_text() -> None:
    text = (
        "| A     | B | C  |\n"
        "|-------|---|----|\n"
        "| 1     | 2 | 3  |\n"
        "| 10 20 | x | 30 |\n"
    )
    assert clean_in_place(text) == text


def test_a_cell_of_several_words_is_not_a_run_of_values() -> None:
    text = (
        "| A               | B | C  |\n"
        "|-----------------|---|----|\n"
        "| 1               | 2 | 3  |\n"
        "| 1,021.00 x 7.60 |   | 30 |\n"
    )
    assert clean_in_place(text) == text


def test_a_run_of_part_numbers_is_left_alone() -> None:
    text = (
        "| A           | B | C  |\n"
        "|-------------|---|----|\n"
        "| x           | y | 3  |\n"
        "| 4-035 4-036 |   | 30 |\n"
    )
    assert clean_in_place(text) == text


def test_recut_into_a_column_holding_no_value_is_refused() -> None:
    text = (
        "| A     |       | C  |\n"
        "|-------|-------|----|\n"
        "| 1     | words | 3  |\n"
        "| 10 20 |       | 30 |\n"
    )
    assert clean_in_place(text) == text


def test_recut_into_a_column_only_the_header_names_is_allowed() -> None:
    text = "| A | B | C |\n|---|---|---|\n| 1 2 |  | 3 |\n| 10 20 |  | 30 |\n"
    assert clean_in_place(text) == (
        "| A  | B  | C  |\n|----|----|----|\n| 1  | 2  | 3  |\n| 10 | 20 | 30 |\n"
    )


def test_swallowed_cell_recut_keeps_row_indentation() -> None:
    text = "  | A | B |\n  |---|---|\n  | 1 | 2 |\n  | 10 20 |  |\n"
    assert clean_in_place(text) == (
        "  | A  | B  |\n  |----|----|\n  | 1  | 2  |\n  | 10 | 20 |\n"
    )


def test_table_without_a_separator_is_not_recut() -> None:
    # No separator exists yet when this rule runs.
    text = "| A | B |\n| 1 | 2 |\n| 10 20 |  |\n"
    assert clean_in_place(text) == (
        "| A     | B |\n|-------|---|\n| 1     | 2 |\n| 10 20 |   |\n"
    )


def test_row_off_the_table_width_blocks_the_recut() -> None:
    text = "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n| 10 20 |  | 30 |\n"
    assert clean_in_place(text) == text


def test_swallowed_cell_in_the_header_is_left_alone() -> None:
    text = "| 10 20 |   | C |\n|-------|---|---|\n| 1     | 2 | 3 |\n"
    assert clean_in_place(text) == text


def test_swallowed_cell_recut_inside_fence_is_not_touched() -> None:
    text = "```\n| A | B |\n|---|---|\n| 1 | 2 |\n| 10 20 |  |\n```\n"
    assert clean_in_place(text) == text


def test_swallowed_cell_recut_is_idempotent() -> None:
    once = clean_in_place(_SWALLOWED_CELL_TABLE)
    assert clean_in_place(once) == once


# ---- in-place fix: a crushed run the table's own columns place ----------------

# A part number and two measures crushed into one cell beside blank columns.
_CRUSHED_RUN_TABLE = (
    "| Code | Size | Mass | Note |\n"
    "|---|---|---|---|\n"
    "| 4-236 | 104.20 | 4.60 | ring |\n"
    "| 4-235 103.87 4.52 |  |  | ring |\n"
)


def test_crushed_run_is_laid_over_the_columns_that_carry_its_forms() -> None:
    assert clean_in_place(_CRUSHED_RUN_TABLE) == laid_out_table(
        "| Code | Size | Mass | Note |",
        "| 4-236 | 104.20 | 4.60 | ring |",
        "| 4-235 | 103.87 | 4.52 | ring |",
    )


def test_a_laid_out_crushed_run_is_no_longer_reported() -> None:
    assert "broken-table" not in _reported(_CRUSHED_RUN_TABLE)


def test_crushed_run_layout_is_idempotent() -> None:
    once = clean_in_place(_CRUSHED_RUN_TABLE)
    assert clean_in_place(once) == once


def test_a_run_its_columns_place_in_two_ways_is_left_alone() -> None:
    text = laid_out_table(
        "| Code | Bore | Cross | Width |",
        "| 4-236 | 104.20 | 108.10 | 109.90 |",
        "| 4-235 | 103.87 103.23 |  |  |",
    )
    assert clean_in_place(text) == text


def test_a_run_no_column_confirms_is_left_alone() -> None:
    text = laid_out_table(
        "| Code | Mass | Note |",
        "| A-1 | 12.5 | ring |",
        "| 4-235 103.87 |  | ring |",
    )
    assert clean_in_place(text) == text


def test_a_number_typeset_with_group_spaces_is_left_alone() -> None:
    # `23 510` is one number set with a group space.
    text = laid_out_table(
        "| Alloy group | Group | Abbreviation | Standard |",
        "| cold strip | 2715 | 418 | 2.0418 |",
        "| tool alloys | 23 510 |  |  |",
    )
    assert clean_in_place(text) == text


def test_a_sole_cell_breaking_two_integers_apart_is_anchored() -> None:
    # Two `<br>` lines in a lone cell were printed apart; no group space here.
    text = laid_out_table(
        "| Code | Count |",
        "| 41 | 700 |",
        "| 12 | 305 |",
        "| 13<br>260 |  |",
    )
    assert "broken-table collapsed=2 width=2" in _reported(text)


def test_a_run_placed_beside_its_own_cell_is_left_alone() -> None:
    text = laid_out_table(
        "| Code | Bore | Cross |",
        "| A-1 | 38.21 | 4.52 |",
        "| 38.21 4.52 |  |  |",
    )
    assert clean_in_place(text) == text


def test_a_run_a_break_stack_holds_is_left_alone() -> None:
    text = laid_out_table(
        "| Code | Bore | Cross | Width |",
        "| 4-216 | 38.21 | 4.52 | 7.2 |",
        "| 4-217 | 38.21 4.52<br>39.74 4.52 |  | 7.2 |",
    )
    assert clean_in_place(text) == text


def test_a_crushed_run_in_the_header_is_left_alone() -> None:
    text = laid_out_table(
        "| 4-235 103.87 4.52 |  |  | Note |",
        "| 4-236 | 104.20 | 4.60 | ring |",
    )
    assert clean_in_place(text) == text


def test_a_crushed_run_on_a_row_off_the_width_is_left_alone() -> None:
    text = (
        "| Code | Size | Mass | Note |\n"
        "|---|---|---|---|\n"
        "| 4-236 | 104.20 | 4.60 | ring |\n"
        "| 4-235 103.87 4.52 |  |  |\n"
    )
    assert clean_in_place(text) == text


def test_crushed_run_layout_inside_a_fence_is_not_touched() -> None:
    text = f"```\n{_CRUSHED_RUN_TABLE}```\n"
    assert clean_in_place(text) == text


# ---- in-place fix: empty table columns ---------------------------------------


def test_empty_table_column_is_dropped() -> None:
    text = "| A |  | C |\n|---|---|---|\n| 1 |  | 3 |\n| 4 |  | 6 |\n"
    assert clean_in_place(text) == "| A | C |\n|---|---|\n| 1 | 3 |\n| 4 | 6 |\n"


def test_empty_table_column_drop_keeps_row_indentation() -> None:
    text = "  | A |  | C |\n  |---|---|---|\n  | 1 |  | 3 |\n"
    assert clean_in_place(text) == "  | A | C |\n  |---|---|\n  | 1 | 3 |\n"


def test_table_column_with_header_content_is_kept() -> None:
    text = "| A | B | C |\n|---|---|---|\n| 1 |   | 3 |\n| 4 |   | 6 |\n"
    assert clean_in_place(text) == text


def test_table_column_with_only_the_header_empty_is_kept() -> None:
    text = "| A |   | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 |   | 6 |\n"
    assert clean_in_place(text) == text


def test_mismatched_table_row_blocks_the_empty_column_fix() -> None:
    text = "| A |  | C |\n|---|---|---|\n| 1 |  |\n"
    assert clean_in_place(text) == text


def test_empty_table_column_inside_fence_is_not_touched() -> None:
    text = "```\n| A |  | C |\n|---|---|---|\n| 1 |  | 3 |\n```\n"
    assert clean_in_place(text) == text


def test_empty_table_column_drop_is_idempotent() -> None:
    text = "| A |  | C |\n|---|---|---|\n| 1 |  | 3 |\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- table: paragraph glued onto the header ----------------------------------

# A paragraph glued onto the header line; the cut proves out to width 2.
_GLUED_HEADER_TABLE = (
    "**Book title** | PREFACE | 5 |\n"
    "|---|---|\n"
    "| CHAPTER 1 | 12 |\n"
    "| CHAPTER 2 | 30 |\n"
    "| CHAPTER 3 | 44 |\n"
)


def test_glued_table_header_paragraph_is_split() -> None:
    assert clean_in_place(_GLUED_HEADER_TABLE) == (
        "**Book title**\n"
        "\n"
        "| PREFACE   | 5  |\n"
        "|-----------|----|\n"
        "| CHAPTER 1 | 12 |\n"
        "| CHAPTER 2 | 30 |\n"
        "| CHAPTER 3 | 44 |\n"
    )


def test_glued_table_header_split_leaves_no_anchor() -> None:
    assert "broken-table" not in _reported(_GLUED_HEADER_TABLE)


def test_glued_table_header_split_is_idempotent() -> None:
    once = clean_in_place(_GLUED_HEADER_TABLE)
    assert clean_in_place(once) == once


def test_glued_table_header_split_keeps_row_indentation() -> None:
    text = "  prose | A | B |\n  |---|---|\n  | 1 | 2 |\n"
    assert clean_in_place(text) == (
        "  prose\n\n  | A | B |\n  |---|---|\n  | 1 | 2 |\n"
    )


def test_table_header_without_a_leading_pipe_is_untouched() -> None:
    text = "A | B\n--|--\n1 | 2\n"
    assert clean_in_place(text) == text


def test_table_header_glue_left_for_anchor_when_cut_does_not_match_width() -> None:
    # Two cells ahead of the header; one cut still misses the width.
    text = "prose one | prose two | A | B |\n|---|---|\n| 1 | 2 |\n"
    assert clean_in_place(text) == text
    assert "broken-table" in _reported(text)


def test_glued_text_on_a_body_row_is_left_for_the_row_anchor() -> None:
    text = "| A | B |\n|---|---|\nprose glued | 1 | 2 |\n| 3 | 4 |\n"
    assert clean_in_place(text) == text


def test_glued_table_header_split_inside_fence_is_not_touched() -> None:
    text = "```\n**Title** | A | B |\n|---|---|\n| 1 | 2 |\n```\n"
    assert clean_in_place(text) == text


def test_setext_heading_with_a_pipe_is_not_split_as_a_table_header() -> None:
    text = "A | B\n---\n\nFollowing paragraph.\n"
    assert clean_in_place(text) == text


def test_well_formed_one_column_table_without_a_leading_pipe_is_untouched() -> None:
    # `A |` counts one cell; its pipe is the closing border.
    text = "A |\n---\nB |\n"
    assert clean_in_place(text) == text


# ---- in-place fix: a table printed several columns of records up -------------

# Two columns of records printed side by side, delivered as one wide grid.
_TWO_UP_TABLE = (
    "| Code | Length | Mass | Code | Length | Mass |\n"
    "|---|---|---|---|---|---|\n"
    "| A-1 | 12.5 | 3.20 | A-4 | 15.5 | 4.20 |\n"
    "| A-2 | 13.5 | 3.40 | A-5 | 16.5 | 4.40 |\n"
    "| A-3 | 14.5 | 3.60 | A-6 | 17.5 | 4.60 |\n"
)


def _row_cells(text: str) -> list[str]:
    """The cell texts of every table row in `text`, the separators left out."""
    return [
        cell.strip()
        for line in text.splitlines()
        if "|" in line and not is_table_separator(line.strip())
        for cell in line.strip().strip("|").split("|")
    ]


def test_a_two_up_table_is_folded_to_one_cycle() -> None:
    # A two-up catalogue numbers down the left column, then the right one.
    assert clean_in_place(_TWO_UP_TABLE) == (
        "| Code | Length | Mass |\n"
        "|------|--------|------|\n"
        "| A-1  | 12.5   | 3.20 |\n"
        "| A-2  | 13.5   | 3.40 |\n"
        "| A-3  | 14.5   | 3.60 |\n"
        "| A-4  | 15.5   | 4.20 |\n"
        "| A-5  | 16.5   | 4.40 |\n"
        "| A-6  | 17.5   | 4.60 |\n"
    )


def test_the_fold_drops_nothing_but_the_header_copy() -> None:
    before = Counter(_row_cells(_TWO_UP_TABLE))
    after = Counter(_row_cells(clean_in_place(_TWO_UP_TABLE)))
    assert before - after == Counter({"Code": 1, "Length": 1, "Mass": 1})
    assert after - before == Counter()


def test_a_three_up_table_is_folded_to_one_cycle() -> None:
    text = (
        "| No. | Part | No. | Part | No. | Part |\n"
        "|---|---|---|---|---|---|\n"
        "| 1 | A-1 | 3 | A-3 | 5 | A-5 |\n"
        "| 2 | A-2 | 4 | A-4 | 6 | A-6 |\n"
    )
    assert clean_in_place(text) == (
        "| No. | Part |\n"
        "|-----|------|\n"
        "| 1   | A-1  |\n"
        "| 2   | A-2  |\n"
        "| 3   | A-3  |\n"
        "| 4   | A-4  |\n"
        "| 5   | A-5  |\n"
        "| 6   | A-6  |\n"
    )


def test_a_part_the_page_left_empty_is_dropped_from_the_tail() -> None:
    text = (
        "| Code | Mass | Code | Mass |\n"
        "|---|---|---|---|\n"
        "| A-1 | 3.20 | A-3 | 4.20 |\n"
        "| A-2 | 3.40 |  |  |\n"
    )
    assert clean_in_place(text) == (
        "| Code | Mass |\n"
        "|------|------|\n"
        "| A-1  | 3.20 |\n"
        "| A-2  | 3.40 |\n"
        "| A-3  | 4.20 |\n"
    )


def test_a_header_of_distinct_titles_is_not_folded() -> None:
    text = (
        "| Code | Length | Mass | Note |\n"
        "|------|--------|------|------|\n"
        "| A-1  | 12.5   | 3.20 | ok   |\n"
    )
    assert clean_in_place(text) == text


def test_a_row_off_the_block_width_blocks_the_fold() -> None:
    text = (
        "| Code | Mass | Code | Mass |\n"
        "|---|---|---|---|\n"
        "| A-1 | 3.20 | A-3 | 4.20 |\n"
        "| A-2 | 3.40 |\n"
    )
    assert clean_in_place(text) == text


def test_a_header_repeating_a_bare_value_is_not_folded() -> None:
    # A numeric grid can print figures where the header belongs.
    text = (
        "| 0.0 | 0.0 | 0.0 | 0.0 |\n"
        "|-----|-----|-----|-----|\n"
        "| 0.0 | 1.0 | 2.0 | 3.0 |\n"
        "| 4.0 | 5.0 | 6.0 | 7.0 |\n"
    )
    assert clean_in_place(text) == text


def test_a_header_repeating_one_title_is_not_folded() -> None:
    text = (
        "| Symbol | Symbol | Symbol | Symbol |\n"
        "|--------|--------|--------|--------|\n"
        "| a      | b      | c      | d      |\n"
    )
    assert clean_in_place(text) == text


def test_a_block_behind_a_second_separator_is_left_to_the_collapse() -> None:
    text = "| Code | Mass | Code | Mass |\n|---|---|---|---|\n|---|---|---|---|\n"
    assert clean_in_place(text) == "Code Mass Code Mass\n"


def test_a_page_mark_inside_a_folded_table_moves_below_its_rows() -> None:
    text = (
        "| Code | Mass | Code | Mass |\n"
        "|---|---|---|---|\n"
        "| A-1 | 3.20 | A-3 | 4.20 |\n"
        f"{page_mark(7)}\n"
        "| A-2 | 3.40 | A-4 | 4.40 |\n"
    )
    out = clean_in_place(text).splitlines()
    assert out[-1] == page_mark(7)
    assert out[2:-1] == [
        "| A-1  | 3.20 |",
        "| A-2  | 3.40 |",
        "| A-3  | 4.20 |",
        "| A-4  | 4.40 |",
    ]


def test_the_fold_is_idempotent() -> None:
    once = clean_in_place(_TWO_UP_TABLE)
    assert clean_in_place(once) == once


def test_the_fold_inside_a_fence_is_not_touched() -> None:
    text = f"```\n{_TWO_UP_TABLE}```\n"
    assert clean_in_place(text) == text


# ---- in-place fix: a table a page break cut in two ---------------------------

# The next page reprints the titles; a page mark stands in the cut.
_SPLIT_TABLE = (
    "| Series | Diameter | Length |\n"
    "|---|---|---|\n"
    "| KRX0210 | 240 | 60 |\n"
    "| KRX0291 | 320 | 90 |\n"
    "\n"
    f"{page_mark(12)}\n"
    "| Series | Diameter | Length |\n"
    "|---|---|---|\n"
    "| KRX0360 | 395 | 90 |\n"
    "| KRX0450 | 495 | 110 |\n"
)

_REUNITED_TABLE = (
    "| Series  | Diameter | Length |\n"
    "|---------|----------|--------|\n"
    "| KRX0210 | 240      | 60     |\n"
    "| KRX0291 | 320      | 90     |\n"
    "| KRX0360 | 395      | 90     |\n"
    "| KRX0450 | 495      | 110    |\n"
)


def test_table_a_page_break_cut_in_two_is_reunited() -> None:
    assert clean_in_place(_SPLIT_TABLE) == _REUNITED_TABLE + f"{page_mark(12)}\n"


def test_reunited_table_is_idempotent() -> None:
    once = clean_in_place(_SPLIT_TABLE)
    assert clean_in_place(once) == once


def test_reunited_table_leaves_no_anchor() -> None:
    assert "broken-table" not in _reported(_SPLIT_TABLE)


def test_page_mark_in_the_cut_stands_above_the_block_after_the_table() -> None:
    text = _SPLIT_TABLE + "\nFollowing paragraph.\n"
    assert clean_in_place(text) == (
        _REUNITED_TABLE + f"\n{page_mark(12)}\nFollowing paragraph.\n"
    )


def test_table_cut_over_two_page_breaks_is_reunited_whole() -> None:
    text = _SPLIT_TABLE + (
        "\n"
        f"{page_mark(13)}\n"
        "| Series | Diameter | Length |\n"
        "|---|---|---|\n"
        "| KRX0600 | 650 | 130 |\n"
    )
    assert clean_in_place(text) == (
        _REUNITED_TABLE
        + "| KRX0600 | 650      | 130    |\n"
        + f"{page_mark(12)}\n{page_mark(13)}\n"
    )


def test_reunited_header_padded_to_another_width_is_still_a_reprint() -> None:
    text = (
        "| Series   | Load |\n"
        "|---|---|\n"
        "| KRX0210  | 60   |\n"
        "\n"
        "| Series | Load     |\n"
        "|---|---|\n"
        "| KRX0360  | 90   |\n"
    )
    assert clean_in_place(text) == (
        "| Series  | Load |\n"
        "|---------|------|\n"
        "| KRX0210 | 60   |\n"
        "| KRX0360 | 90   |\n"
    )


def test_continuation_of_another_width_is_not_reunited() -> None:
    text = (
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n| A | B |\n|---|---|---|\n| 3 | 4 | 5 |\n"
    )
    assert clean_in_place(text) == text


def test_continuation_carrying_titles_of_its_own_is_not_reunited() -> None:
    text = (
        "| Specifications | Units |\n"
        "|----------------|-------|\n"
        "| Peak thrust    | Nm    |\n"
        "\n"
        "| Ratings     | Units |\n"
        "|-------------|-------|\n"
        "| Coil supply | V     |\n"
    )
    assert clean_in_place(text) == text


def test_table_split_by_a_paragraph_is_not_reunited() -> None:
    text = (
        "| Feature | Value  |\n"
        "|---------|--------|\n"
        "| Gap     | 0.4 mm |\n"
        "\n"
        "Coolant is harder to flush out of a narrow slot.\n"
        "\n"
        "| Feature | Value  |\n"
        "|---------|--------|\n"
        "| Gap     | 0.8 mm |\n"
    )
    assert clean_in_place(text) == text


def test_table_split_by_a_picture_is_not_reunited() -> None:
    text = (
        "| Feature | Value  |\n"
        "|---------|--------|\n"
        "| Gap     | 0.4 mm |\n"
        "\n"
        "![](media/_page_4_Figure_1.jpeg)\n"
        "\n"
        "| Feature | Value  |\n"
        "|---------|--------|\n"
        "| Gap     | 0.8 mm |\n"
    )
    assert clean_in_place(text) == text


def test_heading_reprinted_over_a_bare_underline_is_not_reunited() -> None:
    text = "A | B\n---\n\nA | B\n---\n\nFollowing paragraph.\n"
    assert clean_in_place(text) == text


def test_table_reunion_inside_fence_is_not_touched() -> None:
    text = (
        "```\n| A | B |\n|---|---|\n| 1 | 2 |\n\n| A | B |\n|---|---|\n| 3 | 4 |\n```\n"
    )
    assert clean_in_place(text) == text


def test_reunited_row_off_the_width_is_measured_against_the_one_separator() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n\n| A | B |\n|---|---|\n| 3 |\n"
    assert clean(text) == "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 |\n"
    assert _reported(text) == "broken-table expected=2 got=1"


def test_column_only_the_continuation_fills_survives_the_reunion() -> None:
    # Read page by page, the empty-column drop would take this column.
    text = "| A | B |\n|---|---|\n|  | 2 |\n\n| A | B |\n|---|---|\n| 3 | 4 |\n"
    assert clean_in_place(text) == "| A | B |\n|---|---|\n|   | 2 |\n| 3 | 4 |\n"


# ---- anchoring: broken table -------------------------------------------------


def test_broken_table_row_is_reported() -> None:
    text = "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n"
    assert clean(text) == text
    assert _reported(text) == "broken-table expected=3 got=2"


def test_consistent_table_is_not_anchored() -> None:
    text = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    assert clean(text) == text


def test_broken_table_inside_fence_is_not_anchored() -> None:
    text = "```\n| A | B |\n|---|---|\n| 1 |\n```\n"
    assert clean(text) == text


def test_body_row_short_a_cell_is_still_reported_per_row() -> None:
    text = "| A | B |\n|---|---|\n| 1 |\n| 2 | 3 |\n| 4 |\n"
    assert _reported(text).count("broken-table expected=2 got=1") == 2


def test_pipe_line_over_a_setext_underline_is_not_a_table() -> None:
    text = "Value | unit\n---\n\nFollowing paragraph.\n"
    assert "broken-table" not in _reported(text)


def test_table_no_row_confirms_is_not_measured() -> None:
    text = "| A | B | C |\n|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n"
    assert "broken-table" not in _reported(text)


# ---- anchoring: a grid collapsed into one cell -------------------------------

# The whole row crushed into one cell; the cell count still agrees.
_COLLAPSED_ROW_TABLE = (
    "| Fluid   | Rating | Code                 |\n"
    "|---------|--------|----------------------|\n"
    "| Acetone | 4      | K2210                |\n"
    "|         |        | Xylene<br>1<br>K5184 |\n"
)


def test_row_crushed_into_one_cell_is_anchored() -> None:
    assert "broken-table collapsed=3 width=3" in _reported(_COLLAPSED_ROW_TABLE)


def test_row_crushed_into_one_cell_is_not_repaired_in_place() -> None:
    assert clean_in_place(_COLLAPSED_ROW_TABLE) == _COLLAPSED_ROW_TABLE


def test_collapsed_row_report_is_the_same_on_a_second_pass() -> None:
    cleaned = clean(_COLLAPSED_ROW_TABLE)
    assert cleaned == _COLLAPSED_ROW_TABLE
    assert _reported(cleaned) == _reported(_COLLAPSED_ROW_TABLE)


def test_run_of_columns_crushed_mid_row_is_anchored() -> None:
    # A partial crush keeps the width; two placements fit, so it is only reported.
    text = (
        "| Code | Bore | Cross | Width |\n"
        "|---|---|---|---|\n"
        "| 4-236 | 104.20 | 108.10 | 109.90 |\n"
        "| 4-235 | 103.87 103.23 |  |  |\n"
    )
    assert "broken-table collapsed=2 width=4" in _reported(text)


def test_a_repeated_header_crushed_into_one_cell_is_not_anchored() -> None:
    # The header has the title form, so it cannot confirm its own repeat.
    text = (
        "| Type | Size | Mass |\n"
        "|---|---|---|\n"
        "| R-12 | 12.5 | 0.31 |\n"
        "| Type<br>Size<br>Mass |  |  |\n"
        "| R-14 | 14.0 | 0.44 |\n"
    )
    assert "broken-table" not in _reported(text)


def test_a_row_of_units_under_the_titles_is_not_anchored() -> None:
    text = (
        "| Bore | Stroke | Ratio |\n"
        "|---|---|---|\n"
        "| mm<br>mm<br>% |  |  |\n"
        "| 40.0 | 36.0 | 8.5 |\n"
    )
    assert "broken-table" not in _reported(text)


def test_a_number_printed_with_group_spaces_is_not_anchored() -> None:
    # `1 250 000` is one value set with group spaces.
    text = (
        "| Code | Mass | Note |\n"
        "|---|---|---|\n"
        "| A-1 | 12.5 | ring |\n"
        "| 1 250 000 |  |  |\n"
    )
    assert "broken-table" not in _reported(text)


def test_only_the_rows_their_own_columns_confirm_are_counted() -> None:
    # Header repeats outnumber the damaged rows in a catalogue.
    repeat = "| Type<br>Size<br>Mass |  |  |\n"
    text = (
        "| Type | Size | Mass |\n"
        "|---|---|---|\n"
        "| R-12 | 12.5 | 0.31 |\n" + repeat * 4 + "| R-14<br>14.0<br>0.44 |  |  |\n"
    )
    assert _reported(text).count("broken-table") == 1


# One cell of a two-row stack carries two values on each line.
_STACKED_ROW_TABLE = laid_out_table(
    "| Code | Bore | Cross | Width |",
    "| 4-216 | 38.21 | 4.52 | 7.2 |",
    "| 4-217<br>4-218 | 38.21 4.52<br>39.74 4.52 |  | 7.2<br>7.2 |",
)


def test_a_cell_stacking_two_values_to_a_line_is_anchored() -> None:
    # The run spans two columns, not four values.
    text = laid_out_table(
        "| Code | Bore | Cross | Width |",
        "| 4-216 | 38.21 | 4.52 | 7.2 |",
        "| 4-217<br>4-218 | 38.21 4.52<br>39.74 4.52 |  | 7.2 |",
    )
    assert "broken-table collapsed=2 width=4" in _reported(text)


def test_a_stacked_row_names_one_run_and_no_more() -> None:
    assert _reported(_STACKED_ROW_TABLE) == "broken-table collapsed=2 width=4"


def test_a_stacked_row_is_not_repaired_in_place() -> None:
    assert clean_in_place(_STACKED_ROW_TABLE) == _STACKED_ROW_TABLE


def test_a_cell_stacking_one_value_to_a_line_is_not_anchored() -> None:
    text = (
        "| Code | Bore | Cross | Width |\n"
        "|---|---|---|---|\n"
        "| 4-216 | 38.21 | 4.52 | 7.2 |\n"
        "| 4-217 | 39.74 |  | 7.2<br>7.2 |\n"
    )
    assert "broken-table" not in _reported(text)


def test_a_stack_whose_lines_disagree_on_their_width_is_not_anchored() -> None:
    text = (
        "| Code | Bore | Cross | Width |\n"
        "|---|---|---|---|\n"
        "| 4-216 | 38.21 | 4.52 | 7.2 |\n"
        "| 4-217 | 38.21 4.52<br>39.74 |  | 7.2 |\n"
    )
    assert "broken-table" not in _reported(text)


# No row of the block kept its grid.
_UNWITNESSED_RUN_TABLE = laid_out_table(
    "| Code | Size | Mass |",
    "| 4-235 103.87 4.52 |  |  |",
    "| 4-236 104.20 4.60 |  |  |",
)


def test_a_run_no_row_of_the_block_confirms_is_anchored() -> None:
    # Unknown columns neither confirm nor refuse the run.
    assert _reported(_UNWITNESSED_RUN_TABLE) == "\n".join(
        ["broken-table collapsed=3 width=3"] * 2
    )


def test_a_run_no_row_of_the_block_confirms_is_not_repaired() -> None:
    assert clean_in_place(_UNWITNESSED_RUN_TABLE) == _UNWITNESSED_RUN_TABLE


def test_words_without_digits_beside_blank_columns_are_not_anchored() -> None:
    text = (
        "| Term | A | B | C |\n"
        "|---|---|---|---|\n"
        "| the pressure of the gas |  |  |  |\n"
    )
    assert "broken-table" not in _reported(text)


def test_two_runs_claiming_one_blank_column_are_not_anchored() -> None:
    text = "| A | B | C |\n|---|---|---|\n| 1.5 2.5 |  | 3.5 4.5 |\n"
    assert "broken-table" not in _reported(text)


def test_a_stacked_title_beside_a_filled_cell_is_not_anchored() -> None:
    text = "| A | B | C |\n|---|---|---|\n| Speed<br>rpm |  | 5 |\n"
    assert "broken-table" not in _reported(text)


def test_multiline_header_cell_is_not_anchored() -> None:
    text = (
        "| Finish | k<br>q > 40 %<br>Rz<br>[μm] | Rtot. |\n"
        "|---|---|---|\n"
        "| Honed | 0.6 | 2.4 |\n"
    )
    assert "broken-table" not in _reported(text)


def test_full_grid_with_wrapped_cells_is_not_anchored() -> None:
    text = (
        "| Cold<br>press-fit<br>joint | Hot<br>shrink-fit<br>joint |\n"
        "|---|---|\n"
        "| Heat the hub<br>first | Press |\n"
    )
    assert "broken-table" not in _reported(text)


def test_value_wrapped_across_lines_in_a_lone_cell_is_not_anchored() -> None:
    text = (
        "| Pros | Cons |\n"
        "|---|---|\n"
        "| Quick setup | Coarse edge finish |\n"
        "| Can cut thin plates for<br>small welded frames |  |\n"
    )
    assert "broken-table" not in _reported(text)


def test_one_column_table_row_is_not_a_collapsed_grid() -> None:
    text = "| Item |\n|---|\n| a<br>b<br>c |\n"
    assert "broken-table" not in _reported(text)


def test_a_separator_first_block_that_cannot_render_is_reported() -> None:
    text = "Intro paragraph.\n\n|---|---|\n| a | b | c |\n| 1 | 2 |\n"
    assert clean(text) == text
    assert _reported(text) == "broken-table header=missing"


def test_a_blank_cell_header_dropped_lets_the_separator_sink() -> None:
    text = "|  |  |\n|---|---|\n| 1 | 2 |\n"
    assert clean(text) == "| 1 | 2 |\n|---|---|\n"
    assert "broken-table" not in _reported(text)


def test_the_missing_header_report_is_the_same_on_a_second_pass() -> None:
    text = "Intro paragraph.\n\n|---|---|\n| a | b | c |\n| 1 | 2 |\n"
    assert _reported(clean(text)) == _reported(text)


def test_headerless_block_no_row_confirms_is_not_a_table() -> None:
    text = "Intro paragraph.\n\n|---|---|---|\n| 1 | 2 |\n"
    assert "broken-table" not in _reported(text)


def test_thematic_break_is_not_a_headerless_table() -> None:
    text = "Intro paragraph.\n\n---\n\nNext paragraph.\n"
    assert "broken-table" not in _reported(text)


def test_a_row_both_off_width_and_crushed_is_reported_once() -> None:
    text = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| x<br>y<br>z |  |\n"
    assert _reported(text) == "broken-table expected=3 got=2"


def test_collapsed_grid_inside_fence_is_not_anchored() -> None:
    text = "```\n| A | B |\n|---|---|\n|  | a<br>b<br>c |\n```\n"
    assert clean(text) == text


# ---- in-place fix: a contents list rendered as a one-column table -----------

_CONTENTS_TABLE = (
    "Preceding paragraph.\n\n"
    "| 7 Applications 89 |\n"
    "|-------------------|\n"
    "| 7.1 Rail vehicles 89 |\n"
    "| 7.1.1 Bogie 89 |\n"
    "| 7.2 Medical devices 90 |\n"
    "| 7.3 Food processing 90 |\n\n"
    "Following paragraph.\n"
)


def test_contents_rendered_as_a_one_column_table_is_laid_back_out() -> None:
    assert clean_in_place(_CONTENTS_TABLE) == (
        "Preceding paragraph.\n\n"
        "7 Applications 89\n"
        "7.1 Rail vehicles 89\n"
        "7.1.1 Bogie 89\n"
        "7.2 Medical devices 90\n"
        "7.3 Food processing 90\n\n"
        "Following paragraph.\n"
    )


def test_a_stacked_contents_cell_is_split_at_every_break() -> None:
    text = (
        "| 7 Applications 89<br>7.1 Rail vehicles 89 |\n"
        "|---|\n"
        "| 7.1.1 Bogie 89 |\n"
        "| 7.1.2 Door system 89 |\n"
    )
    assert clean_in_place(text) == (
        "7 Applications 89\n"
        "7.1 Rail vehicles 89\n"
        "7.1.1 Bogie 89\n"
        "7.1.2 Door system 89\n"
    )


def test_a_dot_leader_between_a_title_and_its_page_is_squeezed() -> None:
    text = (
        "| 1 Introduction . . . . . . 7 |\n"
        "|---|\n"
        "| 1.1 Scope . . . . . . 7 |\n"
        "| 1.2 References . . . . . . 8 |\n"
    )
    assert clean_in_place(text) == ("1 Introduction 7\n1.1 Scope 7\n1.2 References 8\n")


def test_a_one_column_table_of_plain_phrases_is_left_alone() -> None:
    text = (
        "| Stock grades        |\n"
        "|---------------------|\n"
        "| Glass-filled nylons |\n"
        "| Closed-cell foam    |\n"
        "| Felt                |\n"
    )
    assert clean_in_place(text) == text


def test_a_one_column_table_of_dimension_ranges_is_left_alone() -> None:
    text = "| 12.0 - 455.0 |\n|--------------|\n| 12.0 - 655.0 |\n| 38.0 - 655.0 |\n"
    assert clean_in_place(text) == text


def test_a_flat_numbered_column_without_a_dotted_number_is_left_alone() -> None:
    text = "| 1 Steel 200  |\n|--------------|\n| 2 Iron 190   |\n| 3 Copper 390 |\n"
    assert clean_in_place(text) == text


def test_a_two_column_contents_table_is_left_to_the_post_stage() -> None:
    text = (
        "| 1 Introduction 7 | 5 Accessories 63 |\n"
        "|------------------|------------------|\n"
        "| 1.1 Scope 7      | 5.1 Grease 63    |\n"
    )
    assert clean_in_place(text) == text


def test_a_short_one_column_contents_block_is_left_alone() -> None:
    text = "| 1 Introduction 7 |\n|------------------|\n| 1.1 Scope 7      |\n"
    assert clean_in_place(text) == text


def test_contents_table_decomposition_is_idempotent() -> None:
    once = clean(_CONTENTS_TABLE)
    assert clean(once) == once


def test_contents_table_decomposition_reports_no_finding() -> None:
    assert not clean_with_report(_CONTENTS_TABLE).findings


# ---- in-place fix: an in-cell break inside a printed contents zone ------------


def _contents_zone_body(*rows: str) -> str:
    """A body opening with a printed contents table under a contents heading."""
    return "# Contents\n\n" + laid_out_table("| Section | Title | Page |", *rows)


def test_a_contents_title_broken_after_every_word_is_glued() -> None:
    text = _contents_zone_body(
        "| 4.2.5 | Grid-Based<br>Versus<br>Models | 73 |",
        "| 4.2.6 | Layout<br>to<br>Avoid<br>Distortion<br> | 74 |",
        "| 4.3 | Overview | 80 |",
    )
    assert clean_in_place(text) == _contents_zone_body(
        "| 4.2.5 | Grid-Based Versus Models | 73 |",
        "| 4.2.6 | Layout to Avoid Distortion | 74 |",
        "| 4.3 | Overview | 80 |",
    )


def test_a_contents_cell_with_no_break_keeps_its_text() -> None:
    text = (
        "# Contents\n\n| Section | Title | Page |\n|---|---|---|\n"
        "| 1 | Introduction<br>and Scope | 7 |\n"
        "| 1.1 |   Terms and Definitions   | 8 |\n"
        "| 2 | Statics | 20 |\n"
    )
    out = clean_in_place(text).splitlines()
    assert _row_cells(out[5]) == ["1.1", "Terms and Definitions", "8"]
    assert _row_cells(out[6]) == ["2", "Statics", "20"]


def test_a_table_outside_a_contents_zone_keeps_its_in_cell_breaks() -> None:
    text = (
        "# Introduction\n\n"
        "| Part | Note                      |\n"
        "|------|---------------------------|\n"
        "| A-1  | first line<br>second line |\n"
        "| B-2  | plain                     |\n"
    )
    assert clean_in_place(text) == text


def test_a_body_table_past_a_repeated_heading_keeps_its_in_cell_breaks() -> None:
    # A running header must not carry a rewrite past the zone boundary.
    text = (
        "# Contents\n\n"
        "| Section | Title | Page |\n"
        "|---------|-------|------|\n"
        "| 1       | Wiring | 7   |\n"
        "\n# Handbook\n\n"
        "| Wire          | Polarity              |\n"
        "|---------------|-----------------------|\n"
        "| Red<br>Black  | Positive<br>Negative  |\n"
        "\n# Handbook\n\nPlain text.\n"
    )
    assert "| Red<br>Black" in clean_in_place(text)


def test_a_column_of_like_values_outside_a_zone_is_left_alone() -> None:
    # Without the zone gate, stacked part numbers look like a wrapped phrase.
    text = (
        "| Codes                      | Grade |\n"
        "|----------------------------|-------|\n"
        "| 10-224<br>10-225<br>10-226 | A     |\n"
        "| 10-227<br>10-228<br>10-229 | B     |\n"
    )
    assert clean_in_place(text) == text


def test_a_cell_stacking_whole_entries_is_left_alone() -> None:
    text = _contents_zone_body(
        "| 1<br>1.1<br>2 | Introduction<br>Terms<br>Statics | 3<br>4<br>9 |",
        "| 2.1 | Forces | 11 |",
        "| 3 | Kinematics | 19 |",
    )
    assert clean_in_place(text) == text


def test_a_cell_stacking_two_pages_is_left_alone() -> None:
    text = _contents_zone_body(
        "| 9.3 | Fatigue | 122<br>124 |",
        "| 9.4 | Fracture | 126 |",
        "| 9.5 | Creep | 130 |",
    )
    assert clean_in_place(text) == text


def test_gluing_a_contents_entry_does_not_lower_the_witness_count() -> None:
    broken = _contents_zone_body(
        "| 1 | Introduction<br>and<br>Scope | 7 |",
        "| 1.1 | Terms | 8 |",
        "| 2 | Balance<br>of<br>a<br>Welded<br>Frame | 20 |",
    )
    intact = _contents_zone_body(
        "| 1 | Introduction and Scope | 7 |",
        "| 1.1 | Terms | 8 |",
        "| 2 | Balance of a Welded Frame | 20 |",
    )
    count = printed_outline(segments(intact), KEYWORDS).title_count
    assert count > 0
    assert (
        printed_outline(segments(clean_in_place(broken)), KEYWORDS).title_count == count
    )


def test_gluing_a_contents_entry_is_idempotent() -> None:
    text = _contents_zone_body(
        "| 4.2.5 | Grid-Based<br>Versus<br>Models | 73 |",
        "| 4.2.6 | Layout<br>to<br>Avoid<br>Distortion | 74 |",
        "| 4.3 | Overview | 80 |",
    )
    once = clean(text)
    assert clean(once) == once


# ---- in-place fix: a contents entry wrapped onto a second table row -----------


def _ranked_contents_body(*rows: str) -> str:
    """A printed contents whose records name their own rank in a cell of it.

    A row with no rank of its own is read by its column and stands deepest: the
    shape a wrapped title arrives in.
    """
    return "# Contents\n\n" + laid_out_table("| Rank | No. | Title | Page |", *rows)


def test_a_contents_entry_wrapped_onto_a_second_row_is_joined() -> None:
    text = _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Balance of a Welded Frame Under |  |",
        "|  |  | Uniform Load | 12 |",
        "| Cap. | III | Kinematics | 19 |",
    )
    assert clean_in_place(text) == _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Balance of a Welded Frame Under Uniform Load | 12 |",
        "| Cap. | III | Kinematics | 19 |",
    )


def test_joining_a_wrapped_entry_gives_the_table_its_ladder_back() -> None:
    # The wrapped row opens two steps deeper, so the table would be dropped whole.
    text = _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Balance of a Welded Frame Under |  |",
        "|  |  | Uniform Load | 12 |",
        "| Cap. | III | Kinematics | 19 |",
    )
    assert printed_outline(segments(text), KEYWORDS).title_count == 0
    assert printed_outline(segments(clean_in_place(text)), KEYWORDS).title_count == 3


def test_a_row_stating_its_own_number_is_left_standing() -> None:
    text = _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Statics |  |",
        "|  |  | 2.1 Uniform Load | 12 |",
    )
    assert clean_in_place(text) == text


def test_a_row_under_a_finished_entry_is_left_standing() -> None:
    text = _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Statics | 9 |",
        "|  |  | Uniform Load | 12 |",
    )
    assert clean_in_place(text) == text


def test_a_row_opening_no_deeper_than_the_entry_above_is_left_standing() -> None:
    text = _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Statics |  |",
        "| Cap. |  | Uniform Load | 12 |",
    )
    assert clean_in_place(text) == text


def test_a_row_overlapping_the_entry_in_two_columns_is_left_standing() -> None:
    text = _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Statics |  |",
        "|  | III | Uniform Load | 12 |",
    )
    assert clean_in_place(text) == text


def test_rows_of_two_printed_tables_are_not_joined() -> None:
    text = (
        "# Contents\n\n"
        + laid_out_table(
            "| Rank | No. | Title | Page |",
            "| Cap. | I | Introduction | 7 |",
            "| Cap. | II | Balance of a Welded Frame |  |",
        )
        + "\n"
        + laid_out_table(
            "| Rank | No. | Section | Page |",
            "|  |  | Uniform Load | 12 |",
            "| Cap. | IV | Kinematics | 19 |",
        )
    )
    assert clean_in_place(text) == text


def test_a_table_outside_a_contents_zone_keeps_its_wrapped_row() -> None:
    text = "# Introduction\n\n" + laid_out_table(
        "| Line | Part | Note | Count |",
        "| A-1 | Bolt | hex head |  |",
        "|  |  | stainless | 12 |",
    )
    assert clean_in_place(text) == text


def test_joining_a_wrapped_entry_is_idempotent() -> None:
    text = _ranked_contents_body(
        "| Cap. | I | Introduction | 7 |",
        "| Cap. | II | Balance of a Welded Frame Under |  |",
        "|  |  | Uniform Load | 12 |",
        "| Cap. | III | Kinematics | 19 |",
    )
    once = clean(text)
    assert clean(once) == once


# ---- in-place fix: an HTML cell opened around its formula ----------------------


# The office route writes a complex table as raw HTML; markdown is not read there.
def _html_table(*cells: str) -> str:
    rows = "\n".join(cells)
    return f"<table>\n<thead>\n<tr>\n{rows}\n</tr>\n</thead>\n</table>\n"


def test_cell_with_one_paragraph_of_math_is_opened() -> None:
    text = _html_table(
        '<th style="text-align: center;">'
        '<p><span class="math display">$$F = 1$$</span></p></th>'
    )
    assert clean_in_place(text) == _html_table(
        '<th style="text-align: center;">\n\n$$F = 1$$\n\n</th>'
    )


def test_cell_without_a_paragraph_wrapper_is_opened_too() -> None:
    text = _html_table('<td><span class="math inline">$x$</span></td>')
    assert clean_in_place(text) == _html_table("<td>\n\n$x$\n\n</td>")


def test_cell_of_several_paragraphs_is_opened_paragraph_by_paragraph() -> None:
    text = _html_table(
        '<th><p><span class="math display">$$F = 1$$</span></p>\n'
        '<p>where <span class="math inline">$R$</span> is the radius</p>\n'
        "<p>end</p></th>"
    )
    assert clean_in_place(text) == _html_table(
        "<th>\n\n$$F = 1$$\n\nwhere $R$ is the radius\n\nend\n\n</th>"
    )


def test_span_the_route_drew_as_html_keeps_its_wrapper() -> None:
    text = _html_table('<th><p><span class="math inline"><em>L</em></span></p></th>')
    assert clean_in_place(text) == text


def test_cell_holding_a_picture_is_left_alone() -> None:
    text = _html_table(
        '<th><p><img src="a/b.jpeg" alt="" /></p>\n'
        '<p>Figure 5 at <span class="math inline">$R = 2$</span></p></th>'
    )
    assert clean_in_place(text) == text


def test_cell_holding_a_list_is_left_alone() -> None:
    text = _html_table(
        '<th><ul><li><span class="math inline">$x$</span></li></ul></th>'
    )
    assert clean_in_place(text) == text


def test_cell_holding_a_nested_table_is_left_alone() -> None:
    text = _html_table(
        '<th><table><tr><td><span class="math inline">$x$</span></td></tr></table></th>'
    )
    assert clean_in_place(text) == text


def test_content_opening_on_a_markdown_marker_is_left_alone() -> None:
    text = _html_table(
        '<th><p><span class="math display">$$F = 1$$</span></p>\n'
        "<p>- 0,214 at rest</p></th>"
    )
    assert clean_in_place(text) == text


def test_content_opening_on_a_signed_value_is_opened() -> None:
    text = _html_table(
        '<th><p><span class="math display">$$F = 1$$</span></p>\n'
        "<p>-0,214 at rest</p></th>"
    )
    assert clean_in_place(text) == _html_table(
        "<th>\n\n$$F = 1$$\n\n-0,214 at rest\n\n</th>"
    )


def test_content_opening_on_a_fence_is_left_alone() -> None:
    text = _html_table(
        '<th><p><span class="math display">$$F = 1$$</span></p>\n<p>```</p></th>'
    )
    assert clean_in_place(text) == text


def test_prose_carrying_inline_markup_is_left_alone() -> None:
    text = _html_table(
        '<th><p>Literal *a* and <span class="math inline">$x$</span></p></th>'
    )
    assert clean_in_place(text) == text


def test_a_paired_character_inside_the_formula_is_no_refusal() -> None:
    text = _html_table(
        '<td><p>at <span class="math inline">$a_{1} + b_{2}$</span></p></td>'
    )
    assert clean_in_place(text) == _html_table("<td>\n\nat $a_{1} + b_{2}$\n\n</td>")


def test_cell_with_no_formula_is_left_alone() -> None:
    text = _html_table("<th><p>Name</p>\n<p>of the part</p></th>")
    assert clean_in_place(text) == text


def test_two_cells_on_one_line_are_left_alone() -> None:
    text = _html_table('<th><span class="math inline">$x$</span></th><th>2</th>')
    assert clean_in_place(text) == text


def test_math_span_outside_a_table_keeps_its_wrapper() -> None:
    text = 'Text <span class="math inline">$x$</span> after it\n'
    assert clean_in_place(text) == text


def test_opened_cell_stays_inside_the_protected_zone() -> None:
    text = _html_table('<th><p><span class="math display">$$F = 1$$</span></p></th>')
    opened = clean_in_place(text)
    assert all(protected for _, protected in segments(opened))


def test_opening_an_html_cell_is_idempotent() -> None:
    text = _html_table(
        '<th><p><span class="math display">$$F = 1$$</span></p>\n'
        '<p>where <span class="math inline">$R$</span> is the radius</p></th>'
    )
    once = clean(text)
    assert clean(once) == once
