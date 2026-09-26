"""Per-file pipeline: convert one queued file into a result.

Stages: conversion, cleaning, quality evaluation, then inspection and
post-processing when requested. An `md` input is re-cleaned, not converted.
Under `--engine <model>` a pdf or djvu is recognized from page rasters instead
of through its engine.

`process_file` is the per-file isolation boundary: any failure, typed or
not, leaves that file without a result, removes its `in_progress` stub, and
lets the batch continue.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from collections.abc import Generator, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import TextIO
from urllib.parse import unquote

from raw2md.cleaner import CleanOptions, clean_with_report
from raw2md.cleaning import DEFAULT_WITNESS_MIN, Finding
from raw2md.config import RunConfig
from raw2md.engines import (
    ConversionError,
    ConvertOptions,
    EngineNotFoundError,
    EngineRegistry,
    EngineUnavailableError,
    check_source,
)
from raw2md.header import (
    LLM_FIELD_FAILED,
    ConversionMethod,
    HeaderParseError,
    ResultStatus,
    build_stub,
    format_partial_stage,
    from_yaml_block,
    render_result,
    strip_own_header,
)
from raw2md.keywords import Keywords, default_keywords
from raw2md.llm import DocumentTooLargeError, MediaPart, ProviderError
from raw2md.llm.acceptance import TouchedLines, accept
from raw2md.llm.inspection.common import (
    InspectionReplyError,
    InspectOperation,
    InspectResult,
)
from raw2md.llm.inspection.coordinator import inspect
from raw2md.llm.ocr import OcrOperation, OcrResult, recognize
from raw2md.llm.post.common import PostOperation
from raw2md.llm.post.coordinator import PostResult, post_process
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.links import HTML_IMG_RE, IMAGE_RE
from raw2md.mdtext.pages import page_mark_number, split_page_marks
from raw2md.media import (
    convert_emf_media,
    dedupe_repeated_images,
    drop_furniture_images,
    flatten_pandoc_media,
    is_rewritable_target,
    rewrite_media_links,
)
from raw2md.output import (
    OutputCollisionError,
    OutputTarget,
    debug_dir_for,
    encode_link_path,
    ensure_writable,
    write_md,
)
from raw2md.progress import STAGE_NAMES, FileProgress, capture_engine_output
from raw2md.quality.evaluator import Evaluation, evaluate
from raw2md.queue import (
    QueueItem,
    is_complete,
    is_unfinished,
    readiness_hash,
    write_in_progress_stub,
)
from raw2md.source_outline import SourceOutline
from raw2md.source_text import SourceText

_logger = logging.getLogger("raw2md")

_MD_EXTENSION = ".md"
_PDF_EXTENSION = ".pdf"
_DJVU_EXTENSION = ".djvu"

# Sources LLM OCR can recognize; docx and md convert normally.
_OCR_EXTENSIONS = frozenset({_PDF_EXTENSION, _DJVU_EXTENSION})

# Internal routes for cleaning; the header names the model instead.
_OCR_METHODS = {
    _PDF_EXTENSION: ConversionMethod.LLM_OCR,
    _DJVU_EXTENSION: ConversionMethod.DJVU_LLM_OCR,
}

# The header's `engine` for a route without an LLM; `source` already carries
# the djvu extension.
_ROUTE_ENGINE_NAMES = {
    ConversionMethod.MARKER: "marker",
    ConversionMethod.DJVU_MARKER: "marker",
    ConversionMethod.PANDOC: "pandoc",
    ConversionMethod.CLEAN: "clean",
}


def _header_engine(method: ConversionMethod, ocr_model: str | None) -> str:
    """The header's `engine` field: the model that ran, or the route's own name."""
    return ocr_model if ocr_model is not None else _ROUTE_ENGINE_NAMES[method]


class Outcome(Enum):
    """Per-file result class the orchestrator maps to an exit code."""

    OK = "ok"  # a result was written (status ok or bad), or already finished
    NO_RESULT = "no_result"  # nothing written: collision, broken source, failure
    LLM_ERROR = "llm_error"  # conversion succeeded but an LLM step failed
    SKIPPED = "skipped"  # not a failure: a queued source vanished before this run


@dataclass(frozen=True)
class FileResult:
    """Outcome of processing one queue item.

    `status` is the verdict when a result was written, else None. A failure
    carries no reason: it was logged where it was caught.
    """

    outcome: Outcome
    status: ResultStatus | None


@dataclass(frozen=True)
class RunContext:
    """Shared per-run state handed to each file.

    `progress_stream` None means stderr. `resume` skips files that already
    finished. The LLM operations are None when off. `temp_root` holds the
    per-file scratch folders and assembled PDFs; None for an injected registry.
    `witness_min` and `keywords` are the run's resolved settings.
    """

    config: RunConfig
    registry: EngineRegistry
    log_stream: TextIO | None = None
    progress_stream: TextIO | None = None
    resume: bool = False
    post: PostOperation | None = None
    inspection: InspectOperation | None = None
    ocr: OcrOperation | None = None
    temp_root: Path | None = None
    witness_min: int = DEFAULT_WITNESS_MIN
    keywords: Keywords = field(default_factory=default_keywords)


@dataclass(frozen=True)
class _Conversion:
    """A route's body and the facts about its source that later stages weigh.

    `ocr_model` gates the cleaning rules for a recognized body and the hint
    that recommends recognition. `source_pdf` is the pdf the route assembled
    and kept, for inspection; the route owns its lifetime.
    """

    body: str
    method: ConversionMethod
    ocr_model: str | None
    source_hash: str
    source_pages: int | None
    source_pdf: Path | None
    image_base: Path
    disable_image_extraction: bool
    source_text: SourceText
    outline: SourceOutline


@dataclass(frozen=True)
class _EvaluationContext:
    """The inputs every evaluation of one file shares.

    The first evaluation leaves the math and body-line bases None; every
    re-evaluation after it carries them, and the inspection coverage once
    inspection ran, so lost coverage keeps deciding.
    """

    source_pages: int | None
    base_dir: Path
    source_text: SourceText
    source_outline: SourceOutline
    cleaning_findings: tuple[Finding, ...]
    keywords: Keywords
    math_spans_before: int | None = None
    cleaning_body_lines: int | None = None
    inspection_chunks: int | None = None
    inspection_chunks_done: int | None = None

    def evaluate(self, body: str) -> Evaluation:
        return evaluate(
            body,
            source_pages=self.source_pages,
            base_dir=self.base_dir,
            source_text=self.source_text,
            source_outline=self.source_outline,
            math_spans_before=self.math_spans_before,
            cleaning_findings=self.cleaning_findings,
            cleaning_body_lines=self.cleaning_body_lines,
            inspection_chunks=self.inspection_chunks,
            inspection_chunks_done=self.inspection_chunks_done,
            keywords=self.keywords,
        )


@dataclass(frozen=True)
class _InspectionPass:
    """What the inspection stage left for the rest of the file.

    `header_field` is the model key whenever the pass ran, even partly;
    `failed` when it could not run; None when it does not apply (docx, md).
    `touched` feeds acceptance. `chunks` and `chunks_done` feed the coverage
    check; None when the pass was not chunked.
    """

    body: str
    header_field: str | None
    outcome: Outcome
    changed: bool = False
    touched: TouchedLines = field(default_factory=TouchedLines)
    chunks: int | None = None
    chunks_done: int | None = None

    @property
    def lost_coverage(self) -> bool:
        return (
            self.chunks is not None
            and self.chunks_done is not None
            and self.chunks_done < self.chunks
        )


def process_file(item: QueueItem, ctx: RunContext) -> FileResult:
    """Run one file through the pipeline and return its outcome.

    The one sanctioned broad catch: an unforeseen error is logged with its
    traceback (file only), the stub is dropped, and the file gets no result.
    Ctrl+C still stops the run: `KeyboardInterrupt` is not an `Exception`.
    """
    target = item.output_target(ctx.config.output_dir)
    try:
        return _dispatch(item, target, ctx)
    except Exception:
        _logger.exception("failed %s: unexpected error", item.source.name)
        _discard_stub_on_error(target)
        return FileResult(Outcome.NO_RESULT, None)


def _dispatch(item: QueueItem, target: OutputTarget, ctx: RunContext) -> FileResult:
    """Route one file to its md, OCR, or engine handler."""
    source = item.source
    if not source.exists():
        # Removed since the queue was saved; not a failure.
        _logger.warning("skip %s: source no longer exists", source.name)
        return FileResult(Outcome.SKIPPED, None)
    # A fresh run skips by name at queue build (--skip-existing), not here.
    if ctx.resume:
        done = _completed_status(source, target)
        if done is not None:
            return FileResult(Outcome.OK, done)
    stages = _route_stage_names(source, ctx)
    with FileProgress(source.name, stages, file=ctx.progress_stream) as bar:
        suffix = source.suffix.lower()
        if suffix == _MD_EXTENSION:
            return _process_md(item, target, ctx, bar)
        if ctx.ocr is not None and suffix in _OCR_EXTENSIONS:
            return _process_ocr(item, target, ctx, bar)
        return _process_engine(item, target, ctx, bar)


def _route_stage_names(source: Path, ctx: RunContext) -> tuple[str, ...]:
    """The named stages this file's route will run, in order.

    Inspection applies to a pdf or djvu only, as in `_build_inspection_source`;
    post applies to any source.
    """
    stages = list(STAGE_NAMES[:3])
    if ctx.inspection is not None and source.suffix.lower() in _OCR_EXTENSIONS:
        stages.append(STAGE_NAMES[3])  # inspection
    if ctx.post is not None:
        stages.append(STAGE_NAMES[4])  # post-processing
    return tuple(stages)


def _completed_status(source: Path, target: OutputTarget) -> ResultStatus | None:
    """Status of an existing finished result for `source`, or None if not done."""
    if not is_complete(source, target):
        return None
    try:
        header = from_yaml_block(target.md_path.read_text(encoding="utf-8"))
    except (OSError, HeaderParseError):
        return None
    return header.status if header is not None else None


def _clear_targets(
    item: QueueItem, target: OutputTarget, ctx: RunContext, source_hash: str
) -> FileResult | None:
    """Clear the result name; return a NO_RESULT when it must not be taken.

    Called only after the source is validated, so an existing result is not
    dropped for a file that then fails early. The `--debug` folder is cleared
    only while the flag is on.
    """
    debug_dir = debug_dir_for(target) if ctx.config.debug else None
    if ctx.resume and is_unfinished(target, source_hash):
        _logger.info(
            "redoing %s: left in progress by an interrupted run", item.source.name
        )
    try:
        ensure_writable(target, protect=item.source, extra=debug_dir)
    except OutputCollisionError as exc:
        _logger.error("skip %s: %s", item.source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return FileResult(Outcome.NO_RESULT, None)
    return None


def _process_engine(
    item: QueueItem, target: OutputTarget, ctx: RunContext, bar: FileProgress
) -> FileResult:
    """Convert a pdf/docx/djvu source through its engine and finish the pipeline."""
    source = item.source
    if ctx.ocr is not None:
        _logger.info(
            "OCR not applicable to %s (not an image source); converting normally",
            source.name,
        )
    try:
        engine = ctx.registry.select(source)
    except (EngineUnavailableError, EngineNotFoundError) as exc:
        # An ERROR like any other lost result; the startup note is a WARNING.
        _logger.error("skip %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return FileResult(Outcome.NO_RESULT, None)

    try:
        source_hash = readiness_hash(source)
        # Before the result name is cleared: a rerun over a broken source keeps
        # the previous result.
        check_source(source)
    except OSError as exc:
        _logger.error("failed %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return FileResult(Outcome.NO_RESULT, None)
    except ConversionError as exc:
        _logger.error("failed %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return FileResult(Outcome.NO_RESULT, None)

    refusal = _clear_targets(item, target, ctx, source_hash)
    if refusal is not None:
        return refusal

    write_in_progress_stub(
        target,
        source_name=source.name,
        engine=_header_engine(engine.method, None),
        source_hash=source_hash,
    )

    bar.update_stage(STAGE_NAMES[0])  # conversion
    # Held across `_finish`: inspection reads what the engine leaves there.
    with _scratch_dir(ctx) as scratch_dir:
        options = ConvertOptions(
            extract_media=ctx.config.extract_images,
            on_phase=bar.set_phase,
            mark_pages=ctx.inspection is not None,
            scratch_dir=scratch_dir,
        )
        # Engine output stays out of the log; this pair stands for it.
        _logger.info("converting %s via %s", source.name, engine.method.value)
        try:
            with capture_engine_output(ctx.log_stream):
                result = engine.convert(source, target.media_dir, options)
        except ConversionError as exc:
            _logger.error("failed %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
            _discard_result(target)
            return FileResult(Outcome.NO_RESULT, None)
        _logger.info("converted %s", source.name)

        body, media = drop_furniture_images(target.media_dir, result.media, result.body)
        body, media = dedupe_repeated_images(source, target.media_dir, media, body)
        media = flatten_pandoc_media(target.media_dir, media)
        body, media = convert_emf_media(target.media_dir, media, body)
        body = rewrite_media_links(body, target, media)
        conversion = _Conversion(
            body=body,
            method=engine.method,
            ocr_model=None,
            source_hash=source_hash,
            source_pages=result.source_pages,
            source_pdf=result.source_pdf,
            image_base=target.md_path.parent,
            disable_image_extraction=not ctx.config.extract_images,
            source_text=SourceText.from_source(source),
            outline=SourceOutline.from_source(source),
        )
        return _finish(item, target, ctx, bar, conversion)


@contextmanager
def _scratch_dir(ctx: RunContext) -> Iterator[Path | None]:
    """Yield the per-file scratch folder for the engine, or None when unwanted.

    Offered only when inspection runs: an assembled scan runs to hundreds of
    megabytes. Cleanup errors are ignored: the result is already written.
    """
    if ctx.inspection is None or ctx.temp_root is None:
        yield None
        return
    ctx.temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="raw2md_source_", dir=ctx.temp_root, ignore_cleanup_errors=True
    ) as tmp:
        yield Path(tmp)


def _process_md(
    item: QueueItem, target: OutputTarget, ctx: RunContext, bar: FileProgress
) -> FileResult:
    """Re-clean a md input: strip a raw2md header, then clean and evaluate."""
    source = item.source
    if ctx.ocr is not None:
        _logger.info(
            "OCR not applicable to %s (not an image source); cleaning normally",
            source.name,
        )
    try:
        text = source.read_text(encoding="utf-8")
        source_hash = readiness_hash(source)
    except (OSError, UnicodeDecodeError) as exc:
        _logger.error("failed %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return FileResult(Outcome.NO_RESULT, None)

    refusal = _clear_targets(item, target, ctx, source_hash)
    if refusal is not None:
        return refusal

    write_in_progress_stub(
        target,
        source_name=source.name,
        engine=_header_engine(ConversionMethod.CLEAN, None),
        source_hash=source_hash,
    )

    bar.update_stage(STAGE_NAMES[0])  # conversion: the header strip
    _, body = strip_own_header(text)
    # With another output dir, no media is copied: links point back at the
    # source folder.
    result_dir = target.md_path.parent
    if result_dir.resolve() != source.parent.resolve():
        body = _redirect_md_links(body, source.parent, result_dir)
    conversion = _Conversion(
        body=body,
        method=ConversionMethod.CLEAN,
        ocr_model=None,
        source_hash=source_hash,
        source_pages=None,
        source_pdf=None,
        image_base=result_dir,
        disable_image_extraction=not ctx.config.extract_images,
        source_text=SourceText.empty(),
        outline=SourceOutline.empty(),
    )
    return _finish(item, target, ctx, bar, conversion)


def _process_ocr(
    item: QueueItem, target: OutputTarget, ctx: RunContext, bar: FileProgress
) -> FileResult:
    """Recognize a pdf/djvu source via the LLM, replacing the native engine.

    No media is extracted. There is no fallback, so any failure leaves no
    result: a provider error is an LLM error (exit 5), an oversize page or a
    failed djvu assembly a conversion error (exit 4).
    """
    source = item.source
    op = ctx.ocr
    assert op is not None  # guarded by process_file
    method = _OCR_METHODS[source.suffix.lower()]
    try:
        source_hash = readiness_hash(source)
        # As in `_process_engine`, before any page is rendered or sent.
        check_source(source)
    except OSError as exc:
        _logger.error("failed %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return FileResult(Outcome.NO_RESULT, None)
    except ConversionError as exc:
        _logger.error("failed %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return FileResult(Outcome.NO_RESULT, None)

    refusal = _clear_targets(item, target, ctx, source_hash)
    if refusal is not None:
        return refusal

    if not ctx.config.extract_images:
        _logger.info(
            "OCR ignores --disable-image-extraction for %s (no media extracted)",
            source.name,
        )

    write_in_progress_stub(
        target,
        source_name=source.name,
        engine=_header_engine(method, op.model_key),
        source_hash=source_hash,
    )

    bar.update_stage(STAGE_NAMES[0])  # conversion (recognition)
    # Opened here: a failed recognition never reaches `_finish`, and its paid
    # replies are the only record of the run.
    ocr_trace = _open_ocr_trace(ctx, target)
    try:
        ocr_result = _recognize(source, ctx, op, ocr_trace)
    except DocumentTooLargeError as exc:
        _logger.error("failed %s: OCR page too large: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        _discard_result(target)
        return FileResult(Outcome.NO_RESULT, None)
    except ProviderError as exc:
        _logger.error("OCR failed for %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        _discard_result(target)
        return FileResult(Outcome.LLM_ERROR, None)
    except ConversionError as exc:
        _logger.error("failed %s: %s", source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        _discard_result(target)
        return FileResult(Outcome.NO_RESULT, None)

    conversion = _Conversion(
        body=ocr_result.body,
        method=method,
        ocr_model=op.model_key,
        source_hash=source_hash,
        source_pages=ocr_result.pages,
        # The rendering pdf is gone; inspection assembles its own.
        source_pdf=None,
        image_base=target.md_path.parent,
        disable_image_extraction=False,
        # A born-digital pdf may be recognized too; its text still witnesses.
        source_text=SourceText.from_source(source),
        outline=SourceOutline.from_source(source),
    )
    return _finish(item, target, ctx, bar, conversion)


def _open_ocr_trace(ctx: RunContext, target: OutputTarget) -> LlmTrace | None:
    """The `--debug` recorder for the OCR route, or None when the flag is off.

    The folder is created with the first entry: an empty one left by a failure
    before any request would block the next run.
    """
    if not ctx.config.debug:
        return None
    return LlmTrace(debug_dir_for(target))


def _recognize(
    source: Path, ctx: RunContext, op: OcrOperation, trace: LlmTrace | None = None
) -> OcrResult:
    """Render the source's pages and transcribe them through the LLM.

    The result's `pages` is the density denominator of this route. A render
    or djvu assembly failure surfaces as `ConversionError`.
    """
    with _render_ocr_pages(source, ctx) as pages:
        result = recognize(
            pages, op, mark_pages=ctx.inspection is not None, trace=trace
        )
    _logger.info("OCR %s: %d pages recognized", source.name, result.pages)
    if result.empty_replies:
        # Only a lost page is a hole in the result.
        log = _logger.warning if result.lost_pages else _logger.info
        log(
            "OCR %s: %d empty replies, %d recovered on retry, %d pages lost",
            source.name,
            result.empty_replies,
            result.recovered,
            result.lost_pages,
        )
    return result


@contextmanager
def _render_ocr_pages(source: Path, ctx: RunContext) -> Iterator[Iterator[bytes]]:
    """Yield a page-raster iterator for OCR; assemble a djvu source first.

    The iterator holds the document open: consume it inside the `with` block.
    """
    from raw2md.engines import pymupdf

    if source.suffix.lower() == _PDF_EXTENSION:
        with closing(_safe_render(pymupdf.render_pages(source), source)) as pages:
            yield pages
        return
    if ctx.temp_root is None:
        raise ConversionError("no temp path available to assemble the djvu source")
    from raw2md.engines.djvu import djvu_to_pdf

    ctx.temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="raw2md_ocr_", dir=ctx.temp_root) as tmp:
        pdf_path = Path(tmp) / "ocr.pdf"
        djvu_to_pdf(source, pdf_path, ctx.temp_root)
        with closing(_safe_render(pymupdf.render_pages(pdf_path), source)) as pages:
            yield pages


def _safe_render(pages: Iterator[bytes], source: Path) -> Generator[bytes, None, None]:
    """Yield page rasters, mapping a PyMuPDF render failure to ConversionError.

    The failure surfaces lazily while pages are pulled, so it is caught around
    the iteration only; provider errors pass through.
    """
    try:
        yield from pages
    except (RuntimeError, OSError) as exc:
        raise ConversionError(f"could not render {source.name}: {exc}") from exc


def _finish(
    item: QueueItem,
    target: OutputTarget,
    ctx: RunContext,
    bar: FileProgress,
    conversion: _Conversion,
) -> FileResult:
    """Clean, evaluate, run the LLM stages, then write the result (all routes).

    Under `--debug` each stage that runs saves a snapshot of the body.
    """
    config = ctx.config
    debug_dir = _open_debug_dir(ctx, target)
    trace = LlmTrace(debug_dir) if debug_dir is not None else None
    _save_debug_stage(debug_dir, "conversion", conversion.body)
    bar.update_stage(STAGE_NAMES[1])  # cleaning
    clean_options = CleanOptions(
        base_dir=conversion.image_base,
        disable_image_extraction=conversion.disable_image_extraction,
        method=conversion.method,
        llm_ocr=conversion.ocr_model is not None,
        source_text=conversion.source_text,
        outline=conversion.outline,
        witness_min=ctx.witness_min,
        keywords=ctx.keywords,
    )
    # Page marks ride through cleaning and come out right after it: later
    # stages see the unmarked body, and the page map indexes it.
    cleaning = clean_with_report(conversion.body, clean_options)
    cleaned, pages = split_page_marks(cleaning.body)
    findings = _report_cleaning(item.source.name, cleaning.body, cleaning.findings)
    _save_debug_stage(debug_dir, "cleaning", cleaned)
    bar.update_stage(STAGE_NAMES[2])  # quality evaluation
    evaluation_context = _EvaluationContext(
        source_pages=conversion.source_pages,
        base_dir=conversion.image_base,
        source_text=conversion.source_text,
        source_outline=conversion.outline,
        cleaning_findings=findings,
        keywords=clean_options.keywords,
    )
    evaluation = evaluation_context.evaluate(cleaned)
    evaluation_context = replace(
        evaluation_context,
        # The base for a re-evaluation to catch math spans lost by LLM edits.
        math_spans_before=int(evaluation.metrics["math_spans"]),
        # The cleaning report's thresholds stay scaled for the body it measured.
        cleaning_body_lines=int(evaluation.metrics["body_lines"]),
    )

    # Header field values: None (`none`), a model key, `failed`, or post's
    # `partial`.
    inspection_field: str | None = None
    post_field: str | None = None
    outcome = Outcome.OK

    # Inspection fixes content first; post then repairs the markup.
    if ctx.inspection is not None:
        inspection = _run_inspection(
            cleaned,
            pages,
            ctx,
            bar,
            item,
            conversion.source_pdf,
            conversion.source_text,
            trace,
        )
        cleaned = inspection.body
        inspection_field = inspection.header_field
        inspected = inspection.changed
        outcome = _worse(outcome, inspection.outcome)
        # None when inspection did not apply; snapshots follow the field.
        if inspection_field is not None:
            _save_debug_stage(debug_dir, "inspection", cleaned)
            cleaned, accepted = _run_acceptance(cleaned, inspection.touched, item)
            _save_debug_stage(debug_dir, "acceptance", cleaned)
            inspected = inspected or accepted
        evaluation_context = replace(
            evaluation_context,
            inspection_chunks=inspection.chunks,
            inspection_chunks_done=inspection.chunks_done,
        )
        # Lost coverage needs a re-evaluation even with nothing applied.
        if inspected or inspection.lost_coverage:
            # Before post, whose failure falls back to this evaluation.
            evaluation = evaluation_context.evaluate(cleaned)

    # Always asked when requested: post picks its own zones. An idle post
    # makes no call and still records its model.
    if ctx.post is not None:
        cleaned, evaluation, post_field, p_outcome = _run_post(
            cleaned, evaluation, evaluation_context, ctx, bar, item, trace
        )
        outcome = _worse(outcome, p_outcome)
        _save_debug_stage(debug_dir, "post", cleaned)

    ocr_applicable = item.source.suffix.lower() in _OCR_EXTENSIONS
    _warn_quality_verdict(
        item.source.name,
        evaluation,
        recommend_llm_ocr=ocr_applicable and conversion.ocr_model is None,
        recommend_llm_post=ctx.post is None,
    )

    header = build_stub(
        item.source.name,
        engine=_header_engine(conversion.method, conversion.ocr_model),
        inspection=inspection_field,
        post=post_field,
        source_hash=conversion.source_hash,
    )
    header.status = evaluation.status
    header.issues = evaluation.issues
    write_md(target, render_result(header, cleaned, emit_yaml=config.yaml_header))
    return FileResult(outcome, evaluation.status)


def _open_debug_dir(ctx: RunContext, target: OutputTarget) -> Path | None:
    """Create and return this file's debug folder, or None when --debug is off.

    `_clear_targets` already removed an old one.
    """
    if not ctx.config.debug:
        return None
    debug_dir = debug_dir_for(target)
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def _report_cleaning(
    source_name: str, cleaned: str, findings: tuple[Finding, ...]
) -> tuple[Finding, ...]:
    """Log the cleaning stage's report and address it to the body that survives.

    Counts go to INFO, each finding to DEBUG. Line numbers move to the body
    without page marks, which every later stage reads.
    """
    if not findings:
        return ()
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    _logger.info(
        "cleaning %s: %d defects left for a later stage (%s)",
        source_name,
        len(findings),
        ", ".join(f"{kind} {count}" for kind, count in sorted(counts.items())),
    )
    numbers = _numbering_without_page_marks(cleaned)
    moved = tuple(replace(f, line=numbers[f.line]) for f in findings)
    for finding in moved:
        _logger.debug("cleaning %s: %s", source_name, finding.describe())
    return moved


def _numbering_without_page_marks(cleaned: str) -> dict[int, int]:
    """Line number in `cleaned` -> its number once the page marks are removed.

    A mark's line maps to the line below it.
    """
    numbers: dict[int, int] = {}
    removed = 0
    for index, line in enumerate(cleaned.split("\n"), start=1):
        if page_mark_number(line) is not None:
            removed += 1
        numbers[index] = index - removed
    return numbers


def _save_debug_stage(debug_dir: Path | None, stage: str, body: str) -> None:
    """Write one stage's body snapshot under `--debug`; a no-op when it is off."""
    if debug_dir is None:
        return
    with (debug_dir / f"{stage}.md").open("w", encoding="utf-8", newline="") as f:
        f.write(body)


