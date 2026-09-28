"""Tests for the reporting pass.

`cleaning.findings` reports what deterministic cleaning must not decide. Most
tests read a clean through `_reported`, which writes each finding back above the
line it addresses, so one value states both the body and the report.
"""

from __future__ import annotations

import itertools
import time
from pathlib import Path

from raw2md.cleaner import CleanOptions, clean, clean_in_place, clean_with_report
from raw2md.cleaning import Finding, block_shows_defect
from raw2md.mdtext.formulas import is_valid_math
from raw2md.mdtext.loops import collapse_repetition_loops

from ._helpers import laid_out_table


def _findings(text: str, options: CleanOptions | None = None) -> list[Finding]:
    """The findings of one clean, in report order."""
    return list(clean_with_report(text, options).findings)


def _detail(finding: Finding) -> str:
    """A finding as the report writes it, without its address."""
    return f"{finding.kind} {finding.detail}".rstrip()


def _reported(text: str, options: CleanOptions | None = None) -> str:
    """The cleaned body with every finding written back above its own line.

    An address that drifted puts the comment over the wrong line.
    """
    result = clean_with_report(text, options)
    lines = result.body.split("\n")
    for finding in reversed(result.findings):
        lines.insert(finding.line - 1, f"<!-- finding {_detail(finding)} -->")
    return "\n".join(lines)


# ---- anchoring: hyphenation -------------------------------------------------


def test_hyphenation_is_anchored() -> None:
    assert _reported("inter-\nrupted word\n") == (
        "<!-- finding hyphenation -->\ninter-\nrupted word\n"
    )


def test_hyphenation_anchored_for_cyrillic() -> None:
    # Joined, so no `\n` escape touches a Cyrillic word (RUF001).
    body = "\n".join(["преры-", "вание", ""])
    assert _reported(body) == "<!-- finding hyphenation -->\n" + body


def test_hyphenation_skipped_when_next_line_uppercase() -> None:
    assert _reported("inter-\nRupted\n") == "inter-\nRupted\n"


def test_hyphenation_skipped_after_digit() -> None:
    # `5-` is not a split word; the char before the hyphen must be a letter.
    assert _reported("5-\nvalue\n") == "5-\nvalue\n"


def test_hyphenation_skipped_before_protected_zone() -> None:
    text = "word-\n```\ncode\n```\n"
    assert _reported(text) == text


def test_no_anchors_inside_code_fence() -> None:
    text = "```\nword-\nvalue\n```\n"
    assert _reported(text) == text


# ---- anchoring: hyphenation across a gap ------------------------------------


def test_hyphenation_gap_anchored_across_a_blank_line() -> None:
    # Joined, so no `\n` escape touches a Cyrillic word (RUF001).
    text = "\n".join(["Третий электромо-", "", "тор отличается.", ""])
    assert _reported(text) == ("<!-- finding hyphenation-gap blocks=1 -->\n" + text)


def test_hyphenation_gap_anchored_across_a_figure() -> None:
    text = "\n".join(
        ["Третий электромо-", "", "![](gear.png)", "", "тор отличается.", ""]
    )
    assert _reported(text) == ("<!-- finding hyphenation-gap blocks=2 -->\n" + text)


def test_hyphenation_gap_block_count_merges_figure_touching_continuation() -> None:
    # With no blank line, the figure and the continuation are one block for `post`.
    text = "\n".join(
        [
            "Третий электромо-",
            "",
            "![](gear.png)",
            "тор отличается.",
            "",
            "Unrelated paragraph.",
            "",
        ]
    )
    assert _reported(text) == ("<!-- finding hyphenation-gap blocks=1 -->\n" + text)


def test_hyphenation_gap_skipped_when_continuation_uppercase() -> None:
    text = "\n".join(["Третий электромо-", "", "Торий отличается.", ""])
    assert _reported(text) == text


def test_hyphenation_rejoin_across_exactly_the_search_bound() -> None:
    text = (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромо-\n"
        "\n\n\n\n"
        "тор отличается.\n"
    )
    assert clean_in_place(text) == (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромотор отличается.\n"
    )


def test_hyphenation_gap_skipped_past_the_search_bound() -> None:
    # The blank-run collapse still leaves one blank line.
    text = (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромо-\n"
        "\n\n\n\n\n"
        "тор отличается.\n"
    )
    assert clean_in_place(text) == (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромо-\n"
        "\n"
        "тор отличается.\n"
    )


def test_hyphenation_gap_not_anchored_before_protected_zone() -> None:
    text = "word-\n\n```\ncode\n```\n"
    assert _reported(text) == text


# ---- anchoring: flattened block ----------------------------------------------


def test_flattened_block_is_anchored() -> None:
    text = "Name\nAge\nCity\nJohn\n30\nNYC\n"
    assert _reported(text) == (
        "<!-- finding flattened-block lines=6 -->\nName\nAge\nCity\nJohn\n30\nNYC\n"
    )


def test_short_run_below_threshold_is_not_anchored() -> None:
    text = "Name\nAge\nCity\nJohn\n30\n"
    assert _reported(text) == text


def test_multi_line_display_formula_is_not_flattened() -> None:
    # Short rows between lone `$$` read as a crushed column by length alone.
    text = "$$\n\\begin{array}{cc}\na & b \\\\\nc & d\n\\end{array}\n$$\n"
    assert _reported(text) == text


