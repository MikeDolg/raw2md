"""Tests for the inspection edit guard: the bans and the licence of the markup."""

from __future__ import annotations

from raw2md.llm.edit_guard import display_tail_fold, rejection_reason
from raw2md.source_text import SourceText

# In-word breaks a model writes, spelled out because none shows what it is: a
# non-breaking hyphen, a soft hyphen, the typographic hyphen, an en dash.
CRUSHED = (
    "Property Quantity Velocity extreme Temperature lowest Pressure average "
    "Supply continuous Torque changeable"
)

NON_BREAKING_HYPHEN = "\u2011"
SOFT_HYPHEN = "\u00ad"
HYPHEN = "\u2010"
EN_DASH = "\u2013"


def allowed(
    old: str,
    new: str,
    source_text: SourceText | None = None,
    source_page: int | None = None,
) -> bool:
    return rejection_reason(old, new, source_text, source_page) is None


# --- bans that hold for every edit ------------------------------------------


def test_rewritten_image_target_refused() -> None:
    old = "![](media/_page_300_Figure_2.jpeg)"
    new = "![](media/_page_301_Figure_2.jpeg)"
    assert rejection_reason(old, new) == "image links changed"


def test_dropped_image_link_refused() -> None:
    # A removed link leaves nothing broken behind, so the count is held.
    old = "See ![](media/fig.jpeg) for the layout."
    new = "See the layout."
    assert rejection_reason(old, new) == "image links changed"


def test_swapped_image_targets_refused() -> None:
    # The set of links is the same, so the order has to be compared.
    old = "![](media/fig_1.jpeg) ![](media/fig_2.jpeg)"
    new = "![](media/fig_2.jpeg) ![](media/fig_1.jpeg)"
    assert rejection_reason(old, new) == "image links changed"


def test_html_img_src_is_covered() -> None:
    old = '<img src="media/fig.png" width="200" />'
    new = '<img src="media/other.png" width="200" />'
    assert rejection_reason(old, new) == "image links changed"


def test_edit_beside_an_image_link_allowed() -> None:
    old = "Figure 1. Layout ![](media/fig.jpeg) of the devise"
    new = "Figure 1. Layout ![](media/fig.jpeg) of the device"
    assert allowed(old, new)


def test_literal_escape_refused() -> None:
    old = "| Gain | 9 |"
    new = r"| Gain | 9 |\n| Offset | 8 |"
    assert rejection_reason(old, new) == "literal escape sequence"


def test_latex_command_is_not_read_as_an_escape() -> None:
    # These commands begin with an escape letter and are no lost line break.
    old = r"Let $\nu \to \rho$ and $x \times y$ be given."
    new = r"Let $\nu \to \rho$ and $x \times y$ be found."
    assert allowed(old, new)


def test_pre_existing_escape_does_not_block_an_unrelated_edit() -> None:
    # The ban is on introducing the sequence, not on a line that has one.
    old = r"A line already carrying a \n trace and a typo of it's own."
    new = r"A line already carrying a \n trace and a typo of its own."
    assert allowed(old, new)


def test_protocol_object_refused() -> None:
    old = "The part is delivered separately."
    new = '{"line": 385, "flag": "hyphenation"}'
    assert rejection_reason(old, new) is not None


def test_protocol_fragment_inside_prose_refused() -> None:
    old = "The part is delivered separately."
    new = 'The part {"old": "x", "new": "y"} separately.'
    assert rejection_reason(old, new) == "protocol object in the replacement"


def test_json_like_prose_without_protocol_keys_refused() -> None:
    # Any whole JSON container is protocol residue, whatever its keys.
    old = "The part is delivered separately."
    new = '{"a": 1}'
    assert rejection_reason(old, new) == "replacement parses as json"


def test_defect_name_as_replacement_refused() -> None:
    # The model answered with the defect it saw instead of a repair.
    old = "Nu ="
    new = "broken-formula"
    assert rejection_reason(old, new) == "defect name as the replacement"


def test_defect_name_the_tool_does_not_use_refused() -> None:
    # A name composed to the pattern, not taken from the vocabulary.
    old = "- emission (Probe"
    new = "broken-block"
    assert rejection_reason(old, new) == "defect name as the replacement"


def test_defect_name_replacing_punctuation_refused() -> None:
    # A short line gives no digit, span, or link to compare.
    old = ","
    new = "flattened-block"
    assert rejection_reason(old, new) == "defect name as the replacement"


def test_defect_name_inside_prose_allowed() -> None:
    # A hyphenated word in ordinary text is not a bare name.
    old = "The plug-and-play link needs no setnp."
    new = "The plug-and-play link needs no setup."
    assert allowed(old, new)


def test_hyphenated_repair_of_a_longer_line_allowed() -> None:
    old = "The read-onlу valve opens by hand."  # noqa: RUF001
    new = "The read-only valve opens by hand."
    assert allowed(old, new)


def test_defect_name_already_in_the_body_may_be_repaired() -> None:
    # Putting text back over a leaked name must stay possible.
    old = "broken-formula"
    new = "Nu ="
    assert allowed(old, new)


def test_changed_number_refused() -> None:
    old = "Diameter 120 mm at length 300 mm."
    new = "Diameter 120 mm at length 800 mm."
    assert rejection_reason(old, new) == "digit runs changed"


def test_added_number_refused() -> None:
    old = "Diameter is shown in the plan."
    new = "Diameter 120 mm is shown in the plan."
    assert rejection_reason(old, new) == "digit runs changed"


def test_case_of_a_part_code_may_be_fixed() -> None:
    # Only the digit runs are held; the letters of a code stay repairable.
    assert allowed("Item wsm-200 in stock.", "Item WSM-200 in stock.")


