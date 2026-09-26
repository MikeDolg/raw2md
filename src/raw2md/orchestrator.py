"""Run orchestrator: lock, queue, batch bar, and exit-code aggregation.

One run at a time processes files one by one: marker holds the GPU. The
queue is saved up front and removed only when no file failed; a crash or a
failure leaves it for `resume`. The engine registry is injectable, so tests
run without marker, a GPU, or a temp path.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO

from raw2md.cleaning import DEFAULT_WITNESS_MIN
from raw2md.config import RunConfig, requests_llm
from raw2md.engines import DjvuEngine, EngineRegistry, MarkerEngine, PandocEngine
from raw2md.exit_codes import ExitCode
from raw2md.header import ResultStatus
from raw2md.keywords import Keywords, KeywordsError, default_keywords, load_keywords
from raw2md.llm import Provider, build_provider
from raw2md.llm.chunking import DEFAULT_PAGES_PER_REQUEST, chunk_budget
from raw2md.llm.inspection.common import InspectOperation
from raw2md.llm.ocr import OcrOperation
from raw2md.llm.post.common import PostOperation
from raw2md.lock import LockHeldError, RunLock
from raw2md.logging_setup import screen_info, setup_logging
from raw2md.paths import keywords_file, prompts_file, settings_file
from raw2md.pipeline import FileResult, Outcome, RunContext, process_file
from raw2md.progress import BatchProgress
from raw2md.prompts import Prompts, PromptsError, load_prompts, resolve_prompt
from raw2md.queue import (
    Queue,
    QueueError,
    build_queue,
    load_queue,
    remove_queue,
    save_queue,
)
from raw2md.settings import (
    ModelConfig,
    Settings,
    SettingsError,
    default_settings,
    load_settings,
    resolve_log_file,
)
from raw2md.temp import TempPathError, select_temp_root

_logger = logging.getLogger("raw2md")

# md has no engine but is queued and re-cleaned.
_MD_EXTENSION = "md"


class _LlmUnavailableError(Exception):
    """A requested LLM tool cannot start the run (exit code 3).

    Raised before any file: a missing tool is global to the run.
    """


@dataclass(frozen=True)
class _RunSettings:
    """settings.json, prompts.yaml, and keywords.yaml loaded once per run.

    `settings` and `keywords` are always loaded; a broken file falls back to
    the defaults and keeps its error, which only an LLM operation that needs a
    model raises. `prompts` is read only when an LLM step is requested, so a
    broken prompts.yaml never blocks a plain run.
    """

    settings: Settings
    settings_error: SettingsError | None
    prompts: Prompts | None
    prompts_error: PromptsError | None
    keywords: Keywords
    keywords_error: KeywordsError | None


def _load_run_settings(config: RunConfig) -> _RunSettings:
    try:
        settings = load_settings(settings_file())
        settings_error = None
    except SettingsError as exc:
        settings = default_settings()
        settings_error = exc
    prompts: Prompts | None = None
    prompts_error: PromptsError | None = None
    if requests_llm(config):
        try:
            prompts = load_prompts(prompts_file())
        except PromptsError as exc:
            prompts_error = exc
    try:
        keywords = load_keywords(keywords_file())
        keywords_error = None
    except KeywordsError as exc:
        keywords = default_keywords()
        keywords_error = exc
    return _RunSettings(
        settings, settings_error, prompts, prompts_error, keywords, keywords_error
    )


def _open_run(config: RunConfig) -> tuple[_RunSettings, TextIO | None]:
    """Load the run's files, start its logging, and warn about their fallbacks.

    `--llm-latex-fix` is warned too: a rewritten formula renders as cleanly as
    a repaired one, so the run log is the only record that tells them apart.
    """
    run_settings = _load_run_settings(config)
    log_stream = _init_logging(config, run_settings.settings)
    if run_settings.settings_error is not None:
        _logger.warning(
            "settings.json is invalid (%s); using built-in defaults",
            run_settings.settings_error,
        )
    if run_settings.keywords_error is not None:
        _logger.warning(
            "keywords.yaml is invalid (%s); using the shipped dictionary",
            run_settings.keywords_error,
        )
    if config.llm_latex_fix:
        _logger.warning(
            "--llm-latex-fix is on: inspection may rewrite a formula, and a "
            "rewritten formula cannot be told from a repaired one"
        )
    return run_settings, log_stream


def run(config: RunConfig, *, registry: EngineRegistry | None = None) -> int:
    """Process INPUT: build the queue under the lock and run it."""
    config = _absolutize(_normalize_output_dir(config))
    # Before any file: a source removed during the run must not turn a
    # single-file run into batch exit codes.
    single_file = config.input_path.is_file()
    run_settings, log_stream = _open_run(config)
    return _under_lock(
        lambda: _run_locked(
            config, registry, log_stream, run_settings, single_file=single_file
        )
    )


def _run_locked(
    config: RunConfig,
    registry: EngineRegistry | None,
    log_stream: TextIO | None,
    run_settings: _RunSettings,
    *,
    single_file: bool,
) -> int:
    ctx = _start_context(config, registry, log_stream, run_settings, resume=False)
    if ctx is None:
        return int(ExitCode.MISSING_DEPENDENCY)
    supported = ctx.registry.extensions() | {_MD_EXTENSION}
    try:
        queue = build_queue(config, supported)
    except QueueError as exc:
        _logger.error("%s", exc)  # noqa: TRY400 -- expected error; no traceback wanted here
        return int(ExitCode.ARGUMENT_ERROR)
    try:
        save_queue(queue)
    except OSError as exc:
        # No run without the queue that makes it resumable.
        _logger.error("could not save queue: %s", exc)  # noqa: TRY400 -- expected error; no traceback wanted here
        return int(ExitCode.MISSING_DEPENDENCY)
    return _process_and_finish(ctx, queue, single_file=single_file)


def run_resume(*, registry: EngineRegistry | None = None) -> int:
    """Resume the saved queue under the lock, replaying its parameters.

    The queue is read under the lock, so a concurrent run cannot replace it
    in between. Logging is console-only until the saved parameters are read.
    """
    _init_logging(None, None)
    return _under_lock(lambda: _resume_locked(registry))


def _resume_locked(registry: EngineRegistry | None) -> int:
    try:
        queue = load_queue()
    except QueueError as exc:
        _logger.error("%s", exc)  # noqa: TRY400 -- expected error; no traceback wanted here
        return int(ExitCode.ARGUMENT_ERROR)
    config = queue.params
    # Before any file, as in `run`.
    single_file = config.input_path.is_file()
    run_settings, log_stream = _open_run(config)
    ctx = _start_context(config, registry, log_stream, run_settings, resume=True)
    if ctx is None:
        return int(ExitCode.MISSING_DEPENDENCY)
    return _process_and_finish(ctx, queue, single_file=single_file)


def _under_lock(body: Callable[[], int]) -> int:
    """Run `body` holding the run lock; a held lock is exit code 3."""
    lock = RunLock()
    try:
        lock.acquire()
    except LockHeldError as exc:
        _logger.error("%s", exc)  # noqa: TRY400 -- expected error; no traceback wanted here
        return int(ExitCode.MISSING_DEPENDENCY)
    try:
        return body()
    finally:
        lock.release()


# Shared, so the summary's error count agrees with the exit code.
_FAILURE_OUTCOMES = (Outcome.NO_RESULT, Outcome.LLM_ERROR)


def _process_and_finish(ctx: RunContext, queue: Queue, *, single_file: bool) -> int:
    """Run every queued file; remove the queue only once nothing needs a redo."""
    results = _process_all(ctx, queue)
    # A failure keeps the queue. Resume redoes only files without a result: a
    # post or inspection LLM_ERROR already wrote its base result.
    if not any(result.outcome in _FAILURE_OUTCOMES for result in results):
        remove_queue()
    return int(aggregate_exit_code(results, single_file=single_file))


def _process_all(ctx: RunContext, queue: Queue) -> list[FileResult]:
    screen_info(
        _logger,
        "raw2md: starting run of %d file(s) in %s at %s",
        len(queue.items),
        ctx.config.input_path,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # noqa: DTZ005 -- local wall-clock shown in the console banner
    )
    results: list[FileResult] = []
    start = time.monotonic()
    try:
        with BatchProgress(len(queue.items), file=ctx.progress_stream) as bar:
            for item in queue.items:
                results.append(process_file(item, ctx))
                bar.advance()
    except KeyboardInterrupt:
        # The summary covers what finished before Ctrl+C.
        _report_summary(results, start)
        raise
    _report_summary(results, start)
    return results


def _report_summary(results: list[FileResult], start: float) -> None:
    """Log the run summary: files, elapsed time, throughput, errors, bad quality.

    Bad quality is counted apart from errors: it does not affect the exit code.
    """
    elapsed = time.monotonic() - start
    files = len(results)
    errors = sum(1 for result in results if result.outcome in _FAILURE_OUTCOMES)
    bad_quality = sum(1 for result in results if result.status is ResultStatus.BAD)
    rate = files / elapsed * 60 if elapsed > 0 else 0.0
    screen_info(
        _logger,
        "raw2md: finished %d file(s) in %s (%.2f files/min), "
        "%d error(s), %d bad-quality",
        files,
        timedelta(seconds=round(elapsed)),
        rate,
        errors,
        bad_quality,
    )


def aggregate_exit_code(results: list[FileResult], *, single_file: bool) -> ExitCode:
    """Map per-file outcomes to the process exit code.

    A single file maps directly: 0 for ok, bad, or skipped; 4 for no result;
    5 for a failed LLM step. A batch with any failure gives 1. Nothing to do is
    success.
    """
    if single_file:
        if not results:
            return ExitCode.SUCCESS
        outcome = results[0].outcome
        if outcome is Outcome.LLM_ERROR:
            return ExitCode.LLM_ERROR
        if outcome is Outcome.NO_RESULT:
            return ExitCode.CONVERSION_ERROR
        return ExitCode.SUCCESS  # OK or SKIPPED
    if any(result.outcome in _FAILURE_OUTCOMES for result in results):
        return ExitCode.PARTIAL_BATCH_ERROR
    return ExitCode.SUCCESS


def _provider_for(
    model_key: str, model: ModelConfig, cache: dict[str, Provider]
) -> Provider:
    """Return the provider for `model_key`, reusing one instance per key in a run.

    Operations on one model share its rpm throttle; separate instances would
    each start unthrottled.
    """
    provider = cache.get(model_key)
    if provider is None:
        provider = build_provider(model)
        cache[model_key] = provider
    return provider


@dataclass(frozen=True)
class _ResolvedModel:
    model: ModelConfig
    provider: Provider
    prompt: str


def _resolve_model(
    operation: str,
    model_key: str,
    providers: dict[str, Provider],
    run_settings: _RunSettings,
    *,
    vision_reason: str | None = None,
) -> _ResolvedModel:
    """Look up the model, provider, and prompt of one LLM operation.

    `operation` names the operation in errors and its section of prompts.yaml.
    A `vision_reason` requires a vision provider and ends the error when it
    has none; the CLI allow-list check does not cover capability.
    """
    if run_settings.settings_error is not None:
        raise _LlmUnavailableError(f"settings.json: {run_settings.settings_error}")
    model = run_settings.settings.models.get(model_key)
    if model is None:
        raise _LlmUnavailableError(
            f"{operation} model '{model_key}' is not defined in settings.json"
        )
    provider = _provider_for(model_key, model, providers)
    if vision_reason is not None and not provider.supports_vision:
        raise _LlmUnavailableError(
            f"{operation} model '{model_key}' has no vision; {vision_reason}"
        )
    availability = provider.available()
    if not availability.ok:
        raise _LlmUnavailableError(
            f"{operation} model '{model_key}': {availability.reason}"
        )
    if run_settings.prompts_error is not None:
        raise _LlmUnavailableError(f"prompts.yaml: {run_settings.prompts_error}")
    # A requested operation implies `requests_llm`, which loaded the prompts.
    assert run_settings.prompts is not None
    prompt = resolve_prompt(run_settings.prompts, operation, model_key)
    return _ResolvedModel(model, provider, prompt)


def _resolve_post(
    config: RunConfig, providers: dict[str, Provider], run_settings: _RunSettings
) -> PostOperation | None:
    """Build the post-processing operation, or None when `--llm-post` is off."""
    model_key = config.llm_post
    if model_key is None:
        return None
    resolved = _resolve_model("post", model_key, providers, run_settings)
    return PostOperation(
        provider=resolved.provider, prompt=resolved.prompt, model_key=model_key
    )


def _resolve_inspection(
    config: RunConfig, providers: dict[str, Provider], run_settings: _RunSettings
) -> InspectOperation | None:
    """Build the inspection operation, or None when `--llm-inspection` is off."""
    model_key = config.llm_inspection
    if model_key is None:
        return None
    resolved = _resolve_model(
        "inspection",
        model_key,
        providers,
        run_settings,
        vision_reason="inspection needs an API model",
    )
    model = resolved.model
    # The byte ceiling comes from the provider, so the planner cuts against the
    # limit its size guard enforces.
    return InspectOperation(
        provider=resolved.provider,
        prompt=resolved.prompt,
        model_key=model_key,
        token_budget=chunk_budget(model.tpm),
        tpm=model.tpm,
        pages_per_request=model.pages_per_request or DEFAULT_PAGES_PER_REQUEST,
        max_request_bytes=resolved.provider.request_byte_limit,
        latex_fix=config.llm_latex_fix,
    )


def _resolve_ocr(
    config: RunConfig, providers: dict[str, Provider], run_settings: _RunSettings
) -> OcrOperation | None:
    """Build the LLM OCR operation, or None when `--engine` names no model."""
    model_key = config.llm_ocr
    if model_key is None:
        return None
    resolved = _resolve_model(
        "ocr",
        model_key,
        providers,
        run_settings,
        vision_reason="OCR needs an API model",
    )
    return OcrOperation(
        provider=resolved.provider, prompt=resolved.prompt, model_key=model_key
    )


def _start_context(
    config: RunConfig,
    registry: EngineRegistry | None,
    log_stream: TextIO | None,
    run_settings: _RunSettings,
    *,
    resume: bool,
) -> RunContext | None:
    """Resolve the LLM operations and the engines into the run context.

    None means the run cannot start, and the cause is logged. The default
    registry is built only when none is given, and only it needs a temp root.
    """
    settings = run_settings.settings
    temp_root: Path | None = None
    try:
        providers: dict[str, Provider] = {}
        post = _resolve_post(config, providers, run_settings)
        inspection = _resolve_inspection(config, providers, run_settings)
        ocr = _resolve_ocr(config, providers, run_settings)
        if registry is None:
            temp_root = select_temp_root()
            registry = build_default_registry(
                config,
                temp_root,
                log_stream,
                recognition_batch_size=settings.marker_recognition_batch_size,
            )
    except (TempPathError, _LlmUnavailableError) as exc:
        _logger.error("%s", exc)  # noqa: TRY400 -- expected error; no traceback wanted here
        return None
    _report_unavailable(registry)
    return RunContext(
        config=config,
        registry=registry,
        log_stream=log_stream,
        resume=resume,
        post=post,
        inspection=inspection,
        ocr=ocr,
        temp_root=temp_root,
        witness_min=(
            DEFAULT_WITNESS_MIN
            if settings.cleaning_witness_min is None
            else settings.cleaning_witness_min
        ),
        keywords=run_settings.keywords,
    )


def build_default_registry(
    config: RunConfig,
    temp_root: Path,
    log_stream: TextIO | None,
    *,
    recognition_batch_size: int | None = None,
) -> EngineRegistry:
    """Build the pdf/docx/djvu registry sharing one marker model."""
    marker = MarkerEngine(
        temp_root,
        cuda=config.cuda,
        log_stream=log_stream,
        recognition_batch_size=recognition_batch_size,
    )
    pandoc = PandocEngine()
    djvu = DjvuEngine(marker, temp_root)
    return EngineRegistry([marker, pandoc, djvu])


def _report_unavailable(registry: EngineRegistry) -> None:
    """Log a startup note for each missing engine; its formats are skipped."""
    for engine in registry.unavailable():
        formats = ", ".join(sorted(engine.extensions))
        _logger.warning(
            "engine for %s is unavailable; those files will be skipped", formats
        )


def _absolutize(config: RunConfig) -> RunConfig:
    """Make input and output paths absolute so a resume is cwd-independent.

    `absolute()`, not `resolve()`, keeps symlinks.
    """
    output_dir = config.output_dir
    return replace(
        config,
        input_path=config.input_path.absolute(),
        output_dir=None if output_dir is None else output_dir.absolute(),
    )


def _normalize_output_dir(config: RunConfig) -> RunConfig:
    """Fold an output dir that points at the input's own folder into in-place.

    In place, an md input takes the `_cleaned` name instead of overwriting its
    own source.
    """
    if config.output_dir is None:
        return config
    base = config.input_path
    base = base.parent if base.is_file() else base
    try:
        in_place = config.output_dir.resolve() == base.resolve()
    except OSError:
        in_place = False
    return replace(config, output_dir=None) if in_place else config


def _init_logging(config: RunConfig | None, settings: Settings | None) -> TextIO | None:
    """Configure logging, resolving file logging via `resolve_log_file`.

    `config` None, before a resume reads its parameters, gives a console-only
    logger, so lock and queue errors still surface.
    """
    if config is None:
        return setup_logging(False)
    assert settings is not None
    return setup_logging(resolve_log_file(config.log_file, settings))
