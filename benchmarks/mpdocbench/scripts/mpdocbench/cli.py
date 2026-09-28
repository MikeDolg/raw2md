"""The command line of the benchmark runner: one subcommand per phase."""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from mpdocbench import convert, fetch, pdfs, report, scoring
from mpdocbench.pins import (
    LANGUAGES,
    BenchmarkError,
    DataDir,
    Pins,
    RunDir,
    dump_yaml,
    load_pins,
    load_yaml,
    read_annotation,
    select_documents,
)


def _fetch(args: argparse.Namespace, pins: Pins) -> None:
    record = fetch.fetch(pins, DataDir(args.data))
    missing = record["missing"]
    total = record["documents"]
    print(f"fetched {total - len(missing)} of {total} documents")
    if missing:
        print(f"missing {len(missing)}: {record['missing_reason']}")


def _build(args: argparse.Namespace, pins: Pins) -> None:
    data, run = DataDir(args.data), RunDir(args.run)
    if not data.record.is_file():
        raise BenchmarkError(f"{data.root} holds no fetch.yaml; run fetch first")
    fetched = load_yaml(data.record)
    chosen = sorted(args.documents) if args.documents else None
    record = load_yaml(run.record) if run.record.is_file() else {}
    if record.get("sessions") and (
        record.get("language"),
        record.get("documents"),
    ) != (args.language, chosen):
        raise BenchmarkError(
            f"{run.root} was converted for another set of documents;"
            " start another run folder"
        )
    documents = select_documents(
        read_annotation(data.annotation(pins), args.language), chosen
    )
    built = pdfs.build(documents, data.images, run.pdfs, fetched.get("missing") or [])
    record.update({"language": args.language, "documents": chosen})
    dump_yaml(run.record, record)
    print(f"built {len(built)} PDFs in {run.pdfs}")


def _convert(args: argparse.Namespace, _pins: Pins) -> None:
    convert.convert(RunDir(args.run), args.llm)


def _score(args: argparse.Namespace, pins: Pins) -> None:
    run = RunDir(args.run)
    result = scoring.score(
        pins, DataDir(args.data), run, args.scorer_python, args.skip_metric
    )
    print(f"result written to {run.results}\n")
    print(report.render([result], pins))


def _all(args: argparse.Namespace, pins: Pins) -> None:
    _fetch(args, pins)
    _build(args, pins)
    _convert(args, pins)
    _score(args, pins)


def _report(args: argparse.Namespace, pins: Pins) -> None:
    print(report.render([load_yaml(path) for path in args.results], pins), end="")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py", description="Run the MPDocBench-Parse benchmark against raw2md."
    )
    phases = parser.add_subparsers(dest="phase", required=True)

    def add(
        name: str, help_text: str, *, data: bool, run: bool
    ) -> argparse.ArgumentParser:
        sub = phases.add_parser(name, help=help_text)
        if data:
            sub.add_argument(
                "--data",
                type=Path,
                default=Path("mpdocbench-data"),
                help="where the harness and the pages are downloaded"
                " (default: %(default)s)",
            )
        if run:
            sub.add_argument(
                "--run",
                type=Path,
                default=Path("mpdocbench-run"),
                help="the folder of this run: PDFs, raw2md output, result"
                " (default: %(default)s)",
            )
        return sub

    def add_language(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--language", choices=LANGUAGES, default="all")
        sub.add_argument(
            "--documents",
            nargs="+",
            metavar="NAME",
            help="only these documents of the language set, for a trial run;"
            " the result is then not comparable with the leaderboard",
        )

    def add_llm(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--llm",
            metavar="MODEL",
            help="run the LLM inspection and post stages with this model key of"
            " settings.json",
        )

    def add_scorer(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--scorer-python",
            type=Path,
            required=True,
            help="the interpreter of the scorer environment",
        )
        sub.add_argument(
            "--skip-metric",
            action="append",
            default=[],
            metavar="METRIC",
            help="do not compute this metric, for example CDM on a machine"
            " without LaTeX; the result states it as n/a",
        )

    add(
        "fetch",
        "download the harness and the pages from the authors",
        data=True,
        run=False,
    )
    add_language(add("build", "assemble one PDF per document", data=True, run=True))
    add_llm(add("convert", "convert the PDFs with raw2md", data=False, run=True))
    add_scorer(
        add("score", "score the run and write results.yaml", data=True, run=True)
    )
    every = add("all", "fetch, build, convert, and score", data=True, run=True)
    add_language(every)
    add_llm(every)
    add_scorer(every)
    shown = phases.add_parser("report", help="print results as one Markdown table")
    shown.add_argument(
        "results",
        type=Path,
        nargs="+",
        help="results.yaml files, a pair of columns each",
    )
    return parser


_PHASES = {
    "fetch": _fetch,
    "build": _build,
    "convert": _convert,
    "score": _score,
    "all": _all,
    "report": _report,
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # The table carries arrows, and a redirected stream on Windows takes a
    # code page that has none.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        _PHASES[args.phase](args, load_pins())
    except BenchmarkError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0
