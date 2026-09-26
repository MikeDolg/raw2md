"""Tests for recovering a heading the source never marked with `#`.

A text route converts an unstyled document into paragraphs: a heading marked
only by bold, by capitals, or by a bare section number arrives as prose. The
paragraph repairs that make a torn title whole are tested here too.
"""

from __future__ import annotations

from raw2md.cleaner import CleanOptions, clean, clean_in_place
from raw2md.header import ConversionMethod

from ._helpers import (
    body,
    clean_full_text,
    clean_text,
    outlined,
)

# ---- headings marker lost to plain text ---------------------------------------

# marker dropped the marker of a `6.1.1.1`-depth heading; its parent is present.
_LOST_HEADING_TEXT = (
    "# 6 Maintenance\n"
    "\n"
    "## 6.1 Inspection\n"
    "\n"
    "### 6.1.1 Visual check\n"
    "\n"
    "#### 6.1.1.1 Interval\n"
    "\n"
    "### 6.1.3 Valve check\n"
    "\n"
    "6.1.3.1 Interval\n"
    "\n"
    "Once a year.\n"
)


def test_lost_numbered_heading_is_restored_at_its_depth_level() -> None:
    assert clean_in_place(_LOST_HEADING_TEXT) == _LOST_HEADING_TEXT.replace(
        "\n6.1.3.1 Interval\n", "\n#### 6.1.3.1 Interval\n"
    )


def test_restored_heading_is_stable_on_a_second_clean() -> None:
    once = clean(_LOST_HEADING_TEXT)
    assert clean(once) == once


def test_number_line_without_a_parent_heading_is_left_alone() -> None:
    # Chapter 9 has no heading, so `9.4` is a figure label glued to a number.
    text = "## 8.1 Cups\n\n## 8.2 Covers\n\n9.4 Fig. 9.5\n\n## 10.1 Shafts\n"
    assert clean_in_place(text) == text


def test_number_line_without_letters_is_left_alone() -> None:
    text = "# 1 A\n\n## 1.1 B\n\n1.5 2.47\n\n## 1.9 C\n"
    assert clean_in_place(text) == text


def test_number_line_inside_a_paragraph_is_left_alone() -> None:
    text = (
        "\n".join(
            [
                "# 1 A",
                "",
                "## 1.1 B",
                "",
                "According to the section:",
                "1.5 Interval",
                "",
                "## 1.9 C",
            ]
        )
        + "\n"
    )
    assert clean_in_place(text) == text


def test_number_out_of_its_sequence_is_left_alone() -> None:
    text = "# 1 A\n\n1.9 Interval\n\n## 1.1 B\n\n## 1.2 C\n"
    assert clean_in_place(text) == text


def test_number_of_a_depth_without_headings_is_left_alone() -> None:
    text = "# 1 A\n\n## 1.1 B\n\n1.1.5 Interval\n\n## 1.2 C\n"
    assert clean_in_place(text) == text


def test_number_in_a_list_item_is_left_alone() -> None:
    text = "# 1 A\n\n## 1.1 B\n\n- 1.5 Interval\n\n## 1.9 C\n"
    assert clean_in_place(text) == text


def test_number_line_in_a_code_fence_is_left_alone() -> None:
    text = "# 1 A\n\n## 1.1 B\n\n```\n1.5 Interval\n```\n\n## 1.9 C\n"
    assert clean_in_place(text) == text


# The opening paragraph on the line that lost its heading marker.
_LOST_RUN_IN_TAIL = (
    "The original fixture holds an infinitely long rod clamped between two "
    "rigid steel jaws, loaded in plain bending and cooled along its lateral "
    "faces, and every later section of the report compares its own "
    "solution against that configuration."
)

_LOST_RUN_IN_TEXT = (
    "# 3 Method\n"
    "\n"
    "## 3.1 Setup\n"
    "\n"
    "Text.\n"
    "\n"
    f"3.2 Test Arrangements. {_LOST_RUN_IN_TAIL}\n"
    "\n"
    "## 3.3 Results\n"
)

