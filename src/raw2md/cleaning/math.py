"""Rules that repair what a converter made of the source's formulas.

The coordinator runs them in this order: reclose a display span and an inline
span that a trailing backslash glued shut, keep a table cell's display math on
its row, defuse false math around a text-mode environment, rejoin a formula
cut into several spans, drop HTML tags inside a span, normalize for KaTeX,
lift a legend's prose out of a display span, promote a paragraph formula, fold
an equation number into `\\tag{}`, unwrap a single-glyph span, drop a
content-free span, drop an orphan sizing command, close an unpaired
`\\left`/`\\right`, and clear the tail behind a display closer;
`separate_glued_inline_spans` runs after every rule that reads span bounds.
Each repairs markup only; recognition damage needs judgment and goes to the
reporting pass.

`collapse_repeated_spans`, `drop_loop_residue`, and
`resolve_unclosed_environment_spans` serve the reporting pass instead. Span
detection is shared with the evaluator through `mdtext`.
"""

from __future__ import annotations

import logging
import re

from raw2md.cleaning.segments import LIST_ITEM_RE, is_blank_at
from raw2md.mdtext.formulas import (
    MathEnvDefects,
    is_broken_math_span,
    is_formula_continuation,
    is_valid_math,
    math_env_argument_open,
    math_env_defects,
    text_mode_math,
)
from raw2md.mdtext.links import mask_addresses
from raw2md.mdtext.loops import math_repeated_span_cuts
from raw2md.mdtext.math_spans import math_span_content, math_span_ranges, math_spans
from raw2md.mdtext.pages import page_mark_number
from raw2md.mdtext.zones import Segment, inline_code_ranges, mask_inline_code

_logger = logging.getLogger("raw2md")

# Mirrors the evaluator's span patterns, so the cleaner normalizes exactly the
# zones it validates. A backslash before a delimiter escapes it.
_DISPLAY_MATH_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$([^\n]+?)(?<!\\)\$")

# One unescaped `$$`, opener or closer, to track span state past a closer that
# damage hid.
_DISPLAY_DELIM_RE = re.compile(r"(?<!\\)\$\$")

# What a formula can end on before a glued closer: whitespace, an unfinished
# group's open brace, or `\right.`. A closing bracket, a digit, and a letter
# stay out: a printed dollar sits flush against them (`(5)\$`). Each
# alternative is fixed width, as a lookbehind requires.
_FORMULA_END_LOOKBEHIND = r"(?:(?<=[\s{])|(?<=\\right\.))"

# A display closer glued shut by a backslash run, explicit spaces among it.
# `(?!\$)` leaves `\$$$`, a printed dollar then the real closer, to pair.
_RUNAWAY_DISPLAY_CLOSE_RE = re.compile(
    _FORMULA_END_LOOKBEHIND + r"\\(?:[ \t]*\\)*\$\$(?!\$)"
)

# A closing bracket before an inline span's glued closer marks a printed amount
# (`(5)\$`). A letter is not excluded, since an inline formula often ends on
# one; `is_valid_math` decides where the formula ends.
_INLINE_CLOSE_PRINTED_AMOUNT = frozenset(")]}")

# The whitespace before `\label{...}` goes with it, so the tail trim never
# touches whitespace it did not orphan.
_LABEL_RE = re.compile(r"[ \t]*\\label\{[^}]*\}")

# A pipe-table row by its leading border, which pandoc and marker always emit;
# this matches a row not yet well-formed enough to confirm as a table.
_TABLE_ROW_START_RE = re.compile(r"^[ \t]*\|")

# A line break followed by another row's border: a display match reached past
# its own row. Adjacent rows carry no blank line between them.
_ROW_BOUNDARY_RE = re.compile(r"\n[ \t]*\|")

# A span's line break with the indent around it, collapsed to one space.
_MATH_LINE_BREAK_RE = re.compile(r"[ \t]*\n[ \t]*")

# pandoc's separator between adjacent inline elements; beside an unwrapped span
# it is leftover markup.
_SEPARATOR_COMMENT = "<!-- -->"

# LaTeX a docx equation editor writes for a single prose glyph. Closed on
# purpose: `R`, `D`, `\theta` are real one-letter variables. `{^\circ}` is the
# editor's bare degree sign.
_SINGLE_GLYPH_COMMANDS = {
    "\\varnothing": "∅",  # author's own substitute for the diameter sign
    "\\circ": "°",
    "{^\\circ}": "°",
}

# The same glyphs emitted bare inside `$...$`.
_SINGLE_GLYPH_BARE = frozenset({"℃", "°", "∅"})

# Spacing the editor puts beside the glyph inside the span: presentation, not a
# second symbol.
_LATEX_SPACERS = ("\\qquad", "\\quad", "\\;", "\\,", "\\ ")

# Spacing commands without a letter in their name. A run of only these is what
# a recognition loop leaves (`\!\!\!\!`); a bare operator (`+`) is the
# document's own symbol and never matches.
_LETTERLESS_SPACERS = ("\\!", "\\,", "\\;", "\\ ")

# `content` is content-free when it is nothing but a run of the spacers above,
# whitespace included between them.
_SPACER_RESIDUE_RE = re.compile(
    "(?:" + "|".join(re.escape(spacer) for spacer in _LETTERLESS_SPACERS) + r"|\s)+"
)

# Grouping delimiters that tell a whole expression from a cut fragment. Braces
# are markup, and `is_valid_math` already refuses unbalanced ones.
_GROUP_OPENERS = frozenset("([")
_GROUP_CLOSERS = frozenset(")]")

# Macros whose argument is text. `\mbox` is here because a body can reach a
# rule before normalization rewrites it.
_TEXT_MACROS = ("\\text{", "\\mbox{")

# Every macro a converter sets prose in, the shaped ones included: here the
# wrapping itself comes off.
_PROSE_MACROS = ("\\text{", "\\textit{", "\\textbf{", "\\textrm{", "\\mbox{")

# Two words in one macro argument: a legend's prose, as opposed to a formula's
# own text mode (`\text{\tiny MAX}`, a one-word condition).
_PROSE_WORD_PAIR_RE = re.compile(r"[^\W\d_]{3,}\s+[^\W\d_]{3,}")

# Share of a span's characters in prose above which it reads as a legend entry.
# Observed entries run from 0.6 to 0.8, and just under 0.4 when the symbol is a
# full fraction; a formula with a worded condition reaches a third at most once
# the guards refuse the shapes that are formulas regardless.
_PROSE_SHARE_MIN = 0.35

# The dash, in each width, that a page prints between a symbol and its
# explanation.
_LEGEND_DASHES = frozenset("-–—")  # noqa: RUF001  # the dash in each width

# Entry punctuation that goes with the prose when it ends a math run. Narrower
# than `_CLINGING`: a closing bracket ends a formula (`\right)`) as often as a
# sentence.
_LEGEND_MARKS = frozenset(",.;:") | _LEGEND_DASHES

# Either sizing command may size a delimiter the other does not match
# (`\right.` prints nothing), so the sized character belongs to the command,
# not to the formula's own grouping.
_SIZING_COMMANDS = ("\\left", "\\right")

# What a sizing command may size; `\leftarrow`'s letters are not one.
_SIZED_DELIMITERS = _GROUP_OPENERS | _GROUP_CLOSERS | frozenset(".|")

# Word-bounded, so `\leftarrow` is never a sizing command.
_SIZING_TOKEN_RE = re.compile(r"\\left\b|\\right\b")

# A delimiter written as a command (`\langle`, `\{`, `\|`); whether it sizes is
# the renderer's answer.
_DELIMITER_NAME_RE = re.compile(r"\\(?:[a-zA-Z]+|.)")

# Punctuation that belongs to the word before it: a span removed from between
# them leaves no space.
_CLINGING = frozenset(",.;:!?%)]}»…")

# Equation numbering (`12`, `D13`, `6.7`, `3a`). No symbols, so a trailing
# condition (`1 \le i \le n-1`) stays content.
_NUMBERING = r"[A-Za-z]{0,2}\d+(?:\.\d+)*[a-z]?"

# On a line of its own the numbering may carry a chapter (`III.24`, `2-10`);
# inside a span `(2-10)` could be a subtraction, so the tail keeps the narrower
# form.
_NUMBER_LINE_NUMBERING = rf"(?:(?:[IVXLC]+|\d+)[.\-])?{_NUMBERING}"

# The equation number marker leaves as text at a span's tail, held off by
# spacing. `_split_equation_number` re-derives the match from `group(0)`.
_EQUATION_NUMBER_RE = re.compile(
    rf"(?:\\q?quad|\\[;,]|[ \t])[ \t]*\([ \t]*({_NUMBERING})[ \t]*\)$"
)

# The equation number on its own line directly under the block.
_NUMBER_LINE_RE = re.compile(
    rf"^[ \t]*\([ \t]*({_NUMBER_LINE_NUMBERING})[ \t]*\)[ \t]*$"
)

# The number a collapsed carrier table left behind a display closer. It is all
# that stands there, so the wider line form applies; the parentheses may come
# escaped, since the cell was markdown text.
_CELL_NUMBER_RE = re.compile(rf"^\\?\([ \t]*({_NUMBER_LINE_NUMBERING})[ \t]*\\?\)$")

# A display formula's sentence mark stranded on the line below. A lone dash is
# not one: it means a range or an empty cell.
_STRANDED_TAIL = frozenset(",.;")

# A bracketed condition stranded under its block: bare (`[n \neq 1].`), wrapped
# whole (`$[a, b>0].$`), or holding a span (`[ $x^2 < a^2$ ]`).
_CONDITION_LINE_RE = re.compile(r"^\[(?P<body>[^\[\]]*)\][,.;]?$")

# A condition states a relation (`_RELATION_RE`), so a cross-reference
# (`[See 48.32.]`) stays a paragraph. Conditions and paragraph formulas share
# one relation set, so the two readings cannot drift apart.

# And a condition holds no prose: no word of three letters or more. Two letters
# stay allowed (`ab`, `kg`).
_CONDITION_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
_CONDITION_WORD_RE = re.compile(r"[^\W\d_]{3,}")

# Markup a span would print as characters: an HTML tag (`a<sup>2</sup> < 1`)
# or a bold run.
_CONDITION_MARKUP_RE = re.compile(r"</?[A-Za-z][^>]*>|\*\*")

# Longest condition, in characters. The longest printed condition measured is
# 27; a longer bracketed line is an enumeration or a paragraph.
_CONDITION_MAX = 40

# Holds a rejoined condition off the formula, as marker holds a number off; a
# plain space collapses in math mode.
_CONDITION_SPACER = "\\quad"

# The indentation at which markdown reads a line as a code block rather than as
# a paragraph, where no list item is open above it.
_CODE_INDENT = 4

