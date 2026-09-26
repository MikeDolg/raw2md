"""Tests for the list rules.

Every repair is conservative: a block that could be real nesting stays as it
stands.
"""

from __future__ import annotations

from raw2md.cleaner import clean, clean_in_place

# ---- list de-nesting ---------------------------------------------------------


def test_numbered_zigzag_restored_to_flat_ordered() -> None:
    # marker writes a numbered list as alternating `- N.` bullets.
    text = "- 2. A\n  - 3. B\n- 4. C\n"
    assert clean_in_place(text) == "2. A\n3. B\n4. C\n"


def test_paren_delimiter_is_preserved_on_restore() -> None:
    assert clean_in_place("- 2) A\n  - 3) B\n") == "2) A\n3) B\n"


def test_number_bullet_text_after_number_is_kept() -> None:
    assert clean_in_place("- 2. First point\n- 3. Second point\n") == (
        "2. First point\n3. Second point\n"
    )


def test_indented_code_lines_are_not_rewritten_as_lists() -> None:
    # Four-space indented lines are an indented code block.
    text = "para\n\n    - 2. A\n    - 3. B\n"
    assert clean_in_place(text) == text


def test_numeric_bullet_with_restarted_sublist_is_preserved() -> None:
    text = "- 2024. Plan\n  - 1. Scope\n  - 2. Risks\n"
    assert clean_in_place(text) == text


def test_non_ascending_number_bullets_are_left_alone() -> None:
    text = "- 3. C\n  - 1. A\n- 2. B\n"
    assert clean_in_place(text) == text


def test_gapped_numeric_bullets_like_years_are_left_alone() -> None:
    # An ordered list would renumber the years.
    text = "- 2023. Revenue\n- 2025. Profit\n"
    assert clean_in_place(text) == text


def test_lone_numbered_subpoint_child_is_preserved() -> None:
    text = "- A\n- B\n  - 1. Only subpoint\n- C\n"
    assert clean_in_place(text) == text


def test_lone_number_bullet_is_left_alone() -> None:
    text = "- 5. Only numbered\n- other item\n"
    assert clean_in_place(text) == text


def test_number_text_without_boundary_is_not_a_marker() -> None:
    text = "- 2.text\n- 3.more\n"
    assert clean_in_place(text) == text


def test_real_bullet_nesting_is_preserved() -> None:
    text = "- A\n  - B\n  - C\n- D\n"
    assert clean_in_place(text) == text


def test_real_numbered_sub_list_under_parent_is_preserved() -> None:
    text = "- Topic\n  - 1. Intro\n  - 2. Scope\n"
    assert clean_in_place(text) == text


def test_nested_numbered_sublist_restored_independently_of_outer() -> None:
    # The child restart is no break in the parent count; indent widens from 2 to 3.
    text = "- 1. A\n- 2. B\n- 3. Step:\n  - 1. Sub A\n  - 2. Sub B\n- 4. C\n"
    assert clean_in_place(text) == (
        "1. A\n2. B\n3. Step:\n   1. Sub A\n   2. Sub B\n4. C\n"
    )


def test_nested_run_that_does_not_itself_qualify_stays_nested() -> None:
    # The deeper run does not qualify, but shifts with the widened parent marker.
    text = "- 1. A\n- 2. B\n  - detail one\n  - detail two\n- 3. C\n"
    assert clean_in_place(text) == (
        "1. A\n2. B\n   - detail one\n   - detail two\n3. C\n"
    )


def test_nested_numbered_sublist_restore_is_idempotent() -> None:
    text = "- 1. A\n- 2. B\n- 3. Step:\n  - 1. Sub A\n  - 2. Sub B\n- 4. C\n"
    once = clean(text)
    assert clean(once) == once


def test_zigzag_continuation_item_keeps_its_own_child_and_is_restored() -> None:
    # "2. B" has its own child, which shifts from 4 to 3 with it.
    text = "- 1. A\n  - 2. B\n    - note\n- 3. C\n"
    assert clean_in_place(text) == "1. A\n2. B\n   - note\n3. C\n"


