"""Tests for applying inspection edits under the edit guard."""

from __future__ import annotations

import pytest

from raw2md.llm.inspection.coordinator import inspect
from raw2md.source_text import SourceText

from ._helpers import (
    CRUSHED_ROW,
    FLAGGED_FORMULA_BODY,
    MARKER_BODY,
    MATH_DAMAGE_BODY,
    NON_BREAKING_HYPHEN,
    SOUND_FORMULA_BODY,
    SOURCE,
    edits_reply,
    make_op,
    mask,
    skip_reason,
)

# --- semantic substitution -------------------------------------------------


def test_semantic_edit_applied_by_address() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "Here the [unreadable] word is lost.",
                "new": "Here the clear word is back.",
            }
        )
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.format_flags) == (1, 0, 0)
    assert "[unreadable]" not in result.body
    assert "Here the clear word is back." in result.body
    assert "# Heading" in result.body
    assert "Another paragraph." in result.body


def test_semantic_edit_skipped_on_mismatch() -> None:
    op = make_op(
        edits_reply({"page": 1, "line": 3, "old": "totally different text", "new": "X"})
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.format_flags) == (0, 1, 0)
    assert result.body == MARKER_BODY
    assert "[unreadable]" in result.body


def test_semantic_edit_skipped_out_of_range() -> None:
    op = make_op(edits_reply({"page": 1, "line": 999, "old": "anything", "new": "X"}))
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == MARKER_BODY


def test_conflicting_edits_keep_the_first() -> None:
    line = "Here the [unreadable] word is lost."
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": line, "new": "Here the first edit landed."},
            {"page": 1, "line": 3, "old": line, "new": "Here the second edit landed."},
        )
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 1)
    assert "first edit" in result.body
    assert "second edit" not in result.body


def test_noop_edit_dropped_before_address_resolution(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The address is out of range, so only the no-op cause can drop it silently.
    op = make_op(
        edits_reply({"page": 1, "line": 999, "old": "same text", "new": "same text"})
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 0)
    messages = [r.message for r in caplog.records]
    assert any("old equals new" in m for m in messages)
    assert not any("no such address" in m for m in messages)


def test_noop_edit_does_not_block_a_real_edit_at_the_same_address() -> None:
    line = "Here the [unreadable] word is lost."
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": line, "new": line},
            {"page": 1, "line": 3, "old": line, "new": "Here it is fixed."},
        )
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)
    assert "Here it is fixed." in result.body


def test_edit_differing_by_one_space_is_not_a_noop() -> None:
    line = "Here the [unreadable] word is lost."
    op = make_op(edits_reply({"page": 1, "line": 3, "old": line, "new": line + " "}))
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 0)


def test_semantic_edit_on_protected_line_skipped() -> None:
    body = "\n".join(["```", "code line", "```", ""])
    op = make_op(
        edits_reply({"page": 1, "line": 2, "old": "code line", "new": "fixed line"})
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped) == (0, 1)
    assert result.body == body


def test_whitespace_insensitive_match() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "  Here the [unreadable] word is lost.  ",
                "new": "Here the clear word is back.",
            }
        )
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert result.applied == 1
    assert "clear" in result.body


# --- the edit guard bounds an applied edit -----------------------------------


