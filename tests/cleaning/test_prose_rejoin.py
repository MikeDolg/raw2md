"""Tests for the prose rules that join text a layout tore apart.

Each join needs evidence from elsewhere in the body; without it the defect is
reported instead.
"""

from __future__ import annotations

import pytest

from raw2md.cleaner import CleanOptions, clean, clean_in_place
from raw2md.mdtext.pages import page_mark, split_page_marks
from raw2md.source_text import SourceText

from ._helpers import reported

# ---- in-place fix: hyphenation rejoin ---------------------------------------


def test_hyphenation_rejoined_when_merged_form_repeats_in_the_document() -> None:
    text = (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффи-\n"
        "циент отличается.\n"
    )
    assert clean_in_place(text) == (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффициент отличается.\n"
    )


def test_hyphenation_rejoin_is_idempotent() -> None:
    text = (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффи-\n"
        "циент отличается.\n"
    )
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_two_breaks_in_a_row_rejoin_in_the_same_pass() -> None:
    # The merged line still carries the second break.
    text = (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "Первый электромотор стоит здесь.\n"
        "Второй электромотор стоит там.\n"
        "\n"
        "Третий коэффи-\n"
        "циент отличается и электромо-\n"
        "тор работает.\n"
    )
    assert clean_in_place(text) == (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "Первый электромотор стоит здесь.\n"
        "Второй электромотор стоит там.\n"
        "\n"
        "Третий коэффициент отличается и электромотор работает.\n"
    )


def test_hyphenation_not_rejoined_on_a_single_occurrence() -> None:
    # One match is too weak a basis under Russian inflection.
    text = (
        "Единственное упоминание коэффициент здесь.\n"
        "\n"
        "Третий коэффи-\n"
        "циент отличается.\n"
    )
    assert clean(text) == (
        "Единственное упоминание коэффициент здесь.\n"
        "\n"
        "Третий коэффи-\n"
        "циент отличается.\n"
    )
    assert reported(text) == "hyphenation"


def test_hyphenation_rejoined_when_the_source_text_attests_it() -> None:
    options = CleanOptions(source_text=SourceText(["См. коэффициент трения."]))
    # Joined, so no `\n` escape touches a Cyrillic word (RUF001).
    text = "\n".join(["Третий коэффи-", "циент отличается.", ""])
    assert clean_in_place(text, options) == "Третий коэффициент отличается.\n"


def test_hyphenation_not_rejoined_with_a_digit_in_either_half() -> None:
    # The merged form would confirm, so only the digit guard blocks the join.
    text = (
        "Модель M5200 используется часто.\n"
        "Модель M5200 тоже здесь.\n"
        "\n"
        "Модуль M5-\n"
        "200 применяется в схеме.\n"
    )
    assert clean_in_place(text) == text


def test_hyphenation_not_rejoined_when_hyphenated_spelling_is_conventional() -> None:
    # Three same-line hyphenated copies make it the document's own spelling.
    text = (
        "Термин коэффи-циент здесь и коэффи-циент там.\n"
        "И снова коэффи-циент рядом.\n"
        "Также коэффициент встречается тут.\n"
        "И коэффициент здесь тоже.\n"
        "\n"
        "Другой коэффи-\n"
        "циент отличается.\n"
    )
    assert clean_in_place(text) == text


def test_hyphenation_rejoined_across_a_blank_line() -> None:
    text = (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффи-\n"
        "\n"
        "циент отличается.\n"
    )
    assert clean_in_place(text) == (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффициент отличается.\n"
    )


def test_hyphenation_rejoin_across_a_blank_line_is_idempotent() -> None:
    text = (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффи-\n"
        "\n"
        "циент отличается.\n"
    )
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_hyphenation_rejoined_across_a_figure() -> None:
    text = (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромо-\n"
        "\n"
        "![](gear.png)\n"
        "\n"
        "тор отличается.\n"
    )
    assert clean_in_place(text) == (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромотор отличается.\n"
        "\n"
        "![](gear.png)\n"
    )


