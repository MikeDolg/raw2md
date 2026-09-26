"""Tests for the spacing route: letter-spaced runs and the run list."""

from __future__ import annotations

from raw2md.cleaner import clean_with_report
from raw2md.llm.post.coordinator import post_process

from ._helpers import (
    call_count,
    join_blocks,
    make_op,
    runs_reply,
    sent_text,
)

# --- a word set letter by letter ---------------------------------------------

# Letters spaced apart; the body spells the word nowhere else.
SPACED_ZONE = ["All the i d e n t i c a l values here."]
SPACED_FIXED = "All the identical values here."

# The run widened over the group at either end.
SPACED_RUN = "the i d e n t i c a l values"
SPACED_RUN_CLOSED = "the identical values"

SPACED_HEADING = ["# C O N T E N T S"]
SPACED_HEADING_FIXED = "# CONTENTS"


def test_a_letter_spaced_run_in_prose_is_rebuilt() -> None:
    op = make_op([runs_reply((1, SPACED_RUN_CLOSED))])
    result = post_process(join_blocks(SPACED_ZONE), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.repaired_runs, result.refused_runs) == (1, 0)
    assert result.body == SPACED_FIXED + "\n"


def test_a_letter_spaced_heading_is_rebuilt() -> None:
    op = make_op([runs_reply((1, "CONTENTS"))])
    result = post_process(join_blocks(SPACED_HEADING), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == SPACED_HEADING_FIXED + "\n"


def test_the_spacing_request_names_the_repair_and_the_run() -> None:
    op = make_op([runs_reply((1, SPACED_RUN_CLOSED))])
    post_process(join_blocks(SPACED_ZONE), op)
    sent = sent_text(op)
    assert "Close the spaces" in sent
    assert f"1: {SPACED_RUN}" in sent
    assert f"in: {SPACED_ZONE[0]}" in sent


def test_a_reply_that_changes_a_letter_is_refused() -> None:
    changed = "the identicol values"
    op = make_op([runs_reply((1, changed)), runs_reply((1, changed))])
    body = join_blocks(SPACED_ZONE)
    result = post_process(body, op)
    assert call_count(op) == 2
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.repaired_runs, result.refused_runs) == (0, 2)
    assert result.body == body


def test_a_reply_reaching_past_the_run_is_refused() -> None:
    welded = "All the identical values"
    op = make_op([runs_reply((1, welded)), runs_reply((1, welded))])
    body = join_blocks(SPACED_ZONE)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_run_the_body_attests_is_cleaned_and_opens_no_zone() -> None:
    raw = join_blocks(
        SPACED_ZONE,
        ["The identical case matters here."],
        ["The identical case again."],
    )
    cleaned = clean_with_report(raw).body
    assert SPACED_ZONE[0] not in cleaned
    op = make_op([])
    result = post_process(cleaned, op)
    assert call_count(op) == 0
    assert result.body == cleaned


def test_a_run_the_reader_leaves_standing_spends_one_request() -> None:
    # A reply naming no run is terminal.
    op = make_op([runs_reply()])
    body = join_blocks(SPACED_ZONE)
    result = post_process(body, op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted, result.unchanged) == (0, 1, 1)
    assert (result.repaired_runs, result.refused_runs) == (0, 0)
    assert result.body == body


def test_a_reply_closing_part_of_a_run_is_refused() -> None:
    partial = "the ident i c a l values"
    op = make_op([runs_reply((1, partial)), runs_reply((1, partial))])
    body = join_blocks(SPACED_ZONE)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_run_left_standing_beside_a_closed_one_is_accepted() -> None:
    zone = ["The a b c axes and the i d e n t i c a l values."]
    fixed = "The a b c axes and the identical values."
    op = make_op([runs_reply((2, SPACED_RUN_CLOSED))])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 1
    assert (result.repaired_runs, result.refused_runs) == (1, 0)
    assert result.body == fixed + "\n"


