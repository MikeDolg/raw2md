"""The provider marks a text layer page as a scan when one image covers it."""

from __future__ import annotations

import ctypes
from collections.abc import Iterator
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest
from PIL import Image

from ._helpers import Loader, engine_copy

_PAGE = (600.0, 800.0)
_TEXT = "An invented line of the text layer that sits above the picture"


@pytest.fixture
def engine() -> Iterator[Loader]:
    with engine_copy() as load:
        yield load


def _add_text(doc: pdfium.PdfDocument, page: pdfium.PdfPage) -> None:
    text_obj = pdfium_c.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", 14.0)
    buffer = (ctypes.c_ushort * (len(_TEXT) + 1))(*[ord(c) for c in _TEXT], 0)
    pdfium_c.FPDFText_SetText(text_obj, buffer)
    pdfium_c.FPDFPageObj_Transform(text_obj, 1, 0, 0, 1, 40, 400)
    pdfium_c.FPDFPage_InsertObject(page.raw, text_obj)


def _add_image(
    doc: pdfium.PdfDocument,
    page: pdfium.PdfPage,
    box: tuple[float, float, float, float],
) -> None:
    left, bottom, width, height = box
    image = pdfium.PdfImage.new(doc)
    image.set_bitmap(pdfium.PdfBitmap.from_pil(Image.new("RGB", (60, 80), "white")))
    image.set_matrix(pdfium.PdfMatrix().scale(width, height).translate(left, bottom))
    page.insert_obj(image)


def _pdf(path: Path, images: list[tuple[float, float, float, float]]) -> Path:
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(*_PAGE)
    for box in images:
        _add_image(doc, page, box)
    _add_text(doc, page)
    page.gen_content()
    doc.save(str(path))
    doc.close()
    return path


def _scan_pages(engine: Loader, path: Path) -> set[int]:
    provider = engine("marker.providers.pdf").PdfProvider(str(path))
    assert 0 in provider.page_lines
    scan_pages: set[int] = provider.scan_pages
    return scan_pages


def test_full_page_image_is_a_scan(engine: Loader, tmp_path: Path) -> None:
    path = _pdf(tmp_path / "full.pdf", [(0.0, 0.0, 600.0, 800.0)])
    assert _scan_pages(engine, path) == {0}


def test_image_at_threshold_is_a_scan(engine: Loader, tmp_path: Path) -> None:
    path = _pdf(tmp_path / "edge.pdf", [(0.0, 0.0, 600.0, 720.0)])
    assert _scan_pages(engine, path) == {0}


def test_image_below_threshold_is_not_a_scan(engine: Loader, tmp_path: Path) -> None:
    path = _pdf(tmp_path / "below.pdf", [(0.0, 0.0, 600.0, 712.0)])
    assert _scan_pages(engine, path) == set()


def test_two_half_page_images_are_not_a_scan(engine: Loader, tmp_path: Path) -> None:
    path = _pdf(
        tmp_path / "halves.pdf",
        [(0.0, 0.0, 600.0, 400.0), (0.0, 400.0, 600.0, 400.0)],
    )
    assert _scan_pages(engine, path) == set()


def test_page_without_image_is_not_a_scan(engine: Loader, tmp_path: Path) -> None:
    path = _pdf(tmp_path / "plain.pdf", [])
    assert _scan_pages(engine, path) == set()