def test_hyphenation_rejoin_across_a_figure_is_idempotent() -> None:
    text = (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромо-\n"
        "\n"
        "![](gear.png)\n"
        "\n"
        "тор отличается.\n"
    )
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_hyphenation_rejoin_across_a_figure_keeps_a_multiline_continuation() -> None:
    # The second line of the continuation stays behind the first.
    text = (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромо-\n"
        "\n"
        "![](gear.png)\n"
        "\n"
        "тор отличается и\n"
        "продолжается дальше.\n"
    )
    assert clean_in_place(text) == (
        "Первый электромотор здесь.\n"
        "Второй электромотор тоже.\n"
        "\n"
        "Третий электромотор отличается и\n"
        "продолжается дальше.\n"
        "\n"
        "![](gear.png)\n"
    )


def test_hyphenation_gap_not_rejoined_with_a_digit_in_either_half() -> None:
    text = (
        "Модель M5200 используется часто.\n"
        "Модель M5200 тоже здесь.\n"
        "\n"
        "Модуль M5-\n"
        "\n"
        "200 применяется в схеме.\n"
    )
    assert clean_in_place(text) == text


# The body spells the merged form twice above.
_PAGE_BREAK_SPLIT = (
    "Первый коэффициент лежит в основе.\n"
    "Второй коэффициент нужен для расчёта.\n"
    "\n"
    "Третий коэффи-\n"
    "\n"
    f"{page_mark(2)}\n"
    "циент отличается.\n"
    "\n"
    "Дальше идёт своя строка.\n"
)


def test_hyphenation_rejoined_across_a_page_mark() -> None:
    assert clean_in_place(_PAGE_BREAK_SPLIT) == (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффициент отличается.\n"
        "\n"
        f"{page_mark(2)}\n"
        "Дальше идёт своя строка.\n"
    )


def test_hyphenation_rejoin_across_a_page_mark_is_idempotent() -> None:
    once = clean_in_place(_PAGE_BREAK_SPLIT)
    assert clean_in_place(once) == once


def test_a_figure_opening_the_new_page_stays_behind_its_mark() -> None:
    # Moved above the mark, the figure would be compared with the previous page.
    text = _PAGE_BREAK_SPLIT.replace(
        f"{page_mark(2)}\n",
        f"{page_mark(2)}\n![f](a.png)\n\n",
    )
    cleaned = clean_in_place(text)
    assert cleaned.index(page_mark(2)) < cleaned.index("![f](a.png)")


@pytest.mark.parametrize(
    "gap",
    [
        "{mark}![b](b.png)\n\n",
        "![a](a.png)\n\n{mark}",
        "![a](a.png)\n\n{mark}![b](b.png)\n\n",
        "{mark}",
    ],
)
def test_stripping_the_marks_gives_the_unmarked_result(gap: str) -> None:
    # The body after the strip must equal the body cleaned without inspection.
    mark_line = page_mark(2) + "\n"
    template = _PAGE_BREAK_SPLIT.replace(mark_line, gap)
    marked = clean_in_place(template.format(mark=mark_line))
    stripped, _ = split_page_marks(marked)
    assert stripped == clean_in_place(template.format(mark=""))


def test_a_page_mark_spends_none_of_the_gap_budget() -> None:
    filled_gap = _PAGE_BREAK_SPLIT.replace(
        f"\n{page_mark(2)}\n",
        f"\n![f](a.png)\n\n![f](b.png)\n{page_mark(2)}\n",
    )
    assert "Третий коэффициент отличается." in clean_in_place(filled_gap)


def test_a_carried_page_mark_leaves_the_body_the_marks_were_never_in() -> None:
    witness = [
        "Первый коэффициент лежит в основе.",
        "Второй коэффициент нужен для расчёта.",
        "",
    ]
    for gap in ([""], []):
        split = ["Третий коэффи-", *gap]
        tail = ["циент отличается.", "", "Дальше идёт своя строка.", ""]
        marked = "\n".join([*witness, *split, page_mark(2), *tail])
        plain = "\n".join([*witness, *split, *tail])
        body, pages = split_page_marks(clean_in_place(marked))
        assert body == clean_in_place(plain), gap
        assert pages, gap


def test_a_page_break_split_without_a_witness_is_reported() -> None:
    text = (
        "Обычный абзац стоит выше.\n"
        "\n"
        "Третий коэффи-\n"
        "\n"
        f"{page_mark(2)}\n"
        "циент отличается.\n"
    )
    assert clean_in_place(text) == text
    assert reported(text) == "hyphenation-gap blocks=1"


