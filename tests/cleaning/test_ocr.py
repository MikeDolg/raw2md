"""Tests for the two families `cleaning.ocr` holds.

The LLM-OCR route extracts no media, so any image link, hyperlink, or bracketed
placeholder in its output is invented and stripped. Recognition damage is
repaired only where the body itself attests the right spelling.
"""

from __future__ import annotations

from dataclasses import replace

from raw2md.cleaner import CleanOptions, clean, clean_in_place
from raw2md.cleaning import DEFAULT_WITNESS_MIN
from raw2md.header import ConversionMethod
from raw2md.keywords import default_keywords

# ---- --engine <model>: dropping fabricated links and placeholders -------------

_OCR_OPTIONS = CleanOptions(llm_ocr=True)


def test_ocr_image_link_is_removed() -> None:
    # LLM-OCR extracts no media, so every image link is false.
    text = "before\n\n![](img_p22.png)\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nafter\n"


def test_ocr_external_image_url_is_removed() -> None:
    text = "before\n\n![image](https://i.imgur.com/gK9Q5fS.jpg)\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nafter\n"


def test_ocr_html_image_tag_is_removed() -> None:
    text = 'before\n\n<img src="img_0.png" alt="fig">\n\nafter\n'
    assert clean(text, _OCR_OPTIONS) == "before\n\nafter\n"


def test_ocr_external_hyperlink_is_unwrapped() -> None:
    # A scanned page has no hyperlinks; the visible text stays.
    text = "before\n\nSee [source](https://example.com/page).\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nSee source.\n\nafter\n"


def test_ocr_invented_placeholder_is_removed() -> None:
    text = "before\n\n[Изображение ленточного конвейера]\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nafter\n"


def test_ocr_placeholder_words_come_from_the_dictionary() -> None:
    options = CleanOptions(
        llm_ocr=True,
        keywords=replace(default_keywords(), image_placeholders=("вставк*",)),
    )
    stated = "\n".join(["before", "", "[Вставка картинки]", "", "after"]) + "\n"
    assert clean(stated, options) == "before\n\nafter\n"
    dropped = "\n".join(["before", "", "[Изображение конвейера]", "", "after"]) + "\n"
    assert clean(dropped, options) == dropped


def test_ocr_uncertainty_marker_survives() -> None:
    text = "before [unreadable] after\n"
    assert clean(text, _OCR_OPTIONS) == text


def test_ocr_unrelated_bracket_line_survives() -> None:
    text = "before\n\n[1]\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == text


def test_ocr_bracket_line_with_unrelated_ris_substring_survives() -> None:
    # Words that only contain the letters of the figure keyword are no caption.
    text = "before\n\n[Риски и юрисдикция проекта]\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == text


def test_ocr_lost_page_marker_survives() -> None:
    text = "before\n\n[page 2 not recognized]\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == text


def test_ocr_placeholder_matching_a_caption_keeps_the_text() -> None:
    # A placeholder repeating a caption of the body loses only its brackets.
    # Joined, so no `\n` escape touches a Cyrillic word (RUF001).
    caption = "Рис. 1. Ленточный конвейер."
    text = "\n".join([caption, "", f"[{caption}]"]) + "\n"
    assert clean(text, _OCR_OPTIONS) == "\n".join([caption, "", caption]) + "\n"


def test_ocr_real_caption_is_untouched() -> None:
    text = "Рис. 1. Ленточный конвейер.\n"
    assert clean(text, _OCR_OPTIONS) == text


def test_ocr_image_inside_html_table_cell_is_removed() -> None:
    text = '<table>\n<tr><td><img src="fake.png"></td><td>data</td></tr>\n</table>\n'
    assert clean(text, _OCR_OPTIONS) == (
        "<table>\n<tr><td></td><td>data</td></tr>\n</table>\n"
    )


