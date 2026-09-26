"""Tests for the prose rules that read one line at a time."""

from __future__ import annotations

import string
import unicodedata
from dataclasses import replace

import pytest

from raw2md.cleaner import CleanOptions, clean, clean_in_place
from raw2md.cleaning.prose import _HOMOGLYPH_LATIN_TO_CYRILLIC, is_caption_label
from raw2md.keywords import default_keywords
from raw2md.mdtext.pages import page_mark

# A soft hyphen and the zero-width family (joiner, non-joiner, space, BOM).
SOFT_HYPHEN = chr(0x00AD)
ZWSP = chr(0x200B)
ZWNJ = chr(0x200C)
ZWJ = chr(0x200D)
BOM = chr(0xFEFF)

# ---- junk lines --------------------------------------------------------------


def test_drops_stray_symbol_run() -> None:
    # A `=====` run not under a text line is stray junk, not a setext underline.
    assert clean_in_place("a\n\n=====\nb\n") == "a\n\nb\n"


def test_drops_bullet_and_dot_noise() -> None:
    assert clean_in_place("a\n....\nb\n•••\nc\n") == "a\nb\nc\n"


def test_keeps_a_single_lone_symbol() -> None:
    assert clean_in_place("a\n-\nb\n") == "a\n-\nb\n"


def test_keeps_thematic_breaks() -> None:
    assert clean_in_place("a\n---\n***\n___\nb\n") == "a\n---\n***\n___\nb\n"


def test_keeps_spaced_thematic_break() -> None:
    assert clean_in_place("a\n* * *\nb\n") == "a\n* * *\nb\n"


def test_keeps_table_separator_row() -> None:
    text = "| H | I |\n|---|---|\n| 1 | 2 |\n"
    assert clean_in_place(text) == text


def test_keeps_aligned_table_separator_row() -> None:
    assert clean_in_place("a\n| :---: | ---: |\nb\n") == "a\n| :---: | ---: |\nb\n"


def test_keeps_line_with_alphanumerics() -> None:
    assert clean_in_place("text===\n") == "text===\n"


def test_keeps_cyrillic_line() -> None:
    assert clean_in_place("Текст\n") == "Текст\n"


def test_keeps_standalone_latex_row_separator() -> None:
    # `\\` alone on a line is a LaTeX row separator.
    text = "a\n" + "\\" * 2 + "\nb\n"
    assert clean_in_place(text) == text


def test_keeps_standalone_doubled_latex_row_separator() -> None:
    assert clean_in_place("a\n" + "\\" * 4 + "\nb\n") == "a\n" + "\\" * 4 + "\nb\n"


def test_drops_odd_backslash_run_as_junk() -> None:
    assert clean_in_place("a\n" + "\\" * 3 + "\nb\n") == "a\nb\n"


def test_keeps_a_symbol_only_row_inside_a_display_block() -> None:
    text = (
        "$$D = \\begin{bmatrix}\nv_1 & & \\\\\n& . & \\\\\n& & v_N\n\\end{bmatrix}$$\n"
    )
    assert clean_in_place(text) == text


def test_a_display_block_line_gets_no_prose_fix() -> None:
    text = "$$\n\\text{Tаблица} = x\n$$\n"  # noqa: RUF001 -- mixed-script sample
    assert clean_in_place(text) == text


def test_an_unpaired_display_delimiter_stops_at_its_paragraph() -> None:
    # An unpaired `$$` opens no block, so the prose after it is still fixed.
    text = "Broken $$ formula\n\n.,;:\n\nTаблица 1\n"  # noqa: RUF001 -- homoglyph
    assert clean_in_place(text) == "Broken $$ formula\n\nТаблица 1\n"  # noqa: RUF001


# ---- invisible format characters -----------------------------------------


def test_soft_hyphen_removed_mid_word() -> None:
    text = "cam" + SOFT_HYPHEN + "shaf" + SOFT_HYPHEN + "ts\n"
    assert clean_in_place(text) == "camshafts\n"


def test_zero_width_chars_removed_mid_word() -> None:
    text = "a" + ZWSP + "b" + ZWNJ + "c" + ZWJ + "d" + BOM + "e\n"
    assert clean_in_place(text) == "abcde\n"