def test_valid_math_span_may_not_be_rewritten() -> None:
    # The rewrite renders as cleanly as the original; only a condemned span is
    # open.
    old = r"Then $E = mc^2$ and so on."
    new = r"Then $E = mc^{2}$ and so on."
    assert rejection_reason(old, new) == "valid math span changed"


def test_broken_math_span_may_be_repaired_without_an_anchor() -> None:
    # `\left` without `\right` condemns the span on its own, and the
    # backslash-outside-math ban does not reach into a condemned span either.
    old = r"Then $\left( x + y$ below."
    new = r"Then $\left( x + y \right)$ below."
    assert allowed(old, new)


def test_repair_that_leaves_the_span_broken_refused() -> None:
    old = r"Then $\left( x$ below."
    new = r"Then $\frac{x}{$ below."
    assert rejection_reason(old, new) == "rebuilt math span still broken"


def test_math_edit_reaching_into_the_prose_refused() -> None:
    # The span repair is licensed; the words beside it are a second edit.
    old = r"The value $\left( x$ is found."
    new = r"The value $\left( x \right)$ is computed."
    assert rejection_reason(old, new) == ("edit changes math and the text around it")


def test_repair_of_a_broken_span_may_not_invent_a_number() -> None:
    old = r"Then $\left( x$ below."
    new = r"Then $x_{12}$ below."
    assert rejection_reason(old, new) == "digit runs added"


def test_looping_span_counts_as_broken_though_it_balances() -> None:
    # A loop balances, so validity alone would freeze it.
    old = r"Then $x_1+x_1+x_1+x_1+x_1+x_1+x_1$ below."
    new = r"Then $x_1 + y$ below."
    assert allowed(old, new)


def test_span_with_a_split_index_may_be_repaired() -> None:
    # Spacing inside an index prints nothing, so a split index is an artifact.
    old = r"The moment $M_{y  n  1}$ is set."
    new = r"The moment $M_{yn1}$ is set."
    assert allowed(old, new)


def test_repair_leaving_the_index_split_refused() -> None:
    # One run of spaces is left, so the span still reads as split.
    old = r"The moment $M_{y  n  1}$ is set."
    new = r"The moment $M_{y  n1}$ is set."
    assert rejection_reason(old, new) == "rebuilt math span still broken"


def test_index_with_a_single_space_is_not_split() -> None:
    # One space in a compound subscript is deliberate; only a run of spaces is
    # the artifact.
    old = r"Then $F_{z n1} = 1$ and so on."
    new = r"Then $F_{z n2} = 1$ and so on."
    assert rejection_reason(old, new) == "valid math span changed"


# One display formula cut into a damaged span per line: only together do the
# pieces balance.
CUT_FORMULA = "\n".join(
    [
        r"$$S = \frac{1}{2}\left[\left(\begin{aligned} p_{k}\right)^2$$",
        r"$$+ \left(q_{k}\right)^2\right]$$",
    ]
)


def test_a_formula_cut_across_lines_is_judged_assembled() -> None:
    # Piece by piece the first line is unbalanced; as one formula it balances.
    new = "\n".join(
        [
            r"$$S = \frac{1}{2}\left[\left(p_{k}\right)^2$$",
            r"$$+ \left(q_{k}\right)^2\right]$$",
        ]
    )
    assert allowed(CUT_FORMULA, new)


def test_a_cut_formula_still_unbalanced_after_the_repair_refused() -> None:
    new = "\n".join(
        [
            r"$$S = \frac{1}{2}\left[\left(p_{k}\right)^2$$",
            r"$$+ \left(q_{k}\right)^2$$",
        ]
    )
    assert rejection_reason(CUT_FORMULA, new) == ("rebuilt math span still broken")


def test_a_cut_formula_may_not_be_fused_into_one_span() -> None:
    # Without one-to-one spans there is nothing to judge against.
    new = r"$$S = \frac{1}{2}\left[\left(p_{k}\right)^2 + \left(q_{k}\right)^2\right]$$"
    assert rejection_reason(CUT_FORMULA, new) == "math span count changed"


def test_a_cut_formula_may_not_gain_prose() -> None:
    new = "\n".join(
        [
            r"Then $$S = \frac{1}{2}\left[\left(p_{k}\right)^2$$",
            r"$$+ \left(q_{k}\right)^2\right]$$",
        ]
    )
    assert rejection_reason(CUT_FORMULA, new) == (
        "edit changes math and the text around it"
    )


def test_a_sound_span_beside_a_cut_formula_is_not_read_as_a_piece_of_it() -> None:
    # The second line balances on its own, so the pair is judged span by span.
    old = "\n".join([r"$$S = \left[ p_{k}$$", r"$$E = mc^2$$"])
    new = "\n".join([r"$$S = \left[ p_{k} \right]$$", r"$$E = mc^{2}$$"])
    assert rejection_reason(old, new) == "valid math span changed"


def test_span_whose_spaces_lie_outside_its_index_may_not_be_rewritten() -> None:
    # A space beside an operator is the author's formatting.
    old = r"The sum $\sum_{i = 1}^{n} x_{i}$ is given."
    new = r"The sum $\sum_{i = 1}^{n} y_{i}$ is given."
    assert rejection_reason(old, new) == "valid math span changed"


def test_sizing_command_with_no_delimiter_may_be_repaired() -> None:
    # `\left`/`\right` pair by count, so a dropped bracket still balances.
    old = r"Then $F = \left  F_{y} + C \right$ below."
    new = r"Then $F = \left( F_{y} + C \right)$ below."
    assert allowed(old, new)


def test_delimiter_that_prints_nothing_leaves_the_span_valid() -> None:
    # `\left\{ ... \right.` is how a system of equations closes.
    old = r"The system $\left\{ x = y \right.$ is given."
    new = r"The system $\left\{ x = z \right.$ is given."
    assert rejection_reason(old, new) == "valid math span changed"


