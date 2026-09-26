"""Tests for the heading rules that read one heading's own line.

The missing space after a marker, emphasis around the whole title, a running
header restated page after page, and a heading run into its paragraph.
"""

from __future__ import annotations

from dataclasses import replace

from raw2md.cleaner import CleanOptions, clean, clean_in_place
from raw2md.keywords import default_keywords
from raw2md.source_text import tokenize

from ._helpers import reported

# ---- heading space -----------------------------------------------------------


def test_adds_space_after_heading_marker() -> None:
    assert clean_in_place("##Text\n") == "## Text\n"


def test_fixes_every_heading_level() -> None:
    text = "#A\n##B\n###C\n####D\n#####E\n######F\n"
    assert clean_in_place(text) == "# A\n## B\n### C\n#### D\n##### E\n###### F\n"


def test_leaves_already_spaced_heading() -> None:
    assert clean_in_place("## Text\n") == "## Text\n"


def test_leaves_lone_hash() -> None:
    assert clean_in_place("#\n") == "#\n"


def test_leaves_seven_hashes_alone() -> None:
    assert clean_in_place("#######Text\n") == "#######Text\n"


# ---- heading emphasis ----------------------------------------------------------


def test_strips_bold_wrapping_whole_heading_text() -> None:
    assert clean_in_place("## **1.2. Classification**\n") == "## 1.2. Classification\n"


def test_strips_underscore_emphasis_wrapping_whole_heading() -> None:
    assert clean_in_place("## __1.2 Foo__\n") == "## 1.2 Foo\n"


def test_strips_emphasis_from_word_heading_without_number() -> None:
    assert clean_in_place("## **Chapter 6**\n") == "## Chapter 6\n"


def test_partial_emphasis_inside_heading_is_untouched() -> None:
    text = "## Foo **bar** baz\n"
    assert clean_in_place(text) == text


def test_emphasis_run_at_start_only_is_untouched() -> None:
    text = "## **Foo** rest\n"
    assert clean_in_place(text) == text


def test_two_separate_emphasis_runs_in_heading_are_untouched() -> None:
    text = "## **A** and **B**\n"
    assert clean_in_place(text) == text


def test_heading_emphasis_in_code_fence_is_not_stripped() -> None:
    text = "```\n## **1.2 Foo**\n```\n"
    assert clean_in_place(text) == text


def test_heading_emphasis_strip_runs_before_heading_numbering() -> None:
    # marker wraps some numbered headings in bold, hiding the number.
    text = "## **1.2. A**\n### 1.3 B\n"
    assert clean_in_place(text) == "## 1.2. A\n## 1.3 B\n"


def test_heading_emphasis_strip_is_idempotent() -> None:
    text = "## **1.2 Foo**\n### 1.3 Bar\n"
    once = clean(text)
    assert clean(once) == once


def test_strips_single_asterisk_wrapping_whole_heading_text() -> None:
    assert clean_in_place("## *7.3.4.2 Foo*\n") == "## 7.3.4.2 Foo\n"


def test_strips_single_underscore_wrapping_whole_heading_text() -> None:
    assert clean_in_place("## _1.2 Foo_\n") == "## 1.2 Foo\n"


def test_single_asterisk_strip_keeps_the_title_text_verbatim() -> None:
    assert (
        clean_in_place("## *1.2. Classification of systems*\n")
        == "## 1.2. Classification of systems\n"
    )


def test_single_asterisk_heading_wrap_strip_runs_before_heading_numbering() -> None:
    text = "## *1.2. A*\n### 1.3 B\n"
    assert clean_in_place(text) == "## 1.2. A\n## 1.3 B\n"


def test_partial_single_asterisk_emphasis_inside_heading_is_untouched() -> None:
    text = "## Foo *bar* baz\n"
    assert clean_in_place(text) == text


def test_two_separate_single_asterisk_runs_in_heading_are_untouched() -> None:
    text = "## *A* and *B*\n"
    assert clean_in_place(text) == text


# ---- heading leading glyph --------------------------------------------------


def test_strips_leading_bullet_before_heading_number() -> None:
    assert clean_in_place("# • 1. Introduction\n") == "# 1. Introduction\n"


