"""Tests for the block route: crushed runs, swallowed prose, broken formulas."""

from __future__ import annotations

from collections.abc import Sequence

from raw2md.llm.base import (
    TextPart,
)
from raw2md.llm.post.coordinator import post_process
from raw2md.mdtext.formulas import is_valid_math
from raw2md.mdtext.math_spans import math_span_content, math_spans

from ._helpers import (
    ZONE,
    ZONE_FIXED,
    call_count,
    call_parts,
    join_blocks,
    make_op,
    reason_text,
    sent_text,
)

# --- context blocks ----------------------------------------------------------


def test_context_blocks_travel_labeled_and_read_only() -> None:
    before = ["Intro paragraph stands above the zone."]
    after = ["Closing paragraph stands below the zone."]
    op = make_op([ZONE_FIXED])
    result = post_process(join_blocks(before, ZONE, after), op)
    sent = sent_text(op)
    assert "Intro paragraph stands above the zone." in sent
    assert "Closing paragraph stands below the zone." in sent
    assert "Context above the zone" in sent
    assert "Context below the zone" in sent
    assert (result.repaired, result.reverted) == (1, 0)
    # Context is never written back, so it appears once.
    assert result.body.count("Intro paragraph stands above the zone.") == 1
    assert result.body.count("Closing paragraph stands below the zone.") == 1


def test_no_context_at_the_document_edges() -> None:
    op = make_op([ZONE_FIXED])
    post_process(join_blocks(ZONE, ["Closing paragraph stands below the zone."]), op)
    sent = sent_text(op)
    assert "Context above the zone" not in sent
    assert "Context below the zone" in sent


def test_no_context_across_a_protected_zone() -> None:
    # The fence close touches the zone, so the block above is protected.
    body = "```\ncode\n```\n" + join_blocks(ZONE)
    op = make_op([ZONE_FIXED])
    post_process(body, op)
    assert "Context above the zone" not in sent_text(op)


