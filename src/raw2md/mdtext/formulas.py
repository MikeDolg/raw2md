"""Damage inside a math span: environments, validity, and cut formulas.

KaTeX judges validity through `katex.py`. The environment scan and the
broken-span test are shared by the evaluator, the cleaner, and the LLM edit
guard, so all stages call the same formula lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from raw2md import katex
from raw2md.mdtext.loops import math_repetition_loop
from raw2md.mdtext.math_spans import (
    MATH_DELIMITER_RE,
    has_unpaired_delimiter,
    math_span_content,
    math_span_ranges,
    math_spans,
)
from raw2md.mdtext.zones import mask_inline_code

# Applied only at an unescaped backslash, so `\\end{split}` (a line break,
# then `end`) is no closer.
_MATH_ENV_RE = re.compile(r"\\(begin|end)\{([A-Za-z]+\*?)\}")

# Openers whose column spec (`\begin{array}[t]{c|c}`) belongs to them. A
# closed set: elsewhere the next group is the formula's first term.
_ENV_ARGUMENT_OWNERS = frozenset({"array", "tabular"})
_ENV_ARGUMENT_RE = re.compile(r"[ \t]*(?:\[[^\]]*\])?[ \t]*\{[^{}]*\}")

# Text-mode environments: a math span declaring one holds a text block.
_TEXT_MODE_ENVS = frozenset(
    {
        "abstract",
        "center",
        "description",
        "document",
        "enumerate",
        "figure",
        "flushleft",
        "flushright",
        "itemize",
        "longtable",
        "minipage",
        "quotation",
        "quote",
        "supertabular",
        "tabu",
        "table",
        "tabular",
        "tabularx",
        "tabulary",
        "thebibliography",
        "verbatim",
        "wrapfigure",
    }
)


_COMMAND_HEAD_RE = re.compile(r"\\([A-Za-z]+|.)", re.DOTALL)

# Recognition splits an index with space runs (`M_{y  n  1}`). A single space
# may be meant (`F_{z n1}`). An index with a command or a group is not read.
_INDEX_GROUP_RE = re.compile(r"(?<!\\)_\{([^{}\\]*)\}")
_INDEX_GAP_RE = re.compile(r"[^\W_]\s{2,}[^\W_]")

# Tokens a formula never opens with. A span that opens with one continues
# the span above. Commands match whole names: `\left` is not `\le`.
_CONTINUATION_SYMBOLS = ("+", "-", "=", ")", "]", "}", ",")
_CONTINUATION_COMMANDS = frozenset(
    {
        "right",
        "end",
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


@dataclass(frozen=True)
class MathEnvDefects:
    """Environment damage found in the content of one math span.

    Spans and offsets: closers with no opener, `&` outside any environment
    and group, openers that never close (with their argument), and the `&`
    those openers hold. A caller may drop all of them. `crossed` counts
    closers out of nesting order; only the evaluator acts on it.
    """

    orphan_ends: tuple[tuple[int, int], ...]
    stray_amps: tuple[int, ...]
    unmatched_begins: tuple[tuple[int, int], ...]
    orphan_amps: tuple[int, ...]
    crossed: int


@dataclass
class _OpenEnv:
    """An environment the scan has opened and not closed, with the `&` it holds."""

    name: str
    start: int
    end: int
    amps: list[int]


def math_env_defects(content: str) -> MathEnvDefects:
    """Find unbalanced environments and misplaced `&` in a math span's content.

    marker cuts an aligned block across two spans: the tail keeps `\\end{split}`
    and its `&` but not the opener. A closer matches the nearest open
    environment of its name, so an inner one left open does not orphan it; an
    out-of-order close counts in `crossed`. Escapes are scanned as pairs. An
    `&` inside a brace group is text (`\\text{R&D}`).
    """
    open_envs: list[_OpenEnv] = []
    orphan_ends: list[tuple[int, int]] = []
    stray_amps: list[int] = []
    crossed = 0
    brace_depth = 0
    i = 0
    length = len(content)
    while i < length:
        ch = content[i]
        if ch == "\\":
            m = _MATH_ENV_RE.match(content, i)
            if m is None:
                i += 2  # an escaped character: `\&`, `\\`, `\{`
                continue
            name = m.group(2)
            if m.group(1) == "begin":
                i = _env_argument_end(content, name, m.end())
                open_envs.append(_OpenEnv(name, m.start(), i, []))
                continue
            if any(env.name == name for env in open_envs):
                if open_envs[-1].name != name:
                    crossed += 1
                _close_env(open_envs, name)
            else:
                orphan_ends.append(m.span())
            i = m.end()
            continue
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth = max(0, brace_depth - 1)
        elif ch == "&" and not brace_depth:
            if open_envs:
                open_envs[-1].amps.append(i)
            else:
                stray_amps.append(i)
        i += 1
    return MathEnvDefects(
        orphan_ends=tuple(orphan_ends),
        stray_amps=tuple(stray_amps),
        unmatched_begins=tuple((env.start, env.end) for env in open_envs),
        orphan_amps=tuple(amp for env in open_envs for amp in env.amps),
        crossed=crossed,
    )


def _env_argument_end(content: str, name: str, end: int) -> int:
    """The end of the opener at `end`, its closed argument included."""
    if name not in _ENV_ARGUMENT_OWNERS:
        return end
    argument = _ENV_ARGUMENT_RE.match(content, end)
    return end if argument is None else argument.end()


def _close_env(open_envs: list[_OpenEnv], name: str) -> None:
    """Close the innermost open environment named `name`, keeping the ones above."""
    for idx in range(len(open_envs) - 1, -1, -1):
        if open_envs[idx].name == name:
            del open_envs[idx]
            return


def math_unclosed_environment(line: str) -> bool:
    """True when a math span in `line` leaves a `\\begin{env}` unmatched or crossed.

    A truncated matrix has no closer to show where it broke, so it is a lost
    formula like a loop. One line only: marker writes a span on one line.
    Inline code is masked.
    """
    if "$" not in line:
        return False
    return any(
        _has_unclosed_environment(span) for span in math_spans(mask_inline_code(line))
    )


def _has_unclosed_environment(span: str) -> bool:
    """True when `span`'s content leaves an environment unmatched or crossed."""
    defects = math_env_defects(math_span_content(span))
    return bool(defects.unmatched_begins or defects.crossed)


