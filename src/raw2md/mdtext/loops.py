"""Repetition loops of a degenerated recognizer, and their trim.

The evaluator and the cleaner share the detector: the evaluator counts a
loop as a lost formula, and the cleaner trims it to one copy of its unit.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from raw2md.mdtext.links import mask_addresses
from raw2md.mdtext.math_spans import math_span_ranges, math_spans
from raw2md.mdtext.zones import mask_inline_code

# Recognition degenerates autoregressively and repeats one unit until a
# length cap. Calibrated on scanned technical documents: true loops run 8 to
# 338 repeats, legitimate formulas at most 1.
_LOOP_MIN_PERIOD = 3
_LOOP_MAX_PERIOD = 80
_LOOP_MIN_REPEATS = 6

# Prose has no metacharacter signal. A refrain runs six or eight times;
# observed loops run 63 to 337.
_PROSE_LOOP_MIN_REPEATS = 10

# Lazy unit: the shortest period is captured. Whole copies only.
_LOOP_RUN_RE = re.compile(
    rf"(.{{{_LOOP_MIN_PERIOD},{_LOOP_MAX_PERIOD}}}?)\1{{{_LOOP_MIN_REPEATS - 1},}}"
)

# A long unit is weighed by the bytes it inserts, not by the copy count.
# Calibrated on 24 bodies: 9 runs of 190 to 916 bytes, all in 2 already
# degenerated bodies. The longest unit observed is 229 characters.
_LOOP_LONG_MIN_PERIOD = _LOOP_MAX_PERIOD + 1
_LOOP_LONG_MAX_PERIOD = 400
_LOOP_LONG_MIN_REPEATS = 3
_LOOP_LONG_MIN_INSERTED = 400

# Where a run's first characters return is its period, found by a search
# instead of trying every length. Shorter than the shortest long unit.
_LOOP_LONG_WINDOW = 24

# Whole inline spans repeated back to back, matched one span per token.
# Observed cycles hold up to seven distinct spans.
_SPAN_RUN_MAX_PERIOD = 8

# A loop repeats its separator unchanged; prose joins a variable to the next
# word differently each time. The bound limits what one cut may take: a
# clause the page printed is longer.
_SPAN_RUN_MAX_GAP = 16

# A pipe would merge table columns; `$` belongs to a span; a backtick opens
# code, where repetition is quoting.
_SPAN_RUN_GAP_STOPCHARS = frozenset("|$`")

# A gap removes the adjacency evidence, so the count alone decides. A page's
# row of one value reaches 10 copies; gap loops run 30 to 334.
_SPAN_RUN_SEPARATED_MIN_REPEATS = 20

# Without a metacharacter the count alone decides. A page's row of one value
# reaches 10 copies; such loops run 156 to 334.
_SPAN_RUN_PLAIN_MIN_REPEATS = 20

# A looped sub-expression carries one; `5 = 5 = 5 ...` does not.
_MATH_LOOP_METACHARS = frozenset("\\{}_^")

# `\begin{array}`'s argument degenerating into one column letter. Only its
# position marks it. The brace is matched by depth, and `@{...}` contents are
# blanked, since they may spell text from the same letters. The bar is far
# past any hand-set column count.
_ARRAY_BEGIN_RE = re.compile(r"\\begin\{array\}(?:\[[^\]]*\])?\{")
_AT_DECLARATION_RE = re.compile(r"@\{[^{}]*\}")
_COLUMN_SPEC_LOOP_LETTERS = "lcrpmb"
_COLUMN_SPEC_LOOP_MIN_REPEATS = 20
_COLUMN_SPEC_LOOP_UNIT_RE = re.compile(
    rf"([{_COLUMN_SPEC_LOOP_LETTERS}])\1{{{_COLUMN_SPEC_LOOP_MIN_REPEATS - 1},}}"
)

# Same reasons as `_SPAN_RUN_GAP_STOPCHARS`.
_PROSE_LOOP_STOPCHARS = frozenset("|$`")


def math_repetition_loop(line: str) -> bool:
    """True when a math span in `line` degenerated into a repetition loop.

    The original formula is lost; the evaluator and the cleaner share this
    detector, read before the trim removes the loop. Shapes: a unit with a
    metacharacter repeated past the count bar (`ds_{ij}^{\\ e}+...`), a long
    unit past the byte bar, a column-spec letter loop, and whole repeated
    spans. One line only; a multi-line display formula is out of scope.
    """
    if "$" not in line:
        return False
    if any(_has_repetition_loop(span) for span in math_spans(line)):
        return True
    return bool(math_repeated_span_cuts(line))


def collapse_repetition_loops(line: str) -> str:
    """`line` with every repetition loop trimmed to a single copy of its unit.

    The overwritten content is lost, so an LLM step has nothing to rebuild.
    One copy stays: it invents nothing, and a span stays a span, which
    inspection needs to restore it. The unit must read as math inside a span
    and as prose outside. Repeats until stable; each pass shortens the line.
    """
    while True:
        collapsed = _collapse_loops_once(line)
        if collapsed == line:
            return line
        line = collapsed


def _collapse_loops_once(line: str) -> str:
    """One collapsing pass over `line`, math spans and the prose between them.

    Most lines carry no run and exit after one scan of the whole line.
    """
    if _LOOP_RUN_RE.search(line) is None and not _may_hold_long_loop(line):
        return line
    out: list[str] = []
    last = 0
    for start, end in math_span_ranges(line):
        out.append(_collapse_prose_loops(line[last:start]))
        out.append(_collapse_math_loops(line[start:end]))
        last = end
    out.append(_collapse_prose_loops(line[last:]))
    return "".join(out)


def _may_hold_long_loop(line: str) -> bool:
    """True when `line` is long enough, and math enough, to hold a long run."""
    return "$" in line and len(line) >= _LOOP_LONG_MIN_REPEATS * _LOOP_LONG_MIN_PERIOD


def _collapse_math_loops(span: str) -> str:
    """Collapse the loops of one math span, the count bar before the byte bar."""
    collapsed = _collapse_loops(span, _is_math_loop_unit)
    runs = _long_loop_runs(collapsed)
    if not runs:
        return collapsed
    out: list[str] = []
    last = 0
    for start, end, unit in runs:
        out.append(collapsed[last:start])
        out.append(unit)
        last = end
    out.append(collapsed[last:])
    return "".join(out)


def _collapse_prose_loops(text: str) -> str:
    """Collapse the loops of `text` outside math; code and addresses are masked."""
    masked = mask_addresses(text)
    return _collapse_loops(
        text, _is_prose_loop_unit, _PROSE_LOOP_MIN_REPEATS, scan=masked
    )


def _collapse_loops(
    text: str,
    unit_ok: Callable[[str], bool],
    min_repeats: int = _LOOP_MIN_REPEATS,
    scan: str | None = None,
) -> str:
    """`text` with each qualifying repetition run replaced by one copy of its unit.

    `scan` is a same-length mask to search. A run that reaches into a masked
    stretch stays.
    """
    if scan is None:
        scan = text
    out: list[str] = []
    pos = 0
    for match in _LOOP_RUN_RE.finditer(scan):
        start, end = match.span()
        unit = match.group(1)
        if (end - start) // len(unit) < min_repeats:
            continue
        if scan[start:end] != text[start:end] or not unit_ok(unit):
            continue
        out.append(text[pos:start])
        out.append(unit)
        pos = end
    if not out:
        return text
    out.append(text[pos:])
    return "".join(out)


def _has_repetition_loop(region: str) -> bool:
    """True when `region` holds a math unit repeated back to back past the threshold."""
    if _has_column_spec_loop(region):
        return True
    if any(
        _is_math_loop_unit(match.group(1)) for match in _LOOP_RUN_RE.finditer(region)
    ):
        return True
    return bool(_long_loop_runs(region))


def _long_loop_runs(region: str) -> list[tuple[int, int, str]]:
    """Every run in `region` of a unit too long for the count bar to weigh.

    Runs come as bounds and one unit copy, left to right, never overlapping.
    A start with no metacharacter within `_LOOP_LONG_MAX_PERIOD` is skipped
    unsearched, which keeps a spill of one digit over thousands of positions
    linear.
    """
    runs: list[tuple[int, int, str]] = []
    floor = _LOOP_LONG_MIN_REPEATS * _LOOP_LONG_MIN_PERIOD
    length = len(region)
    start = 0
    metachar = _next_metachar(region, 0)
    while start + floor <= length:
        if metachar is not None and metachar < start:
            metachar = _next_metachar(region, start)
        if metachar is None or metachar - start >= _LOOP_LONG_MAX_PERIOD:
            start += 1
            continue
        found = _long_loop_at(region, start)
        if found is None:
            start += 1
            continue
        end, unit = found
        runs.append((start, end, unit))
        start = end
    return runs


def _next_metachar(region: str, start: int) -> int | None:
    """Index of the first LaTeX metacharacter in `region` at or after `start`."""
    for i in range(start, len(region)):
        if region[i] in _MATH_LOOP_METACHARS:
            return i
    return None


def _long_loop_at(region: str, start: int) -> tuple[int, str] | None:
    """The end and the unit of the long run starting at `start`, or None.

    Each return of the window is a candidate period until the cap. The unit
    must read as math, checked before the copies are counted because it is
    cheaper.
    """
    window = region[start : start + _LOOP_LONG_WINDOW]
    limit = start + _LOOP_LONG_MAX_PERIOD + _LOOP_LONG_WINDOW
    at = region.find(window, start + _LOOP_LONG_MIN_PERIOD, limit)
    while at != -1:
        period = at - start
        unit = region[start:at]
        if _is_math_loop_unit(unit):
            copies = 1
            while region[at + (copies - 1) * period : at + copies * period] == unit:
                copies += 1
            if (
                copies >= _LOOP_LONG_MIN_REPEATS
                and (copies - 1) * period >= _LOOP_LONG_MIN_INSERTED
            ):
                return start + copies * period, unit
        at = region.find(window, at + 1, limit)
    return None


def _has_column_spec_loop(region: str) -> bool:
    """True when an `\\begin{array}` argument in `region` loops one column letter."""
    for arg in _array_column_spec_args(region):
        masked = _AT_DECLARATION_RE.sub("#", arg)
        if _COLUMN_SPEC_LOOP_UNIT_RE.search(masked) is not None:
            return True
    return False


def _array_column_spec_args(region: str) -> list[str]:
    """Every `\\begin{array}` column-spec argument in `region`, braces balanced.

    An unclosed spec runs to the end of `region`.
    """
    args: list[str] = []
    length = len(region)
    for match in _ARRAY_BEGIN_RE.finditer(region):
        start = match.end()
        depth = 1
        i = start
        while i < length and depth:
            if region[i] == "{":
                depth += 1
            elif region[i] == "}":
                depth -= 1
            i += 1
        end = i - 1 if depth == 0 else i
        args.append(region[start:end])
    return args


def _is_math_loop_unit(unit: str) -> bool:
    """True when `unit` carries an alphanumeric and a LaTeX metacharacter."""
    return any(ch.isalnum() for ch in unit) and any(
        ch in _MATH_LOOP_METACHARS for ch in unit
    )


def _is_prose_loop_unit(unit: str) -> bool:
    """True when `unit` has a letter and no stop character.

    Repeated numbers and punctuation rules are written on purpose.
    """
    return any(ch.isalpha() for ch in unit) and not any(
        ch in _PROSE_LOOP_STOPCHARS for ch in unit
    )


def math_repeated_span_cuts(line: str) -> list[tuple[int, int]]:
    """The `[start, end)` ranges of `line` that repeat a run of inline math spans.

    Cutting them leaves one copy of the cycle (`$v_{m-1}$   $v_{m-1}$ ...`).
    The gap between copies must repeat identically; prose naming a variable
    joins it to different words each time. Display spans and truncated tails
    are excluded. The cheap `$` count skips most lines.
    """
    if line.count("$") < 2 * _LOOP_MIN_REPEATS:
        return []
    cuts: list[tuple[int, int]] = []
    for mark, run in _span_loop_runs(line):
        bar = _LOOP_MIN_REPEATS if mark == "" else _SPAN_RUN_SEPARATED_MIN_REPEATS
        cuts.extend(_span_loop_cuts(line, run, bar))
    return cuts


def _span_loop_runs(line: str) -> list[tuple[str, list[tuple[int, int]]]]:
    """The runs of evenly divided inline span ranges in `line`, long enough to loop.

    Spans are found on the code-masked line, but gaps are read off the line
    itself: in the mask a quoted stretch would look like an empty gap.
    """
    runs: list[list[tuple[int, int]]] = [[]]
    # The gap the run's first pair set; None until the run holds two spans.
    marks: list[str | None] = [None]
    for start, end in math_span_ranges(mask_inline_code(line)):
        if not _is_inline_span(line[start:end]):
            runs.append([])
            marks.append(None)
            continue
        current = runs[-1]
        mark = _span_gap_mark(line[current[-1][1] : start]) if current else None
        if mark is None:
            runs.append([(start, end)])
            marks.append(None)
        elif marks[-1] in (None, mark):
            marks[-1] = mark
            current.append((start, end))
        else:
            # The previous span opens the new run, so a loop does not lose its
            # first copy to a neighbour divided another way.
            runs.append([current[-1], (start, end)])
            marks.append(mark)
    return [
        (mark or "", run)
        for mark, run in zip(marks, runs, strict=True)
        if len(run) >= _LOOP_MIN_REPEATS
    ]


def _span_gap_mark(gap: str) -> str | None:
    """What `gap` holds between two spans, or None when it cannot divide copies.

    Whitespace of any kind is normalized, so "" means whitespace alone. A line
    break divides nothing: marker writes a span on one line.
    """
    if "\n" in gap:
        return None
    mark = " ".join(gap.split())
    if len(mark) > _SPAN_RUN_MAX_GAP:
        return None
    if any(ch in _SPAN_RUN_GAP_STOPCHARS for ch in mark):
        return None
    return mark


def _is_inline_span(span: str) -> bool:
    """True when `span` is a closed `$...$` pair, not a display span or a tail."""
    return (
        len(span) > 2
        and span.startswith("$")
        and not span.startswith("$$")
        and span.endswith("$")
    )


def _span_loop_cuts(
    line: str, run: list[tuple[int, int]], min_repeats: int
) -> list[tuple[int, int]]:
    """The ranges to cut from `line` so each loop inside `run` keeps one cycle.

    A cut takes the repeats with their gaps, from the end of the kept cycle.
    """
    spans = [line[start:end] for start, end in run]
    cuts: list[tuple[int, int]] = []
    index = 0
    while index < len(spans):
        loop = _span_loop_at(spans, index, min_repeats)
        if loop is None:
            index += 1
            continue
        period, end = loop
        cuts.append((run[index + period - 1][1], run[end - 1][1]))
        index = end
    return cuts


def _span_loop_at(
    spans: list[str], index: int, min_repeats: int
) -> tuple[int, int] | None:
    """The cycle `spans` repeats from `index` on, as `(period, end)`, or None.

    The shortest period wins. The cycle needs an alphanumeric. A cycle with
    math markup is a loop at `min_repeats`; a row of bare values (`$0$ $0$`)
    needs `_SPAN_RUN_PLAIN_MIN_REPEATS`.
    """
    for period in range(1, _SPAN_RUN_MAX_PERIOD + 1):
        end = index + period
        while (
            end + period <= len(spans)
            and spans[end : end + period] == spans[index : index + period]
        ):
            end += period
        repeats = (end - index) // period
        if repeats < min_repeats:
            continue
        cycle = "".join(spans[index : index + period])
        if not any(ch.isalnum() for ch in cycle):
            continue
        if _is_math_loop_unit(cycle) or repeats >= _SPAN_RUN_PLAIN_MIN_REPEATS:
            return period, end
    return None