def test_a_break_whose_page_opens_on_a_new_sentence_is_left_alone() -> None:
    text = (
        "Первый коэффициент лежит в основе.\n"
        "Второй коэффициент нужен для расчёта.\n"
        "\n"
        "Третий коэффи-\n"
        "\n"
        f"{page_mark(2)}\n"
        "Следующая глава начинается здесь.\n"
    )
    assert clean_in_place(text) == text
    assert reported(text) == ""


def test_only_the_confirmed_break_across_a_page_loses_its_finding() -> None:
    text = _PAGE_BREAK_SPLIT + "\n".join(
        [
            "",
            "Здесь стоит другое переме-",
            "",
            page_mark(3),
            "щение и дальше текст.",
            "",
        ]
    )
    cleaned = clean_in_place(text)
    assert "Третий коэффициент отличается." in cleaned
    assert "Здесь стоит другое переме-" in cleaned
    assert reported(text) == "hyphenation-gap blocks=1"


# ---- in-place fix: hyphenation seam under an emphasis marker ----------------

_MARKER_SEAM_WITNESS = (
    "Первый коэффициент лежит в основе работы.\n"
    "Второй коэффициент нужен для точного расчёта.\n"
    "\n"
)


def test_a_seam_carrying_an_emphasis_marker_is_rejoined() -> None:
    # The bold closes at the line end and reopens on the next line.
    # Joined, so no `\n` escape touches a Cyrillic word (RUF001).
    split = "\n".join(["**Третий коэффи-**", "**циент отличается заметно.**", ""])
    assert clean_in_place(_MARKER_SEAM_WITNESS + split) == (
        _MARKER_SEAM_WITNESS + "**Третий коэффициент отличается заметно.**\n"
    )


def test_a_seam_without_a_marker_is_still_rejoined() -> None:
    split = "\n".join(["Третий коэффи-", "циент отличается заметно.", ""])
    assert clean_in_place(_MARKER_SEAM_WITNESS + split) == (
        _MARKER_SEAM_WITNESS + "Третий коэффициент отличается заметно.\n"
    )


def test_a_double_asterisk_inside_code_at_the_seam_is_not_a_marker() -> None:
    split = "\n".join(["Третий коэффи-`**`", "циент отличается.", ""])
    text = _MARKER_SEAM_WITNESS + split
    assert clean_in_place(text) == text
    assert "hyphenation" not in reported(text)


def test_a_marker_seam_without_a_witness_stays_a_finding() -> None:
    text = "\n".join(
        [
            "Обычный абзац стоит выше и тянется дальше.",
            "",
            "**Другой разде-**",
            "**лочка отличается заметно.**",
            "",
        ]
    )
    assert clean_in_place(text) == text
    assert reported(text) == "hyphenation"


def test_a_seam_marked_on_one_side_only_is_not_rejoined() -> None:
    # A marker on one side alone opens or closes a run of its own.
    split = "\n".join(["**Третий коэффи-**", "циент отличается заметно.", ""])
    text = _MARKER_SEAM_WITNESS + split
    assert clean_in_place(text) == text
    assert reported(text) == "hyphenation"


def test_a_seam_reopened_under_another_marker_is_not_rejoined() -> None:
    split = "\n".join(["**Третий коэффи-**", "*циент отличается заметно.*", ""])
    text = _MARKER_SEAM_WITNESS + split
    assert clean_in_place(text) == text


# ---- in-place fix: compound hyphen by majority -------------------------------

# One line per copy, so a count of spellings is a count of lines.
_HYPHENATED = "The cost-effective option matters here.\n"
_JOINED = "The costeffective option matters here.\n"


def test_a_lost_compound_hyphen_is_restored_by_the_body_majority() -> None:
    # The conversion joined the compound halves, so no line-end rule sees it.
    text = _HYPHENATED * 3 + _JOINED
    assert clean_in_place(text) == _HYPHENATED * 4


