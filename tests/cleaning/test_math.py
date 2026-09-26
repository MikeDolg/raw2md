"""Tests for the formula rules.

`cleaning.math` repairs the shape a converter gave a formula, never the
recognition inside it.
"""

from __future__ import annotations

from raw2md.cleaner import clean, clean_in_place
from raw2md.cleaning.math import _DISPLAY_MATH_RE, _PROSE_SHARE_MIN
from raw2md.mdtext.formulas import is_valid_math
from raw2md.mdtext.math_spans import math_span_content, math_spans
from raw2md.mdtext.pages import page_mark

# ---- display math and setext -------------------------------------------------


def test_keeps_display_math_delimiters() -> None:
    # `$$` on its own line bounds a display formula; it is structure, not junk.
    text = "Paragraph.\n\n$$\nE = mc^2\n$$\n"
    assert clean_in_place(text) == text


def test_keeps_setext_h1_underline() -> None:
    # `====` directly under a text line is a setext H1 underline, not junk.
    assert clean_in_place("Title\n====\n\nBody.\n") == "Title\n====\n\nBody.\n"


def test_keeps_setext_h2_underline() -> None:
    assert clean_in_place("Sub\n----\n\nBody.\n") == "Sub\n----\n\nBody.\n"


def test_drops_setext_run_under_heading() -> None:
    # An ATX heading is a complete block, so the run below it is stray junk.
    assert clean_in_place("# Title\n====\n\nBody.\n") == "# Title\n\nBody.\n"


def test_clean_is_idempotent_on_math_and_setext() -> None:
    text = "Title\n====\n\n$$\nE = mc^2\n$$\n\nBody.\n"
    once = clean(text)
    assert clean(once) == once


# ---- math normalization for KaTeX ---------------------------------------------


def test_mbox_becomes_text_in_inline_math() -> None:
    text = r"$P_{\mbox{\tiny MAX}}$" + "\n"
    assert clean_in_place(text) == r"$P_{\text{\tiny MAX}}$" + "\n"


def test_mbox_becomes_text_in_display_math() -> None:
    text = r"$$P_{\mbox{\tiny MAX}}$$" + "\n"
    assert clean_in_place(text) == r"$$P_{\text{\tiny MAX}}$$" + "\n"


def test_textsc_becomes_text_in_inline_math() -> None:
    # KaTeX has no small-capitals command.
    text = r"$M\textsc{h}/\textsc{m}^2$" + "\n"
    assert clean_in_place(text) == r"$M\text{h}/\text{m}^2$" + "\n"


def test_a_straight_quote_after_a_symbol_becomes_a_double_prime() -> None:
    # An equation editor takes `"` typed for `''` verbatim.
    text = '$t"$ and $$t_{1} = \\frac{(t" + t\')}{2} + \\alpha"$$\n'
    expected = "$t''$ and $$t_{1} = \\frac{(t'' + t')}{2} + \\alpha''$$\n"
    assert clean_in_place(text) == expected


def test_a_quote_raised_into_a_superscript_becomes_primes() -> None:
    # A `'` inside the group would be raised twice.
    text = '$\\mu_{2-3}^{"} + a_{rs}^{""} + x^{"a}$\n'
    expected = (
        "$\\mu_{2-3}^{\\prime\\prime} + a_{rs}^{\\prime\\prime\\prime\\prime}"
        " + x^{\\prime\\prime a}$\n"
    )
    assert clean_in_place(text) == expected
    assert clean_in_place(expected) == expected


def test_a_quote_in_text_mode_or_after_a_word_stays() -> None:
    # Text mode, a currency pair, and an accent command behind a backslash.
    text = (
        '$$x = \\text{"a"} \\tag{A"}$$\n\n'
        'It costs $5 for the "Basic" plan and $6 more.\n\n'
        '$\\text{zul\\"{a}ssig}$\n'
    )
    assert clean_in_place(text) == text


def test_label_and_its_leading_space_are_dropped_from_display_math() -> None:
    text = r"$$a = \mu P\, R_{\rm max}. \label{eq:pcu_H}$$" + "\n"
    assert clean_in_place(text) == r"$$a = \mu P\, R_{\rm max}.$$" + "\n"


def test_nested_display_delimiters_are_dropped_in_inline_math() -> None:
    assert clean_in_place(r"$x\[y\]z$" + "\n") == "$xyz$\n"


def test_nested_display_delimiters_survive_in_display_math() -> None:
    # The removal is scoped to `$...$`; a display span keeps its content as-is.
    text = r"$$x\[y\]z$$" + "\n"
    assert clean_in_place(text) == text


def test_double_subscript_gets_an_empty_group() -> None:
    assert clean_in_place("$x_{a}_{b}$\n") == "$x_{a}{}_{b}$\n"


def test_double_subscript_chain_is_fully_disarmed() -> None:
    assert clean_in_place("$x_{a}_{b}_{c}$\n") == "$x_{a}{}_{b}{}_{c}$\n"


def test_double_subscript_with_nested_braces_is_disarmed() -> None:
    # A `[^{}]*` scan would stop at the inner brace.
    text = r"$x_{\text{a}}_{b}$" + "\n"
    assert clean_in_place(text) == r"$x_{\text{a}}{}_{b}$" + "\n"


def test_trailing_stray_backslash_is_trimmed() -> None:
    assert clean_in_place("$x^2 \\ $\n") == "$x^2$\n"


def test_trailing_slash_space_run_is_trimmed() -> None:
    assert clean_in_place("$x^2 \\ \\ $\n") == "$x^2$\n"


def test_trailing_backslash_before_own_line_delimiter_is_trimmed() -> None:
    text = "$$\nx^2 \\\n$$\n"
    assert clean_in_place(text) == "$$\nx^2\n$$\n"


def test_double_backslash_line_break_is_kept_in_display_math() -> None:
    # `\\` is a LaTeX line break, not an artifact.
    text = "$$a \\\\ $$\n"
    assert clean_in_place(text) == text


def test_label_removal_only_eats_its_own_leading_space() -> None:
    text = r"$$a \label{x} b$$" + "\n"
    assert clean_in_place(text) == "$$a b$$\n"


def test_prose_with_two_dollar_signs_is_left_untouched() -> None:
    text = "Price is $5 and cost $10.\n"
    assert clean_in_place(text) == text


def test_prose_pulled_into_math_is_left_for_inspection() -> None:
    text = r"$P_{\text{ном}}=150\text{MH}, а на внешнем}-(0,48)$" + "\n"  # noqa: RUF001
    assert clean_in_place(text) == text


def test_math_fixes_do_not_cross_a_code_fence() -> None:
    # A `$` opened in plain text and one inside a fenced block must never pair.
    text = "$a\n```\n$b\n```\n"
    assert clean_in_place(text) == text


def test_math_normalization_is_idempotent() -> None:
    text = r"$P_{\mbox{\tiny MAX}}$ and $$a = b. \label{eq:1}$$ and $x_{a}_{b}$" + "\n"
    once = clean(text)
    assert clean(once) == once


# ---- runaway display span ---------------------------------------------------


def test_a_backslash_glued_display_closer_is_reclosed() -> None:
    # The glued backslash escapes the `$`, so the span swallows the prose below.
    text = "$$a = b \\ \\ \\$$\n\nProse between.\n\n$$c = d$$\n"
    assert clean_in_place(text) == "$$a = b$$\n\nProse between.\n\n$$c = d$$\n"


def test_a_double_backslash_glued_to_the_closer_goes_whole() -> None:
    assert clean_in_place("$$a = b \\\\$$\n") == "$$a = b$$\n"


def test_a_stub_span_glued_at_its_brace_is_reclosed() -> None:
    text = "$$\\frac{\\$$\n\nProse.\n\n$$c = d$$\n"
    assert clean_in_place(text) == "$$\\frac{$$\n\nProse.\n\n$$c = d$$\n"


def test_a_reunited_tail_glued_at_its_full_stop_is_reclosed() -> None:
    text = "$$a = \\left. b \\right.\\$$\n\nProse.\n\n$$c = d$$\n"
    assert clean_in_place(text) == "$$a = \\left. b \\right.$$\n\nProse.\n\n$$c = d$$\n"