def test_strips_leading_pictogram_before_heading_number() -> None:
    assert clean_in_place("# 🗣 24. References\n") == "# 24. References\n"


def test_bullet_before_heading_number_lets_it_join_the_ladder() -> None:
    text = "## • 1.2 A\n### 1.3 B\n"
    assert clean_in_place(text) == "## 1.2 A\n## 1.3 B\n"


def test_pictogram_before_heading_number_lets_it_join_the_ladder() -> None:
    text = "## 🗣 1.2 A\n### 1.3 B\n"
    assert clean_in_place(text) == "## 1.2 A\n## 1.3 B\n"


def test_section_mark_before_heading_number_is_untouched() -> None:
    text = "# § 5\n"
    assert clean_in_place(text) == text


def test_number_mark_before_heading_number_is_untouched() -> None:
    text = "# № 5\n"
    assert clean_in_place(text) == text


def test_measure_mark_before_heading_number_is_untouched() -> None:
    text = "# ⌀ 20 mm\n# ℃ 100 point\n"
    assert clean_in_place(text) == text


def test_partial_emphasis_before_heading_number_is_untouched() -> None:
    text = "# *Lesson* 5\n"
    assert clean_in_place(text) == text


def test_leading_glyph_without_a_number_is_not_stripped() -> None:
    text = "# • Introduction\n"
    assert clean_in_place(text) == text


def test_math_span_opening_a_heading_is_untouched() -> None:
    text = "# $1 + x$ approximation\n"
    assert clean_in_place(text) == text


def test_link_opening_a_heading_is_untouched() -> None:
    text = "# [3D printing](https://example.org)\n"
    assert clean_in_place(text) == text


def test_sign_of_a_heading_number_is_untouched() -> None:
    text = "# -20 C operation\n"
    assert clean_in_place(text) == text


def test_bracket_around_a_heading_number_is_untouched() -> None:
    text = '# (1) Foo\n# "3D" rules\n'
    assert clean_in_place(text) == text


# ---- letter-spaced title ---------------------------------------------------

# The body spells both words of the spaced title whole.
_TITLE_WITNESS = "The volumes of gas matter here.\n"


def test_letter_spaced_title_is_rebuilt_into_the_words_the_body_spells() -> None:
    # Recognition groups a spaced title irregularly.
    text = _TITLE_WITNESS + "\n## V OL UM ES G AS\n"
    assert clean_in_place(text) == _TITLE_WITNESS + "\n## VOLUMES GAS\n"


def test_a_title_of_ordinary_words_is_not_rebuilt() -> None:
    text = _TITLE_WITNESS + "\n## VOLUMES OF GAS\n"
    assert clean_in_place(text) == text


def test_a_spaced_title_the_body_attests_nothing_of_is_left_alone() -> None:
    text = "\n## V OL UM ES G AS\n"
    assert clean_in_place(text) == "## V OL UM ES G AS\n"


def test_a_spaced_title_two_readings_cover_equally_is_left_alone() -> None:
    text = "The ab and bc tokens matter.\n\n## A B C\n"
    assert clean_in_place(text) == text


def test_a_spaced_run_inside_an_ordinary_title_is_left_to_the_title_rule() -> None:
    witness = "The ident token matters here.\nThe ident token again.\n"
    text = witness + "\n## Some rather long words and i d e n t values\n"
    assert clean_in_place(text) == text


def test_letter_spaced_title_rebuild_is_idempotent() -> None:
    text = _TITLE_WITNESS + "\n## V OL UM ES G AS\n"
    once = clean(text)
    assert clean(once) == once


# ---- an oversize heading -------------------------------------------------------

_OVERSIZE_TITLE = (
    "Detailed description of the assembly procedure, its tolerances, the fixture "
    "it needs, the torque each fastener takes, and every inspection the finished "
    "part must pass before it can leave the cell for the next station on the line"
)


def test_an_oversize_heading_loses_its_marker() -> None:
    assert len(_OVERSIZE_TITLE) > 200
    assert clean_in_place(f"### {_OVERSIZE_TITLE}\n") == f"{_OVERSIZE_TITLE}\n"


def test_a_title_at_the_length_ceiling_keeps_its_marker() -> None:
    title = "T" + "i" * 199  # exactly 200 characters
    assert clean_in_place(f"## {title}\n") == f"## {title}\n"