def test_ocr_external_link_inside_html_table_cell_is_unwrapped() -> None:
    text = "<table>\n<tr><td>[source](https://example.com)</td></tr>\n</table>\n"
    assert clean(text, _OCR_OPTIONS) == (
        "<table>\n<tr><td>source</td></tr>\n</table>\n"
    )


def test_ocr_reference_style_image_is_removed() -> None:
    text = "before\n\n![fig][1]\n\n[1]: img_p1.png\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nafter\n"


def test_ocr_reference_style_external_link_is_unwrapped() -> None:
    text = "before\n\nSee [source][1] for more.\n\n[1]: https://example.com/page\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nSee source for more.\n\nafter\n"


def test_ocr_reference_style_label_matches_case_insensitively() -> None:
    # CommonMark matches reference labels regardless of case and spacing.
    text = "before\n\nSee [source][Ref] for more.\n\n[ref]: https://example.com/page\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nSee source for more.\n\nafter\n"


def test_ocr_collapsed_reference_image_is_removed() -> None:
    text = "before\n\n![fig][]\n\n[fig]: img_p1.png\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nafter\n"


def test_ocr_collapsed_reference_external_link_is_unwrapped() -> None:
    text = "before\n\nSee [Source][] for more.\n\n[source]: https://example.com/page\n\nafter\n"
    assert clean(text, _OCR_OPTIONS) == "before\n\nSee Source for more.\n\nafter\n"


def test_ocr_collapsed_reference_keeps_a_definition_still_in_use() -> None:
    text = "![fig][]\n\nSee [fig][] below.\n\n[fig]: #appendix\n"
    assert clean(text, _OCR_OPTIONS) == "See [fig][] below.\n\n[fig]: #appendix\n"


def test_ocr_reference_style_local_link_is_untouched() -> None:
    text = "See [section][1] below.\n\n[1]: #appendix\n"
    assert clean(text, _OCR_OPTIONS) == text


def test_ocr_reference_style_removal_is_idempotent() -> None:
    text = (
        "before\n\n![fig][1]\n\n[1]: img_p1.png\n\n"
        "See [source][2] too.\n\n[2]: https://example.com/page\n\nafter\n"
    )
    once = clean(text, _OCR_OPTIONS)
    assert clean(once, _OCR_OPTIONS) == once


def test_marker_route_image_links_are_not_touched() -> None:
    # The strip is gated on `llm_ocr`, not on the method.
    options = CleanOptions(method=ConversionMethod.MARKER)
    text = "before\n\n![](img_p22.png)\n\nafter\n"
    assert clean(text, options) == text


def test_ocr_fabrication_removal_is_idempotent() -> None:
    text = (
        "before\n\n![](img_p22.png)\n\n"
        "[Изображение ленточного конвейера]\n\n"
        "See [source](https://example.com/page).\n\nafter\n"
    )
    once = clean(text, _OCR_OPTIONS)
    assert clean(once, _OCR_OPTIONS) == once


# ---- the token the body attests ----------------------------------------------

# Every body prints its own witness, so a low bar keeps the bodies short.
_ATTESTED = CleanOptions(witness_min=5)


def _body(*paragraphs: str) -> str:
    """A body from `paragraphs`, one blank line apart."""
    return "\n\n".join(paragraphs) + "\n"


def _repeated(token: str, times: int) -> str:
    """`token` spelled `times` times over, the witness a body states."""
    return " ".join([token] * times)


def test_code_case_comes_from_the_capitalised_witness() -> None:
    text = _body(
        "Catalogue: " + _repeated("KX4702300", 5) + ".",
        "Item kx4702300 is listed in the inventory.",
    )
    fixed = clean_in_place(text, _ATTESTED)
    assert "kx4702300" not in fixed
    assert fixed.count("KX4702300") == 6


def test_code_case_without_a_witness_is_left_alone() -> None:
    text = _body("Item kx4702300 is listed in the inventory.")
    assert clean_in_place(text, _ATTESTED) == text