def test_invisible_format_char_in_code_fence_is_untouched() -> None:
    text = "```\na" + SOFT_HYPHEN + "b\n```\n"
    assert clean_in_place(text) == text


def test_invisible_format_char_in_html_table_is_untouched() -> None:
    text = "<table><tr><td>a" + SOFT_HYPHEN + "b</td></tr></table>\n"
    assert clean_in_place(text) == text


def test_degree_celsius_sign_is_untouched() -> None:
    text = "200℃\n"
    assert clean_in_place(text) == text


def test_ordinary_hyphen_is_untouched() -> None:
    assert clean_in_place("M5-200\n") == "M5-200\n"


def test_invisible_format_strip_is_idempotent() -> None:
    text = "cam" + SOFT_HYPHEN + "shafts\n"
    once = clean_in_place(text)
    assert clean_in_place(once) == once


# ---- homoglyphs ----------------------------------------------------------


def test_homoglyph_table_pairs_ascii_letters_with_cyrillic_ones() -> None:
    pairs = _HOMOGLYPH_LATIN_TO_CYRILLIC
    assert all(latin in string.ascii_letters for latin in pairs)
    assert all(unicodedata.name(cyr).startswith("CYRILLIC ") for cyr in pairs.values())
    assert all(latin.isupper() == cyr.isupper() for latin, cyr in pairs.items())
    assert len(set(pairs.values())) == len(pairs)


def test_latin_capital_homoglyph_normalized() -> None:
    assert clean_in_place("Tаблица 1\n") == "Таблица 1\n"  # noqa: RUF001


def test_multiple_latin_homoglyphs_normalized_despite_latin_majority() -> None:
    # One Cyrillic letter has no Latin double; it anchors the word as Cyrillic.
    assert clean_in_place("наcoca\n") == "насоса\n"  # noqa: RUF001


def test_latin_capital_m_homoglyph_normalized() -> None:
    assert clean_in_place("Mини\n") == "Мини\n"


def test_trailing_latin_y_homoglyph_normalized() -> None:
    assert clean_in_place("нагрузкy\n") == "нагрузку\n"  # noqa: RUF001


def test_hyphenated_latin_u_is_untouched() -> None:
    text = "U-образного сечения\n"
    assert clean_in_place(text) == text


def test_latin_abbreviation_is_untouched() -> None:
    text = "стандарт ISO и DIN\n"
    assert clean_in_place(text) == text


def test_pure_latin_word_of_doubler_letters_is_untouched() -> None:
    text = "cop\n"
    assert clean_in_place(text) == text


def test_pure_cyrillic_word_is_untouched() -> None:
    text = "Таблица насоса\n"
    assert clean_in_place(text) == text


def test_homoglyph_in_code_fence_is_untouched() -> None:
    text = "```\nTаблица\n```\n"  # noqa: RUF001
    assert clean_in_place(text) == text


def test_homoglyph_in_html_table_is_untouched() -> None:
    text = "<table><tr><td>Tаблица</td></tr></table>\n"  # noqa: RUF001
    assert clean_in_place(text) == text


def test_homoglyph_in_link_target_is_untouched() -> None:
    text = "[src](docs/Tаблица.md)\n"  # noqa: RUF001
    assert clean_in_place(text) == text


def test_homoglyph_in_link_text_is_normalized_target_kept() -> None:
    text = "[Tаблица](docs/report.md)\n"  # noqa: RUF001
    assert clean_in_place(text) == "[Таблица](docs/report.md)\n"


def test_homoglyph_reference_link_label_kept_in_sync_with_definition() -> None:
    # The label ties the use site to the definition; both sides stay.
    text = "See [Tаблица][Tаблица] below.\n\n[Tаблица]: docs/report.md\n"  # noqa: RUF001
    expected = "See [Таблица][Tаблица] below.\n\n[Tаблица]: docs/report.md\n"  # noqa: RUF001
    assert clean_in_place(text) == expected


def test_homoglyph_normalization_is_idempotent() -> None:
    text = "Tаблица наcoca\n"  # noqa: RUF001
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_cyrillic_homoglyph_normalized_toward_latin() -> None:
    assert clean_in_place("TORСH\n") == "TORCH\n"  # noqa: RUF001


