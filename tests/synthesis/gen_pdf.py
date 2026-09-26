"""Generate a born-digital PDF from a Markdown corpus fixture via pandoc+xelatex."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ._paths import (
    FONTS_DIR,
    HANDWRITING_FONT_EXT,
    HANDWRITING_FONT_NAME,
    SOURCE_DATE_EPOCH,
)


def generate_pdf(
    md_path: Path,
    out_dir: Path,
    *,
    stem: str | None = None,
    handwriting: bool = False,
) -> Path:
    """Render *md_path* to a PDF in *out_dir* via ``pandoc --pdf-engine=xelatex``.

    ``handwriting=True`` switches to the committed Cyrillic handwriting font.
    *SOURCE_DATE_EPOCH* is fixed so the output is deterministic.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = stem or md_path.stem
    out_name += ("_handwriting" if handwriting else "") + ".pdf"
    out_path = out_dir / out_name

    # fontspec needs forward slashes even on Windows.
    if handwriting:
        font_name = f"{HANDWRITING_FONT_NAME}{HANDWRITING_FONT_EXT}"
        font_opts = f"Path={FONTS_DIR.as_posix()}/"
    else:
        font_name = "Times New Roman"
        font_opts = ""

    cmd = [
        "pandoc",
        str(md_path),
        "--output",
        str(out_path),
        "--pdf-engine=xelatex",
        "--resource-path",
        str(md_path.parent),
        "--variable",
        f"mainfont={font_name}",
    ]
    if font_opts:
        cmd += ["--variable", f"mainfontoptions={font_opts}"]

    env = {**os.environ, "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH}

    result = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        check=False,  # returncode checked below
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pandoc+xelatex failed for {md_path.name}:\n{result.stderr}"
        )

    return out_path
