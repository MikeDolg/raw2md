"""Generate a DOCX from a Markdown corpus fixture via pandoc."""

from __future__ import annotations

import subprocess
from pathlib import Path


def generate_docx(
    md_path: Path,
    out_dir: Path,
    *,
    stem: str | None = None,
) -> Path:
    """Render *md_path* to a DOCX in *out_dir* via ``pandoc``.

    pandoc writes the math as OMML; image paths resolve against the markdown file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ((stem or md_path.stem) + ".docx")

    cmd = [
        "pandoc",
        str(md_path),
        "--output",
        str(out_path),
        "--resource-path",
        str(md_path.parent),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, check=False
    )  # returncode checked below
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed for {md_path.name}:\n{result.stderr}")

    return out_path
