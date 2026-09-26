"""Tests for the heading rules that settle a level from the whole document.

The rules read the ladder: the numbering depth, the source outline, the nesting
of unnumbered headings, the printed contents, and the gaps the settled levels
leave.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from raw2md.cleaner import CleanOptions, clean, clean_in_place
from raw2md.cleaning import printed_outline
from raw2md.cleaning.headings import close_section_level_gaps, detect_oversize_headings
from raw2md.keywords import default_keywords
from raw2md.mdtext.zones import segments
from raw2md.source_outline import SourceOutline

from ._helpers import (
    laid_out_table,
    outlined,
    reported,
)

KEYWORDS = default_keywords()

# ---- heading numbering consistency -------------------------------------------


def test_aligns_same_depth_headings_to_shared_level() -> None:
    assert clean_in_place("## 4.1.3 Foo\n### 4.1.4 Bar\n") == (
        "## 4.1.3 Foo\n## 4.1.4 Bar\n"
    )


def test_majority_level_wins_for_a_depth() -> None:
    text = "### 1.1 A\n### 1.2 B\n### 1.3 C\n## 1.4 D\n"
    assert clean_in_place(text) == "### 1.1 A\n### 1.2 B\n### 1.3 C\n### 1.4 D\n"


def test_only_hash_count_changes_not_number_or_title() -> None:
    assert clean_in_place("# 2.1 Intro\n## 2.2 Setup\n") == (
        "# 2.1 Intro\n# 2.2 Setup\n"
    )


def test_single_numbered_heading_is_left_alone() -> None:
    assert clean_in_place("### 7.2.1 Lonely\n") == "### 7.2.1 Lonely\n"


def test_different_depths_keep_their_levels() -> None:
    text = "# 1 Top\n## 1.1 Sub\n## 1.2 Sub\n"
    assert clean_in_place(text) == text


def test_deeper_number_gets_a_deeper_level() -> None:
    text = "### 1.1 A\n### 1.2 B\n## 1.1.1 C\n## 1.1.2 D\n"
    assert clean_in_place(text) == "### 1.1 A\n### 1.2 B\n#### 1.1.1 C\n#### 1.1.2 D\n"


def test_subsections_sit_one_level_below_their_parent() -> None:
    text = "# 5 Mounting\n\n# 5.1 Mounting\n\n# 5.2 Removal\n"
    assert clean_in_place(text) == "# 5 Mounting\n\n## 5.1 Mounting\n\n## 5.2 Removal\n"


def test_deep_numbering_keeps_one_level_per_depth() -> None:
    # `###` for the top depth would push depth 6 past `######`.
    text = (
        "### 1.1 A\n"
        "### 1.2 B\n"
        "### 1.1.1 C\n"
        "### 1.1.1.1 D\n"
        "### 1.1.1.1.1 E\n"
        "### 1.1.1.1.1.1 F\n"
    )
    assert clean_in_place(text) == (
        "## 1.1 A\n"
        "## 1.2 B\n"
        "### 1.1.1 C\n"
        "#### 1.1.1.1 D\n"
        "##### 1.1.1.1.1 E\n"
        "###### 1.1.1.1.1.1 F\n"
    )


def test_unnumbered_headings_are_untouched() -> None:
    text = "## 3.1 Numbered\n### Plain Heading\n## 3.2 Numbered\n"
    assert clean_in_place(text) == text


def test_numbering_in_code_fence_is_not_normalized() -> None:
    text = "## 5.1 A\n```\n#### 5.2 still code\n```\n## 5.3 B\n"
    assert clean_in_place(text) == text


def test_trailing_dot_number_counts_by_components() -> None:
    assert clean_in_place("## 4.1. A\n### 4.2 B\n") == "## 4.1. A\n## 4.2 B\n"


def test_the_shallowest_dotted_depth_sets_the_levels_under_it() -> None:
    # A converter crushes deep headings onto one marker, so the deep majority is weak.
    text = (
        "## 3.1 Alpha\n\n"
        "#### 3.1.1 One\n\n"
        "#### 3.1.2 Two\n\n"
        "#### 3.1.3 Three\n\n"
        "#### 3.1.4 Four\n\n"
        "## 3.2 Beta\n\n"
        "## 3.3 Gamma\n"
    )

    assert clean_in_place(text) == (
        "## 3.1 Alpha\n\n"
        "### 3.1.1 One\n\n"
        "### 3.1.2 Two\n\n"
        "### 3.1.3 Three\n\n"
        "### 3.1.4 Four\n\n"
        "## 3.2 Beta\n\n"
        "## 3.3 Gamma\n"
    )


def test_a_lone_dotted_heading_does_not_anchor_the_ladder() -> None:
    text = "## 3.1 Alpha\n\n#### 3.1.1 One\n\n#### 3.1.2 Two\n\n#### 3.1.3 Three\n"

    assert clean_in_place(text) == (
        "### 3.1 Alpha\n\n#### 3.1.1 One\n\n#### 3.1.2 Two\n\n#### 3.1.3 Three\n"
    )


def test_a_catalogue_number_does_not_set_a_heading_level() -> None:
    # Running-head page numbers, part codes and figure references name no section.
    text = (
        "### 22 Drive Components\n\n"
        "### 23 Drive Components\n\n"
        "### 24 Drive Components\n\n"
        "#### 4-138 Bushing\n\n"
        "#### Fig. 5.4 Slot\n"
    )

    assert clean_in_place(text) == text


# ---- heading levels from the source outline ------------------------------------


def test_heading_takes_its_level_from_the_outline() -> None:
    text = "# Alpha\n\n### Beta\n"
    options = outlined((1, "Alpha"), (2, "Beta"))

    assert clean_in_place(text, options) == "# Alpha\n\n## Beta\n"


def test_a_heading_the_outline_does_not_state_is_left_alone() -> None:
    text = "# Alpha\n\n## Beta\n"

    assert clean_in_place(text, outlined((1, "Alpha"))) == text


def test_without_an_outline_levels_are_what_they_were() -> None:
    text = "# Alpha\n\n## Beta\n"

    assert clean_in_place(text) == clean_in_place(text, CleanOptions())
    assert clean_in_place(text) == text


def test_outline_level_deeper_than_atx_lands_on_the_last_level() -> None:
    # The neighbour keeps the ladder dense, so gap closing does not undo the clamp.
    text = "## Deep\n\n## Other\n"
    options = outlined((8, "Deep"), (5, "Other"))

    assert clean_in_place(text, options) == "###### Deep\n\n##### Other\n"


def test_numbering_does_not_override_a_level_the_outline_stated() -> None:
    text = "## 1 Alpha\n\n## 1.1 Beta\n\n## 1.2 Gamma\n"
    options = outlined((1, "1.2 Gamma"))

    assert clean_in_place(text, options) == (
        "# 1 Alpha\n\n## 1.1 Beta\n\n# 1.2 Gamma\n"
    )


def test_a_stated_level_pulls_the_rest_of_its_depth_along() -> None:
    # Without the outline the majority `###` would anchor the map.
    text = "## 1 Alpha\n\n### 1.1 Beta\n\n### 1.2 Gamma\n"
    options = outlined((1, "1 Alpha"))

    assert clean_in_place(text) == text
    assert clean_in_place(text, options) == (
        "# 1 Alpha\n\n## 1.1 Beta\n\n## 1.2 Gamma\n"
    )


def test_a_dense_outline_outranks_the_numbering_anchor() -> None:
    text = (
        "## 3.1 Alpha\n\n"
        "#### 3.1.1 One\n\n"
        "#### 3.1.2 Two\n\n"
        "#### 3.1.3 Three\n\n"
        "## 3.2 Beta\n\n"
        "## 3.3 Gamma\n"
    )
    options = outlined(
        (1, "3.1 Alpha"),
        (2, "3.1.1 One"),
        (2, "3.1.2 Two"),
        (2, "3.1.3 Three"),
        (1, "3.2 Beta"),
        (1, "3.3 Gamma"),
    )

    assert clean_in_place(text, options) == (
        "# 3.1 Alpha\n\n"
        "## 3.1.1 One\n\n"
        "## 3.1.2 Two\n\n"
        "## 3.1.3 Three\n\n"
        "# 3.2 Beta\n\n"
        "# 3.3 Gamma\n"
    )


def test_a_contents_line_matching_the_outline_stays_prose() -> None:
    text = "# Contents\n\nIntroduction\n\n## Introduction\n\nBody text.\n"
    options = outlined((1, "Contents"), (1, "Introduction"))

    assert clean_in_place(text, options) == (
        "# Contents\n\nIntroduction\n\n# Introduction\n\nBody text.\n"
    )


def test_outline_does_not_reach_into_a_code_fence() -> None:
    text = "# Alpha\n\n```\n### Alpha\n```\n"

    assert clean_in_place(text, outlined((1, "Alpha"))) == text


def test_outline_levelling_is_idempotent() -> None:
    text = "# 1 Alpha\n\n### 1.1 Beta\n\n#### Gamma\n"
    options = outlined((1, "1 Alpha"), (2, "1.1 Beta"), (2, "Gamma"))

    once = clean(text, options)
    assert clean(once, options) == once


# ---- the outline read as the document's skeleton --------------------------------


def _catalog_outline() -> CleanOptions:
    """An outline whose chapter and part the body never prints as headings."""
    return outlined(
        (1, "Handbook"),
        (2, "Products"),
        (3, "Pumps"),
        (3, "Valves"),
        (3, "Filters"),
    )


def test_the_printed_part_of_the_outline_ladder_is_lifted_to_the_top() -> None:
    # The outline has an unprinted chapter and part above the printed sections.
    text = "# Pumps\n\n# Advantages\n\n# Valves\n\n# Advantages\n\n# Filters\n"

    assert clean_in_place(text, _catalog_outline()) == (
        "# Pumps\n\n## Advantages\n\n# Valves\n\n## Advantages\n\n# Filters\n"
    )


def test_the_lifted_outline_ladder_is_idempotent() -> None:
    text = "# Pumps\n\n# Advantages\n\n# Valves\n\n# Filters\n"
    options = _catalog_outline()

    once = clean(text, options)
    assert clean(once, options) == once


def test_a_heading_above_the_first_outline_section_keeps_its_level() -> None:
    text = "# Cover\n\n# Pumps\n\n# Advantages\n\n# Valves\n\n# Filters\n"

    assert clean_in_place(text, _catalog_outline()) == (
        "# Cover\n\n# Pumps\n\n## Advantages\n\n# Valves\n\n# Filters\n"
    )


def test_a_heading_too_long_to_be_a_title_loses_its_marker_before_the_outline() -> None:
    crushed = ("Prose the layout model tagged as a heading. " * 6).strip()
    text = f"# Pumps\n\n# {crushed}\n\n# Valves\n\n# Filters\n"

    assert clean_in_place(text, _catalog_outline()) == (
        f"# Pumps\n\n{crushed}\n\n# Valves\n\n# Filters\n"
    )


def test_a_dense_outline_leaves_the_levels_it_states() -> None:
    text = "# Handbook\n\n## Pumps\n\n### Impellers\n\n## Valves\n"
    options = outlined((1, "Handbook"), (2, "Pumps"), (3, "Impellers"), (2, "Valves"))

    assert clean_in_place(text, options) == text


def test_a_body_printing_little_of_the_outline_keeps_the_stated_levels() -> None:
    # Three titles of seven: too little of the outline to be the skeleton.
    text = "# Pumps\n\n#### Advantages\n\n# Valves\n\n# Filters\n"
    options = outlined(
        (3, "Pumps"),
        (3, "Valves"),
        (3, "Filters"),
        (2, "Part one"),
        (2, "Part two"),
        (2, "Part three"),
        (2, "Part four"),
    )

    assert clean_in_place(text, options) == (
        "### Pumps\n\n#### Advantages\n\n### Valves\n\n### Filters\n"
    )


def test_an_outline_of_two_titles_is_no_skeleton() -> None:
    text = "# Pumps\n\n#### Advantages\n\n# Valves\n"
    options = outlined((3, "Pumps"), (3, "Valves"))

    assert clean_in_place(text, options) == (
        "### Pumps\n\n#### Advantages\n\n### Valves\n"
    )


# ---- unnumbered heading hierarchy ----------------------------------------------


def test_unnumbered_subsection_moves_one_level_below_its_parent() -> None:
    text = "## 2.1 Wire Drawing\n## Wire drawing pros and cons\n## 2.2 Tube Drawing\n"
    assert clean_in_place(text) == (
        "## 2.1 Wire Drawing\n### Wire drawing pros and cons\n## 2.2 Tube Drawing\n"
    )


def test_unnumbered_heading_one_level_below_its_parent_is_untouched() -> None:
    text = "## 2.1 Wire Drawing\n### For small batches\n## 2.2 Tube Drawing\n"
    assert clean_in_place(text) == text


def test_unnumbered_heading_level_jump_wider_than_one_is_closed() -> None:
    text = "## 2.1 Wire Drawing\n#### For small batches\n## 2.2 Tube Drawing\n"
    assert clean_in_place(text) == (
        "## 2.1 Wire Drawing\n### For small batches\n## 2.2 Tube Drawing\n"
    )


def test_unnumbered_heading_level_jump_of_three_still_closes_to_one() -> None:
    text = "## 2.1 Wire Drawing\n###### For small batches\n## 2.2 Tube Drawing\n"
    assert clean_in_place(text) == (
        "## 2.1 Wire Drawing\n### For small batches\n## 2.2 Tube Drawing\n"
    )


def test_two_unnumbered_siblings_under_one_parent_are_untouched() -> None:
    # `### Details` is a sibling of `### Intro`, not a child.
    text = "## 1 A\n### Intro\n### Details\n"
    assert clean_in_place(text) == text


def test_repeated_level_jump_siblings_are_all_closed_the_same_way() -> None:
    # After `First` is closed, `Second` is still measured against `2.1`.
    text = "## 2.1 A\n#### First\n#### Second\n"
    assert clean_in_place(text) == "## 2.1 A\n### First\n### Second\n"


def test_unnumbered_grandchild_is_measured_against_its_own_parent() -> None:
    text = "## 1 A\n### Methods\n#### Setup\n"
    assert clean_in_place(text) == text


def test_numbered_heading_level_jump_from_its_own_numbering_is_untouched() -> None:
    # `1.2` fills the level between, so the ladder is dense.
    text = "# 1 Chapter\n\n## 1.1.1 Deep\n\n## 1.2 Section\n"
    assert clean_in_place(text) == "# 1 Chapter\n\n### 1.1.1 Deep\n\n## 1.2 Section\n"


def test_outline_stated_heading_level_jump_is_untouched() -> None:
    # `1.1.1 Delta` fills the level between, so the ladder is dense.
    text = "# 1 Alpha\n\n#### Gamma\n\n## 1.1 Beta\n\n### 1.1.1 Delta\n"
    options = outlined((1, "1 Alpha"), (4, "Gamma"))

    assert clean_in_place(text, options) == text


def test_unnumbered_heading_level_jump_fix_is_idempotent() -> None:
    text = "## 2.1 Wire Drawing\n#### For small batches\n## 2.2 Tube Drawing\n"
    once = clean(text)
    assert clean(once) == once


def test_new_unnumbered_chapter_is_not_pulled_under_the_previous_section() -> None:
    text = "## 3.4 Heat Balance\n# Pump Interaction\n## Delivered Flow\n"
    assert clean_in_place(text) == text


def test_references_heading_stays_at_the_top() -> None:
    text = "## 2.1 Setup\n## References\n"
    assert clean_in_place(text) == text


def test_qualified_references_heading_still_stays_at_the_top() -> None:
    # The references keywords need the full word.
    text = "## 2.1 Setup\n## References and notes\n"
    assert clean_in_place(text) == text


def test_appendix_heading_stays_at_the_top() -> None:
    text = "## 3.1 General notes\n## Приложение\n"
    assert clean_in_place(text) == text


def test_the_top_level_section_words_come_from_the_dictionary() -> None:
    options = CleanOptions(
        keywords=replace(KEYWORDS, top_level_sections=("conclusion",))
    )
    stated = "## 3.1 General notes\n## Conclusion\n"
    assert clean_in_place(stated, options) == stated
    dropped = "## 3.1 General notes\n## Приложение\n"
    assert clean_in_place(dropped, options) == (
        "## 3.1 General notes\n### Приложение\n"
    )


def test_reference_frame_heading_is_not_mistaken_for_a_references_list() -> None:
    text = "## 2.1 Coordinate Systems\n## Reference frame\n"
    assert clean_in_place(text) == "## 2.1 Coordinate Systems\n### Reference frame\n"


def test_application_of_force_heading_is_not_mistaken_for_an_appendix() -> None:
    text = "## 2.1 Setup\n## Приложение силы\n"
    assert clean_in_place(text) == "## 2.1 Setup\n### Приложение силы\n"


def test_unnumbered_heading_fix_does_not_reach_into_a_code_fence() -> None:
    text = "## 2.1 Setup\n```\n## Crushed inside a fence\n```\n"
    assert clean_in_place(text) == text


def test_unnumbered_heading_fix_is_idempotent() -> None:
    text = "## 2.1 Wire Drawing\n## Wire drawing pros and cons\n## 2.2 Tube Drawing\n"
    once = clean(text)
    assert clean(once) == once


def test_repeated_unanchored_heading_converges_to_the_shallowest_level() -> None:
    # One copy at each of four levels: the tie-break takes the shallowest.
    text = (
        "# MODULE 1\n"
        "## Review questions\n"
        "# MODULE 2\n"
        "### Review questions\n"
        "# MODULE 3\n"
        "#### Review questions\n"
        "# MODULE 4\n"
        "##### Review questions\n"
    )
    assert clean_in_place(text) == (
        "# MODULE 1\n"
        "## Review questions\n"
        "# MODULE 2\n"
        "## Review questions\n"
        "# MODULE 3\n"
        "## Review questions\n"
        "# MODULE 4\n"
        "## Review questions\n"
    )


def test_repeated_unanchored_heading_converges_to_its_own_majority() -> None:
    text = "# A\n## Overview\n# B\n## Overview\n# C\n#### Overview\n# D\n## Overview\n"
    assert clean_in_place(text) == (
        "# A\n## Overview\n# B\n## Overview\n# C\n## Overview\n# D\n## Overview\n"
    )


def test_anchored_heading_repeated_under_different_depth_parents_is_untouched() -> None:
    # Each copy sits at its own numbered parent's level + 1.
    text = (
        "## 3 Product A\n"
        "### Technical data\n"
        "## 10 Product B\n"
        "### Sub Variant\n"
        "#### Technical data\n"
    )
    assert clean_in_place(text) == text


def test_repeated_heading_level_fix_is_idempotent() -> None:
    text = (
        "# MODULE 1\n"
        "## Review questions\n"
        "# MODULE 2\n"
        "### Review questions\n"
        "# MODULE 3\n"
        "#### Review questions\n"
        "# MODULE 4\n"
        "##### Review questions\n"
    )
    once = clean(text)
    assert clean(once) == once


def test_repeated_heading_leveled_onto_a_settled_sibling_is_reclosed() -> None:
    # Left unresolved, the sibling-as-child shape would show only on a second clean.
    text = "#### Section 2\n#### Section 2\n#### 2 A\n## Section 2\n"
    assert clean_in_place(text) == (
        "#### Section 2\n#### Section 2\n#### 2 A\n##### Section 2\n"
    )


def test_numbered_heading_class_converges_to_the_class_mode() -> None:
    # Forty members scattered over four levels by per-page typography.
    levels = [1] * 4 + [2] * 26 + [3] * 8 + [4] * 2
    text = "".join(
        f"{'#' * level} LECTURE {number}\n\nLecture body.\n\n"
        for number, level in enumerate(levels, start=1)
    )
    cleaned = clean_in_place(text)

    assert [line for line in cleaned.splitlines() if line.startswith("#")] == [
        f"## LECTURE {number}" for number in range(1, len(levels) + 1)
    ]


def test_heading_classes_are_kept_apart_by_their_prefix() -> None:
    # The second module opens with its own section, so its sections read nested.
    text = (
        "# MODULE 1\n\n"
        "## LECTURE 1\n\nA\n\n"
        "### LECTURE 2\n\nB\n\n"
        "## LECTURE 3\n\nC\n\n"
        "# MODULE 2\n\n"
        "## Introduction\n\nG\n\n"
        "### Section 1\n\nD\n\n"
        "### Section 2\n\nE\n\n"
        "### Section 3\n\nF\n"
    )
    assert clean_in_place(text) == (
        "# MODULE 1\n\n"
        "## LECTURE 1\n\nA\n\n"
        "## LECTURE 2\n\nB\n\n"
        "## LECTURE 3\n\nC\n\n"
        "# MODULE 2\n\n"
        "## Introduction\n\nG\n\n"
        "### Section 1\n\nD\n\n"
        "### Section 2\n\nE\n\n"
        "### Section 3\n\nF\n"
    )


def test_two_headings_sharing_a_prefix_are_not_a_class() -> None:
    text = "# Table 1\n\nA\n\n## Table 2\n\nB\n"
    assert clean_in_place(text) == text


def test_one_number_repeated_is_not_a_class() -> None:
    # Titles differ past the number, so the exact-text vote is silent too.
    text = (
        "# Priority 1 - tables\n\nA\n\n"
        "### Priority 1 - formulas\n\nB\n\n"
        "## Priority 1 - headings\n\nC\n"
    )
    assert clean_in_place(text) == text


def test_exact_repeats_still_vote_when_the_class_bar_is_missed() -> None:
    text = "# Section 2\n\nA\n\n### Section 2\n\nB\n\n### Section 2\n\nC\n"
    assert clean_in_place(text) == (
        "### Section 2\n\nA\n\n### Section 2\n\nB\n\n### Section 2\n\nC\n"
    )


def test_anchored_numbered_series_settles_on_its_own_majority() -> None:
    # 91 of 129 members already carry the level of the rank.
    parts = ["# 1. Part one\n"]
    number = 1
    for depth, count in ((2, 91), (3, 33), (4, 5)):
        if depth > 2:
            parts.append(f"{'#' * (depth - 1)} Chapter {depth}\n")
        for _ in range(count):
            parts.append(f"{'#' * depth} § {number}. Topic\n")
            number += 1
    cleaned = clean_in_place("".join(parts))

    assert [line for line in cleaned.splitlines() if line.startswith("## §")] == [
        f"## § {n}. Topic" for n in range(1, 130)
    ]


def test_anchored_repeat_settles_where_its_majority_is_overwhelming() -> None:
    # 61 copies against 4 overrule the anchor of the variant heading.
    pages = [f"## {n} Product {n}\n### IMPORTANT NOTE\n" for n in range(1, 62)]
    pages += [
        f"## {n} Product {n}\n### Variant\n#### IMPORTANT NOTE\n" for n in range(62, 66)
    ]
    cleaned = clean_in_place("".join(pages))

    assert cleaned.count("### IMPORTANT NOTE") == 65
    assert "#### IMPORTANT NOTE" not in cleaned


def test_a_group_settled_heading_holds_its_own_level_for_what_nests_under_it() -> None:
    pages = [f"## {n} Product {n}\n### IMPORTANT NOTE\n" for n in range(1, 62)]
    pages += [
        f"## {n} Product {n}\n### Variant\n"
        f"#### IMPORTANT NOTE\n#### Detail {chr(3 + n)}\n"
        for n in range(62, 66)
    ]
    cleaned = clean_in_place("".join(pages))

    assert "\n### IMPORTANT NOTE\n#### Detail A\n" in cleaned


def test_an_unnumbered_repeat_split_three_against_two_takes_the_majority() -> None:
    text = "".join(
        [f"## {n} Product {n}\n### Technical data\n" for n in range(1, 4)]
        + [
            f"## {n} Product {n}\n### Variant\n#### Technical data\n"
            for n in range(4, 6)
        ]
    )
    cleaned = clean_in_place(text)

    assert [
        line for line in cleaned.splitlines() if line.endswith("Technical data")
    ] == ["### Technical data"] * 5


def test_a_numbered_repeat_split_three_against_two_is_untouched() -> None:
    text = "".join(
        [f"## {n} Product {n}\n### Section 2\n" for n in range(1, 4)]
        + [f"## {n} Product {n}\n### Variant\n#### Section 2\n" for n in range(4, 6)]
    )
    assert clean_in_place(text) == text


def test_a_repeated_plate_settles_on_one_level() -> None:
    levels = [3] * 14 + [4] * 10 + [5] * 6 + [6] * 2
    parts = []
    for n, level in enumerate(levels, start=1):
        number = ".".join([str(n), *["1"] * (level - 3)])
        parts.append(f"{'#' * (level - 1)} {number} Section {n}\n")
        parts.append(f"{'#' * level} Hint\n")
        parts.append("The passage the plate warns about.\n")
    cleaned = clean_in_place("".join(parts))

    assert [line for line in cleaned.splitlines() if line.endswith("Hint")] == [
        "### Hint"
    ] * 32


def test_an_evenly_split_plate_takes_the_deeper_level() -> None:
    text = "".join(
        [f"## {n} Product {n}\n### Hint\n" for n in range(1, 3)]
        + [f"## {n} Product {n}\n### Variant\n#### Hint\n" for n in range(3, 5)]
    )
    cleaned = clean_in_place(text)

    assert [line for line in cleaned.splitlines() if line.endswith("Hint")] == [
        "#### Hint"
    ] * 4


def test_the_repeated_plate_fix_is_idempotent() -> None:
    text = "".join(
        [f"## {n} Product {n}\n### Hint\n" for n in range(1, 4)]
        + [f"## {n} Product {n}\n### Variant\n#### Hint\n" for n in range(4, 6)]
    )
    once = clean(text)
    assert clean(once) == once


def test_a_numbered_series_settles_before_nesting_reaches_its_members() -> None:
    # 18 of 19 chapters arrived on one level, so the series settles first.
    parts = ["# 1. Part one\n"]
    for chapter in range(1, 20):
        parts.append(f"{'###' if chapter == 7 else '##'} CHAPTER {chapter}\n")
        parts.append(f"Body of chapter {chapter}.\n")
        parts.append(f"## 1.{chapter} Section one\n")
        parts.append("Body.\n")
    cleaned = clean_in_place("\n".join(parts))

    assert [line for line in cleaned.splitlines() if "CHAPTER" in line] == [
        f"## CHAPTER {chapter}" for chapter in range(1, 20)
    ]


def test_a_series_of_three_settles_no_level_before_nesting() -> None:
    parts = ["# 1. Part one\n"]
    for chapter in range(1, 4):
        parts.append(f"## CHAPTER {chapter}\n")
        parts.append(f"Body of chapter {chapter}.\n")
        parts.append(f"## 1.{chapter} Section one\n")
        parts.append("Body.\n")
    cleaned = clean_in_place("\n".join(parts))

    assert [line for line in cleaned.splitlines() if "CHAPTER" in line] == [
        "## CHAPTER 1",
        "### CHAPTER 2",
        "### CHAPTER 3",
    ]


def test_a_series_member_with_a_parent_of_its_own_keeps_its_place() -> None:
    # Two sections nest under a variant: a real parent.
    text = (
        "## 1 Product 1\n### Section 1\n"
        "## 2 Product 2\n### Section 2\n"
        "## 3 Product 3\n### Variant\n#### Section 3\n"
        "## 4 Product 4\n### Variant\n#### Section 4\n"
    )
    assert clean_in_place(text) == text


def test_a_series_split_three_against_two_is_not_settled_early() -> None:
    text = (
        "## 1 Product 1\n### Section 1\n"
        "## 2 Product 2\n### Section 2\n"
        "## 3 Product 3\n### Section 3\n"
        "## 4 Product 4\n### Variant\n#### Section 4\n"
        "## 5 Product 5\n### Variant\n#### Section 5\n"
    )
    assert clean_in_place(text) == text


def test_the_early_series_settle_is_idempotent() -> None:
    parts = ["# 1. Part one\n"]
    for chapter in range(1, 20):
        parts.append(f"{'###' if chapter == 7 else '##'} CHAPTER {chapter}\n")
        parts.append(f"Body of chapter {chapter}.\n")
        parts.append(f"## 1.{chapter} Section one\n")
        parts.append("Body.\n")
    once = clean("\n".join(parts))
    assert clean(once) == once


def test_anchored_series_of_three_is_untouched() -> None:
    text = "# 1. Part one\n## § 1. Topic\n## § 2. Topic\n## Chapter 2\n### § 3. Topic\n"
    assert clean_in_place(text) == text


def test_a_class_stands_above_the_dotted_numbers_under_it() -> None:
    # Each chapter number opens the dotted numbers of its sections.
    parts = []
    for chapter in (11, 12, 13):
        parts.append(f"{'###' if chapter == 12 else '##'} Chapter {chapter}\n")
        parts.append(f"## {chapter}.3 Section\n")
        parts.append(f"### {chapter}.3.3 Subsection\n")
    cleaned = clean_in_place("\n".join(parts))

    assert [line for line in cleaned.splitlines() if line.startswith("#")] == [
        line
        for chapter in (11, 12, 13)
        for line in (
            f"# Chapter {chapter}",
            f"## {chapter}.3 Section",
            f"### {chapter}.3.3 Subsection",
        )
    ]


def test_a_class_of_two_is_not_ranked_by_the_numbers_under_it() -> None:
    text = "## 12.3 Section\n\n### Chapter 12\n\n## 13.3 Section\n\n### Chapter 13\n"
    assert clean_in_place(text) == text


def test_a_class_with_no_dotted_numbers_under_it_is_untouched() -> None:
    text = (
        "## 1.3 Section\n\n### Chapter 11\n\n"
        "## 2.3 Section\n\n### Chapter 12\n\n"
        "## 3.3 Section\n\n### Chapter 13\n"
    )
    assert clean_in_place(text) == text


def test_a_lone_title_numbered_like_a_section_is_untouched() -> None:
    text = "## 12.3 Section\n\n### Figure 12\n\n## 12.4 Section\n\n### 12.4.1 Sub\n"
    assert clean_in_place(text) == text


def test_a_class_over_top_level_sections_stops_at_the_first_level() -> None:
    text = (
        "## Chapter 11\n\n# 11.3 Section\n\n"
        "## Chapter 12\n\n# 12.3 Section\n\n"
        "## Chapter 13\n\n# 13.3 Section\n"
    )
    assert clean_in_place(text) == (
        "# Chapter 11\n\n# 11.3 Section\n\n"
        "# Chapter 12\n\n# 12.3 Section\n\n"
        "# Chapter 13\n\n# 13.3 Section\n"
    )


def test_a_class_is_not_ranked_by_sections_outside_its_own_stretch() -> None:
    # Each caption number reappears in a later section, not under the caption.
    text = (
        "## 1.1 Introduction\n\nBody.\n\n"
        "### Figure 1\n\nCaption.\n\n"
        "### Figure 2\n\nCaption.\n\n"
        "### Figure 3\n\nCaption.\n\n"
        "## 2.1 Methods\n\nBody.\n\n"
        "## 3.1 Results\n\nBody.\n"
    )
    assert clean_in_place(text) == text


def test_the_class_rank_from_dotted_numbers_is_idempotent() -> None:
    parts = []
    for chapter in (11, 12, 13):
        parts.append(f"{'###' if chapter == 12 else '##'} Chapter {chapter}\n")
        parts.append(f"## {chapter}.3 Section\n")
        parts.append(f"### {chapter}.3.3 Subsection\n")
    once = clean("\n".join(parts))
    assert clean(once) == once


def test_part_code_headings_are_not_a_class() -> None:
    text = "# KTX6 Series\n\nA\n\n### KTX7 Series\n\nB\n\n## KTX8 Series\n\nC\n"
    assert clean_in_place(text) == text


def test_part_code_with_a_letter_suffix_is_not_a_class() -> None:
    text = "# Model 100A\n\nA\n\n## Model 100B\n\nB\n\n## Model 200A\n\nC\n"
    assert clean_in_place(text) == text


def test_dotted_numbers_are_not_a_class() -> None:
    text = (
        "# Chapter 1.2 General\n\nA\n\n"
        "### Chapter 1.3 Other\n\nB\n\n"
        "## Chapter 1.4 More\n\nC\n"
    )
    assert clean_in_place(text) == text


def test_section_sign_heading_class_converges_to_the_class_mode() -> None:
    text = (
        "# § 1. General provisions\n\nA\n\n## § 2. Rules\n\nB\n\n## § 3. Joints\n\nC\n"
    )
    assert clean_in_place(text) == (
        "## § 1. General provisions\n\nA\n\n## § 2. Rules\n\nB\n\n## § 3. Joints\n\nC\n"
    )


def test_roman_numbered_heading_class_converges_to_the_class_mode() -> None:
    # The series opens at the bare letter I.
    text = "# CHAPTER I\n\nA\n\n## CHAPTER II\n\nB\n\n## CHAPTER III\n\nC\n"
    assert clean_in_place(text) == (
        "## CHAPTER I\n\nA\n\n## CHAPTER II\n\nB\n\n## CHAPTER III\n\nC\n"
    )


def test_single_letter_type_codes_are_not_a_roman_class() -> None:
    # C, D and M are one-letter roman numerals, but a real series does not open there.
    text = "# Type C\n\nA\n\n## Type D\n\nB\n\n## Type M\n\nC\n"
    assert clean_in_place(text) == text


def test_arabic_glava_heading_class_still_works() -> None:
    text = "# CHAPTER 1\n\nA\n\n## CHAPTER 2\n\nB\n\n## CHAPTER 3\n\nC\n"
    assert clean_in_place(text) == (
        "## CHAPTER 1\n\nA\n\n## CHAPTER 2\n\nB\n\n## CHAPTER 3\n\nC\n"
    )


def test_lone_section_sign_heading_is_not_a_class() -> None:
    text = "# Introduction\n\nA\n\n## § 1. Basic terms\n\nB\n"
    assert clean_in_place(text) == text


def test_title_opening_with_a_roman_numeral_is_not_a_class() -> None:
    text = (
        "# IV The annual congress sets new tasks\n\n"
        "A\n\n"
        "## IV The annual congress sums up\n\n"
        "B\n\n"
        "### IV The annual congress closes\n\n"
        "C\n"
    )
    assert clean_in_place(text) == text


def test_heading_class_keeps_the_title_and_its_case() -> None:
    text = "# LECTURE 1\n\nA\n\n### Lecture 2\n\nB\n\n### lecture 3\n\nC\n"
    assert clean_in_place(text) == (
        "### LECTURE 1\n\nA\n\n### Lecture 2\n\nB\n\n### lecture 3\n\nC\n"
    )


def test_heading_class_level_fix_is_idempotent() -> None:
    text = (
        "# LECTURE 1\n\nA\n\n"
        "### LECTURE 2\n\nB\n\n"
        "### LECTURE 3\n\nC\n\n"
        "#### LECTURE 4\n\nD\n"
    )
    once = clean(text)
    assert clean(once) == once


def test_repeated_oversize_heading_candidates_both_lose_their_markers() -> None:
    text = f"# {_OVERSIZE_HEADING_TITLE}\n## {_OVERSIZE_HEADING_TITLE}\n"
    assert clean_in_place(text) == (
        f"{_OVERSIZE_HEADING_TITLE}\n{_OVERSIZE_HEADING_TITLE}\n"
    )


_OVERSIZE_HEADING_TITLE = (
    "Detailed discussion of the manufacturing process, its constraints, "
    "and every downstream consequence for the design team to consider, "
    "written out here in full rather than as a short title a human would "
    "actually give a section of a real document"
)


def test_an_oversize_unnumbered_heading_is_demoted_and_unreported() -> None:
    assert len(_OVERSIZE_HEADING_TITLE) > 200
    text = f"## 2.1 Setup\n## {_OVERSIZE_HEADING_TITLE}\n## 2.2 Next\n"

    assert clean(text) == f"## 2.1 Setup\n{_OVERSIZE_HEADING_TITLE}\n## 2.2 Next\n"
    assert reported(text) == ""


def test_an_oversize_heading_under_an_outline_only_parent_loses_its_marker() -> None:
    text = f"# Pump Interaction\n\n# {_OVERSIZE_HEADING_TITLE}\n"
    options = outlined((1, "Pump Interaction"))

    assert clean(text, options) == (
        f"# Pump Interaction\n\n{_OVERSIZE_HEADING_TITLE}\n"
    )
    assert reported(text, options) == ""


def test_the_oversize_heading_strip_is_idempotent() -> None:
    text = f"## 2.1 Setup\n## {_OVERSIZE_HEADING_TITLE}\n## 2.2 Next\n"
    once = clean(text)
    assert clean(once) == once


def test_detect_oversize_headings_still_backstops_a_synthesized_heading() -> None:
    # Only heading recovery can build an oversize heading after the strip.
    seg_list = [
        ("## 1 Chapter", False),
        ("", False),
        (f"##### {_OVERSIZE_HEADING_TITLE}", False),
    ]
    assert detect_oversize_headings(seg_list, SourceOutline.empty(), KEYWORDS) == {2: 1}


# ---- a gap one section leaves in the ladder ------------------------------------


def test_section_skipping_a_rank_the_rest_of_the_body_uses_is_closed() -> None:
    text = "# A\n\n## A1\n\n# B\n\n### B1\n"
    assert clean_in_place(text) == "# A\n\n## A1\n\n# B\n\n## B1\n"


def test_rank_standing_anywhere_in_the_section_keeps_the_jump() -> None:
    text = "# A\n\n### A1\n\n## A2\n\n# B\n\n## B1\n"
    assert clean_in_place(text) == text


def test_numbering_skipping_a_depth_in_one_chapter_is_closed() -> None:
    text = "# 1 Alpha\n\n### 1.1.1 Deep\n\n# 2 Beta\n\n## 2.1 Gamma\n"
    assert (
        clean_in_place(text)
        == "# 1 Alpha\n\n## 1.1.1 Deep\n\n# 2 Beta\n\n## 2.1 Gamma\n"
    )


def test_outline_stated_heading_keeps_its_rank_over_the_gap() -> None:
    text = "# 1 Alpha\n\n### Gamma\n\n# 2 Beta\n\n## 2.1 Delta\n"
    options = outlined((1, "1 Alpha"), (3, "Gamma"))

    assert clean_in_place(text, options) == text


def test_a_wider_gap_is_left_standing() -> None:
    text = "# A\n\n#### B\n\n# C\n\n## C1\n\n### C2\n"
    assert clean_in_place(text) == text


def test_a_setext_heading_holds_the_rank_between() -> None:
    text = "# A\n\nTitle\n-----\n\n### B\n\n# C\n\n### D\n"
    assert clean_in_place(text) == "# A\n\nTitle\n-----\n\n### B\n\n# C\n\n## D\n"


def test_a_gapped_section_moves_with_everything_it_holds() -> None:
    text = "# A\n\n### A1\n\n#### A2\n\n# B\n\n## B1\n\n### B2\n\n#### B3\n"
    assert clean_in_place(text) == (
        "# A\n\n## A1\n\n### A2\n\n# B\n\n## B1\n\n### B2\n\n#### B3\n"
    )


def test_a_hole_the_move_leaves_inside_the_section_closes_next_round() -> None:
    # Outside the coordinator rounds, one walk leaves the subsection two ranks under.
    seg_list = [("# A", False), ("### A1", False), ("##### A2", False)]
    assert [line for line, _ in close_section_level_gaps(seg_list)] == [
        "# A",
        "## A1",
        "### A2",
    ]


def test_a_section_holding_a_settled_heading_stays_whole() -> None:
    seg_list = [("# A", False), ("### A1", False), ("#### Remark", False)]
    assert close_section_level_gaps(seg_list, group_settled=frozenset({2})) == seg_list


def test_section_gap_closing_is_idempotent() -> None:
    once = clean("# A\n\n## A1\n\n# B\n\n### B1\n\n#### B2\n")
    assert clean(once) == once


# ---- a heading level the document never uses -----------------------------------


def test_level_no_heading_stands_on_is_collapsed() -> None:
    text = "# A\n\n### B\n"
    assert clean_in_place(text) == "# A\n\n## B\n"


def test_dense_heading_ladder_is_left_alone() -> None:
    text = "# A\n\n## B\n\n### C\n\n## D\n"
    assert clean_in_place(text) == text


def test_two_unused_levels_collapse_until_the_ladder_is_dense() -> None:
    text = "# A\n\n### B\n\n##### C\n"
    assert clean_in_place(text) == "# A\n\n## B\n\n### C\n"


def test_outline_stated_levels_take_part_in_the_collapse() -> None:
    # Most of the outline is unprinted, so no skeleton lift; the collapse closes it.
    text = "# MODLINK\n\nA\n\n### Setup\n\nB\n\n### Wiring\n\nC\n"
    options = outlined(
        (1, "MODLINK"),
        (2, "General information"),
        (2, "Mounting"),
        (2, "Diagnostics"),
        (2, "Приложение"),
        (3, "Setup"),
        (3, "Wiring"),
    )

    assert clean_in_place(text, options) == (
        "# MODLINK\n\nA\n\n## Setup\n\nB\n\n## Wiring\n\nC\n"
    )


def test_body_starting_below_the_top_level_is_not_promoted() -> None:
    text = "## A\n\n### B\n"
    assert clean_in_place(text) == text


def test_gap_above_the_document_s_own_top_level_still_closes() -> None:
    text = "## A\n\n#### B\n\n## C\n"
    assert clean_in_place(text) == "## A\n\n### B\n\n## C\n"


def test_setext_heading_holds_its_level_in_the_ladder() -> None:
    text = "# A\n\nTitle\n-----\n\n### B\n"
    assert clean_in_place(text) == text


def test_heading_in_a_code_fence_does_not_hold_a_level() -> None:
    text = "# A\n\n```\n## sample\n```\n\n### B\n"
    assert clean_in_place(text) == "# A\n\n```\n## sample\n```\n\n## B\n"


def test_heading_level_collapse_is_idempotent() -> None:
    once = clean("# A\n\n### B\n\n##### C\n")
    assert clean(once) == once


def test_a_rank_the_body_never_prints_closes_for_every_section() -> None:
    # The collapse runs before the section lift; rank 2 is never printed.
    text = "# A\n\n### A1\n\n#### A2\n\n# B\n\n#### B1\n"
    assert clean_in_place(text) == "# A\n\n## A1\n\n### A2\n\n# B\n\n## B1\n"


# ---- protected zones vs numbering --------------------------------------------


def test_numbered_heading_in_front_matter_is_not_counted() -> None:
    text = "---\n### 1.1 X\n### 1.2 Y\n---\n## 1.3 A\n"
    assert clean_in_place(text) == text


def test_numbered_heading_in_html_table_is_not_counted() -> None:
    text = (
        "## 2.1 A\n"
        "<table>\n"
        "<tr><td>### 2.2 x</td></tr>\n"
        "<tr><td>### 2.3 y</td></tr>\n"
        "</table>\n"
    )
    assert clean_in_place(text) == text


# ---- heading levels from the contents the body prints ---------------------------


def _contents_body(*rows: str) -> str:
    """A body opening with a printed contents table built from `rows`."""
    return _contents_body_headed("# Оглавление", *rows)


def _contents_body_headed(heading: str, *rows: str) -> str:
    """`_contents_body` with the contents heading given rather than fixed.

    The table is laid out as cleaning delivers it, so cleaning leaves it as it
    stands; a row off the header width stays as written.
    """
    header = "| Section | Title | Стр. |"
    if any(row.count("|") != header.count("|") for row in rows):
        table = f"{header}\n|---|---|---|\n" + "".join(f"{row}\n" for row in rows)
    else:
        table = laid_out_table(header, *rows)
    return f"{heading}\n\n{table}"


def test_the_printed_contents_gives_each_heading_class_its_own_level() -> None:
    text = _contents_body(
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
        "|  | § 3. Belt tension | 9 |",
        "|  | § 4. Drive pair | 12 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n\n"
        "#### § 3. Belt tension\n\n"
        "### § 4. Drive pair\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "# Chapter 2 Setup\n\n"
        "## § 3. Belt tension\n\n"
        "## § 4. Drive pair\n"
    )


def test_the_contents_heading_word_comes_from_the_dictionary() -> None:
    options = CleanOptions(keywords=replace(KEYWORDS, contents_heading=("index",)))
    rows = (
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
    )
    body = "\n### Chapter 1 Introduction\n\n#### § 1. Basic terms\n\n### § 2. Rules\n"
    levelled = "\n# Chapter 1 Introduction\n\n## § 1. Basic terms\n\n## § 2. Rules\n"
    stated = _contents_body_headed("# Index", *rows) + body
    assert clean_in_place(stated, options).endswith(levelled)
    dropped = _contents_body_headed("# Оглавление", *rows) + body
    assert not clean_in_place(dropped, options).endswith(levelled)


def test_a_contents_entry_matches_the_body_past_its_page_number() -> None:
    text = _contents_body(
        "| Chapter 1 | Introduction . . . . . | 3 |",
        "|  | § 1. Basic terms . . . | 3 |",
        "|  | § 2. Rules . . . . . . . | 5 |",
        "| Chapter 2 | Setup . . . . . . | 9 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "# Chapter 2 Setup\n"
    )


def test_a_contents_row_never_becomes_a_heading() -> None:
    text = _contents_body(
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )

    assert clean_in_place(text).startswith(
        _contents_body(
            "| Chapter 1 | Introduction | 3 |",
            "|  | § 1. Basic terms | 3 |",
            "|  | § 2. Rules | 5 |",
            "| Chapter 2 | Setup | 9 |",
        )
    )


def test_a_contents_record_that_kept_its_page_number_is_skipped() -> None:
    # The page cell is lost, so the trailing numbers are ambiguous.
    text = _contents_body(
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules 5 |  |",
        "| Chapter 2 | Setup | 9 |",
        "|  | § 3. Belt tension | 12 |",
        "|  | § 4. Drive pair | 15 |",
        "|  | § 5. Lubrication | 18 |",
        "|  | § 6. Backlash | 21 |",
    ) + ("\n### Chapter 1 Introduction\n\n#### § 1. Basic terms\n\n### § 2. Rules\n")

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n## § 1. Basic terms\n\n### § 2. Rules\n"
    )


def test_a_contents_whose_table_lost_its_columns_states_nothing() -> None:
    text = _contents_body(
        "| Chapter 1 Introduction | 3 |",
        "| § 1. Basic terms | 3 |",
        "| § 2. Rules | 5 |",
        "| Chapter 2 Setup | 9 |",
    ) + (
        "\n## Chapter 1 Introduction\n\n"
        "### § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "### Chapter 2 Setup\n"
    )

    assert clean_in_place(text) == text


def test_a_body_with_no_printed_contents_is_left_alone() -> None:
    text = _contents_body_headed(
        "# Overview",
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n## Chapter 1 Introduction\n\n"
        "### § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "### Chapter 2 Setup\n"
    )

    assert clean_in_place(text) == text


def test_the_source_outline_outranks_the_contents_the_body_prints() -> None:
    text = _contents_body(
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )
    options = outlined(
        (1, "Chapter 1 Introduction"),
        (1, "§ 1. Basic terms"),
        (1, "§ 2. Rules"),
        (1, "Chapter 2 Setup"),
    )

    assert clean_in_place(text, options).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "# § 1. Basic terms\n\n"
        "# § 2. Rules\n\n"
        "# Chapter 2 Setup\n"
    )


def test_reading_the_printed_contents_is_idempotent() -> None:
    text = _contents_body(
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )

    once = clean(text)
    assert clean(once) == once


def test_a_contents_heading_glued_onto_the_table_header_still_opens_it() -> None:
    # marker merges the line above a table into the table header.
    text = (
        "# Оглавление | Section | Title | Стр. |\n"
        "|---|---|---|\n"
        "| Chapter 1 | Introduction | 3 |\n"
        "|  | § 1. Basic terms | 3 |\n"
        "|  | § 2. Rules | 5 |\n"
        "| Chapter 2 | Setup | 9 |\n\n"
        "### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "# Chapter 2 Setup\n"
    )


def test_a_contents_table_with_no_column_labels_keeps_its_first_entry() -> None:
    # With no column labels, the converter puts the first entry in the header row.
    text = (
        "# Оглавление\n\n"
        "| Chapter 1 | Introduction | 3 |\n"
        "|---|---|---|\n"
        "|  | § 1. Basic terms | 3 |\n"
        "|  | § 2. Rules | 5 |\n"
        "|  | § 3. Belt tension | 9 |\n\n"
        "### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### § 3. Belt tension\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "## § 3. Belt tension\n"
    )


def test_a_contents_that_reads_upside_down_states_nothing() -> None:
    # Centered chapter titles land right of the section marks.
    text = (
        "# Оглавление\n\n"
        "| § | 1. | Basic terms     | 3  |\n"
        "|---|----|-----------------|----|\n"
        "| § | 2. | Rules           | 5  |\n"
        "|   |    | Chapter 2 Setup | 9  |\n"
        "| § | 3. | Belt tension    | 9  |\n"
        "| § | 4. | Drive pair      | 12 |\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "## Chapter 2 Setup\n\n"
        "## § 3. Belt tension\n"
    )

    assert clean_in_place(text) == text


def test_a_glued_contents_heading_leaves_the_entry_beside_it_readable() -> None:
    text = (
        "# Оглавление | Chapter 1 | Introduction | 3 |\n"
        "|---|---|---|\n"
        "|  | § 1. Basic terms | 3 |\n"
        "|  | § 2. Rules | 5 |\n"
        "|  | § 3. Belt tension | 9 |\n\n"
        "### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### § 3. Belt tension\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "## § 3. Belt tension\n"
    )


@pytest.mark.parametrize(
    "heading",
    [
        "# 1.2 Содержание",  # a running header's section number ahead of the word
        "# II. Оглавление",  # a roman folio ahead of the word
        "# Inhaltsverzeichnis",  # DE
        "# Sommaire",  # FR
        "# Índice",  # ES/IT, and the accent a scan drops
        "# 目录",  # ZH
        "# I N D I C E",  # a scan that prints the word letter-spaced
        "# TABLE DES MATIERES",  # FR, and the accent a scan drops
    ],
)
def test_a_printed_contents_zone_opens_on_each_served_heading_form(
    heading: str,
) -> None:
    text = _contents_body_headed(
        heading,
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "# Chapter 2 Setup\n"
    )


def test_a_letter_spaced_non_contents_word_leaves_the_zone_shut() -> None:
    text = _contents_body_headed(
        "# С П И С О К",  # noqa: RUF001 -- a Cyrillic word spelled letter by letter
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n## Chapter 1 Introduction\n\n"
        "### § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "### Chapter 2 Setup\n"
    )

    assert clean_in_place(text) == text


def test_a_section_named_after_the_contents_word_opens_no_zone() -> None:
    text = _contents_body_headed(
        "# Содержание тома",
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n## Chapter 1 Introduction\n\n"
        "### § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "### Chapter 2 Setup\n"
    )

    assert clean_in_place(text) == text


def test_a_contents_heading_crushed_with_its_first_entry_still_opens_the_zone() -> None:
    # A page break leaves the contents heading and the first entries on one line.
    text = _contents_body_headed(
        "# Оглавление. Chapter 1 Introduction",
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "# Chapter 2 Setup\n"
    )


def test_a_multi_word_contents_word_crushed_with_its_entries_opens_the_zone() -> None:
    text = _contents_body_headed(
        "# TABLE DES MATIERES. INTRODUCTION",
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
        "| Chapter 2 | Setup | 9 |",
    ) + (
        "\n### Chapter 1 Introduction\n\n"
        "#### § 1. Basic terms\n\n"
        "### § 2. Rules\n\n"
        "##### Chapter 2 Setup\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "# Chapter 2 Setup\n"
    )


def _contents_zone(*blocks: tuple[str, ...]) -> str:
    """A body whose contents the converter cut into one table per `blocks` entry."""
    tables = "\n".join(
        "| Section | Title | Стр. |\n|---|---|---|\n"
        + "".join(f"{row}\n" for row in rows)
        for rows in blocks
    )
    return f"# Оглавление\n\n{tables}"


def test_a_printed_contents_cut_into_tables_states_one_ladder() -> None:
    # One contents page cut into four tables; the fourth lost its columns.
    text = _contents_zone(
        (
            "| 1 |  |  | Introduction | 3 |",
            "|  | 1.1 |  | Basic terms | 3 |",
            "|  |  | 1.1.1 | Terms | 4 |",
        ),
        (
            "| 2 |  |  | Setup | 9 |",
            "|  | 2.1 |  | Belt tension | 9 |",
            "|  |  | 2.1.1 | Pulley size | 10 |",
        ),
        (
            "| 3 |  |  | Wiring | 20 |",
            "|  | 3.1 |  | Feed rate | 20 |",
            "|  |  | 3.1.1 | Feed ramp | 22 |",
        ),
        (
            "| 4 Tuning | 30 |",
            "| 4.1 Tool wear | 30 |",
            "|  | 4.1.1 Spindle power | 32 |",
        ),
    ) + (
        "\n## 1 Introduction\n\n"
        "## 1.1 Basic terms\n\n"
        "## 1.1.1 Terms\n\n"
        "## 2 Setup\n\n"
        "## 2.1 Belt tension\n\n"
        "## 2.1.1 Pulley size\n\n"
        "## 3 Wiring\n\n"
        "## 3.1 Feed rate\n\n"
        "## 3.1.1 Feed ramp\n\n"
        "## 4 Tuning\n\n"
        "## 4.1 Tool wear\n\n"
        "## 4.1.1 Spindle power\n"
    )

    assert clean_in_place(text).endswith(
        "\n# 1 Introduction\n\n"
        "## 1.1 Basic terms\n\n"
        "### 1.1.1 Terms\n\n"
        "# 2 Setup\n\n"
        "## 2.1 Belt tension\n\n"
        "### 2.1.1 Pulley size\n\n"
        "# 3 Wiring\n\n"
        "## 3.1 Feed rate\n\n"
        "### 3.1.1 Feed ramp\n\n"
        "# 4 Tuning\n\n"
        "## 4.1 Tool wear\n\n"
        "### 4.1.1 Spindle power\n"
    )


def test_a_contents_table_that_lost_a_column_does_not_rerank_the_zone() -> None:
    intact = (
        "| 1 |  |  | Introduction | 3 |",
        "|  | 1.1 |  | Basic terms | 3 |",
        "|  |  | 1.1.1 | Terms | 4 |",
    )
    damaged = (
        "| 2 Setup | 9 |",
        "| 2.1 Belt tension | 9 |",
        "| 2.1.1 Pulley size | 10 |",
    )
    body = "\n## 1 Introduction\n\n## 1.1 Basic terms\n\n## 1.1.1 Terms\n"
    ladder = "\n# 1 Introduction\n\n## 1.1 Basic terms\n\n### 1.1.1 Terms\n"

    assert clean_in_place(_contents_zone(intact, damaged) + body).endswith(ladder)
    assert clean_in_place(_contents_zone(intact) + body).endswith(ladder)


def test_a_dotted_number_states_the_depth_whatever_the_column() -> None:
    text = _contents_zone(
        (
            "| 1 | Introduction | 3 |",
            "|  | 1.1 Basic terms | 3 |",
            "| 1.1.1 | Terms | 4 |",
            "| 2 | Setup | 9 |",
            "| 2.1.1 | Pulley size | 10 |",
        ),
    ) + (
        "\n## 1 Introduction\n\n"
        "## 1.1 Basic terms\n\n"
        "## 1.1.1 Terms\n\n"
        "## 2 Setup\n\n"
        "## 2.1.1 Pulley size\n"
    )

    assert clean_in_place(text).endswith(
        "\n# 1 Introduction\n\n"
        "## 1.1 Basic terms\n\n"
        "### 1.1.1 Terms\n\n"
        "# 2 Setup\n\n"
        "### 2.1.1 Pulley size\n"
    )


def test_a_one_column_contents_is_read_by_the_numbers_of_its_records() -> None:
    text = _contents_zone(
        (
            "| 1 | Introduction | 3 |",
            "| 1.1 | Basic terms | 3 |",
            "| 1.2 | Rules | 5 |",
        ),
        (
            "| 1.2.1 | Joints | 6 |",
            "| 2 | Setup | 9 |",
            "| 2.1 | Belt tension | 9 |",
        ),
    )
    outline = printed_outline(segments(text), KEYWORDS)

    assert outline.title_count == 6
    assert outline.level_for("1 Introduction") == 1
    assert outline.level_for("1.2 Rules") == 2
    assert outline.level_for("1.2.1 Joints") == 3
    assert outline.level_for("2.1 Belt tension") == 2


def test_a_contents_page_printing_one_rank_states_that_rank() -> None:
    text = _contents_zone(
        (
            "| 1 | Introduction | 3 |",
            "| 1.1 | Basic terms | 3 |",
        ),
        (
            "| 1.2 | Rules | 5 |",
            "| 1.3 | Joints | 6 |",
            "| 1.4 | Base loads | 7 |",
        ),
    )
    outline = printed_outline(segments(text), KEYWORDS)

    assert outline.title_count == 5
    assert outline.level_for("1.4 Base loads") == 2


def test_a_numbered_record_does_not_save_a_table_read_upside_down() -> None:
    text = _contents_zone(
        (
            "| 1 | Introduction | 3 |",
            "|  |  | Chapter 2 Setup | 9 |",
            "| 1.1 | Basic terms | 4 |",
        ),
    )

    assert printed_outline(segments(text), KEYWORDS).title_count == 0


def test_a_numbered_contents_in_one_table_reads_by_its_columns() -> None:
    text = _contents_zone(
        (
            "| 1 |  | Introduction | 3 |",
            "|  | 1.1 | Basic terms | 3 |",
            "|  | 1.2 | Rules | 5 |",
            "| 2 |  | Setup | 9 |",
            "|  | 2.1 | Belt tension | 9 |",
        ),
    ) + (
        "\n### 1 Introduction\n\n"
        "#### 1.1 Basic terms\n\n"
        "### 1.2 Rules\n\n"
        "##### 2 Setup\n\n"
        "#### 2.1 Belt tension\n"
    )

    assert clean_in_place(text).endswith(
        "\n# 1 Introduction\n\n"
        "## 1.1 Basic terms\n\n"
        "## 1.2 Rules\n\n"
        "# 2 Setup\n\n"
        "## 2.1 Belt tension\n"
    )


def test_a_chapter_number_the_zone_opens_states_the_top_rank() -> None:
    # An empty leading column; `1.1` and `2.1` make `1` and `2` chapters.
    text = _contents_zone(
        (
            "|  | 1 | Introduction | 3 |",
            "|  | 1.1 | Basic terms | 4 |",
            "|  | 1.1.1 | Terms | 5 |",
            "|  | 2 | Setup | 9 |",
            "|  | 2.1 | Belt tension | 11 |",
        ),
    ) + (
        "\n## 1 Introduction\n\n"
        "## 1.1 Basic terms\n\n"
        "## 1.1.1 Terms\n\n"
        "## 2 Setup\n\n"
        "## 2.1 Belt tension\n"
    )

    assert clean_in_place(text).endswith(
        "\n# 1 Introduction\n\n"
        "## 1.1 Basic terms\n\n"
        "### 1.1.1 Terms\n\n"
        "# 2 Setup\n\n"
        "## 2.1 Belt tension\n"
    )


def test_a_number_the_zone_never_opens_is_read_by_its_column() -> None:
    text = _contents_zone(
        (
            "| Introduction | 3 |",
            "|  | 1.1 Basic terms | 4 |",
            "|  | 2 standard sizes | 6 |",
            "| Setup | 9 |",
            "|  | 1.2 Belt tension | 11 |",
        ),
    ) + (
        "\n## Introduction\n\nBody.\n\n## 1.1 Basic terms\n\nBody.\n\n"
        "## 2 standard sizes\n\nBody.\n\n## Setup\n\nBody.\n\n"
        "## 1.2 Belt tension\n\nBody.\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Introduction\n\nBody.\n\n## 1.1 Basic terms\n\nBody.\n\n"
        "## 2 standard sizes\n\nBody.\n\n# Setup\n\nBody.\n\n"
        "## 1.2 Belt tension\n\nBody.\n"
    )


def test_an_unnumbered_child_stays_under_its_numbered_parent() -> None:
    text = _contents_zone(
        (
            "| 1.1 Basic terms |  |  | 3 |",
            "|  |  | Setup rules | 4 |",
            "| 1.2 Belt tension |  |  | 9 |",
            "|  |  | Pulley size | 11 |",
        ),
    ) + (
        "\n## 1.1 Basic terms\n\nBody.\n\n## Setup rules\n\nBody.\n\n"
        "## 1.2 Belt tension\n\nBody.\n\n## Pulley size\n\nBody.\n"
    )

    assert clean_in_place(text).endswith(
        "\n# 1.1 Basic terms\n\nBody.\n\n## Setup rules\n\nBody.\n\n"
        "# 1.2 Belt tension\n\nBody.\n\n## Pulley size\n\nBody.\n"
    )


def test_a_contents_page_opening_inside_the_tree_keeps_its_depth() -> None:
    text = _contents_zone(
        (
            "| Introduction | 3 |",
            "|  | Basic terms | 4 |",
        ),
        (
            "|  | Belt tension | 9 |",
            "|  |  | Pulley size | 10 |",
        ),
    ) + (
        "\n## Introduction\n\nBody.\n\n## Basic terms\n\nBody.\n\n"
        "## Belt tension\n\nBody.\n\n## Pulley size\n\nBody.\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Introduction\n\nBody.\n\n## Basic terms\n\nBody.\n\n"
        "## Belt tension\n\nBody.\n\n### Pulley size\n\nBody.\n"
    )


def test_a_rank_word_with_its_roman_number_in_its_own_column_states_the_top_rank() -> (
    None
):
    text = _contents_zone(
        (
            "| Ch. | I | Introduction | 3 |",
            "| Ch. | II | Setup | 9 |",
            "| Ch. | III | Wiring | 20 |",
        ),
    ) + ("\n### Ch. I Introduction\n\n### Ch. II Setup\n\n### Ch. III Wiring\n")

    assert clean_in_place(text).endswith(
        "\n# Ch. I Introduction\n\n# Ch. II Setup\n\n# Ch. III Wiring\n"
    )


def test_an_arabic_rank_number_in_its_own_column_is_read_the_same_way() -> None:
    text = _contents_zone(
        (
            "| Part | 1 | Introduction | 3 |",
            "| Part | 2 | Setup | 9 |",
            "| Part | 3 | Wiring | 20 |",
        ),
    ) + ("\n### Part 1 Introduction\n\n### Part 2 Setup\n\n### Part 3 Wiring\n")

    assert clean_in_place(text).endswith(
        "\n# Part 1 Introduction\n\n# Part 2 Setup\n\n# Part 3 Wiring\n"
    )


def test_a_column_repeating_a_page_word_is_not_read_as_a_page() -> None:
    # The header keeps the page word; a bad scan turns it into a stray digit below.
    text = (
        "# Оглавление\n\n"
        "| Ch. | I | Introduction | стр. | 3 |\n"
        "|---|---|---|---|---|\n"
        "| Ch. | II | Setup | стр. | 9 |\n"
        "| Ch. | III | Wiring | 11 | 20 |\n\n"
        "### Ch. I Introduction\n\n### Ch. II Setup\n\n### Ch. III Wiring\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Ch. I Introduction\n\n# Ch. II Setup\n\n# Ch. III Wiring\n"
    )


def test_the_page_label_word_comes_from_the_dictionary() -> None:
    options = CleanOptions(keywords=replace(KEYWORDS, contents_page_label=("page",)))
    text = (
        "# Оглавление\n\n"
        "| Ch. | I | Introduction | стр. | 3 |\n"
        "|---|---|---|---|---|\n"
        "| Ch. | II | Setup | стр. | 9 |\n"
        "| Ch. | III | Wiring | 11 | 20 |\n\n"
        "### Ch. I Introduction\n\n### Ch. II Setup\n\n### Ch. III Wiring\n"
    )
    levelled = "\n# Ch. I Introduction\n\n# Ch. II Setup\n\n# Ch. III Wiring\n"
    assert clean_in_place(text).endswith(levelled)
    assert not clean_in_place(text, options).endswith(levelled)


def test_a_lost_page_marker_inside_the_contents_zone_states_no_record() -> None:
    text = (
        "# Оглавление\n\n"
        "[page 2 not recognized]\n\n"
        "| Section | Title | Стр. |\n|---|---|---|\n"
        "| 1 | Introduction | 3 |\n"
        "| 1.1 | Basic terms | 3 |\n\n"
        "### 1 Introduction\n\n### 1.1 Basic terms\n"
    )
    outline = printed_outline(segments(text), KEYWORDS)
    assert outline.title_count == 2
    assert outline.level_for("1 Introduction") == 1
    assert outline.level_for("1.1 Basic terms") == 2


def test_a_contents_naming_two_ranks_keeps_the_chapter_under_its_part() -> None:
    text = (
        "# Оглавление\n\n"
        "| Section | № | Title | Стр. |\n"
        "|---|---|---|---|\n"
        "| Part | I |  | Basics | 3 |\n"
        "|  | Chapter | 1 | Introduction | 5 |\n"
        "|  | Chapter | 2 | Setup | 9 |\n"
        "| Part | II |  | Appendices | 20 |\n\n"
        "### Part I Basics\n\n#### Chapter 1 Introduction\n\n"
        "#### Chapter 2 Setup\n\n### Part II Appendices\n"
    )

    assert clean_in_place(text).endswith(
        "\n# Part I Basics\n\n## Chapter 1 Introduction\n\n"
        "## Chapter 2 Setup\n\n# Part II Appendices\n"
    )


# ---- the furniture of a printed contents page ------------------------------

_RUNNING_HEAD = "## Operating manual"

_CUT_CONTENTS_BODY = (
    "\n### Chapter 1 Introduction\n\n"
    "#### § 1. Basic terms\n\n"
    "### § 2. Rules\n\n"
    "##### Chapter 2 Setup\n\n"
    "#### § 3. Belt tension\n\n"
    "### § 4. Drive pair\n"
)


def _contents_cut_by(
    furniture: str, *, above: str = "", heading: str = "# Оглавление"
) -> str:
    """A printed contents cut into two pages, `furniture` standing between them.

    `above` stands over the contents heading. The body writes every title at its own
    level, so the output level of a title is what the zone states about it.
    """
    first = _contents_page(
        "| Chapter 1 | Introduction | 3 |",
        "|  | § 1. Basic terms | 3 |",
        "|  | § 2. Rules | 5 |",
    )
    second = _contents_page(
        "| Chapter 2 | Setup | 9 |",
        "|  | § 3. Belt tension | 9 |",
        "|  | § 4. Drive pair | 12 |",
    )
    opening = f"{above}\n\n" if above else ""
    return f"{opening}{heading}\n\n{first}\n{furniture}\n\n{second}{_CUT_CONTENTS_BODY}"


def _contents_page(*rows: str) -> str:
    """One printed page of a contents, as the converter renders it: a table."""
    return "| Section | Title | Стр. |\n|---|---|---|\n" + "".join(
        f"{row}\n" for row in rows
    )


def test_a_running_head_does_not_close_the_printed_contents_zone() -> None:
    text = _contents_cut_by(_RUNNING_HEAD, above=_RUNNING_HEAD)

    assert clean_in_place(text).endswith(
        "\n# Chapter 1 Introduction\n\n"
        "## § 1. Basic terms\n\n"
        "## § 2. Rules\n\n"
        "# Chapter 2 Setup\n\n"
        "## § 3. Belt tension\n\n"
        "## § 4. Drive pair\n"
    )


def test_a_running_head_leaves_every_record_of_the_contents_readable() -> None:
    text = _contents_cut_by(_RUNNING_HEAD, above=_RUNNING_HEAD)

    assert printed_outline(segments(text), KEYWORDS).title_count == 6


def test_a_section_heading_closes_the_printed_contents_zone() -> None:
    text = _contents_cut_by("## Part one. Setup")

    assert printed_outline(segments(text), KEYWORDS).title_count == 3


def test_a_repeated_heading_opens_no_contents_zone_of_its_own() -> None:
    text = _contents_cut_by(_RUNNING_HEAD, above=_RUNNING_HEAD, heading="# Overview")

    assert printed_outline(segments(text), KEYWORDS).title_count == 0


def test_reading_a_contents_past_its_running_head_is_idempotent() -> None:
    once = clean(_contents_cut_by(_RUNNING_HEAD, above=_RUNNING_HEAD))

    assert clean(once) == once