def _warn_quality_verdict(
    source_name: str,
    evaluation: Evaluation,
    *,
    recommend_llm_ocr: bool,
    recommend_llm_post: bool,
) -> None:
    """Surface the verdict, its defects, and the two repair hints.

    Defects are logged with the measured detail the header does not carry. An
    `ok` file with issues gets an INFO line, so its header `issues` has a
    match in the log. The repair hint waits for a `bad` verdict.
    """
    if evaluation.status is ResultStatus.BAD:
        _logger.warning(
            "quality bad for %s: %s", source_name, ", ".join(evaluation.defect_report)
        )
    elif evaluation.issues:
        _logger.info(
            "quality ok for %s, below threshold: %s",
            source_name,
            ", ".join(evaluation.defect_report),
        )
    # Repairing the markup of badly recognized text is wasted.
    if evaluation.recognition_failure and recommend_llm_ocr:
        _logger.warning(
            "recognition failure suspected for %s; consider --engine", source_name
        )
    elif (
        evaluation.status is ResultStatus.BAD
        and evaluation.repairable
        and recommend_llm_post
    ):
        _logger.warning(
            "formatting defects look repairable for %s; consider --llm-post",
            source_name,
        )


def _worse(current: Outcome, other: Outcome) -> Outcome:
    """Combine two LLM-phase outcomes: an LLM error wins over OK."""
    if Outcome.LLM_ERROR in (current, other):
        return Outcome.LLM_ERROR
    return current


