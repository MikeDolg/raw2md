"""What the post routes share: the operation, a zone's outcome, a retry note.

The list routes (tables, ladder, spacing) also share their reply protocol here:
a JSON list asked for under a schema where the provider allows it, decoded the
same way when it comes back as free text.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from raw2md.llm.base import EmptyReason, Part, Provider, ProviderError, Reply
from raw2md.mdtext.zones import Segment

_logger = logging.getLogger("raw2md")


# For the echo check a soft break collapses to a space, but a blank line stays
# a paragraph break: closing one is the repair of a crushed run.
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def _collapse_whitespace_run(match: re.Match[str]) -> str:
    return "\n\n" if match.group().count("\n") >= 2 else " "


TRACE_OP = "post"


@dataclass(frozen=True)
class PostOperation:
    """A resolved post-processing operation, built once per run."""

    provider: Provider
    prompt: str
    model_key: str


def block_end(seg_list: list[Segment], start: int) -> int:
    """Index past the run of plain non-blank lines starting at `start`."""
    end = start
    while end < len(seg_list):
        line, protected = seg_list[end]
        if protected or not line.strip():
            break
        end += 1
    return end


# A larger context block is dropped: context is optional, and an oversized
# request fails post for the whole file. A normal block runs well under it.
# The spacing route bounds its lines by the same measure.
MAX_CONTEXT_CHARS = 4000


@dataclass(frozen=True)
class ZoneOutcome:
    """What one zone came back as.

    `lines` are the repaired zone when `accepted`, the original otherwise. A
    table zone is `accepted` on one row. A table zone sent in parts can carry
    both a `failure` and an accepted repair.
    """

    lines: list[str]
    accepted: bool
    joins: int = 0
    refused_joins: int = 0
    unchanged: bool = False
    repaired_rows: int = 0
    refused_rows: int = 0
    failure: ProviderError | None = None


def retry_note(reason: str) -> str:
    """The extra part sent with a retry, naming what the rejected reply broke."""
    return (
        f"Your previous reply for this zone was rejected: {reason}. Send a "
        "corrected reply for the same zone that follows the instructions above."
    )


def normalized_zone(lines: list[str]) -> str:
    """`lines` as a reader sees them: soft breaks read as spaces, ends trimmed."""
    return _WHITESPACE_RUN_RE.sub(_collapse_whitespace_run, "\n".join(lines)).strip()


# Largest reply one request of a list route may draw, in characters. Wide
# tables of printed scans drew replies the output cap cut off mid-JSON. Well
# under a small model's output budget, since escaping and keys come on top;
# set by hand, not measured.
MAX_REPLY_CHARS = 8000

# One reply entry beyond its text: braces, keys, a small index; rounded up.
ENTRY_REPLY_OVERHEAD = 24

# The list JSON around the entries themselves: `{"rows": []}`, `{"runs": []}`.
LIST_WRAPPER_CHARS = 12


# A code fence the model sometimes wraps around the JSON.
JSON_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*)\n```\s*$", re.DOTALL)

# Rejections a list route's retry note names, so the note stays short.
REPLY_REASON_LIMIT = 3


def log_unparsed_reply(reply: Reply, what: str, *, attempt: int, listing: str) -> None:
    """Log a reply the list decoder could not read, cut-off apart from garbage.

    A cut-off list asks for a smaller part, garbage for a better prompt. INFO
    first, WARNING when the retry fails the same way.
    """
    log = _logger.info if attempt == 1 else _logger.warning
    tail = ", retrying once" if attempt == 1 else " on the retry too"
    if reply.empty_reason is EmptyReason.TRUNCATED or _looks_truncated(reply.text):
        log("post: %s reply cut off before the %s closed%s", what, listing, tail)
    else:
        log("post: %s reply not a %s%s", what, listing, tail)


def _looks_truncated(reply: str) -> bool:
    """True when an unparsed reply began as the JSON list and was cut short."""
    stripped = reply.strip()
    if stripped.startswith("```"):
        return JSON_FENCE_RE.match(stripped) is None
    return stripped.startswith(("{", "["))


def schema_reply(
    op: PostOperation, parts: Sequence[Part], schema: dict[str, object]
) -> Reply:
    """Ask for a JSON list, schema-constrained where the provider allows it.

    A provider without that contract answers in free text, which is why the
    decoders tolerate a fence and an index written as text.
    """
    return op.provider.generate_reply(op.prompt, parts, response_schema=schema)


def parse_text_edits(reply: str, listing: str, key: str) -> dict[int, str] | None:
    """The indexed texts a reply names, or None when it is not that list at all.

    Shared by the table and spacing routes. An unusable entry is dropped, not
    the reply.
    """
    stripped = reply.strip()
    fenced = JSON_FENCE_RE.match(stripped)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data = data.get(listing, [])
    if not isinstance(data, list):
        return None
    edits: dict[int, str] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        number = reply_number(entry.get(key))
        text = entry.get("text")
        if number is not None and isinstance(text, str):
            edits[number] = text
    return edits


def reply_number(value: object) -> int | None:
    """An index a reply wrote as a number or as digits, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
