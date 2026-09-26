"""Tests for masking sound formulas out of the inspection request."""

from __future__ import annotations

import pytest

from raw2md.llm.inspection.coordinator import inspect

from ._helpers import (
    MASK_BRACKET,
    MATH_DAMAGE_BODY,
    SOUND_FORMULA_BODY,
    SOURCE,
    edits_reply,
    make_op,
    mask,
    sent_text,
)

# --- a sound formula is masked out of the request ---------------------------


def test_sound_span_goes_into_the_request_as_a_mask() -> None:
    op = make_op(edits_reply())
    inspect(SOUND_FORMULA_BODY, SOURCE, op)
    sent = sent_text(op)
    assert f"The moment {mask()} is set." in sent
    assert f"1.5: {mask()}" in sent
    assert "$" not in sent


def test_damaged_span_goes_into_the_request_as_it_stands() -> None:
    op = make_op(edits_reply())
    inspect(MATH_DAMAGE_BODY, SOURCE, op)
    sent = sent_text(op)
    assert r"The value $\mbox{E} = \left( x$ is found." in sent
    assert MASK_BRACKET not in sent


def test_unclosed_math_region_goes_into_the_request_as_it_stands() -> None:
    # The region content reads as sound; only the missing closer is wrong.
    body = "\n".join(
        ["# Heading", "", r"The value $x \cdot y is found.", "", "End.", ""]
    )
    op = make_op(edits_reply())
    inspect(body, SOURCE, op)
    sent = sent_text(op)
    assert r"The value $x \cdot y is found." in sent
    assert MASK_BRACKET not in sent


def test_flag_shows_every_span_as_it_stands() -> None:
    op = make_op(edits_reply(), latex_fix=True)
    inspect(SOUND_FORMULA_BODY, SOURCE, op)
    sent = sent_text(op)
    assert "The moment $M_{yn1}$ is set." in sent
    assert "$$E = mc^2$$" in sent
    assert MASK_BRACKET not in sent


TWO_SPAN_BODY = "\n".join(
    ["# Heading", "", "Here $a$ and $b$ are equal.", "", "End.", ""]
)


def test_edit_quoting_the_mask_is_applied_over_the_bodys_own_span() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The moment {mask()} is set.",
                "new": f"The moment {mask()} is found.",
            }
        )
    )
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 0, 0)
    assert "The moment $M_{yn1}$ is found." in result.body


def test_unmasked_edit_puts_the_spans_back_in_the_bodys_own_order() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"Here {mask(1)} and {mask(2)} are equal.",
                "new": f"Here {mask(1)} and {mask(2)} are unequal.",
            }
        )
    )
    result = inspect(TWO_SPAN_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 0, 0)
    assert "Here $a$ and $b$ are unequal." in result.body


def test_the_formula_the_reply_wrote_is_thrown_away() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The moment {mask()} is set.",
                "new": "The moment $M_{yn1} + 1$ is found.",
            }
        )
    )
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 0, 0)
    assert "The moment $M_{yn1}$ is found." in result.body


