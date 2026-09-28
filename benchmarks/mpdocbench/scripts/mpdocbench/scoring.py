"""Score a converted run and write its result.

A run converted with `-d` holds two bodies per document: the engine output
(`conversion.md` under `<doc>.debug/`) and the final result (`<doc>.md`). Both
are scored over the same documents, so the difference between the two columns
is what raw2md adds to the engine.

The scorer lives in its own environment and is not importable from here, so it
runs as a subprocess of the interpreter `--scorer-python` names, from its own
folder: it writes its output to `./result`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mpdocbench.pins import (
    BenchmarkError,
    DataDir,
    Document,
    Pins,
    RunDir,
    dump_yaml,
    load_yaml,
    read_annotation,
    select_documents,
    system_name,
)
from raw2md.header import ResultStatus, strip_own_header

ENGINE = "engine"
RESULT = "result"
STAGES = (ENGINE, RESULT)
NOT_AVAILABLE = "n/a"

_METRIC_RESULT = "metric_result.json"
_CONFIG = "config.yaml"
_LOG = "scorer.log"
# What the scorer prints when a text match runs past its 30 seconds and falls
# back to a simpler algorithm. It says so nowhere else, and a text score with
# many fallbacks is a different measurement.
_FALLBACK_MARK = "match_gt2pred_simple will be used"
_REQUEST_MARK = "-- request ("

# CDM renders every formula through these, and it reports a missing toolchain
# as a zero score rather than as an error.
_CDM = "CDM"
_CDM_TOOLS = ("xelatex", "magick")


@dataclass(frozen=True)
class Census:
    annotated: list[Document]
    missing: list[str]  # not fetched
    failed: list[str]  # fetched, but raw2md left no body for one of the stages
    scored: list[Document]


def body_path(outputs: Path, document: str, stage: str) -> Path:
    if stage == RESULT:
        return outputs / f"{document}.md"
    return outputs / f"{document}.debug" / "conversion.md"


def take_census(
    annotated: Sequence[Document], missing: Sequence[str], outputs: Path
) -> Census:
    """Sort the annotated documents into missing, failed, and scored."""
    absent = set(missing)
    failed, scored = [], []
    for document in annotated:
        if document.name in absent:
            continue
        if _finished(outputs, document.name):
            scored.append(document)
        else:
            failed.append(document.name)
    return Census(
        annotated=list(annotated),
        missing=[doc.name for doc in annotated if doc.name in absent],
        failed=failed,
        scored=scored,
    )


def _finished(outputs: Path, document: str) -> bool:
    """Both bodies exist, and the result is not the stub of a conversion.

    raw2md writes an `in_progress` stub at the result name before it converts,
    so an interrupted run leaves a result file with no body behind.
    """
    if not all(body_path(outputs, document, stage).is_file() for stage in STAGES):
        return False
    text = body_path(outputs, document, RESULT).read_text(encoding="utf-8")
    header, _ = strip_own_header(text)
    return header is None or header.status is not ResultStatus.IN_PROGRESS


def layout_predictions(
    outputs: Path, folder: Path, documents: Sequence[Document], stage: str
) -> None:
    """Copy one stage body per document into `folder`, named as the scorer reads it."""
    # A folder left from an earlier attempt would hand the scorer bodies that
    # this scoring never chose.
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for document in documents:
        text = body_path(outputs, document.name, stage).read_text(encoding="utf-8")
        # The result carries raw2md's YAML header, which the scorer would read
        # as body text. The engine body has none.
        _, body = strip_own_header(text)
        (folder / f"{document.name}.md").write_text(
            body, encoding="utf-8", newline="\n"
        )


def active_metrics(pins: Pins) -> dict[str, list[str]]:
    """Every pinned metric that no key of `metrics_off` turns off.

    A key names a metric, or one element of it as `<element>.<metric>`: the same
    metric can be measurable on one element and not on another.
    """
    active = {
        element: [
            name
            for name in names
            if name not in pins.metrics_off
            and f"{element}.{name}" not in pins.metrics_off
        ]
        for element, names in pins.metrics.items()
    }
    return {element: names for element, names in active.items() if names}


def check_cdm_environment(metrics: Mapping[str, Sequence[str]]) -> None:
    if not any(_CDM in names for names in metrics.values()):
        return
    missing = [tool for tool in _CDM_TOOLS if shutil.which(tool) is None]
    if missing:
        raise BenchmarkError(
            f"{_CDM} needs {', '.join(missing)} on PATH and would otherwise score"
            f" every formula as zero; build the scorer environment or pass"
            f" --skip-metric {_CDM}"
        )


def scorer_config(
    metrics: Mapping[str, Sequence[str]],
    *,
    annotation: Path,
    predictions: Path,
    match_method: str,
    language: str,
) -> dict[str, Any]:
    # The scorer resolves these from its own folder, and a relative path that
    # lands on nothing scores as an aggregate over an empty set.
    for role, path in (("annotation", annotation), ("prediction", predictions)):
        if not path.is_absolute():
            raise BenchmarkError(f"the {role} path {path} has to be absolute")
    dataset: dict[str, Any] = {
        "dataset_name": "end2end_dataset",
        "ground_truth": {"data_path": str(annotation)},
        "prediction": {"data_path": str(predictions)},
        "match_method": match_method,
    }
    if language != "all":
        dataset["filter"] = {"language": language}
    return {
        "end2end_eval": {
            "metrics": {
                element: {"metric": list(names)} for element, names in metrics.items()
            },
            "dataset": dataset,
        }
    }


def run_scorer(
    harness: Path, scorer_python: Path, config: Path, save_name: str, log: Path
) -> Path:
    """Run the harness on one prediction folder and return its aggregate output.

    Standard output goes to the log: it is the only place the scorer names a
    text match that fell back. The progress bar on standard error stays on the
    terminal.
    """
    result_dir = harness / "result" / save_name
    if result_dir.exists():
        shutil.rmtree(result_dir)
    # A redirected stream takes the encoding of the system, not of the file,
    # and the scorer prints Chinese element names.
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    with log.open("w", encoding="utf-8") as stream:
        completed = subprocess.run(
            [str(scorer_python), "pdf_validation.py", "--config", str(config)],
            cwd=harness,
            check=False,
            stdout=stream,
            env=environment,
        )
    if completed.returncode != 0:
        raise BenchmarkError(
            f"the scorer exited with {completed.returncode} on {save_name}"
        )
    metric_path = result_dir / _METRIC_RESULT
    if not metric_path.is_file():
        raise BenchmarkError(f"the scorer wrote no {_METRIC_RESULT} for {save_name}")
    return metric_path


def headline_scores(
    metric_result: Mapping[str, Any], pins: Pins, active: Mapping[str, Sequence[str]]
) -> dict[str, Any]:
    """One number per `<element>.<metric>`: the aggregate `headline` names.

    A metric turned off, or one the scorer found no sample for, reads `n/a`.
    """
    scores: dict[str, Any] = {}
    for element, names in pins.metrics.items():
        for name in names:
            key = f"{element}.{name}"
            value = metric_result.get(element, {}).get("all", {}).get(name, {})
            number = value.get(pins.headline[name]) if isinstance(value, dict) else None
            if name not in active.get(element, ()) or not isinstance(
                number, int | float
            ):
                scores[key] = NOT_AVAILABLE
            else:
                scores[key] = round(float(number), 4)
    # A key without an element (`CDM`) turns a pinned metric off, and that
    # metric already has its rows above.
    for key in pins.metrics_off:
        if "." in key:
            scores.setdefault(key, NOT_AVAILABLE)
    return scores


def count_fallbacks(log: Path) -> int:
    return sum(
        1
        for line in log.read_text(encoding="utf-8").splitlines()
        if _FALLBACK_MARK in line
    )


def count_llm_requests(outputs: Path, documents: Sequence[Document]) -> int:
    """Requests the run spent on these documents, counted in the debug traffic."""
    total = 0
    for document in documents:
        for trace in sorted((outputs / f"{document.name}.debug" / "llm").glob("*.txt")):
            total += sum(
                1
                for line in trace.read_text(encoding="utf-8").splitlines()
                if line.startswith(_REQUEST_MARK)
            )
    return total


def build_result(
    pins: Pins,
    *,
    run_record: Mapping[str, Any],
    census: Census,
    scores: Mapping[str, Mapping[str, Any]],
    fallbacks: Mapping[str, int],
    llm_requests: int,
    scoring_minutes: float,
    missing_reason: str | None,
) -> dict[str, Any]:
    """The result of one run: what ran, on what, over which documents, the scores."""
    language = str(run_record["language"])
    sessions = run_record.get("sessions") or []
    notes = [
        f"{key} is {NOT_AVAILABLE}: {reason}."
        for key, reason in sorted(pins.metrics_off.items())
    ]
    notes += [
        f"The {stage} text match fell back to the simple algorithm"
        f" on {count} documents."
        for stage, count in fallbacks.items()
        if count
    ]
    return {
        "benchmark": "MPDocBench-Parse",
        "raw2md": run_record.get("raw2md"),
        "command": run_record.get("command"),
        "llm": run_record.get("llm"),
        "language": language,
        "scored_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "pins": {
            "upstream_commit": pins.upstream_commit,
            "dataset_sha256": pins.dataset_sha256,
            "slidevqa_revision": pins.slidevqa_revision,
        },
        "machine": {
            "gpu": run_record.get("gpu"),
            "conversion_platform": run_record.get("platform"),
            "scoring_cpus": os.cpu_count(),
            "scoring_platform": system_name(),
        },
        "time": {
            "conversion_minutes": round(sum(float(s["minutes"]) for s in sessions), 1),
            "scoring_minutes": round(scoring_minutes, 1),
        },
        "documents": {
            "annotated": len(census.annotated),
            "missing": len(census.missing),
            "failed": len(census.failed),
            "scored": len(census.scored),
            "pages_scored": sum(len(doc.pages) for doc in census.scored),
            # The leaderboard counts every document of the benchmark.
            "chosen": run_record.get("documents"),
            "comparable_with_leaderboard": language == "all"
            and len(census.scored) == pins.dataset_documents,
            "missing_reason": missing_reason if census.missing else None,
            "missing_list": census.missing,
            "failed_list": census.failed,
        },
        "llm_requests": llm_requests,
        "scores": {
            key: {stage: scores[stage].get(key, NOT_AVAILABLE) for stage in STAGES}
            for key in scores[ENGINE]
        },
        "notes": notes,
    }


def score(
    pins: Pins,
    data: DataDir,
    run: RunDir,
    scorer_python: Path,
    skip_metrics: Sequence[str] = (),
) -> dict[str, Any]:
    """Score both stages of a run and write `results.yaml`. Return it."""
    if not data.record.is_file():
        raise BenchmarkError(f"{data.root} holds no fetch.yaml; run fetch first")
    if not run.record.is_file() or not load_yaml(run.record).get("sessions"):
        raise BenchmarkError(f"{run.root} holds no conversion; run convert first")
    fetched = load_yaml(data.record)
    run_record = load_yaml(run.record)
    language = str(run_record["language"])
    harness = data.harness(pins).resolve()
    annotation = data.annotation(pins).resolve()

    pins_used = pins
    if skip_metrics:
        off = dict(pins.metrics_off)
        for name in skip_metrics:
            off.setdefault(name, "the scoring session skipped it")
        pins_used = replace(pins, metrics_off=off)
    active = active_metrics(pins_used)
    check_cdm_environment(active)

    chosen = run_record.get("documents")
    census = take_census(
        select_documents(read_annotation(annotation, language), chosen),
        fetched.get("missing") or [],
        run.outputs,
    )
    if not census.scored:
        raise BenchmarkError(f"{run.outputs} holds no document with both bodies")

    started = time.monotonic()
    scores: dict[str, dict[str, Any]] = {}
    fallbacks: dict[str, int] = {}
    for stage in STAGES:
        stage_dir = run.scoring.resolve() / stage
        # The scorer names its output folder after the prediction folder, so
        # the name carries the run: two runs scored from one clone would
        # otherwise overwrite each other's output.
        predictions = stage_dir / f"{run.root.name}-{stage}"
        layout_predictions(run.outputs, predictions, census.scored, stage)
        print(f"{stage}: scoring {len(census.scored)} documents", flush=True)
        config = stage_dir / _CONFIG
        dump_yaml(
            config,
            scorer_config(
                active,
                annotation=annotation,
                predictions=predictions,
                match_method=pins.match_method,
                language=language,
            ),
        )
        log = stage_dir / _LOG
        metric_path = run_scorer(harness, scorer_python, config, predictions.name, log)
        shutil.copyfile(metric_path, stage_dir / _METRIC_RESULT)
        scores[stage] = headline_scores(
            json.loads(metric_path.read_text(encoding="utf-8")), pins_used, active
        )
        fallbacks[stage] = count_fallbacks(log)

    result = build_result(
        pins_used,
        run_record=run_record,
        census=census,
        scores=scores,
        fallbacks=fallbacks,
        llm_requests=count_llm_requests(run.outputs, census.scored),
        scoring_minutes=(time.monotonic() - started) / 60,
        missing_reason=fetched.get("missing_reason"),
    )
    dump_yaml(run.results, result)
    return result