def test_pipe_table_rows_are_not_flattened() -> None:
    text = (
        "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n| 7 | 8 |\n| 9 | 0 |\n"
    )
    assert _reported(text) == text


# ---- anchoring: broken formula -----------------------------------------------


def test_repetition_loop_is_anchored_and_trimmed() -> None:
    body = "Then $a_{1}" + "+a_{1}" * 7 + "$ ends the readable sentence here.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n"
        "Then $a_{1}+a_{1}$ ends the readable sentence here.\n"
    )


def test_runaway_math_loop_is_cut_to_one_copy() -> None:
    body = r"$$\eta = \eta_{I}" + r" \eta_{S}" * 338 + "$$\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n" + r"$$\eta = \eta_{I} \eta_{S}$$" + "\n"
    )


def test_long_looped_unit_is_cut_below_the_copy_bar() -> None:
    # A unit too long for the count bar; the byte bar catches it.
    head = r"F(u) = \frac{1}{b} \ln \left| u \right| + \sum_{k} c_{k} u^{k}"
    unit = (
        r" - \frac{1 \cdot 5}{3 \cdot 7 \cdot 9} \frac{u^{5}}{b^{5}}"
        r" + \frac{1 \cdot 5 \cdot 7}{3 \cdot 7 \cdot 9 \cdot 11} \frac{u^{7}}{b^{7}}"
        r" - \frac{1}{3} \ln \left| \frac{b}{u} \right| \ln \left| \frac{3b}{u} \right|"
    )
    assert len(unit) > 200  # past the period cap the copy count is read at
    assert _reported("$$" + head + unit * 5 + "$$\n") == (
        "<!-- finding broken-formula -->\n$$" + head + unit + "$$\n"
    )
    assert is_valid_math(head + unit)


def test_long_looped_unit_below_the_byte_bar_is_kept() -> None:
    unit = (
        r" + \frac{1 \cdot 5}{3 \cdot 7 \cdot 9} \frac{u^{5}}{b^{5}} \sin^{2} u"
        r" - \ln \left| \frac{b}{u} \right|"
    )
    assert 80 < len(unit) < 135
    body = "$$y = x" + unit * 3 + "$$\n"
    assert _reported(body) == body


def test_short_looped_unit_below_the_copy_bar_is_kept() -> None:
    unit = r" + \frac{x^{2}}{a^{2}} \cos^{2} \varphi"
    assert len(unit) < 80
    body = "$$y = x" + unit * 5 + "$$\n"
    assert _reported(body) == body


def test_a_long_unit_carrying_its_markup_late_is_still_cut() -> None:
    unit = " " + " ".join(f"x{number}" for number in range(100, 160)) + r" \alpha"
    assert 200 < len(unit) < 400  # past the period cap, inside the long branch's
    line = "$$y = 1" + unit * 3 + "$$"
    assert collapse_repetition_loops(line) == "$$y = 1" + unit + "$$"


def test_a_long_plain_run_is_answered_without_rescanning_it() -> None:
    # The bound separates a linear walk from a rescan, not one machine from another.
    line = "$" + "0" * 20000 + "$"
    started = time.monotonic()
    assert collapse_repetition_loops(line) == line
    assert time.monotonic() - started < 5


def test_series_written_out_term_by_term_is_kept() -> None:
    terms = "".join(
        rf" + \frac{{1 \cdot {n}}}{{2 \cdot {n + 1} \cdot {n + 2}}} "
        rf"\frac{{x^{{{n}}}}}{{a^{{{n}}}}} \cos^{{{n}}} \varphi"
        for n in range(1, 9)
    )
    assert len(terms) > 3 * 81
    body = "$$y = x" + terms + "$$\n"
    assert _reported(body) == body


def test_valid_formula_is_not_anchored_broken() -> None:
    body = "A series $x^1 + x^2 + x^3 + x^4 + x^5 + x^6 + x^7 + x^8$ reads fine.\n"
    assert _reported(body) == body


def test_loop_in_prose_is_trimmed_without_an_anchor() -> None:
    # Post has no class for a prose loop, so no anchor.
    body = "word " + "ha ha " * 8 + "in an otherwise ordinary sentence.\n"
    assert _reported(body) == "word ha in an otherwise ordinary sentence.\n"


def test_loop_in_a_table_cell_is_trimmed() -> None:
    body = "| Index | " + "the contract of " * 63 + "|\n"
    assert _reported(body) == "| Index | the contract of |\n"


def test_repeated_cells_are_not_trimmed() -> None:
    # The unit spans a cell separator.
    body = "| aa | aa | aa | aa | aa | aa | aa |\n"
    assert _reported(body) == body


def test_repeated_numbers_are_not_trimmed() -> None:
    body = "| 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 |\n"
    assert _reported(body) == body
    assert _reported("Row 12 12 12 12 12 12 12 12 of readings.\n") == (
        "Row 12 12 12 12 12 12 12 12 of readings.\n"
    )


def test_repetition_inside_inline_code_is_not_trimmed() -> None:
    body = "Prints `ha ha ha ha ha ha ha ha ` in a loop.\n"
    assert _reported(body) == body


def test_repetition_inside_a_link_target_is_not_trimmed() -> None:
    for body in (
        "[ref](https://example.com/abcabcabcabcabcabc)\n",
        "![](media/abcabcabcabcabcabc.png)\n",
        "See https://example.com/abcabcabcabcabcabc and further.\n",
        '<img src="media/abcabcabcabcabcabc.png" alt="" />\n',
        "[ref]: https://example.com/abcabcabcabcabcabc\n",
        # A relative reference target has no scheme to recognize it by.
        "[ref]: media/abcabcabcabcabcabcabcabcabcabc.png\n",
        "Write to abcabcabcabcabcabc@example.com for contact.\n",
    ):
        assert _reported(body) == body


