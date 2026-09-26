"""DjVu conversion engine.

The chain: ddjvu renders one TIFF per page, img2pdf assembles a PDF, and
marker converts it. Direct DjVu-to-PDF needs a text layer, which is rare.
ddjvu and img2pdf are optional dependencies.

djvutxt reads the text layer for the source witness; it is not part of the
conversion chain.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from contextlib import ExitStack
from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path

from raw2md.engines.base import (
    ConversionError,
    ConversionResult,
    ConvertOptions,
    Engine,
    condense_process_output,
)
from raw2md.engines.marker import MarkerEngine
from raw2md.header import ConversionMethod

_logger = logging.getLogger("raw2md")

# A hung ddjvu would block the batch; 5 minutes covers one page group.
_DDJVU_TIMEOUT_S: int = 300

# djvused only walks the document directory.
_DJVUSED_TIMEOUT_S: int = 60

# djvutxt decodes no image and answers a whole book in under a second.
_DJVUTXT_TIMEOUT_S: int = 60

# djvutxt closes the text of every page it prints with a form feed.
_PAGE_SEPARATOR: str = "\f"

# Groups bound the ddjvu timeout per call: a large scan may not decode within
# one window.
_PAGES_PER_GROUP: int = 16

# One TIFF per page: a multi-page TIFF of a book can exceed the 4 GB cap of the
# classic container. Names carry the page number, so groups stay in sequence.
_PAGE_TIFF_TEMPLATE: str = "page%04d.tiff"
_PAGE_TIFF_GLOB: str = "page*.tiff"
_PAGE_NUMBER_RE = re.compile(r"\d+")

# Fixed, so a non-ASCII source still yields an ASCII path.
_ASSEMBLED_PDF_NAME: str = "assembled.pdf"


def djvu_to_pdf(source: Path, dest_pdf: Path, temp_root: Path) -> None:
    """Convert a .djvu to a PDF at `dest_pdf` via ddjvu -> img2pdf.

    The TIFFs live in a temp dir under `temp_root`; a non-ASCII source is
    copied there. A staging `OSError` becomes `ConversionError`, a per-file
    failure rather than a batch abort.
    """
    try:
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="raw2md_djvu_", dir=temp_root
        ) as tmp_str:
            tmp = Path(tmp_str)
            resolved = source.resolve()
            if str(resolved).isascii():
                work_source = resolved
            else:
                work_source = tmp / f"input{source.suffix.lower()}"
                shutil.copy2(resolved, work_source)
            pages_dir = tmp / "pages"
            pages_dir.mkdir()
            _assemble_pdf(_ddjvu_to_tiffs(work_source, pages_dir), dest_pdf)
    except OSError as exc:
        raise ConversionError(
            f"could not stage djvu source {source.name}: {exc}"
        ) from exc


def djvu_to_pdf_bytes(source: Path, temp_root: Path) -> bytes:
    """Convert a .djvu to PDF and return its bytes."""
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="raw2md_djvu_", dir=temp_root) as tmp_str:
        dest = Path(tmp_str) / "source.pdf"
        djvu_to_pdf(source, dest, temp_root)
        return dest.read_bytes()


def page_texts(source: Path) -> list[str]:
    """Text layer of each page of `source`, in page order, via djvutxt.

    A page with no text yields "", so the list aligns with the pages. djvutxt
    separates only pages that have text, so the one-call dump is used only when
    it is unambiguous (no text, or one chunk per page); a partial layer is
    re-read page by page. Raises `ConversionError` when the pages cannot be
    counted or djvutxt fails; a missing layer is not an error.
    """
    total = page_count(source)
    if total is None:
        raise ConversionError(f"could not count pages of {source.name}")
    chunks = _split_page_texts(_djvutxt(source, None))
    if not chunks:
        return [""] * total
    if len(chunks) == total:
        return chunks
    return [_page_text(source, number) for number in range(1, total + 1)]


def _page_text(source: Path, page: int) -> str:
    """Text of one page, without the separator djvutxt closes it with."""
    return "".join(_split_page_texts(_djvutxt(source, page)))


def _split_page_texts(dump: str) -> list[str]:
    """Split a djvutxt dump into page texts on its form-feed separator.

    The separator closes a page, so the trailing empty piece is dropped.
    """
    chunks = dump.split(_PAGE_SEPARATOR)
    if chunks and not chunks[-1]:
        chunks.pop()
    return chunks


def _djvutxt(source: Path, page: int | None) -> str:
    """Run djvutxt over one page of `source`, or the whole document when None."""
    command = ["djvutxt"]
    if page is not None:
        command.append(f"-page={page}")
    command.append(str(source))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=_DJVUTXT_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"djvutxt timed out after {_DJVUTXT_TIMEOUT_S}s") from exc
    except OSError as exc:
        raise ConversionError(
            f"djvutxt not found or could not be launched: {exc}"
        ) from exc
    if result.returncode != 0:
        stderr = condense_process_output(result.stderr.decode(errors="replace").strip())
        raise ConversionError(f"djvutxt failed (code {result.returncode}): {stderr}")
    return result.stdout.decode("utf-8", errors="replace")


def _ddjvu_to_tiffs(source: Path, out_dir: Path) -> list[Path]:
    """Export every DjVu page to its own TIFF in `out_dir`, in page order.

    Without a page count the document renders in one call under one timeout.
    """
    total = page_count(source)
    if total is None:
        _render_pages(source, out_dir, None)
    else:
        for first in range(1, total + 1, _PAGES_PER_GROUP):
            _render_pages(
                source, out_dir, (first, min(first + _PAGES_PER_GROUP - 1, total))
            )
    pages = sorted(out_dir.glob(_PAGE_TIFF_GLOB), key=_page_number)
    if not pages:
        raise ConversionError(f"ddjvu rendered no pages of {source.name}")
    return pages


def _page_number(tiff_path: Path) -> int:
    """Page number in a TIFF name; sorting by name breaks past the zero padding."""
    match = _PAGE_NUMBER_RE.search(tiff_path.stem)
    return int(match.group()) if match is not None else 0


def page_count(source: Path) -> int | None:
    """Number of pages in the DjVu per djvused, or None when it cannot be read.

    djvused is optional: without it the route renders in one call.
    """
    try:
        result = subprocess.run(
            ["djvused", "-e", "n", str(source)],
            capture_output=True,
            check=False,
            timeout=_DJVUSED_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _logger.warning("djvused could not count pages of %s: %s", source.name, exc)
        return None
    if result.returncode != 0:
        stderr = condense_process_output(result.stderr.decode(errors="replace").strip())
        _logger.warning(
            "djvused failed (code %s) on %s: %s", result.returncode, source.name, stderr
        )
        return None
    lines = [
        line.strip()
        for line in result.stdout.decode(errors="replace").splitlines()
        if line.strip()
    ]
    if not lines or not lines[-1].isdigit() or int(lines[-1]) < 1:
        _logger.warning("djvused reported no page count for %s", source.name)
        return None
    return int(lines[-1])


def _render_pages(source: Path, out_dir: Path, pages: tuple[int, int] | None) -> None:
    """Render `pages` (all of them when None) into per-page TIFFs via ddjvu."""
    command = ["ddjvu", "-format=tiff", "-eachpage"]
    if pages is not None:
        command.append(f"-page={pages[0]}-{pages[1]}")
    command += [str(source), str(out_dir / _PAGE_TIFF_TEMPLATE)]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=_DDJVU_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"ddjvu timed out after {_DDJVU_TIMEOUT_S}s") from exc
    except OSError as exc:
        raise ConversionError(
            f"ddjvu not found or could not be launched: {exc}"
        ) from exc
    if result.returncode != 0:
        stderr = condense_process_output(result.stderr.decode(errors="replace").strip())
        raise ConversionError(f"ddjvu failed (code {result.returncode}): {stderr}")


def _assemble_pdf(tiff_paths: list[Path], output: Path) -> None:
    """Assemble per-page TIFFs into a PDF via img2pdf, streamed to disk.

    A scan large enough to need per-page rendering is a memory problem too.
    """
    try:
        import img2pdf

        with output.open("wb") as stream:
            img2pdf.convert([str(path) for path in tiff_paths], outputstream=stream)
    except Exception as exc:
        # A partial PDF must not be handed to marker as if it were complete.
        output.unlink(missing_ok=True)
        raise ConversionError(f"img2pdf assembly failed: {exc}") from exc


class DjvuEngine(Engine):
    """DjVu conversion via ddjvu -> img2pdf -> marker.

    `marker_engine` is shared with the queue, so its model loads once.
    `temp_root` holds the intermediate TIFFs and PDF.
    """

    def __init__(self, marker_engine: MarkerEngine, temp_root: Path) -> None:
        self._marker = marker_engine
        self._temp_root = temp_root

    @property
    def method(self) -> ConversionMethod:
        return ConversionMethod.DJVU_MARKER

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({"djvu"})

    def available(self) -> bool:
        """True when ddjvu, img2pdf, and marker are all present."""
        return (
            shutil.which("ddjvu") is not None
            and find_spec("img2pdf") is not None
            and self._marker.available()
        )

    def convert(
        self, source: Path, media_dir: Path, options: ConvertOptions
    ) -> ConversionResult:
        """Convert a .djvu to Markdown via ddjvu -> img2pdf -> marker.

        With `scratch_dir` the assembled PDF stays there and is named on the
        result, so inspection does not assemble the book twice. Without it the
        PDF lives in a temp dir removed on exit.
        """
        with ExitStack() as stack:
            if options.scratch_dir is not None:
                pdf_dir = options.scratch_dir
            else:
                self._temp_root.mkdir(parents=True, exist_ok=True)
                pdf_dir = Path(
                    stack.enter_context(
                        tempfile.TemporaryDirectory(
                            prefix="raw2md_djvu_", dir=self._temp_root
                        )
                    )
                )
            pdf_path = pdf_dir / _ASSEMBLED_PDF_NAME
            djvu_to_pdf(source, pdf_path, self._temp_root)
            result = self._marker.convert(pdf_path, media_dir, options)
            if options.scratch_dir is not None:
                result = replace(result, source_pdf=pdf_path)
        return result
