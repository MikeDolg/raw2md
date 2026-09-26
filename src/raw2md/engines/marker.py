"""Marker conversion engine for pdf files.

marker runs as a library: the model dictionary loads once per engine and
serves the whole queue. Its LLM pass (`use_llm`) stays off. Every marker
import is lazy, so the fast test layer never loads a model.

Under `mark_pages` the output is paginated and the separators become page
marks. The marks carry page boundaries through cleaning, which rewrites and
drops lines, so a line-index map would be stale by inspection.

marker and surya print progress to stdout/stderr; a call captures it so the
progress bars stay intact. marker breaks on non-ASCII paths, so such a source
is copied into the ASCII temp folder first.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from typing import Any, TextIO

from raw2md.engines.base import (
    ConversionError,
    ConversionResult,
    ConvertOptions,
    Engine,
)
from raw2md.header import ConversionMethod
from raw2md.mdtext.pages import page_mark
from raw2md.progress import capture_engine_output

# The tail of marker's `{<page-id>}<separator>` line. The default separator
# (dashes) reads as a thematic break the body may carry itself.
_PAGE_SEPARATOR = "<!-- raw2md-page-break -->"

# marker's pagination line: its 0-based page id, then the separator above.
_PAGE_BREAK_RE = re.compile(r"^\{(\d+)\}" + re.escape(_PAGE_SEPARATOR) + r"$")


class MarkerEngine(Engine):
    """marker-based conversion engine for .pdf files.

    `temp_root` is used only for a non-ASCII source path. `cuda` False forces
    CPU. `log_stream` receives marker output; without it the output is
    discarded. `recognition_batch_size` None leaves marker's device default.
    """

    def __init__(
        self,
        temp_root: Path,
        *,
        cuda: bool = True,
        log_stream: TextIO | None = None,
        recognition_batch_size: int | None = None,
    ) -> None:
        self._temp_root = temp_root
        self._cuda = cuda
        self._log_stream = log_stream
        self._recognition_batch_size = recognition_batch_size
        self._models: dict[str, Any] | None = None

    @property
    def method(self) -> ConversionMethod:
        return ConversionMethod.MARKER

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({"pdf"})

    def available(self) -> bool:
        """True when the marker package is importable (no model load here)."""
        return find_spec("marker") is not None

    def convert(
        self, source: Path, media_dir: Path, options: ConvertOptions
    ) -> ConversionResult:
        """Convert a .pdf to Markdown via the marker library.

        Raises `ConversionError` when marker is absent or conversion fails.
        """
        if not self.available():
            raise ConversionError("marker is not installed")

        work_source, cleanup = self._prepare_ascii_input(source)
        try:
            with capture_engine_output(self._log_stream, on_phase=options.on_phase):
                models = self._load_models()
                text, images = self._run_marker(
                    work_source, models, options.extract_media, options.mark_pages
                )
            media = (
                self._save_images(images, media_dir) if options.extract_media else ()
            )
            source_pages = self._count_pages(work_source)
        except ConversionError:
            raise
        except Exception as exc:
            raise ConversionError(_failure_reason(source, exc)) from exc
        finally:
            cleanup()

        return ConversionResult(body=text, media=media, source_pages=source_pages)

    def _count_pages(self, source: Path) -> int | None:
        """Page count of the pdf fed to marker, so a djvu gets one too.

        A failed count skips the density check instead of failing a successful
        conversion.
        """
        from raw2md.engines import pymupdf

        try:
            return pymupdf.count_pages(source)
        except (RuntimeError, OSError):
            return None

    def _load_models(self) -> dict[str, Any]:
        """Load and cache the marker model dictionary (the heavy step)."""
        models = self._models
        if models is None:
            from marker.models import create_model_dict

            # device=None lets marker auto-detect the GPU; "cpu" forces CPU.
            device = None if self._cuda else "cpu"
            models = create_model_dict(device=device)
            self._models = models
        return models

    def _run_marker(
        self,
        source: Path,
        models: dict[str, Any],
        extract_media: bool,
        mark_pages: bool,
    ) -> tuple[str, dict[str, Any]]:
        """Run marker on `source`, returning (markdown, images-by-name).

        Options go through marker's `ConfigParser`, which derives the processors
        and the renderer; a raw config dict would silently ignore them.
        """
        from marker.config.parser import ConfigParser
        from marker.converters.pdf import PdfConverter
        from marker.output import text_from_rendered

        options: dict[str, Any] = {"output_format": "markdown"}
        if not extract_media:
            options["disable_image_extraction"] = True
        if mark_pages:
            options["paginate_output"] = True
            options["page_separator"] = _PAGE_SEPARATOR
        if self._recognition_batch_size is not None:
            options["recognition_batch_size"] = self._recognition_batch_size

        config_parser = ConfigParser(options)
        converter = PdfConverter(
            config=config_parser.generate_config_dict(),
            artifact_dict=models,
            processor_list=config_parser.get_processors(),
            renderer=config_parser.get_renderer(),
        )
        rendered = converter(str(source))
        text, _ext, images = text_from_rendered(rendered)
        if mark_pages:
            text = _rewrite_page_breaks(text)
        return text, images

    def _save_images(self, images: dict[str, Any], media_dir: Path) -> tuple[str, ...]:
        """Write marker's in-memory images into `media_dir`, sorted by name."""
        if not images:
            return ()
        media_dir.mkdir(parents=True, exist_ok=True)
        names: list[str] = []
        for name, image in sorted(images.items()):
            out = media_dir / name
            out.parent.mkdir(parents=True, exist_ok=True)
            image.save(out)
            names.append(out.relative_to(media_dir).as_posix())
        return tuple(names)

    def _prepare_ascii_input(self, source: Path) -> tuple[Path, Callable[[], None]]:
        """Return an ASCII path to feed marker plus a cleanup callback."""
        absolute = source.resolve()
        if str(absolute).isascii():
            return absolute, lambda: None

        self._temp_root.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="marker_", dir=self._temp_root))
        dest = work_dir / f"input{source.suffix.lower()}"
        shutil.copy2(absolute, dest)
        return dest, lambda: shutil.rmtree(work_dir, ignore_errors=True)