def test_latin_direction_normalized_despite_cyrillic_majority() -> None:
    assert clean_in_place("GAZС\n") == "GAZC\n"  # noqa: RUF001


def test_cyrillic_word_of_only_ambiguous_letters_untouched() -> None:
    text = "сор\n"  # noqa: RUF001
    assert clean_in_place(text) == text


def test_latin_direction_blocked_by_a_cyrillic_anchor() -> None:
    text = "Sбс\n"  # noqa: RUF001
    assert clean_in_place(text) == text


def test_cyrillic_homoglyph_in_link_target_is_untouched() -> None:
    text = "[src](docs/TORСH.md)\n"  # noqa: RUF001
    assert clean_in_place(text) == text


def test_cyrillic_homoglyph_in_link_text_is_normalized_target_kept() -> None:
    text = "[TORСH](docs/report.md)\n"  # noqa: RUF001
    assert clean_in_place(text) == "[TORCH](docs/report.md)\n"


def test_latin_direction_normalization_is_idempotent() -> None:
    once = clean_in_place("TORСH\n")  # noqa: RUF001
    assert clean_in_place(once) == once


# ---- html anchors and internal links ------------------------------------------


def test_strips_empty_span_anchor() -> None:
    text = '<span id="page-50-2"></span>Text\n'
    assert clean_in_place(text) == "Text\n"


def test_unwraps_internal_link_to_its_text() -> None:
    text = "See Table [2,](#page-49-0) section\n"
    assert clean_in_place(text) == "See Table 2, section\n"


def test_span_and_internal_link_together() -> None:
    text = '<span id="page-55-2"></span>See Table [2,](#page-49-0) section\n'
    assert clean_in_place(text) == "See Table 2, section\n"


def test_span_before_image_link_is_stripped() -> None:
    text = '<span id="page-4-1"></span>![alt](img.jpeg)\n'
    assert clean_in_place(text) == "![alt](img.jpeg)\n"


def test_image_link_is_untouched() -> None:
    text = "![alt](img.png)\n"
    assert clean_in_place(text) == text


def test_external_link_with_scheme_is_untouched() -> None:
    text = "[site](https://example.com)\n"
    assert clean_in_place(text) == text


def test_mailto_link_is_untouched() -> None:
    text = "[me](mailto:me@example.com)\n"
    assert clean_in_place(text) == text


def test_internal_link_with_title_is_unwrapped() -> None:
    text = '[text](#target "title")\n'
    assert clean_in_place(text) == "text\n"


def test_span_in_code_fence_is_not_stripped() -> None:
    text = '```\n<span id="page-1-0"></span>\n```\n'
    assert clean_in_place(text) == text


def test_span_in_html_table_is_not_stripped() -> None:
    text = '<table>\n<tr><td><span id="page-1-0"></span></td></tr>\n</table>\n'
    assert clean_in_place(text) == text


def test_span_strip_runs_before_heading_numbering() -> None:
    # An anchor before the number hides it from `_HEADING_NUM_RE`.
    text = '#### <span id="page-50-2"></span>6.1.1.1 A\n### 6.1.1.2 B\n'
    assert clean_in_place(text) == "### 6.1.1.1 A\n### 6.1.1.2 B\n"


def test_anchor_stripping_is_idempotent() -> None:
    text = 'See Table <span id="x"></span>[2,](#page-49-0) section\n'
    once = clean(text)
    assert clean(once) == once


# ---- page furniture left standing as prose --------------------------------------

# Plain text: the converter did not mark the band as a heading.
FURNITURE_HEADER = "Bulletin of Machine Design"


def _paged_body(margins: list[list[str]], filler: int = 12) -> str:
    """A document whose page `n` closes with the margin lines `margins[n - 1]`.

    The filler is unique per line, so only the margin repeats. The opening ATX
    heading keeps heading recovery off the lines under test.
    """
    lines = ["# Report"]
    for page, margin in enumerate(margins, start=1):
        lines.extend(
            f"Body line {page}.{index} of the section under discussion."
            for index in range(filler)
        )
        lines.extend(margin)
    return "\n\n".join(lines) + "\n"


