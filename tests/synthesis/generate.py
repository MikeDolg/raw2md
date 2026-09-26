"""Generate all synthesis formats for all corpus fixtures into *out_dir*.

Intended for manual inspection during development::

    py -X utf8 tests/synthesis/generate.py tests/synthesis/generated

The output folder is gitignored.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._paths import CORPUS_DIR
from .gen_djvu import generate_djvu
from .gen_docx import generate_docx
from .gen_pdf import generate_pdf
from .gen_scan import generate_scan


def generate_all(out_dir: Path, *, seed: int = 42) -> dict[str, Path]:
    """Generate all synthesis formats and return a mapping of name -> path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Path] = {}

    mixed_md = CORPUS_DIR / "mixed.md"
    handwriting_md = CORPUS_DIR / "handwriting.md"
    images_md = CORPUS_DIR / "images.md"

    results["mixed.pdf"] = generate_pdf(mixed_md, out_dir)
    results["mixed.docx"] = generate_docx(mixed_md, out_dir)

    mixed_pdf = results["mixed.pdf"]
    results["mixed.djvu"] = generate_djvu(mixed_pdf, out_dir)

    results["mixed_scan.pdf"] = generate_scan(
        mixed_pdf, out_dir, degraded=False, seed=seed
    )
    results["mixed_scan_degraded.pdf"] = generate_scan(
        mixed_pdf, out_dir, degraded=True, seed=seed
    )

    hw_pdf = generate_pdf(handwriting_md, out_dir, handwriting=True)
    results["handwriting.pdf"] = hw_pdf
    results["handwriting_scan.pdf"] = generate_scan(
        hw_pdf, out_dir, stem="handwriting", degraded=True, seed=seed
    )

    results["images.pdf"] = generate_pdf(images_md, out_dir)
    results["images.docx"] = generate_docx(images_md, out_dir)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate all synthesis formats for round-trip testing."
    )
    parser.add_argument(
        "out_dir",
        nargs="?",
        default=str(Path(__file__).parent / "generated"),
        help="Output directory (default: tests/synthesis/generated/)",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for degradation"
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    print(f"Generating into {out_dir} ...")
    results = generate_all(out_dir, seed=args.seed)
    for name, path in results.items():
        size_kb = path.stat().st_size // 1024
        print(f"  {name}: {size_kb} KB")
    print("Done.")


if __name__ == "__main__":
    main()
