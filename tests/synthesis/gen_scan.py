"""Generate scan-like PDFs from a born-digital PDF via rasterisation + img2pdf.

A clean and a degraded raster tell a layout defect from a recognition defect.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

import pikepdf

from ._degrade import degrade, rasterize_pdf
from ._paths import RASTER_DPI


def _rewrite_deterministic(pdf_path: Path) -> None:
    """Rewrite *pdf_path* so identical pages always yield identical bytes.

    img2pdf 0.6.3 compares the pikepdf version as a string, so with pikepdf 10 it
    never asks for a deterministic /ID and qpdf seeds it from the clock. A resave
    carries the input's /ID over, so it has to be replaced as well.
    """
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        if "/ID" in pdf.trailer:
            del pdf.trailer["/ID"]
        pdf.save(pdf_path, deterministic_id=True, linearize=True)


def _pages_to_pdf_via_files(pages_png: list[bytes], out_path: Path) -> None:
    """Write pages to temp PNG files then assemble with img2pdf."""
    with tempfile.TemporaryDirectory(prefix="raw2md_scan_") as tmp:
        tmp_dir = Path(tmp)
        png_paths: list[str] = []
        for idx, data in enumerate(pages_png):
            p = tmp_dir / f"page{idx:04d}.png"
            p.write_bytes(data)
            png_paths.append(str(p))
        # --nodate: a creation timestamp would defeat the deterministic rewrite.
        result = subprocess.run(
            ["img2pdf", "--nodate", "-o", str(out_path), *png_paths],
            capture_output=True,
            text=True,
            check=False,  # returncode checked below
        )
        if result.returncode != 0:
            raise RuntimeError(f"img2pdf failed:\n{result.stderr}")
    _rewrite_deterministic(out_path)


def generate_scan(
    pdf_path: Path,
    out_dir: Path,
    *,
    stem: str | None = None,
    degraded: bool = False,
    seed: int = 42,
    dpi: int = RASTER_DPI,
) -> Path:
    """Rasterise *pdf_path* into a scan-like PDF, degraded by *seed* if asked."""
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_scan_degraded" if degraded else "_scan"
    out_path = out_dir / ((stem or pdf_path.stem) + suffix + ".pdf")

    pages = rasterize_pdf(pdf_path, dpi=dpi)

    png_buffers: list[bytes] = []
    for idx, img in enumerate(pages):
        frame = degrade(img, seed=seed + idx) if degraded else img
        buf = io.BytesIO()
        frame.convert("RGB").save(buf, format="PNG")
        png_buffers.append(buf.getvalue())

    _pages_to_pdf_via_files(png_buffers, out_path)
    return out_path