def test_a_stray_line_break_hyphen_is_dropped_by_the_body_majority() -> None:
    text = "\n".join(["Расчет нагрузки идет так."] * 3 + ["Здесь нагруз-ки видно.", ""])
    assert clean_in_place(text) == "\n".join(
        ["Расчет нагрузки идет так."] * 3 + ["Здесь нагрузки видно.", ""]
    )


def test_a_compound_without_a_majority_is_left_as_it_stands() -> None:
    text = _HYPHENATED * 2 + _JOINED * 2
    assert clean_in_place(text) == text


def test_compound_hyphen_settling_is_idempotent() -> None:
    once = clean_in_place(_HYPHENATED * 3 + _JOINED)
    assert clean_in_place(once) == once


def test_compound_hyphen_counts_reach_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = _HYPHENATED * 3 + _JOINED + "The sealring holds.\n" * 3
    text += "A seal-ring holds.\n"
    with caplog.at_level("INFO", logger="raw2md"):
        clean_in_place(text)
    assert any(
        "compound hyphens settled: 1 restored, 1 dropped" in record.message
        for record in caplog.records
    )


def test_a_compound_with_a_digit_in_either_half_is_left_alone() -> None:
    text = "\n".join(
        ["Модель M5200 используется."] * 3 + ["Модуль M5-200 в схеме.", ""]
    )
    assert clean_in_place(text) == text


def test_a_compound_two_different_breaks_claim_is_left_alone() -> None:
    # A non-breaking hyphen is a different spelling to every later search.
    non_breaking = f"The cost{chr(0x2011)}effective option matters.\n"
    text = _HYPHENATED * 3 + non_breaking + _JOINED
    assert clean_in_place(text) == text


def test_a_longer_word_holding_the_spelling_is_not_split() -> None:
    text = _HYPHENATED * 3 + "The costeffectiveness matters.\n"
    assert clean_in_place(text) == text


def test_a_compound_is_counted_in_prose_only() -> None:
    text = (
        "Use `cost-effective` in code.\n"
        "See [it](https://example.com/cost-effective).\n"
        "Then $cost-effective$ holds.\n"
        "And \\(cost-effective\\) holds too.\n"
        "\n```\ncost-effective\n```\n\n"
        "A costeffective option here.\n"
    )
    assert clean_in_place(text) == text


def test_a_display_block_on_its_own_lines_is_not_prose() -> None:
    # A per-line mask leaves the lines between lone `$$` bare.
    text = _JOINED * 3 + "$$\ncost-effective\n$$\n"
    assert clean_in_place(text) == text
    text = _HYPHENATED * 3 + "$$\ncosteffective\n$$\n"
    assert clean_in_place(text) == text


def test_a_compound_is_rewritten_in_prose_only() -> None:
    text = (
        _HYPHENATED * 3 + "Use `costeffective` in code.\n"
        "See [it](https://example.com/costeffective).\n"
        "Then $costeffective$ holds.\n"
        "And \\(costeffective\\) holds too.\n"
        "\n```\ncosteffective\n```\n"
    )
    assert clean_in_place(text) == text


def test_a_dropped_hyphen_needs_the_exact_case_the_body_uses() -> None:
    # The majority forms, but dropping the hyphen gives `NonLinear`.
    text = "Nonlinear systems apply here.\n" * 3 + "The Non-Linear case matters.\n"
    assert clean_in_place(text) == text


def test_a_restored_hyphen_needs_the_exact_case_the_body_uses() -> None:
    text = "The Cost-effective option matters.\n" * 3 + "A costeffective plan too.\n"
    assert clean_in_place(text) == text


def test_a_settled_compound_only_takes_a_spelling_the_body_already_uses() -> None:
    # Breaking `Diester` would give `Di-ester`, which the body never spells.
    text = (
        "The Di-Ester compound holds.\n"
        "Also Di-Ester again.\n"
        "Then di-ester once more.\n"
        "A Diester line too.\n"
    )
    assert clean_in_place(text) == text


def test_a_settled_compound_applies_when_the_body_spells_it_exactly() -> None:
    text = "The Di-ester compound holds.\n" * 3 + "A Diester line too.\n"
    assert clean_in_place(text) == "The Di-ester compound holds.\n" * 3 + (
        "A Di-ester line too.\n"
    )


