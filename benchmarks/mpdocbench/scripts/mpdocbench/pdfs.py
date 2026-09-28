"""Assemble the page images of each document into one PDF.

raw2md takes documents, not images, so each document folder becomes one PDF in
the page order of the annotation. The stored JPEG bytes go in unchanged: a
resample or a re-encode would hand the engine another page than the benchmark
scores against.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import img2pdf
import pikepdf

from mpdocbench.pins import BenchmarkError, Document


def assemble(pages: Sequence[Path], out_pdf: Path) -> None:
    """Write one PDF holding `pages` in the given order, without resampling.

    img2pdf reports a rejected image through several unrelated exception
    types, and a partial PDF must not reach the converter as if it were whole,
    so every failure of the writer ends here as one error.
    """
    try:
        with out_pdf.open("wb") as stream:
            img2pdf.convert(
                [str(path) for path in pages], outputstream=stream, nodate=True
            )
    except Exception as error:
        out_pdf.unlink(missing_ok=True)
        raise BenchmarkError(f"img2pdf failed on {out_pdf.name}: {error}") from error
    _make_deterministic(out_pdf)


def _make_deterministic(pdf_path: Path) -> None:
    """Rewrite the PDF so that the same pages always give the same bytes.

    img2pdf 0.6 asks pikepdf for a deterministic /ID only behind a string
    comparison of the version ("10.9.1" >= "6.2.0" is False), so with pikepdf
    10 qpdf seeds /ID from the clock. A resave keeps the inherited /ID, so it
    has to go first.
    """
    try:
        with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
            if "/ID" in pdf.trailer:
                del pdf.trailer["/ID"]
            pdf.save(pdf_path, deterministic_id=True)
    except (pikepdf.PdfError, OSError) as error:
        pdf_path.unlink(missing_ok=True)
        raise BenchmarkError(f"cannot rewrite {pdf_path.name}: {error}") from error


def build(
    documents: Sequence[Document], images: Path, out_dir: Path, missing: Sequence[str]
) -> list[str]:
    """Build one PDF per document that `fetch` found whole. Return their names.

    A PDF of a document outside `documents` is removed: raw2md converts the
    whole folder, and a stale input from another language set would be
    converted and scored with this run.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    skipped = set(missing)
    wanted = [document for document in documents if document.name not in skipped]
    names = {document.name for document in wanted}
    for stale in out_dir.glob("*.pdf"):
        if stale.stem not in names:
            stale.unlink()
    for document in wanted:
        pages = [images / document.name / page for page in document.pages]
        absent = [page.name for page in pages if not page.is_file()]
        if absent:
            raise BenchmarkError(
                f"{document.name}: pages absent on disk that fetch did not report:"
                f" {absent}; run fetch again"
            )
        assemble(pages, out_dir / f"{document.name}.pdf")
    return [document.name for document in wanted]