_LOST_RUN_IN_SPLIT = (
    "# 3 Method\n"
    "\n"
    "## 3.1 Setup\n"
    "\n"
    "Text.\n"
    "\n"
    "## 3.2 Test Arrangements\n"
    "\n"
    f"{_LOST_RUN_IN_TAIL}\n"
    "\n"
    "## 3.3 Results\n"
)


def test_lost_heading_fused_with_its_paragraph_is_split() -> None:
    assert len(_LOST_RUN_IN_TEXT.splitlines()[6]) > 200
    assert clean_in_place(_LOST_RUN_IN_TEXT) == _LOST_RUN_IN_SPLIT


def test_split_promotion_is_stable_on_a_second_clean() -> None:
    once = clean(_LOST_RUN_IN_TEXT)
    assert clean(once) == once


def test_split_promotion_keeps_the_outline_levels_aligned() -> None:
    # The split moves every line below it; settled levels must stay settled.
    text = _LOST_RUN_IN_TEXT + "\n## Discussion\n"
    options = outlined((2, "Discussion"))

    assert clean_in_place(text, options) == _LOST_RUN_IN_SPLIT + "\n## Discussion\n"


def test_paragraph_too_long_to_be_a_title_is_not_promoted() -> None:
    paragraph = "3.2 Interval of the valve check. " + " ".join(
        ["The check is done once a year."] * 8
    )
    text = "\n".join(
        [
            "# 3 Maintenance",
            "",
            "## 3.1 Inspection",
            "",
            paragraph,
            "",
            "## 3.3 Check",
            "",
        ]
    )

    assert len(paragraph) > 200
    assert clean_in_place(text) == text


def test_paragraph_within_title_length_is_still_promoted() -> None:
    text = "\n".join(
        [
            "# 3 Maintenance",
            "",
            "## 3.1 Inspection",
            "",
            "3.2 Interval of the valve check",
            "",
            "## 3.3 Check",
            "",
        ]
    )

    assert clean_in_place(text) == text.replace("\n3.2 Interval", "\n## 3.2 Interval")


# ---- headings a source marked in bold instead of styling ----------------------


# Headings marked only in bold, as an unstyled docx converts.
_UNSTYLED_TEXT = body(
    "**INTRO**",
    "Text.",
    "**2.1 Alpha**",
    "Text.",
    "**2.1.1 One**",
    "Text.",
    "**2.1.2 Two**",
    "Text.",
    "**2.1.3 Three**",
    "Text.",
)

_UNSTYLED_RECOVERED = body(
    "# INTRO",
    "Text.",
    "## 2.1 Alpha",
    "Text.",
    "### 2.1.1 One",
    "Text.",
    "### 2.1.2 Two",
    "Text.",
    "### 2.1.3 Three",
    "Text.",
)


def test_bold_ladder_is_promoted_by_its_numbering_depth() -> None:
    assert clean_text(_UNSTYLED_TEXT) == _UNSTYLED_RECOVERED


def test_recovery_is_stable_on_a_second_clean() -> None:
    once = clean_full_text(_UNSTYLED_TEXT)
    assert clean_full_text(once) == once


def test_underscore_wrap_is_recovered_too() -> None:
    text = _UNSTYLED_TEXT.replace("**", "__")
    assert clean_text(text) == _UNSTYLED_RECOVERED


def test_bold_paragraphs_without_a_ladder_stay_prose() -> None:
    text = body("**INTRO**", "Text.", "**2.1 Alpha**", "Text.", "**2.2 Beta**")
    assert clean_text(text) == text


def test_recovery_is_off_when_the_body_already_has_a_heading() -> None:
    text = "# Preface\n\n" + _UNSTYLED_TEXT
    assert clean_text(text) == text


def test_recovery_is_off_when_the_body_has_a_setext_heading() -> None:
    text = "Preface\n=======\n\n" + _UNSTYLED_TEXT
    assert clean_text(text) == text