# The relation that makes a line an equation or a condition: comparisons,
# equivalences, set and geometric relations, and arrows. Word-bounded (`\to` is
# not read in `\top`), with a longer spelling before the shorter it opens with.
_RELATION_RE = re.compile(
    r"[<>=]|\\(?:"
    r"neq|ne|leqslant|geqslant|leq|le|geq|ge|ll|gg|"
    r"equiv|approx|cong|simeq|sim|propto|"
    r"subseteq|subsetneq|subset|supseteq|supsetneq|supset|notin|in|ni|"
    r"perp|parallel|"
    r"longrightarrow|longleftarrow|longmapsto|Longrightarrow|Longleftrightarrow|"
    r"to|gets|rightarrow|leftarrow|leftrightarrow|Rightarrow|Leftrightarrow|mapsto"
    r")(?![A-Za-z])"
)

# Content length, in characters, past which a relation stands between real
# subexpressions and a page displays it. A relation between two bare atoms
# (`a = b`) runs to about a dozen.
_PARAGRAPH_FORMULA_MIN = 16

# A `\tag{}` anywhere, and one at the very end: both say the equation is closed.
_TAG_RE = re.compile(r"\\tag\{")
_TAG_TAIL_RE = re.compile(r"[ \t]*\\tag\{[^{}]*\}[ \t]*$")

# A LaTeX command at the head of a span's content and at its tail -- the two
# positions a seam puts an operator in.
_COMMAND_HEAD_RE = re.compile(r"\\[A-Za-z]+")
_COMMAND_TAIL_RE = re.compile(r"\\([A-Za-z]+)$")

# Operators a typesetter repeats on both ends of a formula broken across lines;
# a subset of the `is_formula_continuation` tokens. A closer at both ends is two
# closers.
_SEAM_SYMBOLS = ("=", "+", "-")
_SEAM_COMMANDS = frozenset(
    {
        "pm",
        "mp",
        "times",
        "cdot",
        "le",
        "leq",
        "ge",
        "geq",
        "approx",
        "equiv",
    }
)

# Null delimiters that hold one formula open across a printed line break.
_NULL_RIGHT = "\\right."
_NULL_LEFT = "\\left."

# What plain TeX writes an equation number with, and what KaTeX understands
# instead: the same number in the same place, in a command a browser renders.
_EQNO_RE = re.compile(r"[ \t]*\\eqno[ \t]*\(([^()]*)\)")

# A straight double quote standing for a double prime, in two shapes: after a
# single-letter symbol or a command (`t"`, `\alpha"`), and opening a
# superscript group (`^{"}`). After a letter run it is prose; after a backslash
# it is an accent (`\"{a}`).
_QUOTE_AFTER_SYMBOL_RE = re.compile(r'(?:(?<![^\W\d_\\])[^\W\d_]|\\[A-Za-z]+)"')
_QUOTE_SUPERSCRIPT_RE = re.compile(r'\^\{("+)')

# The macros whose argument is text rather than mathematics, where a quote is
# the quote it looks like; an equation's number is set in text mode too.
_TEXT_MODE_ARGUMENT_RE = re.compile(r"\\(?:text[a-z]*|mbox|tag\*?)[ \t]*\{")


def fix_table_math(seg_list: list[Segment]) -> list[Segment]:
    """Keep a pipe-table row's display math on one line and escape its bare pipes.

    A GFM row is one line and every bare `|` is a cell border, so a cell's
    `$$...$$` that spans lines or holds `\\left|` breaks the row. Display spans
    only: inline `$5 | $6` is two cells' amounts, while pandoc writes `$$` only
    for a formula. Runs per run of plain lines and before `normalize_math`, so
    later line rules see one row. `unescape_math_pipes` undoes the escape when a
    rule takes the row apart.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed_text = _fix_table_math_zones(run_text)
        out.extend((fixed_line, False) for fixed_line in fixed_text.split("\n"))
    return out


def _fix_table_math_zones(text: str) -> str:
    """Fix every display span of `text` that opens on a pipe-table row.

    Spans are found with inline code masked, so a cell quoting `` `$$` `` pairs
    into no false span; the offsets still address `text`.
    """
    masked = mask_inline_code(text)
    pieces: list[str] = []
    last = 0
    for start, end in math_span_ranges(masked):
        span = text[start:end]
        pieces.append(text[last:start])
        if (
            _is_closed_display_span(masked[start:end])
            and _opens_on_table_row(masked, start)
            and not _leaves_its_own_row(span)
        ):
            pieces.append(_fix_table_math_span(span))
        else:
            pieces.append(span)
        last = end
    pieces.append(text[last:])
    return "".join(pieces)


def _is_closed_display_span(span: str) -> bool:
    """True when `span` is a real `$$...$$` pair.

    `math_span_ranges` also reports an unclosed tail that ends on an escaped
    `$`, which a plain endswith check would read as closed.
    """
    return bool(_DISPLAY_MATH_RE.fullmatch(span))


def _leaves_its_own_row(span: str) -> bool:
    """True when `span` crosses a blank line or another row's leading border.

    A cell's wrapped formula does neither, so such a span paired with an
    unrelated `$$` after its own closer was lost; it is left for the reporting
    pass. A continuation line opening with an absolute-value bar reads the same
    and stays unjoined: telling it apart needs the table's column count.
    """
    return bool("\n\n" in span or _ROW_BOUNDARY_RE.search(span))


def _opens_on_table_row(text: str, pos: int) -> bool:
    """True when the line of `text` holding offset `pos` starts a pipe-table row."""
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", line_start)
    if line_end == -1:
        line_end = len(text)
    return bool(_TABLE_ROW_START_RE.match(text[line_start:line_end]))


def _fix_table_math_span(span: str) -> str:
    """`span` joined onto one line with its bare pipes escaped.

    A matrix row separator is the explicit `\\\\`, so a source line break means
    nothing to the renderer.
    """
    content = span[2:-2]
    content = _MATH_LINE_BREAK_RE.sub(" ", content)
    content = _escape_bare_pipes(content)
    return f"$${content}$$"


def _escape_bare_pipes(content: str) -> str:
    """`content` with every bare `|` escaped to `\\|`; an escaped one is kept.

    A backslash and its next character are consumed as a pair, so `\\\\|` reads
    as an escaped backslash and a bare bar.
    """
    out: list[str] = []
    i = 0
    length = len(content)
    while i < length:
        ch = content[i]
        if ch == "\\" and i + 1 < length:
            out.append(content[i : i + 2])
            i += 2
            continue
        if ch == "|":
            out.append("\\|")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def unescape_math_pipes(line: str) -> str:
    """`line` with the pipe escapes taken back off its display spans.

    Off the row, `\\|` is the norm operator rather than the bar the cell held.
    Display spans only, found with inline code masked, as the escape found them.
    """
    masked = mask_inline_code(line)
    pieces: list[str] = []
    last = 0
    for match in _DISPLAY_MATH_RE.finditer(masked):
        start, end = match.span()
        pieces.append(line[last:start])
        pieces.append(f"$${_unescape_pipes(line[start + 2 : end - 2])}$$")
        last = end
    pieces.append(line[last:])
    return "".join(pieces)


def _unescape_pipes(content: str) -> str:
    """`content` with every `\\|` back to `|`, scanned like `_escape_bare_pipes`."""
    out: list[str] = []
    i = 0
    length = len(content)
    while i < length:
        ch = content[i]
        if ch == "\\" and i + 1 < length:
            out.append("|" if content[i + 1] == "|" else content[i : i + 2])
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def reclose_runaway_display_spans(seg_list: list[Segment]) -> list[Segment]:
    r"""Close a display span whose own trailing backslash glued its `$$` shut.

    marker can end a formula with spaces and a backslash flush against `$$`
    (`\$$`); the closer never pairs, and every heading and formula up to the
    next opener reads as one math block. Inside an open span, a backslash run
    glued to `$$` on a formula end, reached before any unescaped `$$`, goes
    whole and `$$` closes there. Runs before every span-scoped rule, since each
    reads span bounds. Inline code is masked; idempotent.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed = _reclose_runaway_display(run_text)
        out.extend((fixed_line, False) for fixed_line in fixed.split("\n"))
    return out


def _reclose_runaway_display(text: str) -> str:
    """`text` with every backslash-glued display closer restored to a plain `$$`.

    Offsets come from the inline-code mask, which has the same length as `text`.
    """
    scan = mask_inline_code(text)
    pieces: list[str] = []
    pos = 0
    while True:
        opener = _DISPLAY_DELIM_RE.search(scan, pos)
        if opener is None:
            pieces.append(text[pos:])
            return "".join(pieces)
        pieces.append(text[pos : opener.end()])
        cursor = opener.end()
        real_close = _DISPLAY_DELIM_RE.search(scan, cursor)
        glued = _RUNAWAY_DISPLAY_CLOSE_RE.search(scan, cursor)
        if glued is not None and (
            real_close is None or glued.end() <= real_close.start()
        ):
            pieces.append(text[cursor : glued.start()].rstrip(" \t"))
            pieces.append("$$")
            pos = glued.end()
        elif real_close is not None:
            pieces.append(text[cursor : real_close.end()])
            pos = real_close.end()
        else:
            pieces.append(text[cursor:])
            return "".join(pieces)


