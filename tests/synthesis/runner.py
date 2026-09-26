"""Full round-trip runner with timing and VRAM reporting.

Runs the corpus fixture x format matrix and prints a defect-summary table. It
needs the ``roundtrip`` toolchain; a row whose tool is missing is skipped.

Usage::

    py -X utf8 -m tests.synthesis.runner
    py -X utf8 -m tests.synthesis.runner --formats pdf docx
    py -X utf8 -m tests.synthesis.runner --fixtures mixed --out report.md
    py -X utf8 -m tests.synthesis.runner --work-dir D:/tmp/rtrip
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ._paths import CORPUS_DIR, FONTS_DIR, HANDWRITING_FONT_EXT, HANDWRITING_FONT_NAME
from ._structure import StructureCounts, StructureDiff, compare_structure
from .roundtrip import FORMATS, run_roundtrip

_FORMAT_FIXTURES: dict[str, tuple[str, ...]] = {
    "pdf": (
        "mixed",
        "headers",
        "tables",
        "formulas",
        "images",
        "nested_lists",
        "multilang",
        "long_doc",
    ),
    "docx": (
        "mixed",
        "headers",
        "tables",
        "images",
        "formulas",
        "nested_lists",
        "footnotes",
        "multilang",
        "long_doc",
        "engineering_prose",
        "math_legend",
    ),
    "djvu": ("mixed",),
    "scan": ("mixed",),
    "scan_degraded": ("mixed",),
    "handwriting_scan": ("handwriting",),
}


def _structural_diffs(
    fmt: str, ref: StructureCounts, out: StructureCounts
) -> list[StructureDiff] | None:
    """Return diffs for formats where structural comparison is meaningful.

    Born-digital PDF skips the per-level heading check and splits the formula
    tolerance. Scan formats are left out: marker re-levels headings on a raster.
    """
    if fmt == "docx":
        return compare_structure(
            ref, out, display_formula_tolerance=1, inline_formula_tolerance=1
        )
    if fmt == "pdf":
        diffs = compare_structure(
            ref,
            out,
            check_headings=False,
            table_tolerance=1,
            image_tolerance=1,
            display_formula_tolerance=0,
            inline_formula_tolerance=4,
        )
        # marker re-levels headings; the total must hold within 2.
        if abs(ref.headings_total - out.headings_total) > 2:
            diffs.append(
                StructureDiff("headings_total", ref.headings_total, out.headings_total)
            )
        return diffs
    if fmt == "djvu":
        formula_tol = max(ref.display_formulas, ref.inline_formulas)
        return compare_structure(
            ref,
            out,
            heading_tolerance=3,
            table_tolerance=1,
            display_formula_tolerance=formula_tol,
            inline_formula_tolerance=formula_tol,
            image_tolerance=ref.images,
        )
    return None  # scan / scan_degraded / handwriting_scan


@dataclass
class RunRecord:
    """Outcome of one round-trip run in the full runner."""

    fixture: str
    fmt: str
    skipped: bool = False
    skip_reason: str | None = None
    elapsed_s: float | None = None
    peak_vram_mb: float | None = None
    exit_code: int | None = None
    status: str | None = None
    recognition_failure: bool | None = None
    repairable: bool | None = None
    struct_diffs: list[str] = field(default_factory=list)
    error: str | None = None


def _check_tools(fmt: str) -> str | None:
    """Return a human-readable skip reason when a required tool is absent."""
    if shutil.which("pandoc") is None:
        return "pandoc not installed"
    if fmt in ("pdf", "djvu", "scan", "scan_degraded", "handwriting_scan"):
        if shutil.which("xelatex") is None:
            return "xelatex not installed"
        if importlib.util.find_spec("marker") is None:
            return "marker not installed"
    if fmt == "djvu":
        for tool in ("c44", "djvm", "ddjvu"):
            if shutil.which(tool) is None:
                return f"{tool} (DjVuLibre) not installed"
    if fmt in ("scan", "scan_degraded", "handwriting_scan") and (
        shutil.which("img2pdf") is None
    ):
        return "img2pdf not installed"
    if fmt == "handwriting_scan":
        font = FONTS_DIR / f"{HANDWRITING_FONT_NAME}{HANDWRITING_FONT_EXT}"
        if not font.is_file():
            return "handwriting font resource absent"
    return None


def _reset_vram() -> None:
    """Reset the CUDA peak memory counter if a GPU is available."""
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def _peak_vram_mb() -> float | None:
    """Return peak CUDA memory usage in MB since the last reset, or None."""
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    return float(torch.cuda.max_memory_allocated()) / (1024 * 1024)


def run_one(
    fixture: str,
    fmt: str,
    work_root: Path,
    *,
    seed: int = 42,
) -> RunRecord:
    """Run one round-trip; an exception is stored in ``RunRecord.error``."""
    skip = _check_tools(fmt)
    if skip:
        return RunRecord(fixture=fixture, fmt=fmt, skipped=True, skip_reason=skip)

    fixture_path = CORPUS_DIR / f"{fixture}.md"
    if not fixture_path.is_file():
        return RunRecord(
            fixture=fixture,
            fmt=fmt,
            skipped=True,
            skip_reason=f"{fixture}.md not in corpus",
        )

    work_dir = work_root / f"{fixture}_{fmt}"
    _reset_vram()
    t0 = time.perf_counter()
    try:
        result = run_roundtrip(fixture_path, fmt, work_dir, seed=seed)
    except Exception as exc:  # noqa: BLE001 -- captures any generation/conversion failure for the report
        return RunRecord(
            fixture=fixture,
            fmt=fmt,
            elapsed_s=time.perf_counter() - t0,
            peak_vram_mb=_peak_vram_mb(),
            error=str(exc),
        )

    elapsed = time.perf_counter() - t0
    peak = _peak_vram_mb()
    status = result.header.status.value if result.header is not None else None

    recog_fail: bool | None = None
    repairable: bool | None = None
    ev = result.evaluation
    if ev is not None:
        recog_fail = ev.recognition_failure
        repairable = ev.repairable

    diff_strs: list[str] = []
    out_counts = result.output_counts
    if out_counts is not None:
        raw = _structural_diffs(fmt, result.reference_counts, out_counts)
        if raw is not None:
            diff_strs = [f"{d.kind}({d.expected}→{d.actual})" for d in raw]

    return RunRecord(
        fixture=fixture,
        fmt=fmt,
        elapsed_s=elapsed,
        peak_vram_mb=peak,
        exit_code=result.exit_code,
        status=status,
        recognition_failure=recog_fail,
        repairable=repairable,
        struct_diffs=diff_strs,
    )


def format_report(records: list[RunRecord]) -> str:
    """Render the run records as a plain-text summary table."""
    w = (16, 16, 8, 5, 9, 10)
    header = (
        f"{'fixture':<{w[0]}} {'format':<{w[1]}} {'status':<{w[2]}}"
        f" {'exit':<{w[3]}} {'time(s)':<{w[4]}} {'VRAM(MB)':<{w[5]}} diffs/notes"
    )
    sep = "-" * 80
    lines = [header, sep]

    for r in records:
        if r.skipped:
            lines.append(
                f"{r.fixture:<{w[0]}} {r.fmt:<{w[1]}} {'—':<{w[2]}}"
                f" {'—':<{w[3]}} {'—':<{w[4]}} {'—':<{w[5]}} SKIP: {r.skip_reason}"
            )
            continue

        status_s = r.status or "—"
        exit_s = str(r.exit_code) if r.exit_code is not None else "—"
        elapsed_s = f"{r.elapsed_s:.1f}" if r.elapsed_s is not None else "—"
        vram_s = f"{r.peak_vram_mb:.0f}" if r.peak_vram_mb is not None else "—"

        if r.error is not None:
            note = f"ERROR: {r.error[:60]}"
        else:
            parts: list[str] = list(r.struct_diffs)
            if r.recognition_failure:
                parts.append("recog_fail")
            if r.repairable:
                parts.append("repairable")
            note = "; ".join(parts) if parts else "—"

        lines.append(
            f"{r.fixture:<{w[0]}} {r.fmt:<{w[1]}} {status_s:<{w[2]}}"
            f" {exit_s:<{w[3]}} {elapsed_s:<{w[4]}} {vram_s:<{w[5]}} {note}"
        )

    total = len(records)
    skipped = sum(1 for r in records if r.skipped)
    errors = sum(1 for r in records if not r.skipped and r.error is not None)
    with_notes = sum(
        1
        for r in records
        if not r.skipped
        and r.error is None
        and (r.struct_diffs or r.recognition_failure or r.repairable)
    )
    clean = total - skipped - errors - with_notes

    lines += [
        sep,
        (
            f"total: {total}  skipped: {skipped}  errors: {errors}"
            f"  notes: {with_notes}  clean: {clean}"
        ),
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the full round-trip matrix and print a defect-summary report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=list(FORMATS),
        default=list(FORMATS),
        metavar="FMT",
        help="formats to run (default: all)",
    )
    parser.add_argument(
        "--fixtures",
        nargs="+",
        default=None,
        metavar="FIXTURE",
        help="corpus fixtures (default: format-specific defaults from the matrix)",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="working directory for generated files (default: a fresh temp dir)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the report to this file in addition to stdout",
    )
    parser.add_argument("--seed", type=int, default=42, help="generation seed")
    args = parser.parse_args(argv)

    work_root: Path = args.work_dir or Path(tempfile.mkdtemp(prefix="raw2md_runner_"))

    pairs: list[tuple[str, str]] = [
        (fixture, fmt)
        for fmt in args.formats
        for fixture in (args.fixtures or list(_FORMAT_FIXTURES.get(fmt, ())))
    ]

    records: list[RunRecord] = []
    for i, (fixture, fmt) in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] {fixture} / {fmt} ...", flush=True)
        record = run_one(fixture, fmt, work_root, seed=args.seed)
        records.append(record)
        if record.skipped:
            print(f"  -> skipped: {record.skip_reason}")
        elif record.error:
            print(f"  -> error: {record.error}")
        else:
            t = f"{record.elapsed_s:.1f}s" if record.elapsed_s is not None else "?"
            v = (
                f"{record.peak_vram_mb:.0f}MB"
                if record.peak_vram_mb is not None
                else "no GPU"
            )
            d = ", ".join(record.struct_diffs) if record.struct_diffs else "clean"
            print(f"  -> {record.status}  {t}  {v}  {d}")

    report = format_report(records)
    print(f"\n{report}")
    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
        print(f"\nReport written to: {args.out}")

    return 1 if any(not r.skipped and r.error is not None for r in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
