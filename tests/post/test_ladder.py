"""Tests for the ladder route: the level list and the ladder's vetoes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raw2md.llm.post.coordinator import post_process
from raw2md.llm.trace import LlmTrace

from ._helpers import (
    ZONE,
    ZONE_FIXED,
    call_count,
    join_blocks,
    make_op,
    reason_text,
    sent_text,
)

# --- the heading ladder: the whole outline as one zone -----------------------

# The outline steps from level 1 to level 3.
LADDER_SKIP = (["# Scope"], ["### Materials"], ["Text of the first section."])


def levels_reply(*headings: tuple[int, int, str]) -> str:
    """A level-indexed reply naming each `(index, level, title)` triple."""
    return json.dumps(
        {
            "headings": [
                {"heading": number, "level": level, "title": title}
                for number, level, title in headings
            ]
        }
    )


def heading_lines(body: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith("#")]


def test_a_heading_moves_to_the_level_the_reply_names() -> None:
    op = make_op([levels_reply((2, 2, "Materials"))])
    result = post_process(join_blocks(*LADDER_SKIP), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_headings, result.refused_headings) == (1, 0)
    assert result.body == join_blocks(
        ["# Scope"], ["## Materials"], ["Text of the first section."]
    )


def test_a_relevelled_outline_adds_and_drops_no_heading() -> None:
    op = make_op([levels_reply((2, 2, "Materials"))])
    result = post_process(join_blocks(*LADDER_SKIP), op)
    assert heading_lines(result.body) == ["# Scope", "## Materials"]


def test_the_request_carries_the_whole_outline_behind_its_indices() -> None:
    op = make_op([levels_reply((2, 2, "Materials"))])
    post_process(join_blocks(*LADDER_SKIP), op)
    sent = sent_text(op)
    assert "1: # Scope" in sent
    assert "2: ### Materials" in sent
    assert "Text of the first section." not in sent


def test_a_reply_under_another_title_is_refused() -> None:
    changed = levels_reply((2, 2, "Materials and methods"))
    op = make_op([changed, changed])
    body = join_blocks(*LADDER_SKIP)
    result = post_process(body, op)
    assert call_count(op) == 2
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_headings, result.refused_headings) == (0, 2)
    assert "another title" in reason_text(op)
    assert result.body == body


def test_a_title_copied_with_its_marker_is_accepted() -> None:
    # The marker states the level, which the reply names apart.
    op = make_op([levels_reply((2, 2, "### Materials"))])
    result = post_process(join_blocks(*LADDER_SKIP), op)
    assert call_count(op) == 1
    assert (result.repaired, result.repaired_headings) == (1, 1)
    assert heading_lines(result.body) == ["# Scope", "## Materials"]


def test_the_marker_a_title_carries_is_no_part_of_the_check() -> None:
    op = make_op([levels_reply((2, 2, "## Materials"))])
    result = post_process(join_blocks(*LADDER_SKIP), op)
    assert (result.repaired, result.repaired_headings) == (1, 1)
    assert heading_lines(result.body) == ["# Scope", "## Materials"]


def test_another_title_behind_a_marker_is_refused_all_the_same() -> None:
    changed = levels_reply((2, 2, "### Materials and methods"))
    op = make_op([changed, changed])
    body = join_blocks(*LADDER_SKIP)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_headings, result.refused_headings) == (0, 2)
    assert "another title" in reason_text(op)
    assert result.body == body


def test_a_title_of_its_own_opening_with_a_hash_still_names_its_heading() -> None:
    # A title that starts with a hash keeps it; only the shown marker is dropped.
    body = join_blocks(["# Scope"], ["### # 5 Materials"], ["Text."])
    op = make_op([levels_reply((2, 2, "### # 5 Materials"))])
    result = post_process(body, op)
    assert (result.repaired, result.repaired_headings) == (1, 1)
    assert heading_lines(result.body) == ["# Scope", "## # 5 Materials"]


def test_a_title_stripped_past_its_own_hash_is_refused() -> None:
    body = join_blocks(["# Scope"], ["### # 5 Materials"], ["Text."])
    short = levels_reply((2, 2, "5 Materials"))
    op = make_op([short, short])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "another title" in reason_text(op)
    assert result.body == body


def test_a_heading_returned_at_its_own_level_is_no_edit() -> None:
    op = make_op([levels_reply((1, 1, "Scope"), (2, 2, "Materials"))])
    result = post_process(join_blocks(*LADDER_SKIP), op)
    assert call_count(op) == 1
    assert (result.repaired_headings, result.refused_headings) == (1, 0)
    assert heading_lines(result.body) == ["# Scope", "## Materials"]


def test_a_reply_carrying_no_title_is_refused() -> None:
    naked = json.dumps({"headings": [{"heading": 2, "level": 2}]})
    op = make_op([naked, naked])
    body = join_blocks(*LADDER_SKIP)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "without the title" in reason_text(op)
    assert result.body == body


def test_a_sound_ladder_spends_no_request() -> None:
    op = make_op([])
    body = join_blocks(["# Scope"], ["## Materials"], ["Text of the first section."])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_one_title_at_two_levels_opens_the_zone() -> None:
    # A running header read as a section on one page, a subsection on the next.
    body = join_blocks(
        ["# Preface"],
        ["Text."],
        ["## Preface"],
        ["More text."],
        ["## Sections"],
        ["Section text."],
    )
    op = make_op([levels_reply((2, 1, "Preface"))])
    result = post_process(body, op)
    assert call_count(op) == 1
    assert (result.repaired, result.repaired_headings) == (1, 1)
    assert heading_lines(result.body) == ["# Preface", "# Preface", "## Sections"]


def test_a_reply_that_opens_a_gap_in_the_ladder_reverts() -> None:
    body = join_blocks(["# Preface"], ["## Preface"], ["## Sections"], ["Text."])
    gap = levels_reply((3, 4, "Sections"))
    op = make_op([gap, gap])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_headings, result.vetoed_headings) == (0, 2)
    assert "skips more levels" in reason_text(op)
    assert result.body == body


def test_a_reply_that_flattens_the_ladder_leaves_no_edit() -> None:
    # Each entry of a flattening reply empties a rank, so no entry survives.
    body = join_blocks(["# Scope"], ["## Materials"], ["#### Makeup"], ["Text."])
    flat = levels_reply((1, 2, "Scope"), (3, 2, "Makeup"))
    op = make_op([flat, flat])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_headings, result.vetoed_headings) == (0, 4)
    assert "stands on fewer levels" in reason_text(op)
    assert result.body == body


def test_a_branch_moved_down_lands_with_the_entry_under_it() -> None:
    # Read one at a time, the first entry would empty its rank.
    body = join_blocks(["# Scope"], ["## Materials"], ["#### Makeup"], ["Text."])
    op = make_op([levels_reply((1, 2, "Scope"), (2, 3, "Materials"))])
    result = post_process(body, op)
    assert call_count(op) == 1
    assert (result.repaired_headings, result.vetoed_headings) == (2, 0)
    assert heading_lines(result.body) == ["## Scope", "### Materials", "#### Makeup"]


def test_the_entry_that_regresses_the_ladder_is_dropped_alone() -> None:
    body = join_blocks(
        ["# Scope"],
        ["### Materials"],
        ["### Appendix"],
        ["Text."],
        ["### Appendix"],
        ["More text."],
    )
    op = make_op([levels_reply((2, 2, "Materials"), (4, 2, "Appendix"))])
    result = post_process(body, op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_headings, result.vetoed_headings) == (1, 1)
    assert heading_lines(result.body) == [
        "# Scope",
        "## Materials",
        "### Appendix",
        "### Appendix",
    ]


def test_a_vetoed_entry_is_counted_apart_from_a_refused_one() -> None:
    body = join_blocks(
        ["# Scope"],
        ["### Materials"],
        ["### Appendix"],
        ["Text."],
        ["### Appendix"],
        ["More text."],
    )
    op = make_op(
        [
            levels_reply(
                (2, 2, "Materials"),  # accepted
                (4, 2, "Appendix"),  # vetoed: one title at two levels
                (9, 2, "Makeup"),  # refused: no heading of this document
            )
        ]
    )
    result = post_process(body, op)
    assert call_count(op) == 1
    assert (result.repaired_headings, result.refused_headings) == (1, 1)
    assert result.vetoed_headings == 1


def test_a_reply_that_pours_one_rank_into_another_reverts() -> None:
    # The most crowded level gets more: a merge of two ranks.
    body = join_blocks(
        ["# Scope"],
        ["## Appendix"],
        ["## Methods"],
        ["### Makeup"],
        ["### Data"],
        ["#### Tables"],
        ["#### Appendix"],
        ["Text."],
    )
    merge = levels_reply((6, 3, "Tables"))
    op = make_op([merge, merge])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "most crowded level" in reason_text(op)
    assert result.body == body


def test_a_reply_that_splits_a_title_over_two_levels_reverts() -> None:
    body = join_blocks(
        ["# Scope"],
        ["### Materials"],
        ["### Appendix"],
        ["Text."],
        ["### Appendix"],
        ["More text."],
    )
    split = levels_reply((4, 2, "Appendix"))
    op = make_op([split, split])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "more titles at two levels" in reason_text(op)
    assert result.body == body


def test_a_branch_shifted_one_rank_is_accepted() -> None:
    body = join_blocks(["# Scope"], ["### Materials"], ["### Makeup"], ["Text."])
    op = make_op([levels_reply((2, 2, "Materials"), (3, 2, "Makeup"))])
    result = post_process(body, op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_headings, result.refused_headings) == (2, 0)
    assert result.vetoed_headings == 0
    assert heading_lines(result.body) == ["# Scope", "## Materials", "## Makeup"]


def test_a_level_more_than_two_ranks_off_is_refused() -> None:
    far = levels_reply((2, 6, "Materials"))
    op = make_op([far, far])
    body = join_blocks(*LADDER_SKIP)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "moves 3 ranks" in reason_text(op)
    assert result.body == body


# Three ranks off the level its numbering names, past the shift ceiling.
LADDER_WITNESSED_FAR_SHIFT = (
    ["# Scope"],
    ["## § 1. First"],
    ["## § 2. Second"],
    ["## § 3. Third"],
    ["##### § 4. Fourth"],
    ["##### Appendix"],
    ["Text."],
)


def test_a_witnessed_move_past_the_shift_ceiling_is_accepted() -> None:
    op = make_op([levels_reply((5, 2, "§ 4. Fourth"))])
    result = post_process(join_blocks(*LADDER_WITNESSED_FAR_SHIFT), op)
    assert (result.repaired_headings, result.refused_headings) == (1, 0)
    assert heading_lines(result.body)[4] == "## § 4. Fourth"


def test_the_same_shift_without_a_witness_is_still_refused() -> None:
    body = join_blocks(
        ["# Scope"],
        ["## First"],
        ["## Second"],
        ["## Third"],
        ["##### Fourth"],
        ["##### Appendix"],
        ["Text."],
    )
    far = levels_reply((5, 2, "Fourth"))
    op = make_op([far, far])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "moves 3 ranks" in reason_text(op)
    assert result.body == body


def test_an_index_outside_the_outline_is_refused() -> None:
    stray = levels_reply((9, 2, "Materials"))
    op = make_op([stray, stray])
    body = join_blocks(*LADDER_SKIP)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "not a heading of this document" in reason_text(op)
    assert result.body == body


def test_a_level_markdown_does_not_hold_is_refused() -> None:
    deep = levels_reply((2, 7, "Materials"))
    op = make_op([deep, deep])
    body = join_blocks(*LADDER_SKIP)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "outside the 1 to 6" in reason_text(op)
    assert result.body == body


def test_the_levels_it_was_given_read_as_an_echo() -> None:
    # An echo is terminal.
    same = levels_reply((2, 3, "Materials"))
    op = make_op([same])
    body = join_blocks(*LADDER_SKIP)
    result = post_process(body, op)
    assert (result.repaired, result.reverted, result.unchanged) == (0, 1, 1)
    assert call_count(op) == 1
    assert result.body == body


def test_a_fenced_level_list_is_still_a_level_list() -> None:
    fenced = f"```json\n{levels_reply((2, 2, 'Materials'))}\n```"
    op = make_op([fenced])
    result = post_process(join_blocks(*LADDER_SKIP), op)
    assert (result.repaired, result.repaired_headings) == (1, 1)
    assert heading_lines(result.body) == ["# Scope", "## Materials"]


def test_a_heading_inside_a_protected_zone_is_no_heading() -> None:
    op = make_op([])
    body = join_blocks(["```", "# Scope", "### Materials", "```"])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_the_ladder_zone_goes_before_the_block_zones() -> None:
    op = make_op([levels_reply((2, 2, "Materials")), ZONE_FIXED])
    result = post_process(join_blocks(*LADDER_SKIP, ZONE), op)
    assert call_count(op) == 2
    assert "Heading ladder to repair" in sent_text(op, 0)
    assert ZONE[0] in sent_text(op, 1)
    assert (result.repaired, result.reverted) == (2, 0)
    assert "## Materials" in result.body
    assert ZONE_FIXED in result.body


def test_the_ladder_zone_is_named_in_the_trace(tmp_path: Path) -> None:
    op = make_op([levels_reply((2, 2, "Materials"))])
    trace = LlmTrace(tmp_path)

    post_process(join_blocks(*LADDER_SKIP), op, trace)

    text = (tmp_path / "llm" / "post.txt").read_text(encoding="utf-8")
    assert "### zone 1 (heading-ladder)  attempt 1" in text


def test_a_reply_that_is_not_a_level_list_reverts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(["I moved the second heading up one level.", "Sorry: same answer."])
    body = join_blocks(*LADDER_SKIP)
    with caplog.at_level("INFO", logger="raw2md"):
        result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "JSON level list" in reason_text(op)
    assert any("not a level list" in record.message for record in caplog.records)
    assert result.body == body


def test_an_underlined_heading_fills_the_rung_it_holds() -> None:
    op = make_op([])
    body = join_blocks(
        ["# Scope"], ["Materials", "---------"], ["### Makeup"], ["Text."]
    )
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_an_underlined_heading_travels_but_is_refused_as_an_edit() -> None:
    # A setext level is on its own line, out of reach of a marker rewrite.
    body = join_blocks(
        ["# Scope"], ["Materials", "========="], ["### Makeup"], ["Text."]
    )
    edit = levels_reply((2, 2, "Materials"))
    op = make_op([edit, edit])
    result = post_process(body, op)
    sent = sent_text(op)
    assert "2: Materials" in sent
    assert "=========" in sent
    assert (result.repaired, result.reverted) == (0, 1)
    assert "states its level with an underline" in reason_text(op)
    assert result.body == body


def test_an_outline_of_underlined_headings_alone_spends_no_request() -> None:
    op = make_op([])
    body = join_blocks(
        ["Scope", "====="], ["Text."], ["Scope", "-----"], ["More text."]
    )
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


# --- the ladder veto: what the document states about its own ranks -----------

# A numbered series off its level, and a skipped rung under it.
SERIES_LADDER = (
    ["# Scope"],
    ["## § 1. First"],
    ["## § 2. Second"],
    ["## § 3. Third"],
    ["#### § 4. Fourth"],
    ["#### Appendix"],
    ["Text."],
)


def test_a_move_the_numbering_confirms_lands_in_the_widest_rank() -> None:
    op = make_op([levels_reply((5, 2, "§ 4. Fourth"))])
    result = post_process(join_blocks(*SERIES_LADDER), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_headings, result.vetoed_headings) == (1, 0)
    assert heading_lines(result.body) == [
        "# Scope",
        "## § 1. First",
        "## § 2. Second",
        "## § 3. Third",
        "## § 4. Fourth",
        "#### Appendix",
    ]


def test_a_merge_of_two_ranks_no_numbering_states_is_refused() -> None:
    merge = levels_reply((6, 2, "Appendix"))
    op = make_op([merge, merge])
    body = join_blocks(*SERIES_LADDER)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_headings, result.vetoed_headings) == (0, 2)
    assert "most crowded level" in reason_text(op)
    assert result.body == body


def test_a_reply_flattening_a_numbered_ladder_keeps_its_levels() -> None:
    # A witness answers only for the heading it names.
    flat = levels_reply((1, 2, "Scope"), (5, 2, "§ 4. Fourth"), (6, 2, "Appendix"))
    op = make_op([flat])
    result = post_process(join_blocks(*SERIES_LADDER), op)
    assert (result.repaired_headings, result.vetoed_headings) == (1, 2)
    assert heading_lines(result.body) == [
        "# Scope",
        "## § 1. First",
        "## § 2. Second",
        "## § 3. Third",
        "## § 4. Fourth",
        "#### Appendix",
    ]


def test_a_witnessed_move_does_not_veto_the_entries_behind_it() -> None:
    body = join_blocks(
        ["# Scope"],
        ["## § 1. First"],
        ["## § 2. Second"],
        ["## § 3. Third"],
        ["#### § 4. Fourth"],
        ["##### Makeup"],
        ["Text."],
    )
    op = make_op([levels_reply((5, 2, "§ 4. Fourth"), (6, 3, "Makeup"))])
    result = post_process(body, op)
    assert (result.repaired_headings, result.vetoed_headings) == (2, 0)
    assert heading_lines(result.body)[4:] == ["## § 4. Fourth", "### Makeup"]


def test_the_numbering_does_not_lift_the_veto_on_a_skipped_level() -> None:
    body = join_blocks(
        ["# Scope"],
        ["### § 1. First"],
        ["### § 2. Second"],
        ["### § 3. Third"],
        ["#### § 4. Fourth"],
        ["##### Depth"],
        ["Text."],
    )
    gap = levels_reply((5, 3, "§ 4. Fourth"))
    op = make_op([gap, gap])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_headings, result.vetoed_headings) == (0, 2)
    assert "skips more levels" in reason_text(op)
    assert result.body == body


def test_a_series_too_scattered_to_agree_states_no_rank() -> None:
    body = join_blocks(
        ["# Scope"],
        ["## § 1. First"],
        ["## § 2. Second"],
        ["### § 3. Third"],
        ["### § 4. Fourth"],
        ["##### Appendix"],
        ["Text."],
    )
    merge = levels_reply((5, 2, "§ 4. Fourth"))
    op = make_op([merge, merge])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "most crowded level" in reason_text(op)
    assert result.body == body


def test_the_printed_contents_confirms_a_move_of_its_own() -> None:
    body = join_blocks(
        ["# Contents"],
        [
            "| Part | Title | Page |",
            "|---|---|---|",
            "| Preface |  | 3 |",
            "|  | Basic terms | 3 |",
            "|  | Rules | 5 |",
            "| Loads |  | 9 |",
            "|  | Bending | 9 |",
            "|  | Torsion | 12 |",
        ],
        ["# Preface"],
        ["## Basic terms"],
        ["## Rules"],
        ["# Loads"],
        ["## Bending"],
        ["#### Torsion"],
        ["Text."],
    )
    op = make_op([levels_reply((7, 2, "Torsion"))])
    result = post_process(body, op)
    assert (result.repaired_headings, result.vetoed_headings) == (1, 0)
    assert heading_lines(result.body)[-1] == "## Torsion"


def test_a_catalog_of_letter_grades_states_no_rank() -> None:
    # Grade letters are valid roman numerals, so the class is a coincidence.
    body = join_blocks(
        ["# Scope"],
        ["## Type C"],
        ["## Type D"],
        ["## Type M"],
        ["#### Type X"],
        ["#### Appendix"],
        ["Text."],
    )
    move = levels_reply((5, 2, "Type X"))
    op = make_op([move, move])
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body
