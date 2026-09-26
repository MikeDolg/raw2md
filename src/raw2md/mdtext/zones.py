"""Protected zones of a markdown body, and inline code masking.

Front matter, fenced code, and HTML tables are kept verbatim by every pass
that edits text; the cleaner, the evaluator, and the LLM stages read them
from one classifier so that their verdicts on a body agree. Inline code is
masked with blanks of the same width, so offsets into the line stay valid.
"""

from __future__ import annotations

import re
from enum import Enum, auto

# group(2) is the info string; a closing fence leaves it empty (CommonMark).
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

_BACKTICK_RUN_RE = re.compile(r"`+")

# Tables may nest, so opens and closes are counted, not paired.
_TABLE_OPEN_RE = re.compile(r"<table\b", re.IGNORECASE)
_TABLE_CLOSE_RE = re.compile(r"</table\b", re.IGNORECASE)


# Text line tagged with whether it is protected (kept verbatim) or plain.
Segment = tuple[str, bool]


class _ZoneKind(Enum):
    """Why a line is protected, or that it is not protected at all."""

    PLAIN = auto()
    FRONT_MATTER = auto()
    FENCE = auto()
    TABLE = auto()


def segments(text: str) -> list[Segment]:
    """Split `text` into ``(line, protected)`` pairs without altering any line.

    Protected: leading front matter, fenced code, and HTML tables, nested ones
    included. A trailing newline adds no empty line.
    """
    return [(line, kind is not _ZoneKind.PLAIN) for line, kind in _zone_kinds(text)]


def block_bounds(lines: list[str], protected: list[bool], idx: int) -> tuple[int, int]:
    """The ``[start, end)`` span of the block holding line `idx`.

    A block ends at a blank line or a change in protection. It is what one
    format defect spans, however many lines a finding names.
    """
    start = idx
    while (
        start > 0
        and lines[start - 1].strip() != ""
        and protected[start - 1] == protected[idx]
    ):
        start -= 1
    end = idx + 1
    count = len(lines)
    while end < count and lines[end].strip() != "" and protected[end] == protected[idx]:
        end += 1
    return start, end


def html_table_lines(text: str) -> list[bool]:
    """True for each line of `text` inside an HTML table; indexed as `segments`.

    Lets a caller edit a cell value while front matter and fences stay verbatim.
    """
    return [kind is _ZoneKind.TABLE for _, kind in _zone_kinds(text)]


def _zone_kinds(text: str) -> list[tuple[str, _ZoneKind]]:
    """Classify each line of `text` by the protected zone (if any) holding it."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]

    result: list[tuple[str, _ZoneKind]] = []
    start = _classify_front_matter(lines, result)

    fence_marker: str | None = None
    table_depth = 0
    for line in lines[start:]:
        if fence_marker is not None:
            result.append((line, _ZoneKind.FENCE))
            if _closes_fence(line, fence_marker):
                fence_marker = None
            continue
        if table_depth > 0:
            result.append((line, _ZoneKind.TABLE))
            table_depth = max(0, table_depth + _table_delta(line))
            continue
        fence = _FENCE_RE.match(line)
        if fence is not None:
            result.append((line, _ZoneKind.FENCE))
            fence_marker = fence.group(1)
            continue
        if _TABLE_OPEN_RE.search(line):
            result.append((line, _ZoneKind.TABLE))
            table_depth = max(0, _table_delta(line))
            continue
        result.append((line, _ZoneKind.PLAIN))
    return result


def _classify_front_matter(
    lines: list[str], result: list[tuple[str, _ZoneKind]]
) -> int:
    """Mark a leading ``---`` ... ``---`` block as front matter; return the next index.

    Without a closer the `---` is a thematic break.
    """
    if not lines or lines[0].rstrip() != "---":
        return 0
    for j in range(1, len(lines)):
        if lines[j].rstrip() == "---":
            result.extend((lines[k], _ZoneKind.FRONT_MATTER) for k in range(j + 1))
            return j + 1
    return 0


def _closes_fence(line: str, marker: str) -> bool:
    """True when `line` closes the fence opened by `marker` (CommonMark)."""
    m = _FENCE_RE.match(line)
    if m is None:
        return False
    closer = m.group(1)
    return (
        closer[0] == marker[0] and len(closer) >= len(marker) and not m.group(2).strip()
    )


def inline_code_ranges(line: str) -> list[tuple[int, int]]:
    """The `[start, end)` ranges of `line` held by inline code spans.

    Ranges include the backticks: a quoted `$$` would otherwise shift every
    delimiter pair after it. One line only, though CommonMark allows more: a
    stray backtick would mask an arbitrary stretch.
    """
    ranges: list[tuple[int, int]] = []
    pos = 0
    while True:
        opener = _BACKTICK_RUN_RE.search(line, pos)
        if opener is None:
            return ranges
        closer = _matching_backtick_run(line, opener)
        if closer is None:
            pos = opener.end()
            continue
        ranges.append((opener.start(), closer.end()))
        pos = closer.end()


def _matching_backtick_run(line: str, opener: re.Match[str]) -> re.Match[str] | None:
    """The backtick run closing `opener`, or None when it never closes."""
    width = opener.end() - opener.start()
    pos = opener.end()
    while True:
        candidate = _BACKTICK_RUN_RE.search(line, pos)
        if candidate is None:
            return None
        if candidate.end() - candidate.start() == width:
            return candidate
        pos = candidate.end()


def mask_inline_code(text: str) -> str:
    """`text` with every inline code span blanked; offsets are preserved."""
    out: list[str] = []
    for line in text.split("\n"):
        ranges = inline_code_ranges(line)
        if not ranges:
            out.append(line)
            continue
        chars = list(line)
        for start, end in ranges:
            chars[start:end] = " " * (end - start)
        out.append("".join(chars))
    return "\n".join(out)


def blank_match(match: re.Match[str]) -> str:
    """Spaces of the same width as `match`, so a mask keeps the text's offsets."""
    return " " * (match.end() - match.start())


def _table_delta(line: str) -> int:
    return len(_TABLE_OPEN_RE.findall(line)) - len(_TABLE_CLOSE_RE.findall(line))