def test_a_bare_email_local_part_is_not_hyphenated_by_the_body_majority() -> None:
    # Unmasked, the 3:1 majority would break the address in two.
    text = _HYPHENATED * 3 + "Contact costeffective@example.com now.\n"
    assert clean_in_place(text) == text


def test_an_email_in_a_mailto_link_or_code_span_is_still_untouched() -> None:
    text = _HYPHENATED * 3 + (
        "[email](mailto:costeffective@example.com) or "
        "`costeffective@example.com` in code.\n"
    )
    assert clean_in_place(text) == text


def test_word_beside_a_masked_email_is_still_settled_by_the_majority() -> None:
    text = _HYPHENATED * 3 + "See a@example.com and the costeffective plan.\n"
    assert clean_in_place(text) == _HYPHENATED * 3 + (
        "See a@example.com and the cost-effective plan.\n"
    )


# ---- in-place fix: letter-spaced runs ----------------------------------------

# Two occurrences are the floor.
_SPACED_WITNESS = "The identical values matter here.\nThe identical case too.\n"


def test_letter_spaced_run_is_joined_when_the_body_spells_the_word() -> None:
    text = _SPACED_WITNESS + "All i d e n t i c a l values follow.\n"
    assert clean_in_place(text) == _SPACED_WITNESS + "All identical values follow.\n"


def test_letter_spaced_run_without_a_witness_is_left_alone() -> None:
    text = "All i d e n t i c a l values follow.\n"
    assert clean_in_place(text) == text


def test_letter_spaced_run_needs_more_than_one_occurrence() -> None:
    once = "The identical values matter here.\n"
    text = once + "All i d e n t i c a l values follow.\n"
    assert clean_in_place(text) == text


def test_letter_spaced_run_ending_a_sentence_is_read_whole() -> None:
    text = _SPACED_WITNESS + "The values are i d e n t i c a l.\n"
    assert clean_in_place(text) == _SPACED_WITNESS + "The values are identical.\n"


def test_a_pair_of_one_letter_words_is_not_a_run() -> None:
    text = "The ab form holds.\nThe ab form again.\nCompare a b here.\n"
    assert clean_in_place(text) == text


def test_a_printed_list_of_single_letter_symbols_is_left_alone() -> None:
    text = (
        "The abc form holds.\nThe abc form again.\n\na — area\nb — width\nc — depth\n"
    )
    assert clean_in_place(text) == text


def test_letter_spaced_run_takes_in_the_group_recognition_kept_together() -> None:
    text = _SPACED_WITNESS + "All i d e n t ical values follow.\n"
    assert clean_in_place(text) == _SPACED_WITNESS + "All identical values follow.\n"


def test_letter_spaced_run_leaves_a_neighbour_the_body_uses_as_a_word() -> None:
    text = (
        "The identical values matter here.\n"
        "The identical case too.\n"
        "The identicalvalues token also occurs.\n"
        "The identicalvalues token occurs again.\n"
        "All i d e n t i c a l values follow.\n"
    )
    assert clean_in_place(text) == text.replace(
        "i d e n t i c a l values follow", "identical values follow"
    )


def test_letter_spaced_run_is_counted_in_prose_only() -> None:
    text = (
        _SPACED_WITNESS
        + "Then $i d e n t i c a l$ holds.\n"
        + "And \\(i d e n t i c a l\\) holds too.\n"
        + "$$\ni d e n t i c a l\n$$\n"
    )
    assert clean_in_place(text) == text


def test_letter_spaced_run_join_count_reaches_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = _SPACED_WITNESS + "All i d e n t i c a l values follow.\n"
    with caplog.at_level("INFO", logger="raw2md"):
        clean_in_place(text)
    assert any(
        "letter-spaced runs joined: 1" in record.message for record in caplog.records
    )


def test_letter_spaced_run_join_is_idempotent() -> None:
    text = _SPACED_WITNESS + "All i d e n t i c a l values follow.\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- flattened paragraphs (narrow-column layout) ----------------------------


# A two-column glossary read straight down the page, one line at a time.
_GLOSSARY_ENTRIES = [
    "Arbor Another name for a mill cutter shaft.",
    "This is the round bar on which the cutters are",
    "set.",
    "Broaching Machining process in which a",
    "toothed cutting tool is drawn along the bore to",
    "shape keyways and splines.",
]


