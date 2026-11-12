"""Tests for the join of a paragraph that a page, a figure, or a caption cut.

The rule runs on LLM-OCR and on a md input, and reads the text at the cut.
"""

from __future__ import annotations

import pytest

from raw2md.cleaner import CleanOptions, clean_in_place
from raw2md.header import ConversionMethod
from raw2md.mdtext.pages import page_mark, split_page_marks

OCR = CleanOptions(method=ConversionMethod.LLM_OCR)
MD = CleanOptions(method=ConversionMethod.CLEAN)


def _ocr_pages(*pages: str) -> str:
    """A LLM-OCR body with a page mark above each page."""
    return (
        "\n\n".join(f"{page_mark(n)}\n{page}" for n, page in enumerate(pages, 1)) + "\n"
    )


def test_paragraph_cut_by_a_page_mark_joins() -> None:
    text = _ocr_pages(
        "The pump feeds the tank while the",
        "valve stays closed.\n\nThe next paragraph starts here.",
    )
    assert clean_in_place(text, OCR) == (
        f"{page_mark(1)}\n"
        "The pump feeds the tank while the valve stays closed.\n"
        "\n"
        f"{page_mark(2)}\n"
        "The next paragraph starts here.\n"
    )


def test_figure_and_caption_move_after_the_joined_paragraph() -> None:
    text = (
        "The pump feeds the tank while the\n"
        "\n"
        "![Pump](pump.png)\n"
        "\n"
        "Figure 2. The pump and the tank.\n"
        "\n"
        "valve stays closed.\n"
        "\n"
        "The next paragraph starts here.\n"
    )
    assert clean_in_place(text, MD) == (
        "The pump feeds the tank while the valve stays closed.\n"
        "\n"
        "![Pump](pump.png)\n"
        "\n"
        "Figure 2. The pump and the tank.\n"
        "\n"
        "The next paragraph starts here.\n"
    )


def test_page_that_opens_on_a_figure_keeps_its_mark_above_it() -> None:
    text = _ocr_pages(
        "The pump feeds the tank while the",
        "Figure 2. The pump.\n\nvalve stays closed.\n\nThe next paragraph.",
    )
    cleaned = clean_in_place(text, OCR)
    assert cleaned == (
        f"{page_mark(1)}\n"
        "The pump feeds the tank while the valve stays closed.\n"
        "\n"
        f"{page_mark(2)}\n"
        "Figure 2. The pump.\n"
        "\n"
        "The next paragraph.\n"
    )
    body, pages = split_page_marks(cleaned)
    assert "\n\n\n" not in body
    assert pages == ((0, 1), (2, 2))


def test_cut_join_is_idempotent() -> None:
    text = _ocr_pages(
        "The pump feeds the tank while the",
        "Figure 2. The pump.\n\nvalve stays closed and the",
        "motor stops.",
    )
    once = clean_in_place(text, OCR)
    assert "while the valve stays closed and the motor stops." in once
    assert clean_in_place(once, OCR) == once


@pytest.mark.parametrize(
    "first",
    [
        "The pump feeds the tank.",
        "Is the valve closed?",
        "The pump stops (see below).",
        'He said "stop."',
        "The tank holds:",
    ],
)
def test_finished_sentence_does_not_join(first: str) -> None:
    text = f"{first}\n\nvalve stays closed.\n"
    assert clean_in_place(text, MD) == text


def test_capital_letter_after_the_cut_does_not_join() -> None:
    text = "The pump feeds the tank while the\n\nValve stays closed.\n"
    assert clean_in_place(text, MD) == text


@pytest.mark.parametrize(
    "second",
    [
        "# valve stays closed",
        "- valve stays closed",
        "1. valve stays closed",
        "| valve | closed |\n| --- | --- |\n| a | b |",
        "$$\nx = 1\n$$",
        "b) valve stays closed",
        "k = valve constant",
        "> valve stays closed",
    ],
)
def test_structure_after_the_cut_does_not_join(second: str) -> None:
    text = f"The pump feeds the tank while the\n\n{second}\n"
    assert "while the valve" not in clean_in_place(text, MD)


@pytest.mark.parametrize(
    "first",
    ["# The pump and the", "- The pump and the", "$x + y$"],
)
def test_structure_before_the_cut_does_not_join(first: str) -> None:
    text = f"{first}\n\nvalve stays closed.\n"
    assert clean_in_place(text, MD) == text


def test_protected_zone_between_the_halves_stops_the_join() -> None:
    text = (
        "The pump feeds the tank while the\n\n```\ncode\n```\n\nvalve stays closed.\n"
    )
    assert clean_in_place(text, MD) == text


def test_inside_a_protected_zone_nothing_joins() -> None:
    text = "```\nThe pump feeds the tank while the\n\nvalve stays closed.\n```\n"
    assert clean_in_place(text, MD) == text


def test_hyphen_at_the_cut_is_left_to_the_rejoin() -> None:
    text = "The pump feeds the reser-\n\nvoir only once.\n"
    assert clean_in_place(text, MD) == text


