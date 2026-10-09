"""Round-trip harness: generate a format, convert it, collect the result.

A known-correct corpus fixture is rendered into a target format and converted
back by raw2md, so the result can be checked against the ground truth.
It also runs standalone for manual inspection::

    py -X utf8 -m tests.synthesis.roundtrip tests/corpus/mixed.md docx
"""

from __future__ import annotations

import argparse
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from raw2md.config import RunConfig
from raw2md.header import ResultHeader, ResultStatus, strip_own_header
from raw2md.orchestrator import run
from raw2md.output import resolve_output_target
from raw2md.quality.evaluator import Evaluation, evaluate

from ._structure import StructureCounts, compare_structure, count_structure
from .gen_djvu import generate_djvu
from .gen_docx import generate_docx
from .gen_pdf import generate_pdf
from .gen_scan import generate_scan

TERMINAL_STATUSES: tuple[ResultStatus, ...] = (ResultStatus.OK, ResultStatus.BAD)

# The names are also pytest parametrization ids and the CLI format argument.
FORMATS: tuple[str, ...] = (
    "pdf",
    "docx",
    "djvu",
    "scan",
    "scan_degraded",
    "handwriting_scan",
)


@dataclass(frozen=True)
class RoundtripResult:
    """Outcome of one round-trip: the run's exit code and the parsed result.

    `output_body` is the result without the YAML header, or None without a result.
    """

    fmt: str
    fixture: Path
    input_file: Path
    exit_code: int
    output_md: Path | None
    header: ResultHeader | None
    output_body: str | None
    reference_body: str

    @property
    def reference_counts(self) -> StructureCounts:
        return count_structure(self.reference_body)

    @property
    def output_counts(self) -> StructureCounts | None:
        if self.output_body is None:
            return None
        return count_structure(self.output_body)

    @property
    def source_pages(self) -> int | None:
        """Source page count for the density check, as the pipeline computes it."""
        if self.input_file.suffix.lower() != ".pdf":
            return None
        from raw2md.engines import pymupdf

        try:
            return pymupdf.count_pages(self.input_file)
        except (RuntimeError, OSError):
            return None

    @property
    def evaluation(self) -> Evaluation | None:
        """Re-evaluate the delivered body to recover the quality metrics and hints.

        The final header keeps only ``status``; the metrics and ``recognition_failure``
        are stripped at the final write. The header's status stays authoritative.
        """
        if self.output_body is None or self.output_md is None:
            return None
        return evaluate(
            self.output_body,
            source_pages=self.source_pages,
            base_dir=self.output_md.parent,
        )


def _generate_input(
    fixture_md: Path, fmt: str, gen_dir: Path, *, seed: int, stem: str | None = None
) -> Path:
    """Render `fixture_md` into the target format and return the generated file.

    `stem` overrides the file name, so a name CommonMark treats specially can be
    tested; the scan and djvu chains carry it through the intermediate PDF.
    """
    if fmt == "pdf":
        return generate_pdf(fixture_md, gen_dir, stem=stem)
    if fmt == "docx":
        return generate_docx(fixture_md, gen_dir, stem=stem)
    if fmt == "djvu":
        return generate_djvu(generate_pdf(fixture_md, gen_dir, stem=stem), gen_dir)
    if fmt == "scan":
        pdf = generate_pdf(fixture_md, gen_dir, stem=stem)
        return generate_scan(pdf, gen_dir, degraded=False, seed=seed)
    if fmt == "scan_degraded":
        pdf = generate_pdf(fixture_md, gen_dir, stem=stem)
        return generate_scan(pdf, gen_dir, degraded=True, seed=seed)
    if fmt == "handwriting_scan":
        pdf = generate_pdf(fixture_md, gen_dir, handwriting=True, stem=stem)
        return generate_scan(
            pdf, gen_dir, stem=stem or "handwriting", degraded=True, seed=seed
        )
    raise ValueError(f"unknown round-trip format: {fmt!r}")


def _make_config(
    input_path: Path, output_dir: Path, flags: Mapping[str, object]
) -> RunConfig:
    """Build a RunConfig from harness defaults, overridden by `flags`."""
    base: dict[str, object] = {
        "input_path": input_path,
        "output_dir": output_dir,
        "skip_existing": False,
        "yaml_header": True,
        "extract_images": True,
        "llm_ocr": None,
        "llm_inspection": None,
        "llm_post": None,
        "llm_latex_fix": False,
        "cuda": True,
        "log_file": False,
        "debug": False,
    }
    base.update(flags)
    return RunConfig(**base)  # type: ignore[arg-type]


def _read_output(md_path: Path) -> tuple[ResultHeader | None, str | None]:
    """Read a result file, splitting off the raw2md header; (None, None) if absent."""
    if not md_path.exists():
        return None, None
    text = md_path.read_text(encoding="utf-8")
    header, body = strip_own_header(text)
    return header, body


def run_roundtrip(
    fixture_md: Path,
    fmt: str,
    work_dir: Path,
    *,
    seed: int = 42,
    stem: str | None = None,
    **flags: object,
) -> RoundtripResult:
    """Generate `fmt` from `fixture_md`, convert it, and collect the result.

    The input goes to ``work_dir/input`` and the result to ``work_dir/out``.
    `flags` overrides RunConfig defaults. The run lock and temp path resolve
    against ``Path.home``, which a test patches to a tmp tree.
    """
    input_file = _generate_input(
        fixture_md, fmt, work_dir / "input", seed=seed, stem=stem
    )
    out_dir = work_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    config = _make_config(input_file, out_dir, flags)
    exit_code = run(config)
    target = resolve_output_target(input_file, output_dir=out_dir)
    header, body = _read_output(target.md_path)
    return RoundtripResult(
        fmt=fmt,
        fixture=fixture_md,
        input_file=input_file,
        exit_code=exit_code,
        output_md=target.md_path if target.md_path.exists() else None,
        header=header,
        output_body=body,
        reference_body=fixture_md.read_text(encoding="utf-8"),
    )


def dump_pair(result: RoundtripResult, dest_dir: Path) -> tuple[Path, Path]:
    """Write the source/output pair side by side for a word-level review."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    source = dest_dir / f"{result.fixture.stem}.source.md"
    output = dest_dir / f"{result.fixture.stem}.{result.fmt}.output.md"
    source.write_text(result.reference_body, encoding="utf-8", newline="")
    output.write_text(result.output_body or "", encoding="utf-8", newline="")
    return source, output


def main(argv: Sequence[str] | None = None) -> int:
    """Run one round-trip and report it for manual inspection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="corpus md fixture to round-trip")
    parser.add_argument("fmt", choices=FORMATS, help="target format")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="working directory (default: a fresh temp dir)",
    )
    parser.add_argument("--seed", type=int, default=42, help="generation seed")
    args = parser.parse_args(argv)

    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="raw2md_roundtrip_"))
    result = run_roundtrip(args.fixture, args.fmt, work_dir, seed=args.seed)

    print(f"format: {result.fmt}  input: {result.input_file}")
    print(f"exit code: {result.exit_code}")
    if result.header is not None:
        print(f"status: {result.header.status.value}  engine: {result.header.engine}")
    out_counts = result.output_counts
    if out_counts is not None:
        diffs = compare_structure(result.reference_counts, out_counts)
        print(f"structure diffs: {diffs or 'none'}")
    source, output = dump_pair(result, work_dir / "pair")
    print("comparison pair:")
    print(f"  source: {source}")
    print(f"  output: {output}")
    print(f"  diff:   git diff --no-index {source} {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
