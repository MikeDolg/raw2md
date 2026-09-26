"""Tests for decoding an inspection reply and counting its flags."""

from __future__ import annotations

import json

import pytest

from raw2md.llm.inspection.common import InspectionReplyError
from raw2md.llm.inspection.coordinator import inspect

from ._helpers import (
    CONTROL_CHAR_BODY,
    CONTROL_LATEX_BODY,
    FORMULA_PIECES,
    LATEX_BODY,
    MARKER_BODY,
    QUOTED_LABEL_BODY,
    QUOTED_LIST_BODY,
    QUOTED_PHRASE_BODY,
    REPAIRED_PIECES,
    SOURCE,
    SPLIT_FORMULA_BODY,
    TABLE_BODY,
    edits_reply,
    make_op,
)

# --- a format flag writes nothing ------------------------------------------


def test_format_flag_leaves_the_body_untouched() -> None:
    # The table stage reads the row for itself.
    op = make_op(edits_reply({"page": 1, "line": 3, "flag": "broken-table"}))
    result = inspect(TABLE_BODY, SOURCE, op)
    assert (result.applied, result.format_flags) == (0, 1)
    assert result.body == TABLE_BODY


def test_an_edit_of_the_same_reply_still_applies() -> None:
    body = "\n".join(
        ["# Heading", "", "Here the [unreadable] word is lost.", "", "| x |", ""]
    )
    op = make_op(
        edits_reply(
            {"page": 1, "line": 5, "flag": "broken-table"},
            {
                "page": 1,
                "line": 3,
                "old": "Here the [unreadable] word is lost.",
                "new": "Here the clear word is back.",
            },
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.format_flags) == (1, 1)
    assert "Here the clear word is back." in result.body


def test_flags_are_counted_by_type_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "flag": "broken-table"},
            {"page": 1, "line": 3, "flag": "broken-table"},
            {"page": 1, "line": 1, "flag": "hyphenation"},
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(TABLE_BODY, SOURCE, op)
    assert result.format_flags == 3
    assert any(
        "3 format flag(s) reported" in record.message
        and "broken-table x2" in record.message
        and "hyphenation x1" in record.message
        for record in caplog.records
    )


def test_a_flag_addressing_nothing_is_counted_all_the_same() -> None:
    # A flag address is not read, so an address past the page still counts.
    op = make_op(
        edits_reply(
            *[
                {"page": 9, "line": line, "flag": "broken-table"}
                for line in (9, 10, 11, 12)
            ]
        )
    )
    result = inspect(TABLE_BODY, SOURCE, op, pages=[(0, 9)])
    assert result.format_flags == 4
    assert result.body == TABLE_BODY


def test_a_reply_of_flags_alone_parses() -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "flag": "broken-table"},
            {"page": 1, "line": 3, "flag": "flattened-block"},
        )
    )
    result = inspect(TABLE_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.format_flags) == (0, 0, 2)
    assert result.body == TABLE_BODY


def test_an_unknown_flag_type_is_counted_like_any_other() -> None:
    op = make_op(edits_reply({"page": 1, "line": 3, "flag": "not-a-real-type"}))
    result = inspect(TABLE_BODY, SOURCE, op)
    assert result.format_flags == 1
    assert result.body == TABLE_BODY


# --- tolerant reply parsing ------------------------------------------------


def test_top_level_list_reply_accepted() -> None:
    op = make_op(json.dumps([{"page": 1, "line": 3, "flag": "broken-table"}]))
    result = inspect(TABLE_BODY, SOURCE, op)
    assert result.format_flags == 1


def test_fenced_json_reply_accepted() -> None:
    op = make_op(
        "```json\n"
        + edits_reply({"page": 1, "line": 3, "flag": "broken-table"})
        + "\n```"
    )
    result = inspect(TABLE_BODY, SOURCE, op)
    assert result.format_flags == 1


def test_latex_backslashes_are_parsed_and_applied() -> None:
    # `\right` starts with a JSON control letter, so a naive decode corrupts it.
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "Let \(\alpha\) and \left( x \right) be given.", '
        r'"new": "Let \(\beta\) be given."}]}'
    )
    op = make_op(reply)
    result = inspect(LATEX_BODY, SOURCE, op)
    assert result.applied == 1
    assert r"\(\beta\) be given." in result.body
    assert r"\left(" not in result.body


def test_latex_valid_escape_letters_are_not_taken_as_control_chars() -> None:
    # `\beta`, `\to`, `\nu`, `\right` start with valid JSON escapes.
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "Sum: \beta \to \nu at \right.", '
        r'"new": "Sum: \beta at \right."}]}'
    )
    op = make_op(reply)
    result = inspect(CONTROL_LATEX_BODY, SOURCE, op)
    assert result.applied == 1
    assert r"Sum: \beta at \right." in result.body
    # `\n` is the body's own line separator.
    assert not any(c in result.body for c in "\t\r\b\f")


def test_control_character_in_place_of_a_command_is_restored_before_match() -> None:
    # `_repair_reply_text` keeps `\uXXXX`, so the control character reaches `old`.
    reply = (
        '{"edits": [{"page": 1, "line": 3, '
        '"old": "Given \\u0008eta, \\u000corall x and \\u000bec{v}.", '
        '"new": "Given \\u0008eta (fixed), \\u000corall x and \\u000bec{v}."}]}'
    )
    op = make_op(reply)
    result = inspect(CONTROL_CHAR_BODY, SOURCE, op)
    assert result.applied == 1
    assert r"Given \beta (fixed), \forall x and \vec{v}." in result.body