def test_numbered_sublist_under_zigzag_continuation_is_restored() -> None:
    # The grandchildren restart their own count, apart from the outer one.
    text = "- 1. A\n  - 2. B\n    - 1. sub\n    - 2. sub\n- 3. C\n"
    assert clean_in_place(text) == "1. A\n2. B\n   1. sub\n   2. sub\n3. C\n"


def test_four_space_nested_numbered_sublist_is_restored() -> None:
    # Inside a confirmed list, a four-space run is not indented code.
    text = "- 1. A\n- 2. B\n- 3. Step:\n    - 1. Sub A\n    - 2. Sub B\n- 4. C\n"
    assert clean_in_place(text) == (
        "1. A\n2. B\n3. Step:\n     1. Sub A\n     2. Sub B\n4. C\n"
    )


def test_real_bullet_nesting_inside_restored_numbered_list_is_preserved() -> None:
    # All three shift by +1, so C stays one level under B.
    text = "- 1. Parent\n  - A\n  - B\n    - C\n  - D\n- 2. Other\n"
    assert clean_in_place(text) == (
        "1. Parent\n   - A\n   - B\n     - C\n   - D\n2. Other\n"
    )


def test_flat_demoted_numbered_list_without_zigzag_is_restored() -> None:
    text = "- 2. A\n- 3. B\n- 4. C\n"
    assert clean_in_place(text) == "2. A\n3. B\n4. C\n"


def test_restored_numbered_list_keeps_a_real_nested_child() -> None:
    # The child shifts from 2 to 3 with the wider `1. ` marker.
    text = "- 1. Topic\n  - detail\n- 2. Other\n"
    assert clean_in_place(text) == "1. Topic\n   - detail\n2. Other\n"


def test_lone_child_among_flush_is_flattened() -> None:
    text = "- A\n- B\n  - C\n- D\n"
    assert clean_in_place(text) == "- A\n- B\n- C\n- D\n"


def test_single_child_after_one_flush_is_left_alone() -> None:
    text = "- A\n  - B\n- C\n"
    assert clean_in_place(text) == text


def test_ordered_markers_are_left_untouched() -> None:
    text = "1. A\n2. B\n3. C\n"
    assert clean_in_place(text) == text


def test_denesting_does_not_cross_a_blank_line() -> None:
    text = "- 2. A\n\n  - 3. B\n"
    assert clean_in_place(text) == text


def test_denesting_does_not_reach_into_a_code_fence() -> None:
    text = "```\n- 2. A\n  - 3. B\n```\n"
    assert clean_in_place(text) == text


def test_spaced_dashes_are_a_thematic_break_not_a_list() -> None:
    text = "para\n\n- - -\n\nmore\n"
    assert clean_in_place(text) == text


def test_list_restore_is_idempotent() -> None:
    text = "- 2. A\n  - 3. B\n- 4. C\n"
    once = clean(text)
    assert clean(once) == once


def test_list_flatten_is_idempotent() -> None:
    text = "- A\n- B\n  - C\n- D\n"
    once = clean(text)
    assert clean(once) == once


def test_restored_numbered_list_with_child_is_idempotent() -> None:
    text = "- 2. A\n- 3. B\n  - detail\n- 4. C\n"
    once = clean(text)
    assert clean(once) == once


def test_bold_numbered_marker_glued_to_text_gets_a_space() -> None:
    # marker writes the item number as bold text without the space after it.
    assert clean_in_place("- **10.**ZENTRIX\n") == "- **10.** ZENTRIX\n"


def test_bold_numbered_marker_mid_sentence_is_left_alone() -> None:
    text = "- See section **10.**for details\n"
    assert clean_in_place(text) == text


def test_bold_numbered_marker_already_spaced_is_unchanged() -> None:
    text = "- **10.** ZENTRIX\n"
    assert clean_in_place(text) == text