def test_ladder_without_a_heading_of_its_own_parent_is_promoted() -> None:
    # Five siblings under one wrap are their own evidence once a ladder is proven.
    text = body(
        "**1.1.1 One**",
        "Text.",
        "**1.1.2 Two**",
        "Text.",
        "**1.1.3 Three**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 A**",
        "Text.",
        "**2.1.2 B**",
        "Text.",
        "**2.1.3 C**",
    )
    assert clean_text(text) == body(
        "### 1.1.1 One",
        "Text.",
        "### 1.1.2 Two",
        "Text.",
        "### 1.1.3 Three",
        "Text.",
        "## 2.1 Alpha",
        "Text.",
        "### 2.1.1 A",
        "Text.",
        "### 2.1.2 B",
        "Text.",
        "### 2.1.3 C",
    )


def test_numbered_paragraph_without_a_parent_is_left_wrapped() -> None:
    text = _UNSTYLED_TEXT + "\n**3.9.9 Orphan**\n"
    assert clean_text(text) == _UNSTYLED_RECOVERED + "\n**3.9.9 Orphan**\n"


def test_number_out_of_its_sequence_is_left_wrapped() -> None:
    text = _UNSTYLED_TEXT + "\n**2.1.2 Again**\n"
    assert clean_text(text) == _UNSTYLED_RECOVERED + "\n**2.1.2 Again**\n"


def test_label_out_of_sequence_above_the_ladder_is_left_wrapped() -> None:
    # Bounded on both sides, `9.4` stays wrapped; losing `2.1` is the cheaper error.
    text = body(
        "**9.4 Fig. 9.5**",
        "Text.",
        "**INTRO**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_text(text) == body(
        "**9.4 Fig. 9.5**",
        "Text.",
        "## INTRO",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
    )


def test_lead_in_to_a_list_is_not_promoted() -> None:
    text = _UNSTYLED_TEXT + "\n**Key findings:**\n"
    assert clean_text(text) == _UNSTYLED_RECOVERED + "\n**Key findings:**\n"


def test_lowercase_opening_is_not_promoted() -> None:
    text = _UNSTYLED_TEXT + "\n**and its limits**\n"
    assert clean_text(text) == _UNSTYLED_RECOVERED + "\n**and its limits**\n"


def test_paragraph_right_below_another_wrapped_one_is_not_promoted_on_its_own() -> None:
    # The second half of the title above, merged by case agreement.
    text = body(
        "**INTRO**",
        "**UNDER THE HEAT**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_text(text) == body(
        "# INTRO UNDER THE HEAT",
        "Text.",
        "## 2.1 Alpha",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
    )


def test_uppercase_tail_is_not_merged_into_a_mixed_case_heading() -> None:
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha**",
        "**AND ITS LIMITS**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "Text.",
        "## 2.1 Alpha",
        "**AND ITS LIMITS**",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
    )


def test_lowercase_tail_still_needs_a_numbered_heading() -> None:
    text = body(
        "**INTRO**",
        "**and its scope**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "**and its scope**",
        "Text.",
        "## 2.1 Alpha",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
    )


def test_uppercase_tail_ending_in_a_full_stop_is_not_joined() -> None:
    # A trailing full stop marks a sentence set in capitals.
    text = body(
        "**INTRO**",
        "**THIS IS A WARNING.**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "**THIS IS A WARNING.**",
        "Text.",
        "## 2.1 Alpha",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
    )