def test_flattened_paragraphs_run_is_joined_where_it_continues() -> None:
    text = "\n\n".join(_GLOSSARY_ENTRIES) + "\n"
    assert clean(text) == (
        "Arbor Another name for a mill cutter shaft.\n"
        "\n"
        "This is the round bar on which the cutters are set.\n"
        "\n"
        "Broaching Machining process in which a toothed cutting "
        "tool is drawn along the bore to shape keyways and splines.\n"
    )


def test_flattened_paragraphs_run_is_idempotent() -> None:
    text = "\n\n".join(_GLOSSARY_ENTRIES) + "\n"
    once = clean(text)
    assert clean(once) == once


def test_flattened_paragraphs_join_count_reaches_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    text = "\n\n".join(_GLOSSARY_ENTRIES) + "\n"
    with caplog.at_level("INFO", logger="raw2md"):
        clean_in_place(text)
    assert any(
        "flattened paragraphs joined: 3 blocks" in record.message
        for record in caplog.records
    )


def test_flattened_paragraphs_run_below_threshold_is_left_alone() -> None:
    text = "\n\n".join(_GLOSSARY_ENTRIES[:-1]) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_join_refuses_a_repeated_seam() -> None:
    # Same words on both sides of the seam: a repeat, not a continuation.
    entries = [
        *_GLOSSARY_ENTRIES[:3],
        "Broaching Machining process in which a",
        "in which a toothed cutting tool is drawn to",
        "shape keyways and splines.",
    ]
    text = "\n\n".join(entries) + "\n"
    assert "in which a\n\nin which a toothed" in clean(text)
    assert reported(text) == ""


def test_split_word_is_reported_when_the_run_is_joined_away() -> None:
    entries = [
        "Arbor Another name for a mill cutter shaft.",
        "This is the round bar on which the cutters are",
        "set.",
        "Broaching Machining process in which a",
        "toothed cutting tool is drawn along the bore to shape the",
        "keyways and splines of the hub. It runs under a coolant, emul-",
        "sion, and the hub comes off the press finished.",
    ]
    text = "\n\n".join(entries) + "\n"
    report = reported(text)
    assert "hyphenation-gap blocks=1" in report
    assert "flattened-paragraphs" not in report


def test_flattened_paragraphs_run_broken_by_a_heading_is_not_reported() -> None:
    entries = [*_GLOSSARY_ENTRIES[:3], "### Heading", *_GLOSSARY_ENTRIES[3:]]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_run_broken_by_a_table_is_not_anchored() -> None:
    entries = [
        *_GLOSSARY_ENTRIES[:3],
        "| A | B |\n|---|---|\n| 1 | 2 |",
        *_GLOSSARY_ENTRIES[3:],
    ]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_run_broken_by_a_list_is_not_anchored() -> None:
    entries = [*_GLOSSARY_ENTRIES[:3], "- item one", *_GLOSSARY_ENTRIES[3:]]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_run_broken_by_a_figure_is_not_anchored() -> None:
    entries = [*_GLOSSARY_ENTRIES[:3], "![](gear.png)", *_GLOSSARY_ENTRIES[3:]]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_run_broken_by_a_thematic_break_is_not_anchored() -> None:
    entries = [*_GLOSSARY_ENTRIES[:3], "---", *_GLOSSARY_ENTRIES[3:]]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_run_broken_by_a_blockquote_is_not_anchored() -> None:
    entries = [*_GLOSSARY_ENTRIES[:3], "> a quote", *_GLOSSARY_ENTRIES[3:]]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_short_formula_beside_short_prose_is_not_anchored() -> None:
    entries = [
        "One equation shows the link:",
        "$$a + b = c$$",
        "Another equation shows more:",
        "$$x + y = z$$",
        "A third equation matters too:",
        "$$p + q = r$$",
    ]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_run_stops_at_a_protected_zone() -> None:
    entries = [*_GLOSSARY_ENTRIES[:3], "```\ncode\n```", *_GLOSSARY_ENTRIES[3:]]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_escaped_ordered_markers_are_not_a_flattened_paragraphs_run() -> None:
    # Escaped numbering from docx is still an enumeration.
    entries = [
        "3\\. Harlow. Layout of small assembly cells, 2011.",
        "4\\. Brandt. Fixtures for light sheet parts, 1960.",
        "5\\. Ostrom. Wear of guide rails in service, 1969.",
        "6\\. Keller. Swivel drives for transfer tables, 2015.",
        "7\\. Lindqvist. Stiffness of welded frames, 1964.",
        "8\\. Voss. Basics of fastener selection, 1978.",
    ]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_escaped_bullet_markers_are_not_a_flattened_paragraphs_run() -> None:
    entries = [
        "\\- the frame stays at room temperature;",
        "\\- the base plate does not move;",
        "\\- the two rails stay parallel;",
        "\\- friction in the joints can be neglected;",
        "\\- the load stays below five percent of the limit;",
        "\\- the weight of the cover can be neglected.",
    ]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_escaped_marker_lines_are_not_a_flattened_block() -> None:
    text = "\n".join(f"{n}\\. item {n}" for n in range(1, 8)) + "\n"
    assert clean(text) == text