def reclose_runaway_inline_spans(seg_list: list[Segment]) -> list[Segment]:
    r"""Close an inline span whose own backslash glued its `$` closer shut.

    The office docx route can write `$X$ word` as `$X\$word`. Each line is read
    alone. The first glued `$` after an opener is the closer, unless a digit or
    a closing bracket stands before it or a digit after it: a printed amount
    (`5\$`, `(5)\$`, `\$5`). The content up to it, past trailing legend
    punctuation, must render. The closer is restored with one space after it.
    Inline code and whole display spans are masked. Runs beside the display
    rule; idempotent.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, protected))
            continue
        out.append((_reclose_runaway_inline_line(line), False))
    return out


def _reclose_runaway_inline_line(line: str) -> str:
    """`line` with every backslash-glued inline closer restored to a plain `$`.

    Offsets come from a copy with inline code and then whole display spans
    blanked; masking code first keeps a `` `$$` `` quoted twice from pairing
    into a display span across the prose between.
    """
    scan = _DISPLAY_MATH_RE.sub(_blank_display_span, mask_inline_code(line))
    pieces: list[str] = []
    pos = 0
    length = len(scan)
    while pos < length:
        boundary = _next_inline_boundary(scan, pos)
        if boundary is None:
            pieces.append(line[pos:])
            break
        kind, idx = boundary
        if kind == "escaped":
            # A printed dollar with no span open to close.
            pieces.append(line[pos : idx + 2])
            pos = idx + 2
            continue
        pieces.append(line[pos:idx])
        closer = _next_inline_boundary(scan, idx + 1)
        if closer is None:
            pieces.append(line[idx:])
            break
        close_kind, close_idx = closer
        if close_kind == "real":
            pieces.append(line[idx : close_idx + 1])
            pos = close_idx + 1
            continue
        fixed = _close_escaped_inline_span(line, idx, close_idx)
        if fixed is None:
            pieces.append(line[idx : close_idx + 2])
            pos = close_idx + 2
            continue
        pieces.append(fixed)
        pos = close_idx + 2
        # The space `_close_escaped_inline_span` put back replaces whatever
        # whitespace the glue left; skip it.
        while pos < length and line[pos] in " \t":
            pos += 1
    return "".join(pieces)


def _blank_display_span(match: re.Match[str]) -> str:
    """`match`, a whole `$$...$$` on one line, blanked to spaces of its length."""
    return " " * len(match.group(0))


def _next_inline_boundary(text: str, pos: int) -> tuple[str, int] | None:
    r"""The next inline delimiter in `text` from `pos`: kind and index, or None.

    The kind is "real", indexing the `$`, or "escaped", indexing the backslash a
    fix removes. A backslash and the next character are read as a pair. `\$$` is
    a display closer's escape and is stepped over.
    """
    i = pos
    length = len(text)
    while i < length:
        char = text[i]
        if char == "\\":
            escapes_dollar = i + 1 < length and text[i + 1] == "$"
            glues_display = i + 2 < length and text[i + 2] == "$"
            if escapes_dollar and not glues_display:
                return ("escaped", i)
            i += 2
            continue
        if char == "$":
            return ("real", i)
        i += 1
    return None


def _close_escaped_inline_span(
    line: str, open_pos: int, backslash_pos: int
) -> str | None:
    r"""The replacement for `line[open_pos:backslash_pos+2]`, or None to leave it.

    A digit or a closing bracket before the glued `\$`, or a digit after it, is
    a printed amount. Otherwise the content, past trailing legend punctuation,
    must render to count as the formula this closer belongs to. The trailing
    space of the result replaces the whitespace the caller skips.
    """
    body = line[open_pos + 1 : backslash_pos]
    if body and (body[-1].isdigit() or body[-1] in _INLINE_CLOSE_PRINTED_AMOUNT):
        return None
    if line[backslash_pos + 2 : backslash_pos + 3].isdigit():
        return None
    formula, marks = _split_legend_marks(body.rstrip())
    if not formula or not is_valid_math(formula):
        return None
    return f"${formula}${marks} "


def defuse_false_math(seg_list: list[Segment]) -> list[Segment]:
    """Strip the math delimiters off a line whose "formula" is a text block.

    A span declaring a text-mode environment (`text_mode_math`) is a printed
    table the recognition wrapped in `$`. Every unescaped `$` on the line goes,
    since one survivor would pair with a real formula further down. The text is
    untouched and nothing is reported. Runs before the normalization.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected or not text_mode_math(line):
            out.append((line, protected))
            continue
        out.append((_strip_math_delimiters(line), False))
    return out


def _strip_math_delimiters(line: str) -> str:
    """Remove every unescaped `$` outside an inline code span from `line`.

    Trailing whitespace a removed delimiter leaves goes too.
    """
    quoted = inline_code_ranges(line)
    out: list[str] = []
    i = 0
    length = len(line)
    while i < length:
        if line[i] == "\\":
            out.append(line[i : i + 2])  # an escaped character, `\$` included
            i += 2
            continue
        if line[i] == "$" and not any(start <= i < end for start, end in quoted):
            i += 1
            continue
        out.append(line[i])
        i += 1
    return "".join(out).rstrip()


def lift_prose_from_display_math(seg_list: list[Segment]) -> list[Segment]:
    r"""Lift the prose a converter pulled into a display span back out of it.

    Recognition reads a legend entry (symbol, dash, explanation) as one display
    span with the explanation in `\text{}`; a dropped or doubled closer on such
    entries shifts every display pairing after it. A line qualifies when it is
    one `$$` span whole, mostly prose (`_PROSE_SHARE_MIN`) in real words, with a
    dash after the leading formula, and holds no environment, `\tag{}`, or `\\`
    break. An entry without a closer qualifies only above a line that opens a
    display span. What stays a span must render and close its groups, and a
    command inside the prose leaves the line alone. Idempotent.
    """
    out: list[Segment] = []
    for index, (line, protected) in enumerate(seg_list):
        if protected:
            out.append((line, protected))
            continue
        below = _plain_line_below(seg_list, index)
        lifted = _lift_prose_line(line, below)
        out.append(((line if lifted is None else lifted), False))
    return out


def _plain_line_below(seg_list: list[Segment], index: int) -> str:
    """The plain line under `index`; empty below a protected zone or at the end."""
    below = index + 1
    if below >= len(seg_list) or seg_list[below][1]:
        return ""
    return seg_list[below][0]


def _lift_prose_line(line: str, below: str) -> str | None:
    """`line` rewritten as the legend entry it is, or None when it is not one."""
    core = line.strip()
    if not core.startswith("$$"):
        return None
    content, closed = _whole_line_span_content(core)
    if content is None:
        return None
    if not closed and not _opens_a_display_span(below):
        return None
    runs = _prose_runs(content)
    if not _reads_as_legend(runs):
        return None
    lifted = _lift_runs(runs)
    if lifted is None:
        return None
    indent = line[: len(line) - len(line.lstrip())]
    return (indent + lifted).rstrip()


def _whole_line_span_content(core: str) -> tuple[str | None, bool]:
    """The content of the display span that is the whole of `core`, and its close.

    The closer is the run of `$` the line ends on, since damage leaves one entry
    without a closer and another with it doubled. A display delimiter inside
    means more than one span.
    """
    end = len(core)
    while end > 0 and core[end - 1] == "$" and not _is_escaped(core, end - 1):
        end -= 1
    content = core[2:end]
    if not content.strip():
        return None, False
    if _DISPLAY_DELIM_RE.search(mask_inline_code(content)):
        return None, False
    return content, end < len(core)


def _opens_a_display_span(line: str) -> bool:
    """True when `line` opens a display span with content, not a lone closer."""
    core = line.strip()
    return core.startswith("$$") and bool(core[2:].strip())


def _is_escaped(text: str, idx: int) -> bool:
    """True when the character at `idx` is escaped by an odd run of backslashes."""
    backslashes = 0
    cursor = idx - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _prose_runs(content: str) -> list[tuple[bool, str]]:
    """`content` cut into `(is_prose, text)` runs at its prose macros.

    An argument is taken whole by brace depth. One whose brace never closes runs
    to the end: the same damage cut the span's own closer.
    """
    runs: list[tuple[bool, str]] = []
    start = 0
    cursor = 0
    length = len(content)
    while cursor < length:
        if content[cursor] != "\\":
            cursor += 1
            continue
        macro = next(
            (name for name in _PROSE_MACROS if content.startswith(name, cursor)), None
        )
        if macro is None:
            cursor += 2  # an escape or a command of the formula's own
            continue
        end = _matching_brace(content, cursor + len(macro) - 1)
        runs.append((False, content[start:cursor]))
        if end is None:
            runs.append((True, content[cursor + len(macro) :]))
            return runs
        runs.append((True, content[cursor + len(macro) : end]))
        cursor = end + 1
        start = cursor
    runs.append((False, content[start:]))
    return runs


def _reads_as_legend(runs: list[tuple[bool, str]]) -> bool:
    """True when the runs of one span read as a printed legend entry."""
    prose = [text for is_prose, text in runs if is_prose]
    if not any(_PROSE_WORD_PAIR_RE.search(text) for text in prose):
        return False
    # Without the dash, the prose is the formula's own qualifier.
    if not _LEGEND_DASHES & set(_split_legend_marks(runs[0][1].strip())[1]):
        return False
    # A command in the prose would stand in the body as bare markup.
    if any("\\" in text for text in prose):
        return False
    math = "".join(text for is_prose, text in runs if not is_prose)
    if any(token in math for token in ("\\tag{", "\\begin{", "\\end{", "\\\\")):
        return False
    prose_chars = sum(len(text) for text in prose)
    math_chars = sum(len(text.strip()) for is_prose, text in runs if not is_prose)
    return prose_chars >= _PROSE_SHARE_MIN * (prose_chars + math_chars)


def _lift_runs(runs: list[tuple[bool, str]]) -> str | None:
    """The runs of a legend entry as one line of prose, or None to leave it.

    The first run must be a formula that renders on its own; a span that is
    prose end to end belongs to the false-math rule.
    """
    lifted = _lift_math_run(runs[0][1], is_head=True)
    if lifted is None:
        return None
    for is_prose, text in runs[1:]:
        piece = text if is_prose else _lift_math_run(text, is_head=False)
        if piece is None:
            return None
        # The two sides of a removed boundary each carried a space; keep one.
        while lifted.endswith(" ") and piece.startswith(" "):
            piece = piece[1:]
        lifted += piece
    return lifted


def _lift_math_run(run: str, *, is_head: bool) -> str | None:
    """`run` as it stands outside a display span, or None when it cannot stand.

    A run without a letter or digit is the legend's punctuation and stays text;
    a math run becomes an inline span, its outer spacing kept outside.
    """
    body = run.strip()
    if not body or not any(char.isalnum() for char in body):
        return None if is_head else run
    lead = run[: len(run) - len(run.lstrip())]
    trail = run[len(run.rstrip()) :]
    formula, marks = _split_legend_marks(body)
    # Trim the spacer the normalization would trim later, so it does not decide
    # validity here.
    formula = _trim_math_tail(formula)
    if not formula or not is_valid_math(formula) or not _groups_closed(formula):
        return None
    return f"{lead}${formula}${marks}{trail}"


def _split_legend_marks(body: str) -> tuple[str, str]:
    """`body` split into the formula and the legend punctuation trailing it.

    The spacing before a mark goes with the mark.
    """
    formula = body
    marks = ""
    while formula and formula[-1] in _LEGEND_MARKS:
        marks = formula[-1] + marks
        formula = formula[:-1]
        stripped = formula.rstrip()
        marks = formula[len(stripped) :] + marks
        formula = stripped
    return formula, marks


def reunite_split_formulas(seg_list: list[Segment]) -> list[Segment]:
    """Join back a display formula the engine cut into several `$$` spans.

    Every piece is a display span alone on its line, and every piece after the
    first opens with a token no formula opens with (`is_formula_continuation`)
    or follows a null-delimiter seam. Blank lines stay in the run; any other
    line ends it. A head that is numbered or ends on its sentence mark is
    finished, unless it ends on a dangling operator: a typesetter can print the
    number beside the first half and repeat the operator after the break, so the
    operator is kept once and the number moves to the end.
    """
    out: list[Segment] = []
    idx = 0
    total = len(seg_list)
    spans = seams = 0
    while idx < total:
        line, protected = seg_list[idx]
        if protected or not _is_lone_display_span(line):
            out.append((line, protected))
            idx += 1
            continue
        joined, last, closed = _reunite_from(seg_list, idx)
        if not closed:
            out.append((line, protected))
            idx += 1
            continue
        indent = line[: len(line) - len(line.lstrip())]
        out.append((f"{indent}{joined}", False))
        spans += 1
        seams += closed
        idx = last + 1
    if spans:
        _logger.info("display formulas reunited: %d over %d seams", spans, seams)
    return out