def test_a_title_of_199_characters_is_untouched() -> None:
    title = "T" + "i" * 198  # one short of the ceiling
    assert clean_in_place(f"## {title}\n") == f"## {title}\n"


def test_an_oversize_heading_keeps_its_title_byte_for_byte() -> None:
    title = f"6.1.3 {_OVERSIZE_TITLE}"
    assert clean_in_place(f"#### {title}\n") == f"{title}\n"


def test_a_marker_left_inside_an_oversize_title_is_stripped_too() -> None:
    text = f"## # {_OVERSIZE_TITLE}\n"
    once = clean_in_place(text)
    assert once == f"{_OVERSIZE_TITLE}\n"
    assert clean_in_place(once) == once


def test_the_oversize_heading_strip_skips_a_code_fence() -> None:
    text = f"Intro.\n\n```\n## {_OVERSIZE_TITLE}\n```\n"
    assert clean_in_place(text) == text


# ---- a crushed form's caption ----------------------------------------------------


def test_a_crushed_form_splits_from_its_bold_caption() -> None:
    text = f"# **A specimen certificate** {_OVERSIZE_TITLE}\n"
    assert clean_in_place(text) == (
        f"**A specimen certificate**\n\n{_OVERSIZE_TITLE}\n"
    )


def test_a_crushed_form_split_is_idempotent() -> None:
    text = f"# **A specimen certificate** {_OVERSIZE_TITLE}\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_a_full_line_wrap_on_an_oversize_heading_is_not_split() -> None:
    text = f"### **{_OVERSIZE_TITLE}**\n"
    assert clean_in_place(text) == f"{_OVERSIZE_TITLE}\n"


# ---- running-header heading dedup -----------------------------------------------


def test_repeated_numbered_heading_is_dropped_after_the_first() -> None:
    text = (
        "### 3.1 General provisions\n\n"
        "Text on page one.\n\n"
        "### 3.1 General provisions\n\n"
        "Text on page two.\n"
    )
    assert clean_in_place(text) == (
        "### 3.1 General provisions\n\nText on page one.\n\nText on page two.\n"
    )


def test_many_repeats_all_collapse_to_the_first() -> None:
    text = "## 7 Applications\nA\n\n## 7 Applications\nB\n\n## 7 Applications\nC\n"
    assert clean_in_place(text) == "## 7 Applications\nA\n\nB\n\nC\n"


def test_a_copy_that_drops_its_number_is_the_same_running_header() -> None:
    # Byte-for-byte matching would let the copy without the number close the slot.
    text = (
        "### 3.1 General provisions\n\n"
        "Text on page one.\n\n"
        "### General provisions\n\n"
        "Text on page two.\n\n"
        "### 3.1 General provisions\n\n"
        "Text on page three.\n"
    )
    assert clean_in_place(text) == (
        "### 3.1 General provisions\n\n"
        "Text on page one.\n\nText on page two.\n\nText on page three.\n"
    )


def test_a_copy_set_in_another_case_is_the_same_running_header() -> None:
    text = "### 3.1 General provisions\n\nA\n\n### 3.1  GENERAL PROVISIONS\n\nB\n"
    assert clean_in_place(text) == "### 3.1 General provisions\n\nA\n\nB\n"


def test_a_copy_that_lost_a_diacritic_is_the_same_running_header() -> None:
    text = "## 2 Écoulement des fluides\n\nA\n\n## 2 Ecoulement des fluides\n\nB\n"
    assert clean_in_place(text) == "## 2 Écoulement des fluides\n\nA\n\nB\n"


def test_a_sibling_of_another_number_keeps_its_heading() -> None:
    text = "### 3.1 Calculations\n\nA\n\n### 3.2 Calculations\n\nB\n"
    assert clean_in_place(text) == text


def test_a_number_the_open_section_never_carried_opens_its_own_section() -> None:
    # A slot adopting the number of a dropped copy would break the fixed point.
    text = "## Overview\n\nA\n\n## 3.1 Overview\n\nB\n\n## 3.2 Overview\n\nC\n"
    once = clean(text)
    assert once == text
    assert clean(once) == once