def test_a_stub_span_stops_the_cascade_through_the_body() -> None:
    text = (
        "$$\\frac{\\$$\n\n"
        "## A heading the stub swallowed\n\n"
        "Ordinary prose in between.\n\n"
        "$$x_2 = b + c$$\n\n"
        "$$x_3 = d + e$$\n"
    )
    cleaned = clean_in_place(text)
    spans = _DISPLAY_MATH_RE.findall(cleaned)
    assert len(spans) == 3
    assert all(is_valid_math(content) for content in spans[1:])
    assert "heading the stub swallowed" in cleaned
    assert not any("swallowed" in content for content in spans)


def test_a_printed_dollar_glued_to_a_digit_is_not_reclosed() -> None:
    text = "$$C = 5\\$$\n\nProse.\n\n$$c = d$$\n"
    assert clean_in_place(text) == text


def test_a_printed_dollar_glued_to_a_closed_group_is_not_reclosed() -> None:
    for tail in ("(5)", "\\text{USD}"):
        text = f"$$C = {tail}\\$$\n\nProse.\n\n$$c = d$$\n"
        assert clean_in_place(text) == text


def test_a_printed_dollar_outside_math_is_left_alone() -> None:
    text = "The list price is \\$5, marked up from \\$4.\n"
    assert clean_in_place(text) == text


def test_a_printed_dollar_inside_a_closed_display_span_survives() -> None:
    text = "$$C = 5\\$ \\cdot n$$\n"
    assert clean_in_place(text) == text


def test_a_runaway_span_decomposes_into_valid_spans() -> None:
    text = (
        "$$x_1 = a \\ \\ \\$$\n\n"
        "## A heading the runaway swallowed\n\n"
        "Ordinary prose in between.\n\n"
        "$$x_2 = b + c$$\n\n"
        "$$x_3 = d + e$$\n"
    )
    cleaned = clean_in_place(text)
    spans = _DISPLAY_MATH_RE.findall(cleaned)
    assert len(spans) == 3
    assert all(is_valid_math(content) for content in spans)
    assert "heading the runaway swallowed" in cleaned
    assert not any("swallowed" in content for content in spans)


def test_reclose_is_idempotent() -> None:
    text = "$$a = b \\ \\$$\n\nProse.\n\n$$c = d$$\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- runaway inline span ------------------------------------------------------


def test_an_escaped_inline_closer_is_reclosed() -> None:
    # The office docx route escapes the closer and eats the space after it.
    text = "$X\\$word\n"
    assert clean_in_place(text) == "$X$ word\n"


def test_an_escaped_closer_past_a_legend_dash_is_reclosed() -> None:
    text = "$Y - \\$word;\n"
    assert clean_in_place(text) == "$Y$ - word;\n"


def test_reclosing_an_inline_span_makes_the_lines_delimiter_count_even() -> None:
    text = "Formula $X\\$word here.\n"
    cleaned = clean_in_place(text)
    assert cleaned == "Formula $X$ word here.\n"
    unescaped = sum(
        1
        for i, char in enumerate(cleaned)
        if char == "$" and (i == 0 or cleaned[i - 1] != "\\")
    )
    assert unescaped % 2 == 0


def test_a_printed_dollar_glued_to_a_digit_is_not_reclosed_inline() -> None:
    text = "$5\\$word\n"
    assert clean_in_place(text) == text


def test_a_printed_dollar_glued_to_a_closed_group_is_not_reclosed_inline() -> None:
    text = "$(5)\\$word\n"
    assert clean_in_place(text) == text


def test_an_escaped_closer_whose_content_never_renders_is_left_alone() -> None:
    text = "$\\sqrt{2\\$word\n"
    assert clean_in_place(text) == text


def test_a_stray_escaped_inline_dollar_with_no_open_span_is_left_alone() -> None:
    text = "The price is \\$5 today.\n"
    assert clean_in_place(text) == text


def test_a_display_span_on_one_line_is_not_read_as_two_inline_boundaries() -> None:
    text = "$$a = b$$ and $c\\$d\n"
    assert clean_in_place(text) == "$$a = b$$ and $c$ d\n"


def test_a_printed_amount_before_a_digit_is_not_reclosed_inline() -> None:
    text = "Use $x before paying \\$5.\n"
    assert clean_in_place(text) == text


def test_a_quoted_display_delimiter_does_not_hide_a_damaged_span() -> None:
    # Inline code is masked before the delimiters are read.
    text = "A `$$` before $X\\$word then `$$` after.\n"
    assert clean_in_place(text) == "A `$$` before $X$ word then `$$` after.\n"


def test_reclosing_an_escaped_inline_closer_is_idempotent() -> None:
    text = "$X\\$word\n"
    once = clean(text)
    assert clean(once) == once


def test_a_truncated_display_span_with_no_glued_run_is_left_alone() -> None:
    text = "$$a = b + c\n\nMore prose.\n"
    assert clean_in_place(text) == text


def test_reclose_runs_before_table_math() -> None:
    text = (
        "| col | value |\n"
        "|-----|-------|\n"
        "| $$a =\n b + c \\ \\$$ | 1 |\n\n"
        "Tail paragraph.\n\n$$z = 0$$\n"
    )
    cleaned = clean_in_place(text)
    assert "| $$a = b + c$$ | 1     |" in cleaned


# ---- prose lifted out of a display span --------------------------------------


def test_a_legend_entry_is_lifted_out_of_its_display_span() -> None:
    text = "$$p - \\text{oil pressure in the gearbox, } \\textit{MN/m}^2;$$\n"
    assert clean_in_place(text) == "$p$ - oil pressure in the gearbox, MN/m$^2$;\n"


def test_the_formula_of_a_lifted_entry_stays_a_span() -> None:
    text = (
        "$$x_1 = \\frac{a}{b} - "
        "\\text{share of scrap in the batch, } \\textit{kg/kg};$$\n"
    )
    cleaned = clean_in_place(text)
    assert cleaned.startswith("$x_1 = \\frac{a}{b}$ - ")
    assert "share of scrap in the batch, kg/kg;" in cleaned


def test_every_span_a_lift_leaves_renders() -> None:
    text = (
        "$$S(k) = G\\left(\\frac{\\pi}{3}, k\\right) - "
        "\\text{a tabulated sum, the sum from } x_1 "
        "\\text{ to } x_2 \\text{ taken as a difference};$$\n"
    )
    cleaned = clean_in_place(text)
    spans = math_spans(cleaned)
    assert len(spans) == 3
    assert all(is_valid_math(math_span_content(span)) for span in spans)


def test_an_entry_whose_closer_the_damage_ate_is_lifted() -> None:
    # A lost closer shifts the pairing of every delimiter behind it.
    text = (
        "$$w - \\text{coolant flow through the spindle, } \\textit{l/s};\n"
        "$$t - \\text{oil temperature at the pump, } \\textit{deg};$$\n\n"
        "Ordinary prose.\n\n$$z = 0$$\n"
    )
    cleaned = clean_in_place(text)
    assert cleaned.startswith(
        "$w$ - coolant flow through the spindle, l/s;\n"
        "$t$ - oil temperature at the pump, deg;\n"
    )
    assert "$$z = 0$$" in cleaned
    assert "Ordinary prose." in cleaned


def test_a_multi_line_display_block_keeps_its_first_line() -> None:
    # The line below closes the block instead of opening one.
    text = "$$x = a - \\text{under this bound}\n+ b + c$$\n\n$$y = d$$\n"
    assert clean_in_place(text) == text


def test_a_block_closing_on_its_own_line_keeps_its_first_line() -> None:
    text = "$$q = a - \\text{under this bound}\n$$\n"
    assert clean_in_place(text) == text


def test_a_doubled_closer_goes_with_the_lift() -> None:
    text = "$$m - \\text{mass flow of the coolant, } \\textit{kg/s};$$$$\n"
    assert clean_in_place(text) == "$m$ - mass flow of the coolant, kg/s;\n"


def test_a_formula_whose_text_mode_states_a_condition_is_left_alone() -> None:
    text = (
        "$$x_4 = 20 \\sin \\frac{\\pi}{2} \\cdot 4 = 0, "
        "\\text{ since } \\sin 2\\pi = 0;$$\n"
    )
    assert clean_in_place(text) == text


def test_a_bracketed_condition_is_left_alone() -> None:
    # The prose stands inside a group the formula opens.
    text = "$$[m - \\text{whole numbers above zero}].$$\n"
    assert clean_in_place(text) == text


def test_a_qualified_equation_without_a_dash_is_left_alone() -> None:
    text = "$$x = y \\text{ for all integers};$$\n"
    assert clean_in_place(text) == text


