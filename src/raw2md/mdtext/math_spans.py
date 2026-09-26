"""Location of math spans in a line, and math masking.

marker writes `$...$` and `$$...$$`; pandoc writes `\\(...\\)` and
`\\[...\\]`. A backslash escapes a `$`, so a printed dollar sign opens no span.
"""

from __future__ import annotations

import re

from raw2md.mdtext.zones import blank_match

# A backslash escapes a delimiter. Loops are judged inside spans only, so a
# currency `$` next to repeated prose is no formula.
_DISPLAY_MATH_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$([^\n]+?)(?<!\\)\$")

# pandoc's math dialect, which the `$` readers do not parse.
RAW_LATEX_SPAN_RE = re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]")

# `\$` is a printed dollar sign, not a delimiter.
MATH_DELIMITER_RE = re.compile(r"(?<!\\)\$")


def is_math_only_line(core: str) -> bool:
    """True when `core` is nothing but math spans, with no other content.

    An axis label repeated under every plot is content, not a loop. Display
    spans go first, so their `$$` never split into inline matches.
    """
    remainder = _DISPLAY_MATH_RE.sub("", core)
    remainder = _INLINE_MATH_RE.sub("", remainder)
    return not remainder.strip()


def math_span_ranges(line: str) -> list[tuple[int, int]]:
    """The `[start, end)` ranges of `line` that hold math, delimiters included.

    Closed display and inline spans, plus an unclosed trailing `$` region
    with a backslash: a truncated formula leaves its closer looking escaped
    (`...^{\\$`), and the backslash tells it from a currency `$`.
    """
    ranges: list[tuple[int, int]] = []
    gaps: list[tuple[int, int]] = []
    last = 0
    for match in _DISPLAY_MATH_RE.finditer(line):
        gaps.append((last, match.start()))
        ranges.append(match.span())
        last = match.end()
    gaps.append((last, len(line)))

    for index, (start, end) in enumerate(gaps):
        gap = line[start:end]
        closed_end = 0
        for match in _INLINE_MATH_RE.finditer(gap):
            ranges.append((start + match.start(), start + match.end()))
            closed_end = match.end()
        # Only the last gap: an earlier `$` pairs with something later.
        if index == len(gaps) - 1:
            tail = _unclosed_math_start(gap[closed_end:])
            if tail is not None and "\\" in gap[closed_end + tail + 1 :]:
                ranges.append((start + closed_end + tail, end))
    return sorted(ranges)


def _unclosed_math_start(text: str) -> int | None:
    """Offset of the first unescaped `$` in `text`, or None when there is none."""
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2  # skip the escaped character, so `\$` is not read as a delimiter
            continue
        if text[i] == "$":
            return i
        i += 1
    return None


def has_unpaired_delimiter(text: str) -> bool:
    """True when an unescaped `$` of `text` sits outside every closed span."""
    outside = _INLINE_MATH_RE.sub("", _DISPLAY_MATH_RE.sub("", text))
    return MATH_DELIMITER_RE.search(outside) is not None


def math_span_content(span: str) -> str:
    """The content of `span`: `$$...$$`, `$...$`, or a truncated `$...`."""
    if len(span) >= 4 and span.startswith("$$") and span.endswith("$$"):
        return span[2:-2]
    if len(span) >= 2 and span.startswith("$") and span.endswith("$"):
        return span[1:-1]
    return span.removeprefix("$")


def math_spans(text: str) -> list[str]:
    """The math spans of `text` in order, delimiters included."""
    return [text[start:end] for start, end in math_span_ranges(text)]


def mask_math(text: str) -> str:
    """`text` with every math span blanked, delimiters included; offsets kept.

    Both dialects: marker's `$` and pandoc's paired `\\(...\\)`, `\\[...\\]`
    on one line. A lone pandoc opener looks like an escaped bracket.
    """
    out: list[str] = []
    for line in text.split("\n"):
        # pandoc first, so a `$` inside its region opens no span.
        masked = RAW_LATEX_SPAN_RE.sub(blank_match, line)
        ranges = math_span_ranges(masked)
        if not ranges:
            out.append(masked)
            continue
        chars = list(masked)
        for start, end in ranges:
            chars[start:end] = " " * (end - start)
        out.append("".join(chars))
    return "\n".join(out)
