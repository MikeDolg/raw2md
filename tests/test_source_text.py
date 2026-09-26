"""Tests for the source text witness: page text, token lookup, empty fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from raw2md.engines import ConversionError
from raw2md.source_text import SourceText


def _make_pdf(path: Path, pages: list[str | None]) -> None:
    """Write a PDF whose i-th page carries `pages[i]`, or nothing for None."""
    doc = pymupdf.open()
    try:
        for text in pages:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        doc.save(str(path))
    finally:
        doc.close()


def test_witness_exposes_page_text_in_order(tmp_path: Path) -> None:
    source = tmp_path / "book.pdf"
    _make_pdf(source, ["First page body text.", "Second page body text."])

    witness = SourceText.from_source(source)

    assert witness.has_layer is True
    assert witness.page_count == 2
    assert "First page" in witness.pages[0]
    assert "Second page" in witness.pages[1]


def test_witness_is_empty_for_a_scan(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    _make_pdf(source, [None, None])

    witness = SourceText.from_source(source)

    assert witness.has_layer is False
    assert witness.page_count == 0
    assert witness.has_token("anything") is False


def test_witness_is_empty_when_the_layer_is_too_thin_to_attest(tmp_path: Path) -> None:
    # Below the per-page floor a stray glyph on a scan would attest a form.
    source = tmp_path / "sparse.pdf"
    _make_pdf(source, ["12"])

    assert SourceText.from_source(source).has_layer is False


@pytest.mark.parametrize("name", ["memo.docx", "notes.md"])
def test_witness_is_empty_for_a_source_without_a_page_layer(
    tmp_path: Path, name: str
) -> None:
    source = tmp_path / name
    source.write_bytes(b"content")

    assert SourceText.from_source(source).has_layer is False


def test_witness_reads_the_text_layer_of_a_djvu(tmp_path: Path) -> None:
    # A scanned book often carries its scanner's recognition under the pages.
    source = tmp_path / "scan.djvu"
    source.write_bytes(b"djvu")

    with patch(
        "raw2md.engines.djvu.page_texts",
        return_value=["", "См. коэффициент трения на этой странице."],
    ):
        witness = SourceText.from_source(source)

    assert witness.has_layer is True
    assert witness.page_count == 2
    assert witness.has_token("коэффициент") is True
    # A text-less page keeps its place in the sequence.
    assert witness.has_token("коэффициент", page=0) is False
    assert witness.has_token("коэффициент", page=1) is True


@pytest.mark.parametrize("pages", [["", "", ""], ["12"]])
def test_witness_is_empty_for_a_djvu_with_nothing_to_attest(
    tmp_path: Path, pages: list[str]
) -> None:
    # No text layer, and one below the pdf per-page floor: neither confirms.
    source = tmp_path / "scan.djvu"
    source.write_bytes(b"djvu")

    with patch("raw2md.engines.djvu.page_texts", return_value=pages):
        witness = SourceText.from_source(source)

    assert witness.has_layer is False


def test_unreadable_djvu_yields_an_empty_witness_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # djvutxt missing from PATH costs the witness, never the conversion.
    source = tmp_path / "scan.djvu"
    source.write_bytes(b"djvu")

    with (
        patch(
            "raw2md.engines.djvu.page_texts",
            side_effect=ConversionError("djvutxt not found or could not be launched"),
        ),
        caplog.at_level(logging.WARNING, logger="raw2md"),
    ):
        witness = SourceText.from_source(source)

    assert witness.has_layer is False
    assert "scan.djvu" in caplog.text


def test_unreadable_pdf_yields_an_empty_witness_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.4 not really a pdf")

    with caplog.at_level(logging.WARNING, logger="raw2md"):
        witness = SourceText.from_source(source)

    assert witness.has_layer is False
    assert "broken.pdf" in caplog.text


def test_token_lookup_spans_the_document_and_narrows_to_a_page(
    tmp_path: Path,
) -> None:
    source = tmp_path / "book.pdf"
    _make_pdf(source, ["alpha beta and more text", "gamma delta and more text"])

    witness = SourceText.from_source(source)

    assert witness.has_token("gamma") is True
    assert witness.has_token("gamma", page=1) is True
    assert witness.has_token("gamma", page=0) is False
    # A page number the source does not have is answered, not raised.
    assert witness.has_token("gamma", page=7) is False


def test_token_lookup_ignores_case_and_typographic_forms() -> None:
    # A soft hyphen and an `ffi` ligature, as a PDF text layer carries them;
    # joined, since an escape next to Cyrillic trips RUF001.
    hyphenated = "\u00ad".join(["Коэффи", "циент"])

    witness = SourceText([hyphenated, "The o\ufb03ce"])

    assert witness.has_token("КОЭФФИЦИЕНТ") is True
    assert witness.has_token("office") is True


def test_a_hyphenated_break_attests_the_halves_not_the_joined_form() -> None:
    witness = SourceText(["\n".join(["коэффи-", "циент"])])

    assert witness.has_token("коэффи") is True
    assert witness.has_token("циент") is True
    assert witness.has_token("коэффициент") is False


@pytest.mark.parametrize("query", ["", "   ", "...", "two words"])
def test_a_query_that_is_not_one_token_is_not_attested(query: str) -> None:
    witness = SourceText(["two words here"])

    assert witness.has_token(query) is False


def test_an_empty_witness_attests_nothing() -> None:
    # With no text layer a rule that needs confirmation does not fire.
    witness = SourceText.empty()

    assert witness.has_layer is False
    assert witness.pages == ()
    assert witness.has_token("word") is False
    assert witness.has_token("word", page=0) is False