def test_a_cases_block_is_left_alone() -> None:
    text = (
        "$$b = \\begin{cases} 1, & \\text{if } i = 1, \\\\ "
        "0 & \\text{otherwise.} \\end{cases}$$\n"
    )
    assert clean_in_place(text) == text


def test_a_numbered_equation_is_left_alone() -> None:
    text = "$$\\alpha = \\frac{\\lambda}{d} \\text{ Nu in units}. \\tag{IV.7}$$\n"
    assert clean_in_place(text) == text


def test_an_argument_holding_a_command_is_left_alone() -> None:
    text = "$$R - \\text{specific heat of the oil, } \\textit{J/(kg \\cdot K)};$$\n"
    assert clean_in_place(text) == text


def test_the_prose_share_floor_decides_a_borderline_span() -> None:
    long_formula = "$$a + b + c + d + e + f + g + h = k - \\text{under this bound};$$\n"
    short_formula = "$$a = k - \\text{under this bound};$$\n"
    assert clean_in_place(long_formula) == long_formula
    assert clean_in_place(short_formula) == "$a = k$ - under this bound;\n"
    assert 0 < _PROSE_SHARE_MIN < 1


def test_the_lift_is_idempotent() -> None:
    text = "$$q - \\text{heat flow, } \\textit{W};$$\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_a_lift_does_not_reach_into_a_code_fence() -> None:
    text = "```\n$$p - \\text{oil pressure in the gearbox, } \\textit{MN}^2;$$\n```\n"
    assert clean_in_place(text) == text


# ---- math environments --------------------------------------------------------


def test_orphan_environment_end_and_its_amp_are_dropped() -> None:
    # marker's split of an aligned block keeps `\end{split}` but not the opener.
    text = r"$$&\tau_{23} = \pm \frac{1}{2} (\sigma_2 - \sigma_3) \end{split}$$" + "\n"
    fixed = r"$$\tau_{23} = \pm \frac{1}{2} (\sigma_2 - \sigma_3)$$" + "\n"
    assert clean_in_place(text) == fixed


def test_paired_environment_and_its_amps_survive() -> None:
    text = r"$$\begin{split} a &= b \\ c &= d \end{split}$$" + "\n"
    assert clean_in_place(text) == text


def test_stray_amps_are_dropped_past_a_line_break() -> None:
    text = r"$$&a = b \\ &c = d\end{split}$$" + "\n"
    assert clean_in_place(text) == r"$$a = b \\ c = d$$" + "\n"


def test_unclosed_environment_goes_with_its_amps() -> None:
    text = r"$$\begin{split} a &= b \\ c &= d$$" + "\n"
    assert clean_in_place(text) == r"$$a = b \\ c = d$$" + "\n"


def test_escaped_amp_is_not_alignment_markup() -> None:
    text = r"$$a \& b$$" + "\n"
    assert clean_in_place(text) == text


def test_amp_in_a_currency_pair_is_left_untouched() -> None:
    # Two dollar signs on a line make a span, so prose can land in one.
    text = "Prices are $5 & $6 today.\n"
    assert clean_in_place(text) == text


def test_amp_inside_a_brace_group_is_text_not_alignment() -> None:
    # Dropping an `&` inside an argument would delete a letter.
    text = r"$$\text{R&D} &= 5 \end{split}$$" + "\n"
    assert clean_in_place(text) == r"$$\text{R&D} = 5$$" + "\n"


def test_closer_matches_across_an_inner_unclosed_environment() -> None:
    text = r"$$\begin{split}\begin{array}{c} a \end{split}$$" + "\n"
    assert clean_in_place(text) == text


def test_an_unclosed_environment_aligning_nothing_is_left_alone() -> None:
    # Without an `&` the opener may be a real matrix whose rows were cut.
    text = r"$$\begin{pmatrix} a$$" + "\n"
    assert clean_in_place(text) == text


def test_orphan_environment_end_is_dropped_from_inline_math() -> None:
    assert clean_in_place(r"$&x \end{split}$" + "\n") == "$x$\n"


def test_environment_balance_is_idempotent() -> None:
    text = r"$$&\tau = \pm \frac{1}{2} \end{split}$$" + "\n"
    once = clean(text)
    assert clean(once) == once


def test_a_truncated_array_spec_keeps_its_unmatched_opener() -> None:
    text = r"$$\begin{array}{ccc$$" + "\n"
    assert clean_in_place(text) == text


def test_plain_tex_equation_number_becomes_a_tag() -> None:
    assert clean_in_place(r"$$a = b \eqno(43)$$" + "\n") == r"$$a = b \tag{43}$$" + "\n"


# ---- a display formula cut across spans ---------------------------------------


def test_a_continuation_piece_joins_the_span_above_it() -> None:
    # marker emits a long display formula one `$$...$$` per printed line.
    text = "$$U = a + b$$\n\n$$+ c + d$$\n"
    assert clean_in_place(text) == "$$U = a + b + c + d$$\n"


def test_a_chain_of_five_pieces_collapses_into_one_span() -> None:
    text = "$$U = a$$\n\n$$+ b$$\n\n$$+ c$$\n\n$$+ d$$\n\n$$+ e$$\n"
    assert clean_in_place(text) == "$$U = a + b + c + d + e$$\n"


def test_an_operator_repeated_at_the_seam_is_kept_once() -> None:
    # Russian typesetting repeats the operator on both ends of a break.
    text = "$$I = a + b =$$\n\n$$= c + d$$\n"
    assert clean_in_place(text) == "$$I = a + b = c + d$$\n"


def test_the_number_printed_at_the_seam_moves_to_the_end() -> None:
    text = "$$I = a + b = (6.7)$$\n\n$$= c + d$$\n"
    assert clean_in_place(text) == "$$I = a + b = c + d \\tag{6.7}$$\n"


def test_a_number_the_seam_does_not_attest_stays_where_it_was_printed() -> None:
    text = "$$a = b \\cdot (10)$$\n\n$$+ c$$\n"
    assert clean_in_place(text) == "$$a = b \\cdot (10) + c$$\n"


def test_a_head_stating_its_own_number_takes_no_continuation() -> None:
    text = "$$a = b + c \\quad (10)$$\n\n$$- d = e \\quad (11)$$\n"
    assert clean_in_place(text) == "$$a = b + c \\tag{10}$$\n\n$$- d = e \\tag{11}$$\n"


def test_a_head_carrying_a_tag_takes_no_continuation() -> None:
    text = "$$a = b + c \\tag{10}$$\n\n$$- d = e$$\n"
    assert clean_in_place(text) == text


def test_a_tag_beside_a_dangling_operator_does_not_finish_the_equation() -> None:
    text = "$$a = b \\cdot \\tag{10}$$\n\n$$\\cdot c$$\n"
    assert clean_in_place(text) == "$$a = b \\cdot c \\tag{10}$$\n"


def test_a_formula_closed_by_its_own_full_stop_takes_no_continuation() -> None:
    text = "$$a = b + c.$$\n\n$$- d = e$$\n"
    assert clean_in_place(text) == text


def test_a_null_delimiter_is_not_sentence_punctuation() -> None:
    text = "$$U = \\left\\{ a + b \\right.$$\n\n$$+ c$$\n"
    assert clean_in_place(text) == "$$U = \\left\\{ a + b \\right. + c$$\n"


def test_a_number_line_between_two_spans_stops_the_join() -> None:
    text = "$$a = b + c$$\n\n(10)\n\n$$- d = e$$\n"
    assert clean_in_place(text) == text


def test_prose_between_two_spans_stops_the_join() -> None:
    text = "$$a = b + c$$\n\nwhere the terms are\n\n$$+ d$$\n"
    assert clean_in_place(text) == text


def test_a_span_opening_a_formula_of_its_own_is_not_joined() -> None:
    text = "$$a = b + c$$\n\n$$d = e$$\n"
    assert clean_in_place(text) == text


def test_a_closing_bracket_at_a_seam_is_not_read_as_a_repeat() -> None:
    text = "$$U = \\left[ (a + b)$$\n\n$$) \\right]$$\n"
    assert clean_in_place(text) == "$$U = \\left[ (a + b) ) \\right]$$\n"


def test_an_unclosed_array_a_join_reunites_is_dropped_with_its_amp() -> None:
    text = (
        "$$R = \\left( a - \\Omega$$\n"
        "\n"
        "$$+ \\left(\\begin{array}{c|c} b & c\\right)^2\\right)$$\n"
    )
    joined = "$$R = \\left( a - \\Omega + \\left(b c\\right)^2\\right)$$\n"
    assert clean_in_place(text) == joined


