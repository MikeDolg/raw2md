"""Tests for the source outline witness: entry reading, title lookup, conflicts."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf
import pytest

from raw2md.source_outline import SourceOutline


def _make_pdf(path: Path, toc: list[list[object]], *, pages: int = 3) -> None:
    """Write a PDF of `pages` blank pages carrying `toc` as its outline."""
    doc = pymupdf.open()
    try:
        for _ in range(pages):
            doc.new_page()
        if toc:
            doc.set_toc(toc)
        doc.save(str(path))
    finally:
        doc.close()


def test_witness_reads_the_outline_of_a_pdf(tmp_path: Path) -> None:
    source = tmp_path / "book.pdf"
    _make_pdf(source, [[1, "1 Introduction", 1], [2, "1.1 Scope", 2]])

    witness = SourceOutline.from_source(source)

    assert witness.has_outline is True
    assert witness.title_count == 2
    assert witness.level_for("1 Introduction") == 1
    assert witness.level_for("1.1 Scope") == 2


def test_witness_is_empty_for_a_pdf_without_bookmarks(tmp_path: Path) -> None:
    source = tmp_path / "plain.pdf"
    _make_pdf(source, [])

    witness = SourceOutline.from_source(source)

    assert witness.has_outline is False
    assert witness.level_for("anything") is None


@pytest.mark.parametrize("name", ["memo.docx", "book.djvu", "notes.md"])
def test_witness_is_empty_for_a_source_without_an_outline_format(
    tmp_path: Path, name: str
) -> None:
    source = tmp_path / name
    source.write_bytes(b"content")

    assert SourceOutline.from_source(source).has_outline is False


def test_unreadable_pdf_yields_an_empty_witness_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.4 not really a pdf")

    with caplog.at_level(logging.WARNING, logger="raw2md"):
        witness = SourceOutline.from_source(source)

    assert witness.has_outline is False
    assert "broken.pdf" in caplog.text


def test_lookup_ignores_markup_punctuation_and_case() -> None:
    # The same title in different typography; the words must match.
    witness = SourceOutline([(2, "3.1 Load Cases")])

    assert witness.level_for("**3.1. Load cases**") == 2
    assert witness.level_for("3.1 LOAD CASES") == 2


def test_a_title_repeated_at_one_level_keeps_it() -> None:
    witness = SourceOutline([(3, "Conclusions"), (3, "Conclusions")])

    assert witness.level_for("Conclusions") == 3


def test_a_title_the_outline_places_at_two_levels_states_nothing() -> None:
    # The two occurrences are indistinguishable, so no level is stated.
    witness = SourceOutline([(1, "Appendix"), (3, "Appendix")])

    assert witness.has_outline is False
    assert witness.level_for("Appendix") is None


def test_a_title_without_a_word_is_not_indexed() -> None:
    witness = SourceOutline([(1, "***"), (1, "   ")])

    assert witness.has_outline is False


def test_an_entry_below_the_first_level_is_dropped() -> None:
    witness = SourceOutline([(0, "Broken"), (1, "Real")])

    assert witness.level_for("Broken") is None
    assert witness.level_for("Real") == 1


def test_found_titles_counts_the_outline_titles_a_body_prints() -> None:
    witness = SourceOutline([(1, "Introduction"), (2, "Scope"), (3, "Summary")])

    assert witness.found_titles(["**Introduction**", "Other", "SUMMARY"]) == 2


def test_found_titles_counts_a_repeated_title_once() -> None:
    # A rubric printed on every page prints one title of the outline, not thirty.
    witness = SourceOutline([(3, "Specifications"), (3, "Design")])

    assert witness.found_titles(["Specifications"] * 30) == 1


def test_an_empty_witness_finds_no_titles() -> None:
    assert SourceOutline.empty().found_titles(["Introduction"]) == 0


def test_an_empty_witness_states_nothing() -> None:
    witness = SourceOutline.empty()

    assert witness.has_outline is False
    assert witness.title_count == 0
    assert witness.level_for("Introduction") is None