def test_repetition_in_a_protected_zone_is_not_trimmed() -> None:
    body = "```\n" + "ha " * 10 + "\n```\n"
    assert _reported(body) == body


def test_repeated_identifier_on_dollar_line_is_not_anchored() -> None:
    # `$` as currency; the underscore makes the unit look like LaTeX.
    body = "Use $HOME and " + "foo_bar" * 8 + " here.\n"
    assert _reported(body) == body


def test_repeated_phrase_below_the_prose_bar_is_kept() -> None:
    body = " AND ".join(["THIS CLAUSE RUNS ON"] * 8) + "\n"
    assert _reported(body) == body


def test_truncated_math_tail_loop_is_anchored_and_trimmed() -> None:
    # A loop cut mid-token leaves its closing `$` looking escaped.
    body = "Or $ds_{ij}" + "^{ e}+ds_{ij}" * 8 + "^{\\$\n"
    assert _reported(body) == "<!-- finding broken-formula -->\nOr\n"


def test_a_trimmed_loop_is_reported_by_the_pass_that_cut_it() -> None:
    body = "Then $a_{1}" + "+a_{1}" * 7 + "$ ends the readable sentence here.\n"
    once = clean(body)
    assert clean(once) == once
    assert [_detail(f) for f in _findings(body)] == ["broken-formula"]
    assert _findings(once) == []


def test_repeated_span_run_is_anchored_and_trimmed() -> None:
    # Each copy carries its own `$`, so neither the prose nor the math branch sees it.
    body = "Then " + " ".join(["$v_2$"] * 340) + " closes the readable sentence.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen $v_2$ closes the readable sentence.\n"
    )
    once = clean(body)
    assert clean(once) == once


def test_repeated_span_cycle_is_trimmed_to_one_copy() -> None:
    body = "Then " + " ".join(["$a_1$", "$b_1$"] * 8) + " closes the sentence.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen $a_1$ $b_1$ closes the sentence.\n"
    )


def test_repeated_span_across_prose_is_not_trimmed() -> None:
    # Observed loops of this shape run tens to hundreds of copies.
    body = " ".join([r"a gap of $\mu$ m"] * 8) + " ends this readable line.\n"
    assert _reported(body) == body


def test_repeated_spans_split_by_one_separator_are_trimmed() -> None:
    # The whitespace around the mark varies from copy to copy.
    body = "Then " + " ;  ".join(["$X_1$"] * 149) + " ; closes the sentence.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen $X_1$ ; closes the sentence.\n"
    )


def test_repeated_spans_divided_by_a_word_are_trimmed() -> None:
    body = "Then " + " word ".join(["$f(x)$"] * 82) + " word closes the line.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen $f(x)$ word closes the line.\n"
    )
    assert clean(body).count("$") == body.count("$") - 2 * 81


def test_repeated_spans_divided_by_a_mark_and_a_word_are_trimmed() -> None:
    body = "Then " + " ;  word ".join(["$v$"] * 30) + " ; word ends the line.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen $v$ ; word ends the line.\n"
    )


def test_repeated_spans_split_by_a_separator_below_the_bar_are_kept() -> None:
    body = "Then " + ", ".join(["$v_2$"] * 8) + " closes the readable sentence.\n"
    assert _reported(body) == body


def test_repeated_spans_split_by_changing_connectors_are_not_trimmed() -> None:
    body = "Then " + " and $v_2$, ".join(["$v_2$"] * 8) + " closes the sentence.\n"
    assert _reported(body) == body


def test_a_printed_row_of_one_value_and_its_unit_is_kept() -> None:
    body = "Then " + " mm ".join(["$5$"] * 10) + " mm ends this readable line.\n"
    assert _reported(body) == body


def test_repeated_spans_divided_by_a_clause_are_not_trimmed() -> None:
    body = "Then " + " is the same as the ".join(["$v_2$"] * 30) + " ends here.\n"
    assert _reported(body) == body


def test_a_table_row_of_repeated_value_cells_keeps_them() -> None:
    header = "| " + " | ".join(f"c{index}" for index in range(30)) + " |"
    delimiter = "|" + "|".join(["---"] * 30) + "|"
    row = "| " + " | ".join(["$0$"] * 30) + " |"
    assert clean(f"{header}\n{delimiter}\n{row}\n").count("$0$") == 30


def test_repeated_span_run_below_the_bar_is_kept() -> None:
    body = "Then " + " ".join(["$v_2$"] * 5) + " closes the readable sentence.\n"
    assert _reported(body) == body


def test_repeated_bare_value_spans_are_not_trimmed() -> None:
    body = "Then " + " ".join(["$0$"] * 8) + " closes the readable sentence.\n"
    assert _reported(body) == body


def test_repeated_bare_value_spans_past_the_plain_bar_are_trimmed() -> None:
    body = "Then " + " ".join(["$v(0)$"] * 290) + " closes the sentence.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen $v(0)$ closes the sentence.\n"
    )


def test_a_trimmed_span_loop_takes_the_whole_cycle_off_the_line() -> None:
    body = "Then $a_1$ " + " ".join(["$b_2$"] * 40) + " ends $c_3$ here.\n"
    assert clean(body).count("$") == body.count("$") - 2 * 39