def test_delimiter_written_under_another_name_leaves_the_span_valid() -> None:
    # A renderer accepts several names for the same bracket.
    old = r"The brackets $\left\lparen x = y \right\rparen$ are given."
    new = r"The brackets $\left\lparen x = z \right\rparen$ are given."
    assert rejection_reason(old, new) == "valid math span changed"


def test_word_repair_beside_a_valid_formula_allowed() -> None:
    assert allowed(r"Let $\alpha$ be set.", r"Let $\alpha$ be fixed.")


def test_prose_may_be_carried_out_of_a_span() -> None:
    # A swallowed word leaves the span; no symbol of the content changes.
    old = r"Then $Value x = 5$ is found."
    new = r"Then Value $x = 5$ is found."
    assert allowed(old, new)


def test_prose_carried_out_of_a_span_may_hold_a_number() -> None:
    # The number crosses from math into prose unchanged.
    old = r"$Figure 2 x$ given"
    new = r"Figure 2 $x$ given"
    assert allowed(old, new)


def test_delimiter_move_may_not_smuggle_a_changed_symbol() -> None:
    old = r"Then $Value x = 5$ is found."
    new = r"Then Value $x = 6$ is found."
    assert not allowed(old, new)


def test_delimiters_may_not_walk_onto_other_content() -> None:
    # Tokens and delimiter count hold, but the pair moved onto another word.
    old = "Current $x$ grows"
    assert not allowed(old, "Current x $grows$")
    assert not allowed(old, "$Current x grows$")


def test_index_may_not_borrow_a_digit_from_the_prose() -> None:
    # The prose number must not pay for the changed index.
    old = r"Formula 2: $\left(x_1$"
    new = r"Formula 2: $x_2$"
    assert rejection_reason(old, new) == "digit runs added"


def test_delimiters_may_not_be_stripped_altogether() -> None:
    # Every token survives; only the delimiter count refuses the raw LaTeX.
    old = r"Then $\frac{a}{b}$ is found."
    new = r"Then \frac{a}{b} is found."
    assert rejection_reason(old, new) == "math span count changed"


def test_delimiters_may_not_be_left_unpaired() -> None:
    # The count and tokens hold, but the formula dissolved into prose.
    assert rejection_reason("$x$ given", "x $$ given") == ("math span count changed")


def test_delimiters_may_not_be_left_empty() -> None:
    # The pair still parses as a span; only its soundness refuses it.
    assert not allowed("$x$ given", "$ $ x given")


def test_escaped_currency_is_not_a_delimiter() -> None:
    # `\$` is currency, so this is a prose change, not a delimiter move.
    old = r"Price \$5 per piece."
    new = r"Price \$5 per pair."
    assert allowed(old, new)
    assert rejection_reason(old, r"Price \$6 per piece.") == ("digit runs changed")


def test_math_number_outside_a_span_is_still_held() -> None:
    # The weaker digit rule covers spans only, not the prose of the line.
    old = r"Figure 3 sets $\alpha$."
    new = r"Figure sets $\alpha$."
    assert rejection_reason(old, new) == "digit runs changed"


def test_table_row_narrowed_without_an_anchor_refused() -> None:
    # Merging two cells changes the width, and nothing licenses a recut.
    old = "| A | B | C |"
    new = "| A | B and C |"
    assert rejection_reason(old, new) == "table cell count changed"


def test_table_separator_narrowed_refused() -> None:
    # The separator declares the width every body row is measured against.
    old = "| --- | --- | --- | --- | --- | --- | --- |"
    new = "| --- | --- | --- | --- | --- | --- |"
    assert rejection_reason(old, new) == "table cell count changed"


def test_table_edit_inside_a_cell_allowed() -> None:
    assert allowed("| velocity | small |", "| velocity | large |")


def test_table_cell_count_change_refused_on_a_standing_row() -> None:
    # Recutting a grid is post's repair; inspection may not change the count.
    reason = rejection_reason("| A B |", "| A | B |")
    assert reason == "table cell count changed"


def test_rebuild_of_a_crushed_row_may_change_its_cell_count() -> None:
    # The crushed line has a stray pipe; the content check bounds the rebuild.
    old = CRUSHED.replace("Quantity", "Quantity |")
    new = (
        "| Property | Quantity |\n| Velocity extreme | Temperature lowest |\n"
        "| Pressure average | Supply continuous |\n| Torque changeable |"
    )
    assert allowed(old, new)


def test_a_standing_row_is_never_read_as_crushed() -> None:
    # A line that shows its grid borders keeps its width.
    reason = rejection_reason("| A | B |", "| A B |")
    assert reason == "table cell count changed"


def test_edit_that_matches_a_neighbouring_cell_refused() -> None:
    # An errata row holds a misprint beside its correction; making them match
    # erases the row's point.
    old = "| the Bnidge. | the Bridge. |"
    new = "| the Bridge. | the Bridge. |"
    assert rejection_reason(old, new) == "edit made a row's cells match"


def test_edit_leaving_cells_different_allowed() -> None:
    old = "| the Bnidge. | the Bridge. |"
    new = "| the Bnidqe. | the Bridge. |"
    assert allowed(old, new)


def test_row_that_already_repeated_a_value_stays_unaffected() -> None:
    # The cells matched before the edit too.
    old = "| DUP | DUP |"
    new = "| DUQ | DUQ |"
    assert allowed(old, new)


def test_prose_and_a_pipe_free_line_unaffected_by_the_collision_ban() -> None:
    assert allowed("Here a typo.", "Here an error.")
    assert allowed("Table caption without any cells.", "Table caption fixed.")