def test_bold_numbered_marker_glued_to_punctuation_is_left_alone() -> None:
    text = "- **10.**, next\n"
    assert clean_in_place(text) == text


def test_bold_marker_space_fix_is_idempotent() -> None:
    text = "- **10.**ZENTRIX\n"
    once = clean(text)
    assert clean(once) == once


def test_bold_numbered_marker_in_indented_code_is_left_alone() -> None:
    text = "para\n\n    - **10.**ZENTRIX\n"
    assert clean_in_place(text) == text


def test_bold_numbered_marker_in_a_nested_list_item_gets_a_space() -> None:
    text = "- Parent\n    - **10.**ZENTRIX\n"
    assert clean_in_place(text) == "- Parent\n    - **10.** ZENTRIX\n"


# ---- stray bullet glyph -------------------------------------------------------


def test_bullet_glyph_trailing_a_list_item_is_dropped() -> None:
    # marker can put its bullet dingbat at the end of the item above.
    text = "- First item text ❚\n- Second item text\n"
    assert clean_in_place(text) == "- First item text\n- Second item text\n"


def test_bullet_glyph_alone_on_a_line_is_dropped() -> None:
    text = "- First item\n\n❚\n\n- Second item\n"
    assert clean_in_place(text) == "- First item\n\n- Second item\n"


def test_bullet_glyph_opening_a_heading_is_left_alone() -> None:
    text = "### ❚ Mounting Notes\n"
    assert clean_in_place(text) == text


def test_bullet_glyph_inside_a_table_cell_is_left_alone() -> None:
    text = "| A | ❚ one<br>❚ two |\n| --- | --- |\n| B | ❚ three |\n"
    assert clean_in_place(text) == (
        "| A | ❚ one<br>❚ two |\n|---|----------------|\n| B | ❚ three        |\n"
    )


def test_bullet_glyph_trailing_ordinary_prose_is_left_alone() -> None:
    text = "Ordinary prose line ❚\n"
    assert clean_in_place(text) == text


def test_bullet_glyph_drop_is_idempotent() -> None:
    text = "- First item text ❚\n- Second item text\n"
    once = clean(text)
    assert clean(once) == once


def test_bullet_glyph_in_indented_code_is_left_alone() -> None:
    text = "para\n\n    - literal ❚\n    ❚\n"
    assert clean_in_place(text) == text


# ---- literal bullet glyph opening a line ------------------------------------


def test_a_line_opened_with_a_literal_bullet_glyph_becomes_a_marker() -> None:
    text = "Lead-in line here.\n\n• KT 754\n• KT 755\n"
    assert clean_in_place(text) == "Lead-in line here.\n\n- KT 754\n- KT 755\n"


def test_an_indented_literal_bullet_glyph_is_promoted() -> None:
    text = "Lead-in line here.\n\n  • nested note text\n"
    assert clean_in_place(text) == "Lead-in line here.\n\n  - nested note text\n"


def test_a_bullet_glyph_mid_line_is_left_alone() -> None:
    text = "The list separator • is printed between the two field names.\n"
    assert clean_in_place(text) == text


def test_a_bullet_glyph_alone_on_a_line_is_left_alone() -> None:
    text = "First paragraph.\n\n•\n\nSecond paragraph.\n"
    assert clean_in_place(text) == "First paragraph.\n\n•\n\nSecond paragraph.\n"


def test_a_literal_bullet_glyph_in_a_code_fence_is_left_alone() -> None:
    text = "```\n• not a list here\n```\n"
    assert clean_in_place(text) == text


def test_a_bullet_glyph_opening_an_unbordered_table_row_is_left_alone() -> None:
    # A GFM table may omit border pipes, so its first cell opens the line.
    text = "• item | value\n--- | ---\n• other | 12\n"
    assert clean_in_place(text) == "• item  | value\n--------|------\n• other | 12\n"


def test_literal_bullet_promotion_is_idempotent() -> None:
    once = clean_in_place("Lead-in.\n\n• one item\n• two item\n")
    assert clean_in_place(once) == once
