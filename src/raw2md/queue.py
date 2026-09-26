"""Global batch queue, persistence, and resume.

The queue is built whole at the start of a run, so the progress bar has an
exact denominator and a resume replays the original parameters. It is saved
to `queue.json` with the run parameters, never changed per file, and removed
on success.

`--skip-existing` asks whether the result name holds a finished result
(`has_finished_result`); resume asks whether this very source was finished,
by `source_hash` (`is_complete`). `is_unfinished` finds the `in_progress`
stub of an interrupted file. The supported extensions are injected, so the
queue does not import the engines.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from raw2md.config import RunConfig
from raw2md.header import (
    DEFAULT_ENGINE,
    HeaderParseError,
    ResultStatus,
    build_stub,
    compute_source_hash,
    from_yaml_block,
    strip_own_header,
    to_yaml_block,
)
from raw2md.logging_setup import screen_info
from raw2md.output import (
    OutputTarget,
    atomic_write_text,
    existing_md,
    is_own_result,
    resolve_output_target,
    write_md,
)
from raw2md.paths import queue_file

_logger = logging.getLogger("raw2md")

# Bump when the shape or the meaning of a saved field changes; a file of any
# other version is refused rather than misread.
QUEUE_VERSION = 5


class QueueError(Exception):
    """Queue could not be built, saved, or loaded."""


@dataclass(frozen=True)
class QueueItem:
    """One source file in the queue.

    `include_extension` is decided at build time and saved, so a resume
    reproduces the same targets.
    """

    source: Path
    include_extension: bool

    def output_target(self, output_dir: Path | None) -> OutputTarget:
        return resolve_output_target(
            self.source,
            output_dir=output_dir,
            include_extension=self.include_extension,
        )


@dataclass(frozen=True)
class Queue:
    """The frozen file list plus the run parameters that produced it."""

    params: RunConfig
    items: tuple[QueueItem, ...]


def queue_path() -> Path:
    return queue_file()


def _normalized_ext(path: Path) -> str:
    """Extension lower-cased and without the leading dot, as the engines read it."""
    return path.suffix.lower().lstrip(".")


def _is_in_place(input_dir: Path, output_dir: Path | None) -> bool:
    """Whether folder results land back in the scanned folder (no separate output)."""
    return output_dir is None or output_dir.resolve() == input_dir.resolve()


def _discover_sources(
    input_path: Path, supported: frozenset[str], output_dir: Path | None
) -> list[Path]:
    """Resolve INPUT to the ordered list of files to queue.

    A named file is always queued; its format is judged at conversion. A
    folder is scanned without recursion and sorted by name. In place, an md
    with raw2md's own header is a prior result and is skipped. A folder that
    yields nothing gets a warning: the run succeeds either way.
    """
    if input_path.is_file():
        return [input_path.resolve()]
    if input_path.is_dir():
        in_place = _is_in_place(input_path, output_dir)
        matches: list[Path] = []
        unsupported = 0
        earlier_results = 0
        for child in input_path.iterdir():
            if not child.is_file():
                continue
            if _normalized_ext(child) not in supported:
                unsupported += 1
                continue
            if in_place and _normalized_ext(child) == "md" and is_own_result(child):
                earlier_results += 1
                continue
            matches.append(child.resolve())
        if not matches:
            _logger.warning(
                "no convertible file in %s: %d of an unsupported format, "
                "%d result(s) of an earlier run",
                input_path,
                unsupported,
                earlier_results,
            )
        # The same order on case-sensitive and case-insensitive disks.
        return sorted(matches, key=lambda p: (p.name.lower(), p.name))
    raise QueueError(f"input path does not exist: {input_path}")


def _result_key(target: OutputTarget) -> tuple[str, str]:
    """Case-insensitive identity of a result md path, for collision grouping."""
    return (str(target.md_path.parent).lower(), target.md_path.name.lower())


def _resolve_items(
    sources: list[Path], output_dir: Path | None
) -> tuple[QueueItem, ...]:
    """Turn sources into items, flagging stem/extension collisions.

    Colliding default result names get `include_extension`. An in-place md
    source reserves its own `<stem>.md`, since its result is
    `<stem>_cleaned.md`; a sibling `<stem>.pdf` must not take that name. A
    collision the extension cannot resolve is left to the writer.
    """
    targets = {
        src: resolve_output_target(src, output_dir=output_dir, include_extension=False)
        for src in sources
    }
    counts: dict[tuple[str, str], int] = {}
    for target in targets.values():
        key = _result_key(target)
        counts[key] = counts.get(key, 0) + 1
    # Only in place: with an output dir the md result keeps `<stem>.md` and
    # already counts as a target.
    for src in sources:
        if output_dir is None and _normalized_ext(src) == "md":
            key = (str(src.parent).lower(), src.name.lower())
            counts[key] = counts.get(key, 0) + 1
    return tuple(
        QueueItem(source=src, include_extension=counts[_result_key(targets[src])] > 1)
        for src in sources
    )


def readiness_hash(source: Path) -> str:
    """The `source_hash` that marks `source` as processed.

    An `md` input hashes its body without raw2md's own header, so a re-fed
    result is recognized. Other formats hash the raw bytes.
    """
    if source.suffix.lower() == ".md":
        _, body = strip_own_header(source.read_text(encoding="utf-8"))
        return compute_source_hash(body.encode("utf-8"))
    return compute_source_hash(source.read_bytes())


def is_complete(source: Path, target: OutputTarget) -> bool:
    """True when `target` already holds a finished result for `source`.

    Finished means an `ok` or `bad` status and a matching `source_hash`. A
    headerless result (`--no-yaml`) is not finished.
    """
    try:
        text = target.md_path.read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        header = from_yaml_block(text)
    except HeaderParseError:
        return False
    if header is None or header.status not in (ResultStatus.OK, ResultStatus.BAD):
        return False
    try:
        digest = readiness_hash(source)
    except (OSError, UnicodeDecodeError):
        return False
    return header.source_hash == digest


def has_finished_result(target: OutputTarget) -> bool:
    """True when `target`'s md name is already held by a finished result.

    Only the name counts, not which source produced the result. A stub or an
    md without raw2md's header leaves the file to be processed.
    """
    md = existing_md(target)
    if md is None:
        return False
    try:
        header = from_yaml_block(md.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, HeaderParseError):
        return False
    return header is not None and header.status in (ResultStatus.OK, ResultStatus.BAD)


def is_unfinished(target: OutputTarget, source_hash: str) -> bool:
    """True when `target` holds this tool's own unfinished result for `source_hash`.

    Anything else keeps the protection an existing result has.
    """
    try:
        text = target.md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    try:
        header = from_yaml_block(text)
    except HeaderParseError:
        return False
    return (
        header is not None
        and header.status is ResultStatus.IN_PROGRESS
        and header.source_hash == source_hash
    )


def build_queue(config: RunConfig, supported_extensions: frozenset[str]) -> Queue:
    """Build the whole queue up front from INPUT.

    `--skip-existing` drops its files here, so the bar total is exact.
    """
    sources = _discover_sources(
        config.input_path, supported_extensions, config.output_dir
    )
    items = _resolve_items(sources, config.output_dir)
    if config.skip_existing:
        items = tuple(item for item in items if _keep_in_queue(item, config.output_dir))
    return Queue(params=config, items=items)


def _keep_in_queue(item: QueueItem, output_dir: Path | None) -> bool:
    """False for an item `--skip-existing` drops, naming the result it kept.

    Shown on the console: otherwise a run that skipped everything looks like a
    run that found nothing.
    """
    target = item.output_target(output_dir)
    if not has_finished_result(target):
        return True
    screen_info(
        _logger,
        "skip %s: result already exists: %s",
        item.source.name,
        target.md_path,
    )
    return False


def write_in_progress_stub(
    target: OutputTarget,
    *,
    source_name: str,
    source_hash: str,
    engine: str = DEFAULT_ENGINE,
    inspection: str | None = None,
    post: str | None = None,
) -> None:
    """Write the header-only `in_progress` stub before conversion starts.

    A crash leaves the stub, which resume and `--skip-existing` redo.
    """
    header = build_stub(
        source_name,
        engine=engine,
        inspection=inspection,
        post=post,
        source_hash=source_hash,
    )
    write_md(target, to_yaml_block(header))


def _params_to_json(config: RunConfig) -> dict[str, Any]:
    return {
        "input_path": str(config.input_path),
        "output_dir": None if config.output_dir is None else str(config.output_dir),
        "skip_existing": config.skip_existing,
        "yaml_header": config.yaml_header,
        "extract_images": config.extract_images,
        "llm_ocr": config.llm_ocr,
        "llm_inspection": config.llm_inspection,
        "llm_post": config.llm_post,
        "llm_latex_fix": config.llm_latex_fix,
        "cuda": config.cuda,
        "log_file": config.log_file,
        "debug": config.debug,
    }


def _model_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def _params_from_json(data: Any) -> RunConfig:
    if not isinstance(data, Mapping):
        raise QueueError("queue.json params must be an object")
    try:
        output_dir = data["output_dir"]
        return RunConfig(
            input_path=Path(str(data["input_path"])),
            output_dir=None if output_dir is None else Path(str(output_dir)),
            skip_existing=bool(data["skip_existing"]),
            yaml_header=bool(data["yaml_header"]),
            extract_images=bool(data["extract_images"]),
            llm_ocr=_model_or_none(data["llm_ocr"]),
            llm_inspection=_model_or_none(data["llm_inspection"]),
            llm_post=_model_or_none(data["llm_post"]),
            llm_latex_fix=bool(data["llm_latex_fix"]),
            cuda=bool(data["cuda"]),
            log_file=bool(data["log_file"]),
            debug=bool(data["debug"]),
        )
    except KeyError as exc:
        raise QueueError(f"queue.json missing run parameter: {exc}") from exc


def _items_from_json(data: Any) -> tuple[QueueItem, ...]:
    if not isinstance(data, list):
        raise QueueError("queue.json items must be a list")
    try:
        return tuple(
            QueueItem(
                source=Path(str(entry["source"])),
                include_extension=bool(entry["include_extension"]),
            )
            for entry in data
        )
    except (KeyError, TypeError) as exc:
        raise QueueError(f"queue.json item is malformed: {exc}") from exc


def save_queue(queue: Queue, path: Path | None = None) -> None:
    """Persist the queue and its run parameters to `queue.json`, atomically."""
    target = path if path is not None else queue_file()
    envelope = {
        "version": QUEUE_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": _params_to_json(queue.params),
        "items": [
            {"source": str(item.source), "include_extension": item.include_extension}
            for item in queue.items
        ],
    }
    text = json.dumps(envelope, ensure_ascii=False, indent=2)
    atomic_write_text(target, text)


def load_queue(path: Path | None = None) -> Queue:
    """Load the saved queue, reconstructing its run parameters.

    Raises `QueueError` when no queue is saved or the file is unreadable, not
    JSON, or of an unsupported version.
    """
    source = path if path is not None else queue_file()
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise QueueError("no saved queue to resume") from exc
    except OSError as exc:
        raise QueueError(f"cannot read queue.json: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QueueError(f"queue.json is not valid JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise QueueError("queue.json must be a JSON object")
    if data.get("version") != QUEUE_VERSION:
        raise QueueError(f"unsupported queue version: {data.get('version')!r}")
    return Queue(
        params=_params_from_json(data.get("params")),
        items=_items_from_json(data.get("items")),
    )


def remove_queue(path: Path | None = None) -> None:
    """Remove the saved queue; a no-op when none exists. Called on success."""
    target = path if path is not None else queue_file()
    target.unlink(missing_ok=True)