def test_display_delimiter_added_refused() -> None:
    old = "As shown below."
    new = "$$"
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_display_delimiter_removed_refused() -> None:
    old = "$$"
    new = "Formula below."
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_display_delimiter_line_left_alone_allowed() -> None:
    assert allowed("$$", "$$")


def test_display_delimiter_stamped_beside_a_list_marker_refused() -> None:
    # The delimiter shares its line with text, so a count of bare `$$` lines
    # misses it, and every later pair closes against the wrong partner.
    old = "1)"
    new = "1) $$"
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_inline_opener_without_its_closer_refused() -> None:
    # An unclosed inline span runs to the end of the body.
    old = "dA = outer diameter"
    new = "$d_{A} = outer diameter"
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_display_delimiter_traded_for_an_inline_one_refused() -> None:
    # Both counts turn odd at once.
    reason = rejection_reason("$$", "$")
    assert reason == "math delimiter parity changed"


def test_a_closed_inline_pair_added_keeps_the_parity() -> None:
    # Both delimiters arrive together, so the span count refuses it, not this
    # ban.
    old = "dA = outer diameter"
    new = "$d_{A}$ = outer diameter"
    assert rejection_reason(old, new) == "math span count changed"


def test_a_printed_dollar_is_not_a_delimiter() -> None:
    # `\$` is printed currency, not a delimiter.
    old = "Price 5\\$ per piece"
    new = "Price 5\\$ per unit"
    assert allowed(old, new)


def test_a_delimiter_glued_into_a_word_refused() -> None:
    # A display block never opens mid-word, so `a$$b` is no delimiter.
    reason = rejection_reason("$$", "a$$b")
    assert reason == "math delimiter parity changed"


def test_a_repair_that_drops_the_closing_delimiter_refused() -> None:
    # The trailing backslash reads as math, which hides the missing closer
    # from every other ban.
    old = r"Formula $\left(x$"
    new = r"Formula $x + \alpha"
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_a_dollar_behind_an_escaped_backslash_is_a_delimiter() -> None:
    # The first backslash escapes the second, so the `$` is active.
    old = r"a \\ b"
    new = r"a \\$ b"
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_a_delimiter_traded_for_a_quoted_one_refused() -> None:
    # Backticks print the dollars, so the display block loses its opener.
    reason = rejection_reason("$$", "`$$`")
    assert reason == "math delimiter parity changed"


def test_a_code_span_may_gain_a_dollar() -> None:
    # A dollar inside backticks opens no span.
    old = "The path comes from `HOME`."
    new = "The path comes from `$HOME`."
    assert allowed(old, new)


def test_a_printed_dollar_losing_its_escape_refused() -> None:
    # A dropped escape leaves a dollar that opens an unclosed span.
    old = "Price 5\\$ per piece"
    new = "Price 5$ per unit"
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_display_delimiter_unpaired_inside_multiline_replacement_refused() -> None:
    # Parity is checked before the shape: a bare `$$` line pairs with nothing.
    old = "Formula: A B"
    new = "Formula: A\n$$\nB"
    reason = rejection_reason(old, new)
    assert reason == "math delimiter parity changed"


def test_display_block_may_not_be_laid_out_across_lines() -> None:
    # Parity holds, but a line that carries math is structure, not a crushed
    # run.
    old = "$$ E = mc^2 $$"
    new = "$$\nE = mc^2\n$$"
    assert rejection_reason(old, new) == "multi-line replacement"


def test_multi_line_replacement_refused_on_an_ordinary_line() -> None:
    assert rejection_reason("One line of prose.", "One line\nof prose.") == (
        "multi-line replacement"
    )


# --- a display line keeps its closing delimiter ------------------------------


def test_prose_behind_the_closing_delimiter_refused() -> None:
    # The span still parses, but the tail takes away the closer.
    old = "$$v = 12$$"
    new = "$$v = 12$$ m/s"
    assert rejection_reason(old, new) == "text behind the closing display delimiter"


def test_a_sentence_mark_behind_the_closer_is_placed_inside_the_span() -> None:
    # The mark closes the formula's sentence, so the guard folds it inside.
    old = "$$x = a$$"
    new = "$$x = a$$."
    assert allowed(old, new)
    assert display_tail_fold(old, new) == "$$x = a.$$"


def test_the_fold_keeps_the_equation_number_last() -> None:
    # The tag prints where the formula ends, so the mark goes before it.
    old = r"$$x = a \tag{12}$$"
    new = r"$$x = a \tag{12}$$,"
    assert display_tail_fold(old, new) == r"$$x = a, \tag{12}$$"


def test_a_mark_the_formula_already_ends_with_refused() -> None:
    # The span already ends on the mark; folding would print it twice.
    old = "$$x = a;$$"
    new = "$$x = a;$$;"
    assert display_tail_fold(old, new) is None
    assert rejection_reason(old, new) == "text behind the closing display delimiter"


def test_a_mark_on_its_own_line_is_not_this_fold() -> None:
    # A closer on another line is refused, not folded.
    old = "$$x = a$$"
    new = "$$x = a$$\n."
    assert display_tail_fold(old, new) is None
    assert rejection_reason(old, new) == "text behind the closing display delimiter"


def test_a_line_that_already_carried_a_tail_is_not_held_to_the_shape() -> None:
    # The tail is the line's own, not the edit's.
    old = "$$x = a$$ кгс"
    new = "$$x = a$$ kgf"
    assert allowed(old, new)


def test_unwrapping_a_false_formula_is_left_to_the_math_bans() -> None:
    # No closer is left, so the span count answers instead.
    old = "$$Table 5$$"
    new = "Table 5"
    assert rejection_reason(old, new) == "math span count changed"


# --- an insertion beside an untouched span may not repeat its content -------