def test_a_running_header_and_its_page_number_are_dropped_as_a_pair() -> None:
    text = _paged_body(
        [[FURNITURE_HEADER, f"MARCH 2014, Vol. 31 / 04200{page}"] for page in range(4)]
    )
    assert clean_in_place(text) == _paged_body([[] for _ in range(4)])


def test_a_page_number_printed_above_its_header_is_dropped_too() -> None:
    text = _paged_body(
        [[f"MARCH 2014, Vol. 31 / 04200{page}", FURNITURE_HEADER] for page in range(4)]
    )
    assert clean_in_place(text) == _paged_body([[] for _ in range(4)])


def test_a_bold_running_header_is_dropped_with_its_page_number() -> None:
    text = _paged_body(
        [
            [f"**{FURNITURE_HEADER}**", f"MARCH 2014, Vol. 31 / 04200{page}"]
            for page in range(4)
        ]
    )
    assert clean_in_place(text) == _paged_body([[] for _ in range(4)])


def test_a_repeated_line_without_a_numbered_neighbour_is_kept() -> None:
    text = _paged_body([[FURNITURE_HEADER] for _ in range(4)])
    assert clean_in_place(text) == text


def test_a_neighbour_repeating_its_own_number_is_kept() -> None:
    text = _paged_body([[FURNITURE_HEADER, "MARCH 2014, Vol. 31"] for _ in range(4)])
    assert clean_in_place(text) == text


def test_a_neighbour_repeating_its_own_number_in_another_case_is_kept() -> None:
    text = _paged_body(
        [
            [FURNITURE_HEADER, "200 MM"],
            [FURNITURE_HEADER, "200 mm"],
            [FURNITURE_HEADER, "200 MM"],
            [FURNITURE_HEADER, "200 mm"],
        ]
    )
    assert clean_in_place(text) == text


def test_a_catalog_card_field_repeating_per_card_is_kept() -> None:
    text = _paged_body(
        [["Part number", f"KX-{page}0 mm"] for page in range(5)], filler=2
    )
    assert clean_in_place(text) == text


def test_a_numbered_caption_is_not_read_as_a_page_number() -> None:
    # A caption number changes per occurrence like a page number.
    text = _paged_body([["Measured values", f"Table {page}"] for page in range(4)])
    assert clean_in_place(text) == text


def test_the_caption_veto_reads_the_words_of_the_dictionary() -> None:
    options = CleanOptions(
        keywords=replace(default_keywords(), caption_labels=("plate",))
    )
    text = _paged_body([["Measured values", f"Table {page}"] for page in range(4)])
    assert clean_in_place(text, options) != text
    vetoed = _paged_body([["Measured values", f"Plate {page}"] for page in range(4)])
    assert clean_in_place(vetoed, options) == vetoed


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Figure No. 12", True),
        ("Figure No. 12.", True),
        ("Fig. 3", True),
        ("Figure 12", True),
        ("Figure No. 12 shows", False),
        ("Figure No.", False),
    ],
)
def test_a_caption_label_of_several_words_is_read_whole(
    line: str, expected: bool
) -> None:
    # A longer record sharing a first word with a shorter one must still be tried.
    keywords = replace(
        default_keywords(), caption_labels=("figure", "fig", "figure no.")
    )
    assert is_caption_label(line, keywords) is expected


def test_a_short_numbered_sentence_is_not_read_as_a_page_number() -> None:
    text = _paged_body([["Case Study", f"Method {page} applies."] for page in range(4)])
    assert clean_in_place(text) == text


def test_a_repeated_sentence_beside_a_number_is_kept() -> None:
    text = _paged_body(
        [
            ["Dimensions are given in millimetres.", f"Order {page}0"]
            for page in range(4)
        ]
    )
    assert clean_in_place(text) == text


def test_a_sentence_citing_a_numbered_table_is_kept() -> None:
    text = _paged_body(
        [
            [
                "For special duty, the plant can supply other grades.",
                f"The grade pairs we stock are given in Table {page}.",
            ]
            for page in range(4)
        ]
    )
    assert clean_in_place(text) == text


def test_a_sentence_tail_beside_a_number_is_kept() -> None:
    text = _paged_body(
        [["peaks, etc.", f"Table {page}: available range"] for page in range(4)]
    )
    assert clean_in_place(text) == text


