"""Generate a DjVu from a born-digital PDF: rasterise, c44 per page, djvm."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from ._degrade import rasterize_pdf
from ._paths import RASTER_DPI


def generate_djvu(
    pdf_path: Path,
    out_dir: Path,
    *,
    stem: str | None = None,
    dpi: int = RASTER_DPI,
) -> Path:
    """Rasterise *pdf_path* into a multi-page DjVu in *out_dir*; needs DjVuLibre."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ((stem or pdf_path.stem) + ".djvu")

    pages = rasterize_pdf(pdf_path, dpi=dpi)

    with tempfile.TemporaryDirectory(prefix="raw2md_djvu_") as tmp:
        tmp_dir = Path(tmp)
        page_djvus: list[Path] = []

        for idx, page_img in enumerate(pages):
            ppm_path = tmp_dir / f"page{idx:04d}.ppm"
            djvu_path = tmp_dir / f"page{idx:04d}.djvu"

            # c44 accepts PPM for colour pages.
            page_img.convert("RGB").save(str(ppm_path))

            result = subprocess.run(
                ["c44", str(ppm_path), str(djvu_path)],
                capture_output=True,
                text=True,
                check=False,  # returncode checked below
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"c44 failed on page {idx} of {pdf_path.name}:\n{result.stderr}"
                )
            page_djvus.append(djvu_path)

        result = subprocess.run(
            ["djvm", "-c", str(out_path), *[str(p) for p in page_djvus]],
            capture_output=True,
            text=True,
            check=False,  # returncode checked below
        )
        if result.returncode != 0:
            raise RuntimeError(f"djvm failed for {pdf_path.name}:\n{result.stderr}")

    return out_path