def math_env_argument_open(content: str, start: int, end: int) -> bool:
    r"""True when the token at `start` owns an argument that never closes.

    `end` is the token's end as `math_env_defects` reports it; when it sits at
    the bare token's end, no closed argument was consumed. Only argument
    owners (`_ENV_ARGUMENT_OWNERS`) qualify. A truncation inside `[...]` or
    `{...}` reads the same.
    """
    match = _MATH_ENV_RE.match(content, start)
    if match is None or match.group(2) not in _ENV_ARGUMENT_OWNERS:
        return False
    if end != match.end():
        return False
    tail = content[end:].lstrip(" \t")
    if tail.startswith("["):
        close = tail.find("]")
        if close == -1:
            return True
        tail = tail[close + 1 :].lstrip(" \t")
    return tail.startswith("{") and tail.count("}") < tail.count("{")


def text_mode_math(line: str) -> bool:
    """True when `line` carries a math delimiter beside a text-mode environment.

    Such a delimiter marks no formula; left, it pairs with a real formula
    further down. Opening end: a math region declaring the environment.
    Closing end: an environment token beside an unpaired delimiter. Raw LaTeX
    in prose beside a sound formula does not qualify. Inline code is masked.
    """
    if "$" not in line:
        return False
    masked = mask_inline_code(line)
    if any(
        _declares_text_mode_env(math_span_content(masked[start:end]))
        for start, end in math_span_ranges(masked)
    ):
        return True
    return _declares_text_mode_env(masked) and has_unpaired_delimiter(masked)