def test_a_setext_heading_over_a_numbered_line_is_kept() -> None:
    # Dropping the text would leave the setext underline as a stray rule.
    text = _paged_body(
        [[f"Table {page}", "Case Study\n----------"] for page in range(4)]
    )
    assert clean_in_place(text) == text


def test_a_band_standing_on_too_few_pages_is_kept() -> None:
    text = _paged_body(
        [[FURNITURE_HEADER, f"MARCH 2014, Vol. 31 / 04200{page}"] for page in range(3)]
    )
    assert clean_in_place(text) == text


def test_a_page_mark_between_the_two_halves_blocks_the_pair() -> None:
    margins = [
        [FURNITURE_HEADER, page_mark(page + 1), f"MARCH 2014, Vol. 31 / 04200{page}"]
        for page in range(4)
    ]
    text = _paged_body(margins)
    assert clean_in_place(text) == text


def test_a_running_header_in_a_code_fence_does_not_count_as_a_copy() -> None:
    margins = [
        [FURNITURE_HEADER, f"MARCH 2014, Vol. 31 / 04200{page}"] for page in range(2)
    ]
    margins.extend(
        [f"```\n{FURNITURE_HEADER}\n\nMARCH 2014, Vol. 31 / 04200{page}\n```"]
        for page in range(2, 4)
    )
    text = _paged_body(margins)
    assert clean_in_place(text) == text


def test_a_document_without_a_page_band_is_unchanged() -> None:
    text = _paged_body([[] for _ in range(4)])
    assert clean_in_place(text) == text


def test_page_furniture_removal_is_idempotent() -> None:
    text = _paged_body(
        [[FURNITURE_HEADER, f"MARCH 2014, Vol. 31 / 04200{page}"] for page in range(4)]
    )
    once = clean(text)
    assert clean(once) == once


# ---- alt file path -------------------------------------------------------------


def test_drops_windows_absolute_path_alt_markdown() -> None:
    text = "![C:\\Users\\Mike\\Desktop\\Photo.jpg](media/image1.jpg)\n"
    assert clean_in_place(text) == "![](media/image1.jpg)\n"


def test_drops_unc_path_alt_markdown() -> None:
    text = "![\\\\server\\share\\Pictures\\img.png](media/image1.png)\n"
    assert clean_in_place(text) == "![](media/image1.png)\n"


def test_drops_bare_filename_alt_markdown() -> None:
    text = "![image1.png](media/image1.png)\n"
    assert clean_in_place(text) == "![](media/image1.png)\n"


def test_meaningful_caption_alt_markdown_untouched() -> None:
    text = "![Deviation chart](media/image1.png)\n"
    assert clean_in_place(text) == text


def test_drops_windows_absolute_path_alt_html_img() -> None:
    text = '<img src="media/image1.jpg" alt="C:\\Users\\Mike\\Desktop\\Photo.jpg" />\n'
    assert clean_in_place(text) == '<img src="media/image1.jpg" alt="" />\n'


def test_drops_bare_filename_alt_html_img() -> None:
    text = '<img alt="image1.png" src="media/image1.png" />\n'
    assert clean_in_place(text) == '<img alt="" src="media/image1.png" />\n'


def test_meaningful_caption_alt_html_img_untouched() -> None:
    text = '<img src="media/image1.png" alt="Deviation chart" />\n'
    assert clean_in_place(text) == text


def test_drops_path_alt_inside_html_table() -> None:
    text = (
        "<table>\n"
        '<tr><td><img src="media/image1.png" alt="C:\\photo.png" /></td></tr>\n'
        "</table>\n"
    )
    expected = (
        '<table>\n<tr><td><img src="media/image1.png" alt="" /></td></tr>\n</table>\n'
    )
    assert clean_in_place(text) == expected


def test_src_and_table_markup_untouched_by_alt_strip() -> None:
    text = (
        "<table>\n"
        "<tr><td>\n"
        '<img src="media/image1.png" alt="C:\\photo.png" />\n'
        "</td></tr>\n"
        "</table>\n"
    )
    assert 'src="media/image1.png"' in clean_in_place(text)
    assert clean_in_place(text).count("<tr>") == text.count("<tr>")