def _reunite_from(seg_list: list[Segment], start: int) -> tuple[str, int, int]:
    """The span the run opening at `start` makes, its last line, and its seams.

    Zero seams means the piece at `start` stands alone.
    """
    content = math_span_content(seg_list[start][0].strip())
    numbers: list[str] = []
    last = start
    seams = 0
    cursor = start + 1
    while cursor < len(seg_list) and not _states_a_finished_equation(content):
        line, protected = seg_list[cursor]
        if not line.strip():
            cursor += 1
            continue
        if protected or not _is_lone_display_span(line):
            break
        piece = math_span_content(line.strip())
        if _breaks_on_null_delimiters(content, piece):
            content = _join_over_null_delimiters(content, piece)
        elif is_formula_continuation(line):
            content = _join_at_seam(content, piece, numbers)
        else:
            break
        last = cursor
        seams += 1
        cursor += 1
    if not seams:
        return "", start, 0
    tail = "".join(f" {number}" for number in numbers)
    return f"$${content}{tail}$$", last, seams


def _is_lone_display_span(line: str) -> bool:
    """True when `line` is one closed display span and nothing else.

    The closer is required: joining the next line onto an unclosed region would
    put text no delimiter bounded inside a formula.
    """
    core = line.strip()
    return (
        core.startswith("$$")
        and core.endswith("$$")
        and len(core) > 4
        and math_spans(core) == [core]
    )


def _states_a_finished_equation(content: str) -> bool:
    """True when `content` states an equation the page has already closed.

    A number, a `\\tag{}`, or a closing full stop or semicolon ends it, unless
    the formula ends on a dangling operator.
    """
    body, number = _split_equation_number(content)
    if _closes_its_statement(body):
        return True
    if not number and not _TAG_RE.search(content):
        return False
    return _trailing_seam_operator(body) is None


def _closes_its_statement(content: str) -> bool:
    """True when `content` ends on a full stop or semicolon, not on `\\right.`."""
    text = content.rstrip()
    if not text.endswith((".", ";")):
        return False
    return not any(text.endswith(f"{command}.") for command in _SIZING_COMMANDS)


def _trim_seam_piece(piece: str) -> str:
    """`piece` with its outer whitespace off, keeping a spacing command's space.

    `\\ ` takes the space as its argument; a closer set against a bare trailing
    backslash would escape into the content.
    """
    return _rstrip_keeping_spacer(piece.lstrip())


def _rstrip_keeping_spacer(text: str, chars: str | None = None) -> str:
    """`text` with its trailing whitespace off, keeping the space of a `\\ `.

    The space is the spacing command's argument: stripped, the text ends on a
    lone backslash that escapes whatever the caller sets against it. An even
    backslash run is `\\\\` line breaks and keeps nothing. A caller inserting
    into a span passes `chars=" \\t"`, since the newline ending a TeX `%`
    comment is content.
    """
    trimmed = text.rstrip() if chars is None else text.rstrip(chars)
    if trimmed == text:
        return trimmed
    backslash_run = len(trimmed) - len(trimmed.rstrip("\\"))
    return f"{trimmed} " if backslash_run % 2 == 1 else trimmed


def _join_at_seam(head: str, tail: str, numbers: list[str]) -> str:
    """Join `tail` onto `head`, holding aside the number printed at the seam.

    The number moves to the end only where the seam repeats its operator, which
    proves the head carries on; elsewhere it stays where it was printed.
    """
    tail = _trim_seam_piece(tail)
    body, number = _split_equation_number(head)
    operator = _repeated_seam_operator(body, tail)
    if operator is None:
        return f"{head.rstrip()} {tail}"
    if number:
        numbers.append(number)
    return f"{body[: -len(operator)].rstrip()} {tail}"


def _breaks_on_null_delimiters(head: str, tail: str) -> bool:
    """True when `head` ends on `\\right.` and `tail` opens on `\\left.`.

    A delimiter that prints nothing closes nothing a reader sees, so the pair is
    a printed line break. The head is read past its closer's spacing residue.
    """
    return _trim_math_tail(head).endswith(_NULL_RIGHT) and tail.lstrip().startswith(
        _NULL_LEFT
    )


def _join_over_null_delimiters(head: str, tail: str) -> str:
    """Join `tail` onto `head`, dropping the null delimiters that held the break.

    The real sizing pair the halves state pairs across the join once the null
    ones go; nothing else moves. The spacing before the head's closer goes too.
    """
    body = _rstrip_keeping_spacer(_trim_math_tail(head)[: -len(_NULL_RIGHT)])
    rest = _trim_seam_piece(tail.lstrip()[len(_NULL_LEFT) :])
    return f"{body} {rest}"


def _split_equation_number(content: str) -> tuple[str, str]:
    """`content` without the equation number at its end, and that number.

    Either the `\\tag{...}` marker writes or the parenthesized text it leaves,
    which keeps the spacing command before it. Only a plain numbering is read,
    so a trailing condition (`(1 \\le i \\le n-1)`) stays content.
    """
    for pattern in (_TAG_TAIL_RE, _EQUATION_NUMBER_RE):
        match = pattern.search(content)
        if match is not None:
            return content[: match.start()].rstrip(), match.group(0).strip()
    return content.rstrip(), ""


def _trailing_seam_operator(content: str) -> str | None:
    """The binary operator `content` ends on, or None when it ends on a term."""
    text = content.rstrip()
    for symbol in _SEAM_SYMBOLS:
        if text.endswith(symbol):
            return symbol
    command = _COMMAND_TAIL_RE.search(text)
    if command is None or command.group(1) not in _SEAM_COMMANDS:
        return None
    return command.group(0)


def _repeated_seam_operator(head: str, tail: str) -> str | None:
    """The operator a typesetter printed on both ends of one seam, or None.

    A closing bracket at both ends is two closers of its own; dropping one would
    unbalance the formula.
    """
    operator = _trailing_seam_operator(head)
    if operator is None:
        return None
    text = tail.lstrip()
    if not operator.startswith("\\"):
        return operator if text.startswith(operator) else None
    command = _COMMAND_HEAD_RE.match(text)
    return operator if command is not None and command.group(0) == operator else None


def promote_paragraph_formula(seg_list: list[Segment]) -> list[Segment]:
    r"""Promote a lone inline formula standing as a whole paragraph to display.

    The line must be one closed inline span whole, open its own block, state a
    relation (`_RELATION_RE`), run past `_PARAGRAPH_FORMULA_MIN`, and render.
    Only the delimiters change. Below the span a blank line or a line the cut
    stranded (a sentence mark, a condition, a number) is allowed. Runs before
    `tag_equation_numbers`, so that stranded line folds into the promoted block.
    Idempotent.
    """
    out: list[Segment] = []
    promoted = 0
    for idx, (line, protected) in enumerate(seg_list):
        rewritten = None if protected else _promote_paragraph_line(line)
        if (
            rewritten is not None
            and _stands_as_paragraph(seg_list, idx)
            and not _reads_as_indented_code(seg_list, idx)
        ):
            out.append((rewritten, False))
            promoted += 1
        else:
            out.append((line, protected))
    if promoted:
        _logger.info("paragraph formulas promoted to display: %d", promoted)
    return out


def _promote_paragraph_line(line: str) -> str | None:
    r"""`line` as the display block its lone inline span makes, or None."""
    core = line.strip()
    if core.startswith("$$") or not core.startswith("$"):
        return None
    if math_spans(core) != [core]:
        return None
    match = _INLINE_MATH_RE.fullmatch(core)
    if match is None:
        return None
    content = match.group(1)
    if len(content.strip()) < _PARAGRAPH_FORMULA_MIN:
        return None
    if _RELATION_RE.search(content) is None:
        return None
    # A span that does not render is misrecognized prose as often as a formula;
    # a stage that judges decides.
    if not is_valid_math(content):
        return None
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}$${content}$$"


def _reads_as_indented_code(seg_list: list[Segment], idx: int) -> bool:
    """True when the line at `idx` is an indented code block, not nested content.

    Nothing else marks such a block, and promoting would rewrite a quoted
    sample. A list item over the indentation, or its indented continuation,
    means nesting; the paragraph above is read whole, since a list item's
    paragraph may continue on unindented lines.
    """
    line = seg_list[idx][0]
    indent = line[: len(line) - len(line.lstrip())]
    if "\t" not in indent and len(indent) < _CODE_INDENT:
        return False
    seen_content = False
    for above in range(idx - 1, -1, -1):
        text, protected = seg_list[above]
        if protected:
            # A protected zone keeps its container open by its own indentation.
            seen_content = True
            if text[:1].isspace():
                return False
            continue
        if not text.strip():
            # A blank line above the paragraph ends it with no marker in it.
            if seen_content:
                return True
            continue
        seen_content = True
        if LIST_ITEM_RE.match(text) is not None or text[:1].isspace():
            return False
    return True


def _stands_as_paragraph(seg_list: list[Segment], idx: int) -> bool:
    """True when the span at `idx` opens a block of its own.

    Above: a blank line, a protected zone, or the edge. Below: the same, or a
    line the cut stranded. Page marks are read through, since they exist only
    with inspection on and must not change the outcome.
    """
    above = _past_page_marks(seg_list, idx, -1)
    if not is_blank_at(seg_list, above):
        return False
    below = _past_page_marks(seg_list, idx, 1)
    if is_blank_at(seg_list, below):
        return True
    # The stranded line counts only directly under the block: the fold reads the
    # next physical line, so a line reached past a mark would stay unfolded.
    if below != idx + 1:
        return False
    return _stranded_under_paragraph(seg_list[below][0])


def _past_page_marks(seg_list: list[Segment], idx: int, step: int) -> int:
    """The first index from `idx` in direction `step` that is not a page mark."""
    pos = idx + step
    while 0 <= pos < len(seg_list) and page_mark_number(seg_list[pos][0]) is not None:
        pos += step
    return pos


def _stranded_under_paragraph(below: str) -> bool:
    """True when `below` is a line the cut strands under a displayed equation."""
    stripped = below.strip()
    return bool(
        stripped
        and (
            stripped[0] in _STRANDED_TAIL
            or _CONDITION_LINE_RE.match(stripped) is not None
            or _NUMBER_LINE_RE.match(stripped) is not None
        )
    )


