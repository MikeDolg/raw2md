"""Tests for the post pass: which zones it sends, refusals, and the trace."""

from __future__ import annotations

from pathlib import Path

import pytest

from raw2md.llm.base import (
    AuthError,
    DocumentTooLargeError,
    RateLimitError,
)
from raw2md.llm.post.coordinator import post_process
from raw2md.llm.trace import LlmTrace

from ._helpers import (
    BROKEN_TABLE_ZONE,
    ROW_FIX,
    ZONE,
    ZONE_FIXED,
    call_count,
    join_blocks,
    make_op,
    rows_reply,
    runs_reply,
    sent_text,
    wide_zone,
)

# --- scope -----------------------------------------------------------------


def test_a_sound_body_returns_unchanged() -> None:
    body = join_blocks(["Just a normal paragraph."], ["Another one."])
    op = make_op([])
    result = post_process(body, op)
    assert result.body == body
    assert call_count(op) == 0
    assert (result.repaired, result.reverted) == (0, 0)


def test_far_block_is_not_sent() -> None:
    # Only the adjacent block travels, as read-only context.
    body = join_blocks(
        ["Distant opening paragraph stays put, far from the zone."],
        ["A buffering paragraph separates the opening from the zone."],
        ZONE,
    )
    op = make_op([ZONE_FIXED])
    result = post_process(body, op)
    assert "Distant opening paragraph stays put, far from the zone." in result.body
    assert call_count(op) == 1
    assert "Distant opening" not in sent_text(op)
    assert "buffering" in sent_text(op)  # the adjacent block, shown as context
    assert ZONE[0] in sent_text(op)


def test_protected_zone_is_not_sent() -> None:
    body = join_blocks(["```", *ZONE, "```"])
    op = make_op([])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_table_zone_sends_the_whole_table_numbered() -> None:
    op = make_op([ROW_FIX])
    post_process(join_blocks(BROKEN_TABLE_ZONE), op)
    assert "1: | A | B |" in sent_text(op)
    assert "2: | --- | --- |" in sent_text(op)
    assert "3: | x |" in sent_text(op)


# --- a refused request costs its own zone ----------------------------------


def test_rate_limit_with_nothing_delivered_propagates() -> None:
    op = make_op([RateLimitError("429")])
    with pytest.raises(RateLimitError):
        post_process(join_blocks(ZONE), op)


def test_document_too_large_with_nothing_delivered_propagates() -> None:
    op = make_op([DocumentTooLargeError("over the limit")])
    with pytest.raises(DocumentTooLargeError):
        post_process(join_blocks(ZONE), op)


def test_a_repair_made_before_a_refusal_reaches_the_body() -> None:
    op = make_op([ZONE_FIXED, RateLimitError("429")])
    result = post_process(join_blocks(ZONE, ZONE), op)
    assert result.body.count(ZONE_FIXED) == 1
    assert ZONE[0] in result.body  # the refused zone stands as it came
    assert (result.planned, result.lost) == (2, 1)
    assert isinstance(result.failure, RateLimitError)
    # A zone lost to the provider is neither a repair nor a revert.
    assert (result.repaired, result.reverted) == (1, 0)


def test_a_spent_budget_stops_the_zones_after_it() -> None:
    op = make_op([ZONE_FIXED, RateLimitError("429")])
    result = post_process(join_blocks(ZONE, ZONE, ZONE), op)
    assert call_count(op) == 2  # the third zone is never sent
    assert (result.planned, result.lost) == (3, 2)
    assert result.body.count(ZONE[0]) == 2


def test_a_refused_access_stops_the_zones_after_it() -> None:
    op = make_op([ZONE_FIXED, AuthError("bad key")])
    result = post_process(join_blocks(ZONE, ZONE, ZONE), op)
    assert call_count(op) == 2  # the third zone is never sent
    assert (result.planned, result.lost) == (3, 2)
    assert isinstance(result.failure, AuthError)


def test_a_refused_access_with_nothing_delivered_sends_one_zone() -> None:
    op = make_op([AuthError("bad key")])
    with pytest.raises(AuthError):
        post_process(join_blocks(ZONE, ZONE, ZONE), op)
    assert call_count(op) == 1