def test_code_the_body_mostly_prints_in_lower_case_is_left_alone() -> None:
    text = _body(
        "Inventory: " + _repeated("kx4702300", 6) + ".",
        "Catalogue: " + _repeated("KX4702300", 5) + ".",
    )
    assert clean_in_place(text, _ATTESTED) == text


def test_a_word_is_not_read_as_a_code() -> None:
    text = _body(
        "Heading: " + _repeated("TABLE", 5) + ".",
        "Here the table is given in full.",
    )
    assert clean_in_place(text, _ATTESTED) == text


def test_a_single_letter_label_is_not_read_as_a_code() -> None:
    text = _body(
        "Diagram: " + _repeated("X1", 5) + ".",
        "Point x1 is marked on the diagram.",
    )
    assert clean_in_place(text, _ATTESTED) == text


def test_a_word_is_repaired_into_the_spelling_the_body_attests() -> None:
    text = _body(
        "Values of " + _repeated("velocity", 5) + " are listed below.",
        "Here veloclty is misspelled.",
    )
    fixed = clean_in_place(text, _ATTESTED)
    assert "veloclty" not in fixed
    assert fixed.count("velocity") == 6


def test_a_word_below_the_witness_bar_is_left_alone() -> None:
    text = _body(
        "Values of " + _repeated("velocity", 4) + " are listed below.",
        "Here veloclty is misspelled.",
    )
    assert clean_in_place(text, _ATTESTED) == text


def test_a_word_with_two_attested_neighbours_is_left_alone() -> None:
    # An inflection has two frequent neighbours, so no repair is decidable.
    text = _body(
        "Values of " + _repeated("worker", 5) + " are listed below.",
        "Here " + _repeated("worked", 5) + " is measured.",
        "The form workes is given apart.",
    )
    assert clean_in_place(text, _ATTESTED) == text


def test_a_short_word_is_never_repaired() -> None:
    text = _body(
        "Here " + _repeated("load", 5) + " is described.",
        "Then lead is mentioned apart.",
    )
    assert clean_in_place(text, _ATTESTED) == text


def test_a_repaired_word_carries_the_case_of_its_own_occurrence() -> None:
    text = _body(
        "Values of " + _repeated("velocity", 5) + " are listed below.",
        "Veloclty is misspelled.",
    )
    assert "Velocity is misspelled" in clean_in_place(text, _ATTESTED)


def test_a_fenced_block_neither_votes_nor_is_repaired() -> None:
    text = "\n".join(
        [
            "Catalogue: " + _repeated("KX4702300", 5) + ".",
            "",
            "```",
            "kx4702300",
            "```",
            "",
        ]
    )
    assert clean_in_place(text, _ATTESTED) == text


def test_the_witness_bar_comes_from_the_options() -> None:
    text = _body(
        "Values of " + _repeated("velocity", 5) + " are listed below.",
        "Here veloclty is misspelled.",
    )
    assert "veloclty" not in clean_in_place(text, CleanOptions(witness_min=5))
    assert clean_in_place(text, CleanOptions(witness_min=6)) == text


def test_the_default_bar_is_the_rules_own() -> None:
    text = _body(
        "Values of " + _repeated("velocity", 5) + " are listed below.",
        "Here veloclty is misspelled.",
    )
    assert CleanOptions().witness_min == DEFAULT_WITNESS_MIN
    assert clean_in_place(text, CleanOptions()) == text


def test_attested_repair_is_idempotent() -> None:
    text = _body(
        "Catalogue: " + _repeated("KX4702300", 5) + ".",
        "Item kx4702300 is listed in the inventory.",
        "Values of " + _repeated("velocity", 5) + " are listed below.",
        "Here veloclty is misspelled.",
    )
    once = clean_in_place(text, _ATTESTED)
    assert clean_in_place(once, _ATTESTED) == once