# Six short blocks, each a whole entry.
_OFFICE_ENTRIES = [
    "AU - Australia, Perth Tel: +61 (0)8-9410 2210",
    "CN - China, Suzhou Tel: +86 512 6801 3300",
    "HK - Hong Kong, Kowloon Tel: +852 3102 4470",
    "IN - India, Pune Tel: +91 20 4120 5530-35",
    "JP - Japan, Osaka Tel: +81 (0)6 4390 1820",
    "KR - South Korea, Busan Tel: +82 51 710 3300",
]


def test_run_of_self_contained_entries_is_not_anchored() -> None:
    text = "\n\n".join(_OFFICE_ENTRIES) + "\n"
    assert clean(text) == text


def test_entry_broken_across_two_blocks_is_joined_and_the_rest_left_apart() -> None:
    entries = [
        *_OFFICE_ENTRIES[:3],
        "IN - India, Pune, Maharashtra,",
        "on the Deccan plateau, Tel: +91 20 4120 5530",
        *_OFFICE_ENTRIES[4:],
    ]
    text = "\n\n".join(entries) + "\n"
    joined = [
        *_OFFICE_ENTRIES[:3],
        "IN - India, Pune, Maharashtra, on the Deccan plateau, Tel: +91 20 4120 5530",
        *_OFFICE_ENTRIES[4:],
    ]
    assert clean(text) == "\n\n".join(joined) + "\n"


def test_lowercase_key_after_a_finished_entry_is_not_a_continuation() -> None:
    entries = [
        "A: Axis distance of rollers [mm]",
        "R: Radius of driven roller [mm]",
        "E: Strain as a decimal (e.g. 5 % = 0.05)",
        "r: Hub inner radius [mm]",
        "L: Length of chain loop [mm]",
        "K: Correction factor",
    ]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_split_word_across_blocks_anchors_the_run() -> None:
    # Nothing attests the merged word, so the pair is not joined.
    entries = [
        "Допустимая нагрузка на ось 250 ньютонов",
        "Погонная масса 87 кг/км",
        "Наличие свинца в покрытии Есть",
        "Стойкость к воздействию агрессив-",
        "ным средам Наличие меди Нет",
        "Класс защиты по IEC 60529",
    ]
    text = "\n\n".join(entries) + "\n"
    assert "flattened-paragraphs blocks=5" in reported(text)
    assert f"{entries[3]}\n\n{entries[4]}" in clean(text)


def test_legend_entry_declaring_a_symbol_is_not_a_continuation() -> None:
    entries = [
        "where",
        "Dn = shaft diameter [mm]",
        "dn = hub diameter [mm]",
        "W = sleeve thickness [mm]",
        "c = 2.47 material factor, valid for Delvane and",
        "Korvex materials",
        "k = Temperature constant:",
    ]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text


def test_flattened_paragraphs_run_with_an_oversize_fragment_is_not_anchored() -> None:
    # Word by word, since a repeated phrase would read as a repetition loop.
    long_entry = " ".join(f"word{n}" for n in range(40))
    entries = [*_GLOSSARY_ENTRIES[:3], long_entry, *_GLOSSARY_ENTRIES[3:]]
    text = "\n\n".join(entries) + "\n"
    assert clean(text) == text