def tag_equation_numbers(seg_list: list[Segment]) -> list[Segment]:
    r"""Fold a display formula's equation number, or rejoin its stranded tail.

    marker leaves a recognized number as a line under the block or as text at
    the span's tail; both fold into `\tag{}`. The cut also strands the closing
    sentence mark, a line opening with one, or a bracketed condition on the line
    below; each folds back inside the span, before the closer and any tag, and
    the remainder of an opening-mark line stays a paragraph. A block already
    tagged takes no second number. Only the line directly under the block, with
    no blank between, counts. Runs per run of plain lines.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    tail_count = line_count = strand_count = condition_count = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed_text, tail_n, line_n, strand_n, condition_n = _tag_zones(run_text)
        tail_count += tail_n
        line_count += line_n
        strand_count += strand_n
        condition_count += condition_n
        out.extend((fixed_line, False) for fixed_line in fixed_text.split("\n"))
    if tail_count or line_count:
        _logger.info(
            "equation numbers tagged: %d under the block, %d inside the span",
            line_count,
            tail_count,
        )
    if strand_count:
        _logger.info("stranded sentence marks rejoined: %d", strand_count)
    if condition_count:
        _logger.info("stranded conditions rejoined: %d", condition_count)
    return out


def _tag_zones(text: str) -> tuple[str, int, int, int, int]:
    r"""Fold every free-standing display span's equation number in `text`.

    A span stands free when only indentation lies between it and a line boundary
    on both sides, so a span in prose or a table row is skipped. The number is
    folded first, then the stranded line under what remains. Returns the text
    and the counts of tail numbers, number lines, sentence marks, and
    conditions.
    """
    pieces: list[str] = []
    last = 0
    tail_count = line_count = strand_count = condition_count = 0
    for match in _DISPLAY_MATH_RE.finditer(text):
        start, end = match.start(), match.end()
        open_line_start = text.rfind("\n", 0, start) + 1
        close_line_end = text.find("\n", end)
        if close_line_end == -1:
            close_line_end = len(text)
        # Measure from what this pass has not consumed yet: a fold above can
        # leave this span opening its own line, which keeps the pass idempotent.
        starts_block = not text[max(open_line_start, last) : start].strip()
        ends_block = not text[end:close_line_end].strip()
        if not (starts_block and ends_block):
            continue
        content = match.group(1)
        span_out = match.group(0)
        consumed = end
        # A stranded mark sits right under the closer, or one line lower once a
        # number line took the first.
        mark_from = close_line_end
        if not _TAG_RE.search(content):
            folded = _fold_tail_number(content)
            if folded is not None:
                span_out = f"$${folded}$$"
                tail_count += 1
            else:
                number, number_end = _match_number_line(text, close_line_end)
                if number is not None:
                    span_out = f"$${_insert_tag(content, number)}$$"
                    consumed = number_end
                    mark_from = number_end
                    line_count += 1
        span_out, folded_to, was_condition = _fold_stranded_line(
            span_out, text, mark_from
        )
        if folded_to != mark_from:
            consumed = folded_to
            if was_condition:
                condition_count += 1
            else:
                strand_count += 1
        if span_out == match.group(0) and consumed == end:
            continue
        pieces.append(text[last:start])
        pieces.append(span_out)
        last = consumed
    pieces.append(text[last:])
    return "".join(pieces), tail_count, line_count, strand_count, condition_count


def _fold_stranded_line(span: str, text: str, pos: int) -> tuple[str, int, bool]:
    r"""`span` with what the cut stranded on the line under `text[pos:]` folded in.

    A lone sentence mark folds whole, a line opening with a mark gives up only
    the mark, and a condition folds whole behind `\quad`. Returns the span, the
    consumed end (`pos` when nothing folded), and whether a condition folded.
    """
    mark, mark_end = _match_stranded_tail(text, pos)
    if mark is not None:
        return _fold_stranded_mark(span, mark), mark_end, False
    head, tail_from, indent = _match_stranded_head(text, pos)
    if head is not None:
        return _fold_stranded_mark(span, head) + "\n" + indent, tail_from, False
    condition, condition_end = _match_stranded_condition(text, pos)
    if condition is not None:
        tail = f" {_CONDITION_SPACER} {condition}"
        folded = _fold_stranded_mark(span, tail)
        if _keeps_its_validity(span, folded):
            return folded, condition_end, True
    return span, pos, False


def _keeps_its_validity(before: str, after: str) -> bool:
    """False when a fold turned a span the renderer accepted into one it rejects."""
    if is_valid_math(after[2:-2]):
        return True
    return not is_valid_math(before[2:-2])


def _insert_tag(content: str, number: str) -> str:
    r"""`content` with `\tag{number}` appended where its own text ends.

    When the closing delimiter stands on its own line, the tag goes on the line
    above and the closer's line is kept unchanged.
    """
    last_newline = content.rfind("\n")
    tail = content[last_newline + 1 :]
    if last_newline == -1 or tail.strip():
        body = content.rstrip(" \t")
        return f"{body} \\tag{{{number}}}"
    body = content[:last_newline].rstrip(" \t")
    return f"{body} \\tag{{{number}}}\n{tail}"


def _fold_tail_number(content: str) -> str | None:
    r"""`content` with its trailing text-form equation number folded into `\tag{}`.

    None when no such number ends `content`. A final newline, which `$` in the
    pattern allows, stays after the tag, so a closer on its own line stays there.
    """
    match = _EQUATION_NUMBER_RE.search(content)
    if match is None:
        return None
    body = content[: match.start()].rstrip()
    tail = content[match.end() :]
    return f"{body} \\tag{{{match.group(1)}}}{tail}"


def _fold_stranded_mark(span: str, tail: str) -> str:
    r"""`span` with `tail` placed where the formula's own sentence ends.

    Inside the closing `$$` and before any `\tag{}`: after the closer a mark
    would read as the delimiter of a span that never closed. When the closer
    stands alone on its line, the tail ends the content's last line.
    """
    inner = span[2:-2]
    tag = _TAG_RE.search(inner)
    if tag is not None:
        head = _rstrip_keeping_spacer(inner[: tag.start()], " \t")
        return f"$${head}{tail} {inner[tag.start() :]}$$"
    last_newline = inner.rfind("\n")
    if last_newline != -1 and not inner[last_newline + 1 :].strip():
        body = _rstrip_keeping_spacer(inner[:last_newline], " \t")
        return f"$${body}{tail}{inner[last_newline:]}$$"
    body = _rstrip_keeping_spacer(inner, " \t")
    return f"$${body}{tail}$$"


def _match_stranded_tail(text: str, pos: int) -> tuple[str | None, int]:
    """The lone sentence mark on the line right under `text[pos:]`, and its end.

    One character from `_STRANDED_TAIL` and nothing else; `pos` comes back
    unchanged when there is none.
    """
    if pos >= len(text) or text[pos] != "\n":
        return None, pos
    line_start = pos + 1
    line_end = text.find("\n", line_start)
    if line_end == -1:
        line_end = len(text)
    mark = text[line_start:line_end].strip()
    if len(mark) != 1 or mark not in _STRANDED_TAIL:
        return None, pos
    return mark, line_end


def _match_stranded_head(text: str, pos: int) -> tuple[str | None, int, str]:
    """The leading sentence mark of the line under `text[pos:]`, and its remainder.

    Returns the mark, where the remainder begins, and the line's indentation,
    which keeps the remainder inside its list item. None when the line does not
    open with a mark, a space, and more text.
    """
    if pos >= len(text) or text[pos] != "\n":
        return None, pos, ""
    line_start = pos + 1
    line_end = text.find("\n", line_start)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    stripped = line.lstrip()
    if len(stripped) < 2 or stripped[0] not in _STRANDED_TAIL:
        return None, pos, ""
    if not stripped[1].isspace():
        return None, pos, ""
    rest = stripped[2:].lstrip()
    if not rest:
        return None, pos, ""
    return stripped[0], line_end - len(rest), line[: len(line) - len(stripped)]


def _match_stranded_condition(text: str, pos: int) -> tuple[str | None, int]:
    r"""The bracketed condition on the line under `text[pos:]`, and its end.

    Returned with its brackets and closing mark; `pos` comes back unchanged
    when the line is no condition (`_reads_as_condition`).
    """
    if pos >= len(text) or text[pos] != "\n":
        return None, pos
    line_start = pos + 1
    line_end = text.find("\n", line_start)
    if line_end == -1:
        line_end = len(text)
    condition = _reads_as_condition(text[line_start:line_end])
    if condition is None:
        return None, pos
    return condition, line_end


def _reads_as_condition(line: str) -> str | None:
    r"""`line` as the condition it states, or None when it states none.

    One bracket group holding a relation and nothing but its closing mark, no
    word of three letters or more, no markup, and within `_CONDITION_MAX`. A
    cross-reference (`[See 45.]`) states no relation. Inline delimiters are
    dropped, and a `$` that survives leaves the line alone. The result is
    normalized (`_fix_math_content`), since a bare condition never passed
    through normalization and would otherwise settle one pass late.
    """
    bare = _INLINE_MATH_RE.sub(lambda match: match.group(1), line.strip())
    if "$" in bare:
        return None
    match = _CONDITION_LINE_RE.match(bare)
    if match is None:
        return None
    body = match.group("body")
    if not body.strip() or len(body) > _CONDITION_MAX:
        return None
    if _CONDITION_MARKUP_RE.search(body):
        return None
    if _RELATION_RE.search(body) is None:
        return None
    if _CONDITION_WORD_RE.search(_CONDITION_COMMAND_RE.sub(" ", body)):
        return None
    return _fix_math_content(bare)


def _match_number_line(text: str, pos: int) -> tuple[str | None, int]:
    """The number on the line right under `text[pos:]`, and where it ends.

    `pos` is the end of the span's closing line; a blank line in between means
    no number. `pos` comes back unchanged when there is none.
    """
    if pos >= len(text) or text[pos] != "\n":
        return None, pos
    line_start = pos + 1
    line_end = text.find("\n", line_start)
    if line_end == -1:
        line_end = len(text)
    match = _NUMBER_LINE_RE.match(text[line_start:line_end])
    if match is None:
        return None, pos
    return match.group(1), line_end


def clear_display_span_tail(seg_list: list[Segment]) -> list[Segment]:
    r"""Give a display block's closing `$$` back the end of its own line.

    The collapse of a one-row carrier table leaves the number or picture that
    stood beside a formula behind its closer, and a renderer then fails on the
    block while every check passes. A number folds into `\tag{}`, unless the
    block is already tagged; anything else moves to its own line. Scoped to a
    line opening on a closed display span with a tail free of `$` and `|`. Runs
    after the table collapse.
    """
    out: list[Segment] = []
    tagged = moved = 0
    for line, protected in seg_list:
        split = None if protected else _split_display_tail(line)
        if split is None:
            out.append((line, protected))
            continue
        indent, span, tail = split
        content = span[2:-2]
        number = _CELL_NUMBER_RE.match(tail)
        if number is not None and not _TAG_RE.search(content):
            out.append((f"{indent}$${_insert_tag(content, number.group(1))}$$", False))
            tagged += 1
            continue
        out.append((f"{indent}{span}", False))
        out.append(("", False))
        out.append((f"{indent}{tail}", False))
        moved += 1
    if tagged or moved:
        _logger.info(
            "display closers freed: %d tails tagged, %d given their own line",
            tagged,
            moved,
        )
    return out


def _split_display_tail(line: str) -> tuple[str, str, str] | None:
    """`line` as its indent, the display span opening it, and the tail behind it.

    None unless a closed span opens the line and a tail follows. A `$` in the
    tail means prose naming mathematics, and a `|` a cell border of a row
    without an outer bar.
    """
    stripped = line.strip()
    if not stripped.startswith("$$"):
        return None
    match = _DISPLAY_MATH_RE.match(stripped)
    if match is None:
        return None
    tail = stripped[match.end() :].strip()
    if not tail or "$" in tail or "|" in tail:
        return None
    return line[: len(line) - len(line.lstrip())], match.group(0), tail


# An HTML tag the recognition leaves inside a span: a footnote star as `<sup>`,
# a formula as a MathML `<math>`. A closed set of names, since `<` and `>` are
# relations and `a<b>c` must stay.
_MATH_SPAN_HTML_RE = re.compile(r"</?(?:sup|sub|math)\b[^>]*>", re.IGNORECASE)


def strip_math_span_html(seg_list: list[Segment]) -> list[Segment]:
    r"""Drop an HTML tag the recognition left standing inside a math span.

    marker can leave `<sup>`, `<sub>`, or `<math>` inside `$` markup
    (`$<sup>^{\ast}</sup>$`). A renderer refuses it, and a repair zone on it
    cannot succeed: the reply strips the tag, and the preservation guard reads
    that as lost content. A tag draws nothing in math mode, so it goes; a span
    left empty is kept. Runs per run of plain lines, before the normalization;
    idempotent.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    stripped = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed_text, run_stripped = _strip_math_span_html_zones(run_text)
        stripped += run_stripped
        out.extend((fixed_line, False) for fixed_line in fixed_text.split("\n"))
    if stripped:
        _logger.info("html tags dropped from math spans: %d", stripped)
    return out