def test_repeated_span_run_held_apart_by_a_non_breaking_space_is_trimmed() -> None:
    body = "Then " + "\u00a0".join(["$v_2$"] * 8) + " closes the sentence.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen $v_2$ closes the sentence.\n"
    )


def test_repeated_span_run_inside_inline_code_is_not_trimmed() -> None:
    # The mask must not make spans standing apart look back to back.
    quoted = "`" + " ".join(["$v_2$"] * 8) + "`"
    assert _reported(f"Writes {quoted} in the readable sentence.\n") == (
        f"Writes {quoted} in the readable sentence.\n"
    )
    apart = " ".join(["$v_2$ `x`"] * 8) + " ends this readable line.\n"
    assert _reported(apart) == apart


# ---- runs of identical blocks and lines --------------------------------------


def test_run_of_identical_blocks_is_cut_to_one_copy() -> None:
    span = "$$S_{I}$$"
    assert clean("\n\n".join([span] * 254) + "\n") == span + "\n"


def test_run_of_identical_lines_is_cut_to_one_copy() -> None:
    line = "$v_{i+1}$"
    assert clean("\n".join([line] * 203) + "\n") == line + "\n"


def test_two_identical_blocks_are_kept() -> None:
    body = "Pneumatic feeders and gates\n\nPneumatic feeders and gates\n"
    assert clean(body) == body


def test_two_identical_lines_are_kept() -> None:
    body = "Pneumatic feeders and gates\nPneumatic feeders and gates\n"
    assert clean(body) == body


def test_identical_blocks_across_prose_are_kept() -> None:
    caption = "Fig. 4. The bearing assembly"
    body = "\n\n".join(
        [caption, "The shaft turns in it.", caption, "It holds.", caption]
    )
    assert clean(body + "\n") == body + "\n"


def test_repeated_table_row_is_kept() -> None:
    rows = ["| Gap | Limit |", *["| 0.02 | 0.02 |"] * 12]
    body = laid_out_table(*rows)
    assert clean(body) == body


def test_a_cut_run_leaves_the_block_it_stood_in_whole() -> None:
    copy = "The pressure holds at the rated value.\n"
    body = (
        "A paragraph opens the section here.\n" + copy * 4 + "It closes after that.\n"
    )
    assert clean(body) == (
        "A paragraph opens the section here.\n" + copy + "It closes after that.\n"
    )


def test_a_run_inside_a_protected_zone_is_not_cut() -> None:
    body = "```\n" + "print(value)\n" * 6 + "```\n"
    assert clean(body) == body


def test_repeated_rows_of_a_multiline_formula_are_kept() -> None:
    row = "1 & 2 \\\\\n"
    body = "$$\\begin{bmatrix}\n" + row * 3 + "3 & 4\n\\end{bmatrix}$$\n"
    assert clean(body) == body


def test_a_run_beside_a_multiline_formula_is_still_cut() -> None:
    copy = "The pressure holds at the rated value.\n"
    formula = "$$\\begin{bmatrix}\n1 & 2 \\\\\n3 & 4\n\\end{bmatrix}$$\n"
    assert clean(copy * 4 + formula) == copy + formula


def test_a_finding_under_a_cut_run_moves_with_its_line(tmp_path: Path) -> None:
    # The cut moves lines below the run up.
    options = CleanOptions(base_dir=tmp_path)
    copy = "The pressure holds at the rated value.\n"
    assert _reported(copy * 3 + "![](media/x.png)\n", options) == (
        copy + "<!-- finding broken-image src=media/x.png -->\n" + "![](media/x.png)\n"
    )


# The cut leaves the opening bracket unclosed.
_TENSOR_LOOP = r"$$[\gamma_{xz}, \gamma_{yz}" + r", \gamma_{xz}" * 8 + "$$"

_INLINE_LOOP = r"$a_{1}[x" + r"+a_{1}[x" * 7 + "$"


def test_loop_fragment_is_dropped_and_the_loss_is_reported() -> None:
    result = clean_with_report(_TENSOR_LOOP + "\n")
    assert result.body == ""
    assert result.findings == (Finding("broken-formula", 1),)


def test_whole_formula_left_by_a_loop_is_kept() -> None:
    body = r"$$\eta = \eta_{I}" + r" \eta_{S}" * 8 + "$$\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n" + r"$$\eta = \eta_{I} \eta_{S}$$" + "\n"
    )


def test_printed_bracket_inside_a_text_macro_does_not_read_as_a_group() -> None:
    body = r"$$\text{(}a_{1}" + r"+a_{1}" * 7 + "$$\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n" + r"$$\text{(}a_{1}+a_{1}$$" + "\n"
    )


def test_invisible_right_delimiter_does_not_read_as_an_open_group() -> None:
    body = r"$$\left[ x \right. + a_{1}" + r"+a_{1}" * 7 + "$$\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n"
        r"$$\left[ x \right. + a_{1}+a_{1}$$"
        "\n"
    )


def test_dropped_fragment_leaves_the_prose_of_its_line() -> None:
    body = f"Then {_INLINE_LOOP} ends the readable sentence here.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen ends the readable sentence here.\n"
    )


def test_a_sound_formula_beside_a_dropped_fragment_survives() -> None:
    body = f"Then $E = mc^{{2}}$ and {_INLINE_LOOP} closes the sentence.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n"
        r"Then $E = mc^{2}$ and closes the sentence."
        "\n"
    )