def test_rewritten_image_target_rejected(caplog: pytest.LogCaptureFixture) -> None:
    # A repointed figure still resolves, so nothing downstream notices.
    body = "\n".join(["# Heading", "", "![](media/fig_1.jpeg)", "", "End.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "![](media/fig_1.jpeg)",
                "new": "![](media/fig_2.jpeg)",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body
    assert any("image links changed" in record.message for record in caplog.records)


def test_dropped_image_link_rejected() -> None:
    body = "\n".join(["Layout ![](media/fig_1.jpeg) of the devise.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "Layout ![](media/fig_1.jpeg) of the devise.",
                "new": "Layout of the device.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


def test_literal_escape_replacement_rejected() -> None:
    # A literal `\n` substituted verbatim glues two lines into one.
    body = "\n".join(["| A | B |", "| --- | --- |", "| x | y |", ""])
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "| x | y |", "new": r"| x | y |\n| z | w |"}
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


def test_protocol_object_replacement_rejected() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 5,
                "old": "Another paragraph.",
                "new": '{"page": 1, "line": 385, "flag": "hyphenation"}',
            }
        )
    )
    result = inspect(MARKER_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == MARKER_BODY


def test_hyphenation_join_applied() -> None:
    body = "\n".join(["коэффи- циент теплоотдачи", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "коэффи- циент теплоотдачи",
                "new": "коэффициент теплоотдачи",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (1, 0)
    assert "коэффициент теплоотдачи" in result.body


def test_edit_past_what_the_markup_licenses_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join([CRUSHED_ROW, ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": CRUSHED_ROW,
                "new": "| Width 10 | Height 20 |\n| Length 30 | Diameter 40 |\n"
                "| Width 11 | Height 21 |\n| Length 31 | Diameter 41 |\n"
                "| Width 12 | Height 22 |\n| Length 32 | 42 |",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body
    assert any("rebuild changes" in record.message for record in caplog.records)


def test_word_split_rejected_without_a_source_witness() -> None:
    body = "\n".join(["The handbook is open.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "The handbook is open.",
                "new": "The hand book is open.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


def test_word_split_applied_when_the_source_witness_confirms_both_halves() -> None:
    body = "\n".join(["The handbook is open.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "The handbook is open.",
                "new": "The hand book is open.",
            }
        )
    )
    witness = SourceText(["hand book"])
    result = inspect(body, SOURCE, op, source_text=witness)
    assert (result.applied, result.rejected) == (1, 0)
    assert "hand book" in result.body


def test_word_split_witness_lookup_is_scoped_to_the_edits_own_page() -> None:
    body = "\n".join(["Sheet one.", "The handbook is open."])
    op = make_op(
        edits_reply(
            {
                "page": 2,
                "line": 1,
                "old": "The handbook is open.",
                "new": "The hand book is open.",
            }
        )
    )
    witness = SourceText(["nothing relevant here", "hand book"])
    result = inspect(body, SOURCE, op, pages=[(0, 1), (1, 2)], source_text=witness)
    assert (result.applied, result.rejected) == (1, 0)
    assert "hand book" in result.body


def test_word_split_witness_on_a_different_page_does_not_confirm() -> None:
    body = "\n".join(["Sheet one.", "The handbook is open."])
    op = make_op(
        edits_reply(
            {
                "page": 2,
                "line": 1,
                "old": "The handbook is open.",
                "new": "The hand book is open.",
            }
        )
    )
    witness = SourceText(["hand book", "nothing relevant here"])
    result = inspect(body, SOURCE, op, pages=[(0, 1), (1, 2)], source_text=witness)
    assert (result.applied, result.rejected) == (0, 1)


def test_word_split_witness_lookup_follows_a_drifted_edit_to_its_real_page() -> None:
    # The address overshoots page 1; only the wide drift anchor reaches page 2.
    body = "\n".join(["Sheet one.", "The handbook is open.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 5,
                "old": "The handbook is open.",
                "new": "The hand book is open.",
            }
        )
    )
    witness = SourceText(["nothing relevant here", "hand book"])
    result = inspect(body, SOURCE, op, pages=[(0, 1), (1, 2)], source_text=witness)
    assert (result.applied, result.rejected) == (1, 0)
    assert "hand book" in result.body


def test_word_break_rejected_when_nothing_spells_the_word_that_way() -> None:
    body = "\n".join(["The module is designed for mounting.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": "The module is designed for mounting.",
                "new": (
                    "The module is desig" + NON_BREAKING_HYPHEN + "ned for mounting."
                ),
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


def test_word_break_applied_when_the_body_spells_the_compound() -> None:
    # The body spells the compound with a hyphen; no source layer is passed.
    body = "\n".join(["A cost-effective option.", "A costeffective solution.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 2,
                "old": "A costeffective solution.",
                "new": "A cost-effective solution.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (1, 0)
    assert "A cost-effective solution." in result.body


def test_hyphen_in_a_link_target_does_not_witness_a_word_break() -> None:
    body = "\n".join(
        ["![Layout](media/cost-effective.png)", "A costeffective solution.", ""]
    )
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 2,
                "old": "A costeffective solution.",
                "new": "A cost-effective solution.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)


def test_minus_sign_in_a_formula_does_not_witness_a_word_break() -> None:
    body = "\n".join(["Let $x-y$ be given.", "The value xy is zero.", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 2,
                "old": "The value xy is zero.",
                "new": "The value x-y is zero.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)


def test_table_separator_narrowing_rejected() -> None:
    # The separator sets the width every body row is measured against.
    body = "\n".join(["| A | B | C |", "| --- | --- | --- |", "| x | y | z |", ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 2,
                "old": "| --- | --- | --- |",
                "new": "| --- | --- |",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


def test_display_delimiter_rewritten_as_prose_rejected() -> None:
    body = "\n".join(["$$", "E = mc^2", "$$", ""])
    op = make_op(edits_reply({"page": 1, "line": 1, "old": "$$", "new": "Formula:"}))
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


# --- two edits on one line --------------------------------------------------

TWO_DEFECTS_BODY = "\n".join(
    ["# Heading", "", "Check the pummp and valf of the unit.", "", "End.", ""]
)


def test_two_fragment_edits_on_one_line_both_apply() -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "pummp", "new": "pump"},
            {"page": 1, "line": 3, "old": "valf", "new": "valve"},
        )
    )
    result = inspect(TWO_DEFECTS_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (2, 0)
    assert "Check the pump and valve of the unit." in result.body


def test_second_fragment_edit_does_not_depend_on_the_reply_order() -> None:
    first = {"page": 1, "line": 3, "old": "pummp", "new": "pump"}
    second = {"page": 1, "line": 3, "old": "valf", "new": "valve"}
    forward = inspect(TWO_DEFECTS_BODY, SOURCE, make_op(edits_reply(first, second)))
    backward = inspect(TWO_DEFECTS_BODY, SOURCE, make_op(edits_reply(second, first)))
    assert forward.body == backward.body
    assert (backward.applied, backward.skipped) == (2, 0)


def test_whole_line_edit_over_a_fragment_is_a_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "pummp", "new": "pump"},
            {
                "page": 1,
                "line": 3,
                "old": "Check the pummp and valf of the unit.",
                "new": "Check the pump and valve of the unit.",
            },
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(TWO_DEFECTS_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 1)
    assert "Check the pump and valf of the unit." in result.body
    assert "conflict" in skip_reason(caplog)


def test_fragment_edit_over_a_whole_line_edit_is_a_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "Check the pummp and valf of the unit.",
                "new": "Check the pump and valve of the unit.",
            },
            {"page": 1, "line": 3, "old": "valf", "new": "valve"},
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(TWO_DEFECTS_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 1)
    assert "conflict" in skip_reason(caplog)


def test_overlapping_fragment_edits_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "pummp and", "new": "pump and"},
            {"page": 1, "line": 3, "old": "and valf", "new": "and valve"},
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(TWO_DEFECTS_BODY, SOURCE, op)
    assert (result.applied, result.skipped) == (1, 1)
    assert "Check the pump and valf of the unit." in result.body
    assert "conflict" in skip_reason(caplog)


# --- a flag of the reply licenses nothing ----------------------------------


_FLAGGED_FORMULA_EDIT = {
    "page": 1,
    "line": 3,
    "old": "The moment $M_{yn1}$ is set.",
    "new": "The moment $M_{xn1}$ is set.",
}


def test_flag_of_the_same_reply_does_not_license_its_edit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "flag": "broken-formula"}, _FLAGGED_FORMULA_EDIT
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(FLAGGED_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected, result.format_flags) == (0, 1, 1)
    assert result.body == FLAGGED_FORMULA_BODY
    assert any("valid math span changed" in record.message for record in caplog.records)


def test_an_edit_carrying_no_flag_is_rejected_the_same_way(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(edits_reply(_FLAGGED_FORMULA_EDIT))
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(FLAGGED_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == FLAGGED_FORMULA_BODY
    assert any("valid math span changed" in record.message for record in caplog.records)


def test_flag_naming_another_defect_of_the_line_changes_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(
        [
            "# Heading",
            "",
            "The moment $M_{yn1}$ is set by hy-",
            "phenation.",
            "",
            "End.",
            "",
        ]
    )
    edit = {
        "page": 1,
        "line": 3,
        "old": "The moment $M_{yn1}$ is set by hy-",
        "new": "The moment $M_{xn1}$ is set by hy-",
    }
    op = make_op(edits_reply({"page": 1, "line": 3, "flag": "hyphenation"}, edit))
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected, result.format_flags) == (0, 1, 1)
    assert any("valid math span changed" in record.message for record in caplog.records)


def test_flag_of_the_reply_does_not_lift_the_other_bans(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = "\n".join(
        [
            "# Heading",
            "",
            "The moment $M_{yn1}$ is set on sheet 15.",
            "",
            "End.",
            "",
        ]
    )
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "flag": "broken-formula"},
            {
                "page": 1,
                "line": 3,
                "old": "The moment $M_{yn1}$ is set on sheet 15.",
                "new": "The moment $M_{yn1}$ is set on sheet 16.",
            },
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected, result.format_flags) == (0, 1, 1)
    assert any("digit runs changed" in record.message for record in caplog.records)


def test_math_repair_edit_applied_as_semantic_edit() -> None:
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "The value $\mbox{E} = \left( x$ is found.", '
        r'"new": "The value $\text{E} = \left( x \right)$ is found."}]}'
    )
    op = make_op(reply)
    result = inspect(MATH_DAMAGE_BODY, SOURCE, op)
    assert result.applied == 1
    assert r"\text{E} = \left( x \right)" in result.body
    assert r"\mbox" not in result.body


def test_applied_math_span_edit_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    reply = (
        r'{"edits": [{"page": 1, "line": 3, '
        r'"old": "The value $\mbox{E} = \left( x$ is found.", '
        r'"new": "The value $\text{E} = \left( x \right)$ is found."}]}'
    )
    op = make_op(reply)
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MATH_DAMAGE_BODY, SOURCE, op)
    assert result.applied == 1
    before, after = (
        repr(r"$\mbox{E} = \left( x$"),
        repr(r"$\text{E} = \left( x \right)$"),
    )
    assert any(
        before in record.message and after in record.message
        for record in caplog.records
    )


def test_non_math_edit_does_not_log_a_math_span_change(
    caplog: pytest.LogCaptureFixture,
) -> None:
    reply = edits_reply(
        {
            "page": 1,
            "line": 3,
            "old": "Here the [unreadable] word is lost.",
            "new": "Here the word is lost.",
        }
    )
    op = make_op(reply)
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(MARKER_BODY, SOURCE, op)
    assert result.applied == 1
    assert not any("math span changed" in record.message for record in caplog.records)


# --- the lines the pass wrote ----------------------------------------------


def test_touched_lines_name_the_substitution() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "Here the [unreadable] word is lost.",
                "new": "Here the clear word is back.",
            },
            {"page": 1, "line": 5, "flag": "flattened-block"},
        )
    )

    result = inspect(f"{CRUSHED_ROW}\n\n".join([MARKER_BODY, ""]), SOURCE, op)

    lines = result.body.split("\n")
    assert [lines[i] for i in sorted(result.touched.edited)] == [
        "Here the clear word is back."
    ]


def test_touched_lines_cover_every_line_of_a_multi_line_replacement() -> None:
    body = "\n".join([CRUSHED_ROW, ""])
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 1,
                "old": CRUSHED_ROW,
                "new": "| Width 10 | Height 20 | Length 30 | Diameter 40 |\n"
                "| --- | --- | --- | --- |\n"
                "| Width 11 | Height 21 | Length 31 | Diameter 41 |\n"
                "| Width 12 | Height 22 | Length 32 | Diameter 42 |",
            }
        )
    )

    result = inspect(body, SOURCE, op)

    lines = result.body.split("\n")
    assert [lines[i] for i in sorted(result.touched.edited)] == [
        "| Width 10 | Height 20 | Length 30 | Diameter 40 |",
        "| --- | --- | --- | --- |",
        "| Width 11 | Height 21 | Length 31 | Diameter 41 |",
        "| Width 12 | Height 22 | Length 32 | Diameter 42 |",
    ]


