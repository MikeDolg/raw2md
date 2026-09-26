"""Place an edit's quote in the body: its page-scoped address, then the text.

An address is only where the search starts. The quote decides, as the whole
line, a formula cut across lines, or a fragment standing on the line once, and
a slip of the address is searched for within a window of lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from raw2md.llm.chunking import PageIndex
from raw2md.mdtext.formulas import is_broken_display_line, is_formula_continuation

# Lines searched on either side of an address that misses. Real replies landed
# one to thirty-nine lines off, most often the right line on the neighbouring
# page. A duplicate inside the window fails safely, as an ambiguous match.
_DRIFT_WINDOW = 40


# Lines past a page's end an address may still resolve to. Small on purpose:
# the line is not yet checked, so a wide slack would place a wrong address.
ADDRESS_OVERSHOOT_SLACK = 2


# A formula cut in two pieces is as split as one cut in six; what admits a
# piece is its own shape, not the run's length.
_DISPLAY_UNIT_MIN_PIECES = 2


# The address prefix of a request line, which a reply sometimes echoes back.
_ADDRESS_PREFIX_RE = re.compile(r"^(\d+)\.(\d+):\s*")


# Punctuation Markdown lets a writer escape, minus what still reads as syntax
# once unescaped and no later check guards: the backslash, `!`, `[`, `]`, `<`,
# `*`, `_`, `` ` ``, `~`. `-`, `+`, `>`, `#` are guarded apart at a line start;
# the edit guard holds `$` and `|` on the body line.
_ESCAPABLE_PUNCTUATION = frozenset("\"#$%&'()+,-./:;=>?@^{|}")


_WORD_CHAR_RE = re.compile(r"\w")


# Log samples: wide enough to show where two texts part or a token broke,
# narrow enough that a wide row or a whole reply does not fill the log.
_MISMATCH_SAMPLE = 120


@dataclass(frozen=True)
class DisplayUnit:
    """The body lines one display formula was cut across.

    `pieces` hold the formula's spans; `[start, end)` also covers the blank
    lines and anchors between them.
    """

    start: int
    end: int
    pieces: tuple[int, ...]


@dataclass(frozen=True)
class Placement:
    """The body line a quote resolved to; `span` is None for the whole line."""

    index: int
    span: tuple[int, int] | None = None


def body_lines(body: str) -> list[str]:
    """Split `body` into lines the way `zones.segments` counts them."""
    lines = body.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def numbered_lines(
    lines: list[str], index: PageIndex, units: dict[int, DisplayUnit]
) -> list[str]:
    """Prefix each body line with its page-scoped ``PAGE.LINE`` address.

    The count restarts on every page, so the model keeps a page-long count. A
    chunk is a slice of this list. The lines of one formula cut apart carry
    its first line's address, which says they are repaired together.
    """
    out: list[str] = []
    for line_index, line in enumerate(lines):
        unit = units.get(line_index)
        page, line_in_page = index.address(line_index if unit is None else unit.start)
        out.append(f"{page}.{line_in_page}: {line}")
    return out


def display_units(
    lines: list[str], protected: list[bool], index: PageIndex
) -> dict[int, DisplayUnit]:
    """Find the display formulas cut across several lines, keyed by every line.

    marker emits a long display formula as one damaged `$$...$$` per line, and
    no piece can be repaired alone. Every piece is a damaged whole-line span,
    and every piece after the first opens with a token no formula opens with;
    otherwise two damaged formulas side by side would merge. Blank lines belong
    to the run; a run stays within one page.
    """
    units: dict[int, DisplayUnit] = {}
    idx = 0
    total = len(lines)
    while idx < total:
        if protected[idx] or not is_broken_display_line(lines[idx]):
            idx += 1
            continue
        pieces = [idx]
        page = index.address(idx)[0]
        cursor = idx + 1
        while cursor < total:
            if lines[cursor].strip() == "":
                cursor += 1
                continue
            if (
                protected[cursor]
                or not is_broken_display_line(lines[cursor])
                or not is_formula_continuation(lines[cursor])
                or index.address(cursor)[0] != page
            ):
                break
            pieces.append(cursor)
            cursor += 1
        if len(pieces) >= _DISPLAY_UNIT_MIN_PIECES:
            unit = DisplayUnit(
                start=pieces[0], end=pieces[-1] + 1, pieces=tuple(pieces)
            )
            for line_index in range(unit.start, unit.end):
                units[line_index] = unit
        idx = pieces[-1] + 1
    return units


def strip_declared_address_prefix(old: str, page: int | None, line: int) -> str:
    """Drop a `<page>.<line>:` prefix from `old` when it names this same edit.

    Only this edit's own address: a clause number can open a real line.
    """
    if page is None:
        return old
    match = _ADDRESS_PREFIX_RE.match(old.strip())
    if match is None:
        return old
    if int(match.group(1)) != page or int(match.group(2)) != line:
        return old
    return old.strip()[match.end() :]


def matches(line: str, old: str) -> bool:
    """True when `old` confirms the line, whitespace and optional escapes aside."""
    return _normalize_escapes(line.strip()) == _normalize_escapes(old.strip())


def unit_text(lines: list[str], unit: DisplayUnit) -> str:
    """The formula's own lines, joined; the blanks and anchors between them out.

    The replacement still swallows them: an anchor left standing would mark
    the line after the formula.
    """
    return "\n".join(lines[piece] for piece in unit.pieces)


def matches_unit(lines: list[str], unit: DisplayUnit, old: str) -> bool:
    """True when `old` confirms the whole formula `unit` was cut across.

    Whitespace runs read as one space: where the cut put the breaks is part of
    the defect.
    """
    return _collapsed(unit_text(lines, unit)) == _collapsed(old)


def _collapsed(text: str) -> str:
    return _normalize_escapes(" ".join(text.split()))


def fragment_spans(line: str, old: str) -> list[tuple[int, int]]:
    """Every ``[start, end)`` span of `line` whose text reads as `old`.

    Offsets are into `line` itself, so the rest of it survives byte for byte.
    A match cutting a word in two or splitting an escape pair is left out.
    Overlapping matches are each returned: a fragment resolves an address only
    by standing on the line exactly once.
    """
    needle = _normalize_escapes(old.strip())
    if not needle:
        return []
    lead = len(line) - len(line.lstrip())
    visible = line[lead:]
    normalized, offsets = _normalize_escapes_with_offsets(visible)
    spans: list[tuple[int, int]] = []
    start = normalized.find(needle)
    while start != -1:
        end = start + len(needle)
        if _stands_apart(normalized, start, end) and not _splits_an_escape(
            visible, offsets[start], offsets[end]
        ):
            spans.append((lead + offsets[start], lead + offsets[end]))
        start = normalized.find(needle, start + 1)
    return spans


def _stands_apart(text: str, start: int, end: int) -> bool:
    """True when `text[start:end]` is not the middle of a longer word."""
    opens_a_word = _WORD_CHAR_RE.match(text, start) is not None
    ends_a_word = _WORD_CHAR_RE.match(text, end - 1) is not None
    if opens_a_word and start > 0 and _WORD_CHAR_RE.match(text, start - 1):
        return False
    return not (ends_a_word and end < len(text) and _WORD_CHAR_RE.match(text, end))


def _splits_an_escape(text: str, start: int, end: int) -> bool:
    """True when `text[start:end]` cuts a backslash away from what it escapes.

    The backslash would then escape the first character of `new`.
    """
    if start > 0 and text[start - 1] == "\\":
        return True
    return end < len(text) and text[end - 1] == "\\"


def _repeats_the_line_around(line: str, span: tuple[int, int], new: str) -> bool:
    """True when `new` already carries the text a splice would keep around it.

    A reply may quote a fragment and answer with the whole line; the splice
    would double the edges. Such an edit is skipped, not taken as a whole-line
    replacement, which would drop what `new` left out.
    """
    start, end = span
    replacement = _normalize_escapes(new.strip())
    prefix = _normalize_escapes(line[:start].strip())
    suffix = _normalize_escapes(line[end:].strip())
    if prefix and replacement.startswith(prefix):
        return True
    return bool(suffix) and replacement.endswith(suffix)


def _normalize_escapes(text: str) -> str:
    """Drop a backslash immediately before Markdown-escapable punctuation.

    A reply routinely echoes an escaped body text unescaped. `text` is already
    stripped of leading whitespace, so index 0 is the line start.
    """
    return _normalize_escapes_with_offsets(text)[0]


def _normalize_escapes_with_offsets(text: str) -> tuple[str, list[int]]:
    """`_normalize_escapes`'s reading of `text`, and where it came from.

    ``offsets[i]`` is the index in `text` of normalized character `i` (the
    backslash, for a resolved pair), plus ``len(text)`` at the end, so a span
    maps back at both ends. A left-to-right scan walks a double backslash one
    pair at a time.
    """
    out: list[str] = []
    offsets: list[int] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if (
            ch == "\\"
            and i + 1 < n
            and text[i + 1] in _ESCAPABLE_PUNCTUATION
            and not _escapes_a_leading_marker(text, i)
        ):
            out.append(text[i + 1])
            offsets.append(i)
            i += 2
            continue
        out.append(ch)
        offsets.append(i)
        i += 1
    offsets.append(n)
    return "".join(out), offsets


# These need trailing whitespace to open a block; `-cash` is a word. A bare
# `>` opens a blockquote with nothing after it.
_LEADING_MARKER_CHARS = frozenset("-+#")


def _escapes_a_leading_marker(text: str, backslash_index: int) -> bool:
    """True when unescaping `text[backslash_index]` would open a block marker.

    Such an escape is kept: a whole-line substitution would otherwise turn it
    into live structure, and no ban checks a list or blockquote marker.
    """
    prefix = text[:backslash_index]
    escaped = text[backslash_index + 1]
    following = text[backslash_index + 2 : backslash_index + 3]
    trails_a_marker = following == "" or following.isspace()
    if prefix == "":
        if escaped == ">":
            return True
        if escaped in _LEADING_MARKER_CHARS:
            return trails_a_marker or (escaped == "#" and following == "#")
        return False
    return escaped in ".)" and prefix.isdigit() and trails_a_marker


def address_label(page: int | None, line: int) -> str:
    return f"line {line}" if page is None else f"page {page} line {line}"


def resolve_address(index: PageIndex, page: int | None, line: int) -> int | None:
    """The body line index an edit's address names, or None when it names none.

    An edit with no page is not resolved: a whole-document count drifts.
    """
    if page is None:
        return None
    return index.locate(page, line, slack=ADDRESS_OVERSHOOT_SLACK)


def wide_drift_anchor(index: PageIndex, page: int | None, line: int) -> int | None:
    """The named page's last line, as the drift search origin for an address
    that overshot the page by more than `ADDRESS_OVERSHOOT_SLACK`.

    The overshoot says nothing about where the target sits, so nothing is
    extrapolated from it; the text match still decides. Without it, an edit
    whose declared page is one off would be dismissed before any search.
    """
    if page is None or line < 1:
        return None
    try:
        position = index.numbers.index(page)
    except ValueError:
        return None
    start, end = index.bounds(position)
    if start >= end:
        return None
    return end - 1


def place_quote(
    lines: list[str], addressed: int | None, idx0: int, old: str, new: str
) -> tuple[Placement | None, str | None]:
    """Where `old` names text to replace, or the reason it names none.

    `addressed` is None when the address overshot and `idx0` is the anchor.
    The addressed line goes before the window, and a whole-line match before a
    fragment. A fragment standing on the addressed line more than once names
    no place anywhere. A None reason leaves the caller to name the mismatch.
    """
    repeated = 0
    if addressed is not None and not matches(lines[addressed], old):
        spans = fragment_spans(lines[addressed], old)
        if len(spans) == 1:
            if _repeats_the_line_around(lines[addressed], spans[0], new):
                return None, "new repeats the line around the fragment"
            return Placement(addressed, spans[0]), None
        repeated = len(spans)
    idx, ambiguous = _resolve_edit_index(lines, idx0, old)
    if idx is not None:
        return Placement(idx), None
    if repeated:
        return None, f"fragment stands on the line {repeated} times"
    if ambiguous:
        return None, "ambiguous drift match"
    hits = _fragment_drift(lines, idx0, old, new)
    if len(hits) == 1:
        return hits[0], None
    if hits:
        return None, f"fragment stands on {len(hits)} lines near the address"
    return None, None


def _fragment_drift(lines: list[str], idx0: int, old: str, new: str) -> list[Placement]:
    """The lines around `idx0` that `old` names as a fragment of themselves.

    `idx0` is left out: it was read already, or it is only a search origin.
    """
    lo = max(0, idx0 - _DRIFT_WINDOW)
    hi = min(len(lines), idx0 + _DRIFT_WINDOW + 1)
    hits: list[Placement] = []
    for idx in range(lo, hi):
        if idx == idx0:
            continue
        spans = fragment_spans(lines[idx], old)
        if len(spans) == 1 and not _repeats_the_line_around(lines[idx], spans[0], new):
            hits.append(Placement(idx, spans[0]))
    return hits


def _resolve_edit_index(
    lines: list[str], idx0: int, old: str
) -> tuple[int | None, bool]:
    """Find the 0-based line `old` confirms whole, tolerating a slip.

    The address first, then the window around it; exactly one match resolves
    the drift. ``(None, True)`` means ambiguous, ``(None, False)`` no match.
    """
    if matches(lines[idx0], old):
        return idx0, False
    lo = max(0, idx0 - _DRIFT_WINDOW)
    hi = min(len(lines), idx0 + _DRIFT_WINDOW + 1)
    candidates = [i for i in range(lo, hi) if i != idx0 and matches(lines[i], old)]
    if len(candidates) == 1:
        return candidates[0], False
    return None, len(candidates) > 1


def mismatch_kind(lines: list[str], idx0: int, old: str) -> tuple[str, int]:
    """Name the shape of a failed match and the line it was found against.

    Diagnostic only, so misses that share a cause read alike in the log. The
    search runs the same window as `_resolve_edit_index`.
    """
    order = [idx0]
    for distance in range(1, _DRIFT_WINDOW + 1):
        order += [idx0 - distance, idx0 + distance]
    for idx in order:
        if not 0 <= idx < len(lines):
            continue
        kind = _divergence(lines[idx], old)
        if kind is not None:
            if idx == idx0:
                return kind, idx
            return f"{kind} {idx - idx0:+d} lines away", idx
    return "unrelated text", idx0


def _divergence(line: str, old: str) -> str | None:
    """How `old` differs from `line`, narrowest first, or None for no shared text."""
    text = old.strip()
    target = line.strip()
    if _ADDRESS_PREFIX_RE.sub("", text) == target:
        return "address prefix"
    if " ".join(text.split()) == " ".join(target.split()):
        return "whitespace"
    if text and text in target:
        return "part of the line"
    if target and target in text:
        return "lines run together"
    return None


def address_miss(index: PageIndex, page: int | None) -> str:
    """Why an address named no body line, for the log."""
    if page is None:
        return "no page given"
    try:
        position = index.numbers.index(page)
    except ValueError:
        return "page not in the body"
    start, end = index.bounds(position)
    return f"page holds {end - start} lines"


def sample(text: str) -> str:
    if len(text) <= _MISMATCH_SAMPLE:
        return text
    return f"{text[:_MISMATCH_SAMPLE]}..."