def test_a_spacing_command_at_the_seam_keeps_the_space_its_closer_needs() -> None:
    # Trimmed at the join, the lone backslash would escape the `$$`.
    text = "$$f(x) = \\left\\{ a + b$$\n\n$$+ c \\right.\\ $$\n"
    out = clean_in_place(text)
    assert out == "$$f(x) = \\left\\{ a + b + c \\right.$$\n"
    assert is_valid_math(math_span_content(math_spans(out)[0]))


def test_a_seam_with_no_spacing_command_still_trims_its_padding() -> None:
    text = "$$U = a + b $$\n\n$$+ c + d $$\n"
    assert clean_in_place(text) == "$$U = a + b + c + d$$\n"


def test_both_spacing_seams_of_one_body_are_repaired() -> None:
    text = (
        "$$A = \\left\\{ x$$\n\n$$+ y \\right.\\ $$\n\n"
        "In between.\n\n"
        "$$B = \\left\\{ p$$\n\n$$+ q \\right.\\ $$\n"
    )
    out = clean_in_place(text)
    assert out == (
        "$$A = \\left\\{ x + y \\right.$$\n\n"
        "In between.\n\n"
        "$$B = \\left\\{ p + q \\right.$$\n"
    )
    assert all(is_valid_math(math_span_content(span)) for span in math_spans(out))


def test_reuniting_a_split_formula_is_idempotent() -> None:
    text = "$$I = a + b =$$\n\n$$= c + d (6.7)$$\n"
    once = clean(text)
    assert clean(once) == once


def test_a_formula_broken_at_null_delimiters_is_joined() -> None:
    text = (
        "$$M = 2\\left( \\int_{a}^{b}{f\\ d\\theta -} \\right.\\ $$\n"
        "\n"
        "$$\\left. \\  - \\int_{c}^{d}{g\\ d\\theta} \\right)$$\n"
    )
    out = clean_in_place(text)
    assert out == (
        "$$M = 2\\left( \\int_{a}^{b}{f\\ d\\theta -}"
        " \\  - \\int_{c}^{d}{g\\ d\\theta} \\right)$$\n"
    )
    assert is_valid_math(math_span_content(math_spans(out)[0]))


def test_the_join_over_null_delimiters_moves_nothing_else() -> None:
    head = "U = \\left\\lbrack \\sum_{i}{x_{i} +}"
    tail = "+ \\sum_{j}{y_{j}} \\right\\rbrack"
    text = f"$${head} \\right.$$\n\n$$\\left. {tail}$$\n"
    assert math_span_content(math_spans(clean_in_place(text))[0]) == f"{head} {tail}"


def test_a_block_closing_on_a_printed_delimiter_joins_nothing() -> None:
    text = "$$U = \\left( a + b \\right)$$\n\n$$\\left. \\  - c \\right)$$\n"
    assert clean_in_place(text) == text


def test_joining_over_null_delimiters_is_idempotent() -> None:
    text = "$$M = \\left( a + \\right.$$\n\n$$\\left. \\  + b \\right)$$\n"
    once = clean(text)
    assert clean(once) == once


# ---- an equation number folded into its own tag --------------------------------


def test_a_number_line_under_the_block_is_folded_into_a_tag() -> None:
    text = "$$a = b$$\n(3)\n"
    assert clean_in_place(text) == "$$a = b \\tag{3}$$\n"


def test_a_number_line_with_a_variant_letter_is_folded() -> None:
    text = "$$a = b$$\n(D13)\n"
    assert clean_in_place(text) == "$$a = b \\tag{D13}$$\n"


def test_a_quad_held_tail_number_is_folded_into_a_tag() -> None:
    text = "$$a = b + c \\quad (10)$$\n"
    assert clean_in_place(text) == "$$a = b + c \\tag{10}$$\n"


def test_a_qquad_held_tail_number_with_a_letter_prefix_is_folded() -> None:
    text = "$$a = b \\qquad (C3)$$\n"
    assert clean_in_place(text) == "$$a = b \\tag{C3}$$\n"


def test_a_dotted_tail_number_is_folded_into_a_tag() -> None:
    text = "$$a = b, c = d (6.7)$$\n"
    assert clean_in_place(text) == "$$a = b, c = d \\tag{6.7}$$\n"


def test_a_block_already_carrying_a_tag_keeps_the_number_line_below_it() -> None:
    text = "$$a = b \\tag{10}$$\n(11)\n"
    assert clean_in_place(text) == text


def test_a_trailing_condition_is_not_read_as_an_equation_number() -> None:
    text = "$$a = b \\quad (1 \\le i \\le n-1)$$\n"
    assert clean_in_place(text) == text


def test_a_number_line_without_a_block_above_it_stays_prose() -> None:
    text = "prose\n\n(3)\n\nmore prose\n"
    assert clean_in_place(text) == text


def test_a_number_line_across_a_blank_line_is_not_folded() -> None:
    text = "$$a = b$$\n\n(3)\n\nmore prose\n"
    assert clean_in_place(text) == text


def test_equation_number_folding_is_idempotent() -> None:
    text = "$$a = b$$\n(3)\n"
    once = clean(text)
    assert clean(once) == once


def test_a_tail_number_behind_a_label_is_still_folded() -> None:
    # The fold runs after `\label{...}` is dropped.
    text = "$$a = b \\quad (3) \\label{eq:1}$$\n"
    assert clean_in_place(text) == "$$a = b \\tag{3}$$\n"


def test_a_plain_tex_number_beside_a_redundant_number_line_is_not_doubled() -> None:
    # `\eqno(3)` is already a tag when this rule runs.
    text = "$$a = b \\eqno(3)$$\n(3)\n"
    assert clean_in_place(text) == "$$a = b \\tag{3}$$\n(3)\n"


def test_a_number_line_under_a_multiline_block_is_folded() -> None:
    text = "$$\na = b\n$$\n(3)\n"
    assert clean_in_place(text) == "$$\na = b \\tag{3}\n$$\n"


def test_a_multiline_block_folding_is_idempotent() -> None:
    text = "$$\na = b\n$$\n(3)\n"
    once = clean(text)
    assert clean(once) == once


def test_a_number_line_after_a_table_cell_span_is_not_folded() -> None:
    text = "| $$x = y$$ | z |\n(3)\n"
    assert clean_in_place(text) == text


def test_a_number_line_after_a_span_embedded_in_prose_is_not_folded() -> None:
    text = "Text before $$x = y$$ and after.\n(3)\n"
    assert clean_in_place(text) == text


def test_an_indented_block_and_its_number_line_are_still_folded() -> None:
    text = "  $$a = b$$\n  (3)\n"
    assert clean_in_place(text) == "  $$a = b \\tag{3}$$\n"


def test_an_indented_multiline_block_keeps_its_closer_indented() -> None:
    text = "  $$\n  a = b\n  $$\n  (3)\n"
    assert clean_in_place(text) == "  $$\n  a = b \\tag{3}\n  $$\n"


def test_a_tail_number_before_an_indented_closer_is_a_known_miss() -> None:
    # Known limit: an indented closer hides the tail number; never a wrong tag.
    text = "  $$\n  a = b \\quad (3)\n  $$\n"
    assert clean_in_place(text) == text


def test_a_roman_numbered_line_is_folded_into_a_tag() -> None:
    text = "$$q = w$$\n(III.24)\n"
    assert clean_in_place(text) == "$$q = w \\tag{III.24}$$\n"


def test_a_dash_joined_number_line_is_folded_into_a_tag() -> None:
    text = "$$q = w$$\n(2-10)\n"
    assert clean_in_place(text) == "$$q = w \\tag{2-10}$$\n"


def test_a_dash_joined_number_in_the_span_tail_is_left_as_content() -> None:
    # Inside a span, `(2-10)` after whitespace is a subtraction.
    text = "$$x = y + (2-10)$$\n"
    assert clean_in_place(text) == text


# ---- a tail left behind a display block's closer ------------------------------

# The office route sets a numbered formula as a one-row table.
_CARRIER_TABLE = "| $$a = b$$ | {tail} |\n|----|----|\n"


def test_a_number_behind_the_closer_is_folded_into_a_tag() -> None:
    # A number behind `$$` breaks the block for a renderer that reads to line end.
    text = _CARRIER_TABLE.format(tail="(1.29)")
    assert clean_in_place(text) == "$$a = b \\tag{1.29}$$\n"