def test_uppercase_tail_merge_is_stable_on_a_second_clean() -> None:
    text = body(
        "**INTRO**",
        "**UNDER THE HEAT**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    once = clean_full_text(text)
    assert clean_full_text(once) == once


def test_uppercase_tail_merge_is_off_on_the_marker_route() -> None:
    options = CleanOptions(method=ConversionMethod.MARKER)
    text = body(
        "**INTRO**",
        "**UNDER THE HEAT**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_in_place(text, options) == text


def test_wrapped_paragraph_inside_a_paragraph_is_left_alone() -> None:
    text = _UNSTYLED_TEXT + "\n**2.1.4 Four**\nstill the same paragraph\n"
    assert clean_text(text) == (
        _UNSTYLED_RECOVERED + "\n**2.1.4 Four**\nstill the same paragraph\n"
    )


def test_partially_wrapped_paragraph_is_left_alone() -> None:
    text = _UNSTYLED_TEXT + "\n**Alpha** and **Beta**\n"
    assert clean_text(text) == _UNSTYLED_RECOVERED + "\n**Alpha** and **Beta**\n"


def test_wrapped_paragraph_without_letters_is_left_alone() -> None:
    text = _UNSTYLED_TEXT + "\n**123**\n"
    assert clean_text(text) == _UNSTYLED_RECOVERED + "\n**123**\n"


def test_bold_ladder_in_a_code_fence_is_not_recovered() -> None:
    text = "```\n" + _UNSTYLED_TEXT + "```\n"
    assert clean_text(text) == text


# ---- headings a source marked by case instead of numbering ---------------------


# No numbering: every section is a standalone all-caps line.
_CAPS_TEXT = body(
    "INTRODUCTION",
    "Text.",
    "METHOD OF MEASUREMENT",
    "Text.",
    "CONCLUSIONS",
    "Text.",
)

_CAPS_RECOVERED = body(
    "## INTRODUCTION",
    "Text.",
    "## METHOD OF MEASUREMENT",
    "Text.",
    "## CONCLUSIONS",
    "Text.",
)


def test_three_all_caps_paragraphs_are_promoted() -> None:
    assert clean_text(_CAPS_TEXT) == _CAPS_RECOVERED


def test_all_caps_recovery_is_stable_on_a_second_clean() -> None:
    once = clean_full_text(_CAPS_TEXT)
    assert clean_full_text(once) == once


def test_wrapped_all_caps_paragraphs_are_promoted_too() -> None:
    text = body("**INTRODUCTION**", "Text.", "**METHOD**", "Text.", "**RESULTS**")
    assert clean_text(text) == body(
        "## INTRODUCTION", "Text.", "## METHOD", "Text.", "## RESULTS"
    )


def test_two_all_caps_paragraphs_are_not_enough() -> None:
    text = body("INTRODUCTION", "Text.", "CONCLUSIONS", "Text.")
    assert clean_text(text) == text


def test_long_all_caps_paragraph_is_not_promoted() -> None:
    shout = " AND ".join(["THIS CLAUSE RUNS ON"] * 8)
    text = body("INTRODUCTION", "Text.", "METHOD", "Text.", shout, "CONCLUSIONS")
    assert clean_text(text) == body(
        "## INTRODUCTION", "Text.", "## METHOD", "Text.", shout, "## CONCLUSIONS"
    )


def test_all_caps_sentence_ending_in_a_full_stop_is_not_promoted() -> None:
    text = body("INTRODUCTION", "Text.", "METHOD", "Text.", "NOTE THIS.", "RESULTS")
    assert clean_text(text) == body(
        "## INTRODUCTION", "Text.", "## METHOD", "Text.", "NOTE THIS.", "## RESULTS"
    )


def test_repeated_all_caps_line_is_not_promoted() -> None:
    text = body(
        "INTRODUCTION",
        "BULLETIN OF GEARING",
        "Text.",
        "METHOD",
        "BULLETIN OF GEARING",
        "Text.",
        "CONCLUSIONS",
    )
    assert clean_text(text) == body(
        "## INTRODUCTION",
        "BULLETIN OF GEARING",
        "Text.",
        "## METHOD",
        "BULLETIN OF GEARING",
        "Text.",
        "## CONCLUSIONS",
    )


def test_all_caps_list_item_is_not_promoted() -> None:
    text = body("INTRODUCTION", "Text.", "METHOD", "Text.", "- ITEM", "CONCLUSIONS")
    assert clean_text(text) == body(
        "## INTRODUCTION", "Text.", "## METHOD", "Text.", "- ITEM", "## CONCLUSIONS"
    )


def test_all_caps_title_tail_is_left_for_the_merge() -> None:
    # The refusal of the tail must not cascade to the next title.
    text = body(
        "MEASURING GEAR BACKLASH",
        "IN SMALL SERVO DRIVES",
        "INTRODUCTION",
        "Text.",
        "CONCLUSIONS",
        "Text.",
    )
    assert clean_text(text) == body(
        "## MEASURING GEAR BACKLASH",
        "IN SMALL SERVO DRIVES",
        "## INTRODUCTION",
        "Text.",
        "## CONCLUSIONS",
        "Text.",
    )


def test_wrapped_all_caps_title_tail_is_merged_into_its_heading() -> None:
    text = body(
        "INTRODUCTION",
        "Text.",
        "**MEASURING METHOD**",
        "**FOR THE PROTOTYPE**",
        "Text.",
        "CONCLUSIONS",
        "Text.",
    )
    assert clean_text(text) == body(
        "## INTRODUCTION",
        "Text.",
        "## MEASURING METHOD FOR THE PROTOTYPE",
        "Text.",
        "## CONCLUSIONS",
        "Text.",
    )


def test_all_caps_recovery_is_off_when_the_body_has_a_heading() -> None:
    text = "# Preface\n\n" + _CAPS_TEXT
    assert clean_text(text) == text


def test_numbered_ladder_wins_over_the_caps_seed() -> None:
    tail = body("APPENDIX A", "Text.", "APPENDIX B")
    assert clean_text(_UNSTYLED_TEXT + "\n" + tail) == (
        _UNSTYLED_RECOVERED + "\n" + tail
    )


# ---- a heading's tail split into its own paragraph -----------------------------


def test_heading_tail_paragraph_is_joined_to_the_heading_above() -> None:
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha**",
        "**and its limits**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
        "Text.",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "Text.",
        "## 2.1 Alpha and its limits",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
        "Text.",
    )


def test_heading_tail_merge_is_stable_on_a_second_clean() -> None:
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha**",
        "**and its limits**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
        "Text.",
    )
    once = clean_full_text(text)
    assert clean_full_text(once) == once