def _strip_math_span_html_zones(text: str) -> tuple[str, int]:
    """Drop the closed-set HTML tags from every math span of `text`, code masked."""
    masked = mask_inline_code(text)
    pieces: list[str] = []
    last = 0
    stripped = 0
    for start, end in math_span_ranges(masked):
        span = text[start:end]
        pieces.append(text[last:start])
        fixed = _strip_span_html(span)
        if fixed is None:
            pieces.append(span)
        else:
            pieces.append(fixed)
            stripped += 1
        last = end
    pieces.append(text[last:])
    return "".join(pieces), stripped


def _strip_span_html(span: str) -> str | None:
    r"""`span` without its `<sup>`/`<sub>`/`<math>` tags, or None to keep it."""
    if not _is_closed_span(span) or not _MATH_SPAN_HTML_RE.search(span):
        return None
    content = _MATH_SPAN_HTML_RE.sub("", math_span_content(span))
    if not content.strip():
        return None
    delimiter = "$$" if span.startswith("$$") else "$"
    return f"{delimiter}{content}{delimiter}"


def normalize_math(seg_list: list[Segment]) -> list[Segment]:
    """Normalize marker's math for KaTeX inside detected `$...$`/`$$...$$` zones.

    Runs per run of plain lines, so a `$` is never paired across a protected
    zone. Only mechanical substitutions that keep the formula's words; see
    `_fix_math_content`. Recognition damage needs judgment and goes to LLM
    inspection.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed_text = _normalize_math_zones(run_text)
        out.extend((fixed_line, False) for fixed_line in fixed_text.split("\n"))
    return out


def _normalize_math_zones(text: str) -> str:
    """Fix marker math in `text`, display zones first.

    The inline pattern would otherwise read the two `$` of a `$$` as its own
    empty span.
    """
    pieces: list[str] = []
    last = 0
    for match in _DISPLAY_MATH_RE.finditer(text):
        pieces.append(_normalize_inline_math(text[last : match.start()]))
        pieces.append(f"$${_fix_math_content(match.group(1))}$$")
        last = match.end()
    pieces.append(_normalize_inline_math(text[last:]))
    return "".join(pieces)


def _normalize_inline_math(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        content = match.group(1).replace("\\[", "").replace("\\]", "")
        return f"${_fix_math_content(content)}$"

    return _INLINE_MATH_RE.sub(repl, text)


def _fix_math_content(content: str) -> str:
    """Apply the command/bracket fixes shared by inline and display math."""
    content = _balance_environments(content)
    content = _drop_unmatched_environment(content)
    content = _EQNO_RE.sub(r" \\tag{\1}", content)
    content = content.replace("\\mbox{", "\\text{")
    content = content.replace("\\textsc{", "\\text{")
    content = _LABEL_RE.sub("", content)
    content = _prime_straight_quotes(content)
    content = _disarm_double_subscripts(content)
    return _trim_math_tail(content)


def _prime_straight_quotes(content: str) -> str:
    """Write a straight double quote standing for a double prime as primes.

    After a symbol letter it becomes `''`; opening a superscript group each
    quote becomes `\\prime\\prime`, since a `'` in the group would be raised
    twice. Text-mode arguments are stepped over.
    """
    if '"' not in content:
        return content
    pieces: list[str] = []
    last = 0
    for start, end in _text_mode_arguments(content):
        pieces.append(_prime_quotes_in_math(content[last:start]))
        pieces.append(content[start:end])
        last = end
    pieces.append(_prime_quotes_in_math(content[last:]))
    return "".join(pieces)


def _text_mode_arguments(content: str) -> list[tuple[int, int]]:
    """The `[start, end)` of each text-mode macro with its argument.

    An unclosed argument runs to the end of `content`.
    """
    ranges: list[tuple[int, int]] = []
    pos = 0
    while (match := _TEXT_MODE_ARGUMENT_RE.search(content, pos)) is not None:
        close = _matching_brace(content, match.end() - 1)
        end = len(content) if close is None else close + 1
        ranges.append((match.start(), end))
        pos = end
    return ranges


def _prime_quotes_in_math(text: str) -> str:
    def superscript(match: re.Match[str]) -> str:
        primes = "\\prime\\prime" * len(match.group(1))
        # A letter right after would extend the command name (`\primex`).
        follower = text[match.end() : match.end() + 1]
        return "^{" + primes + (" " if follower.isalpha() else "")

    text = _QUOTE_SUPERSCRIPT_RE.sub(superscript, text)
    return _QUOTE_AFTER_SYMBOL_RE.sub(lambda m: m.group(0)[:-1] + "''", text)


def _balance_environments(content: str) -> str:
    """Drop the environment markup a split aligned block left behind.

    marker can cut an aligned block across two spans, leaving the tail an
    orphan `\\end{...}` and its `&`, which KaTeX rejects. The orphan closer is
    the proof, so an `&` goes only with one: in prose paired as a span
    (`$5 & $6`) the `&` is a word. The whitespace separating each goes too.
    """
    defects = math_env_defects(content)
    if not defects.orphan_ends:
        return content
    return _cut_out(content, _markup_cuts(content, defects))


def _drop_unmatched_environment(content: str) -> str:
    """Drop a `\\begin{env}` that never closes, where doing so leaves a formula.

    Needs two proofs: an `&` inside (an opener without one may be a real matrix
    whose rows were cut), and a span that renders afterwards (a truncated column
    spec would otherwise stand as text). The orphan `&` goes with the opener.
    """
    defects = math_env_defects(content)
    if not defects.unmatched_begins or not defects.orphan_amps:
        return content
    cuts = sorted(
        [
            (start, _extend_right(content, end))
            for start, end in defects.unmatched_begins
        ]
        + [(pos, _extend_right(content, pos + 1)) for pos in defects.orphan_amps]
    )
    fixed = _cut_out(content, cuts)
    return fixed if is_valid_math(fixed) else content


def _cut_out(content: str, cuts: list[tuple[int, int]]) -> str:
    """`content` without the `[start, end)` stretches of `cuts`, which may abut."""
    pieces: list[str] = []
    last = 0
    for start, end in cuts:
        if start > last:
            pieces.append(content[last:start])
        last = max(last, end)
    pieces.append(content[last:])
    return "".join(pieces)


def _markup_cuts(content: str, defects: MathEnvDefects) -> list[tuple[int, int]]:
    """The `[start, end)` spans to remove, each with its separator, in order.

    Spans may abut (`& \\end{split}`); `_cut_out` never walks backwards.
    """
    cuts = [(_extend_left(content, start), end) for start, end in defects.orphan_ends]
    cuts += [(pos, _extend_right(content, pos + 1)) for pos in defects.stray_amps]
    return sorted(cuts)


def _extend_left(content: str, idx: int) -> int:
    """Move `idx` back over the horizontal whitespace directly before it."""
    while idx > 0 and content[idx - 1] in " \t":
        idx -= 1
    return idx


def _extend_right(content: str, idx: int) -> int:
    """Move `idx` forward over the horizontal whitespace directly after it."""
    while idx < len(content) and content[idx] in " \t":
        idx += 1
    return idx


def _disarm_double_subscripts(content: str) -> str:
    """Insert an empty group between two adjacent `_{...}` subscripts.

    KaTeX rejects `x_{a}_{b}`. The group can nest braces, so its extent comes
    from a balanced-brace scan.
    """
    out: list[str] = []
    i = 0
    length = len(content)
    while i < length:
        if content[i] == "_" and i + 1 < length and content[i + 1] == "{":
            end = _matching_brace(content, i + 1)
            if end is not None:
                out.append(content[i : end + 1])
                i = end + 1
                if i < length and content[i] == "_":
                    out.append("{}")
                continue
        out.append(content[i])
        i += 1
    return "".join(out)


def _matching_brace(text: str, open_idx: int) -> int | None:
    """Index of the `}` matching the `{` at `open_idx`, or None; escapes skipped."""
    depth = 0
    i = open_idx
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _trim_math_tail(content: str) -> str:
    """Strip a stray trailing `\\` (and runs of it) at the span's end.

    Whitespace is stripped only to reach a backslash, so prose mistaken for a
    span round-trips unchanged, and trailing newlines are kept so a closer on
    its own line stays there. A `\\\\` line break stays.
    """
    core = content.rstrip("\r\n")
    trailing_newlines = content[len(core) :]
    trimmed_any = False
    while True:
        stripped = core.rstrip(" \t")
        if stripped.endswith("\\") and not stripped.endswith("\\\\"):
            core = stripped[:-1]
            trimmed_any = True
            continue
        break
    if trimmed_any:
        core = core.rstrip(" \t")
    return core + trailing_newlines


def unwrap_single_glyph_math(seg_list: list[Segment]) -> list[Segment]:
    r"""Unwrap an inline math span whose whole content is one prose glyph.

    A docx equation editor stores a glyph typed through it as a one-character
    equation. Scoped to a closed table (`_SINGLE_GLYPH_COMMANDS`,
    `_SINGLE_GLYPH_BARE`), since `$R$` is a real variable. pandoc's separator
    comment beside the span goes with it. Runs per run of plain lines.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed_text = _unwrap_single_glyph_zones(run_text)
        out.extend((fixed_line, False) for fixed_line in fixed_text.split("\n"))
    return out