def _failure_reason(source: Path, exc: Exception) -> str:
    """Name the defect of the input when PyMuPDF proves it.

    marker reports an unloadable source as its own failure. The marker text is
    kept either way: a failure from elsewhere (out of device memory) must stay
    visible even when the source is also damaged.
    """
    from raw2md.engines import pymupdf

    defect = pymupdf.read_defect(source)
    if defect is None:
        return f"marker conversion failed: {source.name}: {exc}"
    return f"{source.name}: {defect}; marker: {exc}"


def _rewrite_page_breaks(text: str) -> str:
    """Turn marker's pagination separators into raw2md page marks.

    Invariant: without the mark lines, the body is the unpaginated render. A
    mark sits directly above the first line of a page, without blanks of its
    own, and only where a block starts. A page that opens mid-block waits for
    the next block; if none follows, the mark goes to the top of the last
    block, so the page stays in the map. A paragraph split by the boundary is
    rejoined. An empty page stacks its mark with the next one; trailing empty
    pages are dropped.
    """
    out: list[str] = []
    pending: list[int] = []
    drop_blank = False
    # Fallback position for a mark that never finds a later block.
    block_start: int | None = None
    pending_has_text = False
    for line in text.split("\n"):
        match = _PAGE_BREAK_RE.match(line)
        if match is not None:
            # marker numbers pages from 0; raw2md marks and logs count from 1.
            pending.append(int(match.group(1)) + 1)
            drop_blank = True
            continue
        if not line.strip():
            if drop_blank:
                # The blank after the separator; the text's own is in `out`.
                drop_blank = False
                continue
            out.append(line)
            continue
        drop_blank = False
        if pending and _splits_a_paragraph(out):
            # The blank came from pagination: rejoin the paragraph.
            out.pop()
            out[-1] += line
            pending_has_text = True
            continue
        opens_block = not out or not out[-1].strip()
        if opens_block:
            block_start = len(out)
        if pending:
            pending_has_text = True
            if opens_block:
                out.extend(page_mark(page) for page in pending)
                pending.clear()
                pending_has_text = False
        out.append(line)
    if pending and pending_has_text and block_start is not None:
        marks = [page_mark(page) for page in pending]
        out[block_start:block_start] = marks
    # Pagination prepends blanks; strip newlines only, so a first indent stays.
    return "\n".join(out).strip("\n")


def _splits_a_paragraph(out: list[str]) -> bool:
    """True when the last written line is a paragraph awaiting its continuation.

    marker ends such a line with a space and closes an ordinary paragraph
    without one. Asked only at a page boundary.
    """
    return len(out) >= 2 and not out[-1].strip() and out[-2].endswith(" ")