def test_paragraph_after_ordinary_text_is_not_joined_to_a_heading() -> None:
    text = _UNSTYLED_TEXT + "\n**and its limits**\n"
    assert clean_text(text) == _UNSTYLED_RECOVERED + "\n**and its limits**\n"


def test_uppercase_tail_after_a_non_heading_line_is_not_joined() -> None:
    # The line above a caps tail has to be a heading, not caps text.
    text = body(
        "**INTRO**",
        "Text.",
        "**SUMMARY:**",
        "**DETAILS**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "Text.",
        "**SUMMARY:**",
        "**DETAILS**",
        "Text.",
        "## 2.1 Alpha",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
    )


def test_heading_absorbs_at_most_one_tail_paragraph() -> None:
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha**",
        "**and beta**",
        "**and gamma**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
        "Text.",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "Text.",
        "## 2.1 Alpha and beta",
        "**and gamma**",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
        "Text.",
    )


def test_tail_after_an_unnumbered_heading_is_not_joined() -> None:
    # An unnumbered heading is where a bold remark is plausible.
    text = body(
        "**INTRO**",
        "**and its limits**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "**and its limits**",
        "Text.",
        "## 2.1 Alpha",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
    )


# ---- a paragraph a split run or a hard break tore apart ------------------------


def test_split_bold_run_is_stitched_into_one_heading() -> None:
    # The space between the runs stays: a mid-word split cannot be told apart.
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha**",
        "Text.",
        "**2.1.1 O** **ne**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
        "Text.",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "Text.",
        "## 2.1 Alpha",
        "Text.",
        "### 2.1.1 O ne",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
        "Text.",
    )


def test_hard_break_inside_wrapped_heading_is_seen_as_one_paragraph() -> None:
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha\\\nand Omega**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
        "Text.",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "Text.",
        "## 2.1 Alpha and Omega",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
        "Text.",
    )