def test_marked_body_joins_only_across_a_page_mark() -> None:
    text = _ocr_pages(
        "The pump feeds the tank while the\n\nvalve stays closed.",
        "The next page starts here.",
    )
    assert "while the valve" not in clean_in_place(text, OCR)


def test_body_without_marks_joins_at_any_paragraph_break() -> None:
    text = "The pump feeds the tank while the\n\nvalve stays closed.\n"
    assert clean_in_place(text, OCR) == (
        "The pump feeds the tank while the valve stays closed.\n"
    )


@pytest.mark.parametrize(
    "method", [ConversionMethod.PANDOC, ConversionMethod.BUNDLED, None]
)
def test_other_routes_do_not_join(method: ConversionMethod | None) -> None:
    text = "The pump feeds the tank while the\n\nvalve stays closed.\n"
    assert clean_in_place(text, CleanOptions(method=method)) == text


def test_caption_label_without_a_number_is_prose() -> None:
    # A paragraph that opens with a caption word but no number is not stepped.
    text = (
        "The pump feeds the tank while the\n"
        "\n"
        "Figures in this part are schematic.\n"
        "\n"
        "valve stays closed.\n"
    )
    assert clean_in_place(text, MD) == text


def test_caption_with_a_roman_chapter_number_is_stepped() -> None:
    text = (
        "The pump feeds the tank while the\n"
        "\n"
        "Fig. IV.2. The pump.\n"
        "\n"
        "valve stays closed.\n"
    )
    assert clean_in_place(text, MD) == (
        "The pump feeds the tank while the valve stays closed.\n"
        "\n"
        "Fig. IV.2. The pump.\n"
    )


def test_caption_is_no_first_half() -> None:
    text = "Fig. IV.2. The pump and the tank\n\nvalve stays closed.\n"
    assert clean_in_place(text, MD) == text


@pytest.mark.parametrize(
    "first",
    [
        "b iv",
        "remarque",
        "THE PUMP AND THE TANK",
        "4 - spindle\n5 - housing with the",
        "See [the manual](https://example.org/manual)",
    ],
)
def test_margin_line_legend_or_reference_is_no_first_half(first: str) -> None:
    text = f"The pump runs.\n\n{first}\n\nvalve stays closed.\n"
    assert clean_in_place(text, MD) == text


def test_running_title_after_a_roman_folio_does_not_join() -> None:
    text = "The pump feeds the tank while the\n\nxviii Contents\n"
    assert clean_in_place(text, MD) == text


def test_catchword_repeated_at_the_seam_does_not_join() -> None:
    text = "The pump feeds the tank while the valve\n\nvalve stays closed.\n"
    assert clean_in_place(text, MD) == text


def test_bold_hyphen_at_the_cut_is_left_to_the_rejoin() -> None:
    text = "The pump feeds the **reser-**\n\nvoir only once.\n"
    assert "reser-** voir" not in clean_in_place(text, MD)


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Cover design by the studio of the press", "www.example.org"),
        ("Write to the editors at editors@example.org", "ust when the season began"),
        (
            "The pump feeds the tank while the valve of the boiler",
            "feeds the tank while the valve of the boiler stays closed.",
        ),
    ],
)
def test_address_or_restated_fragment_does_not_join(first: str, second: str) -> None:
    text = f"{first}\n\n{second}\n"
    assert clean_in_place(text, MD) == text


def test_paragraph_after_a_page_cut_joins_where_its_mark_lands() -> None:
    # The join moves the page mark down to the next block, so a second pass
    # reads that break as a page cut; the first pass joins it already.
    text = _ocr_pages(
        "The pump feeds the tank while the",
        "valve stays closed and the\n\nmotor stops.\n\nThe next paragraph.",
    )
    once = clean_in_place(text, OCR)
    assert once == (
        f"{page_mark(1)}\n"
        "The pump feeds the tank while the valve stays closed and the motor stops.\n"
        "\n"
        f"{page_mark(2)}\n"
        "The next paragraph.\n"
    )
    assert clean_in_place(once, OCR) == once


def test_index_entry_and_its_subentry_do_not_join() -> None:
    text = "Pressure of the steam in the boiler 12, 48\n\nmean value 51\n"
    assert clean_in_place(text, MD) == text


def test_caption_block_with_a_heading_does_not_join_across_it() -> None:
    text = (
        "The pump feeds the tank while the\n"
        "\n"
        "Figure 2. The pump\n"
        "# Section\n"
        "\n"
        "valve stays closed.\n"
    )
    assert clean_in_place(text, MD) == text


def test_caption_after_two_joins_follows_its_page_mark() -> None:
    text = _ocr_pages(
        "The pump feeds the tank while the",
        "valve stays closed and the\n\nFigure 2. The pump\n\nreturn line runs on.",
    )
    out = clean_in_place(text, OCR)
    assert out.index(page_mark(2)) < out.index("Figure 2.")