def _declares_text_mode_env(text: str) -> bool:
    """True when `text` opens or closes an environment that exists only in text mode."""
    return any(
        match.group(2).rstrip("*") in _TEXT_MODE_ENVS
        for match in _MATH_ENV_RE.finditer(text)
    )


def is_valid_math(content: str) -> bool:
    """True when `content` is non-empty and KaTeX renders it.

    KaTeX renders an empty span, but an empty span is a lost formula. The
    check is one-directional: invalid is truly broken, while a valid span may
    hold a misrecognized symbol. The evaluator counts invalid spans, and an
    LLM step may rewrite only a span this check condemns.
    """
    text = content.strip()
    if not text:
        return False
    return katex.renders(text)


def is_broken_math_span(span: str) -> bool:
    """True when `span` (delimiters included) is damaged rather than merely odd.

    Invalid for KaTeX, a repetition loop, or an index split by spacing. The
    last is not counted by the evaluator: it licenses a rewrite, not a lost
    formula.
    """
    content = math_span_content(span)
    return (
        not is_valid_math(content)
        or math_repetition_loop(span)
        or _has_split_index(content)
    )


def _has_split_index(content: str) -> bool:
    """True when a run of spaces stands between the characters of a `_{...}` index."""
    return any(
        _INDEX_GAP_RE.search(match.group(1))
        for match in _INDEX_GROUP_RE.finditer(content)
    )


def is_broken_display_line(line: str) -> bool:
    """True when the whole line is one damaged display span and nothing else.

    marker cuts a long display formula into one span per line, each damaged
    at the cut. Alone on the line makes the piece addressable; damage says it
    is a fragment. A sound span is a formula of its own.
    """
    core = line.strip()
    if not core.startswith("$$"):
        return False
    return math_spans(core) == [core] and is_broken_math_span(core)


def is_formula_continuation(line: str) -> bool:
    """True when the line's math opens with a token no formula opens with.

    That seam is the one signal that two damaged fragments are one formula.
    """
    content = math_span_content(line.strip()).lstrip()
    if content.startswith(_CONTINUATION_SYMBOLS):
        return True
    command = _COMMAND_HEAD_RE.match(content)
    return command is not None and command.group(1) in _CONTINUATION_COMMANDS


def math_delimiters_only_moved(old: str, new: str) -> bool:
    """True when `new` only narrows `old`'s math to less of the same content.

    Recognition swallows a word into `$...$`; handing it back to prose is the
    one exception to byte-for-byte math. Guards: the same `$` count, the same
    span count (`$x$ y` -> `x $$ y` fails), every new span sound, the same
    tokens with delimiters dropped, and new math tokens a subsequence of the
    old, so delimiters cannot walk off to other text.
    """
    if len(MATH_DELIMITER_RE.findall(old)) != len(MATH_DELIMITER_RE.findall(new)):
        return False
    old_spans = math_spans(old)
    new_spans = math_spans(new)
    if len(old_spans) != len(new_spans):
        return False
    if any(is_broken_math_span(span) for span in new_spans):
        return False
    if MATH_DELIMITER_RE.sub("", old).split() != MATH_DELIMITER_RE.sub("", new).split():
        return False
    return _is_math_token_subsequence(_math_tokens(new), _math_tokens(old))


def _math_tokens(text: str) -> list[str]:
    """The tokens of `text` that sit inside its math spans, delimiters dropped."""
    return MATH_DELIMITER_RE.sub(" ", "".join(math_spans(text))).split()


def _is_math_token_subsequence(inner: list[str], outer: list[str]) -> bool:
    """True when every token of `inner` occurs in `outer`, in order."""
    position = 0
    for token in inner:
        while position < len(outer) and outer[position] != token:
            position += 1
        if position == len(outer):
            return False
        position += 1
    return True