def test_meaningful_alt_inside_html_table_untouched() -> None:
    text = (
        "<table>\n"
        '<tr><td><img src="media/image1.png" alt="Deviation chart" /></td></tr>\n'
        "</table>\n"
    )
    assert clean_in_place(text) == text


def test_alt_path_strip_in_fence_is_not_stripped() -> None:
    text = '```\n<img src="media/image1.png" alt="C:\\photo.png" />\n```\n'
    assert clean_in_place(text) == text


def test_alt_path_strip_is_idempotent() -> None:
    text = "![C:\\Users\\Mike\\Desktop\\Photo.jpg](media/image1.jpg)\n"
    once = clean(text)
    assert clean(once) == once


def test_alt_path_strip_in_html_table_is_idempotent() -> None:
    text = (
        "<table>\n"
        '<tr><td><img src="media/image1.png" alt="C:\\photo.png" /></td></tr>\n'
        "</table>\n"
    )
    once = clean(text)
    assert clean(once) == once


# ---- whole-paragraph emphasis ----------------------------------------------

# Past the length floor with three sentences: prose, not emphasis.
_BOLD_PARAGRAPH = (
    "**Резьбовые соединения применяют для деталей, требующих разборки. "
    "Они передают значительные осевые нагрузки без проскальзывания. "
    "Затяжку контролируют динамометрическим ключом.**\n"
)
_PLAIN_PARAGRAPH = _BOLD_PARAGRAPH.replace("**", "")


def test_bold_wrapping_a_whole_paragraph_is_stripped() -> None:
    assert clean_in_place(_BOLD_PARAGRAPH) == _PLAIN_PARAGRAPH


def test_underscore_wrapping_a_whole_paragraph_is_stripped() -> None:
    text = _BOLD_PARAGRAPH.replace("**", "__")
    assert clean_in_place(text) == _PLAIN_PARAGRAPH


def test_a_bold_phrase_inside_a_paragraph_is_left_alone() -> None:
    text = "Это **важное** условие, которое нельзя нарушать при монтаже узла.\n"
    assert clean_in_place(text) == text


def test_a_short_bold_line_keeps_its_markers_below_the_length_floor() -> None:
    text = "**Внимание. Кожух не снимать.**\n"
    assert clean_in_place(text) == text


def test_a_single_long_bold_sentence_keeps_its_markers() -> None:
    text = (
        "**Настоящий раздел устанавливает требования к материалам, применяемым "
        "при изготовлении несущих элементов подъёмных сооружений и их опор.**\n"
    )
    assert clean_in_place(text) == text


def test_a_bold_wrapped_heading_is_handled_by_the_heading_rule_only() -> None:
    text = (
        "## **Общие положения. Настоящий стандарт распространяется на стальные "
        "трубы для магистральных трубопроводов и отводов к ним.**\n"
    )
    assert clean_in_place(text) == (
        "## Общие положения. Настоящий стандарт распространяется на стальные "
        "трубы для магистральных трубопроводов и отводов к ним.\n"
    )


def test_a_bold_line_that_is_not_its_own_paragraph_is_left_alone() -> None:
    text = (
        "Вводный абзац идёт без пропуска строки перед выделением.\n"
        "**Затем следует фрагмент, который тянется на две фразы. "
        "Вторая нужна, чтобы длина и счёт фраз прошли пороги.**\n"
    )
    assert clean_in_place(text) == text


def test_whole_paragraph_emphasis_in_a_code_fence_is_kept() -> None:
    text = f"```\n{_BOLD_PARAGRAPH}```\n"
    assert clean_in_place(text) == text


def test_whole_paragraph_emphasis_strip_is_idempotent() -> None:
    once = clean(_BOLD_PARAGRAPH)
    assert clean(once) == once


def test_whole_paragraph_emphasis_drop_count_reaches_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="raw2md"):
        clean_in_place(_BOLD_PARAGRAPH)
    assert any(
        "whole-paragraph emphasis dropped: 1" in record.message
        for record in caplog.records
    )


# The bold closes before an italic unit and opens again after it.
_BOLD_PARAGRAPH_WITH_ISLAND = (
    "**Резьбовые соединения применяют для деталей, требующих периодической "
    "разборки при обслуживании узла. Расчётную осевую нагрузку принимают "
    "равной около** *15 кН* **на одно резьбовое соединение; затяжку "
    "контролируют динамометрическим ключом по карте.**\n"
)
_PLAIN_PARAGRAPH_WITH_ISLAND = _BOLD_PARAGRAPH_WITH_ISLAND.replace("**", "")