def test_hard_break_heading_merge_is_stable_on_a_second_clean() -> None:
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha\\\nand Omega**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
        "Text.",
    )
    once = clean_full_text(text)
    assert clean_full_text(once) == once


def test_hard_break_tail_paragraph_is_still_joined_to_its_heading() -> None:
    text = body(
        "**INTRO**",
        "Text.",
        "**2.1 Alpha**",
        "**and\\\nits limits**",
        "Text.",
        "**2.1.1 One**",
        "Text.",
        "**2.1.2 Two**",
        "Text.",
        "**2.1.3 Three**",
        "Text.",
    )
    assert clean_text(text) == body(
        "# INTRO",
        "Text.",
        "## 2.1 Alpha and its limits",
        "Text.",
        "### 2.1.1 One",
        "Text.",
        "### 2.1.2 Two",
        "Text.",
        "### 2.1.3 Three",
        "Text.",
    )


# ---- a protected zone as a paragraph boundary for recovery ---------------------


def test_bold_heading_directly_under_front_matter_is_recovered() -> None:
    # No blank line after the closing `---`: the protected line is a boundary.
    text = "---\nraw2md_version: 0.1.0\n---\n" + _UNSTYLED_TEXT
    assert clean_text(text) == (
        "---\nraw2md_version: 0.1.0\n---\n" + _UNSTYLED_RECOVERED
    )


def test_caps_heading_directly_under_front_matter_is_recovered() -> None:
    text = "---\nraw2md_version: 0.1.0\n---\n" + _CAPS_TEXT
    assert clean_text(text) == ("---\nraw2md_version: 0.1.0\n---\n" + _CAPS_RECOVERED)


def test_caps_heading_directly_before_a_fence_is_recovered() -> None:
    text = (
        "INTRODUCTION\n\nText.\n\nMETHOD OF MEASUREMENT\n\nText.\n\n"
        "CONCLUSIONS\n```\ncode\n```\n"
    )
    assert clean_text(text) == (
        "## INTRODUCTION\n\nText.\n\n## METHOD OF MEASUREMENT\n\nText.\n\n"
        "## CONCLUSIONS\n```\ncode\n```\n"
    )


def test_caps_heading_directly_before_an_html_table_is_recovered() -> None:
    text = (
        "INTRODUCTION\n\nText.\n\nMETHOD OF MEASUREMENT\n\nText.\n\n"
        "CONCLUSIONS\n<table>\n<tr><td>x</td></tr>\n</table>\n"
    )
    assert clean_text(text) == (
        "## INTRODUCTION\n\nText.\n\n## METHOD OF MEASUREMENT\n\nText.\n\n"
        "## CONCLUSIONS\n<table>\n<tr><td>x</td></tr>\n</table>\n"
    )


# ---- the route a body came from ------------------------------------------------


def test_recovery_is_off_on_the_marker_route() -> None:
    # On a recognized page an all-caps line may be a running head or OCR debris.
    options = CleanOptions(method=ConversionMethod.MARKER)
    assert clean_in_place(_CAPS_TEXT, options) == _CAPS_TEXT
    assert clean_in_place(_UNSTYLED_TEXT, options) == _UNSTYLED_TEXT


def test_recovery_is_off_on_the_djvu_route() -> None:
    options = CleanOptions(method=ConversionMethod.DJVU_MARKER)
    assert clean_in_place(_CAPS_TEXT, options) == _CAPS_TEXT


def test_recovery_is_off_when_the_route_is_unknown() -> None:
    assert clean_in_place(_CAPS_TEXT) == _CAPS_TEXT
    assert clean_in_place(_UNSTYLED_TEXT) == _UNSTYLED_TEXT


def test_recovery_is_on_for_the_clean_route() -> None:
    options = CleanOptions(method=ConversionMethod.CLEAN)
    assert clean_in_place(_CAPS_TEXT, options) == _CAPS_RECOVERED


def test_route_does_not_gate_the_other_cleaning_rules() -> None:
    options = CleanOptions(method=ConversionMethod.MARKER)
    assert clean_in_place("##Text\n", options) == "## Text\n"