def test_insertion_of_a_unit_the_span_already_carries_refused() -> None:
    # Every other ban is silent; only this one compares the span's content
    # with what landed beside it.
    old = r"Length is 40 $\mathrm{mm}$ total."
    new = r"Length is 40 mm $\mathrm{mm}$ total."
    assert rejection_reason(old, new) == "insertion duplicates a neighbouring span"


def test_insertion_of_a_word_absent_from_the_span_allowed() -> None:
    old = r"Length is 40 $\mathrm{mm}$ total."
    new = r"Length is exactly 40 $\mathrm{mm}$ total."
    assert allowed(old, new)


def test_prose_edit_away_from_the_span_unaffected() -> None:
    # The edit lands mid-segment, not flush against the span.
    old = r"The mm is a unit. $\mathrm{mm}$ end."
    new = r"The mm is a common unit. $\mathrm{mm}$ end."
    assert allowed(old, new)


def test_comparison_reads_the_spans_rendered_content_not_its_source() -> None:
    # `\left` is a command, not a word the span renders.
    old = r"See $\left(x\right)$ below."
    new = r"See left $\left(x\right)$ below."
    assert allowed(old, new)


def test_word_split_without_a_witness_refused() -> None:
    # Nothing confirms either half is a word of its own.
    old = "The handbook is open."
    new = "The hand book is open."
    reason = rejection_reason(old, new)
    assert reason == "word split without a source witness"


def test_word_split_confirmed_by_the_source_witness_allowed() -> None:
    # The source's text layer attests both halves.
    old = "The handbook is open."
    new = "The hand book is open."
    witness = SourceText(["hand book"])
    assert allowed(old, new, witness)


def test_word_split_witness_is_scoped_to_the_edit_page() -> None:
    # The halves are attested only on a page the address does not name.
    old = "The handbook is open."
    new = "The hand book is open."
    witness = SourceText(["nothing relevant here", "hand book"])
    assert not allowed(old, new, witness, 0)


def test_word_split_witness_confirmed_on_its_own_page_allowed() -> None:
    old = "The handbook is open."
    new = "The hand book is open."
    witness = SourceText(["nothing relevant here", "hand book"])
    assert allowed(old, new, witness, 1)


def test_word_join_needs_no_witness() -> None:
    # The ban is one-way: joining a split is not its business.
    assert allowed("hand book is open", "handbook is open")


def test_absent_witness_does_not_refuse_an_unrelated_edit() -> None:
    assert allowed("Here a typo.", "Here an error.")


def test_word_split_already_present_in_old_does_not_block_an_unrelated_edit() -> None:
    # The split was on the line already.
    old = "Here hand book and handbook: a typo."
    new = "Here hand book and handbook: an error."
    assert allowed(old, new)


def test_second_split_beyond_what_old_already_had_still_refused() -> None:
    # The first split was in `old`; the second is new and not exempt.
    old = "hand book handbook"
    new = "hand book hand book"
    reason = rejection_reason(old, new)
    assert reason == "word split without a source witness"


def test_word_split_with_a_case_change_still_refused() -> None:
    # Tokens are case-folded as the witness reads them.
    old = "Handbook is open."
    new = "hand book is open."
    reason = rejection_reason(old, new)
    assert reason == "word split without a source witness"


def test_non_breaking_hyphen_inside_a_whole_word_refused() -> None:
    # The model writes the printed page's break into a whole word.
    old = "The module is designed for mounting."
    new = "The module is desig" + NON_BREAKING_HYPHEN + "ned for mounting."
    assert rejection_reason(old, new) == "word break without a witness"


def test_soft_hyphens_inside_a_whole_word_refused() -> None:
    # Cleaning strips soft hyphens, so writing them back is refused.
    old = "The valve withstands the load."
    new = "The valve with" + SOFT_HYPHEN + "stan" + SOFT_HYPHEN + "ds the load."
    assert rejection_reason(old, new) == "word break without a witness"


def test_hyphen_and_en_dash_inside_a_whole_word_refused() -> None:
    for break_char in (HYPHEN, EN_DASH):
        old = "A cosmetic defect remains."
        new = f"A cos{break_char}metic defect remains."
        assert rejection_reason(old, new) == "word break without a witness"


def test_control_character_inside_a_whole_word_refused() -> None:
    # The parser decodes the escape, so the control character lands mid-word.
    old = "The cylinder wall is thin."
    new = "The cyl\x10inder wall is thin."
    assert rejection_reason(old, new) == "word break without a witness"


def test_hyphen_attested_by_the_body_allowed() -> None:
    # The body spells the compound with a hyphen that conversion dropped.
    old = "A costeffective solution."
    new = "A cost-effective solution."
    body = frozenset({"cost-effective"})
    assert rejection_reason(old, new, None, None, body) is None


def test_hyphen_attested_by_the_source_layer_allowed() -> None:
    old = "A costeffective solution."
    new = "A cost-effective solution."
    witness = SourceText(["The cost-effective option was taken."])
    assert allowed(old, new, witness)


def test_line_break_hyphen_of_the_source_attests_nothing() -> None:
    # A break at the end of a printed line is layout, not a spelling.
    old = "A costeffective solution."
    new = "A cost-effective solution."
    witness = SourceText(["The cost-\neffective option was taken."])
    reason = rejection_reason(old, new, witness)
    assert reason == "word break without a witness"


def test_witness_for_the_plain_hyphen_does_not_attest_another_break() -> None:
    # The joining character is part of the spelling.
    old = "A costeffective solution."
    new = "A cost" + NON_BREAKING_HYPHEN + "effective solution."
    body = frozenset({"cost-effective"})
    reason = rejection_reason(old, new, None, None, body)
    assert reason == "word break without a witness"