def _run_inspection(
    cleaned: str,
    pages: tuple[tuple[int, int], ...],
    ctx: RunContext,
    bar: FileProgress,
    item: QueueItem,
    source_pdf: Path | None,
    source_text: SourceText,
    trace: LlmTrace | None = None,
) -> _InspectionPass:
    """Inspect the source against the md and apply its edits.

    `pages` maps edit addresses to source pages; empty means one page. A pass
    that could not run records `failed`: OK for a source build failure or an
    oversize request, LLM_ERROR for a provider error or an unusable reply.
    """
    op = ctx.inspection
    assert op is not None  # guarded by the caller
    try:
        source_part = _build_inspection_source(item.source, ctx, source_pdf)
    except _InspectionSourceBuildError as exc:
        # Counted in the bar for a pdf/djvu, so marked even when it cannot run.
        bar.update_stage(STAGE_NAMES[3])  # inspection
        _logger.warning("inspection skipped for %s: %s", item.source.name, exc)
        return _InspectionPass(cleaned, LLM_FIELD_FAILED, Outcome.OK)
    if source_part is None:
        _logger.info("inspection skipped for %s: no image source", item.source.name)
        return _InspectionPass(cleaned, None, Outcome.OK)
    bar.update_stage(STAGE_NAMES[3])  # inspection

    def on_chunk(number: int, total: int) -> None:
        bar.set_phase(f"chunk {number}/{total}")

    try:
        result = inspect(cleaned, source_part, op, pages, source_text, trace, on_chunk)
    except DocumentTooLargeError as exc:
        _logger.warning("skip inspection for %s: %s", item.source.name, exc)
        return _InspectionPass(cleaned, LLM_FIELD_FAILED, Outcome.OK)
    except InspectionReplyError as exc:
        _logger.error("inspection reply unusable for %s: %s", item.source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return _InspectionPass(cleaned, LLM_FIELD_FAILED, Outcome.LLM_ERROR)
    except ProviderError as exc:
        _logger.error("inspection failed for %s: %s", item.source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return _InspectionPass(cleaned, LLM_FIELD_FAILED, Outcome.LLM_ERROR)
    _logger.info(
        "inspection %s: %d applied, %d skipped, %d rejected, %d format flags reported",
        item.source.name,
        result.applied,
        result.skipped,
        result.rejected,
        result.format_flags,
    )
    outcome = Outcome.OK
    if result.failure is not None or result.skipped_chunks:
        outcome = _partial_outcome(result, item.source.name)
    # 0 chunks: one request, no plan to weigh coverage against.
    return _InspectionPass(
        result.body,
        op.model_key,
        outcome,
        changed=result.applied > 0,
        touched=result.touched,
        chunks=result.chunks or None,
        chunks_done=result.chunks - result.skipped_chunks if result.chunks else None,
    )


def _run_acceptance(
    cleaned: str, touched: TouchedLines, item: QueueItem
) -> tuple[str, bool]:
    """Re-read the lines inspection wrote; return the body and whether it moved.

    Runs wherever inspection ran, even with nothing applied, so its `--debug`
    snapshot follows inspection's.
    """
    result = accept(cleaned, touched)
    if result.stripped or result.flagged or result.mended:
        _logger.info(
            "acceptance %s: %d lines stripped, %d rows left off their table width, "
            "%d pipe blocks given a delimiter row",
            item.source.name,
            result.stripped,
            result.flagged,
            result.mended,
        )
    return result.body, result.changed


def _partial_outcome(result: InspectResult, source_name: str) -> Outcome:
    """The run outcome a partly completed inspection carries, logged at its level.

    A provider failure stays an LLM error (ERROR, exit 5) even if it cost one
    chunk. Chunks the model declined or skipped for size only lose coverage (a
    warning). This is the one line per file; retries log at INFO.
    """
    if result.failure is None:
        _logger.warning(
            "inspection incomplete for %s: %d of %d chunks were not inspected in full",
            source_name,
            result.skipped_chunks,
            result.chunks,
        )
        return Outcome.OK
    _logger.error("inspection incomplete for %s: %s", source_name, result.failure)
    return Outcome.LLM_ERROR


class _InspectionSourceBuildError(Exception):
    """The source is image-bearing but its inspection PDF could not be built.

    Unlike None (not applicable, `none`), this records `failed`.
    """


def _build_inspection_source(
    source: Path, ctx: RunContext, source_pdf: Path | None
) -> MediaPart | None:
    """Build the source PDF MediaPart for inspection, or None to skip.

    A djvu reuses `source_pdf` when the route kept one and is assembled only
    otherwise: assembly is the costliest step of that route. docx and md get
    None.
    """
    suffix = source.suffix.lower()
    try:
        if suffix == _PDF_EXTENSION:
            return MediaPart(source.read_bytes(), "application/pdf")
        if suffix == _DJVU_EXTENSION:
            if source_pdf is not None:
                return MediaPart(source_pdf.read_bytes(), "application/pdf")
            if ctx.temp_root is None:
                raise _InspectionSourceBuildError("no temp path")

            from raw2md.engines.djvu import djvu_to_pdf_bytes

            return MediaPart(
                djvu_to_pdf_bytes(source, ctx.temp_root), "application/pdf"
            )
    except (ConversionError, OSError) as exc:
        raise _InspectionSourceBuildError(str(exc)) from exc
    return None


def _run_post(
    cleaned: str,
    evaluation: Evaluation,
    evaluation_context: _EvaluationContext,
    ctx: RunContext,
    bar: FileProgress,
    item: QueueItem,
    trace: LlmTrace | None = None,
) -> tuple[str, Evaluation, str | None, Outcome]:
    """Repair the damaged zones via the LLM and re-evaluate.

    Returns ``(body, evaluation, post_field, outcome)``. `post_field` is the
    model key, a `format_partial_stage` value, or `failed` when no zone came
    back; then the base body and its evaluation stay (OK for an oversize
    request, LLM_ERROR for a provider error).
    """
    op = ctx.post
    assert op is not None  # guarded by the caller
    bar.update_stage(STAGE_NAMES[4])  # post-processing
    try:
        result = post_process(cleaned, op, trace, evaluation_context.keywords)
    except DocumentTooLargeError as exc:
        _logger.warning("skip post for %s: %s", item.source.name, exc)
        return cleaned, evaluation, LLM_FIELD_FAILED, Outcome.OK
    except ProviderError as exc:
        _logger.error("post failed for %s: %s", item.source.name, exc)  # noqa: TRY400 -- expected error, no traceback
        return cleaned, evaluation, LLM_FIELD_FAILED, Outcome.LLM_ERROR
    _logger.info(
        "post %s: %d repaired, %d reverted (%d unchanged), %d hyphen joins kept, "
        "%d refused as words the document does not use, "
        "%d table rows repaired, %d refused, %d heading levels moved, %d refused, "
        "%d dropped by the ladder, %d letter-spaced runs closed, %d refused",
        item.source.name,
        result.repaired,
        result.reverted,
        result.unchanged,
        result.joins,
        result.refused_joins,
        result.repaired_rows,
        result.refused_rows,
        result.repaired_headings,
        result.refused_headings,
        result.vetoed_headings,
        result.repaired_runs,
        result.refused_runs,
    )
    field = op.model_key
    outcome = Outcome.OK
    if result.lost:
        field = format_partial_stage(result.planned - result.lost, result.planned)
        outcome = _partial_post_outcome(result, item.source.name)
    # Deterministic checks over the same body give the same verdict.
    if result.body == cleaned:
        return cleaned, evaluation, field, outcome
    return result.body, evaluation_context.evaluate(result.body), field, outcome


def _partial_post_outcome(result: PostResult, source_name: str) -> Outcome:
    """The run outcome a partly delivered post carries, logged at its level.

    A provider failure stays an LLM error (ERROR, exit 5) even if it cost one
    zone; zones lost only to oversize requests give a warning.
    """
    if result.failure is None:
        _logger.warning(
            "post incomplete for %s: %d of %d zones did not come back in full",
            source_name,
            result.lost,
            result.planned,
        )
        return Outcome.OK
    _logger.error(
        "post incomplete for %s: %d of %d zones did not come back in full: %s",
        source_name,
        result.lost,
        result.planned,
        result.failure,
    )
    return Outcome.LLM_ERROR


def _discard_result(target: OutputTarget) -> None:
    """Remove the in_progress stub and any partial media after a failed convert.

    Best-effort: it runs on a failing path, and raising here would abort the
    batch.
    """
    try:
        target.md_path.unlink(missing_ok=True)
    except OSError as exc:
        _logger.warning("could not remove stub %s: %s", target.md_path.name, exc)
    if target.media_dir.is_dir():
        shutil.rmtree(target.media_dir, ignore_errors=True)


def _discard_stub_on_error(target: OutputTarget) -> None:
    """Discard only our own in_progress stub when the broad guard fires.

    The failure may precede the stub, so a finished or foreign file stays.
    Under the run lock an `in_progress` result is this call's own stub.
    """
    try:
        header = from_yaml_block(target.md_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, HeaderParseError):
        # Not our stub.
        return
    if header is not None and header.status is ResultStatus.IN_PROGRESS:
        _discard_result(target)


def _redirect_md_links(body: str, source_dir: Path, result_dir: Path) -> str:
    """Re-point a md input's relative image links for a distinct output dir.

    The md route copies no media. Paths are computed without the filesystem,
    so a missing image is rewritten like an existing one.
    """
    result_base = result_dir.absolute()

    def redirected(link: str) -> str | None:
        """The link re-pointed at `source_dir`, or None to leave it alone."""
        # Decoded first: an encoded absolute path (`%2Ftmp%2Fa.png`) must
        # still read as non-local.
        decoded_link = unquote(link)
        if not _is_relative_local(decoded_link):
            return None
        absolute = (source_dir / decoded_link).absolute()
        try:
            # relpath has no pathlib equivalent: Path.relative_to cannot emit `..`.
            target = Path(os.path.relpath(absolute, result_base))
        except ValueError:
            # Windows has no relative path between two drives: the absolute
            # path is the only link that still reaches the image.
            target = absolute
        return encode_link_path(target.as_posix())

    def replace_markdown(match: re.Match[str]) -> str:
        alt, link = match.group(1), match.group(2)
        new_link = redirected(link)
        if new_link is None:
            return match.group(0)
        return f"![{alt}]({new_link})"

    # A pandoc result fed back in carries sized images as HTML tags.
    def replace_html_src(match: re.Match[str]) -> str:
        prefix, link, suffix = match.group(1), match.group(2), match.group(3)
        new_link = redirected(link)
        if new_link is None:
            return match.group(0)
        return f"{prefix}{new_link}{suffix}"

    body = IMAGE_RE.sub(replace_markdown, body)
    return HTML_IMG_RE.sub(replace_html_src, body)


def _is_relative_local(link: str) -> bool:
    """True when `link` is a relative local path (not a URL or an absolute path)."""
    if not is_rewritable_target(link):
        return False
    if link.startswith("/"):  # POSIX-absolute
        return False
    # Windows drive-absolute (`C:/...` or `C:\...`).
    return not (len(link) >= 2 and link[1] == ":" and link[0].isalpha())