def test_an_escaped_number_behind_the_closer_is_read_the_same() -> None:
    text = _CARRIER_TABLE.format(tail="\\(2\\)")
    assert clean_in_place(text) == "$$a = b \\tag{2}$$\n"


def test_a_number_behind_the_closer_of_a_plain_line_is_folded() -> None:
    assert clean_in_place("$$a = b$$ (7)\n") == "$$a = b \\tag{7}$$\n"


def test_a_picture_behind_the_closer_takes_its_own_line() -> None:
    text = _CARRIER_TABLE.format(tail='<img src="a/i.png" />')
    assert clean_in_place(text) == '$$a = b$$\n\n<img src="a/i.png" />\n'


def test_a_tail_that_states_no_number_keeps_every_character_it_has() -> None:
    text = _CARRIER_TABLE.format(tail="((1)")
    assert clean_in_place(text) == "$$a = b$$\n\n((1)\n"


def test_a_tail_beside_an_already_tagged_block_takes_its_own_line() -> None:
    text = "$$a = b \\tag{10}$$ (11)\n"
    assert clean_in_place(text) == "$$a = b \\tag{10}$$\n\n(11)\n"


def test_a_span_embedded_in_prose_keeps_the_text_behind_it() -> None:
    assert clean_in_place("Text $$a = b$$ (7)\n") == "Text $$a = b$$ (7)\n"


def test_a_line_carrying_a_second_span_is_left_alone() -> None:
    assert clean_in_place("$$a = b$$ and $$c = d$$\n") == "$$a = b$$ and $$c = d$$\n"


def test_a_row_that_states_no_outer_bar_keeps_its_cells() -> None:
    # Without outer bars, the bar past the closer is a cell border.
    text = "$$a = b$$ | (7)\n--- | ---\n$$c = d$$ | (8)\n"
    assert clean_in_place(text) == (
        "$$a = b$$ | (7)\n----------|----\n$$c = d$$ | (8)\n"
    )


def test_an_indented_block_and_its_moved_tail_keep_their_indentation() -> None:
    text = '  $$a = b$$ <img src="a/i.png" />\n'
    assert clean_in_place(text) == '  $$a = b$$\n\n  <img src="a/i.png" />\n'


def test_clearing_a_tail_behind_the_closer_is_idempotent() -> None:
    text = _CARRIER_TABLE.format(tail='<img src="a/i.png" />')
    once = clean(text)
    assert clean(once) == once


# ---- a display block's stranded sentence tail --------------------------------


def test_a_stranded_comma_line_rejoins_the_block() -> None:
    # marker leaves the comma after a display formula on its own line.
    text = "$$a_{ij} = a_{ji}$$\n,\n"
    assert clean_in_place(text) == "$$a_{ij} = a_{ji},$$\n"


def test_a_stranded_full_stop_line_rejoins_the_block() -> None:
    text = "$$a = b$$\n.\n"
    assert clean_in_place(text) == "$$a = b.$$\n"


def test_a_rejoined_mark_leaves_a_span_the_renderer_accepts() -> None:
    text = "$$\\int_0^{\\infty} e^{-x} \\, dx = 1$$\n.\n"
    cleaned = clean_in_place(text)
    assert cleaned == "$$\\int_0^{\\infty} e^{-x} \\, dx = 1.$$\n"
    (span,) = math_spans(cleaned)
    assert is_valid_math(math_span_content(span))


def test_a_stranded_mark_under_prose_is_left_alone() -> None:
    text = "A sentence that ends on its own line\n.\n"
    assert clean_in_place(text) == text


def test_a_line_opening_on_a_mark_gives_the_block_its_head() -> None:
    text = "$$a = b$$\n, where $c$ is fixed.\n"
    assert clean_in_place(text) == "$$a = b,$$\nwhere $c$ is fixed.\n"


def test_a_line_under_the_block_not_opening_on_a_mark_is_left_alone() -> None:
    text = "$$a = b$$\nwhere c > 0.\n"
    assert clean_in_place(text) == text


def test_a_stranded_head_mark_leaves_a_span_the_renderer_accepts() -> None:
    text = "$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$$\n, hence the claim.\n"
    cleaned = clean_in_place(text)
    assert cleaned == "$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2},$$\nhence the claim.\n"
    (span,) = math_spans(cleaned)
    assert is_valid_math(math_span_content(span))


def test_a_head_mark_under_a_span_embedded_in_prose_is_left_alone() -> None:
    text = "Prose $$a = b$$ prose\n, and the rest.\n"
    assert clean_in_place(text) == text


def test_stranded_head_mark_fold_is_idempotent() -> None:
    text = "$$a = b$$\n, where $c$ is fixed.\n"
    once = clean(text)
    assert clean(once) == once


def test_a_stranded_head_keeps_the_indentation_of_its_remainder() -> None:
    text = "- item\n\n  $$a = b$$\n  , where c.\n"
    assert clean_in_place(text) == "- item\n\n  $$a = b,$$\n  where c.\n"


def test_a_block_the_head_fold_promotes_settles_in_one_pass() -> None:
    text = "$$a$$\n, $$b$$\n.\n"
    once = clean(text)
    assert once == "$$a,$$\n$$b.$$\n"
    assert clean(once) == once


def test_a_numbered_block_still_takes_its_stranded_mark() -> None:
    text = "$$a = b \\tag{3}$$\n.\n"
    assert clean_in_place(text) == "$$a = b. \\tag{3}$$\n"


def test_a_spacing_command_keeps_its_space_before_a_stranded_mark() -> None:
    # Trimmed, the mark would spell `\.`, which the renderer rejects.
    text = "$$a = b\\ \\tag{3}$$\n.\n"
    assert clean_in_place(text) == "$$a = b\\ . \\tag{3}$$\n"
    assert is_valid_math("a = b\\ . \\tag{3}")


def test_a_comment_keeps_the_newline_that_ends_it() -> None:
    # Trimmed, the mark and the tag would join the `%` comment.
    text = "$$a = b % note\n\\tag{3}$$\n.\n"
    assert clean_in_place(text) == "$$a = b % note\n. \\tag{3}$$\n"


def test_a_tail_number_and_a_stranded_mark_are_both_fixed() -> None:
    text = "$$a = b \\quad (3)$$\n.\n"
    assert clean_in_place(text) == "$$a = b. \\tag{3}$$\n"


def test_a_number_line_and_a_stranded_mark_are_both_fixed() -> None:
    text = "$$a = b$$\n(3)\n.\n"
    assert clean_in_place(text) == "$$a = b. \\tag{3}$$\n"


def test_a_stranded_mark_across_a_blank_line_is_not_rejoined() -> None:
    text = "$$a = b$$\n\n.\n\nMore prose.\n"
    assert clean_in_place(text) == text


def test_a_stranded_mark_under_a_multiline_block_is_rejoined() -> None:
    text = "$$\na = b\n$$\n.\n"
    assert clean_in_place(text) == "$$\na = b.\n$$\n"


def test_stranded_mark_rejoin_is_idempotent() -> None:
    text = "$$a = b$$\n,\n"
    once = clean(text)
    assert clean(once) == once


def test_stranded_mark_rejoin_under_a_multiline_block_is_idempotent() -> None:
    text = "$$\na = b\n$$\n.\n"
    once = clean(text)
    assert clean(once) == once


# ---- a display block's stranded condition -------------------------------------


def test_a_stranded_condition_returns_to_its_block() -> None:
    text = "$$s_n = 1$$\n[n \\neq 1].\n"
    assert clean_in_place(text) == "$$s_n = 1 \\quad [n \\neq 1].$$\n"


def test_a_bare_condition_is_normalized_before_it_folds() -> None:
    # A bare condition never passed through normalization.
    text = "$$a = b$$\n[x_{a}_{b} > 0].\n"
    cleaned = clean_in_place(text)
    (span,) = math_spans(cleaned)
    assert is_valid_math(math_span_content(span))
    assert clean(cleaned) == cleaned


def test_a_condition_that_would_break_its_block_is_left_standing() -> None:
    text = "$$a = b$$\n[x > \\sqrt{2].\n"
    assert clean_in_place(text) == text


def test_a_condition_on_a_set_relation_returns_to_its_block() -> None:
    text = "$$a = b$$\n[A \\subseteq B].\n"
    assert clean_in_place(text) == "$$a = b \\quad [A \\subseteq B].$$\n"