def test_witness_for_one_typographic_hyphen_does_not_attest_the_other() -> None:
    # NFKC folds the halves but not the break character.
    old = "A costeffective solution."
    new = "A cost" + HYPHEN + "effective solution."
    witness = SourceText(["A cost" + NON_BREAKING_HYPHEN + "effective option."])
    reason = rejection_reason(old, new, witness)
    assert reason == "word break without a witness"


def test_hyphen_dropped_from_a_compound_unaffected() -> None:
    # The ban is one-way: a word losing its break is not its business.
    assert allowed("Нагруз-ки растут.", "Нагрузки растут.")


def test_edit_beside_a_hyphenated_word_the_line_already_had_allowed() -> None:
    old = "Seal o-ring and oring: a typo."
    new = "Seal o-ring and oring: an error."
    assert allowed(old, new)


def test_second_break_beyond_what_old_already_had_still_refused() -> None:
    old = "o-ring oring"
    new = "o-ring o-ring"
    assert rejection_reason(old, new) == "word break without a witness"


def test_minus_sign_inside_a_condemned_formula_unaffected() -> None:
    # Inside a span a dash is a minus sign.
    old = "$$M_{y  n  1} = ab$$"
    new = "$$M_{yn1} = a-b$$"
    assert allowed(old, new)


def test_heading_marker_removed_refused() -> None:
    old = "## Further reading"
    new = "Further reading"
    assert rejection_reason(old, new) == "heading marker removed"


def test_heading_marker_added_refused() -> None:
    old = "Further reading"
    new = "## Further reading"
    assert rejection_reason(old, new) == "heading marker added"


def test_heading_marker_removal_refused_on_a_hyphenated_line() -> None:
    # Joining the word is a repair; stripping the marker is not licensed.
    old = "## General de-tails"
    new = "General details"
    assert rejection_reason(old, new) == "heading marker removed"


def test_heading_text_edit_with_marker_kept_allowed() -> None:
    assert allowed("## Genaral details", "## General details")


def test_prose_edit_without_a_heading_marker_unaffected() -> None:
    assert allowed("Some line of text.", "Some corrected line.")


def test_heading_marker_ban_steps_aside_for_a_rebuild() -> None:
    # A rebuild of a crushed run may restore `#` with the rest of its markup.
    old = CRUSHED
    new = "# Property\n" + CRUSHED.replace("Property ", "")
    assert allowed(old, new)


def test_latex_command_introduced_in_prose_refused() -> None:
    old = "QX4***"
    new = r"QX4\textsuperscript{\textasteriskcentered}"
    assert rejection_reason(old, new) == "backslash command added outside math"


def test_line_break_written_as_double_backslash_refused() -> None:
    old = "Resin grade TU 90 A"
    new = "Resin grade TU 90 A\\\\"
    assert rejection_reason(old, new) == "backslash command added outside math"


def test_already_present_escaped_dollar_stays_allowed() -> None:
    assert allowed(r"Price \$100 per piece.", r"Price \$100 per pack.")


def test_already_present_backslash_command_may_persist() -> None:
    old = r"The line carries \foo and the rest of the text."
    new = r"The line carries \foo and other text."
    assert allowed(old, new)


def test_backslash_command_duplicated_beyond_the_original_refused() -> None:
    old = r"The value \alpha is given."
    new = r"The value \alpha \alpha is given."
    assert rejection_reason(old, new) == "backslash command added outside math"


def test_escape_swapped_for_an_unrelated_command_refused() -> None:
    # One escape traded for one command keeps a plain count steady.
    old = r"Price \$100 per piece."
    new = r"Price \textsuperscript{100} per piece."
    assert rejection_reason(old, new) == "backslash command added outside math"


def test_raw_latex_delimited_span_may_be_rewritten() -> None:
    # `\(...\)` is pandoc's math delimiter, so a symbol swap inside is math.
    old = r"Let \(\alpha\) follow."
    new = r"Let \(\beta\) follow."
    assert allowed(old, new)


def test_command_outside_a_raw_latex_span_still_counted() -> None:
    # The exclusion covers only the delimited zone.
    old = r"Let \(\alpha\) follow."
    new = r"Let \(\alpha\) \beta follow."
    assert rejection_reason(old, new) == "backslash command added outside math"


def test_wrapping_prose_in_a_fresh_raw_latex_span_refused() -> None:
    # A new zone is not exempt, or wrapping a word would launder a command.
    old = "Let alpha follow."
    new = r"Let \(\alpha\) follow."
    assert rejection_reason(old, new) == "backslash command added outside math"


# --- inline markup (<sub>/<sup>) held ----------------------------------------


def test_dropped_subscript_refused() -> None:
    old = "CO<sub>2</sub>, NO, SO<sub>2</sub>, NH<sub>3</sub>, H<sub>2</sub>O"
    new = "CO2, NO, SO2, NH3, H2O"
    assert rejection_reason(old, new) == "inline markup changed"


def test_added_superscript_refused() -> None:
    old = "1) Applies to a static load"
    new = "<sup>1)</sup> Applies to a static load"
    assert rejection_reason(old, new) == "inline markup changed"


def test_subscript_relocated_to_a_different_word_refused() -> None:
    # Tag count and order hold, but the pair marks a different word.
    old = "CO<sub>2</sub>, SO2"
    new = "CO2, SO<sub>2</sub>"
    assert rejection_reason(old, new) == "inline markup changed"


def test_footnote_marker_relocated_across_the_line_refused() -> None:
    # Neither position touches a word, so only the raw-character fallback
    # catches the move.
    old = "<sup>1)</sup> Applies to a static load"
    new = "Applies to a static load <sup>1)</sup>"
    assert rejection_reason(old, new) == "inline markup changed"