def test_unnumbered_running_header_repeat_is_untouched() -> None:
    text = "## Review questions\n\nA\n\n## Review questions\n\nB\n"
    assert clean_in_place(text) == text


def test_two_line_running_header_drops_its_numbered_half() -> None:
    # The unnumbered line must not close the slot of its numbered line.
    text = (
        "### Overview\n\n#### 2.1 Foo\n\nA\n\n"
        "### Overview\n\n#### 2.1 Foo\n\nB\n\n"
        "### Overview\n\n#### 2.1 Foo\n\nC\n"
    )
    assert clean_in_place(text) == (
        "### Overview\n\n#### 2.1 Foo\n\nA\n\n### Overview\n\nB\n\n### Overview\n\nC\n"
    )


def test_a_different_unnumbered_heading_still_closes_the_slot_below_it() -> None:
    text = (
        "## Part A\n\n### 1 Definitions\n\nA\n\n## Part B\n\n### 1 Definitions\n\nB\n"
    )
    assert clean_in_place(text) == text


def test_a_section_repeated_per_part_keeps_its_restarted_numbering() -> None:
    text = (
        "# Lecture 1\n\n## Questions\n\n### 1 Definition\n\nA\n\n"
        "# Lecture 2\n\n## Questions\n\n### 1 Definition\n\nB\n"
    )
    assert clean_in_place(text) == text


def test_repeat_at_a_different_level_is_dropped_once_the_levels_settle() -> None:
    # The drop runs again after the numbering pass settles the levels.
    text = "### 3.1 General provisions\n\nA\n\n#### 3.1 General provisions\n\nB\n"
    assert clean_in_place(text) == "### 3.1 General provisions\n\nA\n\nB\n"


def test_a_restarted_number_survives_the_settle_at_any_level() -> None:
    text = (
        "## Schedule 1\n\n### 1 Definitions\n\nA\n\n"
        "## Schedule 2\n\n#### 1 Definitions\n\nB\n"
    )
    assert clean_in_place(text) == (
        "## Schedule 1\n\n### 1 Definitions\n\nA\n\n"
        "## Schedule 2\n\n### 1 Definitions\n\nB\n"
    )


def test_single_numbered_heading_has_no_duplicate_to_drop() -> None:
    text = "### 7.2.1 Lonely\n"
    assert clean_in_place(text) == text


def test_two_levels_of_running_header_dedup_independently() -> None:
    text = (
        "### 3.1 Section\nA\n#### 3.1.1 Sub\nA1\n"
        "### 3.1 Section\nB\n#### 3.1.1 Sub\nB1\n"
        "### 3.1 Section\nC\n"
    )
    assert clean_in_place(text) == (
        "### 3.1 Section\nA\n#### 3.1.1 Sub\nA1\nB\nB1\nC\n"
    )


def test_numbering_restarted_in_a_new_part_is_not_merged_into_the_first() -> None:
    text = (
        "## Schedule 1\n\n### 1 Definitions\n\nA\n\n"
        "## Schedule 2\n\n### 1 Definitions\n\nB\n"
    )
    assert clean_in_place(text) == text


def test_running_header_matches_a_run_in_first_occurrence_after_its_split() -> None:
    # The first occurrence was a run-in heading; the drop compares the split title.
    text = (
        "#### 3.1 Test Arrangements. The original fixture holds a rod.\n\n"
        "#### 3.1 Test Arrangements\n\n"
        "More text on page two.\n"
    )
    assert clean_in_place(text) == (
        "#### 3.1 Test Arrangements\n\n"
        "The original fixture holds a rod.\n\n"
        "More text on page two.\n"
    )


def test_running_header_in_a_code_fence_does_not_count_as_a_heading() -> None:
    text = "### 3.1 Foo\n\n```\n### 3.1 Foo\n```\n\n### 3.1 Foo\n"
    assert clean_in_place(text) == "### 3.1 Foo\n\n```\n### 3.1 Foo\n```\n"


def test_running_header_dedup_is_idempotent() -> None:
    text = "### 3.1 Foo\n\nA\n\n### 3.1 Foo\n\nB\n"
    once = clean(text)
    assert clean(once) == once


# ---- run-in heading split ------------------------------------------------------


