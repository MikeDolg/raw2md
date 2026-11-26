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


def _form_pdf(path: Path) -> Path:
    """A page-sized image inside a form that the page scales down to 10%."""
    page_content = (
        b"q 0.1 0 0 0.1 0 0 cm /Fm0 Do Q\nBT /F1 14 Tf 40 400 Td "
        b"(An invented line of the text layer above a small picture) Tj ET"
    )
    form_content = b"q 600 0 0 800 0 0 cm /Im0 Do Q"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> "
            b"/XObject << /Fm0 6 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(page_content), page_content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /XObject /Subtype /Form /BBox [0 0 600 800] "
        b"/Resources << /XObject << /Im0 7 0 R >> >> /Length %d >>\n"
        b"stream\n%s\nendstream" % (len(form_content), form_content),
        (
            b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 "
            b"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\n"
            b"stream\n\xff\nendstream"
        ),
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%s\nendobj\n" % (number, content)
    xref = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        body += b"%010d 00000 n \n" % offset
    body += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    path.write_bytes(body)
    return path


def test_scaled_down_image_in_a_form_is_not_a_scan(
    engine: Loader, tmp_path: Path
) -> None:
    path = _form_pdf(tmp_path / "form.pdf")
    assert _scan_pages(engine, path) == set()


def test_page_without_image_is_not_a_scan(engine: Loader, tmp_path: Path) -> None:
    path = _pdf(tmp_path / "plain.pdf", [])
    assert _scan_pages(engine, path) == set()