def test_neighbour_word_edit_with_markup_unchanged_allowed() -> None:
    # The look-alike is the repair; the subscript must survive it.
    old = "FLOWMETER/ ТЕХОМАТ 6, CO<sub>2</sub> measurement"  # noqa: RUF001
    new = "FLOWMETER/ TEXOMAT 6, CO<sub>2</sub> measurement"
    assert allowed(old, new)


def test_inline_markup_ban_steps_aside_for_a_rebuild() -> None:
    # A crushed run may regain its subscript in a rebuild.
    old = CRUSHED + " CO2"
    new = CRUSHED + " CO<sub>2</sub>"
    assert allowed(old, new)


def test_inline_markup_ban_holds_on_a_line_that_reads_whole() -> None:
    # Without a crushed line nothing licenses the new markup.
    old = "CO2 measurement"
    new = "CO<sub>2</sub> measurement"
    assert rejection_reason(old, new) == "inline markup changed"


# --- a one-letter token keeps its emphasis and its alphabet ------------------


def test_one_letter_token_dropped_bare_and_rescripted_refused() -> None:
    # The wrap is gone, and a Cyrillic letter stands in for the Latin one.
    old = "*m*-ary code"
    new = "м-ary code"
    assert rejection_reason(old, new) is not None


def test_one_letter_token_rescripted_under_its_own_marker_refused() -> None:
    # Italic Cyrillic "т" is shaped like the Latin "m".
    old = "*m*"
    new = "*т*"
    assert rejection_reason(old, new) == "one-letter token changed alphabet"


def test_one_letter_token_dropped_bare_same_alphabet_refused() -> None:
    # The letter survives unwrapped, which picks the other reason.
    old = "*m*-ary code"
    new = "m-ary code"
    assert rejection_reason(old, new) == "one-letter token lost its emphasis"


def test_one_letter_token_corrected_within_its_alphabet_allowed() -> None:
    old = "*m*-ary code"
    new = "*n*-ary code"
    assert allowed(old, new)


def test_one_letter_run_inside_a_formula_is_not_emphasis() -> None:
    # Inside a span an asterisk is a product, not emphasis.
    old = r"Then $\left( a *b* c$ follows."
    new = r"Then $\left( a \ast b \ast c \right)$ follows."
    assert allowed(old, new)


def test_one_letter_emphasis_ban_holds_beside_a_formula() -> None:
    # The math is skipped, but the prose around it is still checked.
    old = r"Here the *m*-ary code and $a *b* c$."
    new = r"Here the m-ary code and $a *b* c$."
    assert rejection_reason(old, new) == "one-letter token lost its emphasis"


def test_emphasis_dropped_around_a_word_allowed() -> None:
    old = "**important** term"
    new = "important term"
    assert allowed(old, new)


def test_whole_paragraph_emphasis_flattened_allowed() -> None:
    # The wrap spans the whole paragraph, not one character.
    old = (
        "**A single letter here needs no marker of its own, and this "
        "sentence is what a converter mistakenly bolds end to end, well "
        "past a hundred and twenty characters.**"
    )
    new = old.strip("*")
    assert allowed(old, new)


# --- a line the markup licenses nothing on ----------------------------------


def test_word_repair_on_an_ordinary_line_allowed() -> None:
    assert allowed("Here the [unreadable] word is lost.", "Here the right word.")


def test_heading_level_change_allowed() -> None:
    assert allowed("## General details", "### General details")


# --- the licence the markup issues ------------------------------------------


def test_hyphenation_join_inside_the_line_allowed() -> None:
    assert allowed("коэффи- циент теплоотдачи", "коэффициент теплоотдачи")


def test_line_break_hyphen_may_not_be_dropped() -> None:
    # The split runs into the line below, which a substitution cannot reach.
    reason = rejection_reason("Полный коэффи-", "Полный коэффи")
    assert reason == "line-break hyphen dropped"


def test_line_break_hyphen_may_not_be_resolved_from_the_line_below() -> None:
    # Text pulled from the line below would stay there too, duplicated.
    reason = rejection_reason("Полный коэффи-", "Полный коэффициент равен")
    assert reason == "line-break hyphen dropped"


def test_word_repair_beside_a_line_break_hyphen_allowed() -> None:
    # A word beside the hyphen is an ordinary repair.
    assert allowed("Полньй коэффи-", "Полный коэффи-")


def test_carriage_return_replacement_refused() -> None:
    reason = rejection_reason("Header Value", "Header\r\nValue")
    assert reason == "carriage return in the replacement"


def test_table_row_recut_refused() -> None:
    # Recutting a grid is post's repair, not inspection's.
    reason = rejection_reason("| transfer velocity |", "| transfer | velocity |")
    assert reason == "table cell count changed"


def test_table_separator_row_may_not_gain_a_column() -> None:
    reason = rejection_reason("| --- | --- |", "| --- | --- | --- |")
    assert reason == "table cell count changed"


def test_broken_table_separator_may_not_become_content() -> None:
    # Other checks tell the separator from a data row, so it must stay one.
    reason = rejection_reason("| --- | --- |", "| Rate | Value |")
    assert reason == "table separator row changed"


def test_broken_table_content_may_not_become_a_separator() -> None:
    reason = rejection_reason("| Rate | Value |", "| --- | --- |")
    assert reason == "table separator row changed"


def test_one_cell_row_may_not_lose_all_its_pipes() -> None:
    # Without its border pipes the one-cell row has collapsed into prose.
    reason = rejection_reason("| A |", "B")
    assert reason == "table row lost its cells"


def test_a_row_may_not_lose_its_pipes_behind_an_escaped_one() -> None:
    # An escaped pipe is content, so it cannot stand in for the grid.
    reason = rejection_reason(r"| A \| B |", r"A \| B")
    assert reason == "table row lost its cells"