def test_a_condition_wrapped_in_an_inline_span_returns_to_its_block() -> None:
    text = "$$y = x^a$$\n$[a, b>0].$\n"
    assert clean_in_place(text) == "$$y = x^a \\quad [a, b>0].$$\n"


def test_a_condition_holding_an_inline_span_returns_to_its_block() -> None:
    text = "$$y = x^a$$\n[ $x^2 < a^2$ ]\n"
    assert clean_in_place(text) == "$$y = x^a \\quad [ x^2 < a^2 ]$$\n"


def test_a_rejoined_condition_leaves_a_span_the_renderer_accepts() -> None:
    text = "$$\\int_0^{\\infty} e^{-ax} dx = \\frac{1}{a}$$\n[a > 0].\n"
    cleaned = clean_in_place(text)
    expected = "$$\\int_0^{\\infty} e^{-ax} dx = \\frac{1}{a} \\quad [a > 0].$$\n"
    assert cleaned == expected
    (span,) = math_spans(cleaned)
    assert is_valid_math(math_span_content(span))


def test_a_stranded_condition_under_a_multiline_block_is_rejoined() -> None:
    text = "$$\ny = x^a\n$$\n[a > 0].\n"
    assert clean_in_place(text) == "$$\ny = x^a \\quad [a > 0].\n$$\n"


def test_a_condition_line_under_prose_is_left_alone() -> None:
    text = "The series converges\n[n > 1].\n"
    assert clean_in_place(text) == text


def test_a_condition_across_a_blank_line_is_not_rejoined() -> None:
    text = "$$y = x^a$$\n\n[a > 0].\n"
    assert clean_in_place(text) == text


def test_a_bracketed_reference_states_no_relation_and_stays() -> None:
    text = "$$y = x^a$$\n[45.11.]\n"
    assert clean_in_place(text) == text


def test_a_bracketed_note_carrying_a_relation_is_still_prose() -> None:
    text = "$$y = x^a$$\n[See 45 for a > 0.]\n"
    assert clean_in_place(text) == text


def test_a_condition_written_with_an_html_superscript_is_left_alone() -> None:
    text = "$$y = x^a$$\n[a<sup>2</sup> < 1].\n"
    assert clean_in_place(text) == text


def test_a_bracketed_list_past_the_bar_is_left_alone() -> None:
    text = "$$y = x^a$$\n[x_1 > 0, x_2 > 0, x_3 > 0, x_4 > 0, x_5 > 0, x_6 > 0]\n"
    assert clean_in_place(text) == text


def test_stranded_condition_rejoin_is_idempotent() -> None:
    text = "$$y = x^a$$\n[a, b>0].\n"
    once = clean(text)
    assert clean(once) == once


# ---- a paragraph formula promoted to a display block -------------------------


def test_a_paragraph_relation_becomes_a_display_block() -> None:
    text = "$\\lim_{n \\to \\infty} x_n = L$\n"
    assert clean_in_place(text) == "$$\\lim_{n \\to \\infty} x_n = L$$\n"


def test_a_short_relation_paragraph_stays_inline() -> None:
    text = "$a = b$\n"
    assert clean_in_place(text) == text


def test_a_paragraph_formula_without_a_relation_stays_inline() -> None:
    text = "$\\Phi(x, y, z, w)$\n"
    assert clean_in_place(text) == text


def test_a_line_with_two_spans_is_left_inline() -> None:
    text = "$x = a$ and $y = b + c + d$\n"
    assert clean_in_place(text) == text


def test_a_span_inside_prose_is_not_promoted() -> None:
    text = "Then $x = \\frac{a + b}{c + d}$ follows for all n.\n"
    assert clean_in_place(text) == text


def test_an_indented_code_sample_is_not_promoted() -> None:
    # Four spaces under a paragraph make a code block.
    text = "Prose.\n\n    $x^2 + y^2 = R^2 + 4\\pi$\n\nProse.\n"
    assert clean_in_place(text) == text


def test_a_formula_at_the_top_of_a_page_is_promoted_through_the_mark() -> None:
    # Inspection writes the mark above each page and removes it after cleaning.
    formula = "\\lim_{n \\to \\infty} x_n = L"
    text = f"Prose.\n\n{page_mark(2)}\n${formula}$\n\nProse.\n"
    assert f"$${formula}$$" in clean_in_place(text)


def test_a_formula_indented_under_a_list_item_is_still_promoted() -> None:
    text = "- item\n\n    $x^2 + y^2 = R^2 + 4\\pi$\n\n- next\n"
    assert clean_in_place(text) == (
        "- item\n\n    $$x^2 + y^2 = R^2 + 4\\pi$$\n\n- next\n"
    )


def test_a_paragraph_formula_that_does_not_render_stays_inline() -> None:
    text = "$P_{x} = 200\\text{MH}, tail}-(0,62)$\n"
    assert clean_in_place(text) == text


def test_promotion_changes_two_delimiters_and_no_content() -> None:
    src = "$x^2 + y^2 = R^2 + 4\\pi$\n"
    out = clean_in_place(src)
    assert out == "$$x^2 + y^2 = R^2 + 4\\pi$$\n"
    assert out.count("$") == src.count("$") + 2
    before = math_span_content(math_spans(src)[0])
    after = math_span_content(math_spans(out)[0])
    assert after == before


def test_a_stranded_condition_folds_into_a_promoted_block() -> None:
    text = "$s_n = \\frac{1}{n}$\n[n \\neq 1].\n"
    assert clean_in_place(text) == "$$s_n = \\frac{1}{n} \\quad [n \\neq 1].$$\n"


def test_a_promoted_block_is_a_span_the_renderer_accepts() -> None:
    text = "$\\int_0^{\\infty} e^{-x} \\, dx = 1 + \\varepsilon$\n"
    cleaned = clean_in_place(text)
    (span,) = math_spans(cleaned)
    assert span.startswith("$$")
    assert span.endswith("$$")
    assert is_valid_math(math_span_content(span))


def test_a_paragraph_formula_promotion_is_idempotent() -> None:
    text = "$x^2 + y^2 = R^2 + 4\\pi$\n"
    once = clean(text)
    assert clean(once) == once


# ---- false math around a text-mode environment --------------------------------


def test_text_mode_environment_loses_its_math_delimiters() -> None:
    # `tabular` exists only in text mode.
    text = r"$\begin{tabular}{llll} $T$ a $ $ $ $$" + "\n"
    assert clean_in_place(text) == r"\begin{tabular}{llll} T a" + "\n"


def test_defused_line_does_not_swallow_a_later_formula() -> None:
    text = (
        "Intro line with plenty of words.\n\n"
        r"$\begin{tabular}{ll} a $$"
        "\n\nProse that must stay prose.\n\n$$E = mc^2$$\n"
    )
    cleaned = clean_in_place(text)
    assert "Prose that must stay prose." in cleaned
    assert "$$E = mc^2$$" in cleaned


def test_both_ends_of_a_multiline_false_block_are_defused() -> None:
    text = (
        "Intro line with plenty of words.\n\n"
        "$$\\begin{tabular}{ll}\na & b \\\\\n\\end{tabular}$$"
        "\n\nOutro line here.\n\n$$E = mc^2$$\n"
    )
    cleaned = clean_in_place(text)
    assert "$" not in cleaned.split("Outro")[0]
    assert "$$E = mc^2$$" in cleaned


def test_text_mode_environment_without_a_delimiter_is_left_alone() -> None:
    text = r"\begin{tabular}{ll} a b \end{tabular}" + "\n"
    assert clean_in_place(text) == text


def test_sound_formula_beside_raw_latex_prose_keeps_its_delimiters() -> None:
    text = r"Use \begin{tabular}{ll} when $n = 2$ holds." + "\n"
    assert clean_in_place(text) == text


def test_math_environment_keeps_its_delimiters() -> None:
    text = r"$$\begin{array}{cc} a & b \end{array}$$" + "\n"
    assert clean_in_place(text) == text


def test_quoted_text_mode_environment_is_not_defused() -> None:
    text = "A line with `$\\begin{tabular}{ll}` quoted in prose.\n"
    assert clean_in_place(text) == text


def test_escaped_dollar_survives_a_defused_line() -> None:
    text = r"$\begin{tabular}{ll} \$5 $" + "\n"
    assert clean_in_place(text) == r"\begin{tabular}{ll} \$5" + "\n"


def test_currency_dollars_are_not_defused() -> None:
    text = "Prices are $5 and $6 today.\n"
    assert clean_in_place(text) == text