def test_a_refusal_that_is_not_the_budget_leaves_the_stage_sending() -> None:
    # An oversize zone is a deliberate skip, not a stage failure.
    op = make_op([DocumentTooLargeError("over the limit"), ZONE_FIXED])
    result = post_process(join_blocks(ZONE, ZONE), op)
    assert call_count(op) == 2
    assert result.body.count(ZONE_FIXED) == 1
    assert (result.planned, result.lost) == (2, 1)
    assert result.failure is None


def test_a_stage_that_delivered_nothing_raises_what_the_run_answers_for() -> None:
    op = make_op([DocumentTooLargeError("over the limit"), RateLimitError("429")])
    with pytest.raises(RateLimitError):
        post_process(join_blocks(ZONE, ZONE), op)


def test_a_refused_table_part_keeps_the_rows_the_parts_before_it_repaired() -> None:
    zone, fixed = wide_zone()
    good = rows_reply(*[(number, fixed) for number in range(3, 9)])
    op = make_op([good, RateLimitError("429")])
    result = post_process(join_blocks(zone), op)
    assert call_count(op) == 2
    assert result.body.count(fixed) == 2
    assert (result.repaired, result.repaired_rows) == (1, 2)
    assert (result.planned, result.lost) == (1, 1)


def test_a_refused_spacing_part_keeps_the_runs_the_parts_before_it_closed() -> None:
    lines = [
        [f"Line {number} holds the w o r d {number} here."] for number in range(300)
    ]
    op = make_op([runs_reply((1, "the word")), RateLimitError("429")])
    result = post_process(join_blocks(*lines), op)
    assert call_count(op) == 2
    assert "Line 0 holds the word 0 here." in result.body
    assert (result.repaired, result.repaired_runs) == (1, 1)
    assert (result.planned, result.lost) == (1, 1)


def test_a_row_turned_down_before_a_refusal_stays_counted() -> None:
    off = rows_reply((3, "| x |  |  |"))
    op = make_op([ZONE_FIXED, off, RateLimitError("429")])
    result = post_process(join_blocks(ZONE, BROKEN_TABLE_ZONE), op)
    assert call_count(op) == 3
    assert (result.repaired_rows, result.refused_rows) == (0, 1)
    assert (result.planned, result.lost) == (2, 1)
    assert isinstance(result.failure, RateLimitError)


def test_a_run_turned_down_before_a_refusal_stays_counted() -> None:
    lines = [
        [f"Line {number} holds the w o r d {number} here."] for number in range(300)
    ]
    op = make_op([ZONE_FIXED, runs_reply((1, "the ward")), RateLimitError("429")])
    result = post_process(join_blocks(ZONE, *lines), op)
    assert call_count(op) == 3
    assert (result.repaired_runs, result.refused_runs) == (0, 1)
    assert (result.planned, result.lost) == (2, 1)
    assert isinstance(result.failure, RateLimitError)


# --- debug trace -----------------------------------------------------------


def test_trace_names_the_zone_by_its_shape(tmp_path: Path) -> None:
    op = make_op([ZONE_FIXED])
    trace = LlmTrace(tmp_path)

    post_process(join_blocks(ZONE), op, trace)

    text = (tmp_path / "llm" / "post.txt").read_text(encoding="utf-8")
    assert "### zone 1 (broken-markup)  attempt 1" in text
    assert ZONE[0] in text
    assert ZONE_FIXED in text


def test_a_sound_body_leaves_no_trace(tmp_path: Path) -> None:
    op = make_op([])
    trace = LlmTrace(tmp_path)

    post_process(join_blocks(["Just a normal paragraph."]), op, trace)

    assert not (tmp_path / "llm").exists()


def test_trace_holds_the_rejected_reply_and_the_retry_note(tmp_path: Path) -> None:
    op = make_op(["a totally different sentence", "yet another wording entirely"])
    trace = LlmTrace(tmp_path)

    result = post_process(join_blocks(ZONE), op, trace)

    assert (result.repaired, result.reverted) == (0, 1)
    text = (tmp_path / "llm" / "post.txt").read_text(encoding="utf-8")
    assert "a totally different sentence" in text
    assert "yet another wording entirely" in text
    assert "attempt 2" in text
    assert "rejected" in text