def test_prose_that_gains_a_pipe_is_not_a_row_losing_its_shape() -> None:
    # A line with no grid is not a row this ban measures.
    assert allowed("Velocity small", "| Velocity | small |")


def test_a_crushed_line_may_gain_breaks_and_markup() -> None:
    old = CRUSHED
    new = (
        "| **Property** | Quantity |\n| --- | --- |\n"
        "| Velocity extreme | Temperature lowest |\n"
        "| Pressure average | Supply continuous |\n| Torque changeable |"
    )
    assert allowed(old, new)


def test_a_rebuild_that_drops_a_word_refused() -> None:
    # The licence covers markup, never content.
    reason = rejection_reason(CRUSHED, "| Property | Quantity |\n| --- | --- |")
    assert reason == "rebuild changes the line's content"


def test_the_same_rebuild_is_refused_on_a_line_that_reads_whole() -> None:
    # The same words at a length one cell could hold read as prose.
    old = "Property Quantity Velocity extreme"
    new = "| Property | Quantity |\n| Velocity | extreme |"
    assert rejection_reason(old, new) == "multi-line replacement"


def test_formula_repair_inside_a_span_allowed() -> None:
    old = r"The value $\mbox{E} = \left( x$ is found."
    new = r"The value $\text{E} = \left( x \right)$ is found."
    assert allowed(old, new)


def test_formula_repair_of_a_truncated_span_allowed() -> None:
    # The escaped closer leaves the span unpaired; rebuilding it stays open.
    old = r"Hence $ds_{ij}+ds_{ij}+ds_{ij}+ds_{ij}+ds_{ij}+ds_{ij}^{\$"
    new = r"Hence $ds_{ij} = \sigma$"
    assert allowed(old, new)


def test_formula_repair_may_drop_but_not_invent_a_number() -> None:
    # Rebuilding a lost span rewrites its indices, but inventing a value stays
    # out.
    loop = r"Hence $x_1+x_1+x_1+x_1+x_1+x_1+x_1^{\$"
    assert not allowed(loop, r"Hence $x_1 = 0$")
    assert allowed(loop, r"Hence $x_1$")
    assert rejection_reason(loop, r"Hence $x_1 = 42$") == "digit runs added"


def test_formula_edit_dropping_a_span_refused() -> None:
    old = r"Let $\alpha$ and $\left( x$ be given."
    new = r"Let $\alpha$ and x be given."
    assert rejection_reason(old, new) == "math span count changed"


def test_a_ban_outranks_the_licence() -> None:
    # Bans are weighed before the licence, so they hold on a crushed line.
    assert rejection_reason("| 12 | мм |", "| 13 | мм |") == ("digit runs changed")
    assert rejection_reason(CRUSHED, CRUSHED + " 12") == "digit runs changed"


def test_an_image_link_is_not_repairable_by_substitution() -> None:
    # The model sees the source, not the media layout, so links stay banned.
    assert allowed("The layout of the devise is below.", "The device layout is below.")
    assert rejection_reason("![](a.png)", "![](b.png)") == "image links changed"


# --- --llm-latex-fix --------------------------------------------------------


def test_valid_span_stays_closed_without_the_flag() -> None:
    old = r"Then $E = mc^2$ and so on."
    new = r"Then $E = mc^{2}$ and so on."
    assert rejection_reason(old, new, latex_fix=False) == ("valid math span changed")


def test_valid_span_may_be_rewritten_under_the_flag() -> None:
    old = r"Then $E = mc^2$ and so on."
    new = r"Then $E = mc^{2}$ and so on."
    assert rejection_reason(old, new, latex_fix=True) is None


def test_flag_still_refuses_a_rewrite_that_leaves_the_span_broken() -> None:
    # The flag opens a valid span; it does not accept damage handed back.
    old = r"Then $E = mc^2$ and so on."
    new = r"Then $\frac{x}{$ and so on."
    assert rejection_reason(old, new, latex_fix=True) == (
        "rebuilt math span still broken"
    )


def test_flag_lets_a_number_inside_a_span_change() -> None:
    # A misread index is what the mode repairs, so the digit rule in math
    # gives.
    old = r"The moment $M_{12}$ is set."
    new = r"The moment $M_{13}$ is set."
    assert rejection_reason(old, new, latex_fix=True) is None


def test_flag_holds_a_number_outside_a_span() -> None:
    # Only the inside-math half of the digit rule is lifted.
    old = r"Figure 2 gives $M_{12}$."
    new = r"Figure 3 gives $M_{12}$."
    assert rejection_reason(old, new, latex_fix=True) == ("digit runs changed")


def test_flag_holds_the_text_around_a_rewritten_span() -> None:
    old = r"The value $E = mc^2$ is found."
    new = r"The value $E = mc^{2}$ is computed."
    assert rejection_reason(old, new, latex_fix=True) == (
        "edit changes math and the text around it"
    )


def test_flag_leaves_a_line_without_math_under_every_ban() -> None:
    old = "Diameter 120 mm at length 300 mm."
    new = "Diameter 120 mm at length 800 mm."
    assert rejection_reason(old, new, latex_fix=True) == ("digit runs changed")
    assert (
        rejection_reason("![](media/a.jpeg)", "![](media/b.jpeg)", latex_fix=True)
        == "image links changed"
    )


def test_a_long_row_missing_one_border_pipe_is_not_read_as_crushed() -> None:
    # A row missing a border pipe is still a row, so length buys no recut.
    old = (
        "| Width 10 | Height 20 | Length 30 | Diameter 40 "
        "| Width 11 | Height 21 | Length 31 | Diameter 41 | Width 12 | Height 22"
    )
    new = old.replace("| Diameter 41", "Diameter 41")
    assert rejection_reason(old, new) == "table cell count changed"
