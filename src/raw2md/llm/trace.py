"""Raw request and reply trace for the LLM steps, written under `--debug`.

Without the reply, a model that answered wrongly and a tool that failed to
apply a correct answer read the same in the log. Each operation appends to
`<result-stem>.debug/llm/<op>.txt` in request order, so a retry sits under the
attempt it repeats. Media is not written: the header names its type and size.
The pipeline never reads the trace back.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from raw2md.llm.base import MediaPart, Part, TextPart

_logger = logging.getLogger("raw2md")

# A subfolder keeps the per-stage body snapshots first in `.debug`.
_TRACE_DIR = "llm"


class LlmTrace:
    """Append-only writer of raw LLM requests and replies for one file.

    The folder is created by the first record, so an operation that sent no
    request leaves no file.
    """

    def __init__(self, debug_dir: Path) -> None:
        self._dir = debug_dir / _TRACE_DIR
        # A failed write is reported once and stops the trace: an unwritable
        # folder fails for every request alike.
        self._broken = False

    def record(
        self,
        op: str,
        what: str,
        parts: Sequence[Part],
        reply: str,
        *,
        attempt: int = 1,
    ) -> None:
        """Append one request/reply pair to `op`'s trace file.

        `what` names the unit (a chunk, a zone, a page) and `attempt` its try.
        A write failure is logged, never raised: the requests are already paid
        for, so losing the trace must not lose the result.
        """
        if self._broken:
            return
        entry = _format_entry(what, parts, reply, attempt)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"{op}.txt"
            with path.open("a", encoding="utf-8", newline="") as handle:
                handle.write(entry)
        except OSError as exc:
            self._broken = True
            _logger.warning("debug: LLM trace for %s not written: %s", op, exc)


def _format_entry(what: str, parts: Sequence[Part], reply: str, attempt: int) -> str:
    """Render one trace entry; the reply stays unparsed and untrimmed."""
    return (
        f"### {what}  attempt {attempt}\n"
        f"{_request_header(parts)}\n"
        f"{_request_text(parts)}\n"
        f"-- reply ({len(reply)} chars) --\n"
        f"{reply}\n\n"
    )


def _request_header(parts: Sequence[Part]) -> str:
    count = len(parts)
    noun = "part" if count == 1 else "parts"
    media = [
        f"{part.mime_type}, {_human_bytes(len(part.data))}"
        for part in parts
        if isinstance(part, MediaPart)
    ]
    suffix = f"; media: {'; '.join(media)}" if media else ""
    return f"-- request ({count} {noun}{suffix}) --"


def _request_text(parts: Sequence[Part]) -> str:
    """The text parts of a request; the prompt is left out, it never differs."""
    return "\n\n".join(part.text for part in parts if isinstance(part, TextPart))


def _human_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