def _unwrap_single_glyph_zones(text: str) -> str:
    """Unwrap every single-glyph inline span of `text`, its separator comment too.

    Spans are found with inline code masked. A stripped spacer becomes a space
    only where the neighbour is not whitespace already. The left neighbour is
    tracked in `last_char`, since two glyph spans can share one separator.
    """
    masked = mask_inline_code(text)
    pieces: list[str] = []
    last = 0
    last_char = ""
    sep_len = len(_SEPARATOR_COMMENT)
    for start, end in math_span_ranges(masked):
        span = text[start:end]
        found = None
        if not _is_closed_display_span(span) and _INLINE_MATH_RE.fullmatch(span):
            found = _single_glyph(span)
        if found is None:
            chunk = text[last:end]
            pieces.append(chunk)
            if chunk:
                last_char = chunk[-1]
            last = end
            continue
        glyph, leading_spacer, trailing_spacer = found
        before = text[last:start]
        if before.endswith(_SEPARATOR_COMMENT):
            before = before[:-sep_len]
        pieces.append(before)
        if before:
            last_char = before[-1]
        if leading_spacer and last_char and not last_char.isspace():
            pieces.append(" ")
        pieces.append(glyph)
        last_char = glyph[-1]
        last = end + sep_len if text[end : end + sep_len] == _SEPARATOR_COMMENT else end
        after = text[last : last + 1]
        if trailing_spacer and after and not after.isspace():
            pieces.append(" ")
            last_char = " "
    pieces.append(text[last:])
    return "".join(pieces)


def _strip_latex_spacer(content: str) -> tuple[str, bool, bool]:
    """Drop one leading and one trailing `_LATEX_SPACERS` token from `content`.

    The flags say which side had one, so the caller can restore a space.
    """
    leading = False
    for spacer in _LATEX_SPACERS:
        if content.startswith(spacer):
            content = content[len(spacer) :]
            leading = True
            break
    trailing = False
    for spacer in _LATEX_SPACERS:
        if content.endswith(spacer):
            content = content[: len(content) - len(spacer)]
            trailing = True
            break
    return content, leading, trailing


def _single_glyph(span: str) -> tuple[str, bool, bool] | None:
    """The glyph an inline span unwraps to, with the spacer flags, or None.

    A span holding only spacers has no glyph and returns None.
    """
    content, leading_spacer, trailing_spacer = _strip_latex_spacer(
        math_span_content(span)
    )
    if content in _SINGLE_GLYPH_COMMANDS:
        return _SINGLE_GLYPH_COMMANDS[content], leading_spacer, trailing_spacer
    if content in _SINGLE_GLYPH_BARE:
        return content, leading_spacer, trailing_spacer
    return None


def _has_significant_content(text: str) -> bool:
    r"""True when `text` carries a letter or digit; `\quad`'s name counts."""
    return any(ch.isalnum() for ch in text)


def _is_spacer_residue(content: str) -> bool:
    r"""True when `content` is nothing but a run of letterless spacing commands.

    A bare operator (`$+$`) is the document's own symbol and stays.
    """
    match = _SPACER_RESIDUE_RE.fullmatch(content)
    return match is not None and bool(content)


def drop_content_free_math_spans(seg_list: list[Segment]) -> list[Segment]:
    r"""Drop a closed math span left holding only letterless spacing commands.

    A degenerate recognition loop (`\!\!\!\!`) has no letter for the repetition
    rule to key on and renders as nothing. There is nothing to restore or
    report, so the span goes whole. A bare operator span stays; an unclosed
    region is left for the reporting pass.
    """
    out: list[Segment] = []
    dropped = 0
    for line, protected in seg_list:
        if protected or "$" not in line:
            out.append((line, protected))
            continue
        fixed = _drop_content_free_spans(line)
        if fixed != line:
            dropped += 1
        out.append((fixed, False))
    if dropped:
        _logger.info("content-free math spans dropped: %d", dropped)
    return out


def _drop_content_free_spans(line: str) -> str:
    """`line` without its content-free math spans, their spacing too; code masked."""
    masked = mask_inline_code(line)
    cuts = [
        _cut_bounds(line, start, end)
        for start, end in math_span_ranges(masked)
        if _is_closed_span(line[start:end])
        and _is_spacer_residue(math_span_content(line[start:end]))
    ]
    if not cuts:
        return line
    pieces: list[str] = []
    last = 0
    for cut_start, cut_end in cuts:
        pieces.append(line[last:cut_start])
        last = cut_end
    pieces.append(line[last:])
    return _join_over_cuts(pieces)


def drop_orphan_sizers(seg_list: list[Segment]) -> list[Segment]:
    r"""Drop a `\left`/`\right` that has no delimiter behind it to size.

    Recognition can drop a printed bracket and keep its sizing command, which
    draws nothing and makes KaTeX refuse the span. The check is per command, and
    a delimiter counts printed or named (`\langle`). Applied only where the drop
    leaves the span rendering and sound (`is_broken_math_span`,
    `_groups_closed`). Runs before `close_unpaired_delimiters`, whose pairing
    count an orphan would throw off.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    dropped = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed_text, run_dropped = _drop_orphan_sizer_zones(run_text)
        dropped += run_dropped
        out.extend((fixed_line, False) for fixed_line in fixed_text.split("\n"))
    if dropped:
        _logger.info("orphan sizing commands dropped: %d", dropped)
    return out


def _drop_orphan_sizer_zones(text: str) -> tuple[str, int]:
    r"""Drop every closed math span's orphan `\left`/`\right` in `text`, code masked."""
    masked = mask_inline_code(text)
    pieces: list[str] = []
    last = 0
    dropped = 0
    for start, end in math_span_ranges(masked):
        span = text[start:end]
        pieces.append(text[last:start])
        fixed = _drop_orphan_sizer(span)
        if fixed is not None:
            pieces.append(fixed)
            dropped += 1
        else:
            pieces.append(span)
        last = end
    pieces.append(text[last:])
    return "".join(pieces), dropped


def _drop_orphan_sizer(span: str) -> str | None:
    r"""`span` with its orphan `\left`/`\right` commands dropped, or None.

    None when the span is unclosed, already renders, has no orphan, or stays
    broken or leaves a bare group open after the drop.
    """
    if not _is_closed_span(span):
        return None
    content = math_span_content(span)
    if is_valid_math(content):
        return None
    fixed_content = _strip_orphan_sizers(content)
    if fixed_content is None or not is_valid_math(fixed_content):
        return None
    if not _groups_closed(fixed_content):
        return None
    delimiter = "$$" if span.startswith("$$") else "$"
    fixed_span = f"{delimiter}{fixed_content}{delimiter}"
    return None if is_broken_math_span(fixed_span) else fixed_span


def _strip_orphan_sizers(content: str) -> str | None:
    r"""`content` with every `\left`/`\right` that sizes no delimiter removed.

    None when no command is an orphan. Each orphan goes with the whitespace
    after it, or before it when nothing follows.
    """
    cuts: list[tuple[int, int]] = []
    for match in _SIZING_TOKEN_RE.finditer(content):
        if _sized_delimiter_end(content, match.start()) is not None:
            continue
        if _sizes_named_delimiter(content, match.end()):
            continue
        after = _extend_right(content, match.end())
        if after > match.end():
            cuts.append((match.start(), after))
        else:
            cuts.append((_extend_left(content, match.start()), match.end()))
    if not cuts:
        return None
    return _cut_out(content, cuts)


def _sizes_named_delimiter(content: str, idx: int) -> bool:
    r"""True when the sizing command ending at `idx` sizes a delimiter by name.

    Which names a renderer sizes is its own table, so the renderer is asked
    rather than a copy of the table kept here.
    """
    match = _DELIMITER_NAME_RE.match(content, _extend_right(content, idx))
    if match is None:
        return False
    return is_valid_math(f"\\left{match.group()} \\right.")


def close_unpaired_delimiters(seg_list: list[Segment]) -> list[Segment]:
    r"""Close a math span's one unpaired `\left`/`\right` with an invisible partner.

    Recognition can drop one half of a sizing pair inside a span that is
    otherwise sound. An unmatched `\right` gets `\left.` right before it, and an
    unmatched `\left` gets `\right.` at the content's end; the bracket may scale
    over a shorter range than printed. Applied only where the result is sound
    (`is_broken_math_span`, `_groups_closed`). Runs per run of plain lines,
    after `drop_content_free_math_spans`.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    closed = 0
    while idx < count:
        line, protected = seg_list[idx]
        if protected:
            out.append((line, True))
            idx += 1
            continue
        start = idx
        while idx < count and not seg_list[idx][1]:
            idx += 1
        run_text = "\n".join(seg_list[i][0] for i in range(start, idx))
        fixed_text, run_closed = _close_unpaired_delimiter_zones(run_text)
        closed += run_closed
        out.extend((fixed_line, False) for fixed_line in fixed_text.split("\n"))
    if closed:
        _logger.info("unpaired sizing delimiters closed: %d", closed)
    return out


def _close_unpaired_delimiter_zones(text: str) -> tuple[str, int]:
    r"""Close every closed math span's one unpaired `\left`/`\right` in `text`."""
    masked = mask_inline_code(text)
    pieces: list[str] = []
    last = 0
    closed = 0
    for start, end in math_span_ranges(masked):
        span = text[start:end]
        pieces.append(text[last:start])
        fixed = _close_unpaired_delimiter(span)
        if fixed is not None:
            pieces.append(fixed)
            closed += 1
        else:
            pieces.append(span)
        last = end
    pieces.append(text[last:])
    return "".join(pieces), closed


def _close_unpaired_delimiter(span: str) -> str | None:
    r"""`span` with its one unpaired `\left`/`\right` closed, or None.

    None when the span is unclosed or already renders, or when the result stays
    broken: `is_broken_math_span` catches damage that still renders, and
    `_groups_closed` a bare `[` that `\left( [a` leaves open.
    """
    if not _is_closed_span(span):
        return None
    content = math_span_content(span)
    if is_valid_math(content):
        return None
    fixed_content = _insert_invisible_partners(content)
    if fixed_content is None or not _groups_closed(fixed_content):
        return None
    delimiter = "$$" if span.startswith("$$") else "$"
    fixed_span = f"{delimiter}{fixed_content}{delimiter}"
    return None if is_broken_math_span(fixed_span) else fixed_span