def test_touched_lines_are_empty_when_nothing_was_written() -> None:
    result = inspect(MARKER_BODY, SOURCE, make_op(edits_reply()))

    assert result.touched.edited == frozenset()


# --- --llm-latex-fix opens a formula ----------------------------------------


def test_valid_span_rejected_without_the_flag(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "The moment $M_{yn1}$ is set.",
                "new": "The moment $M_{xn1}$ is set.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(FLAGGED_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == FLAGGED_FORMULA_BODY
    assert any("valid math span changed" in record.message for record in caplog.records)


def test_valid_span_applied_under_the_flag() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "The moment $M_{yn1}$ is set.",
                "new": "The moment $M_{xn1}$ is set.",
            }
        ),
        latex_fix=True,
    )
    result = inspect(FLAGGED_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (1, 0)
    assert "The moment $M_{xn1}$ is set." in result.body


def test_flag_leaves_the_prose_of_the_line_closed() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": "The moment $M_{yn1}$ is set.",
                "new": "The moment $M_{xn1}$ is found.",
            }
        ),
        latex_fix=True,
    )
    result = inspect(FLAGGED_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == FLAGGED_FORMULA_BODY


# --- a display line keeps its closing delimiter ------------------------------


def test_sentence_mark_behind_the_closer_is_folded_inside_the_span(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A mark left behind `$$` stops the block from rendering.
    op = make_op(
        edits_reply({"page": 1, "line": 5, "old": mask(), "new": f"{mask()}."})
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 0, 0)
    assert "$$E = mc^2.$$" in result.body.split("\n")
    assert any("fold the sentence mark" in record.message for record in caplog.records)


def test_a_unit_behind_the_closer_is_refused() -> None:
    op = make_op(
        edits_reply({"page": 1, "line": 5, "old": mask(), "new": f"{mask()} kgf/cm"})
    )
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (0, 0, 1)
    assert result.body == SOUND_FORMULA_BODY


# The formula is spelled out, not masked, as `latex_fix` sends it.
FRAGMENT_FORMULA_BODY = "\n".join(
    ["# Heading", "", "The moment is set.", "", "$$a = b + c$$", "", "End.", ""]
)


def test_a_fragment_after_the_fold_does_not_rebuild_the_line() -> None:
    # Rebuilt from the line as it arrived, the folded mark would be lost.
    op = make_op(
        edits_reply(
            {"page": 1, "line": 5, "old": "a", "new": "x"},
            {"page": 1, "line": 5, "old": "c$$", "new": "c$$."},
            {"page": 1, "line": 5, "old": "b", "new": "y"},
        ),
        latex_fix=True,
    )
    result = inspect(FRAGMENT_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (2, 1, 0)
    assert "$$x = b + c.$$" in result.body.split("\n")
