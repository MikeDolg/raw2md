"""PyMuPDF analysis shared by the engines: pages, text layer, outline, rasters.

This module is the only boundary around PyMuPDF; core code does not import
the library. It is not an engine: it counts pages, detects a text layer,
reads the outline and the image xrefs, rasterizes pages for LLM OCR, and
answers whether a PDF opens at all.

The `Path` functions read a source file. The `_bytes` functions work on a PDF
held in memory: the inspection source of a djvu never lands on disk.
"""

from __future__ import annotations

from collections.abc import Generator, Iterable
from pathlib import Path

# Absolute import: this names the installed library, not this same-named module.
import pymupdf

# Non-whitespace characters for a text-bearing page: a stray glyph or a page
# number must not pass a scan off as born-digital.
_TEXT_LAYER_MIN_CHARS = 16

# LLM OCR raster resolution: enough for recognition, no larger.
_RENDER_DPI = 200


def count_pages(source: Path) -> int:
    """Number of pages in `source`, the denominator for the density check."""
    with pymupdf.open(source) as doc:
        return int(doc.page_count)


def needs_password(source: Path) -> bool:
    """True when `source` opens only with a password.

    A pdf that does not open at all answers False: a failed read proves
    nothing about a password.
    """
    try:
        with pymupdf.open(source) as doc:
            return bool(doc.needs_pass)
    except (RuntimeError, OSError):
        return False


def read_defect(source: Path) -> str | None:
    """A defect of `source` this reader can state, phrased for a refusal.

    A second reader failing on the same bytes turns an engine load error into
    a statement about the input. Only a defect that leaves nothing to convert
    counts: the file does not open, or it has no page. A repaired structure
    is not a defect.
    """
    try:
        with pymupdf.open(source) as doc:
            pages = int(doc.page_count)
    except (RuntimeError, OSError) as exc:
        return f"the pdf does not open: {exc}"
    if pages == 0:
        return "the pdf carries no readable page"
    return None


def pages_bear_text(pages: Iterable[str]) -> bool:
    """True when any page in `pages` carries enough text to count as a layer.

    Takes page texts, so the djvu text layer is judged by the same floor.
    Stops at the first text-bearing page.
    """
    return any(
        sum(1 for ch in text if not ch.isspace()) >= _TEXT_LAYER_MIN_CHARS
        for text in pages
    )


def has_text_layer(source: Path) -> bool:
    """True when any page of `source` exposes an extractable text layer."""
    with pymupdf.open(source) as doc:
        return pages_bear_text(str(page.get_text("text")) for page in doc)


def outline_entries(source: Path) -> list[tuple[int, str]]:
    """Outline (bookmark) entries of `source` as `(level, title)`, in document order.

    Levels are 1-based. Target pages are dropped: the body has no page
    alignment to use them with.
    """
    with pymupdf.open(source) as doc:
        toc = doc.get_toc(simple=True)
    return [(int(level), str(title)) for level, title, *_ in toc]


def image_placements_by_page(
    source: Path,
) -> list[list[tuple[int, tuple[float, float, float, float, float, float]]]]:
    """(xref, transform) of every image placed on each page of `source`.

    The xref names the shared PDF object, which survives crops that differ in
    bytes. The transform tells apart placements whose bounding box matches but
    whose rotation or flip differs. An inline image (xref 0) has no identity
    and is dropped.
    """
    with pymupdf.open(source) as doc:
        return [
            [
                (int(info["xref"]), tuple(info["transform"]))
                for info in page.get_image_info(xrefs=True)
                if info["xref"]
            ]
            for page in doc
        ]


def page_texts(source: Path) -> list[str]:
    """Text of each page of `source`, in page order; "" for a page with no text."""
    with pymupdf.open(source) as doc:
        return [str(page.get_text("text")) for page in doc]


def count_pages_bytes(data: bytes) -> int:
    """Number of pages in an in-memory PDF."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return int(doc.page_count)


def extract_pages_bytes(data: bytes, first: int, last: int) -> bytes:
    """Return pages `first`..`last` (0-based, inclusive) of a PDF as a new PDF.

    The range is clamped to the document, so a caller may pad it past the edges.
    """
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        start = max(0, first)
        end = min(int(doc.page_count) - 1, last)
        if start > end:
            raise ValueError(f"empty page range {first}..{last}")
        with pymupdf.open() as out:
            out.insert_pdf(doc, from_page=start, to_page=end)
            return bytes(out.tobytes())


def render_pages(
    source: Path, *, dpi: int = _RENDER_DPI
) -> Generator[bytes, None, None]:
    """Yield each page of `source` as PNG bytes for LLM OCR.

    The document stays open until the generator is exhausted. A caller that may
    stop early closes it (`contextlib.closing`): an open file on Windows blocks
    overwriting the source.
    """
    with pymupdf.open(source) as doc:
        for page in doc:
            yield bytes(page.get_pixmap(dpi=dpi).tobytes("png"))