def test_bold_wrapping_a_paragraph_broken_by_an_island_is_stripped() -> None:
    assert clean_in_place(_BOLD_PARAGRAPH_WITH_ISLAND) == _PLAIN_PARAGRAPH_WITH_ISLAND


def test_island_strip_removes_only_the_bold_markers() -> None:
    result = clean_in_place(_BOLD_PARAGRAPH_WITH_ISLAND)
    assert result == _BOLD_PARAGRAPH_WITH_ISLAND.replace("**", "")
    assert "*15 кН*" in result


def test_island_strip_is_idempotent() -> None:
    once = clean(_BOLD_PARAGRAPH_WITH_ISLAND)
    assert clean(once) == once


def test_a_marker_a_code_span_quotes_survives_the_island_strip() -> None:
    quoted = _BOLD_PARAGRAPH_WITH_ISLAND.replace("*15 кН*", "`**15 кН**`")
    result = clean_in_place(quoted)
    assert "`**15 кН**`" in result
    assert not result.startswith("**")


def test_a_bold_caption_with_an_italic_label_is_left_alone() -> None:
    text = "**Рис. 5.** *продольный разрез* **общий вид резьбового соединения.**\n"
    assert clean_in_place(text) == text


def test_a_bold_phrase_in_a_long_paragraph_is_left_alone() -> None:
    text = (
        "Момент затяжки резьбового соединения задают технологической картой, "
        "и **превышение расчётного значения** ведёт к смятию опорного бурта "
        "и потере несущей способности стыка при переменной нагрузке.\n"
    )
    assert clean_in_place(text) == text


# The islands together run past the 32-character ceiling.
_BOLD_PARAGRAPH_WITH_TWO_ISLANDS = (
    "**Осевую силу предварительной затяжки резьбового соединения принимают "
    "равной около** *трёх четвертей предела текучести* **материала болта. "
    "Рабочую нагрузку на стык при этом ограничивают величиной** *одной "
    "четверти осевой силы* **и момент затяжки контролируют динамометрическим "
    "ключом по технологической карте сборки узла.**\n"
)


def test_bold_wrap_broken_by_italic_islands_past_the_ceiling_is_stripped() -> None:
    result = clean_in_place(_BOLD_PARAGRAPH_WITH_TWO_ISLANDS)
    assert result == _BOLD_PARAGRAPH_WITH_TWO_ISLANDS.replace("**", "")
    assert "*трёх четвертей предела текучести*" in result
    assert "*одной четверти осевой силы*" in result


def test_bold_wrap_with_islands_strip_is_idempotent() -> None:
    once = clean(_BOLD_PARAGRAPH_WITH_TWO_ISLANDS)
    assert clean(once) == once


def test_unmarked_prose_past_the_ceiling_keeps_the_wrap() -> None:
    text = (
        "**Момент затяжки резьбового соединения задают технологической картой "
        "сборки узла** и превышение расчётного значения ведёт к смятию опорного "
        "бурта детали, *см. пункт 4,* **что снижает несущую способность стыка "
        "при переменной эксплуатационной нагрузке в течение всего срока службы.**\n"
    )
    assert clean_in_place(text) == text


# ---- bold span glued into a word --------------------------------------------


def test_bold_span_glued_after_a_word_loses_its_markers() -> None:
    text = "The **R**otary **A**xis **SP**eed **L**imiter runs quietly.\n"
    assert clean_in_place(text) == ("The Rotary Axis SPeed Limiter runs quietly.\n")


def test_bold_span_glued_inside_a_parenthesised_expansion() -> None:
    text = "MODLINK (**MOD**ular **LINK**age) bus is the network layer here.\n"
    assert clean_in_place(text) == (
        "MODLINK (MODular LINKage) bus is the network layer here.\n"
    )


def test_bold_span_glued_before_a_word_loses_its_markers() -> None:
    assert clean_in_place("A word with **S**tandardized wording throughout.\n") == (
        "A word with Standardized wording throughout.\n"
    )