def test_dropped_fragment_leaves_no_space_before_punctuation() -> None:
    body = f"Then {_INLINE_LOOP}, and the sentence goes on here.\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\nThen, and the sentence goes on here.\n"
    )


def test_dropped_fragment_keeps_the_indent_of_its_line() -> None:
    body = f"- item\n  - {_INLINE_LOOP} tail of the nested entry\n"
    assert _reported(body) == (
        "- item\n<!-- finding broken-formula -->\n  - tail of the nested entry\n"
    )


def test_unclosed_loop_residue_is_dropped_with_its_delimiter() -> None:
    # A lone `$` left behind would pair with the next formula.
    body = r"See $\alpha_{1}" + r"+\alpha_{1}" * 7 + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\nSee\n"


def test_dropped_fragment_keeps_its_table_row_intact() -> None:
    assert _reported(f"| Index | {_INLINE_LOOP} |\n") == (
        "<!-- finding broken-formula -->\n| Index | |\n"
    )


def test_dropped_fragment_is_idempotent() -> None:
    once = clean(_TENSOR_LOOP + "\n")
    assert _reported(once) == once


def test_dropped_fragment_leaves_no_blank_run_in_the_result() -> None:
    # The final write strips the anchor; no blank run may remain.
    body = f"The strain tensor reads:\n\n{_TENSOR_LOOP}\n\nThe text goes on here.\n"
    assert clean(body) == "The strain tensor reads:\n\nThe text goes on here.\n"


def test_unclosed_math_environment_is_anchored() -> None:
    body = r"$$\begin{array}{cccc}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_balanced_math_environment_is_not_anchored() -> None:
    body = r"$$\begin{array}{cc}a & b\end{array}$$" + "\n"
    assert _reported(body) == body


def test_nested_math_environments_are_treated_as_pairs() -> None:
    body = r"$$\begin{A}\begin{B}x\end{B}\end{A}$$" + "\n"
    assert _reported(body) == body


def test_crossed_math_environments_are_anchored() -> None:
    body = r"$$\begin{A}\begin{B}x\end{A}\end{B}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_unclosed_math_environment_report_is_idempotent() -> None:
    body = r"$$\begin{array}{cccc}$$" + "\n"
    once = clean(body)
    assert _reported(once) == _reported(body)


def test_unclosed_environment_inside_inline_code_is_not_anchored() -> None:
    body = "Example `" + r"$$\begin{array}{c}$$" + "` here.\n"
    assert _reported(body) == body


def test_multiline_display_formula_opening_line_is_not_anchored() -> None:
    # pandoc splits a matrix over several lines; the paragraph balances.
    body = "\n".join(
        [
            r"$$\left\{ \begin{matrix}",
            r"\frac{{\partial w}_{z}}{\partial z} = 0 \\",
            r"\end{matrix} \right.\  \rightarrow \left\{ \begin{array}{r} a \\ "
            r"\end{array} \right.$$",
            "",
        ]
    )
    assert _reported(body) == body


def test_multiline_display_formula_stays_unreported_on_a_second_pass() -> None:
    body = "\n".join([r"$$\begin{matrix}", r"a & b \\", r"\end{matrix}$$", ""])
    once = clean(body)
    assert _reported(once) == body


def test_single_line_unclosed_environment_still_anchored_beside_multiline() -> None:
    body = r"$$\begin{array}{cccc}$$" + "\nA readable sentence follows here.\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_display_formula_that_never_closes_is_still_anchored() -> None:
    body = "\n".join([r"$$\begin{array}{cccc}", r"a & b \\", r"c & d", ""])
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_column_spec_repetition_loop_is_anchored() -> None:
    # Braces and `\end` balance; only the position in the argument shows the loop.
    body = r"$$\begin{array}{" + "c" * 24 + r"} a \end{array}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_column_spec_loop_after_a_vertical_rule_is_anchored() -> None:
    body = r"$$\begin{array}{|" + "c" * 24 + r"} a \end{array}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_column_spec_loop_after_a_position_argument_is_anchored() -> None:
    body = r"$$\begin{array}[t]{" + "c" * 24 + r"} a \end{array}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_column_spec_loop_after_a_braced_column_type_is_anchored() -> None:
    # A naive capture would stop at the `}` of `p{1cm}`.
    body = r"$$\begin{array}{p{1cm}" + "c" * 24 + r"} a \end{array}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_wide_but_plausible_column_spec_is_not_anchored() -> None:
    body = r"$$\begin{array}{" + "c" * 12 + r"} a \end{array}$$" + "\n"
    assert _reported(body) == body


def test_alternating_rules_do_not_form_a_column_spec_loop() -> None:
    body = r"$$\begin{array}{" + "c|" * 20 + r"} a \end{array}$$" + "\n"
    assert _reported(body) == body


def test_long_at_separator_is_not_a_column_spec_loop() -> None:
    body = r"$$\begin{array}{c@{" + "." * 24 + r"}c} a \end{array}$$" + "\n"
    assert _reported(body) == body


def test_at_separator_spelling_out_a_column_letter_is_not_a_loop() -> None:
    body = r"$$\begin{array}{c@{" + "c" * 22 + r"}c} a \end{array}$$" + "\n"
    assert _reported(body) == body


