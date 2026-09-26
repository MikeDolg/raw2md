"""Run an inspection pass: one request, or one per chunk of whole pages.

A refused chunk is tried in halves and given up, and only a spent budget or a
refused access ends the pass. An unusable reply is retried once. The edits
collected go to `apply`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from raw2md.engines import pymupdf
from raw2md.llm.base import (
    MediaPart,
    Part,
    Provider,
    ProviderError,
    Reply,
    TextPart,
    run_answers_for,
    stops_sending,
)
from raw2md.llm.chunking import (
    Chunk,
    PageIndex,
    TokenPacer,
    estimate_tokens,
    halve,
    plan,
)
from raw2md.llm.inspection.addressing import (
    DisplayUnit,
    body_lines,
    display_units,
    numbered_lines,
)
from raw2md.llm.inspection.apply import Coverage, apply_edits
from raw2md.llm.inspection.common import (
    TRACE_OP,
    InspectionReplyError,
    InspectOperation,
    InspectResult,
    SemanticEdit,
)
from raw2md.llm.inspection.masking import masked_lines
from raw2md.llm.inspection.numbering import ChunkFrame, realigned
from raw2md.llm.inspection.reply import RESPONSE_SCHEMA, parse_edits
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.zones import segments
from raw2md.source_text import SourceText

_logger = logging.getLogger("raw2md")


@dataclass(frozen=True)
class _ChunkOutcome:
    """What one chunk produced: its edits, and how much of it was answered.

    `whole` means all of the chunk's text was answered, in one reply or in two
    halves; `answered` that at least one reply came back. `flags` are kept for
    the count alone.
    """

    semantic: list[SemanticEdit]
    flags: list[str]
    answered: bool
    whole: bool
    failure: Exception | None


def inspect(
    body: str,
    source_part: MediaPart,
    op: InspectOperation,
    pages: Sequence[tuple[int, int]] = (),
    source_text: SourceText | None = None,
    trace: LlmTrace | None = None,
    on_chunk: Callable[[int, int], None] | None = None,
) -> InspectResult:
    """Compare `source_part` against `body`, apply the model's edits, rebuild.

    `pages` pairs a body line index with its 1-based source page; an empty map
    addresses the body as one page. `on_chunk(number, total)` is called before
    each planned chunk's request, never for a single request. Provider errors
    and an unusable reply propagate, in a chunked pass only from the first
    chunk; past it the edits collected are applied and the result says how
    much of the source the pass saw.
    """
    lines = body_lines(body)
    protected = [p for _, p in segments(body)]
    index = PageIndex(pages, len(lines))
    units = display_units(lines, protected, index)
    masked = None if op.latex_fix else masked_lines(lines, protected)
    numbered = numbered_lines(lines if masked is None else masked.lines, index, units)
    chunks = plan(
        numbered,
        source_part.data,
        index,
        budget=op.token_budget,
        prompt_tokens=estimate_tokens(op.prompt),
        prompt_bytes=len(op.prompt.encode("utf-8")),
        pages_per_chunk=op.pages_per_request,
        max_bytes=op.max_request_bytes,
    )

    failure: Exception | None = None
    planned = skipped = 0
    if chunks is None:
        parts: list[Part] = [source_part, TextPart("\n".join(numbered))]
        semantic, flags = _request_edits(op, parts, trace=trace)
    else:
        planned = len(chunks)
        semantic, flags, failure, skipped = _inspect_chunks(
            numbered, lines, units, source_part, chunks, index, op, trace, on_chunk
        )
    return apply_edits(
        body,
        semantic,
        flags,
        index,
        units,
        masked,
        Coverage(failure, planned, skipped),
        source_text,
        op.latex_fix,
    )


def _inspect_chunks(
    numbered: list[str],
    lines: list[str],
    units: dict[int, DisplayUnit],
    source_part: MediaPart,
    chunks: list[Chunk],
    index: PageIndex,
    op: InspectOperation,
    trace: LlmTrace | None = None,
    on_chunk: Callable[[int, int], None] | None = None,
) -> tuple[list[SemanticEdit], list[str], Exception | None, int]:
    """Send one request per chunk and collect the edits of all of them.

    A spent budget or a refused access ends the pass, since it refuses every
    chunk left. Any other refusal gives up that chunk alone and the pass goes
    on. A first chunk that got no answer raises instead. Returns the edits, the
    refusal the run answers for, and the chunks left without a full pass.
    """
    pacer = TokenPacer(op.tpm)
    semantic: list[SemanticEdit] = []
    flags: list[str] = []
    judged: Exception | None = None
    skipped = 0
    total = len(chunks)
    for number, chunk in enumerate(chunks, start=1):
        if on_chunk is not None:
            on_chunk(number, total)
        outcome = _chunk_edits(
            numbered,
            source_part,
            ChunkFrame(chunk, lines, index, units),
            op,
            pacer,
            number,
            total,
            trace,
        )
        semantic.extend(outcome.semantic)
        flags.extend(outcome.flags)
        if outcome.whole:
            continue
        failure = outcome.failure
        assert failure is not None  # a chunk is incomplete only when refused
        if number == 1 and not outcome.answered:
            raise failure
        skipped += 1
        # The first such refusal started the loss; a later one repeats it.
        if judged is None and run_answers_for(failure):
            judged = failure
        if stops_sending(failure):
            left = total - number
            _logger.error(
                "inspection: chunk %d/%d refused on a spent budget or a "
                "refused access; ending the pass with the edits collected, "
                "%d of %d chunks left without a full pass: %s",
                number,
                total,
                skipped + left,
                total,
                failure,
            )
            return semantic, flags, failure, skipped + left
        # The caller reports the pass's own verdict once, so this stays at INFO.
        _logger.info(
            "inspection: chunk %d/%d left without a full pass, going on: %s",
            number,
            total,
            failure,
        )
    return semantic, flags, judged, skipped


def _chunk_edits(
    numbered: list[str],
    source_part: MediaPart,
    frame: ChunkFrame,
    op: InspectOperation,
    pacer: TokenPacer,
    number: int,
    total: int,
    trace: LlmTrace | None,
) -> _ChunkOutcome:
    """Ask for one chunk's edits, and for a refused chunk's two halves.

    Only an unusable reply is worth halving: the model often answers half the
    pages. A provider error comes back the same however the pages are cut.
    """
    what = f"chunk {number}/{total}"
    try:
        semantic, flags = _request_edits(
            op,
            _chunk_parts(numbered, source_part, frame.chunk, number, total),
            pacer=pacer,
            tokens=frame.chunk.tokens,
            what=what,
            trace=trace,
            frame=frame,
        )
    except (ProviderError, InspectionReplyError) as exc:
        halves = (
            halve(frame.chunk, frame.index, numbered)
            if isinstance(exc, InspectionReplyError)
            else None
        )
        if halves is None:
            return _ChunkOutcome([], [], answered=False, whole=False, failure=exc)
        _logger.info("inspection: %s refused, sending it as two halves: %s", what, exc)
        return _halved_edits(
            numbered, source_part, frame, halves, op, pacer, number, total, trace, exc
        )
    return _ChunkOutcome(semantic, flags, answered=True, whole=True, failure=None)


def _halved_edits(
    numbered: list[str],
    source_part: MediaPart,
    frame: ChunkFrame,
    halves: tuple[Chunk, Chunk],
    op: InspectOperation,
    pacer: TokenPacer,
    number: int,
    total: int,
    trace: LlmTrace | None,
    refusal: Exception,
) -> _ChunkOutcome:
    """Send both halves of a refused chunk and keep whatever they answer.

    A spent budget or a refused access on either half ends the halving and the
    pass.
    """
    semantic: list[SemanticEdit] = []
    flags: list[str] = []
    answered = 0
    failure: Exception = refusal
    for position, half in enumerate(halves, start=1):
        what = f"chunk {number}/{total} half {position}/2"
        try:
            half_semantic, half_flags = _request_edits(
                op,
                _chunk_parts(numbered, source_part, half, number, total),
                pacer=pacer,
                tokens=half.tokens,
                what=what,
                trace=trace,
                frame=replace(frame, chunk=half),
            )
        except (ProviderError, InspectionReplyError) as exc:
            failure = exc
            # The pass's own outcome is still the caller's to report.
            _logger.info("inspection: %s refused as well: %s", what, exc)
            if stops_sending(exc):
                break
            continue
        semantic.extend(half_semantic)
        flags.extend(half_flags)
        answered += 1
    whole = answered == len(halves)
    if whole:
        _logger.info("inspection: chunk %d/%d answered in halves", number, total)
    return _ChunkOutcome(
        semantic,
        flags,
        answered=answered > 0,
        whole=whole,
        failure=None if whole else failure,
    )


def _request_edits(
    op: InspectOperation,
    parts: list[Part],
    *,
    pacer: TokenPacer | None = None,
    tokens: int = 0,
    what: str = "request",
    trace: LlmTrace | None = None,
    frame: ChunkFrame | None = None,
) -> tuple[list[SemanticEdit], list[str]]:
    """Send one inspection request and parse its reply, retrying once on an
    unusable reply.

    An unusable reply is as often a one-off slip, so it is sent again unless
    `final` says a repeat would fail the same way. `frame`, given for a chunk,
    checks the reply's numbering (`realigned`). A single request escalates to
    WARNING when it gives up; a chunk stays at INFO, since its caller still
    has a rung to try or reports the pass's outcome once.
    """
    level = _logger.info if frame is not None else _logger.warning
    try:
        return realigned(
            parse_edits(_send(op, parts, pacer, tokens, trace, what, attempt=1)),
            frame,
            what,
        )
    except InspectionReplyError as exc:
        if exc.final:
            level("inspection: %s reply unusable, not retrying: %s", what, exc)
            raise
        _logger.info("inspection: %s reply unusable, retrying once: %s", what, exc)
        try:
            return realigned(
                parse_edits(_send(op, parts, pacer, tokens, trace, what, attempt=2)),
                frame,
                what,
            )
        except InspectionReplyError as retry_exc:
            level("inspection: %s reply unusable on the retry too: %s", what, retry_exc)
            raise


def _send(
    op: InspectOperation,
    parts: list[Part],
    pacer: TokenPacer | None,
    tokens: int,
    trace: LlmTrace | None = None,
    what: str = "request",
    attempt: int = 1,
) -> Reply:
    """One paced request, the reply charged too; traced before it is parsed."""
    if pacer is not None:
        pacer.before_request(tokens)
    reply = _generate(op.provider, op.prompt, parts)
    if trace is not None:
        trace.record(TRACE_OP, what, parts, reply.text, attempt=attempt)
    if pacer is not None:
        pacer.after_response(estimate_tokens(reply.text))
    return reply


def _generate(provider: Provider, prompt: str, parts: list[Part]) -> Reply:
    """Ask for the edit list, schema-constrained where the provider allows it.

    A provider without that contract answers in free text, which is what
    the reply parser's repair is for.
    """
    return provider.generate_reply(prompt, parts, response_schema=RESPONSE_SCHEMA)


def _chunk_parts(
    numbered: list[str],
    source_part: MediaPart,
    chunk: Chunk,
    number: int,
    total: int,
) -> list[Part]:
    """Build the request parts for one chunk: its source pages, then its lines.

    A page range that cannot be cut goes against the whole source instead.
    """
    region = TextPart("\n".join(numbered[chunk.start : chunk.end]))
    try:
        pages = pymupdf.extract_pages_bytes(
            source_part.data, chunk.first_page, chunk.last_page
        )
    except (RuntimeError, ValueError, OSError) as exc:
        _logger.warning(
            "inspection: cannot cut pages %d-%d, sending the whole source: %s",
            chunk.first_page + 1,
            chunk.last_page + 1,
            exc,
        )
        return [source_part, TextPart(_chunk_note(chunk, number, total)), region]
    return [
        MediaPart(pages, source_part.mime_type),
        TextPart(_chunk_note(chunk, number, total)),
        region,
    ]


def _chunk_note(chunk: Chunk, number: int, total: int) -> str:
    """Tell the model what part of the document this request covers."""
    return (
        f"This is part {number} of {total} of one document. The attached PDF holds "
        f"its pages {chunk.first_page + 1}-{chunk.last_page + 1}, and the Markdown "
        "below is the matching fragment of the conversion. Every line carries its "
        "own PAGE.LINE address, so report each edit at the address shown on its "
        "line. A line you cannot find on these pages belongs to another part: "
        "leave it alone."
    )
