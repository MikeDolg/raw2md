"""Write the two minimal documents the smoke check converts.

Not the reference corpus: that renders through xelatex, which costs the smoke
environment more than the check. The DOCX carries Cyrillic; the PDF stays Latin,
because the base-14 PDF fonts cannot hold Cyrillic.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pymupdf

_PDF_TITLE = "Smoke test document"

# Quality grades a sparse page as a thin text layer; this text is about twice the floor.
_PDF_BODY = [
    "This page carries a real text layer, so the pdf engine reads it without",
    "recognition. The smoke check asks two things of the pipeline: that a",
    "conversion runs end to end on a machine that has no GPU, and that the",
    "result it writes is graded good rather than bad.",
    "",
    "The page therefore holds more text than a single paragraph. A shorter",
    "page would be reported as a thin text layer, and the check would then",
    "fail on a conversion that in fact succeeded. Every line here is plain",
    "prose, because the point is the pipeline itself rather than any one",
    "cleaning rule; the reference corpus covers those.",
]

_DOCX_MARKDOWN = """# Installation check

The document checks that the installed tool converts a whole file: the
heading, the paragraph, and the list reach the result.

- first item
- second item
"""

_LEFT_MARGIN = 72.0
_TITLE_BASELINE = 100.0
_BODY_BASELINE = 140.0
_BODY_LEADING = 18.0


def write_pdf(path: Path) -> Path:
    """Write a one-page born-digital PDF to *path*, with the metadata cleared."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text(
            (_LEFT_MARGIN, _TITLE_BASELINE), _PDF_TITLE, fontsize=18, fontname="helv"
        )
        baseline = _BODY_BASELINE
        for line in _PDF_BODY:
            page.insert_text(
                (_LEFT_MARGIN, baseline), line, fontsize=11, fontname="helv"
            )
            baseline += _BODY_LEADING
        document.set_metadata({})
        document.save(str(path))
    return path


def write_docx(path: Path) -> Path:
    """Write a one-page DOCX to *path* through pandoc."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source = path.with_suffix(".md")
    source.write_text(_DOCX_MARKDOWN, encoding="utf-8")
    result = subprocess.run(
        ["pandoc", str(source), "--output", str(path)],
        capture_output=True,
        text=True,
        check=False,  # returncode checked below
    )
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed for {source.name}:\n{result.stderr}")
    source.unlink()
    return path


def main(argv: list[str] | None = None) -> int:
    """Write one smoke input: ``gen_smoke.py pdf|docx OUTPUT``."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] not in ("pdf", "docx"):
        print("usage: gen_smoke.py pdf|docx OUTPUT", file=sys.stderr)
        return 2
    target = Path(args[1])
    written = write_pdf(target) if args[0] == "pdf" else write_docx(target)
    print(written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