def test_column_spec_loop_before_an_at_separator_is_still_anchored() -> None:
    body = r"$$\begin{array}{" + "c" * 24 + r"@{sep}c} a \end{array}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_column_spec_loop_after_an_at_separator_is_still_anchored() -> None:
    body = r"$$\begin{array}{c@{sep}" + "c" * 24 + r"} a \end{array}$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_column_spec_repetition_loop_cut_is_idempotent() -> None:
    body = r"$$\begin{array}{" + "c" * 24 + r"} a \end{array}$$" + "\n"
    once = clean(body)
    assert clean(once) == once


def test_a_truncated_argument_with_no_head_is_dropped_without_an_anchor() -> None:
    body = r"$$\begin{array}{cccc$$" + "\n"
    assert _reported(body) == ""


def test_a_head_before_an_unclosed_environment_survives_with_an_anchor() -> None:
    body = r"$$\widetilde{C}_o(s) = \begin{cases}$$" + "\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n" + r"$$\widetilde{C}_o(s) =$$" + "\n"
    )


def test_a_truncated_argument_with_a_head_keeps_the_head_and_an_anchor() -> None:
    body = r"$$a = b \begin{array}{cccc$$" + "\n"
    assert _reported(body) == (
        "<!-- finding broken-formula -->\n" + r"$$a = b$$" + "\n"
    )


def test_row_content_after_a_closed_argument_is_left_for_the_anchor() -> None:
    # The spec closes; the unbalanced brace is in the cut-off row.
    body = r"$$\begin{array}{c}{x$$" + "\n"
    assert _reported(body) == "<!-- finding broken-formula -->\n" + body


def test_a_truncated_optional_position_argument_is_dropped_too() -> None:
    body = r"$$\begin{array}[t$$" + "\n"
    assert _reported(body) == ""


def test_a_closed_optional_argument_with_a_truncated_column_spec_is_dropped() -> None:
    body = r"$$\begin{array}[t]{cccc$$" + "\n"
    assert _reported(body) == ""


def test_resolved_environment_drop_is_idempotent() -> None:
    body = r"$$\begin{array}{cccc$$" + "\n"
    once = clean(body)
    assert clean(once) == once


def test_resolved_environment_head_is_reported_by_the_pass_that_cut_it() -> None:
    body = r"$$\widetilde{C}_o(s) = \begin{cases}$$" + "\n"
    once = clean(body)
    assert clean(once) == once
    assert [_detail(f) for f in _findings(body)] == ["broken-formula"]
    assert _findings(once) == []


def test_trimmed_prose_loop_is_idempotent() -> None:
    body = "| Index | " + "the contract of " * 63 + "|\n"
    once = clean(body)
    assert clean(once) == once


# ---- anchoring: a run of letters spaced apart --------------------------------

_SPACED_WITNESS = "The identical case matters here.\nThe identical case again.\n"


def test_letter_spacing_the_body_cannot_spell_is_anchored() -> None:
    body = "All the i d e n t i c a l values here.\n"
    assert _reported(body) == "<!-- finding letter-spacing -->\n" + body


def test_letter_spacing_the_body_attests_is_joined_and_not_anchored() -> None:
    body = _SPACED_WITNESS + "All the i d e n t i c a l values here.\n"
    assert _findings(body) == []


def test_letter_spacing_in_a_title_is_anchored() -> None:
    body = "## C O N T E N T S\n"
    assert _reported(body) == "<!-- finding letter-spacing -->\n" + body


def test_a_formulas_symbols_are_no_letter_spacing() -> None:
    body = "The values $a b c$ equal one.\n"
    assert _findings(body) == []


# A one-letter conjunction as a word of the prose, designations inside formulas.
_SPACING_WITNESS = "".join(
    f"Опыт {n} и опыт {n} описаны формулой $A_{n} B_{n} x_{n} y_{n}$.\n"
    for n in range(1, 25)
)


def test_the_witness_body_reports_nothing_of_its_own() -> None:
    assert _findings(_SPACING_WITNESS) == []


def test_two_designations_joined_by_a_conjunction_are_no_letter_spacing() -> None:
    body = _SPACING_WITNESS + "События A и B независимы.\n"
    assert _findings(body) == []


def test_an_axis_pair_is_no_letter_spacing() -> None:
    body = _SPACING_WITNESS + "Проекции на оси x и y равны.\n"
    assert _findings(body) == []


# A three-letter word and a longer one, set letter by letter in the prose script.
_SPACED_SHORT = "Здесь м и р описан.\n"  # noqa: RUF001 -- Cyrillic body
_SPACED_LONG = "Все р е з у л ь т а т ы совпали.\n"  # noqa: RUF001 -- Cyrillic body


def test_a_three_letter_word_outside_the_formulas_alphabet_is_anchored() -> None:
    assert [_detail(f) for f in _findings(_SPACING_WITNESS + _SPACED_SHORT)] == [
        "letter-spacing"
    ]


def test_a_spaced_word_beside_that_witness_is_still_anchored() -> None:
    assert [_detail(f) for f in _findings(_SPACING_WITNESS + _SPACED_LONG)] == [
        "letter-spacing"
    ]


# ---- anchoring: broken image link --------------------------------------------


def test_broken_image_is_anchored(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path)
    assert _reported("![](media/x.png)\n", options) == (
        "<!-- finding broken-image src=media/x.png -->\n![](media/x.png)\n"
    )