def test_a_reply_that_folds_context_into_the_zone_reverts() -> None:
    before = ["Intro paragraph stands above the zone."]
    dragged = f"Intro paragraph stands above the zone. {ZONE_FIXED}"
    op = make_op([dragged, dragged])
    result = post_process(join_blocks(before, ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert ZONE[0] in result.body


def test_context_reaches_the_retry_unchanged() -> None:
    before = ["Intro paragraph stands above the zone."]
    op = make_op(["a totally different sentence", "yet another wording entirely"])
    post_process(join_blocks(before, ZONE), op)
    assert call_count(op) == 2
    retry_texts = [p.text for p in call_parts(op, 1) if isinstance(p, TextPart)]
    assert any("Intro paragraph stands above the zone." in t for t in retry_texts)
    assert "rejected" in reason_text(op)


def test_a_degenerately_large_neighbour_is_left_out() -> None:
    # An oversized neighbour would fail the whole stage, not only this zone.
    from raw2md.llm.post.common import MAX_CONTEXT_CHARS

    huge = ["x" * (MAX_CONTEXT_CHARS + 1)]
    op = make_op([ZONE_FIXED])
    result = post_process(join_blocks(huge, ZONE), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert "Context above the zone" not in sent_text(op)
    assert "x" * 100 not in sent_text(op)


# --- preservation, retry, revert -------------------------------------------


def test_preserved_reply_is_applied() -> None:
    op = make_op([ZONE_FIXED])
    result = post_process(join_blocks(ZONE), op)
    assert (result.repaired, result.reverted, result.unchanged) == (1, 0, 0)
    assert ZONE_FIXED in result.body
    assert ZONE[0] not in result.body


def test_word_change_reverts_after_one_retry() -> None:
    op = make_op(["a totally different sentence", "yet another wording entirely"])
    result = post_process(join_blocks(ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert call_count(op) == 2  # the initial attempt plus exactly one retry
    assert ZONE[0] in result.body


def test_retry_succeeds_on_second_attempt() -> None:
    op = make_op(["completely rewritten content here", ZONE_FIXED])
    result = post_process(join_blocks(ZONE), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert call_count(op) == 2
    assert ZONE_FIXED in result.body


def test_unchanged_echo_is_reverted() -> None:
    # An echo is terminal: a retry would have nothing to correct.
    op = make_op([ZONE[0], ZONE[0]])
    result = post_process(join_blocks(ZONE), op)
    assert (result.repaired, result.reverted, result.unchanged) == (0, 1, 1)
    assert call_count(op) == 1
    assert ZONE[0] in result.body


def test_a_pure_rewrap_also_counts_as_unchanged() -> None:
    # A soft line break renders as whitespace, so a re-wrap is an echo.
    rewrap = r"Hence $$E = \frac{mv^2}{2$$" + "\n" + r"for any $v$."
    op = make_op([rewrap])
    result = post_process(join_blocks(ZONE), op)
    assert (result.repaired, result.reverted, result.unchanged) == (0, 1, 1)
    assert call_count(op) == 1


def test_fenced_reply_is_reverted() -> None:
    fenced = f"```\n{ZONE_FIXED}\n```"
    op = make_op([fenced, fenced])
    result = post_process(join_blocks(ZONE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "```" not in result.body


# --- crushed runs: a zone post opens on its own reading ---------------------

# A two-column layout read down the page: one sentence as six paragraphs.
CRUSHED_PROSE = [
    "The test is run on a sample,",
    "which is cut across",
    "the rolling direction, and the result",
    "is brought to a temperature",
    "of twenty degrees Celsius",
    "as the standard requires.",
]
CRUSHED_PROSE_JOINED = (
    "The test is run on a sample, which is cut across the rolling direction, "
    "and the result is brought to a temperature of twenty degrees Celsius as "
    "the standard requires."
)

# The same crush over a list: each entry is cut in half at the column edge.
CRUSHED_LIST = [
    "- measure the width of the sample,",
    "then measure its thickness;",
    "- measure the mass of the sample,",
    "then measure its volume;",
    "- compute the density",
    "as the ratio of mass to volume.",
]
CRUSHED_LIST_REBUILT = (
    "- measure the width of the sample, then measure its thickness;\n"
    "- measure the mass of the sample, then measure its volume;\n"
    "- compute the density as the ratio of mass to volume."
)


def _fragments(lines: Sequence[str]) -> str:
    """The lines as one-line blocks, each split from the next by a blank line."""
    return join_blocks(*([line] for line in lines))


def test_a_crushed_prose_run_is_sent_and_joined() -> None:
    op = make_op([CRUSHED_PROSE_JOINED])
    result = post_process(_fragments(CRUSHED_PROSE), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == CRUSHED_PROSE_JOINED + "\n"


def test_a_crushed_run_request_names_the_repair_itself() -> None:
    op = make_op([CRUSHED_PROSE_JOINED])
    post_process(_fragments(CRUSHED_PROSE), op)
    sent = sent_text(op)
    assert "Crushed zone to repair" in sent
    assert CRUSHED_PROSE[0] in sent
    assert CRUSHED_PROSE[-1] in sent


def test_a_column_of_values_crushed_the_same_way_is_not_sent() -> None:
    # No break cuts a clause, so this is a stack of whole values.
    op = make_op([])
    body = _fragments(["Width", "10", "Height", "20", "Depth", "30"])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert (result.repaired, result.reverted) == (0, 0)
    assert result.body == body


def test_a_crushed_list_is_rebuilt_without_losing_a_word() -> None:
    op = make_op([CRUSHED_LIST_REBUILT])
    result = post_process(_fragments(CRUSHED_LIST), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == CRUSHED_LIST_REBUILT + "\n"
    for line in CRUSHED_LIST:
        for word in line.lstrip("- ").split():
            assert word in result.body


def test_a_crushed_run_answered_with_a_table_is_refused() -> None:
    # Tokens and width both pass; the column assignment is still a guess.
    grid = (
        "| The test is run on a sample, | which is cut across |\n"
        "| --- | --- |\n"
        "| the rolling direction, and the result | is brought to a temperature |\n"
        "| of twenty degrees Celsius | as the standard requires. |"
    )
    op = make_op([grid, grid])
    body = _fragments(CRUSHED_PROSE)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


# A glossary entry whose term is stranded mid-fragment.
CRUSHED_ENTRY = [
    "an instrument that measures the hardness Durometer",
    "of metals, working by the method",
    "of pressing an indenter into",
    "the surface of a sample under",
    "a constant load, the reading comes",
    "from the dial of the instrument.",
]
CRUSHED_ENTRY_RELOCATED = (
    "Durometer an instrument that measures the hardness of metals, working by "
    "the method of pressing an indenter into the surface of a sample under a "
    "constant load, the reading comes from the dial of the instrument."
)


def test_a_crushed_run_ends_at_a_stranded_equation_number() -> None:
    # A reorder-tolerant zone across the number would let the number move.
    op = make_op([])
    body = _fragments([*CRUSHED_PROSE[:3], "(20)", *CRUSHED_PROSE[3:]])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert (result.repaired, result.reverted) == (0, 0)
    assert result.body == body


def test_a_crushed_run_ends_at_a_stranded_list_marker() -> None:
    op = make_op([])
    body = _fragments([*CRUSHED_PROSE[:3], "1.", *CRUSHED_PROSE[3:]])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_a_crushed_run_ends_at_a_stranded_caption_label() -> None:
    op = make_op([])
    body = _fragments([*CRUSHED_PROSE[:3], "Figure 12", *CRUSHED_PROSE[3:]])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_a_crushed_run_opens_past_the_structural_token_before_it() -> None:
    op = make_op([CRUSHED_PROSE_JOINED])
    result = post_process(_fragments(["(20)", *CRUSHED_PROSE]), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == join_blocks(["(20)"], [CRUSHED_PROSE_JOINED])


def test_a_crushed_run_still_accepts_a_relocated_term() -> None:
    op = make_op([CRUSHED_ENTRY_RELOCATED])
    result = post_process(_fragments(CRUSHED_ENTRY), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == CRUSHED_ENTRY_RELOCATED + "\n"


def test_a_crushed_run_reply_that_drops_a_word_reverts() -> None:
    dropped = CRUSHED_PROSE_JOINED.replace(" twenty", "")
    op = make_op([dropped, dropped])
    body = _fragments(CRUSHED_PROSE)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body
    reason = reason_text(op)
    assert "missing" in reason
    assert "twenty" in reason


def test_a_crushed_list_reply_that_drops_a_marker_reverts() -> None:
    # A list marker is a token of its own.
    unmarked = CRUSHED_LIST_REBUILT.replace("- ", "")
    op = make_op([unmarked, unmarked])
    body = _fragments(CRUSHED_LIST)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_crushed_run_wrapped_in_front_matter_reverts() -> None:
    # `---` counts for no token; the protected block it opens refuses the reply.
    wrapped = f"---\n{CRUSHED_PROSE_JOINED}\n---"
    op = make_op([wrapped, wrapped])
    result = post_process(_fragments(CRUSHED_PROSE), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert "protected" in reason_text(op)


# --- a span that swallowed prose --------------------------------------------

# A span closed past the words after the formula; it still renders.
SWALLOWED_ZONE = [
    r"Take the numbers $k_1, k_2, \ldots, k_m, that satisfy the bound$",
]
SWALLOWED_MOVED = r"Take the numbers $k_1, k_2, \ldots, k_m,$ that satisfy the bound"


def test_a_span_that_swallowed_prose_has_its_delimiter_moved() -> None:
    op = make_op([SWALLOWED_MOVED])
    result = post_process(join_blocks(SWALLOWED_ZONE), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == SWALLOWED_MOVED + "\n"


def test_the_swallowed_prose_request_names_the_repair_itself() -> None:
    # The standing rule for math forbids this edit, so the request licenses it.
    op = make_op([SWALLOWED_MOVED])
    post_process(join_blocks(SWALLOWED_ZONE), op)
    sent = sent_text(op)
    assert "Move the delimiter" in sent
    assert SWALLOWED_ZONE[0] in sent


def test_an_accepted_reply_leaves_the_formula_itself_untouched() -> None:
    op = make_op([SWALLOWED_MOVED])
    result = post_process(join_blocks(SWALLOWED_ZONE), op)
    assert math_spans(result.body) == [r"$k_1, k_2, \ldots, k_m,$"]


def test_a_reply_that_rewrites_the_formula_reverts() -> None:
    rewritten = (
        r"Take the numbers $k_{1}, k_{2}, \ldots, k_{m},$ that satisfy the bound"
    )
    op = make_op([rewritten, rewritten])
    body = join_blocks(SWALLOWED_ZONE)
    result = post_process(body, op)
    assert call_count(op) == 2
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_reply_that_drops_a_delimiter_reverts() -> None:
    # Raw LaTeX in the prose: a delimiter may move but not go.
    stripped = r"Take the numbers k_1, k_2, \ldots, k_m, that satisfy the bound"
    op = make_op([stripped, stripped])
    body = join_blocks(SWALLOWED_ZONE)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_sound_span_narrowed_beside_the_swallowing_one_reverts() -> None:
    # The move check reads the zone whole, so each span is checked apart.
    zone = [r"Then $\alpha + \beta$ and $x, for which y$ agree"]
    both = r"Then $\alpha$ + \beta and $x,$ for which y agree"
    op = make_op([both, both])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == join_blocks(zone)


def test_the_swallowing_span_alone_may_be_narrowed() -> None:
    zone = [r"Then $\alpha + \beta$ and $x, for which y$ agree"]
    moved = r"Then $\alpha + \beta$ and $x,$ for which y agree"
    op = make_op([moved])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == moved + "\n"


def test_a_sound_formula_spends_no_request() -> None:
    op = make_op([])
    body = join_blocks([r"It follows that $\frac{a}{b} = c$ for any $n$."])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_two_names_a_command_stands_between_are_no_prose() -> None:
    op = make_op([])
    body = join_blocks([r"$$\Delta PQR \Leftrightarrow \Delta PST;$$"])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_two_capital_labels_side_by_side_are_no_prose() -> None:
    op = make_op([])
    body = join_blocks([r"The triangles $KLM PQR$ are similar."])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_prose_held_in_a_text_macro_is_not_this_zone() -> None:
    # Unwrapping `\text` is the cleaner's work.
    op = make_op([])
    body = join_blocks([r"$$Q = c m \text{ at constant pressure}$$"])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


def test_a_swallowing_span_inside_a_table_is_left_to_the_table_route() -> None:
    op = make_op([])
    body = join_blocks(
        [
            "| Symbol | Value |",
            "| --- | --- |",
            r"| $p, gas pressure$ | 0.5 |",
        ]
    )
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


# --- a formula whose markup broke -------------------------------------------

# The `\frac` denominator group is never closed.
MARKUP_ZONE = [r"Hence $$E = \frac{mv^2}{2$$ for any $v$."]
MARKUP_FIXED = r"Hence $$E = \frac{mv^2}{2}$$ for any $v$."


def test_an_unclosed_group_is_closed_and_the_span_renders() -> None:
    op = make_op([MARKUP_FIXED])
    result = post_process(join_blocks(MARKUP_ZONE), op)
    assert call_count(op) == 1
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == MARKUP_FIXED + "\n"
    assert all(is_valid_math(math_span_content(s)) for s in math_spans(result.body))


def test_the_markup_request_names_the_licence_it_grants() -> None:
    op = make_op([MARKUP_FIXED])
    post_process(join_blocks(MARKUP_ZONE), op)
    sent = sent_text(op)
    assert "Repair the markup" in sent
    assert MARKUP_ZONE[0] in sent


def test_a_left_without_its_right_is_closed_by_the_invisible_delimiter() -> None:
    # A bracket of the model's own may never have been printed.
    zone = [r"$$\left( x + y$$"]
    closed = r"$$\left( x + y \right.$$"
    op = make_op([closed])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == closed + "\n"


def test_a_reply_that_changes_a_symbol_reverts() -> None:
    rewritten = r"Hence $$E = \frac{mc^2}{2}$$ for any $v$."
    op = make_op([rewritten, rewritten])
    body = join_blocks(MARKUP_ZONE)
    result = post_process(body, op)
    assert call_count(op) == 2
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_reply_that_changes_a_digit_reverts() -> None:
    rewritten = r"Hence $$E = \frac{mv^2}{3}$$ for any $v$."
    op = make_op([rewritten, rewritten])
    body = join_blocks(MARKUP_ZONE)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_reply_leaving_the_span_refused_reverts() -> None:
    still_broken = r"Hence $$E = \frac{mv^2}}{2$$ for any $v$."
    op = make_op([still_broken, still_broken])
    body = join_blocks(MARKUP_ZONE)
    result = post_process(body, op)
    assert call_count(op) == 2
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_an_accepted_reply_touches_no_character_of_the_formula() -> None:
    op = make_op([MARKUP_FIXED])
    result = post_process(join_blocks(MARKUP_ZONE), op)
    assert math_spans(result.body) == [r"$$E = \frac{mv^2}{2}$$", "$v$"]


def test_a_sound_span_beside_the_broken_one_comes_back_as_it_stood() -> None:
    zone = [r"Then $x^{12}$ and $\frac{a}{b$ agree."]
    both = r"Then $x^12$ and $\frac{a}{b}$ agree."
    op = make_op([both, both])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == join_blocks(zone)


def test_a_markup_reply_that_drops_a_delimiter_reverts() -> None:
    stripped = r"Hence E = \frac{mv^2}{2} for any $v$."
    op = make_op([stripped, stripped])
    body = join_blocks(MARKUP_ZONE)
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == body


def test_a_delimiter_moved_over_the_formulas_own_characters_reverts() -> None:
    zone = [r"Here $x^{2$ and then text."]
    moved = r"Here x^{2} and then $text$."
    op = make_op([moved, moved])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == join_blocks(zone)


def test_a_delimiter_moved_out_over_the_prose_reverts() -> None:
    zone = [r"Here $x^{2$ and then text."]
    moved = r"Here $x^{2} and then text$."
    op = make_op([moved, moved])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == join_blocks(zone)


def test_a_reply_that_renames_the_environment_reverts() -> None:
    # `cases` sets a brace that `matrix` does not; both render.
    zone = [r"$$\begin{matrix} a & b \\ c & d $$"]
    renamed = r"$$\begin{cases} a & b \\ c & d \end{cases}$$"
    op = make_op([renamed, renamed])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == join_blocks(zone)


def test_a_token_exchanged_with_its_twin_in_the_prose_reverts() -> None:
    # Token counts cannot see the exchange; the order inside the span can.
    zone = [r"$\alpha + y{$ \alpha"]
    swapped = r"\alpha $+ y{} \alpha$"
    op = make_op([swapped, swapped])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == join_blocks(zone)


def test_a_sound_environment_beside_the_broken_one_licenses_no_rename() -> None:
    zone = [r"$$\begin{cases} x \\ y \end{cases}$$ and $$\begin{matrix} a & b $$"]
    renamed = (
        r"$$\begin{cases} x \\ y \end{cases}$$ and $$\begin{cases} a & b \end{cases}$$"
    )
    op = make_op([renamed, renamed])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert result.body == join_blocks(zone)


def test_a_missing_end_is_written_under_the_name_that_stands() -> None:
    zone = [r"$$\begin{pmatrix} a & b \\ c & d $$"]
    closed = r"$$\begin{pmatrix} a & b \\ c & d \end{pmatrix}$$"
    op = make_op([closed])
    result = post_process(join_blocks(zone), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.body == closed + "\n"


def test_a_span_whose_closer_the_damage_ate_opens_no_zone() -> None:
    # Writing a missing delimiter is not moving one.
    op = make_op([])
    body = join_blocks([r"$$\eta = \frac{A}{Q}"])
    result = post_process(body, op)
    assert call_count(op) == 0
    assert result.body == body


# --- hyphenation joins ------------------------------------------------------

# A column edge also split a word, so the join closes a hyphen gap.
SPLIT_RUN = [
    "Измерение проводят на образце,",
    "который вырезан попе-",
    "рёк направления прокатки, и результат",
    "приводят к температуре",
    "двадцать градусов Цельсия",
    "по таблице приложения.",
]

SPLIT_RUN_JOINED = (
    "Измерение проводят на образце, который вырезан поперёк направления "
    "прокатки, и результат приводят к температуре двадцать градусов Цельсия "
    "по таблице приложения."
)

# The heading attests the joined word and ends the run.
SPLIT_ATTEST = ["## Образец режут поперёк волокна"]


def _split_run(*extra: list[str]) -> str:
    """The split run as crushed fragments, followed by `extra` blocks."""
    return _fragments(SPLIT_RUN) + ("\n" + join_blocks(*extra) if extra else "")


def test_a_join_the_document_attests_is_applied_and_counted() -> None:
    op = make_op([SPLIT_RUN_JOINED])
    result = post_process(_split_run(SPLIT_ATTEST), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.joins, result.refused_joins) == (1, 0)


def test_a_join_into_a_word_the_document_never_uses_reverts() -> None:
    # The break is normalized before the token check, so no token catches this.
    op = make_op([SPLIT_RUN_JOINED, SPLIT_RUN_JOINED])
    body = _split_run()
    result = post_process(body, op)
    assert (result.repaired, result.reverted) == (0, 1)
    assert (result.joins, result.refused_joins) == (0, 1)
    assert result.body == body


def test_a_join_attested_by_an_inflected_form_is_applied() -> None:
    run = [
        "Значения получены интерпо-",
        "ляцией по данным",
        "таблицы приложения, и результат",
        "приводят к температуре",
        "двадцать градусов Цельсия",
        "по таблице приложения.",
    ]
    joined = (
        "Значения получены интерполяцией по данным таблицы приложения, и "
        "результат приводят к температуре двадцать градусов Цельсия по таблице "
        "приложения."
    )
    op = make_op([joined])
    result = post_process(
        _fragments(run) + "\n" + join_blocks(["## Метод интерполяции"]), op
    )
    assert (result.repaired, result.reverted) == (1, 0)
    assert result.joins == 1


def test_the_retry_reason_names_the_invented_word() -> None:
    op = make_op([SPLIT_RUN_JOINED, SPLIT_RUN_JOINED])
    post_process(_split_run(), op)
    reason = reason_text(op)
    assert "поперёк" in reason
    assert "температуре" not in reason


def test_a_reply_that_leaves_no_split_counts_no_join() -> None:
    op = make_op([CRUSHED_PROSE_JOINED])
    result = post_process(_fragments(CRUSHED_PROSE), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert (result.joins, result.refused_joins) == (0, 0)


# --- retry carries the rejection reason -------------------------------------


def test_retry_request_differs_from_the_first() -> None:
    op = make_op(["a totally different sentence", "yet another wording entirely"])
    post_process(join_blocks(ZONE), op)
    assert call_count(op) == 2
    assert len(call_parts(op, 1)) > len(call_parts(op, 0))
    assert "rejected" in reason_text(op)


def test_retry_reason_names_a_changed_formula() -> None:
    changed = ZONE_FIXED.replace("mv^2", "mv^3")
    op = make_op([changed, changed])
    post_process(join_blocks(ZONE), op)
    assert "formula" in reason_text(op)


def test_retry_reason_for_an_empty_reply() -> None:
    op = make_op(["", ZONE_FIXED])
    result = post_process(join_blocks(ZONE), op)
    assert (result.repaired, result.reverted) == (1, 0)
    assert "empty" in reason_text(op)


def test_retry_reason_for_a_fenced_reply() -> None:
    # The fence adds tokens, so the token check trips before the fence guard.
    fenced = f"```\n{ZONE_FIXED}\n```"
    op = make_op([fenced, fenced])
    post_process(join_blocks(ZONE), op)
    assert "added" in reason_text(op)


def test_retry_reason_caps_the_number_of_named_tokens() -> None:
    from raw2md.llm.post.blocks import _REASON_TOKEN_LIMIT

    letters = " + ".join("abcdefghijklmnopqrst")  # 20 distinct single letters
    zone = [rf"Hence $$E = {letters} + \frac{{1}}{{2$$ below."]
    op = make_op(["Hence below.", "Hence below."])
    post_process(join_blocks(zone), op)
    reason = reason_text(op)
    missing = reason.split("missing ")[1].split(";")[0].rstrip(")").split(", ")
    assert len(missing) == _REASON_TOKEN_LIMIT


# --- table width ------------------------------------------------------------


def test_a_separator_without_a_table_around_it_is_not_measured() -> None:
    # Both a header and a body row are needed before `---` counts as a table width.
    from raw2md.llm.post.blocks import _row_off_table_width

    assert not _row_off_table_width(["Section A | B", "---"])  # setext heading
    assert not _row_off_table_width(["---", "Rated | 5 A max"])  # thematic break
    assert _row_off_table_width(["Section A | B", "---", "| x | y |"])


def test_a_header_alone_is_measured_when_the_separator_carries_a_pipe() -> None:
    # A separator with a pipe cannot be a setext underline.
    from raw2md.llm.post.blocks import _row_off_table_width

    assert _row_off_table_width(["| A | B |", "| --- | --- | --- |"])
    assert not _row_off_table_width(["| A | B |", "| --- | --- |"])