def test_false_math_defusing_is_idempotent() -> None:
    text = r"$\begin{tabular}{llll} $T$ a $ $ $ $$" + "\n"
    once = clean(text)
    assert clean(once) == once


# ---- in-place fix: table math -------------------------------------------------


def test_bare_pipe_in_table_cell_math_is_escaped() -> None:
    text = (
        "| Formula | Image |\n"
        "|---|---|\n"
        r"| $$\left| \delta_{Smax} \right|$$ | pic |" + "\n"
    )
    expected = (
        "| Formula                            | Image |\n"
        "|------------------------------------|-------|\n"
        r"| $$\left\| \delta_{Smax} \right\|$$ | pic   |" + "\n"
    )
    assert clean_in_place(text) == expected


def test_fixed_table_math_row_is_no_longer_a_broken_table() -> None:
    text = (
        "| Formula | Image |\n"
        "|---|---|\n"
        r"| $$\left| \delta_{Smax} \right|$$ | pic |" + "\n"
    )
    expected = (
        "| Formula                            | Image |\n"
        "|------------------------------------|-------|\n"
        r"| $$\left\| \delta_{Smax} \right\|$$ | pic   |" + "\n"
    )
    assert clean(text) == expected  # no `broken-table` anchor added


def test_multiline_table_cell_formula_is_joined_onto_one_line() -> None:
    text = "\n".join(
        [
            r"| $$\left\{ \begin{array}{r}",
            r" \sigma_{\theta} = \sigma_{\theta}(\rho,z) \\",
            r" \end{array} \right.$$   | \(5\) |",
            "|------------------------|-------|",
            r"| $$\sigma_r$$ | \(6\) |",
            "",
        ]
    )
    expected = (
        r"| $$\left\{ \begin{array}{r} \sigma_{\theta} = "
        r"\sigma_{\theta}(\rho,z) \\ \end{array} \right.$$ | \(5\) |"
        "\n|" + "-" * 95 + "|-------|\n"
        r"| $$\sigma_r$$" + " " * 82 + r"| \(6\) |"
        "\n"
    )
    assert clean_in_place(text) == expected


def test_multiline_table_cell_keeps_a_standalone_row_separator() -> None:
    text = "\n".join(
        [
            r"| $$\begin{array}{r}",
            "a",
            "\\" * 2,
            "b",
            r"\end{array}$$ | 5 |",
            "|---|---|",
            "| $$c$$ | 6 |",
            "",
        ]
    )
    expected = (
        r"| $$\begin{array}{r} a " + "\\" * 2 + r" b \end{array}$$ | 5 |"
        "\n|" + "-" * 41 + "|---|\n| $$c$$" + " " * 35 + "| 6 |\n"
    )
    assert clean_in_place(text) == expected


def test_only_the_span_pipe_is_escaped_not_the_row_borders() -> None:
    text = r"| A | $$x|y$$ | B |" + "\n"
    assert clean_in_place(text) == r"| A | $$x\|y$$ | B |" + "\n"


def test_already_escaped_table_pipe_is_not_doubled() -> None:
    text = r"| $$\left\| x \right\|$$ | y |" + "\n"
    assert clean_in_place(text) == text


def test_inline_table_math_is_left_untouched() -> None:
    # A row's currency amounts pair into the same shape of false inline span.
    text = r"| $\left| x \right|$ | y |" + "\n|---|---|\n"
    assert clean_in_place(text) == text


def test_currency_amounts_in_separate_table_cells_are_untouched() -> None:
    text = "| A | $5 | $6 |\n|---|---|---|\n| B | $7 | $8 |\n"
    assert clean_in_place(text) == text


def test_table_math_same_shapes_outside_a_table_are_untouched() -> None:
    text = r"$$\left| x \right|$$" + "\n"
    assert clean_in_place(text) == text


def test_ordinary_multiline_display_math_outside_a_table_is_untouched() -> None:
    text = "$$\nx = y\n$$\n"
    assert clean_in_place(text) == text


def test_table_row_with_a_lost_closer_does_not_swallow_a_later_formula() -> None:
    # The blank line shows the pairing across rows is false.
    text = "\n".join(
        [
            r"| $$\left\{ \begin{array}{r}",
            "",
            "Some unrelated prose paragraph in between.",
            "",
            r"Real formula: $$y = x^2$$",
            "",
        ]
    )
    assert clean_in_place(text) == text


def test_table_row_with_a_lost_closer_does_not_swallow_the_next_row() -> None:
    # Adjacent rows have no blank line, so the paragraph-break guard misses this.
    text = "\n".join(
        [
            r"| $$a",
            r"| $$b$$ | c |",
            "",
        ]
    )
    assert clean_in_place(text) == text


def test_table_row_with_an_escaped_dollar_tail_is_left_for_anchoring() -> None:
    text = r"| $$x\$" + "\n"
    assert clean_in_place(text) == text


def test_table_math_fix_does_not_cross_a_code_fence() -> None:
    text = "```\n| $$\\left| x \\right|$$ | y |\n```\n"
    assert clean_in_place(text) == text


def test_table_math_fix_is_idempotent() -> None:
    text = "\n".join(
        [
            r"| $$\left\{ \begin{array}{r}",
            r" \sigma_{\theta} = \sigma_{\theta}(\rho,z) \\",
            r" \end{array} \right.$$   | \(5\) |",
            "|------------------------|-------|",
            "",
        ]
    )
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- in-place fix: single-glyph math spans -------------------------------------


def test_varnothing_unwraps_and_drops_its_trailing_separator_comment() -> None:
    text = "sleeve $\\varnothing$<!-- -->540x12,5 mm\n"
    assert clean_in_place(text) == "sleeve ∅540x12,5 mm\n"


def test_braced_circ_unwraps_to_degree_sign() -> None:
    text = "tilt angle 90${^\\circ}$\n"
    assert clean_in_place(text) == "tilt angle 90°\n"


def test_bare_circ_unwraps_to_degree_sign() -> None:
    assert clean_in_place("temperature 90$\\circ$C\n") == "temperature 90°C\n"


def test_already_bare_glyph_in_span_unwraps() -> None:
    text = "gradient 200$℃$\n"
    assert clean_in_place(text) == "gradient 200℃\n"


def test_leading_separator_comment_is_also_dropped() -> None:
    text = "text<!-- -->$\\varnothing$word\n"
    assert clean_in_place(text) == "text∅word\n"


def test_one_letter_variables_stay_math() -> None:
    text = r"$R$ $D$ $\theta$" + "\n"
    assert clean_in_place(text) == text


def test_span_longer_than_a_single_glyph_is_untouched() -> None:
    text = r"$\varnothing+1$" + "\n"
    assert clean_in_place(text) == text


def test_display_math_single_glyph_is_out_of_scope() -> None:
    text = "$$\\varnothing$$\n"
    assert clean_in_place(text) == text


def test_separator_comment_not_touching_an_unwrapped_span_is_untouched() -> None:
    text = "a<!-- -->b $R$\n"
    assert clean_in_place(text) == text


def test_single_glyph_math_in_code_fence_is_untouched() -> None:
    text = "```\n$\\varnothing$\n```\n"
    assert clean_in_place(text) == text


def test_single_glyph_math_quoted_in_code_span_is_untouched() -> None:
    text = "Printed as `$\\varnothing$` in the text.\n"
    assert clean_in_place(text) == text


def test_single_glyph_unwrap_is_idempotent() -> None:
    text = "sleeve $\\varnothing$<!-- -->540x12,5 mm\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_leading_latex_spacer_becomes_an_ordinary_space() -> None:
    text = "of size$\\ \\varnothing$<!-- -->168,3\n"
    assert clean_in_place(text) == "of size ∅168,3\n"


def test_trailing_latex_spacer_becomes_an_ordinary_space() -> None:
    text = "$\\varnothing\\quad$<!-- -->168,3\n"
    assert clean_in_place(text) == "∅ 168,3\n"


def test_latex_spacer_on_bare_glyph_also_unwraps() -> None:
    text = "gradient$\\,℃$200\n"
    assert clean_in_place(text) == "gradient ℃200\n"


def test_span_of_only_a_latex_spacer_does_not_unwrap_to_emptiness() -> None:
    # `\quad` has letters in its own command name, but the span still counts
    # as content-free.
    text = r"$\quad$" + "\n"
    assert clean_in_place(text) == text