def test_restored_quote_that_still_does_not_match_is_skipped_as_before() -> None:
    reply = (
        '{"edits": [{"page": 1, "line": 3, '
        '"old": "Given \\u0008eta, an entirely different rest of the line.", '
        '"new": "Given beta, replaced."}]}'
    )
    op = make_op(reply)
    result = inspect(CONTROL_CHAR_BODY, SOURCE, op)
    assert result.applied == 0
    assert result.skipped == 1


def test_a_cut_formulas_newline_is_not_touched_by_the_restore() -> None:
    # `\n` joins the pieces of a cut formula and must stay a line break.
    corrupted_first_piece = FORMULA_PIECES[0].replace(r"\begin", "\\u0008egin")
    old = "\\n".join([corrupted_first_piece, *FORMULA_PIECES[1:]])
    new = "\\n".join(REPAIRED_PIECES)
    reply = (
        '{"edits": [{"page": 1, "line": 3, "old": "'
        + old
        + '", "new": "'
        + new
        + '"}]}'
    )
    op = make_op(reply)
    result = inspect(SPLIT_FORMULA_BODY, SOURCE, op)
    assert result.applied == 1
    assert result.body == "\n".join(["# Heading", "", *REPAIRED_PIECES, "", "End.", ""])


def test_a_newline_escape_with_no_letter_after_it_stays_a_line_break() -> None:
    body = "\n".join(["# Heading", "", "A line and one more.", "", "End.", ""])
    reply = (
        '{"edits": [{"page": 1, "line": 3, '
        '"old": "A line and one more.", '
        '"new": "A line\\n(one more)."}]}'
    )
    op = make_op(reply)
    result = inspect(body, SOURCE, op, pages=())
    # Only a multi-line defect may span lines.
    assert result.rejected == 1
    assert r"\n" not in result.body


def test_raw_control_character_before_closing_quote_is_escaped() -> None:
    # A literal newline before the closing quote of `old`.
    reply = (
        '{"edits": [{"page": 1, "line": 3, '
        '"old": "Here the [unreadable] word is lost.\n", '
        '"new": "Here the clear word is back."}]}'
    )
    op = make_op(reply)
    result = inspect(MARKER_BODY, SOURCE, op)
    assert result.applied == 1
    assert "Here the clear word is back." in result.body


def test_escaped_quote_and_unicode_escape_survive_repair() -> None:
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "Here the [unreadable] word is lost.", '
        r'"new": "Here the «clear» word is \"back\"."}]}'
    )
    op = make_op(reply)
    result = inspect(MARKER_BODY, SOURCE, op)
    assert result.applied == 1
    assert 'Here the «clear» word is "back".' in result.body


def test_unescaped_quotes_in_old_are_repaired() -> None:
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "**Fig. 2** "a" first, "b" second.", '
        r'"new": "Fig. 2: a first, b second."}]}'
    )
    op = make_op(reply)
    result = inspect(QUOTED_LABEL_BODY, SOURCE, op)
    assert result.applied == 1
    assert "Fig. 2: a first, b second." in result.body


def test_unescaped_quote_followed_by_comma_is_still_embedded() -> None:
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "See the chapter "general installation instructions", '
        r'then proceed.", '
        r'"new": "See the installation chapter, then proceed."}]}'
    )
    op = make_op(reply)
    result = inspect(QUOTED_PHRASE_BODY, SOURCE, op)
    assert result.applied == 1
    assert "See the installation chapter, then proceed." in result.body


def test_quote_before_comma_and_quote_is_still_embedded_without_a_known_key() -> None:
    # "B" is not a key of the reply.
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "Options: "A", "B", and "C".", '
        r'"new": "Options: A, B, and C."}]}'
    )
    op = make_op(reply)
    result = inspect(QUOTED_LIST_BODY, SOURCE, op)
    assert result.applied == 1
    assert "Options: A, B, and C." in result.body


def test_extra_unknown_key_after_new_does_not_corrupt_the_value() -> None:
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "Here the [unreadable] word is lost.", '
        r'"new": "Here the clear word is back.", '
        r'"comment": "restored from context"}]}'
    )
    op = make_op(reply)
    result = inspect(MARKER_BODY, SOURCE, op)
    assert result.applied == 1
    assert "Here the clear word is back." in result.body


def test_empty_edit_list_is_not_a_failure() -> None:
    op = make_op(edits_reply())
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.format_flags) == (0, 0, 0)
    assert result.body == MARKER_BODY


def test_unusable_reply_raises() -> None:
    op = make_op("this is not JSON at all {")
    with pytest.raises(InspectionReplyError):
        inspect(MARKER_BODY, SOURCE, op)


def test_non_list_edits_raise() -> None:
    op = make_op(json.dumps({"edits": "oops"}))
    with pytest.raises(InspectionReplyError):
        inspect(MARKER_BODY, SOURCE, op)


def test_unparseable_reply_message_carries_fragment_and_length() -> None:
    # The quote repair covers only `old` and `new`, so this quote still breaks JSON.
    broken = (
        '{"edits": [{"page": 1, "line": 5, "flag": "'
        + "a" * 300
        + '"quoted"'
        + "b" * 300
        + '"}]}'
    )
    op = make_op(broken)
    with pytest.raises(InspectionReplyError) as excinfo:
        inspect(MARKER_BODY, SOURCE, op)
    message = str(excinfo.value)
    assert f"reply length {len(broken)}" in message
    assert "quoted" in message
    assert "a" * 300 not in message
    assert "b" * 300 not in message