def test_existing_image_is_not_anchored(tmp_path: Path) -> None:
    (tmp_path / "x.png").write_bytes(b"data")
    options = CleanOptions(base_dir=tmp_path)
    assert _reported("![](x.png)\n", options) == "![](x.png)\n"


def test_remote_image_is_not_anchored(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path)
    assert _reported("![](http://example.com/x.png)\n", options) == (
        "![](http://example.com/x.png)\n"
    )


def test_image_check_skipped_without_base_dir() -> None:
    assert _reported("![](media/x.png)\n") == "![](media/x.png)\n"


def test_encoded_existing_image_is_not_anchored(tmp_path: Path) -> None:
    # The target is percent-encoded; the file name on disk has a space.
    (tmp_path / "x y.png").write_bytes(b"data")
    options = CleanOptions(base_dir=tmp_path)
    assert _reported("![](x%20y.png)\n", options) == "![](x%20y.png)\n"


def test_traversal_target_is_not_anchored(tmp_path: Path) -> None:
    # Containment is checked on the resolved path; the escaped file exists.
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    (tmp_path / "outside.png").write_bytes(b"data")
    options = CleanOptions(base_dir=base_dir)
    text = "![](../outside.png)\n"
    assert _reported(text, options) == text


def test_encoded_drive_letter_target_is_not_anchored(tmp_path: Path) -> None:
    # The target decodes to an absolute Windows path.
    options = CleanOptions(base_dir=tmp_path)
    text = "![](C%3A%5Ctemp%5Cx.png)\n"
    assert _reported(text, options) == text


def test_encoded_missing_image_is_anchored(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path)
    assert _reported("![](media/x%20y.png)\n", options) == (
        "<!-- finding broken-image src=media/x%20y.png -->\n![](media/x%20y.png)\n"
    )


# ---- --disable-image-extraction ----------------------------------------------