def test_leading_spacer_unwrap_is_idempotent() -> None:
    text = "of size$\\ \\varnothing$<!-- -->168,3\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_leading_spacer_does_not_double_an_existing_space() -> None:
    text = "foo $\\ \\varnothing$ bar\n"
    assert clean_in_place(text) == "foo ∅ bar\n"


def test_trailing_spacer_does_not_double_an_existing_space() -> None:
    text = "foo $\\varnothing\\quad$ bar\n"
    assert clean_in_place(text) == "foo ∅ bar\n"


def test_leading_spacer_after_an_adjacent_unwrapped_span_still_gets_a_space() -> None:
    # The first unwrap consumes the separator comment, so `before` is empty.
    text = "$\\circ$<!-- -->$\\ \\varnothing$\n"
    assert clean_in_place(text) == "° ∅\n"


# ---- in-place fix: content-free math spans -------------------------------------


def test_a_run_of_a_spacing_command_with_nothing_else_is_dropped() -> None:
    # The unit has no alphanumeric character for the repetition trim to key on.
    text = "$" + "\\!" * 20 + "$\n"
    assert clean_in_place(text) == ""


def test_the_run_takes_its_surrounding_spacing_with_it() -> None:
    text = "The value $" + "\\!" * 6 + "$ here.\n"
    assert clean_in_place(text) == "The value here.\n"


def test_a_single_spacing_command_beside_real_content_is_untouched() -> None:
    text = r"$a\!b$" + "\n"
    assert clean_in_place(text) == text


def test_a_deliberate_operator_only_span_is_untouched() -> None:
    text = "The operator $+$ is used here.\n"
    assert clean_in_place(text) == text
    text = "Compare with $=$ here.\n"
    assert clean_in_place(text) == text


def test_content_free_span_drop_is_idempotent() -> None:
    text = "$" + "\\!" * 20 + "$\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- in-place fix: an unpaired sizing delimiter --------------------------------


def test_an_unpaired_right_gets_a_left_immediately_before_it() -> None:
    text = r"$a + b \right]$" + "\n"
    assert clean_in_place(text) == r"$a + b \left.\right]$" + "\n"


def test_an_unpaired_left_gets_a_right_at_the_content_end() -> None:
    text = r"$\left( a + b$" + "\n"
    assert clean_in_place(text) == r"$\left( a + b \right.$" + "\n"


def test_a_balanced_span_is_untouched() -> None:
    text = r"$\left( a \right)$" + "\n"
    assert clean_in_place(text) == text


def test_a_span_invalid_by_unbalanced_braces_is_untouched() -> None:
    text = r"$\left( x_{a \right)$" + "\n"
    assert clean_in_place(text) == text


def test_a_bare_unclosed_bracket_beside_the_fix_is_left_for_anchoring() -> None:
    text = r"$\left( [a$" + "\n"
    assert clean_in_place(text) == text


def test_unpaired_delimiter_closing_is_idempotent() -> None:
    text = r"$a + b \right]$" + "\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- in-place fix: an orphan sizing command ------------------------------------


def test_a_right_sizing_a_non_delimiter_is_dropped() -> None:
    text = r"$a \right x$" + "\n"
    assert clean_in_place(text) == r"$a x$" + "\n"


def test_an_orphan_left_is_dropped_beside_a_legitimate_pair() -> None:
    text = r"$\left \varphi \left( a \right) - b$" + "\n"
    assert clean_in_place(text) == r"$\varphi \left( a \right) - b$" + "\n"


def test_orphan_sizers_at_both_ends_of_a_span_are_dropped() -> None:
    text = r"$\left \frac{1}{k} \right$" + "\n"
    assert clean_in_place(text) == r"$\frac{1}{k}$" + "\n"


def test_a_named_delimiter_pair_survives_the_orphan_beside_it() -> None:
    text = r"$\left\langle \frac{a}{b} \right\rangle + \left x$" + "\n"
    expected = r"$\left\langle \frac{a}{b} \right\rangle + x$" + "\n"
    assert clean_in_place(text) == expected


def test_an_orphan_drop_leaving_a_bracket_open_is_left_for_anchoring() -> None:
    text = r"$a \right x + [b$" + "\n"
    assert clean_in_place(text) == text


def test_an_orphan_sizer_beside_lost_content_is_left_for_anchoring() -> None:
    text = r"$\left \varphi_{a$" + "\n"
    assert clean_in_place(text) == text


def test_orphan_sizer_drop_is_idempotent() -> None:
    text = r"$a \right x$" + "\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- in-place fix: an HTML tag inside a math span ------------------------------


def test_a_superscript_tag_inside_a_span_is_dropped() -> None:
    # marker writes a footnote star as `<sup>` inside the span.
    text = r"$<sup>^{\ast}</sup>$" + "\n"
    out = clean_in_place(text)
    assert out == r"$^{\ast}$" + "\n"
    assert is_valid_math(math_span_content(math_spans(out)[0]))


def test_a_tag_scrambled_across_the_delimiters_is_dropped() -> None:
    text = r"$<sup>^{\</sup>ast\ast}$" + "\n"
    out = clean_in_place(text)
    assert out == r"$^{\ast\ast}$" + "\n"
    assert is_valid_math(math_span_content(math_spans(out)[0]))


def test_a_math_root_tag_inside_a_span_is_dropped() -> None:
    text = "$<math>a + b</math>$\n"
    assert clean_in_place(text) == "$a + b$\n"


def test_a_display_span_tag_is_dropped() -> None:
    text = "$$<math>E = mc^2</math>$$\n"
    assert clean_in_place(text) == "$$E = mc^2$$\n"


def test_a_tag_outside_a_span_is_left_alone() -> None:
    text = r"$<sup>x</sup>$ and y<sup>2</sup> in the text." + "\n"
    assert clean_in_place(text) == r"$x$ and y<sup>2</sup> in the text." + "\n"


def test_a_span_with_no_tag_is_byte_for_byte_the_same() -> None:
    text = r"$x^{2} + y_{1}$" + "\n"
    assert clean_in_place(text) == text


def test_a_span_left_empty_by_the_strip_is_kept() -> None:
    text = "$<math></math>$\n"
    assert clean_in_place(text) == text


def test_a_tag_in_a_protected_zone_is_kept() -> None:
    text = "```\n$<sup>x</sup>$\n```\n"
    assert clean_in_place(text) == text


def test_math_span_tag_strip_is_idempotent() -> None:
    text = r"$<sup>^{\ast}</sup>$" + "\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- in-place fix: a span glued to the digit beside it --------------------------


def test_separates_a_span_from_the_digit_before_it() -> None:
    # A math plugin does not open a span on a `$` right after an alphanumeric.
    text = "Wall no thicker than 3$S$ in the weld zone.\n"
    assert clean_in_place(text) == "Wall no thicker than 3 $S$ in the weld zone.\n"


def test_separates_a_span_from_the_digit_after_it() -> None:
    text = "The value $S_{2}$3 in the table.\n"
    assert clean_in_place(text) == "The value $S_{2}$ 3 in the table.\n"


def test_keeps_two_printed_amounts_of_one_sentence() -> None:
    text = "Cost 5$ and 6$ in prose.\n"
    assert clean_in_place(text) == text


def test_keeps_a_span_whose_content_holds_a_space() -> None:
    text = r"Spread 3$ \pm 20$ along the length." + "\n"
    assert clean_in_place(text) == text


def test_keeps_a_span_glued_to_a_word() -> None:
    # The plugin refusal is ASCII only; a Cyrillic letter before `$` is fine.
    text = r"Снижение износа$\delta_{S}$ при нагрузке." + "\n"
    assert clean_in_place(text) == text


def test_separates_an_exponent_from_the_mantissa_before_it() -> None:
    text = "Limit 10$^{-3}$ on the flow.\n"
    assert clean_in_place(text) == "Limit 10 $^{-3}$ on the flow.\n"


def test_keeps_a_range_of_printed_amounts() -> None:
    text = "Range $5-$6 per unit.\n"
    assert clean_in_place(text) == text


def test_keeps_a_range_whose_sign_stands_behind_the_number() -> None:
    text = "Price 5$-6$ per unit.\n"
    assert clean_in_place(text) == text


def test_keeps_a_delimiter_pair_inside_a_link_target() -> None:
    text = "See [the file](files/3$x$.pdf) for it.\n"
    assert clean_in_place(text) == text


def test_separating_a_glued_span_is_idempotent() -> None:
    once = clean_in_place("No more than 3$S$ in the zone.\n")
    assert clean_in_place(once) == once
