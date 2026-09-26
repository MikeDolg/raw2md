"""Deterministic image degradation for scan synthesis.

Rotation, JPEG compression, and blur with fixed parameters: the same seed and
input always give the same bytes.
"""

from __future__ import annotations

import io
import random
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


def degrade(
    img: PILImage,
    seed: int,
    *,
    skew_deg: float = 0.8,
    jpeg_quality: int = 75,
    blur_radius: float = 0.6,
) -> PILImage:
    """Return a degraded copy of *img*, byte-identical for the same *seed*."""
    from PIL import Image, ImageFilter

    rng = random.Random(seed)  # noqa: S311 -- seeded for deterministic, reproducible fixtures, not security
    angle = (rng.random() * 2.0 - 1.0) * skew_deg

    # Slight skew, as paper tilts on a scanner bed.
    img = img.rotate(
        angle,
        resample=Image.Resampling.BILINEAR,
        fillcolor=(255, 255, 255),
    )

    # JPEG round-trip adds blocking artifacts.
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=jpeg_quality)
    buf.seek(0)
    img = Image.open(buf)
    img.load()  # detach from BytesIO before it goes out of scope

    # Slight defocus blur of scanner optics.
    return img.filter(ImageFilter.GaussianBlur(radius=blur_radius))


def rasterize_pdf(pdf_path: str | Path, dpi: int = 150) -> list[PILImage]:
    """Render each page of *pdf_path* to an RGB PIL Image at *dpi* resolution."""
    import pymupdf
    from PIL import Image

    doc = pymupdf.open(str(pdf_path))
    pages: list[PILImage] = []
    try:
        mat = pymupdf.Matrix(dpi / 72, dpi / 72)
        for page in doc:
            pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB, alpha=False)
            img: PILImage = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(img)
    finally:
        doc.close()
    return pages