def test_run_in_heading_is_split_from_its_paragraph() -> None:
    text = (
        "#### 3.1 Test Arrangements. The original Harlow's fixture "
        "holds an infinitely long rod.\n"
    )
    expected = (
        "#### 3.1 Test Arrangements\n\n"
        "The original Harlow's fixture holds an infinitely long "
        "rod.\n"
    )
    assert clean_in_place(text) == expected


def test_run_in_split_preserves_word_tokens() -> None:
    text = (
        "#### 3.1 Test Arrangements. The original Harlow's fixture "
        "holds an infinitely long rod.\n"
    )
    before = tokenize(text.removeprefix("#### "))
    after = clean_in_place(text)
    heading, _, paragraph = after.strip("\n").split("\n", 2)
    combined = tokenize(heading.removeprefix("#### ")) + tokenize(paragraph)
    assert sorted(combined) == sorted(before)


def test_genuine_long_heading_is_not_split() -> None:
    text = "#### 3.1 A Comprehensive Overview Of The Experimental Setup And Method\n"
    assert clean_in_place(text) == text


def test_short_heading_without_a_period_is_not_split() -> None:
    text = "#### 3.1 Test Arrangements\n"
    assert clean_in_place(text) == text


def test_abbreviation_before_a_title_case_tail_is_not_split() -> None:
    text = "#### 3.1 Mr. Smith's Approach To The Problem\n"
    assert clean_in_place(text) == text


def test_abbreviation_before_the_real_title_break_is_not_split() -> None:
    text = "#### 3.1 Dr. Smith Method. This method is important.\n"
    assert clean_in_place(text) == text


def test_run_in_split_is_off_in_a_code_fence() -> None:
    text = "```\n#### 3.1 Test Arrangements. The original fixture.\n```\n"
    assert clean_in_place(text) == text


def test_run_in_split_is_idempotent() -> None:
    text = (
        "#### 3.1 Test Arrangements. The original Harlow's fixture "
        "holds an infinitely long rod.\n"
    )
    once = clean(text)
    assert clean(once) == once


# ---- anchoring: run-in heading with a minor word in the title --------------


def test_run_in_heading_with_a_minor_word_is_reported() -> None:
    text = (
        "#### 3.1 Tooling for Rapid Assembly. The next section "
        "describes it in detail.\n"
    )
    assert clean(text) == text
    assert reported(text) == "run-in-heading"


def test_the_minor_words_of_a_title_come_from_the_dictionary() -> None:
    options = CleanOptions(
        keywords=replace(default_keywords(), heading_minor_words=("for",))
    )
    stated = (
        "#### 3.1 Tooling for Rapid Assembly. The next section "
        "describes it in detail.\n"
    )
    assert reported(stated, options) == "run-in-heading"
    dropped = (
        "#### 3.1 Tooling and Rapid Assembly. The next section "
        "describes it in detail.\n"
    )
    assert reported(dropped, options) == ""


def test_run_in_heading_without_an_embedded_sentence_is_not_reported() -> None:
    text = "#### 3.1 Tooling for Rapid Assembly\n"
    assert clean(text) == text


def test_run_in_heading_loose_title_too_long_is_not_anchored() -> None:
    text = (
        "#### 3.1 A Primer on the Tooling and Assembly of Parts for "
        "Rapid Processes and Other Related Topics in the Field. The "
        "next section follows.\n"
    )
    assert clean(text) == text


def test_run_in_heading_loose_abbreviation_is_not_anchored() -> None:
    text = "#### 3.1 Guide to U.S. Assembly. The next section is long enough.\n"
    assert clean(text) == text


def test_run_in_heading_loose_tail_not_prose_is_not_anchored() -> None:
    text = "#### 3.1 Guide to Design. A Method For Rapid Assembly Systems\n"
    assert clean(text) == text


def test_run_in_heading_loose_split_is_off_in_a_code_fence() -> None:
    text = "```\n#### 3.1 Tooling for Rapid Assembly. The next section follows.\n```\n"
    assert clean(text) == text


def test_run_in_heading_loose_is_idempotent() -> None:
    text = (
        "#### 3.1 Tooling for Rapid Assembly. The next section "
        "describes it in detail.\n"
    )
    once = clean(text)
    assert clean(once) == once