def test_a_standalone_bold_number_label_keeps_its_markers() -> None:
    text = "Clause **787.4.** covers the anchorage of the lifting lugs.\n"
    assert clean_in_place(text) == text


def test_a_bold_phrase_between_spaces_keeps_its_markers() -> None:
    text = "An **over current detection** guards the motor windings here.\n"
    assert clean_in_place(text) == text


def test_a_bold_italic_span_is_left_alone() -> None:
    text = "The ***key*** point is stated once in the opening paragraph here.\n"
    assert clean_in_place(text) == text


def test_a_bold_volume_against_its_issue_is_left_alone() -> None:
    text = "Bull. Mach. Des., **41**2, pp. 211-219, states the same bound.\n"
    assert clean_in_place(text) == text


def test_a_bold_span_inside_inline_code_is_left_alone() -> None:
    text = "Write `a**b` in the config and the parser keeps the stars.\n"
    assert clean_in_place(text) == text


def test_bold_glue_strip_is_idempotent() -> None:
    once = clean_in_place("The **R**otary stage is described in full below.\n")
    assert clean_in_place(once) == once


# ---- space inside a roman figure or section number --------------------------


def test_a_space_in_a_roman_figure_number_is_closed() -> None:
    assert clean_in_place("See Рис. V II.11 for the main gearbox housing.\n") == (
        "See Рис. VII.11 for the main gearbox housing.\n"
    )


def test_a_subtractive_roman_number_split_by_a_space_is_closed() -> None:
    assert clean_in_place("The bound follows from формула (I X.41) above.\n") == (
        "The bound follows from формула (IX.41) above.\n"
    )


def test_two_roman_labels_side_by_side_are_left_alone() -> None:
    text = "Regions V V and I II are marked on the diagram on the next page.\n"
    assert clean_in_place(text) == text


def test_a_roman_pair_that_is_not_a_canonical_numeral_is_left_alone() -> None:
    text = "The label V V.3 appears once in the parts list on this page.\n"
    assert clean_in_place(text) == text


def test_an_author_initial_before_a_year_is_left_alone() -> None:
    text = "[4] Harlow K T. 1961 On contact pressure in bolted flanges.\n"
    assert clean_in_place(text) == text


def test_a_roman_number_split_into_three_runs_is_left_whole() -> None:
    # Half-joining `X V II.11` is worse than leaving it.
    text = "Shown in Fig. X V II.11 of the gearbox-housing chapter here.\n"
    assert clean_in_place(text) == text


def test_a_roman_split_inside_math_is_left_alone() -> None:
    text = "The moment about the axis is $x_C L.5$ in the derived form here.\n"
    assert clean_in_place(text) == text


def test_roman_join_is_idempotent() -> None:
    once = clean_in_place("Shown in рис. X I.6 and again in рис. V II.35 below.\n")
    assert clean_in_place(once) == once


# ---- space inside a multi-level entry number --------------------------------


def test_a_split_entry_number_is_closed() -> None:
    assert clean_in_place("82. 1. Requirements for fixing the lifting points.\n") == (
        "82.1. Requirements for fixing the lifting points.\n"
    )


def test_a_bold_split_entry_number_is_closed_with_its_wrapper() -> None:
    assert clean_in_place("**69. 3.** Leak test of the housing.\n") == (
        "**69.3.** Leak test of the housing.\n"
    )


def test_a_page_reference_is_left_alone() -> None:
    text = "The assembly order is given on p. 12 of this manual.\n"
    assert clean_in_place(text) == text


def test_an_inline_enumeration_is_left_alone() -> None:
    assert clean_in_place("1. 2. 3.\n") == "1. 2. 3.\n"


def test_a_wider_space_does_not_hide_the_third_run() -> None:
    assert clean_in_place("1. 2.  3. text.\n") == "1. 2.  3. text.\n"


def test_a_clause_opening_on_a_count_is_still_closed() -> None:
    assert clean_in_place("82. 1. 5 joints are to be checked.\n") == (
        "82.1. 5 joints are to be checked.\n"
    )


def test_entry_number_join_is_idempotent() -> None:
    once = clean_in_place("14. 2. General notes on mounting the supports.\n")
    assert clean_in_place(once) == once