def test_edit_returning_fewer_formulas_is_refused() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"Here {mask(1)} and {mask(2)} are equal.",
                "new": f"Here {mask(1)} and they are unequal.",
            }
        )
    )
    result = inspect(TWO_SPAN_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == TWO_SPAN_BODY


def test_edit_reordering_the_placeholders_is_refused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"Here {mask(1)} and {mask(2)} are equal.",
                "new": f"Here {mask(2)} and {mask(1)} are equal.",
            }
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(TWO_SPAN_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == TWO_SPAN_BODY
    assert any(
        "reorders the placeholders" in record.message for record in caplog.records
    )


def test_a_condemned_span_inside_the_quote_keeps_the_replys_repair() -> None:
    body = "\n".join(
        [
            "# Heading",
            "",
            r"The value $M_{yn1}$ and $\mbox{E} = \left( x$ is found.",
            "",
            "End.",
            "",
        ]
    )
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The value {mask()} and " + r"$\mbox{E} = \left( x$ is found.",
                "new": f"The value {mask()} and "
                r"$\text{E} = \left( x \right)$ is found.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 0, 0)
    assert (
        r"The value $M_{yn1}$ and $\text{E} = \left( x \right)$ is found."
        in result.body
    )


def test_a_placeholder_where_the_quote_held_a_formula_is_refused() -> None:
    body = "\n".join(
        [
            "# Heading",
            "",
            r"The value $M_{yn1}$ and $\mbox{E} = \left( x$ is found.",
            "",
            "End.",
            "",
        ]
    )
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The value {mask()} and " + r"$\mbox{E} = \left( x$ is found.",
                "new": f"The value {mask()} and {mask()} is found.",
            }
        )
    )
    result = inspect(body, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == body


def test_edit_carrying_a_broken_placeholder_is_refused() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The moment {mask()} is set.",
                "new": "The moment ⟦valid formula⟧ is found.",
            }
        )
    )
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.rejected) == (0, 1)
    assert result.body == SOUND_FORMULA_BODY


def test_unmasked_edit_lands_beside_an_ordinary_one() -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "The moment", "new": "The moment of force"},
            {
                "page": 1,
                "line": 3,
                "old": f"{mask()} is set.",
                "new": f"{mask()} is found.",
            },
        )
    )
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (2, 0, 0)
    assert "The moment of force $M_{yn1}$ is found." in result.body


def test_unmasked_edit_conflicting_with_an_applied_one_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    op = make_op(
        edits_reply(
            {"page": 1, "line": 3, "old": "set", "new": "found"},
            {
                "page": 1,
                "line": 3,
                "old": f"{mask()} is set.",
                "new": f"{mask()} is found.",
            },
        )
    )
    with caplog.at_level("INFO", logger="raw2md"):
        result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 1, 0)
    assert "The moment $M_{yn1}$ is found." in result.body
    assert any("conflict" in record.message for record in caplog.records)


# One formula twice on a line and once alone below it.
REPEATED_SPAN_BODY = "\n".join(
    [
        "# Heading",
        "",
        "The value $a$ is small. The value $a$ is small.",
        "",
        "The value $a$ is small.",
        "",
        "End.",
        "",
    ]
)


def test_unmasked_edit_keeps_the_occurrence_its_quote_named() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The value {mask(2)} is small.",
                "new": f"The value {mask(2)} is large.",
            }
        )
    )
    result = inspect(REPEATED_SPAN_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 0, 0)
    assert "The value $a$ is small. The value $a$ is large." in result.body


def test_unmasked_edit_leaves_the_line_its_quote_repeats_alone() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The value {mask(2)} is small.",
                "new": f"The value {mask(2)} is large.",
            }
        )
    )
    result = inspect(REPEATED_SPAN_BODY, SOURCE, op)
    assert result.body.count("The value $a$ is small.") == 2
    assert "The value $a$ is small." in result.body.split("\n")


def test_flag_leaves_a_quoted_placeholder_unread() -> None:
    op = make_op(
        edits_reply(
            {
                "page": 1,
                "line": 3,
                "old": f"The moment {mask()} is set.",
                "new": f"The moment {mask()} is found.",
            }
        ),
        latex_fix=True,
    )
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (0, 1, 0)
    assert result.body == SOUND_FORMULA_BODY


def test_masked_line_still_takes_an_edit_beside_its_formula() -> None:
    op = make_op(edits_reply({"page": 1, "line": 3, "old": "set", "new": "found"}))
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert (result.applied, result.skipped, result.rejected) == (1, 0, 0)
    assert "The moment $M_{yn1}$ is found." in result.body


def test_masking_leaves_the_rebuilt_body_byte_for_byte() -> None:
    op = make_op(edits_reply())
    result = inspect(SOUND_FORMULA_BODY, SOURCE, op)
    assert result.body == SOUND_FORMULA_BODY
