"""Round-trip synthesis tests: verify format generation and determinism.

Behind the ``roundtrip`` marker. Run them explicitly::

    uv run pytest -m roundtrip

Requirements: pandoc, xelatex (MiKTeX/TeX Live), DjVuLibre (c44, djvm),
img2pdf, PyMuPDF, Pillow.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from ._degrade import degrade, rasterize_pdf
from ._paths import CORPUS_DIR
from .gen_djvu import generate_djvu
from .gen_docx import generate_docx
from .gen_pdf import generate_pdf
from .gen_scan import generate_scan

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_MIN_PDF_BYTES = 10_000  # a valid multi-page PDF is never smaller than this
_MIN_DOCX_BYTES = 5_000
_MIN_DJVU_BYTES = 2_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _image_bytes(img: object) -> bytes:
    """Serialise a PIL Image to PNG bytes for comparison."""
    from PIL import Image

    assert isinstance(img, Image.Image)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


@pytest.mark.roundtrip
def test_degrade_deterministic(tmp_path: Path) -> None:
    """Same seed produces byte-identical degraded image regardless of call order."""
    from PIL import Image

    src = Image.new("RGB", (200, 300), color=(230, 230, 200))

    out_a = _image_bytes(degrade(src, seed=42))
    out_b = _image_bytes(degrade(src, seed=42))
    out_c = _image_bytes(degrade(src, seed=99))

    assert out_a == out_b, "degrade is not deterministic for the same seed"
    assert out_a != out_c, "different seeds should produce different output"


@pytest.mark.roundtrip
def test_scan_deterministic(tmp_path: Path) -> None:
    """Scan PDF generated twice with the same seed is byte-identical."""
    mixed_md = CORPUS_DIR / "mixed.md"
    pdf = generate_pdf(mixed_md, tmp_path / "src")

    scan_a = generate_scan(pdf, tmp_path / "a", degraded=True, seed=42)
    scan_b = generate_scan(pdf, tmp_path / "b", degraded=True, seed=42)

    assert scan_a.read_bytes() == scan_b.read_bytes(), (
        "scan generation is not deterministic for the same seed"
    )


# ---------------------------------------------------------------------------
# Generation smoke tests
# ---------------------------------------------------------------------------


@pytest.mark.roundtrip
def test_generate_pdf_mixed(tmp_path: Path) -> None:
    """Born-digital PDF from mixed.md is generated and has expected size."""
    pdf = generate_pdf(CORPUS_DIR / "mixed.md", tmp_path)
    assert pdf.exists()
    size = pdf.stat().st_size
    assert size >= _MIN_PDF_BYTES, f"PDF suspiciously small: {size}"


@pytest.mark.roundtrip
def test_generate_pdf_images(tmp_path: Path) -> None:
    """Born-digital PDF from images.md embeds corpus assets without error."""
    pdf = generate_pdf(CORPUS_DIR / "images.md", tmp_path)
    assert pdf.exists()
    assert pdf.stat().st_size >= _MIN_PDF_BYTES


@pytest.mark.roundtrip
def test_generate_docx_mixed(tmp_path: Path) -> None:
    """DOCX from mixed.md is generated and has expected size."""
    docx = generate_docx(CORPUS_DIR / "mixed.md", tmp_path)
    assert docx.exists()
    assert docx.stat().st_size >= _MIN_DOCX_BYTES


@pytest.mark.roundtrip
def test_generate_docx_images(tmp_path: Path) -> None:
    """DOCX from images.md embeds corpus assets without error."""
    docx = generate_docx(CORPUS_DIR / "images.md", tmp_path)
    assert docx.exists()
    assert docx.stat().st_size >= _MIN_DOCX_BYTES


@pytest.mark.roundtrip
def test_generate_djvu(tmp_path: Path) -> None:
    """DjVu bundle from mixed.pdf is generated and non-trivial."""
    pdf = generate_pdf(CORPUS_DIR / "mixed.md", tmp_path / "pdf")
    djvu = generate_djvu(pdf, tmp_path / "djvu")
    assert djvu.exists()
    assert djvu.stat().st_size >= _MIN_DJVU_BYTES


@pytest.mark.roundtrip
def test_generate_scan_clean(tmp_path: Path) -> None:
    """Clean raster scan PDF (no degradation) is generated."""
    pdf = generate_pdf(CORPUS_DIR / "mixed.md", tmp_path / "pdf")
    scan = generate_scan(pdf, tmp_path / "scan", degraded=False)
    assert scan.exists()
    assert scan.stat().st_size >= _MIN_PDF_BYTES


@pytest.mark.roundtrip
def test_generate_scan_degraded(tmp_path: Path) -> None:
    """Degraded raster scan PDF is generated and differs from clean raster."""
    pdf = generate_pdf(CORPUS_DIR / "mixed.md", tmp_path / "pdf")
    clean = generate_scan(pdf, tmp_path / "clean", degraded=False, seed=42)
    degraded = generate_scan(pdf, tmp_path / "degraded", degraded=True, seed=42)

    assert degraded.exists()
    assert degraded.stat().st_size >= _MIN_PDF_BYTES
    assert clean.read_bytes() != degraded.read_bytes()


@pytest.mark.roundtrip
def test_generate_handwriting_scan(tmp_path: Path) -> None:
    """Handwriting-font PDF is generated and degraded into a scan PDF."""
    hw_pdf = generate_pdf(
        CORPUS_DIR / "handwriting.md", tmp_path / "pdf", handwriting=True
    )
    assert hw_pdf.exists()
    assert hw_pdf.stat().st_size >= _MIN_PDF_BYTES

    hw_scan = generate_scan(
        hw_pdf, tmp_path / "scan", stem="handwriting", degraded=True, seed=42
    )
    assert hw_scan.exists()
    assert hw_scan.stat().st_size >= _MIN_PDF_BYTES


@pytest.mark.roundtrip
def test_rasterize_pdf_page_count(tmp_path: Path) -> None:
    """Rasterising the mixed PDF gives the expected number of pages."""
    pdf = generate_pdf(CORPUS_DIR / "mixed.md", tmp_path)
    pages = rasterize_pdf(pdf)
    assert len(pages) >= 1
    w, h = pages[0].size
    assert w > 500, f"Page dimensions look wrong: {w}x{h}"
    assert h > 700, f"Page dimensions look wrong: {w}x{h}"