def _insert_invisible_partners(content: str) -> str | None:
    r"""`content` with every unmatched `\left`/`\right` closed by its partner.

    None when there is no sizing command or all of them already pair: the span
    fails for another reason.
    """
    matches = list(_SIZING_TOKEN_RE.finditer(content))
    if not matches:
        return None
    pieces: list[str] = []
    last = 0
    open_count = 0
    inserted = False
    for match in matches:
        if match.group() == "\\left":
            open_count += 1
            continue
        if open_count > 0:
            open_count -= 1
            continue
        pieces.append(content[last : match.start()])
        pieces.append("\\left.")
        last = match.start()
        inserted = True
    pieces.append(content[last:])
    fixed = "".join(pieces)
    if open_count:
        closers = " ".join(["\\right."] * open_count)
        fixed = f"{fixed.rstrip()} {closers}"
        inserted = True
    return fixed if inserted else None


# What a printed amount or a range of them prints: digits and number
# punctuation.
_AMOUNT_CONTENT_CHARS = frozenset("0123456789.,'+-\u2013\u2014")


def separate_glued_inline_spans(seg_list: list[Segment]) -> list[Segment]:
    r"""Give an inline span back the space between it and the digit beside it.

    A markdown math plugin refuses a `$` after an alphanumeric or before a digit,
    which keeps `5$` from opening a formula; the office route writes `3$S$`, so
    the refusal falls on a real span. A span holding both delimiters in one token
    is a formula, unless its content prints only an amount (`$5-$6`). One space
    goes outside the span. Scoped to digits: no measured body carries the letter
    case. Runs after every rule that reads span bounds; idempotent.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, protected))
            continue
        out.append((_separate_glued_spans_line(line), False))
    return out


def _separate_glued_spans_line(line: str) -> str:
    """`line` with a space wherever a digit touches an inline span's delimiter.

    Inline code and addresses are masked: a space inside a link target breaks
    the link.
    """
    masked = mask_addresses(line)
    cuts: list[int] = []
    for start, end in math_span_ranges(masked):
        span = masked[start:end]
        if not _shares_one_token(span) or _prints_only_an_amount(span):
            continue
        if start > 0 and _is_ascii_digit(masked[start - 1]):
            cuts.append(start)
        if end < len(masked) and _is_ascii_digit(masked[end]):
            cuts.append(end)
    if not cuts:
        return line
    pieces: list[str] = []
    last = 0
    for cut in cuts:
        pieces.append(line[last:cut])
        pieces.append(" ")
        last = cut
    pieces.append(line[last:])
    return "".join(pieces)


def _shares_one_token(span: str) -> bool:
    """Whether `span` is a closed inline span with both delimiters in one token.

    Two amounts in one sentence (`5$ ... 6$`) pair only across a space.
    """
    if span.startswith("$$") or not span.startswith("$") or not span.endswith("$"):
        return False
    content = span[1:-1]
    return bool(content) and not any(char.isspace() for char in content)


def _prints_only_an_amount(span: str) -> bool:
    """Whether `span`'s content prints only digits and number punctuation."""
    return all(char in _AMOUNT_CONTENT_CHARS for char in span[1:-1])


def _is_ascii_digit(char: str) -> bool:
    return char.isascii() and char.isdigit()


def collapse_repeated_spans(line: str) -> str:
    """`line` with each loop of repeated inline math spans cut back to one cycle.

    One cycle stays: it is what the engine emitted and is a closed span. The cut
    ranges come from `mdtext.loops.math_repeated_span_cuts`, which the finding and the
    evaluator read too.
    """
    cuts = math_repeated_span_cuts(line)
    if not cuts:
        return line
    pieces: list[str] = []
    last = 0
    for cut_start, cut_end in cuts:
        pieces.append(line[last:cut_start])
        last = cut_end
    pieces.append(line[last:])
    return "".join(pieces)


def drop_loop_residue(before: str, after: str) -> str:
    """Remove from `after` every math span the repetition trim left a fragment of.

    A shortened span is a piece the loop ran from, not a formula the page
    printed, and a later LLM step would "restore" it into something false; the
    `broken-formula` finding keeps the loss visible. A span that is a whole
    formula on its own stays. Spans pair by position, since a loop unit holds no
    delimiter; a count mismatch drops nothing.
    """
    old_spans = math_spans(before)
    new_spans = math_spans(after)
    if len(old_spans) != len(new_spans):
        return after
    cuts = [
        _cut_bounds(after, start, end)
        for (start, end), old_span, new_span in zip(
            math_span_ranges(after), old_spans, new_spans, strict=True
        )
        if old_span != new_span and not _is_whole_formula(new_span)
    ]
    if not cuts:
        return after
    pieces: list[str] = []
    last = 0
    for cut_start, cut_end in cuts:
        pieces.append(after[last:cut_start])
        last = cut_end
    pieces.append(after[last:])
    return _join_over_cuts(pieces)


def _cut_bounds(line: str, start: int, end: int) -> tuple[int, int]:
    """The `[start, end)` to remove for the span at `[start, end)` of `line`.

    The whitespace on both sides goes, except a line's own indentation before a
    span at its head.
    """
    cut_start = _extend_left(line, start)
    if cut_start == 0 < start:
        cut_start = start
    return cut_start, _extend_right(line, end)


def _join_over_cuts(pieces: list[str]) -> str:
    """Join the stretches a cut left, one space where two words would collide.

    No space next to an empty side, after whitespace, or before clinging
    punctuation.
    """
    text = pieces[0]
    for piece in pieces[1:]:
        if text and piece and not text[-1].isspace() and piece[0] not in _CLINGING:
            text += " "
        text += piece
    return text.rstrip()


def _is_whole_formula(span: str) -> bool:
    """True when `span` reads as a formula in its own right, not a piece of one.

    It is closed, it renders, and its grouping delimiters close: a list cut off
    mid-way (`[\\gamma_{xz}, \\gamma_{yz}`) balances braces yet is a fragment.
    """
    if not _is_closed_span(span):
        return False
    content = math_span_content(span)
    return is_valid_math(content) and _groups_closed(content)


def _is_closed_span(span: str) -> bool:
    """True when `span` is a delimited pair rather than a region missing its closer."""
    return bool(_is_closed_display_span(span) or _INLINE_MATH_RE.fullmatch(span))


def _groups_closed(content: str) -> bool:
    """True when `content`'s brackets and parentheses open and close in pairs.

    Escapes, text-macro arguments, and sized delimiters are skipped. Brackets
    and parentheses share one depth, since LaTeX crosses them on purpose
    (`[0, 1)`).
    """
    depth = 0
    i = 0
    length = len(content)
    while i < length:
        ch = content[i]
        if ch == "\\":
            past = _text_macro_end(content, i)
            if past is None:
                past = _sized_delimiter_end(content, i)
            i = i + 2 if past is None else past
            continue
        if ch in _GROUP_OPENERS:
            depth += 1
        elif ch in _GROUP_CLOSERS:
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


def _text_macro_end(content: str, idx: int) -> int | None:
    """Index just past the whole `\\text{...}` starting at `idx`, or None.

    In prose inside a formula a bracket is a printed character. An unclosed
    argument returns None and is walked as content.
    """
    for macro in _TEXT_MACROS:
        if content.startswith(macro, idx):
            end = _matching_brace(content, idx + len(macro) - 1)
            return None if end is None else end + 1
    return None


def _sized_delimiter_end(content: str, idx: int) -> int | None:
    """Index just past a `\\left`/`\\right` at `idx` and the delimiter it sizes.

    None when what follows is no sizable delimiter (`\\leftarrow`).
    """
    for command in _SIZING_COMMANDS:
        if not content.startswith(command, idx):
            continue
        end = _extend_right(content, idx + len(command))
        if end < len(content) and content[end] in _SIZED_DELIMITERS:
            return end + 1
    return None


def resolve_unclosed_environment_spans(
    seg_list: list[Segment],
) -> tuple[list[Segment], set[int]]:
    r"""Resolve a math span whose environment declaration never finds its close.

    A truncated argument with no head before it is a bare preamble, and the span
    is dropped. A head with a letter or digit stays and the environment goes;
    such lines are returned for a `broken-formula` anchor. Anything else, such
    as a `\begin{pmatrix}` whose rows were cut, is left for the detector.
    """
    out: list[Segment] = []
    needs_anchor: set[int] = set()
    for idx, (line, protected) in enumerate(seg_list):
        if protected or "$" not in line:
            out.append((line, protected))
            continue
        fixed, kept_head = _resolve_unclosed_environment_line(line)
        out.append((fixed, False))
        if kept_head:
            needs_anchor.add(idx)
    return out, needs_anchor


def _resolve_unclosed_environment_line(line: str) -> tuple[str, bool]:
    """`line` with its unclosed-environment spans resolved, and whether a head stayed.

    Kept heads are spliced in place first; dropped stubs take their spacing and
    need rejoining, so they are cut in a second pass.
    """
    spliced, kept_head = _splice_surviving_heads(line)
    return _drop_headless_stubs(spliced), kept_head


def _splice_surviving_heads(line: str) -> tuple[str, bool]:
    """`line` with an unclosed environment cut from behind a surviving head."""
    masked = mask_inline_code(line)
    pieces: list[str] = []
    last = 0
    kept_head = False
    for start, end in math_span_ranges(masked):
        replacement, has_head = _resolve_unclosed_environment_span(line[start:end])
        if replacement is None or not has_head:
            continue
        pieces.append(line[last:start])
        pieces.append(replacement)
        last = end
        kept_head = True
    if not kept_head:
        return line, False
    pieces.append(line[last:])
    return "".join(pieces), True


def _drop_headless_stubs(line: str) -> str:
    """`line` with a headless environment stub removed, its own spacing too."""
    masked = mask_inline_code(line)
    cuts: list[tuple[int, int]] = []
    for start, end in math_span_ranges(masked):
        replacement, _ = _resolve_unclosed_environment_span(line[start:end])
        if replacement is None:
            cuts.append(_cut_bounds(line, start, end))
    if not cuts:
        return line
    pieces: list[str] = []
    last = 0
    for cut_start, cut_end in cuts:
        pieces.append(line[last:cut_start])
        last = cut_end
    pieces.append(line[last:])
    return _join_over_cuts(pieces)


def _resolve_unclosed_environment_span(span: str) -> tuple[str | None, bool]:
    """`span` resolved if its environment is a stub, and whether a head survived.

    None means drop the span. `span` itself comes back when nothing applies.
    """
    if not _is_closed_span(span):
        return span, False
    content = math_span_content(span)
    defects = math_env_defects(content)
    if not defects.unmatched_begins:
        return span, False
    env_start, env_end = defects.unmatched_begins[0]
    head = content[:env_start].rstrip()
    truncated = math_env_argument_open(content, env_start, env_end)
    significant = _has_significant_content(head)
    if not truncated and not significant:
        return span, False
    if not significant:
        return None, False
    delimiter = "$$" if span.startswith("$$") else "$"
    return f"{delimiter}{head}{delimiter}", True