def test_missing_image_removed_when_extraction_disabled(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    text = "before\n\n![](media/x.png)\n\nafter\n"
    assert _reported(text, options) == "before\n\nafter\n"


def test_meaningful_alt_becomes_a_paragraph(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    assert _reported("![Figure 1](media/x.png)\n", options) == "Figure 1\n"


def test_existing_image_kept_under_disable_flag(tmp_path: Path) -> None:
    (tmp_path / "x.png").write_bytes(b"data")
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    assert _reported("![](x.png)\n", options) == "![](x.png)\n"


def test_encoded_existing_image_kept_under_disable_flag(tmp_path: Path) -> None:
    (tmp_path / "x y.png").write_bytes(b"data")
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    assert _reported("![](x%20y.png)\n", options) == "![](x%20y.png)\n"


def test_missing_html_image_removed_whole_when_extraction_disabled(
    tmp_path: Path,
) -> None:
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    img = '<img src="media/x.png" style="width:5.7in;height:2.4in" />'
    text = f"before\n\n{img}\n\nafter\n"
    assert _reported(text, options) == "before\n\nafter\n"


def test_html_image_inside_text_leaves_the_text(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    text = '<img src="media/x.png" style="width:5in" />Figure 1 Site map\n'
    assert _reported(text, options) == "Figure 1 Site map\n"


def test_html_image_alt_becomes_a_paragraph(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    text = '<img src="media/x.png" alt="Flow &amp; stock" style="width:5in" />\n'
    assert _reported(text, options) == "Flow & stock\n"


def test_existing_html_image_kept_under_disable_flag(tmp_path: Path) -> None:
    (tmp_path / "x.png").write_bytes(b"data")
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    text = '<img src="x.png" style="width:5in" />\n'
    assert _reported(text, options) == text


def test_missing_html_image_is_anchored(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path)
    text = '<img src="media/x.png" style="width:5in" />\n'
    assert _reported(text, options) == (
        f"<!-- finding broken-image src=media/x.png -->\n{text}"
    )


# ---- the shape an anchor type names ------------------------------------------

CRUSHED_INDEX = (
    "K Keyway, 86 L Lever arm, 119 Link A, 119 Link B, 119 Load path, 78 "
    "Lock nuts, 92 Lug plate, 63 M Motor mount, 9 Mesh chart, 131"
)


def test_split_word_shows_the_hyphenation_shape() -> None:
    assert block_shows_defect("hyphenation", ["a word bro-", "ken by a hyphen."])


def test_paragraph_without_a_hyphen_shows_no_hyphenation() -> None:
    # A reader of the source page often calls an ordinary paragraph a hyphen break.
    assert not block_shows_defect(
        "hyphenation", ["An ordinary paragraph without hyphens."]
    )


def test_hyphen_on_the_last_line_of_a_block_shows_nothing() -> None:
    assert not block_shows_defect("hyphenation", ["the line ends with a hyphen-"])


def test_column_run_shows_the_flattened_shape() -> None:
    assert block_shows_defect(
        "flattened-block", ["Name", "Age", "City", "John", "30", "NYC"]
    )


def test_short_run_shows_no_flattened_shape() -> None:
    assert not block_shows_defect("flattened-block", ["Name", "Age", "City", "John"])


def test_crushed_row_shows_the_flattened_shape() -> None:
    assert block_shows_defect("flattened-block", [CRUSHED_INDEX])


def test_intact_contents_list_shows_no_flattened_shape() -> None:
    assert not block_shows_defect(
        "flattened-block",
        [
            "- 1 Introduction 5",
            "- 2 Overview 8",
            "- 3 Installation 14",
            "- 4 Setup 21",
            "- 5 Operation 30",
            "- 6 Maintenance 42",
        ],
    )


def test_lone_heading_shows_no_flattened_shape() -> None:
    assert not block_shows_defect("flattened-block", ["## Design"])


def test_display_formula_with_its_number_shows_no_flattened_shape() -> None:
    assert not block_shows_defect(
        "flattened-block",
        [
            r"$$W_1 = \frac{1}{3}(\beta_1 + \beta_2 t)(J_1 - 2) "
            r"+ \frac{1}{3}(\beta_3 + \beta_4 t)(J_2 - 2) "
            r"- \frac{1}{3}q(J_3 - 1)$$",
            "(15)",
        ],
    )


def test_figure_line_shows_no_broken_formula_shape() -> None:
    assert not block_shows_defect("broken-formula", ["![](doc/_page_7_Picture_2.jpeg)"])


def test_contents_row_shows_no_broken_formula_shape() -> None:
    assert not block_shows_defect(
        "broken-formula", ["| 3.1.5 | Loads<br>3-57 | 3.4 | Fittings<br>3-112 |"]
    )


def test_math_span_shows_the_broken_formula_shape() -> None:
    assert block_shows_defect(
        "broken-formula", [r"Stiffness $c = F / \delta$ of the joint."]
    )


def test_multiline_display_formula_shows_the_broken_formula_shape() -> None:
    assert block_shows_defect(
        "broken-formula",
        ["$$", r"\begin{array}{c}", "a + b", r"\end{array}", "$$"],
    )


def test_raw_latex_span_shows_the_broken_formula_shape() -> None:
    assert block_shows_defect(
        "broken-formula", [r"Stiffness \(c = F / \delta\) of the joint."]
    )


def test_multiline_raw_latex_display_shows_the_broken_formula_shape() -> None:
    assert block_shows_defect("broken-formula", [r"\[", "a + b", r"\]"])


def test_dollar_inside_inline_code_shows_no_broken_formula_shape() -> None:
    assert not block_shows_defect("broken-formula", ["The path comes from `$PATH`."])


def test_table_row_shows_the_broken_table_shape() -> None:
    assert block_shows_defect("broken-table", ["| A | B |", "| --- | --- |", "| x |"])


def test_crushed_row_shows_the_broken_table_shape() -> None:
    assert block_shows_defect("broken-table", [CRUSHED_INDEX])


def test_caption_shows_no_broken_table_shape() -> None:
    assert not block_shows_defect("broken-table", ["Table 2. Estimated values"])


def test_figure_line_shows_no_broken_table_shape() -> None:
    assert not block_shows_defect("broken-table", ["![](doc/_page_9_Picture_4.jpeg)"])


def test_escaped_pipe_shows_no_broken_table_shape() -> None:
    assert not block_shows_defect("broken-table", [r"The notation A \| B in the text."])


def test_type_with_no_readable_shape_passes() -> None:
    assert block_shows_defect("broken-image", ["An ordinary line."])


def test_cleaner_findings_satisfy_their_own_shape() -> None:
    text = "para-\ngraph word\n\nName\nAge\nCity\nJohn\n30\nNYC\n"
    lines = clean(text).split("\n")
    found = _findings(text)
    assert [f.kind for f in found] == ["hyphenation", "flattened-block"]
    for finding in found:
        block = list(
            itertools.takewhile(lambda line: line.strip(), lines[finding.line - 1 :])
        )
        assert block_shows_defect(finding.kind, block)


# ---- anchoring: protected zones and idempotency ------------------------------


def test_anchor_placed_after_front_matter() -> None:
    text = "---\nraw2md_version: 0.1.0\n---\nword-\nvalue\n"
    assert _reported(text) == (
        "---\nraw2md_version: 0.1.0\n---\n<!-- finding hyphenation -->\nword-\nvalue\n"
    )


def test_clean_leaves_well_formed_text_untouched() -> None:
    text = "Hello world.\n\nSecond paragraph.\n"
    assert _reported(text) == text


def test_clean_is_idempotent() -> None:
    text = (
        "para-\ngraph word\n\n"
        "| A | B |\n|---|---|\n| 1 |\n\n"
        "one\ntwo\nthree\nfour\nfive\nsix\n"
    )
    once = clean(text)
    assert clean(once) == once


def test_a_second_clean_reports_the_same_defects() -> None:
    text = (
        "para-\ngraph word\n\n"
        "| A | B |\n|---|---|\n| 1 |\n\n"
        "one\ntwo\nthree\nfour\nfive\nsix\n"
    )
    assert [_detail(f) for f in _findings(text)] == [
        "hyphenation",
        "broken-table expected=2 got=1",
        "flattened-block lines=6",
    ]
    assert _findings(clean(text)) == _findings(text)


def test_removed_image_is_idempotent(tmp_path: Path) -> None:
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    text = "before\n\n![](media/x.png)\n\nafter\n"
    once = clean(text, options)
    assert _reported(once, options) == once


def test_promoted_caption_is_reported_consistently(tmp_path: Path) -> None:
    # The detectors run on the text after the image removal.
    options = CleanOptions(base_dir=tmp_path, disable_image_extraction=True)
    text = "one\ntwo\nthree\nfour\nfive\n![Cap](media/x.png)\n"
    assert _reported(text, options) == (
        "<!-- finding flattened-block lines=6 -->\none\ntwo\nthree\nfour\nfive\nCap\n"
    )
    once = clean(text, options)
    assert _reported(once, options) == _reported(text, options)
