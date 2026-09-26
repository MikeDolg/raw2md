"""LLM-OCR operation: recognize page rasters into Markdown.

Runs under ``--engine <model>`` for ``pdf`` and ``djvu``: one request per page
raster, joined in page order, with no media extracted. OCR is the conversion,
so there is no result to fall back on and provider errors propagate. An empty
reply is retried unless its reason would repeat; a raster with no ink is taken
as a blank page first, so it spends no quota. A page still empty is replaced by
a lost-page marker, so the loss reaches the result.
"""

from __future__ import annotations

import io
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto

from PIL import Image

from raw2md.llm.base import FINAL_EMPTY_REASONS, MediaPart, Provider, empty_reason_label
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.pages import lost_page_marker, page_mark

_logger = logging.getLogger("raw2md")

_TRACE_OP = "ocr"

# Page rasters are rendered as PNG upstream.
_PNG_MIME = "image/png"

# A code fence the model sometimes wraps around the page Markdown.
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*)\n```\s*$", re.DOTALL)

# The first request plus two retries: an empty reply that clears at all clears
# on a repeat, and each attempt costs quota.
_MAX_ATTEMPTS = 3

# Ink test on grayscale levels 0 (black) to 255 (white). The share is a few
# characters at the render resolution: one line of text passes, scanner speckle
# on a blank verso does not.
_INK_LEVEL = 128
_MIN_INK_SHARE = 0.0002


@dataclass(frozen=True)
class OcrOperation:
    """A resolved LLM-OCR operation, built once per run.

    `model_key` is the settings key that the header records as `engine`.
    """

    provider: Provider
    prompt: str
    model_key: str


@dataclass(frozen=True)
class OcrResult:
    """Outcome of one OCR pass over a file.

    `pages` counts every raster sent, blank ones included. `empty_replies`
    counts the pages whose first reply was empty: `recovered` came back on a
    retry, `lost_pages` stayed empty over ink, the rest were blank.
    """

    body: str
    pages: int
    empty_replies: int = 0
    recovered: int = 0
    lost_pages: int = 0


class _PageStatus(Enum):
    TRANSCRIBED = auto()
    RECOVERED = auto()
    BLANK = auto()
    LOST = auto()


def recognize(
    pages: Iterable[bytes],
    op: OcrOperation,
    *,
    mark_pages: bool = False,
    trace: LlmTrace | None = None,
) -> OcrResult:
    """Transcribe each page raster through the vision model and join in order.

    Pages join with a blank line. Under `mark_pages` each page opens with a
    page mark, so inspection can address an edit by page. A page with no text
    has no line to mark, so its mark joins the next page's; trailing blank
    pages stay unmarked. Provider errors propagate.
    """
    transcripts: list[str] = []
    counts: dict[_PageStatus, int] = {}
    pending_marks: list[str] = []
    pages_seen = 0
    for raster in pages:
        pages_seen += 1
        text, status = _transcribe_page(raster, pages_seen, op, trace)
        counts[status] = counts.get(status, 0) + 1
        if mark_pages:
            pending_marks.append(page_mark(pages_seen))
        if text:
            transcripts.append("\n".join([*pending_marks, text]))
            pending_marks.clear()
    body = "\n\n".join(transcripts)
    if body:
        body += "\n"
    recovered = counts.get(_PageStatus.RECOVERED, 0)
    blank = counts.get(_PageStatus.BLANK, 0)
    lost = counts.get(_PageStatus.LOST, 0)
    return OcrResult(
        body=body,
        pages=pages_seen,
        empty_replies=recovered + blank + lost,
        recovered=recovered,
        lost_pages=lost,
    )


def _transcribe_page(
    raster: bytes, page: int, op: OcrOperation, trace: LlmTrace | None = None
) -> tuple[str, _PageStatus]:
    """Transcribe one page, retrying an empty reply that can still recover.

    No retry for a raster with no ink or for a reason a repeat would
    reproduce. `trace` records every attempt, an empty one included.
    """
    what = f"page {page}"
    parts = [MediaPart(raster, _PNG_MIME)]
    reply = op.provider.generate_reply(op.prompt, parts)
    if trace is not None:
        trace.record(_TRACE_OP, what, parts, reply.text)
    text = _clean_reply(reply.text)
    if text:
        return text, _PageStatus.TRANSCRIBED
    _logger.info(
        "OCR page %d: empty reply (%s)", page, empty_reason_label(reply.empty_reason)
    )
    if not _has_ink(raster):
        _logger.info("OCR page %d: raster carries no ink, taken as blank", page)
        return "", _PageStatus.BLANK
    attempts = 1
    while attempts < _MAX_ATTEMPTS and reply.empty_reason not in FINAL_EMPTY_REASONS:
        attempts += 1
        reply = op.provider.generate_reply(op.prompt, parts)
        if trace is not None:
            trace.record(_TRACE_OP, what, parts, reply.text, attempt=attempts)
        text = _clean_reply(reply.text)
        if text:
            _logger.info("OCR page %d: recovered on attempt %d", page, attempts)
            return text, _PageStatus.RECOVERED
        _logger.info(
            "OCR page %d: empty reply on attempt %d (%s)",
            page,
            attempts,
            empty_reason_label(reply.empty_reason),
        )
    _logger.warning(
        "OCR page %d: lost after %d attempt(s), last reason %s",
        page,
        attempts,
        empty_reason_label(reply.empty_reason),
    )
    return lost_page_marker(page), _PageStatus.LOST


def _has_ink(raster: bytes) -> bool:
    """True when the page raster holds enough dark pixels to carry content.

    The histogram needs no downscale, which would average a thin stroke into the
    background. An unreadable raster answers True: a guard that cannot see the
    page must not write it off.
    """
    try:
        with Image.open(io.BytesIO(raster)) as img:
            # Pillow's histogram is untyped: 256 counts in level order.
            histogram: list[int] = img.convert("L").histogram()
    except (OSError, ValueError) as exc:
        _logger.warning("OCR: page raster could not be read (%s); assuming ink", exc)
        return True
    total = sum(histogram)
    if not total:
        return True
    return sum(histogram[:_INK_LEVEL]) / total >= _MIN_INK_SHARE


def _clean_reply(reply: str) -> str:
    stripped = reply.strip()
    fenced = _FENCE_RE.match(stripped)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    return stripped
