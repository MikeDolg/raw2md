"""Tests for the quality evaluator."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from raw2md.cleaner import clean
from raw2md.cleaning import Finding
from raw2md.header import ResultStatus
from raw2md.mdtext.pages import lost_page_marker
from raw2md.quality.evaluator import CheckId, Evaluation, evaluate
from raw2md.source_outline import SourceOutline
from raw2md.source_text import SourceText

# A display span that looped over tensor components; the cut leaves an
# unclosed bracket, so cleaning drops the rest.
_LOOP_FRAGMENT_BODY = (
    "The strain tensor reads as follows in this readable sentence.\n\n"
    r"$$[\gamma_{xz}, \gamma_{yz}" + r", \gamma_{xz}" * 8 + "$$\n"
)


def _fired(ev: Evaluation, check: CheckId) -> bool:
    return any(d.check is check for d in ev.defects)


def _filler_lines(n: int) -> str:
    """`n` distinct readable lines, for tests that need a large body."""
    return "\n".join(
        f"Distinct informative sentence number {i} appears here." for i in range(n)
    )


def _cyrillic_filler_lines(n: int) -> str:
    """`n` distinct Cyrillic-prose lines, for greek-unit escalation tests."""
    return "\n".join(
        f"Информация о результате измерения номер {i} приведена в отчёте."  # noqa: RUF001
        for i in range(n)
    )


def _greek_unit_lines(n: int) -> str:
    """`n` distinct Cyrillic-prose lines each carrying a suspect unit span."""
    return "\n".join(
        rf"Масса образца номер {i} составила $55~\kappa\Gamma$ по паспорту."  # noqa: RUF001
        for i in range(n)
    )


def _left_standing(kind: str, count: int) -> tuple[Finding, ...]:
    """`count` findings of `kind`, as the cleaning stage would report them."""
    return tuple(Finding(kind, line) for line in range(1, count + 1))


# ---- ok baseline -------------------------------------------------------------


def test_clean_body_is_ok() -> None:
    ev = evaluate("# Title\n\nA clean paragraph with plenty of readable words.\n")
    assert ev.status is ResultStatus.OK
    assert ev.defects == ()
    assert not ev.repairable
    assert not ev.recognition_failure


# ==== Text group ==============================================================


# ---- text density ------------------------------------------------------------


def test_low_density_is_recognition_failure() -> None:
    ev = evaluate("a" * 100 + "\n", source_pages=10)
    assert _fired(ev, CheckId.TEXT_DENSITY)
    assert ev.recognition_failure
    assert ev.metrics["density"] < 350


def test_high_density_is_ok() -> None:
    ev = evaluate("a" * 4000 + "\n", source_pages=10)
    assert not _fired(ev, CheckId.TEXT_DENSITY)
    assert ev.status is ResultStatus.OK


def test_density_skipped_without_page_count() -> None:
    ev = evaluate("a" * 50 + "\n")
    assert "density" not in ev.metrics
    assert not _fired(ev, CheckId.TEXT_DENSITY)


# ---- empty body --------------------------------------------------------------


def test_short_body_fires_empty_body() -> None:
    # 13 alphanumeric characters, below the floor of 20.
    ev = evaluate("Hi there friend\n")
    assert _fired(ev, CheckId.EMPTY_BODY)
    assert ev.recognition_failure


def test_body_at_alnum_threshold_is_not_empty() -> None:
    ev = evaluate("a" * 20 + "\n")
    assert not _fired(ev, CheckId.EMPTY_BODY)
    assert ev.status is ResultStatus.OK


# ---- unreadable characters ---------------------------------------------------


_GREEK_ALPHA = chr(0x3B1)  # Greek alpha: outside Latin and Cyrillic (ASCII source)


def test_unreadable_chars_fire_above_threshold() -> None:
    # 220 letters, 18% Greek (outside Latin and Cyrillic).
    body = "a" * 180 + _GREEK_ALPHA * 40 + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.UNREADABLE_CHARS)
    assert ev.recognition_failure


def test_unreadable_skipped_below_letter_floor() -> None:
    # 150 letters (< 200) so the check does not run even at a high share.
    body = "a" * 100 + _GREEK_ALPHA * 50 + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.UNREADABLE_CHARS)


def test_unreadable_not_flagged_at_low_share() -> None:
    # 220 letters, 9% other, below the 15% threshold.
    body = "a" * 200 + _GREEK_ALPHA * 20 + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.UNREADABLE_CHARS)
    assert ev.status is ResultStatus.OK


# ---- mojibake ----------------------------------------------------------------

# A cp1251 text layer read as MacRoman: all Latin letters, so the non-Latin
# share misses it. The look-alikes are the defect, hence the RUF001 waiver.
_MOJIBAKE = (
    "”ÒÚðÓÈÒÚ'Ó ÒÎÛÊËÚ ‰Îˇ ÍÓÌÚðÓÎˇ ÚÓÎ˘ËÌ˚ ÎËÒÚÓ'Ó\"Ó ÔðÓÍ‡Ú‡ Ì‡ ÒÚ‡ÌÂ "
    "ıÓÎÓ‰ÌÓÈ ÔðÓÍ‡ÚÍË ÏÂÚÓ‰ÓÏ ÛÎ¸Úð‡Á'ÛÍÓ'Ó\"Ó ÁÓÌ‰ËðÓ'‡ÌËˇ\n"  # noqa: RUF001
)
_RU_TEXT = "Устройство служит для контроля толщины листового проката на стане\n"
# German prose: legitimate umlauts and an eszett, no Cyrillic anywhere.
_DE_TEXT = (
    "Das Gerät zur Prüfung der Blechdicke während des Walzens wird über die "
    "Führungsschiene geschoben, gemäß Abschnitt drei größer gewählt für die "
    "Messköpfe an beiden Seiten.\n"
)


def test_mojibake_fires_unreadable_and_recognition_failure() -> None:
    # A mojibake body with a readable Cyrillic abstract alongside.
    ev = evaluate(_MOJIBAKE * 6 + _RU_TEXT * 2)
    assert _fired(ev, CheckId.UNREADABLE_CHARS)
    assert ev.recognition_failure
    assert ev.metrics["mojibake_share"] > 0.15


def test_german_text_does_not_fire_mojibake() -> None:
    # Accented Latin without a Cyrillic base is a legitimate DE/EP document.
    ev = evaluate(_DE_TEXT * 4)
    assert not _fired(ev, CheckId.UNREADABLE_CHARS)
    assert "mojibake_share" not in ev.metrics


def test_german_quotation_inside_russian_does_not_fire_mojibake() -> None:
    # The guard is on the accented share, which stays far below the threshold.
    ev = evaluate(_RU_TEXT * 8 + _DE_TEXT)
    assert not _fired(ev, CheckId.UNREADABLE_CHARS)


def test_few_accented_letters_in_cyrillic_body_do_not_fire() -> None:
    # The share is over all letters, so a few accented names do not fire.
    ev = evaluate(_RU_TEXT * 8 + "Ampère Poincaré\n")
    assert not _fired(ev, CheckId.UNREADABLE_CHARS)


def test_mojibake_skipped_below_letter_floor() -> None:
    # Under 200 letters the unreadable check does not run at all.
    ev = evaluate(_MOJIBAKE + _RU_TEXT)
    assert not _fired(ev, CheckId.UNREADABLE_CHARS)


# ==== Math group ==============================================================


# ---- formulas ----------------------------------------------------------------


def test_valid_formula_is_not_flagged() -> None:
    ev = evaluate("Equation $a + b = c$ appears in this readable sentence.\n")
    assert not _fired(ev, CheckId.FORMULAS)


def test_unbalanced_braces_formula_is_flagged() -> None:
    ev = evaluate("Broken $a + {b$ inside this otherwise readable sentence.\n")
    assert _fired(ev, CheckId.FORMULAS)
    assert ev.repairable


def test_currency_is_not_a_formula() -> None:
    ev = evaluate("It costs $5 and the other one is $10 in total today.\n")
    assert not _fired(ev, CheckId.FORMULAS)


def test_span_damaged_but_renderable_is_not_an_invalid_formula() -> None:
    # The span needs repair but still renders, so nothing counts as lost.
    body = r"Moment $M_{y  n  1}$ in a readable sentence." + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FORMULAS)


def test_sizing_command_with_nothing_to_size_is_an_invalid_formula() -> None:
    # The counts balance, but the renderer refuses: the bracket is lost.
    body = r"Force $\left  F \right$ in a readable sentence." + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)


def test_empty_span_is_an_invalid_formula() -> None:
    # A renderer accepts an empty span, yet the formula is gone.
    ev = evaluate("Formula $$$$ in an otherwise readable sentence here.\n")
    assert _fired(ev, CheckId.FORMULAS)


def test_many_invalid_formulas_escalate_to_failure() -> None:
    body = "\n".join(f"line {i} has $x{{{i}$ broken" for i in range(6)) + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)
    assert ev.recognition_failure


def test_orphan_environment_end_is_an_invalid_formula() -> None:
    # The braces balance, so only the environment shows KaTeX rejects it.
    body = r"Tail $$a = b \end{split}$$ inside an otherwise readable sentence." + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)
    assert ev.repairable


def test_unclosed_environment_is_an_invalid_formula() -> None:
    body = r"Head $$\begin{split} a &= b$$ inside a readable sentence here." + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)


def test_crossed_environment_nesting_is_an_invalid_formula() -> None:
    # The counts balance, but LaTeX closes environments innermost-first.
    body = (
        r"Crossed $$\begin{split}\begin{array}{c} a \end{split}\end{array}$$ here."
        "\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)


def test_balanced_environment_is_not_flagged() -> None:
    body = (
        r"Block $$\begin{split} a &= b \\ c &= d \end{split}$$ in a readable line."
        "\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FORMULAS)


def test_repetition_loop_is_an_invalid_formula() -> None:
    # A loop cut off by a length cap is lost even with balanced braces.
    body = "Then $a_{1}" + "+a_{1}" * 7 + "$ ends the readable sentence here.\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)
    assert ev.repairable


def test_repeated_span_run_is_an_invalid_formula() -> None:
    # The count reads the body before the cleaner trims the loop.
    body = "Then " + " ".join(["$v_2$"] * 12) + " closes the readable sentence.\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)


def test_dropped_loop_fragment_is_not_counted_as_a_formula() -> None:
    # Cleaning drops the loop fragment; its report carries the loss.
    ev = evaluate(clean(_LOOP_FRAGMENT_BODY))
    assert not _fired(ev, CheckId.FORMULAS)
    assert ev.metrics["math_spans"] == 0


def test_long_varied_formula_is_not_a_loop() -> None:
    # Terms vary, so the back-to-back repeat count stays low: not a loop.
    body = "A series $x^1 + x^2 + x^3 + x^4 + x^5 + x^6 + x^7 + x^8$ reads fine.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FORMULAS)


def test_repeated_spacing_is_not_a_loop() -> None:
    # Thin spaces hold no alphanumeric, so they are no degenerate unit.
    body = "Spaced $" + r"\," * 20 + "$ in an otherwise readable sentence here.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FORMULAS)


def test_column_spec_repetition_loop_is_an_invalid_formula() -> None:
    # No LaTeX metacharacter: only the place in `\begin{array}`'s argument
    # shows the loop.
    body = (
        r"Block $$\begin{array}{"
        + "c" * 24
        + r"} a \end{array}$$ in a readable line."
        + "\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)


def test_wide_but_plausible_column_spec_is_not_an_invalid_formula() -> None:
    body = (
        r"Block $$\begin{array}{"
        + "c" * 12
        + r"} a \end{array}$$ in a readable line."
        + "\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FORMULAS)


def test_dollar_in_code_fence_is_not_a_formula() -> None:
    body = "```\nx = $a + {b$\n```\n\nA readable paragraph with enough words.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FORMULAS)


def test_formula_escalation_does_not_fire_on_large_document() -> None:
    # 15 invalid formulas on ~10,000 lines stay under the scaled threshold
    # (2 per 1000 lines).
    formulas = "\n".join(f"line {i} has $x{{{i}$ broken" for i in range(15))
    body = _filler_lines(10_000) + "\n" + formulas + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)
    assert not ev.recognition_failure


# ---- lost formulas -------------------------------------------------------------


def test_lost_formula_is_counted_under_its_own_check() -> None:
    # The loss has no repairer, so it is a check of its own.
    body = "A formula recognition already lost.\n"
    ev = evaluate(body, cleaning_findings=_left_standing("broken-formula", 1))
    assert not _fired(ev, CheckId.HYPHENATION)
    assert _fired(ev, CheckId.LOST_FORMULAS)
    assert ev.metrics["lost_formulas"] == 1


def test_single_lost_formula_stays_ok() -> None:
    # Below the floor of 2: recorded in issues, not graded.
    body = "A formula recognition already lost.\n"
    ev = evaluate(body, cleaning_findings=_left_standing("broken-formula", 1))
    assert ev.status is ResultStatus.OK
    assert CheckId.LOST_FORMULAS.value in ev.issues


def test_a_reported_broken_table_is_graded_once() -> None:
    # The `tables` check already counts this row; the finding would count it
    # twice.
    body = "Readable prose above the table here.\n\n| A | B |\n|---|---|\n| 1 |\n"
    ev = evaluate(body, cleaning_findings=_left_standing("broken-table", 1))
    assert ev.issues == (CheckId.TABLES.value,)
    assert ev.metrics["broken_tables"] == 1


def test_lost_formulas_past_threshold_are_bad() -> None:
    body = _filler_lines(1500)
    ev = evaluate(body, cleaning_findings=_left_standing("broken-formula", 3))
    assert ev.status is ResultStatus.BAD
    assert ev.metrics["lost_formulas"] == 3


def test_lost_formula_drives_neither_hint() -> None:
    # A final loss is not repairable, and a few are no recognition failure.
    body = _filler_lines(1500)
    ev = evaluate(body, cleaning_findings=_left_standing("broken-formula", 3))
    assert not ev.repairable
    assert not ev.recognition_failure


def test_lost_formula_threshold_scales_with_the_cleaning_body() -> None:
    # The threshold scales by the body the cleaning stage measured.
    body = _filler_lines(10)
    ev = evaluate(
        body,
        cleaning_findings=_left_standing("broken-formula", 3),
        cleaning_body_lines=10_000,
    )
    assert ev.status is ResultStatus.OK
    assert CheckId.LOST_FORMULAS.value in ev.issues


def test_lost_formulas_detail_reports_the_count() -> None:
    body = _filler_lines(1500)
    ev = evaluate(body, cleaning_findings=_left_standing("broken-formula", 3))
    assert f"{CheckId.LOST_FORMULAS.value} (3 formulas lost)" in ev.defect_report


# ---- math span drift ----------------------------------------------------------


def test_math_spans_are_counted_in_metrics() -> None:
    ev = evaluate("Two formulas $a=1$ and $b=2$ in a readable sentence here.\n")
    assert ev.metrics["math_spans"] == 2


def test_math_span_count_drop_is_flagged() -> None:
    # The total count backs up the per-edit guards.
    ev = evaluate(
        "Reads fine but the formula is simply gone now.\n", math_spans_before=1
    )
    assert _fired(ev, CheckId.MATH_SPAN_DRIFT)
    assert ev.status is ResultStatus.BAD


def test_math_span_count_match_is_not_flagged() -> None:
    ev = evaluate(
        "One formula $a=1$ in a readable sentence here.\n", math_spans_before=1
    )
    assert not _fired(ev, CheckId.MATH_SPAN_DRIFT)


def test_document_without_math_stays_quiet() -> None:
    ev = evaluate(
        "An ordinary sentence with no math in it at all.\n", math_spans_before=0
    )
    assert not _fired(ev, CheckId.MATH_SPAN_DRIFT)
    assert ev.metrics["math_spans"] == 0


def test_dropped_loop_fragment_does_not_drift() -> None:
    # A span the cleaner removed must not read as one an LLM step lost.
    assert evaluate(_LOOP_FRAGMENT_BODY).metrics["math_spans"] == 1
    cleaned = clean(_LOOP_FRAGMENT_BODY)
    before = int(evaluate(cleaned).metrics["math_spans"])
    assert before == 0
    ev = evaluate(cleaned, math_spans_before=before)
    assert not _fired(ev, CheckId.MATH_SPAN_DRIFT)


def test_math_span_drift_skipped_without_a_baseline() -> None:
    # Without a baseline the check is a no-op.
    ev = evaluate("An ordinary sentence with no math in it at all.\n")
    assert not _fired(ev, CheckId.MATH_SPAN_DRIFT)


def test_stray_dollar_and_later_backslash_do_not_merge_into_a_span() -> None:
    # The unclosed-tail rule is per line, so a backslash on a later line
    # does not pair with a stray `$` into one span.
    body = "It costs $5 here.\n\nSee the file at C:\\Users\\name for details.\n"
    ev = evaluate(body)
    assert ev.metrics["math_spans"] == 0


def test_multiline_display_formula_collapsed_to_one_line_does_not_drift() -> None:
    # The closed-pair count spans lines, so reflowing a display block does not
    # read as a new span.
    multiline = (
        "Block\n\n$$\na = b\n$$\n\nMore text with plenty of readable words here.\n"
    )
    before = int(evaluate(multiline).metrics["math_spans"])
    assert before == 1
    collapsed = "Block\n\n$$a = b$$\n\nMore text with plenty of readable words here.\n"
    ev = evaluate(collapsed, math_spans_before=before)
    assert not _fired(ev, CheckId.MATH_SPAN_DRIFT)


def test_repaired_unclosed_span_does_not_drift() -> None:
    # A truncated span counts even unclosed, so its repair is no new span.
    damaged = "Value $x^{\\$ end.\n"
    before = int(evaluate(damaged).metrics["math_spans"])
    assert before == 1
    repaired = "Value $x^{2}$ end.\n"
    ev = evaluate(repaired, math_spans_before=before)
    assert not _fired(ev, CheckId.MATH_SPAN_DRIFT)


# ---- runaway math delimiters --------------------------------------------------


def test_unpaired_display_delimiter_is_flagged() -> None:
    # An odd count means one delimiter never closes; the next real formula's
    # opener becomes its closer and everything between reads as math.
    body = "Intro line here.\n\n$$a = b$$\n\nMore readable text.\n\n$$ stray\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.RUNAWAY_MATH)
    assert ev.status is ResultStatus.BAD


def test_display_block_over_a_heading_is_flagged() -> None:
    body = "Intro line here.\n\n$$a = b\n\n# Chapter two\n\nProse here.\n\nc = d$$\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.RUNAWAY_MATH)


def test_display_block_over_a_table_row_is_flagged() -> None:
    body = (
        "Intro line with plenty of readable words.\n\n$$x\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\ny$$\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.RUNAWAY_MATH)


def test_display_block_over_an_image_is_flagged() -> None:
    body = (
        "Intro line with plenty of readable words.\n\n$$x\n\n"
        "![Test rig](media/fig1.png)\n\ny$$\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.RUNAWAY_MATH)


def test_oversize_display_block_is_flagged() -> None:
    # Past the size cap the block is the document, not a formula anyone typeset.
    body = "Intro line with plenty of readable words.\n\n$$" + "a+b+" * 900 + "$$\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.RUNAWAY_MATH)


def test_ordinary_display_formula_is_not_flagged() -> None:
    body = "Intro line here.\n\n$$E = mc^2$$\n\nOutro line with readable words.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.RUNAWAY_MATH)
    assert ev.status is ResultStatus.OK


def test_standalone_delimiters_are_not_flagged() -> None:
    # The shape where each `$$` sits on its own line, with the formula between.
    body = "Intro line here.\n\n$$\nv^2 = v_0^2 + 2 a s\n$$\n\nOutro line here.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.RUNAWAY_MATH)


def test_quoted_delimiter_does_not_shift_the_pairing() -> None:
    # A `$$` in inline code documents the delimiter; it is not one.
    body = (
        "Some sources put the `$$` on its own line, like so:\n\n"
        "$$\nv = a t\n$$\n\nOutro line with readable words.\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.RUNAWAY_MATH)


def test_adjacent_inline_spans_are_not_a_display_delimiter() -> None:
    # `$a$$b$` is two glued inline spans, not a display delimiter.
    ev = evaluate("Values $a$$b$ in an otherwise readable sentence here.\n")
    assert not _fired(ev, CheckId.RUNAWAY_MATH)


def test_runaway_math_drives_neither_hint() -> None:
    # One stray delimiter decides `bad`, not a recognition failure.
    body = "Intro line with plenty of readable words here.\n\n$$ stray\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.RUNAWAY_MATH)
    assert not ev.repairable
    assert not ev.recognition_failure


def test_dollars_in_a_code_fence_are_not_delimiters() -> None:
    body = "```\n$$ shell prompt $$\n```\n\nA readable paragraph with enough words.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.RUNAWAY_MATH)


# ---- greek units ---------------------------------------------------------------


def test_greek_unit_next_to_integer_is_flagged() -> None:
    # marker's real misread: `55 кГ` (kilogram-force) OCR'd into `55~\kappa\Gamma`.
    body = r"Масса образца составила $55~\kappa\Gamma$ по паспорту прибора." + "\n"  # noqa: RUF001
    ev = evaluate(body)
    assert _fired(ev, CheckId.GREEK_UNITS)
    assert ev.metrics["greek_units"] == 1
    # Only the source tells the right reading, so inspection owns it.
    assert not ev.repairable
    assert not ev.recognition_failure


def test_coefficient_juxtaposed_with_greek_letter_is_not_flagged() -> None:
    # Real math puts a number against a Greek variable with no spacer.
    body = r"Период колебаний равен $2\pi$ секунды по результатам расчёта." + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.GREEK_UNITS)


def test_greek_command_with_other_span_content_is_not_flagged() -> None:
    body = r"Коэффициент $\kappa_{s} = 55$ получен экспериментально в опыте." + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.GREEK_UNITS)


def test_single_greek_unit_symbol_is_not_flagged() -> None:
    # A real unit is one Greek command: `50~\Omega` is correct prose.
    body = r"Резистор номиналом $50~\Omega$ установлен на плате устройства." + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.GREEK_UNITS)


def test_micro_ohm_combination_is_not_flagged() -> None:
    # Micro-ohm is the one SI unit made of two Greek commands.
    body = r"Сопротивление составило $55~\mu\Omega$ на испытательном стенде." + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.GREEK_UNITS)


def test_greek_unit_shape_quoted_in_code_span_is_not_flagged() -> None:
    # Documenting the defect's own shape in inline code is not OCR output.
    body = r"Дефект распознавания выглядит так: `$55~\kappa\Gamma$` в тексте." + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.GREEK_UNITS)


def test_greek_unit_without_cyrillic_context_is_not_flagged() -> None:
    body = r"The sample mass came out to $55~\kappa\Gamma$ per the datasheet." + "\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.GREEK_UNITS)


def test_greek_unit_escalation_does_not_fire_on_large_document() -> None:
    # 15 hits on ~10,000 lines stay under the scaled threshold: a spot check
    # for inspection, not a recognition failure.
    body = _cyrillic_filler_lines(10_000) + "\n" + _greek_unit_lines(15)
    ev = evaluate(body)
    assert _fired(ev, CheckId.GREEK_UNITS)
    assert not ev.recognition_failure


def test_greek_unit_escalation_fires_above_scaled_threshold() -> None:
    body = _cyrillic_filler_lines(10_000) + "\n" + _greek_unit_lines(25)
    ev = evaluate(body)
    assert ev.recognition_failure


# ==== Headings group ==========================================================


# ---- headings ----------------------------------------------------------------


def test_heading_level_jump_is_flagged() -> None:
    ev = evaluate("# Top\n\n### Skipped level two entirely here\n")
    assert _fired(ev, CheckId.HEADINGS)
    assert ev.repairable


def test_heading_step_of_one_is_ok() -> None:
    ev = evaluate("# Top\n\n## Sub\n\n### Deeper section with words\n")
    assert not _fired(ev, CheckId.HEADINGS)


def test_heading_missing_space_is_flagged() -> None:
    ev = evaluate("##Heading glued to its text but long enough to count here\n")
    assert _fired(ev, CheckId.HEADINGS)


def test_heading_in_code_fence_is_ignored() -> None:
    body = "# Real Top\n\n```\n#### deep in code\n```\n\nParagraph with words here.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADINGS)


# ---- heading ladder ----------------------------------------------------------


def _levelled(*headings: tuple[int, str]) -> str:
    """A body of the given headings, each with a paragraph under it."""
    return "\n\n".join(
        f"{'#' * level} {title}\n\nA readable paragraph under {title.lower()}."
        for level, title in headings
    )


def test_numbered_class_split_across_levels_is_flagged() -> None:
    body = _levelled(
        (2, "LECTURE 1"), (2, "LECTURE 2"), (3, "LECTURE 3"), (4, "LECTURE 4")
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.HEADING_LADDER)
    # Two of the four sit off the level the other two settled on.
    assert ev.metrics["heading_ladder_issues"] == 2


def test_section_sign_class_split_across_levels_is_flagged() -> None:
    body = _levelled(
        (2, "§ 1. Key terms"),
        (2, "§ 2. Rules of loads"),
        (3, "§ 3. Bound parts"),
    )
    ev = evaluate(body)
    assert ev.metrics["heading_ladder_issues"] == 1


def test_roman_numbered_class_split_across_levels_is_flagged() -> None:
    body = _levelled((3, "CHAPTER II"), (3, "CHAPTER III"), (4, "CHAPTER IV"))
    ev = evaluate(body)
    assert ev.metrics["heading_ladder_issues"] == 1


def test_repeated_title_split_across_levels_is_flagged() -> None:
    body = _levelled(
        (3, "Review questions"),
        (3, "Review questions"),
        (2, "Review questions"),
    )
    ev = evaluate(body)
    assert ev.metrics["heading_ladder_issues"] == 1


def test_even_ladder_raises_no_defect() -> None:
    body = _levelled(
        (1, "Workshop"),
        (2, "LECTURE 1"),
        (3, "Review questions"),
        (2, "LECTURE 2"),
        (3, "Review questions"),
        (2, "LECTURE 3"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)
    assert "heading_ladder_issues" not in ev.metrics


def test_scattered_ladder_without_a_jump_is_seen() -> None:
    # Every step down is by one, yet one series stands on three levels.
    body = _levelled(
        (2, "LECTURE 1"),
        (3, "LECTURE 2"),
        (4, "LECTURE 3"),
        (3, "LECTURE 4"),
        (3, "LECTURE 5"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADINGS)
    assert ev.metrics["heading_ladder_issues"] == 2


def test_two_members_are_not_a_class() -> None:
    body = _levelled((2, "LECTURE 1"), (3, "LECTURE 2"))
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_one_number_repeated_falls_back_to_the_exact_title() -> None:
    # Not a series, but three equal titles still disagree on their level.
    body = _levelled((2, "Priority 1"), (2, "Priority 1"), (4, "Priority 1"))
    ev = evaluate(body)
    assert ev.metrics["heading_ladder_issues"] == 1


def test_two_series_of_different_names_stay_apart() -> None:
    body = _levelled(
        (2, "LECTURE 1"),
        (2, "LECTURE 2"),
        (2, "LECTURE 3"),
        (3, "MODULE 1"),
        (3, "MODULE 2"),
        (3, "MODULE 3"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_number_opening_a_title_is_not_a_class() -> None:
    # A numbered title states its depth, and the numbering rule owns it.
    body = _levelled((1, "1. Rule of rest"), (1, "2. Rule of balance"))
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_ladder_never_decides_the_status() -> None:
    # In a short body the count is a real share of the structure.
    body = _levelled(
        (2, "LECTURE 1"), (3, "LECTURE 2"), (4, "LECTURE 3"), (5, "LECTURE 4")
    )
    ev = evaluate(body)
    assert ev.metrics["heading_ladder_issues"] == 3
    assert ev.status is ResultStatus.OK
    assert ev.issues == (CheckId.HEADING_LADDER.value,)


def test_ladder_ignores_a_heading_in_a_code_fence() -> None:
    body = (
        _levelled((2, "LECTURE 1"), (2, "LECTURE 2"), (2, "LECTURE 3"))
        + "\n\n```\n#### LECTURE 4\n```\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_ladder_ignores_a_crushed_block_tagged_as_a_heading() -> None:
    crushed = "A crushed block of text that the converter marked as a heading, " * 4
    body = _levelled((2, crushed), (4, crushed))
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_dotted_chain_split_across_levels_is_flagged() -> None:
    # A numbered title names no series, and each title is written once.
    settled = [(3, f"2.1.{n} Section {n}") for n in range(1, 24)]
    scattered = [(4, f"2.2.{n} Section {n}") for n in range(1, 12)]
    ev = evaluate(_levelled(*settled, *scattered))
    assert _fired(ev, CheckId.HEADING_LADDER)
    assert ev.metrics["heading_ladder_issues"] == 11


def test_even_dotted_ladder_raises_no_defect() -> None:
    body = _levelled(
        (2, "1. Introduction"),
        (3, "1.1 Problem statement"),
        (3, "1.2 Notation"),
        (2, "2. Main part"),
        (3, "2.1 Solution method"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_two_dotted_members_are_not_a_chain() -> None:
    body = _levelled((2, "3.1 First part"), (3, "3.2 Second part"))
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_one_dotted_number_repeated_is_not_a_chain() -> None:
    # One number over three sections is a repeat, not a chain of ranks.
    body = _levelled(
        (2, "4.1 Rig layout"),
        (2, "4.1 Unit layout"),
        (4, "4.1 Drive layout"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_a_number_carrying_no_dot_is_not_a_chain() -> None:
    # Bare `1`, `2`, `3` state peers, not depth.
    body = _levelled(
        (2, "1 Introduction"), (2, "2 Solution method"), (3, "3 Conclusions")
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADING_LADDER)


def test_a_heading_off_two_groups_is_counted_once() -> None:
    # The level-4 title stands off its repeated title and off its own depth.
    body = _levelled(
        (2, "6.1 Summary"),
        (2, "6.1 Summary"),
        (4, "6.1 Summary"),
        (2, "6.2 Other"),
    )
    ev = evaluate(body)
    assert ev.metrics["heading_ladder_issues"] == 1


# ---- flat ladder -------------------------------------------------------------


def test_a_ladder_flattened_where_the_numbering_states_depth_is_counted() -> None:
    # No level is skipped and no group stands off; only the numbering states
    # the depth.
    body = _levelled(
        (1, "1. Introduction"),
        (1, "1.1. Key terms"),
        (1, "1.2. Ground rules"),
        (1, "2. Loads"),
        (1, "2.1. Bending"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADINGS)
    assert not _fired(ev, CheckId.HEADING_LADDER)
    # Three of five are subsections, so the two chapters stand off the level.
    assert ev.metrics["flat_ladder_headings"] == 2
    assert ev.status is ResultStatus.BAD
    # Post has no route for a flat ladder, so no hint follows.
    assert not ev.repairable
    assert not ev.recognition_failure


def test_a_ladder_flattened_where_the_printed_contents_states_depth_is_counted() -> (
    None
):
    body = (
        "# Contents\n\n"
        "| Part | Title | Page |\n"
        "|---|---|---|\n"
        "| Introduction |  | 3 |\n"
        "|  | Key terms | 3 |\n"
        "|  | Ground rules | 5 |\n"
        "| Loads |  | 9 |\n"
        "|  | Bending | 9 |\n\n"
    ) + _levelled(
        (1, "Introduction"),
        (1, "Key terms"),
        (1, "Ground rules"),
        (1, "Loads"),
        (1, "Bending"),
    )
    ev = evaluate(body)
    # Three of five are subsections, so the two sections stand off the level.
    assert ev.metrics["flat_ladder_headings"] == 2
    assert ev.status is ResultStatus.BAD


def test_a_flat_ladder_the_body_states_no_depth_for_is_untouched() -> None:
    # Peer sections: flat is how the note was written.
    body = _levelled(
        (1, "Introduction"),
        (1, "Key terms"),
        (1, "Ground rules"),
        (1, "Loads"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FLAT_LADDER)
    assert "flat_ladder_headings" not in ev.metrics
    assert ev.status is ResultStatus.OK


def test_sections_numbered_as_peers_state_no_depth() -> None:
    # Bare numbers state peers, so the numbering is no witness.
    body = _levelled(
        (1, "1. Introduction"),
        (1, "2. Loads"),
        (1, "3. Motion"),
        (1, "4. Paths"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FLAT_LADDER)


def test_a_ladder_the_numbering_agrees_with_counts_nothing() -> None:
    # Three quarters stand on one level, and the numbering puts them there.
    body = _levelled(
        (1, "1. Introduction"),
        (2, "1.1. Key terms"),
        (2, "1.2. Ground rules"),
        (2, "1.3. Bending"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FLAT_LADDER)


def test_the_source_outline_outranks_the_numbering_of_a_title() -> None:
    # With an authored outline, cleaning settles the levels by it alone.
    body = _levelled(
        (1, "1. Introduction"),
        (1, "1.1. Key terms"),
        (1, "1.2. Ground rules"),
        (1, "2. Loads"),
        (1, "2.1. Bending"),
    )
    outline = SourceOutline(
        [
            (1, "1. Introduction"),
            (1, "1.1. Key terms"),
            (1, "1.2. Ground rules"),
            (1, "2. Loads"),
            (1, "2.1. Bending"),
        ]
    )
    ev = evaluate(body, source_outline=outline)
    assert not _fired(ev, CheckId.FLAT_LADDER)


def test_a_ladder_flattened_against_the_source_outline_is_counted() -> None:
    # The outline states the depth that the body lost.
    body = _levelled(
        (1, "Introduction"),
        (1, "Key terms"),
        (1, "Ground rules"),
        (1, "Loads"),
        (1, "Bending"),
    )
    outline = SourceOutline(
        [
            (1, "Introduction"),
            (2, "Key terms"),
            (2, "Ground rules"),
            (1, "Loads"),
            (2, "Bending"),
        ]
    )
    ev = evaluate(body, source_outline=outline)
    assert ev.metrics["flat_ladder_headings"] == 2


def test_a_numbering_depth_past_the_last_level_shares_it() -> None:
    # Seven depths do not fit six levels, so the last two share the sixth.
    body = _levelled(
        (1, "1. Section"),
        (6, "1.1.1.1.1.1. First"),
        (6, "1.1.1.1.1.1. Second"),
        (6, "1.1.1.1.1.1. Third"),
        (6, "1.1.1.1.1.1.1. Fourth"),
        (6, "1.1.1.1.1.1.2. Fifth"),
        (6, "1.1.1.1.1.1.3. Sixth"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FLAT_LADDER)


def test_deep_numbering_that_still_fits_keeps_its_ranks_apart() -> None:
    # Three depths fit six levels, so collapsing them loses a rank.
    body = _levelled(
        (6, "5.1.1.1.1. First"),
        (6, "5.1.1.1.1. Second"),
        (6, "5.1.1.1.1. Third"),
        (6, "5.1.1.1.1.1. Fourth"),
        (6, "5.1.1.1.1.1.1. Fifth"),
    )
    ev = evaluate(body)
    assert ev.metrics["flat_ladder_headings"] == 2


def test_one_demoted_section_does_not_count_the_rank_it_landed_in() -> None:
    # The level settles on its majority rank; the one intruder is the count.
    body = _levelled(
        (2, "1. First chapter"),
        (2, "1.1. First section"),
        (2, "1.2. Second section"),
        (2, "1.3. Third section"),
        (2, "1.4. Fourth section"),
    )
    ev = evaluate(body)
    assert ev.metrics["flat_ladder_headings"] == 1


def test_a_flattened_heading_inside_the_threshold_stays_minor() -> None:
    # One swallowed heading over 500 lines sits inside the scaled tolerance
    # (2 per 1000 lines): recorded in `issues`, left out of the verdict.
    headings = _levelled(
        (1, "1. Introduction"),
        (1, "2. Loads"),
        (1, "3. Motion"),
        (1, "3.1. Bending"),
    )
    ev = evaluate(_filler_lines(500) + "\n\n" + headings)
    assert ev.metrics["flat_ladder_headings"] == 1
    assert ev.status is ResultStatus.OK
    assert CheckId.FLAT_LADDER.value in ev.issues


# ---- lost chapters -----------------------------------------------------------


def _printed_contents(*entries: tuple[int, str]) -> str:
    """A converted contents page: indent as title column, page in last cell."""
    rows = ["| Part | Title | Page |", "|---|---|---|"]
    for page, (depth, title) in enumerate(entries, start=3):
        cells = ["", ""]
        cells[depth] = title
        rows.append(f"| {cells[0]} | {cells[1]} | {page} |")
    return "# Contents\n\n" + "\n".join(rows) + "\n\n"


_TWELVE_CHAPTERS = _printed_contents(
    *[(0, f"Chapter {number}. General provisions") for number in range(1, 13)],
    (1, "First section"),
)


def test_a_chapter_the_contents_states_and_the_body_never_writes_is_counted() -> None:
    # The remaining ladder reads as sound: what is gone leaves no mark.
    body = _TWELVE_CHAPTERS + _levelled((2, "First section"))
    ev = evaluate(body)
    assert ev.metrics["lost_chapters"] == 12
    assert ev.status is ResultStatus.BAD
    # The verdict is this check's own: nothing else the body carries decides it.
    assert [d.check for d in ev.defects if not d.minor] == [CheckId.LOST_CHAPTERS]
    # No hint follows: no step writes a heading the body does not carry.
    assert not ev.repairable
    assert not ev.recognition_failure


def test_chapters_the_body_writes_are_untouched() -> None:
    body = _TWELVE_CHAPTERS + _levelled(
        *[(2, f"Chapter {number}. General provisions") for number in range(1, 13)],
        (3, "First section"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_CHAPTERS)
    assert "lost_chapters" not in ev.metrics


def test_a_body_printing_no_contents_states_no_chapter() -> None:
    # Without a contents witness no chapter is stated.
    body = _levelled(
        (1, "Introduction"),
        (2, "Key terms"),
        (2, "Ground rules"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_CHAPTERS)


def test_one_chapter_inside_the_stated_share_stays_minor() -> None:
    # One of twelve reads as a missed match: in `issues`, out of the verdict.
    body = _TWELVE_CHAPTERS + _levelled(
        *[(2, f"Chapter {number}. General provisions") for number in range(1, 12)],
        (3, "First section"),
    )
    ev = evaluate(body)
    assert ev.metrics["lost_chapters"] == 1
    assert CheckId.LOST_CHAPTERS.value in ev.issues
    assert ev.status is ResultStatus.OK


def test_a_chapter_the_body_underlines_is_found() -> None:
    # An underlined heading names its section as plainly as a `#` one.
    body = _printed_contents(
        (0, "Chapter 1. General provisions"),
        (0, "Chapter 2. Balance equations"),
        (1, "First section"),
    ) + (
        "Chapter 1. General provisions\n"
        "===========================\n\n"
        "The text of chapter one fills a line.\n\n"
        "Chapter 2. Balance equations\n"
        "---------------------------\n\n"
        "The text of chapter two fills a line.\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_CHAPTERS)


def test_a_chapter_written_with_its_numbering_is_found() -> None:
    # The witness compares token sequences, so the numbering punctuation a
    # converter re-spells around one title falls out of the comparison.
    body = _printed_contents(
        (0, "1. Introduction"),
        (1, "1.1. Key terms"),
        (0, "2. Loads"),
    ) + _levelled(
        (2, "1 Introduction"),
        (3, "1.1 Key terms"),
        (2, "2 Loads"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_CHAPTERS)


def test_a_chapter_heading_with_a_rank_word_the_contents_lacks_is_found() -> None:
    # The rank word names no other chapter; the number tells them apart.
    body = _printed_contents(
        (0, "1 Introduction"),
        (0, "2 General provisions"),
        (1, "First section"),
    ) + _levelled(
        (2, "Chapter 1 Introduction"),
        (2, "Chapter 2 General provisions"),
        (3, "First section"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_CHAPTERS)


def test_a_contents_title_with_a_page_glued_on_is_found() -> None:
    # A lost grid fuses the page number onto the title's last word.
    body = _printed_contents(
        (0, "Introduction" + "7"),
        (0, "General provisions" + "12"),
        (1, "First section"),
    ) + _levelled(
        (2, "Introduction"),
        (2, "General provisions"),
        (3, "First section"),
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_CHAPTERS)


def test_chapters_differing_by_the_word_before_their_number_are_counted() -> None:
    # Three chapters share the words after a shared number; one heading must
    # not answer for all three.
    body = _printed_contents(
        (0, "Drive 1 Technical data"),
        (0, "Valve 1 Technical data"),
        (0, "Sensor 1 Technical data"),
        (1, "First section"),
    ) + _levelled(
        (2, "Drive 1 Technical data"),
        (3, "First section"),
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.LOST_CHAPTERS)


def test_a_chapter_split_across_two_headings_is_found() -> None:
    # A rank line read as its own heading, joined with the next, names the
    # chapter.
    body = _printed_contents(
        (0, "Chapter 1 Introduction"),
        (0, "Chapter 2 General provisions"),
        (1, "First section"),
    ) + (
        "## Chapter 1\n\n## Introduction\n\nA readable paragraph.\n\n"
        "## Chapter 2\n\n## General provisions\n\nA readable paragraph.\n\n"
        "### First section\n\nA readable paragraph."
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_CHAPTERS)


def test_a_rank_heading_with_text_under_it_is_not_joined_to_the_next() -> None:
    # Text under the rank heading makes it a section of its own.
    body = _printed_contents(
        (0, "Chapter 1 Introduction"),
        (1, "First section"),
    ) + _levelled(
        (2, "Chapter 1"),
        (2, "Introduction"),
        (3, "First section"),
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.LOST_CHAPTERS)


def test_a_heading_naming_more_than_the_rank_is_not_joined_to_the_next() -> None:
    # A rank heading with part of the name is a title, not half of a split one.
    body = _printed_contents(
        (0, "Chapter 1 Introduction"),
        (1, "First section"),
    ) + _levelled(
        (2, "Chapter 1 General details"),
        (2, "Introduction"),
        (3, "First section"),
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.LOST_CHAPTERS)


def test_chapters_ending_on_a_fused_designation_are_counted() -> None:
    # A title can end on fused letters and digits, so the page split is read
    # on the contents entry alone.
    body = _printed_contents(
        (0, "Standard ISO9001"),
        (0, "Standard ISO14001"),
        (0, "Standard ISO45001"),
        (1, "First section"),
    ) + _levelled(
        (2, "Standard ISO9001"),
        (3, "First section"),
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.LOST_CHAPTERS)


# ==== Layout group ============================================================


# ---- tables ------------------------------------------------------------------


def test_broken_table_row_is_flagged() -> None:
    body = "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n\nFollowing paragraph words.\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.TABLES)
    assert ev.repairable


def test_consistent_table_is_ok() -> None:
    body = "| A | B |\n|---|---|\n| 1 | 2 |\n\nFollowing paragraph with words here.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.TABLES)
    assert ev.status is ResultStatus.OK


def test_collapsed_table_row_is_flagged() -> None:
    # Every row keeps the separator's cell count, so only the grid reading
    # sees this one: the row's values stand in one cell, the rest are blank.
    body = (
        "| Fluid | Rating | Code |\n|---|---|---|\n| Glycol | 3 | K2210 |\n"
        "|  |  | Xylene<br>1<br>K5514 |\n\nFollowing paragraph words.\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.TABLES)


def test_collapsed_rows_are_flagged_where_no_row_kept_the_grid() -> None:
    # The count must not fall as damage rises: a fully broken block states no
    # column forms.
    body = (
        "| Code | Size | Mass |\n|---|---|---|\n"
        "| 7-140 88.40 4.10 |  |  |\n"
        "| 7-141 89.15 4.25 |  |  |\n\nFollowing paragraph words.\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.TABLES)


def test_table_with_an_empty_header_row_is_flagged() -> None:
    # A header row of blank cells names no column.
    body = "|  |  |\n|---|---|\n| 1 | 2 |\n\nFollowing paragraph words.\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.TABLES)


def test_table_separator_is_not_junk() -> None:
    body = "| A | B |\n|---|---|\n| 1 | 2 |\n\nFollowing paragraph with words here.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.JUNK_LINES)
    assert ev.status is ResultStatus.OK


# ---- junk lines --------------------------------------------------------------


def test_junk_lines_above_share_are_flagged() -> None:
    lines = [f"Real sentence number {i} here" for i in range(40)]
    lines += ["@@@", "%%%", "&&&"]  # 3 junk lines of ~7%
    ev = evaluate("\n".join(lines) + "\n")
    assert _fired(ev, CheckId.JUNK_LINES)
    assert ev.repairable


def test_sparse_junk_below_share_is_ok() -> None:
    lines = [f"Real sentence number {i} here" for i in range(100)]
    lines += ["@@@"]  # 1 junk line of ~1%
    ev = evaluate("\n".join(lines) + "\n")
    assert not _fired(ev, CheckId.JUNK_LINES)
    assert ev.status is ResultStatus.OK


def test_display_math_and_setext_are_not_junk() -> None:
    # The evaluator must exclude exactly the symbol lines the cleaner keeps:
    # standalone `$$` delimiters and a setext underline under a text line.
    body = (
        "Title\n====\n\n"
        + "\n".join(f"Real sentence number {i} here" for i in range(30))
        + "\n\n$$\nE = mc^2\n$$\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.JUNK_LINES)
    assert ev.status is ResultStatus.OK


def test_standalone_latex_row_separator_is_not_junk() -> None:
    body = (
        "\n".join(f"Real sentence number {i} here" for i in range(30))
        + "\n\n$$\n\\begin{array}{r}\na\n"
        + "\\" * 2
        + "\nb\n\\end{array}\n$$\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.JUNK_LINES)
    assert ev.status is ResultStatus.OK


# ---- repeats -----------------------------------------------------------------


def test_repeated_line_is_flagged() -> None:
    body = "Intro paragraph here\n" + "Header\n" * 3 + "Body text follows here now.\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)
    assert ev.repairable


def test_line_repeated_twice_is_not_flagged() -> None:
    body = "Intro paragraph here\n" + "Header\n" * 2 + "Body text follows here now.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_figure_wrappers_are_not_flagged() -> None:
    # pandoc's docx shape for 3+ captioned images: a bare <figure>/</figure>
    # pair repeats once per picture, not a recognition artifact.
    body = (
        "Intro paragraph here with plenty of real words.\n\n"
        '<figure>\n<img src="media/image1.jpeg" style="width:1in" />\n</figure>\n\n'
        '<figure>\n<img src="media/image2.jpeg" style="width:1in" />\n</figure>\n\n'
        '<figure>\n<img src="media/image3.jpeg" style="width:1in" />\n</figure>\n\n'
        "Body text follows here now with plenty of real words.\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_standalone_img_tag_is_not_flagged() -> None:
    body = (
        "Intro paragraph here with plenty of real words.\n\n"
        + ('<img src="media/placeholder.png" style="width:1in" />\n' * 3)
        + "Body text follows here now with plenty of real words.\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_math_only_line_is_not_flagged() -> None:
    # An axis label repeated under each plot is content, not a loop.
    body = (
        "Intro paragraph here with plenty of real words.\n\n"
        + "".join(
            f"$U, \\text{{V}}$\n\nCaption text for plot number {i} above.\n\n"
            for i in range(3)
        )
        + "Body text follows here now with plenty of real words.\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_display_math_only_line_is_not_flagged() -> None:
    body = (
        "Intro paragraph here with plenty of real words.\n\n"
        + "".join(
            f"$$E = mc^2$$\n\nCaption text for plot number {i} above.\n\n"
            for i in range(3)
        )
        + "Body text follows here now with plenty of real words.\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_line_mixing_text_and_math_is_still_flagged() -> None:
    # The formula is only part of the line, so the exclusion must not apply.
    body = (
        "Intro paragraph here with plenty of real words.\n\n"
        + ("Note: $U, \\text{V}$\n" * 3)
        + "Body text follows here now with plenty of real words.\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)


def test_repeated_heading_is_not_flagged() -> None:
    # A catalog repeats a section heading once per entry.
    body = "\n\n".join(
        f"#### ORDERING EXAMPLE\n\nEntry number {i} details follow here.\n"
        for i in range(5)
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_table_rows_are_not_flagged() -> None:
    # A reprinted table header is the layout repeating, not the text.
    body = (
        "Intro paragraph here with plenty of real words.\n\n"
        + "| Code | Mass |\n|------|------|\n| A-1  | 3.20 |\n" * 30
        + "\nBody text follows here now with plenty of real words.\n"
    )
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_heading_text_without_marker_is_still_flagged() -> None:
    # Without the heading marker the repeat is a real loop.
    body = (
        "Intro paragraph here with plenty of real words.\n\n"
        + ("ORDERING EXAMPLE\n" * 3)
        + "Body text follows here now with plenty of real words.\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)


def test_repeat_minimum_does_not_fire_on_large_document() -> None:
    # 7 repeats of a connective stay under the scaled minimum (~10 here).
    body = _filler_lines(10_000) + "\n" + "Connective phrase here\n" * 7
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeat_minimum_fires_above_scaled_threshold() -> None:
    body = _filler_lines(10_000) + "\n" + "Connective phrase here\n" * 15
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)


def test_formula_connective_is_not_flagged() -> None:
    # A connective on its own line between formulas is layout, not a loop.
    body = _filler_lines(10_000) + "\n" + "and\n" * 15
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_repeated_word_above_the_connector_length_is_still_flagged() -> None:
    # One character past the connective cutoff, a short-word loop still fires.
    body = _filler_lines(10_000) + "\n" + "Todo\n" * 15
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)


def test_repeated_phrase_is_still_flagged_regardless_of_connector_words() -> None:
    body = _filler_lines(10_000) + "\n" + "or and or\n" * 15
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)


def _catalog_cards(n: int, field: str) -> str:
    """`n` product cards, each opening with the same `field` line."""
    return "\n\n".join(
        field + "\n\n" + _filler_lines(20).replace("number", f"number {i} of")
        for i in range(n)
    )


def test_catalog_field_repeated_once_per_card_is_not_flagged() -> None:
    # A template field line per product card; the spacing tells it from a loop.
    ev = evaluate(_catalog_cards(14, "Trade names:"))
    assert not _fired(ev, CheckId.REPEATS)


def test_boilerplate_under_every_heading_is_not_flagged() -> None:
    # The tightest legitimate spacing: four lines apart.
    body = "".join(f"## Section {i}\n\nNot applicable\n\n" for i in range(12))
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS)


def test_loop_repeating_one_line_per_paragraph_is_still_flagged() -> None:
    # Loop copies two lines apart are still a cluster.
    body = "Intro paragraph here with plenty of real words.\n\n" + (
        "Continued on the next page\n\n" * 8
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)


def test_a_loop_with_a_distant_copy_is_still_flagged() -> None:
    # The median gap decides, so one far occurrence does not excuse the loop.
    body = (
        "Continued on the next page\n" * 8
        + "\n"
        + _filler_lines(200)
        + "\n\nContinued on the next page\n\n"
        + _filler_lines(200).replace("number", "line")
        + "\n\nContinued on the next page\n"
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)


# ==== Media group =============================================================


# ---- images ------------------------------------------------------------------

_IMG_BODY = "A readable paragraph with enough words here.\n\n![]({target})\n"


def test_missing_image_is_flagged(tmp_path: Path) -> None:
    ev = evaluate(_IMG_BODY.format(target="media/x.png"), base_dir=tmp_path)
    assert _fired(ev, CheckId.IMAGES)
    assert ev.repairable


def test_tiny_image_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "x.png").write_bytes(b"123")  # 3 bytes, below 512
    ev = evaluate(_IMG_BODY.format(target="x.png"), base_dir=tmp_path)
    assert _fired(ev, CheckId.IMAGES)
    # A tiny file is bad image content, not a repairable broken link.
    assert not ev.repairable


def test_single_color_image_is_flagged(tmp_path: Path) -> None:
    # BMP is uncompressed, so a solid image passes the 512-byte floor.
    Image.new("RGB", (40, 40), (10, 20, 30)).save(tmp_path / "solid.bmp")
    ev = evaluate(_IMG_BODY.format(target="solid.bmp"), base_dir=tmp_path)
    assert _fired(ev, CheckId.IMAGES)
    assert not ev.repairable


def test_multicolor_image_is_not_flagged(tmp_path: Path) -> None:
    img = Image.new("RGB", (40, 40), (10, 20, 30))
    img.putpixel((0, 0), (200, 100, 50))
    img.save(tmp_path / "ok.bmp")
    ev = evaluate(_IMG_BODY.format(target="ok.bmp"), base_dir=tmp_path)
    assert not _fired(ev, CheckId.IMAGES)
    assert ev.status is ResultStatus.OK


def test_encoded_existing_image_is_not_flagged(tmp_path: Path) -> None:
    # The link is percent-encoded; the file name has a literal space.
    img = Image.new("RGB", (40, 40), (10, 20, 30))
    img.putpixel((0, 0), (200, 100, 50))
    img.save(tmp_path / "x y.bmp")
    ev = evaluate(_IMG_BODY.format(target="x%20y.bmp"), base_dir=tmp_path)
    assert not _fired(ev, CheckId.IMAGES)
    assert ev.status is ResultStatus.OK


def test_traversal_target_is_not_flagged(tmp_path: Path) -> None:
    # `..` escapes base_dir; skip it even though the file exists.
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    (tmp_path / "outside.png").write_bytes(b"data")
    ev = evaluate(_IMG_BODY.format(target="../outside.png"), base_dir=base_dir)
    assert not _fired(ev, CheckId.IMAGES)


def test_encoded_drive_letter_target_is_not_flagged(tmp_path: Path) -> None:
    # Decodes to an absolute path outside base_dir; skip it like a remote URL.
    ev = evaluate(_IMG_BODY.format(target="C%3A%5Ctemp%5Cx.png"), base_dir=tmp_path)
    assert not _fired(ev, CheckId.IMAGES)


def test_remote_image_is_not_flagged(tmp_path: Path) -> None:
    target = "http://example.com/x.png"
    ev = evaluate(_IMG_BODY.format(target=target), base_dir=tmp_path)
    assert not _fired(ev, CheckId.IMAGES)


def test_images_skipped_without_base_dir() -> None:
    ev = evaluate(_IMG_BODY.format(target="media/x.png"))
    assert not _fired(ev, CheckId.IMAGES)
    assert ev.status is ResultStatus.OK


# ---- HTML <img> images (pandoc docx shape) ------------------------------------

_HTML_IMG_BODY = (
    "A readable paragraph with enough words here.\n\n"
    '<img src="{target}" style="width:1in;height:1in" />\n'
)


def test_missing_html_image_is_flagged(tmp_path: Path) -> None:
    ev = evaluate(_HTML_IMG_BODY.format(target="media/x.png"), base_dir=tmp_path)
    assert _fired(ev, CheckId.IMAGES)
    assert ev.repairable


def test_existing_html_image_is_not_flagged(tmp_path: Path) -> None:
    # BMP is uncompressed, so a small image passes the 512-byte floor.
    img = Image.new("RGB", (40, 40), (10, 20, 30))
    img.putpixel((0, 0), (200, 100, 50))
    img.save(tmp_path / "x.bmp")
    ev = evaluate(_HTML_IMG_BODY.format(target="x.bmp"), base_dir=tmp_path)
    assert not _fired(ev, CheckId.IMAGES)
    assert ev.status is ResultStatus.OK


# ---- repeated image links -----------------------------------------------------


def _repeated_image_body(n: int, target: str = "media/logo.png") -> str:
    """`n` links to `target` in distinct paragraphs; only the target repeats."""
    return (
        "\n\n".join(
            f"Distinct informative sentence number {i} appears here.\n\n"
            f"![Alt text {i}]({target})"
            for i in range(n)
        )
        + "\n"
    )


def test_repeated_image_link_is_flagged() -> None:
    ev = evaluate(_repeated_image_body(3))
    assert _fired(ev, CheckId.REPEATED_IMAGES)
    assert ev.metrics["repeated_images"] == 1


def test_pair_of_repeated_image_links_is_not_flagged() -> None:
    ev = evaluate(_repeated_image_body(2))
    assert not _fired(ev, CheckId.REPEATED_IMAGES)


def test_body_without_images_does_not_fire_repeated_images() -> None:
    ev = evaluate(_filler_lines(3))
    assert not _fired(ev, CheckId.REPEATED_IMAGES)


def test_repeated_remote_image_is_not_flagged() -> None:
    ev = evaluate(_repeated_image_body(4, target="http://example.com/logo.png"))
    assert not _fired(ev, CheckId.REPEATED_IMAGES)


def test_repeated_html_image_is_flagged() -> None:
    body = "\n\n".join(
        f"Distinct informative sentence number {i} appears here.\n\n"
        f'<img src="media/icon.png" alt="Alt text {i}" />'
        for i in range(3)
    )
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATED_IMAGES)


def test_repeated_image_does_not_drive_repairable_hint() -> None:
    ev = evaluate(_repeated_image_body(3))
    assert not ev.repairable


def test_repeated_image_alone_keeps_the_result_ok() -> None:
    # A reused logo is a signal to read, not a defect: the verdict stays ok.
    ev = evaluate(_repeated_image_body(3))
    assert ev.status is ResultStatus.OK
    assert ev.issues == (CheckId.REPEATED_IMAGES.value,)
    assert ev.metrics["repeated_images"] == 1


def test_repeated_image_stays_minor_however_many_paths_repeat() -> None:
    body = _repeated_image_body(4) + _repeated_image_body(4, target="media/icon.png")
    ev = evaluate(body)
    assert ev.metrics["repeated_images"] == 2
    assert ev.status is ResultStatus.OK


def test_repeated_image_does_not_shield_a_deciding_check() -> None:
    body = (
        _repeated_image_body(3)
        + "\n| A | B | C |\n|---|---|---|\n| 1 | 2 |\n\nFollowing paragraph words.\n"
    )
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD
    assert ev.issues == (CheckId.TABLES.value, CheckId.REPEATED_IMAGES.value)


# ==== Reported group ==========================================================


# ---- defects cleaning reported ----------------------------------------------


def test_a_reported_defect_is_flagged() -> None:
    body = "inter-\nrupted readable words here.\n"
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 1))
    assert _fired(ev, CheckId.HYPHENATION)
    assert ev.repairable


def test_more_than_ten_reported_defects_is_failure() -> None:
    body = "".join(f"line {i} text\n" for i in range(11))
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 11))
    assert _fired(ev, CheckId.HYPHENATION)
    assert ev.recognition_failure


def test_escalation_does_not_fire_on_large_document() -> None:
    # 27 defects on ~10,000 lines are noise, not a recognition failure.
    body = _filler_lines(10_000)
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 27))
    assert _fired(ev, CheckId.HYPHENATION)
    assert not ev.recognition_failure


def test_escalation_still_fires_above_scaled_threshold() -> None:
    # Same document size, enough defects to clear the scaled threshold
    # (4 per 1000 lines, ~40 here).
    body = _filler_lines(10_000)
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 60))
    assert ev.recognition_failure


def test_few_defects_in_a_long_body_do_not_make_it_bad() -> None:
    # 2 defects over ~1500 lines stay inside the scaled threshold (floor 2,
    # +2 per 1000 lines).
    body = _filler_lines(1500)
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 2))
    assert _fired(ev, CheckId.HYPHENATION)
    assert ev.status is ResultStatus.OK
    assert ev.issues == (CheckId.HYPHENATION.value,)


def test_defects_past_the_threshold_are_bad_before_they_escalate() -> None:
    # Between the two thresholds: bad, not yet a recognition failure.
    body = _filler_lines(1500)
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 10))
    assert ev.status is ResultStatus.BAD
    assert not ev.recognition_failure


def test_a_body_graded_without_a_report_fires_no_reported_check() -> None:
    # Without a cleaning report these checks stay silent.
    body = "inter-\nrupted readable words here.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HYPHENATION)
    assert not _fired(ev, CheckId.LOST_FORMULAS)


def test_the_report_decides_whatever_a_later_stage_wrote() -> None:
    # The count is the cleaning stage's own; later steps cannot move it.
    body = _filler_lines(2000)
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 1))
    assert ev.status is ResultStatus.OK
    assert ev.issues == (CheckId.HYPHENATION.value,)
    assert ev.metrics["hyphenation"] == 1
    assert ev.defect_report == ("hyphenation (1 words split across a break)",)


def test_verdict_weighs_every_defect_cleaning_reported() -> None:
    # 79 defects run far past 2 per 1000 lines, whatever a later step did.
    body = _filler_lines(2000)
    ev = evaluate(
        body,
        cleaning_findings=_left_standing("hyphenation", 79),
        cleaning_body_lines=21038,
    )
    assert ev.status is ResultStatus.BAD
    assert ev.issues == (CheckId.HYPHENATION.value,)


def test_ocr_hint_fires_when_cleaning_crossed_the_threshold() -> None:
    # Cleaning alone found enough to question the recognition.
    body = "Some short readable text line here.\n"
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 11))
    assert ev.recognition_failure


def test_ocr_hint_threshold_scales_with_the_cleaning_body_not_this_one() -> None:
    # The threshold scales by the cleaning-stage body, not the smaller body
    # post left.
    body = _filler_lines(10) + "\n"
    ev = evaluate(
        body,
        cleaning_findings=_left_standing("hyphenation", 11),
        cleaning_body_lines=10_000,
    )
    assert not ev.recognition_failure


def test_every_reported_defect_is_named_by_its_own_check() -> None:
    # Each check names its damage; a run-in heading counts as a crushed
    # paragraph.
    body = _filler_lines(200)
    ev = evaluate(
        body,
        cleaning_findings=_left_standing("hyphenation", 1)
        + _left_standing("hyphenation-gap", 1)
        + _left_standing("flattened-block", 1)
        + _left_standing("flattened-paragraphs", 1)
        + _left_standing("run-in-heading", 1),
    )
    assert ev.issues == (
        CheckId.HYPHENATION.value,
        CheckId.FLATTENED_BLOCKS.value,
    )
    assert ev.metrics["hyphenation"] == 2
    assert ev.metrics["flattened_blocks"] == 3


def test_a_crushed_block_is_named_by_its_own_check() -> None:
    # A flattened block is graded under its own name.
    body = _filler_lines(1500)
    ev = evaluate(body, cleaning_findings=_left_standing("flattened-block", 10))
    assert ev.status is ResultStatus.BAD
    assert ev.issues == (CheckId.FLATTENED_BLOCKS.value,)
    assert ev.defect_report == ("flattened_blocks (10 blocks crushed out of shape)",)


def test_each_reported_check_is_weighed_on_its_own_count() -> None:
    # Each defect has its own tolerance, not one shared by both.
    body = _filler_lines(1500)
    ev = evaluate(
        body,
        cleaning_findings=_left_standing("hyphenation", 3)
        + _left_standing("flattened-block", 3),
    )
    assert ev.status is ResultStatus.OK
    assert len(ev.issues) == 2


def test_the_ocr_hint_sums_the_reported_checks() -> None:
    # The hint sums the cleaning counts; neither alone reaches the floor of 10.
    body = "Some short readable text line here.\n"
    ev = evaluate(
        body,
        cleaning_findings=_left_standing("hyphenation", 6)
        + _left_standing("flattened-block", 6),
    )
    assert ev.recognition_failure


def test_no_check_is_named_for_a_lump_of_reported_defects() -> None:
    # No lump count under either name.
    body = _filler_lines(200)
    ev = evaluate(body, cleaning_findings=_left_standing("hyphenation", 3))
    assert "residual_anchors" not in ev.issues
    assert "residual_anchors" not in ev.metrics


# ==== LLM markers group =======================================================


# ---- LLM-OCR markers ---------------------------------------------------------


def test_ocr_marker_is_flagged() -> None:
    body = "Some recognized words and then a [?] uncertain spot in the text.\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.LLM_OCR_MARKERS)
    # OCR markers are inspection's job: not post-repairable, not a failure alone.
    assert not ev.repairable
    assert not ev.recognition_failure


# ---- lost pages --------------------------------------------------------------


def test_lost_page_marker_is_a_recognition_failure() -> None:
    body = f"Some recognized text.\n\n{lost_page_marker(12)}\n\nMore text.\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.LOST_PAGES)
    assert ev.status is ResultStatus.BAD
    assert ev.metrics["lost_pages"] == 1
    # No repair step can bring a page back; only recognizing it again can.
    assert not ev.repairable
    assert ev.recognition_failure


def test_lost_page_marker_inside_a_protected_zone_is_not_counted() -> None:
    body = f"```text\n{lost_page_marker(3)}\n```\n\nOrdinary text.\n"
    ev = evaluate(body)
    assert not _fired(ev, CheckId.LOST_PAGES)


def test_body_without_lost_pages_stays_quiet() -> None:
    ev = evaluate("A page of ordinary recognized text.\n")
    assert not _fired(ev, CheckId.LOST_PAGES)
    assert "lost_pages" not in ev.metrics


# ---- inspection coverage ------------------------------------------------------

_CLEAN_BODY = "# Title\n\nA clean paragraph with plenty of readable words.\n"


def test_barely_started_inspection_is_bad() -> None:
    # Almost no chunk answered, and the body has no other defect.
    ev = evaluate(_CLEAN_BODY, inspection_chunks=94, inspection_chunks_done=2)
    assert _fired(ev, CheckId.INSPECTION_COVERAGE)
    assert ev.status is ResultStatus.BAD
    assert ev.metrics["inspection_coverage"] < 0.1


def test_a_pass_missing_one_chunk_out_of_many_keeps_its_verdict() -> None:
    # A lost tail chunk is recorded, but it is not "barely inspected".
    ev = evaluate(_CLEAN_BODY, inspection_chunks=65, inspection_chunks_done=64)
    assert _fired(ev, CheckId.INSPECTION_COVERAGE)
    assert "inspection_coverage" in ev.issues
    assert ev.status is ResultStatus.OK


def test_a_pass_missing_one_chunk_does_not_hide_another_defect() -> None:
    body = _filler_lines(1500) + "\n" + _heading_jumps(32) + "\n"
    ev = evaluate(body, inspection_chunks=65, inspection_chunks_done=64)
    assert ev.status is ResultStatus.BAD
    assert "headings" in ev.issues


def test_a_pass_that_covered_its_whole_plan_stays_quiet() -> None:
    # Nothing lost, nothing to report.
    ev = evaluate(_CLEAN_BODY, inspection_chunks=65, inspection_chunks_done=65)
    assert not _fired(ev, CheckId.INSPECTION_COVERAGE)
    assert ev.metrics["inspection_coverage"] == 1
    assert ev.status is ResultStatus.OK


def test_unchunked_pass_skips_the_coverage_check() -> None:
    ev = evaluate(_CLEAN_BODY, inspection_chunks=None, inspection_chunks_done=None)
    assert not _fired(ev, CheckId.INSPECTION_COVERAGE)
    assert "inspection_coverage" not in ev.metrics


# ==== Coverage group ==========================================================


# ---- source coverage ----------------------------------------------------------


def test_source_coverage_measures_both_directions() -> None:
    # Two of four tokens are attested in each direction.
    witness = SourceText(["alpha beta gamma delta"])
    ev = evaluate("alpha beta epsilon zeta\n", source_text=witness)
    assert ev.metrics["result_coverage"] == 0.5
    assert ev.metrics["source_coverage"] == 0.5


def test_source_coverage_ignores_markdown_syntax() -> None:
    # Markup around the source words adds no unmatched token.
    witness = SourceText(["alpha beta gamma delta epsilon zeta"])
    body = "# Alpha\n\n**beta** `gamma`\n\n- delta\n\n| epsilon | zeta |\n|---|---|\n"
    ev = evaluate(body, source_text=witness)
    assert ev.metrics["result_coverage"] == 1.0
    assert ev.metrics["source_coverage"] == 1.0


def test_source_coverage_ignores_image_link_targets() -> None:
    # Image paths and `<img>` attributes are pipeline output, never source
    # tokens.
    witness = SourceText(["alpha beta"])
    body = (
        "alpha beta\n\n"
        "![](media/page_7_figure_3.png)\n\n"
        '<img src="media/page_8_figure_1.png" style="width:1in" />\n'
    )
    ev = evaluate(body, source_text=witness)
    assert ev.metrics["result_coverage"] == 1.0
    assert ev.metrics["source_coverage"] == 1.0


def test_source_coverage_skipped_without_a_witness() -> None:
    ev = evaluate("A clean paragraph with plenty of readable words.\n")
    assert "result_coverage" not in ev.metrics
    assert "source_coverage" not in ev.metrics


def test_source_coverage_skipped_for_a_witness_with_no_layer() -> None:
    # A scan, a docx, or a md input all yield this same empty witness.
    ev = evaluate(
        "A clean paragraph with plenty of readable words.\n",
        source_text=SourceText.empty(),
    )
    assert "result_coverage" not in ev.metrics


# ---- issues property (what the result header persists) -----------------------


def test_issues_empty_on_ok() -> None:
    ev = evaluate("# Title\n\nA clean paragraph with plenty of readable words.\n")
    assert ev.issues == ()


def test_issues_lists_check_ids_in_evaluator_order() -> None:
    # Formulas is checked, and appended to defects, before headings.
    body = (
        "# Top\n\n### Skipped level two entirely here\n\n"
        "Broken $a + {b$ inside this otherwise readable sentence.\n"
    )
    ev = evaluate(body)
    assert ev.issues == (CheckId.FORMULAS.value, CheckId.HEADINGS.value)
    assert "source_coverage" not in ev.metrics


def test_defect_report_carries_the_detail_behind_each_check() -> None:
    body = (
        "# Top\n\n### Skipped level two entirely here\n\n"
        "Broken $a + {b$ inside this otherwise readable sentence.\n"
    )
    ev = evaluate(body)
    # The same order as `issues`, with what was measured.
    assert ev.defect_report == (
        f"{CheckId.FORMULAS.value} (1 invalid)",
        f"{CheckId.HEADINGS.value} (1 level/space issues)",
    )


# ---- verdict thresholds (a small check does not decide alone) ----------------


def _heading_jumps(n: int) -> str:
    """`n` heading-level jumps, each an H3 opened directly under an H1."""
    return "\n\n".join(
        f"# Section number {i}\n\n### Subsection number {i}" for i in range(n)
    )


def _broken_formulas(n: int) -> str:
    """`n` distinct lines each carrying one syntactically invalid math span."""
    return "\n".join(
        f"Measured value {i} is $x{{{i}$ per the table.\n" for i in range(n)
    )


def _half_broken_table(rows: int) -> str:
    """A three-column table of `rows` body rows, every other one a cell short."""
    grid = ["| A | B | C |", "|---|---|---|"]
    grid += [f"| {i} | {i} |" if i % 2 else f"| {i} | {i} | {i} |" for i in range(rows)]
    return "\n".join(grid) + "\n\nFollowing paragraph words.\n"


def test_few_heading_jumps_in_a_long_body_do_not_make_it_bad() -> None:
    # 3 jumps over ~1500 lines: a scan graded almost clean.
    body = _filler_lines(1500) + "\n" + _heading_jumps(3) + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.HEADINGS)
    assert ev.status is ResultStatus.OK
    # Reported, not judged: the header keeps the finding on an ok result.
    assert ev.issues == (CheckId.HEADINGS.value,)
    assert ev.metrics["heading_issues"] == 3


def test_many_heading_jumps_in_the_same_body_are_bad() -> None:
    # The damaged neighbour of the document above, at the same size.
    body = _filler_lines(1500) + "\n" + _heading_jumps(32) + "\n"
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD


def test_a_single_heading_jump_in_a_short_body_is_still_bad() -> None:
    # The tolerance has no floor: one jump in a short document is a real share.
    body = _filler_lines(40) + "\n" + _heading_jumps(1) + "\n"
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD


def test_few_invalid_formulas_in_a_long_body_do_not_make_it_bad() -> None:
    body = _filler_lines(1500) + "\n" + _broken_formulas(2) + "\n"
    ev = evaluate(body)
    assert _fired(ev, CheckId.FORMULAS)
    assert ev.status is ResultStatus.OK


def test_invalid_formulas_past_the_threshold_are_bad_before_they_escalate() -> None:
    # Between the two thresholds: bad, not yet a recognition failure.
    body = _filler_lines(1500) + "\n" + _broken_formulas(3) + "\n"
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD
    assert not ev.recognition_failure


def test_one_repeated_line_in_a_long_body_does_not_make_it_bad() -> None:
    body = _filler_lines(1500) + "\n" + "Connective phrase here\n" * 4
    ev = evaluate(body)
    assert _fired(ev, CheckId.REPEATS)
    assert ev.status is ResultStatus.OK


def test_one_line_repeating_without_end_is_bad_on_its_own() -> None:
    # A loop is one distinct line, so the worst line's volume decides too.
    body = _filler_lines(1500) + "\n" + "Connective phrase here\n" * 40
    ev = evaluate(body)
    assert ev.metrics["repeats"] == 1
    assert ev.status is ResultStatus.BAD


def test_several_repeated_lines_in_the_same_body_are_bad() -> None:
    body = (
        _filler_lines(1500)
        + "\n"
        + "Connective phrase here\n" * 4
        + "Another phrase here\n" * 4
    )
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD


def test_a_check_without_a_threshold_decides_the_status_alone() -> None:
    # Only the small structural checks are weighed; a `[?]` marker is a defect
    # at any size.
    body = _filler_lines(1500) + "\nOne word here is [?] to the recognizer.\n"
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD
    assert ev.issues == (CheckId.LLM_OCR_MARKERS.value,)


def test_a_minor_defect_is_recorded_alongside_a_deciding_one() -> None:
    body = (
        _filler_lines(1500)
        + "\n"
        + _heading_jumps(3)
        + "\nOne word here is [?] to the recognizer.\n"
    )
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD
    assert ev.issues == (CheckId.HEADINGS.value, CheckId.LLM_OCR_MARKERS.value)
    minor = {defect.check for defect in ev.defects if defect.minor}
    assert minor == {CheckId.HEADINGS}


def test_one_broken_table_row_in_a_long_body_does_not_make_it_bad() -> None:
    # A single collapsed row in a body of thousands of lines.
    body = (
        _filler_lines(1500)
        + "\n| A | B | C |\n|---|---|---|\n| 1 | 2 |\n\nFollowing paragraph words.\n"
    )
    ev = evaluate(body)
    assert ev.status is ResultStatus.OK
    # Reported, not judged: the header keeps the finding on an ok result.
    assert ev.issues == (CheckId.TABLES.value,)
    assert ev.metrics["broken_tables"] == 1


def test_a_table_broken_down_the_middle_is_bad() -> None:
    # Half the rows of the table collapsed, well past one per 1000 body lines.
    body = _filler_lines(1500) + "\n" + _half_broken_table(40) + "\n"
    ev = evaluate(body)
    assert ev.metrics["broken_tables"] == 20
    assert ev.status is ResultStatus.BAD


def test_a_single_broken_table_row_in_a_short_body_is_still_bad() -> None:
    # No floor: one collapsed row in a short document is a real share.
    body = (
        _filler_lines(40)
        + "\n| A | B | C |\n|---|---|---|\n| 1 | 2 |\n\nFollowing paragraph words.\n"
    )
    ev = evaluate(body)
    assert ev.status is ResultStatus.BAD


def test_the_table_threshold_scales_with_the_body() -> None:
    # The same broken rows weighed against two body sizes.
    table = _half_broken_table(16)
    assert evaluate(_filler_lines(1500) + "\n" + table).status is ResultStatus.BAD
    assert evaluate(_filler_lines(20_000) + "\n" + table).status is ResultStatus.OK
