"""Tests for placing an edit's quote: drift, escapes, fragments, units."""

from __future__ import annotations

import pytest

from raw2md.llm.inspection.coordinator import inspect

from ._helpers import (
    FLAGGED_FORMULA_BODY,
    FORMULA_PIECES,
    MARKER_BODY,
    REPAIRED_PIECES,
    SOURCE,
    SPLIT_FORMULA_BODY,
    edits_reply,
    make_op,
    mask,
    sent_text,
    skip_reason,
)

# --- semantic substitution, line drift --------------------------------------


def test_semantic_edit_applies_with_positive_line_drift(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 4,
                "old": "Another paragraph.",
                "new": "Last paragraph.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "Last paragraph." in result.body
    assert any("line drift" in record.message for record in caplog.records)


def test_semantic_edit_applies_with_negative_line_drift() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 7,
                "old": "Another paragraph.",
                "new": "Last paragraph.",
            }
        )
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "Last paragraph." in result.body


def test_semantic_edit_skipped_on_ambiguous_drift_match() -> None:
    body = "\n".join(["Intro", "Same text", "filler", "Same text", "End", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 3, "old": "Same text", "new": "Changed"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_semantic_edit_applies_with_wide_line_drift() -> None:
    # The shape of a right line named on the wrong page.
    body = "\n".join(["A", *[f"filler {i}" for i in range(30)], "Target text", "F", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "Target text", "new": "Changed"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "Changed" in result.body


def test_semantic_edit_skipped_when_match_is_outside_drift_window() -> None:
    body = "\n".join(["A", *[f"filler {i}" for i in range(50)], "Target text", "F", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "Target text", "new": "X"}))
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_semantic_edit_with_invalid_line_number_not_applied_via_drift() -> None:
    op = make_op(
        edits_reply({"page": 1, "line": 0, "old": "# Heading", "new": "# Changed"})
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == MARKER_BODY


def test_semantic_edit_on_protected_line_not_applied_via_drift() -> None:
    body = "\n".join(["```", "code line", "```", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "code line", "new": "fixed line"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


# --- semantic substitution, escape normalization ----------------------------


def test_escaped_line_matches_unescaped_old() -> None:
    body = "\n".join(["See the diagram (Fig. 5.4\\).", "Another line \\(as is\\).", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "See the diagram (Fig. 5.4).",
                "new": "See the diagram (Figure 5.4).",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "See the diagram (Figure 5.4)." in result.body
    # The line the edit never addressed keeps its own escaping.
    assert "Another line \\(as is\\)." in result.body


def test_escaped_dollar_matches_plain_dollar() -> None:
    # The replacement keeps the escape: a bare `$` would open a delimiter.
    body = "\n".join(["Price \\$5 today.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "Price $5 today.",
                "new": "Price \\$5 tomorrow.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "Price \\$5 tomorrow." in result.body


def test_double_backslash_is_not_normalized_away() -> None:
    body = "\n".join(["a \\\\ b", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "a \\ b", "new": "a b"}))
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_escaped_leading_hyphen_does_not_match_a_bare_one() -> None:
    # Without the escape the dash turns into a live bullet.
    body = "\n".join(["\\- Not a bullet, just a dash.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "- Not a bullet, just a dash.",
                "new": "- Still not a bullet, just a dash.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_escaped_leading_ordered_marker_does_not_match_a_bare_one() -> None:
    body = "\n".join(["1\\. Not a list, just a numeral.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "1. Not a list, just a numeral.",
                "new": "1. Still not a list, just a numeral.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_escaped_hyphen_without_trailing_space_still_matches() -> None:
    body = "\n".join(["\\-dash to start.", ""])
    op = make_op(
        edits_reply(
            {"page": 1, "line": 1, "old": "-dash to start.", "new": "-dash again."}
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "-dash again." in result.body


def test_escaped_ordered_marker_without_trailing_space_still_matches() -> None:
    body = "\n".join(["3\\.14 is pi.", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "3.14 is pi.", "new": "3.14 is π."})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "3.14 is π." in result.body


def test_escaped_underscore_does_not_match_a_bare_one() -> None:
    # Nothing downstream holds the count of emphasis markers.
    body = "\n".join(["Use \\_id\\_ here.", ""])
    op = make_op(
        edits_reply(
            {"page": 1, "line": 1, "old": "Use _id_ here.", "new": "Use _id_ there."}
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_escaped_backtick_does_not_match_a_bare_one() -> None:
    body = "\n".join(["Say \\`x\\` aloud.", ""])
    op = make_op(
        edits_reply(
            {"page": 1, "line": 1, "old": "Say `x` aloud.", "new": "Say `x` loudly."}
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_escaped_bracket_does_not_match_a_bare_one() -> None:
    body = "\n".join(["See \\[note\\] below.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "See [note] below.",
                "new": "See [note] above.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_escaped_closing_paren_mid_line_still_matches() -> None:
    body = "\n".join(["See item 1\\. above for context.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "See item 1. above for context.",
                "new": "See item 1. above for full context.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "See item 1. above for full context." in result.body


# --- semantic substitution, a fragment of the line --------------------------


def test_fragment_of_the_line_replaced_in_place() -> None:
    body = "\n".join(["See the diagram (Fig. 5.4\\) and the note \\[3\\].", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "the diagram", "new": "the drawing"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert result.body == "See the drawing (Fig. 5.4\\) and the note \\[3\\].\n"


def test_fragment_quoted_without_the_bodys_escape_replaced() -> None:
    body = "\n".join(["Look at the sketch (Fig. 5.4\\) below.", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "(Fig. 5.4)", "new": "(Figure 5.4)"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert result.body == "Look at the sketch (Figure 5.4) below.\n"


def test_fragment_standing_twice_on_the_line_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(["Replace this word and then this word.", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "this word", "new": "that term"})
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body
    assert "fragment stands on the line 2 times" in skip_reason(caplog)


def test_ambiguous_fragment_still_lets_the_drift_search_run() -> None:
    # The window search still resolves `old` onto the line that carries it whole.
    body = "\n".join(["Replace this word and then this word.", "", "this word", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "this word", "new": "that term"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert result.body == "\n".join(
        ["Replace this word and then this word.", "", "that term", ""]
    )


def test_fragment_old_with_a_whole_line_new_not_spliced(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Splicing a whole-line `new` over a fragment would repeat text.
    body = "\n".join(["See the diagram (Fig. 5.4\\) and the note \\[3\\].", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "the diagram",
                "new": "See the drawing (Fig. 5.4) and the note [3].",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body
    assert "new repeats the line around the fragment" in skip_reason(caplog)


def test_whole_line_new_is_not_carried_to_a_drift_match() -> None:
    body = "\n".join(
        ["See the diagram (Fig. 5.4\\) and the note \\[3\\].", "", "the diagram", ""]
    )
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "the diagram",
                "new": "See the drawing (Fig. 5.4) and the note [3].",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_fragment_new_repeating_one_neighbouring_word_still_applies() -> None:
    body = "\n".join(["The bracket holds the shaft in the frame.", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "the shaft", "new": "the spindle"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert result.body == "The bracket holds the spindle in the frame.\n"


def test_fragment_cutting_a_word_in_two_not_replaced() -> None:
    body = "\n".join(["Here the parameter is set exactly.", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "param", "new": "dimen"}))
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_fragment_starting_inside_an_escape_pair_not_replaced() -> None:
    # `\*` stays escaped in the comparison, so the match starts inside the pair.
    body = "\n".join(["The sign \\*asterisk\\* in the text.", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "*asterisk", "new": "*star"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_fragment_edit_is_judged_by_the_whole_line() -> None:
    # The link stands outside the fragment; judged by `new` alone it looks dropped.
    body = "\n".join(["The drawing ![view](img/a.png) shows the part.", ""])
    op = make_op(
        edits_reply(
            {"page": 1, "line": 1, "old": "shows the part", "new": "shows the shaft"}
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (1, 0)
    assert result.body == "The drawing ![view](img/a.png) shows the shaft.\n"


def test_fragment_breaking_the_line_it_lands_on_rejected() -> None:
    # Only the line after the splice shows the third cell.
    body = "\n".join(["| A | B |", "| --- | --- |", "| x | y |", ""])
    op = make_op(edits_reply({"page": 1, "line": 3, "old": "x", "new": "x | z"}))
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


def test_whole_line_edit_does_not_take_the_fragment_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "Here the [unreadable] word is lost.",
                "new": "Here the word is found.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "Here the word is found." in result.body
    assert not any("names a fragment" in r.message for r in caplog.records)


def test_fragment_on_the_addressed_line_beats_a_drift_match() -> None:
    body = "\n".join(["The bracket holds the shaft in place.", "", "the shaft", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "the shaft", "new": "the spindle"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert result.body == "The bracket holds the spindle in place.\n\nthe shaft\n"


def test_fragment_not_searched_from_a_wide_drift_anchor() -> None:
    # The search starts from the last line of page 1, an origin and not an address.
    body = "\n".join(
        [
            "Sheet one.",
            "Some more text of the first sheet.",
            "Sheet two, first line.",
            "",
        ]
    )
    op = make_op(
        edits_reply({"page": 1, "line": 10, "old": "more text", "new": "extra text"})
    )
    result = inspect(body, SOURCE, op, pages=[(0, 1), (2, 2)])
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_fragment_resolves_a_drifted_address(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(["First paragraph.", "The moment $M_1$ is set by the shaft.", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "shaft", "new": "pulley"}))
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert result.body == "\n".join(
        ["First paragraph.", "The moment $M_1$ is set by the pulley.", ""]
    )
    assert any(
        "line drift" in r.message and "fragment" in r.message for r in caplog.records
    )


def test_fragment_standing_on_two_lines_nearby_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(["Heading", "Here stands a shaft.", "Else a shaft stands.", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "shaft", "new": "pulley"}))
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body
    assert "fragment stands on 2 lines near the address" in skip_reason(caplog)


def test_whole_line_nearby_beats_a_fragment_nearby() -> None:
    body = "\n".join(["Heading", "shaft", "Here stands a shaft.", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "shaft", "new": "pulley"}))
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert result.body == "\n".join(["Heading", "pulley", "Here stands a shaft.", ""])


def test_fragment_repeated_on_the_addressed_line_not_taken_nearby(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(["Here a shaft and one more shaft.", "Else stands a shaft.", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "shaft", "new": "pulley"}))
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body
    assert "fragment stands on the line 2 times" in skip_reason(caplog)


def test_fragment_inside_a_valid_math_span_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply({"page": 1, "line": 3, "old": "M_{yn1}", "new": "M_{xn1}"})
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(FLAGGED_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == FLAGGED_FORMULA_BODY
    assert any("valid math span changed" in record.message for record in caplog.records)


def test_fragment_of_a_span_the_same_reply_flagged_still_rejected() -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "flag": "broken-formula"},
            {"page": 1, "line": 3, "old": "$M_{yn1}$", "new": "$M_{xn1}$"},
        )
    )
    result = inspect(FLAGGED_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected, result.format_flags) == (0, 1, 1)
    assert result.body.count("The moment $M_{yn1}$ is set.") == 1


# --- mismatch diagnostics --------------------------------------------------


def test_empty_old_counted_apart_from_a_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(edits_reply({"page": 1, "line": 3, "old": "   ", "new": "Something."}))
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert "empty old" in skip_reason(caplog)


def test_old_that_is_only_its_own_echoed_address_counted_as_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # An empty `old` would match any blank line.
    op = make_op(
        edits_reply({"page": 1, "line": 4, "old": "1.4:", "new": "Something."})
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert "empty old" in skip_reason(caplog)


def test_echoed_own_address_prefix_is_stripped_before_matching() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "1.3: Here the [unreadable] word is lost.",
                "new": "Here the word is fully lost.",
            }
        )
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "Here the word is fully lost." in result.body


def test_echoed_address_prefix_naming_a_different_address_not_stripped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "9.3: Here the [unreadable] word is lost.",
                "new": "Here the word is fully lost.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert "no match, address prefix" in skip_reason(caplog)


def test_respaced_line_named_in_the_log(caplog: pytest.LogCaptureFixture) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "Here the  [unreadable]   word is lost.",
                "new": "Here the word is fully lost.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert "no match, whitespace" in skip_reason(caplog)


def test_quoted_fragment_named_in_the_log(caplog: pytest.LogCaptureFixture) -> None:
    op = make_op(edits_reply({"page": 1, "line": 3, "old": "los", "new": "fully los"}))
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert "no match, part of the line" in skip_reason(caplog)


def test_shape_found_on_a_neighbour_carries_its_distance(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "Another paragrap", "new": "Last paragrap"}
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    reason = skip_reason(caplog)
    assert "no match, part of the line +2 lines away" in reason
    assert "against line 'Another paragraph.'" in reason


def test_unrelated_old_logged_with_both_texts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "A wholly different line.", "new": "Other."}
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    reason = skip_reason(caplog)
    assert "no match, unrelated text" in reason
    assert "A wholly different line." in reason
    assert "Here the [unreadable] word is lost." in reason


def test_long_texts_cut_before_reaching_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(["| " + " | ".join("cell" for _ in range(60)) + " |", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 1, "old": "x" * 400, "new": "| a | b |"})
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    reason = skip_reason(caplog)
    assert "..." in reason
    assert len(reason) < 400


def test_address_on_a_page_the_body_lacks_named_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 9,
                "line": 1,
                "old": "Another paragraph.",
                "new": "Last paragraph.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert "no such address: page not in the body" in skip_reason(caplog)


def test_line_past_the_page_end_on_an_unmapped_body_logs_what_it_holds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No page marks: one synthetic page, so no wide drift anchor.
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 40,
                "old": "Another paragraph.",
                "new": "Last paragraph.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert "no such address: page holds 5 lines" in skip_reason(caplog)


def test_empty_page_logs_what_the_page_holds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(["Sheet one, first.", "Sheet one, second.", "Sheet three.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 2,
                "line": 1,
                "old": "Another paragraph.",
                "new": "Last paragraph.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op, pages=[(0, 1), (2, 2), (2, 3)])
    assert (result.applied, result.skipped) == (0, 1)
    assert "no such address: page holds 0 lines" in skip_reason(caplog)


def test_wide_drift_anchor_recovers_a_match_past_a_short_pages_end() -> None:
    # The address overshoots page 1 by more than the `PageIndex.locate` slack.
    body = "\n".join(
        [
            "Sheet one.",
            "Some more text of the first sheet.",
            "Sheet two, first line.",
            "Sheet two, second line.",
            "Target line of the second sheet.",
            "",
        ]
    )
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 10,
                "old": "Target line of the second sheet.",
                "new": "Fixed.",
            }
        )
    )
    result = inspect(body, SOURCE, op, pages=[(0, 1), (2, 2)])
    assert (result.applied, result.skipped) == (1, 0)
    assert "Fixed." in result.body


# --- multiple edits, no line drift -----------------------------------------


def test_multiple_edits_use_original_numbering() -> None:
    body = "\n".join(
        [
            "# Heading",
            "",
            "Here a word is bro-",
            "ken by a hyphen.",
            "",
            "Another paragraph.",
            "",
        ]
    )
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "flag": "hyphenation"},
            {
                "page": 1,
                "line": 6,
                "old": "Another paragraph.",
                "new": "Last paragraph.",
            },
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.format_flags) == (1, 1)
    lines = result.body.split("\n")
    assert lines[2] == "Here a word is bro-"
    assert "Last paragraph." in result.body


# --- a formula cut across lines --------------------------------------------


def test_a_cut_up_formula_carries_one_address() -> None:
    op = make_op(edits_reply())
    inspect(SPLIT_FORMULA_BODY, SOURCE, op)
    text = sent_text(op)
    for piece in FORMULA_PIECES:
        assert f"1.3: {piece}" in text
    assert "1.11: End." in text


def test_a_sound_formula_beside_a_damaged_one_keeps_its_own_address() -> None:
    body = "\n".join(
        ["# Heading", "", r"$$E = mc^2$$", "", FORMULA_PIECES[0], "", "End.", ""]
    )
    op = make_op(edits_reply())
    inspect(body, SOURCE, op)
    text = sent_text(op)
    assert f"1.3: {mask()}" in text
    assert f"1.5: {FORMULA_PIECES[0]}" in text


def test_a_formula_opening_with_a_sizing_command_is_not_read_as_a_piece() -> None:
    body = "\n".join(
        [
            "# Heading",
            "",
            FORMULA_PIECES[0],
            "",
            r"$$\left( x + y$$",
            "",
            "End.",
            "",
        ]
    )
    op = make_op(edits_reply())
    inspect(body, SOURCE, op)
    text = sent_text(op)
    assert f"1.3: {FORMULA_PIECES[0]}" in text
    assert r"1.5: $$\left( x + y$$" in text


def test_two_damaged_formulas_side_by_side_keep_their_addresses() -> None:
    body = "\n".join(
        [
            "# Heading",
            "",
            FORMULA_PIECES[0],
            "",
            r"$$P = \frac{1}{2}\left[\left(r_{k}\right)^2$$",
            "",
            "End.",
            "",
        ]
    )
    op = make_op(edits_reply())
    inspect(body, SOURCE, op)
    text = sent_text(op)
    assert f"1.3: {FORMULA_PIECES[0]}" in text
    assert r"1.5: $$P = \frac{1}{2}\left[\left(r_{k}\right)^2$$" in text


def test_an_edit_at_that_address_replaces_the_whole_formula() -> None:
    reply = edits_reply(
        {
            "page": 1,
            "line": 3,
            "old": "\n".join(FORMULA_PIECES),
            "new": "\n".join(REPAIRED_PIECES),
        }
    )
    op = make_op(reply)
    result = inspect(SPLIT_FORMULA_BODY, SOURCE, op)
    assert result.applied == 1
    assert result.body == "\n".join(["# Heading", "", *REPAIRED_PIECES, "", "End.", ""])


def test_the_quote_may_write_the_pieces_on_one_line() -> None:
    reply = edits_reply(
        {
            "page": 1,
            "line": 3,
            "old": " ".join(FORMULA_PIECES),
            "new": "\n".join(REPAIRED_PIECES),
        }
    )
    op = make_op(reply)
    result = inspect(SPLIT_FORMULA_BODY, SOURCE, op)
    assert result.applied == 1
    assert r"\begin{aligned}" not in result.body


def test_the_repair_does_not_drift_the_bodys_math_span_count() -> None:
    # The evaluator compares the span count across the LLM steps.
    from raw2md.mdtext.math_spans import math_spans

    reply = edits_reply(
        {
            "page": 1,
            "line": 3,
            "old": "\n".join(FORMULA_PIECES),
            "new": "\n".join(REPAIRED_PIECES),
        }
    )
    result = inspect(SPLIT_FORMULA_BODY, SOURCE, make_op(reply))
    assert result.applied == 1
    assert len(math_spans(result.body)) == len(math_spans(SPLIT_FORMULA_BODY))


def test_a_quote_naming_one_piece_still_edits_that_piece_alone() -> None:
    reply = edits_reply(
        {
            "page": 1,
            "line": 3,
            "old": FORMULA_PIECES[0],
            "new": REPAIRED_PIECES[0],
        }
    )
    op = make_op(reply)
    result = inspect(SPLIT_FORMULA_BODY, SOURCE, op)
    # The rebuilt piece alone is still unbalanced.
    assert result.applied == 0
    assert result.rejected == 1


def test_a_one_line_formula_is_repaired_as_before() -> None:
    body = "\n".join(["# Heading", "", r"$$E = \left( mc^2$$", "", "End.", ""])
    reply = edits_reply(
        {
            "page": 1,
            "line": 3,
            "old": r"$$E = \left( mc^2$$",
            "new": r"$$E = \left( mc^2 \right)$$",
        }
    )
    op = make_op(reply)
    result = inspect(body, SOURCE, op)
    assert result.applied == 1
    assert r"$$E = \left( mc^2 \right)$$" in result.body