def test_each_closed_run_lands_at_its_own_address() -> None:
    zone = ["The i d e n t i c a l and the o r d i n a r y values."]
    op = make_op(
        [runs_reply((1, "The identical and"), (2, "the ordinary values"))],
    )
    result = post_process(join_blocks(zone), op)
    assert (result.repaired_runs, result.refused_runs) == (2, 0)
    assert result.body == "The identical and the ordinary values.\n"


def test_a_systematic_spacing_costs_a_bounded_number_of_requests() -> None:
    count = 300
    lines = [
        [f"Line {number} holds the w o r d {number} here."] for number in range(count)
    ]
    op = make_op([runs_reply((1, "the word")), runs_reply((229, "the word"))])
    result = post_process(join_blocks(*lines), op)
    assert call_count(op) == 2
    assert (result.repaired_runs, result.refused_runs) == (2, 0)
    assert "Line 0 holds the word 0 here." in result.body
    assert "Line 228 holds the word 228 here." in result.body
    assert "Line 1 holds the w o r d 1 here." in result.body


def test_a_reply_naming_a_run_another_part_covers_is_passed_over() -> None:
    count = 300
    lines = [
        [f"Line {number} holds the w o r d {number} here."] for number in range(count)
    ]
    op = make_op([runs_reply((229, "the word")), runs_reply()])
    result = post_process(join_blocks(*lines), op)
    assert call_count(op) == 2
    assert (result.repaired_runs, result.refused_runs) == (0, 0)
    assert "Line 228 holds the w o r d 228 here." in result.body


def test_a_designation_run_does_not_refuse_another_zones_repair() -> None:
    # A spaced run is no defect alone, so it gates no other route.
    zone = [r"Points A B C: $$E = \frac{mv^2}{2$$ for any $v$."]
    fixed = r"Points A B C: $$E = \frac{mv^2}{2}$$ for any $v$."
    op = make_op([fixed, runs_reply()])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (1, 1)
    assert "A B C" in result.body


def test_a_formulas_symbols_make_no_spaced_run() -> None:
    op = make_op([])
    body = join_blocks(["The values $a b c$ equal one."])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


# A one-letter conjunction as a word of the prose, designations inside formulas.
SPACING_WITNESS = [
    f"Опыт {n} и опыт {n} описаны формулой $A_{n} B_{n} x_{n} y_{n}$."
    for n in range(1, 25)
]


def test_an_enumeration_of_designations_opens_no_zone() -> None:
    op = make_op([])
    body = join_blocks(SPACING_WITNESS, ["События A и B независимы."])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


# A surname set letter by letter, a conjunction, and a name.
SPACED_NAME_LINE = "Р у м к е и Дж описали опыт."  # noqa: RUF001 -- Cyrillic body
SPACED_NAME_RUN = "Р у м к е и"  # noqa: RUF001 -- Cyrillic body


def test_a_run_stops_at_the_conjunction_that_ends_it() -> None:
    op = make_op([runs_reply()])
    post_process(join_blocks(SPACING_WITNESS, [SPACED_NAME_LINE]), op)
    assert f"1: {SPACED_NAME_RUN}\n" in sent_text(op)


def test_a_conjunction_left_standing_beside_a_closed_run_is_accepted() -> None:
    op = make_op([runs_reply((1, "Румке и"))])
    result = post_process(join_blocks(SPACING_WITNESS, [SPACED_NAME_LINE]), op)
    assert (result.repaired_runs, result.refused_runs) == (1, 0)
    assert "Румке и Дж описали опыт." in result.body


def test_the_line_under_three_runs_travels_once() -> None:
    zone = ["Here the f i r s t word, the s e c o n d word, the t h i r d word."]
    op = make_op([runs_reply()])
    post_process(join_blocks(zone), op)
    sent = sent_text(op)
    assert sent.count(zone[0]) == 1
    assert sent.endswith(f"3: the t h i r d word\nin: {zone[0]}")
