"""pdfium analysis shared by the engines: pages, text layer, outline, rasters.

This module is the only boundary around `pypdfium2`; core code does not
import the library. It is not an engine: it counts pages, detects a text
layer, reads the outline and the image placements, rasterizes pages for LLM
OCR, and answers whether a PDF opens at all.

The `Path` functions read a source file. The `_bytes` functions work on a PDF
held in memory: the inspection source of a djvu never lands on disk.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pypdfium2
import pypdfium2.raw as pdfium_c

# Non-whitespace characters for a text-bearing page: a stray glyph or a page
# number must not pass a scan off as born-digital.
_TEXT_LAYER_MIN_CHARS = 16

# LLM OCR raster resolution: enough for recognition, no larger.
_RENDER_DPI = 200

# PDF user space units per inch; the render scale is dpi over this.
_UNITS_PER_INCH = 72

# Nesting limits far past any real document, so no entry or image is cut off.
_OUTLINE_MAX_DEPTH = 64
_FORM_MAX_DEPTH = 32

# pdfium reads no matrix off a shading object, so only these are visited.
_PLACED_TYPES = [pdfium_c.FPDF_PAGEOBJ_IMAGE, pdfium_c.FPDF_PAGEOBJ_FORM]

ImagePlacement = tuple[str, tuple[float, ...]]


@contextmanager
def _open(source: Path | bytes) -> Iterator[Any]:
    """Open a PDF and close it on exit: `PdfDocument` is no context manager."""
    doc = pypdfium2.PdfDocument(source)
    try:
        yield doc
    finally:
        doc.close()


def _last_error() -> int:
    """The pdfium code of the last failed load; read it right after the failure.

    pypdfium2 puts only the text of the code into `PdfiumError`.
    """
    return int(pdfium_c.FPDF_GetLastError())


def count_pages(source: Path) -> int:
    """Number of pages in `source`, the denominator for the density check."""
    with _open(source) as doc:
        return len(doc)


def needs_password(source: Path) -> bool:
    """True when `source` opens only with a password.

    A pdf that does not open for another reason answers False: a failed read
    proves nothing about a password.
    """
    try:
        with _open(source):
            return False
    except pypdfium2.PdfiumError:
        return _last_error() == int(pdfium_c.FPDF_ERR_PASSWORD)
    except OSError:
        return False


def read_defect(source: Path) -> str | None:
    """A defect of `source` this reader can state, phrased for a refusal.

    A second reader failing on the same bytes turns an engine load error into
    a statement about the input. Only a defect that leaves nothing to convert
    counts: the file does not open, or it has no page. A repaired structure
    is not a defect.
    """
    try:
        with _open(source):
            return None
    except pypdfium2.PdfiumError as exc:
        # pypdfium2 refuses a document that pdfium loads without error but
        # with no page.
        if _last_error() == pdfium_c.FPDF_ERR_SUCCESS:
            return "the pdf carries no readable page"
        return f"the pdf does not open: {exc}"
    except OSError as exc:
        return f"the pdf does not open: {exc}"


def pages_bear_text(pages: Iterable[str]) -> bool:
    """True when any page in `pages` carries enough text to count as a layer.

    Takes page texts, so the djvu text layer is judged by the same floor.
    Stops at the first text-bearing page.
    """
    return any(
        sum(1 for ch in text if not ch.isspace()) >= _TEXT_LAYER_MIN_CHARS
        for text in pages
    )


def _texts(doc: Any) -> Iterator[str]:
    for page in doc:
        textpage = page.get_textpage()
        # pdfium ends a line with \r\n; the cleaning rules expect \n.
        text = str(textpage.get_text_bounded()).replace("\r\n", "\n")
        textpage.close()
        page.close()
        yield text


def has_text_layer(source: Path) -> bool:
    """True when any page of `source` exposes an extractable text layer."""
    with _open(source) as doc:
        return pages_bear_text(_texts(doc))


def outline_entries(source: Path) -> list[tuple[int, str]]:
    """Outline (bookmark) entries of `source` as `(level, title)`, in document order.

    Levels are 1-based. Target pages are dropped: the body has no page
    alignment to use them with.
    """
    with _open(source) as doc:
        return [
            (int(item.level) + 1, str(item.title))
            for item in doc.get_toc(max_depth=_OUTLINE_MAX_DEPTH)
        ]


def image_placements_by_page(source: Path) -> list[list[ImagePlacement]]:
    """(stream hash, transform) of every image placed on each page of `source`.

    pdfium gives no object number, so a SHA-256 of the raw image stream and of
    the decoded pixels names the shared object: one object has one stream and
    one look, which survive crops that differ in bytes. The transform, taken
    to page space through any form, tells apart placements whose box matches
    but whose rotation or flip differs. An inline image is keyed too: pdfium
    does not tell it apart.
    """
    with _open(source) as doc:
        placements: list[list[ImagePlacement]] = []
        for page in doc:
            placements.append(list(_images(page, None, pypdfium2.PdfMatrix(), 0)))
            page.close()
        return placements


def _image_digest(obj: Any) -> str:
    """SHA-256 of the raw stream and of the decoded pixels.

    The stream alone misses the palette and the decode array: two
    objects can share samples and still draw different pictures.
    """
    digest = hashlib.sha256(bytes(obj.get_data()))
    bitmap = obj.get_bitmap(render=False)
    try:
        digest.update(bitmap.buffer)
    finally:
        bitmap.close()
    return digest.hexdigest()


def _images(page: Any, form: Any, outer: Any, depth: int) -> Iterator[ImagePlacement]:
    """Images on `page`, or inside `form` placed by the page-space `outer`."""
    for obj in page.get_objects(filter=_PLACED_TYPES, max_depth=1, form=form):
        matrix = obj.get_matrix().multiply(outer)
        if obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE:
            yield _image_digest(obj), tuple(float(value) for value in matrix.get())
        elif depth < _FORM_MAX_DEPTH:
            yield from _images(page, obj.raw, matrix, depth + 1)


def page_texts(source: Path) -> list[str]:
    """Text of each page of `source`, in page order; "" for a page with no text."""
    with _open(source) as doc:
        return list(_texts(doc))


def count_pages_bytes(data: bytes) -> int:
    """Number of pages in an in-memory PDF."""
    with _open(data) as doc:
        return len(doc)


def _flatten(doc: Any) -> None:
    """Bake annotation appearances into the pages of `doc`.

    `import_pages` drops the form field tree of the source, so a widget would
    show blank in a reader that needs it. A flattened page shows the same
    everywhere.
    """
    for page in doc:
        status = pdfium_c.FPDFPage_Flatten(page, pdfium_c.FLAT_NORMALDISPLAY)
        page.close()
        if status == pdfium_c.FLATTEN_FAIL:
            raise pypdfium2.PdfiumError("the pdf page cannot be flattened")


def extract_pages_bytes(data: bytes, first: int, last: int) -> bytes:
    """Return pages `first`..`last` (0-based, inclusive) of a PDF as a new PDF.

    The range is clamped to the document, so a caller may pad it past the edges.
    """
    with _open(data) as doc:
        start = max(0, first)
        end = min(len(doc) - 1, last)
        if start > end:
            raise ValueError(f"empty page range {first}..{last}")
        out = pypdfium2.PdfDocument.new()
        try:
            out.import_pages(doc, list(range(start, end + 1)))
            _flatten(out)
            buffer = io.BytesIO()
            out.save(buffer)
            return buffer.getvalue()
        finally:
            out.close()


def render_pages(
    source: Path, *, dpi: int = _RENDER_DPI
) -> Generator[bytes, None, None]:
    """Yield each page of `source` as PNG bytes for LLM OCR.

    The document stays open until the generator is exhausted. A caller that may
    stop early closes it (`contextlib.closing`): an open file on Windows blocks
    overwriting the source.
    """
    with _open(source) as doc:
        # Before any page loads: pdfium draws form fields only with a form env.
        doc.init_forms()
        for page in doc:
            # The default white fill renders RGB with no alpha channel.
            bitmap = page.render(scale=dpi / _UNITS_PER_INCH)
            buffer = io.BytesIO()
            bitmap.to_pil().save(buffer, format="PNG")
            bitmap.close()
            page.close()
            yield buffer.getvalue()
