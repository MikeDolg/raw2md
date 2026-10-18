"""Small PDFs for the tests: text pages, placed images, an outline, a password.

The PDFs are written with `fpdf2`, so a test builds its input without the
library that reads it. A page holds optional text (core font, Latin-1 only)
and one optional image. The same image bytes on several pages share one PDF
object, as a reused picture does.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import EncryptionMethod

Rect = tuple[float, float, float, float]

LOGO_RECT: Rect = (10, 10, 60, 40)

# The same image bigger and moved: a logo blown up on the cover page.
COVER_RECT: Rect = (10, 10, 160, 90)

_TEXT_ORIGIN = 72.0
_TEXT_LEADING = 14.0
_FONT_SIZE = 11


@dataclass(frozen=True)
class Page:
    """One page: its text lines, and an image with the box and turn it is drawn in."""

    text: str | None = None
    image: bytes | None = None
    rect: Rect = LOGO_RECT
    rotate: int = 0


def blank_pages(count: int) -> list[Page]:
    """`count` pages with no content."""
    return [Page() for _ in range(count)]


def text_pages(texts: Sequence[str | None]) -> list[Page]:
    """One page per entry, carrying the text, or nothing for `None`."""
    return [Page(text=text) for text in texts]


def image_pages(
    images: Sequence[bytes | None],
    *,
    rects: Sequence[Rect] | None = None,
    rotates: Sequence[int] | None = None,
) -> list[Page]:
    """One page per entry, drawing the PNG if given.

    `rects` and `rotates` place the image of each page on its own.
    """
    return [
        Page(
            image=image,
            rect=rects[index] if rects is not None else LOGO_RECT,
            rotate=rotates[index] if rotates is not None else 0,
        )
        for index, image in enumerate(images)
    ]


def pdf_bytes(
    pages: Sequence[Page],
    *,
    outline: Sequence[tuple[int, str, int]] = (),
    password: str | None = None,
) -> bytes:
    """A PDF with `pages`; `outline` lists `(level, title, page)`, 1-based.

    The outline entries must follow the page order. A `password` encrypts the
    file with AES-256 and asks for it on opening.
    """
    pdf = FPDF(unit="pt", format="A4")
    pdf.set_font("Helvetica", size=_FONT_SIZE)
    pending = list(outline)
    for number, page in enumerate(pages, start=1):
        pdf.add_page()
        while pending and pending[0][2] == number:
            level, title, _ = pending.pop(0)
            pdf.start_section(title, level - 1)
        _draw(pdf, page)
    if pending:
        raise ValueError(
            f"outline entries out of page order or past the end: {pending}"
        )
    if password is not None:
        pdf.set_encryption(
            owner_password=password,
            user_password=password,
            encryption_method=EncryptionMethod.AES_256,
        )
    return bytes(pdf.output())


def write_pdf(
    path: Path,
    pages: Sequence[Page],
    *,
    outline: Sequence[tuple[int, str, int]] = (),
    password: str | None = None,
) -> None:
    """Write `pdf_bytes(pages, ...)` to `path`."""
    path.write_bytes(pdf_bytes(pages, outline=outline, password=password))


def _draw(pdf: FPDF, page: Page) -> None:
    if page.text:
        for line, text in enumerate(page.text.split("\n")):
            pdf.text(_TEXT_ORIGIN, _TEXT_ORIGIN + line * _TEXT_LEADING, text)
    if page.image is None:
        return
    x0, y0, x1, y1 = page.rect
    with pdf.rotation(page.rotate, (x0 + x1) / 2, (y0 + y1) / 2):
        pdf.image(io.BytesIO(page.image), x=x0, y=y0, w=x1 - x0, h=y1 - y0)
