"""Block route: a crushed run, a span that swallowed prose, a broken formula.

The zone goes as Markdown, with at most one read-only neighbour on each side.
A crushed run is judged as a token multiset, since its repair reorders content;
a math zone by its own invariant. A hyphenation join must be attested by the
body's own words.
"""

from __future__ import annotations

import bisect
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from raw2md.cleaner import clean_with_report
from raw2md.cleaning.findings import LETTER_SPACING_FINDING
from raw2md.cleaning.prose import is_caption_label
from raw2md.cleaning.segments import (
    FLATTENED_PARAGRAPH_MIN_RUN,
    block_content_lines,
    flattened_paragraph_runs,
    run_is_crushed,
)
from raw2md.keywords import Keywords
from raw2md.llm.base import ProviderError, TextPart
from raw2md.llm.post.common import (
    MAX_CONTEXT_CHARS,
    TRACE_OP,
    PostOperation,
    ZoneOutcome,
    block_end,
    normalized_zone,
    retry_note,
)
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.formulas import is_valid_math, math_delimiters_only_moved
from raw2md.mdtext.lines import is_table_separator, is_thematic_break
from raw2md.mdtext.links import IMAGE_RE
from raw2md.mdtext.math_spans import math_span_content, math_spans
from raw2md.mdtext.tables import has_cell_separator, table_cells
from raw2md.mdtext.zones import Segment, segments
from raw2md.source_text import tokenize

# A soft hyphen break; the blank-line form is read for a crushed run only.
_LINE_BREAK = r"[ \t]*\n[ \t]*"
_BLANK_BREAK = r"[ \t]*\n(?:[ \t]*\n)*[ \t]*"

# Collapsed on both sides before the token comparison, so a join is no change.
_HYPHEN_BREAK_RE = re.compile(rf"(\w)-{_LINE_BREAK}")
_HYPHEN_GAP_BREAK_RE = re.compile(rf"(\w)-{_BLANK_BREAK}")

# Read whole: a narrow column can break one word twice (`pur-` / `chas-` /
# `tic`), and a pairwise reading would look for a word no reply writes.
_HYPHEN_SPLIT_RE = re.compile(rf"\w+(?:-{_LINE_BREAK}\w+)+")
_HYPHEN_GAP_SPLIT_RE = re.compile(rf"\w+(?:-{_BLANK_BREAK}\w+)+")

# Inflection keeps the joined form itself out of the body, so a shared prefix
# counts, but only past the split by more than an ending's worth: every word on
# the same stem agrees up to the split.
_JOIN_ATTEST_MARGIN = 3

# A word run, or one non-word character at a time, so whitespace between two
# marks (`**.` vs `** .`) is no token change.
_TOKEN_RE = re.compile(r"\w+|[^\s\w]")

# Exempt anywhere: prose almost never carries a pipe. `-` and `:` are content
# far more often, so only a whole separator or rule line exempts them.
_TABLE_CELL_TOKEN = "|"  # noqa: S105 -- a table cell delimiter character, not a credential

# Zone names for the trace and the log; none is written into the body.
_CRUSHED_ZONE_NAME = "crushed-run"


# A label names the defect and the repair, since the zone carries no mark. The
# repair is the join: a run holds no cell separator, so a grid would be a guess.
_CRUSHED_ZONE_LABEL = (
    "Crushed zone to repair. A narrow two-column layout was read straight down "
    "the page, so one sentence -- or one entry of a list -- stands here as "
    "several one-line paragraphs split by blank lines the author never wrote. "
    "Join the fragments back into the sentence or the entry they came from, "
    "keeping a list marker at the head of its own entry; a term the layout "
    "stranded mid-entry may move to the front of that entry. Change nothing "
    "else: no word, punctuation mark, list marker or emphasis mark may be "
    "added, dropped or reworded, and this zone never becomes a table -- write "
    "no cell separator into the reply. Answer with the repaired zone as "
    "Markdown and nothing else.\n"
)

# A run ends at a line that is a structure whole: an equation number, a list
# marker, a caption label. The reply is read as a multiset, so a number joined
# into a sentence would pass. An equation number carries a digit; a word in
# parentheses is an aside.
_EQUATION_NUMBER_RE = re.compile(r"^\(\s*[\w.\-]{0,8}\d[\w.\-]{0,8}\s*\)$")
_LIST_OPENER_RE = re.compile(r"^(?:[-*+•]|\d+(?:\.\d+)*[.)])$")

_MATH_ZONE_NAME = "swallowed-prose"

# The standing math rule reads as a ban on this edit, so the label names the
# one thing that moves.
_MATH_ZONE_LABEL = (
    "Zone to repair. A math span here closes past the words that follow the "
    "formula, so ordinary prose stands inside the delimiters and reads as "
    "mathematics. Move the delimiter to where the formula itself ends, "
    "leaving those words outside the span. Move delimiters and nothing else: "
    "the zone keeps exactly as many $ as it has now, every character inside a "
    "span stays as it is, and no word, punctuation mark or markup anywhere in "
    "the zone is added, dropped, reordered or reworded. Answer with the "
    "repaired zone as Markdown and nothing else.\n"
)

# Read as a hole rather than dropped, so two names on either side of one are
# never two words side by side.
_MATH_ENVIRONMENT_RE = re.compile(r"\\(?:begin|end)\s*\{[^{}]*\}")
_MATH_COMMAND_RE = re.compile(r"\\[A-Za-z]+|\\[^A-Za-z]")
_MATH_GROUP_RE = re.compile(r"\{[^{}]*\}")
_MATH_HOLE = "\x00"

# Two words of three letters or more with only space between: prose, since a
# formula sets something between two operands. Three letters keep a unit and
# a two-letter index out.
_PROSE_PAIR_RE = re.compile(r"([^\W\d_]{3,})\s+([^\W\d_]{3,})")

_MARKUP_ZONE_NAME = "broken-markup"

# Licenses markup, never a character. The invisible closer is named because
# the alternative is a bracket the source may never have printed.
_MARKUP_ZONE_LABEL = (
    "Zone to repair. A math span here does not render: its markup is broken -- "
    "a group left open, a \\left with no \\right, an environment with no "
    "\\end. Repair the markup and nothing but the markup: you may add or drop "
    "a group's braces { }, a \\left or a \\right, and a \\begin or an \\end, "
    "and where a \\left has no partner, close it with the invisible \\right. "
    "rather than write a bracket of your own. Change nothing else: no letter, "
    "digit, symbol, command or word of the zone may be added, dropped or "
    "replaced, and the zone keeps exactly as many $ as it has now. You have no "
    "source to repair the formula against, so what the span states stays as it "
    "stands, however wrong it reads. Answer with the repaired zone as Markdown "
    "and nothing else.\n"
)

# Word runs stay whole, so two words cannot merge; whitespace is dropped, since
# LaTeX sets its own spacing.
_MARKUP_TOKEN_RE = re.compile(r"\\[A-Za-z]+|\\.|\w+|[^\s\w]")

# `\begin` and `\end` are taken out before tokenizing.
_MARKUP_TOKENS = frozenset({"{", "}", "$", "\\left", "\\right"})

# An environment name is content: `matrix`, `cases`, `pmatrix` set different
# brackets.
_MATH_ENVIRONMENT_NAME_RE = re.compile(r"\\(?:begin|end)\s*\{([^{}]*)\}")

# `\right.` prints nothing, so it closes an open `\left` with no bracket.
_SIZING_COMMANDS = frozenset({"\\left", "\\right"})

# Fixed reasons name no zone content, so a retry never echoes the document.
_EMPTY_REPLY_REASON = "the reply was empty"
_PROTECTED_ZONE_REASON = (
    "the reply added a code fence, table, or other protected block, which is "
    "not allowed in this zone"
)
_UNRESOLVED_REASON = "the reply still leaves the marked defect in place"
_TABLE_WIDTH_REASON = (
    "a row of the table does not hold as many cells as its own separator row; "
    "every row must match the separator's column count"
)
_INVENTED_TABLE_REASON = (
    "the reply built a table out of a zone that holds no cell separator; this "
    "zone is prose or a list, and its repair is a join, never a grid"
)
_MATH_MOVE_REASON = (
    "the reply did more than move the delimiter of the span that holds prose; "
    "this zone keeps as many $ as it has now, every other span comes back "
    "exactly as it stands, and every word stays where it is"
)
_MARKUP_KEPT_REASON = (
    "the reply did more than repair the markup of the broken formula; this "
    "zone keeps as many $ as it has now, a span that already rendered comes "
    "back exactly as it stands, and only braces, \\left, \\right, \\begin and "
    "\\end may be added or dropped"
)
_MARKUP_UNRENDERED_REASON = (
    "the formula still does not render; close what the markup leaves open, "
    "using the invisible \\right. where a \\left has no partner, and write no "
    "character of your own"
)

# Built from zone content, but capped at the one word that broke it.
_INVENTED_JOIN_REASON = (
    "joining the split word produced {word}, which occurs nowhere else in the "
    "document; join two fragments only when they spell a word the document "
    "itself uses, and otherwise leave the split as it stands"
)

# Tokens a diff reason names, so the reason never reads the zone back in full.
_REASON_TOKEN_LIMIT = 8


def crushed_runs(seg_list: list[Segment], keywords: Keywords) -> dict[int, int]:
    """First line index -> end index, for each run of blocks a column crushed.

    The zone is the whole run, blank gaps included, since closing them is the
    repair. A list item counts here, unlike in the cleaner: a reader can see
    where an entry starts. A run stops at a structural line.
    """
    return {
        part[0][0]: part[-1][1]
        for run in flattened_paragraph_runs(seg_list, allow_list_item=True)
        for part in _runs_past_structure(seg_list, run, keywords)
    }


def _runs_past_structure(
    seg_list: list[Segment], run: Sequence[tuple[int, int]], keywords: Keywords
) -> list[list[tuple[int, int]]]:
    """`run` cut at every block holding a line that is a structure of its own.

    Each piece must again be long enough and show a break inside a clause.
    """
    parts: list[list[tuple[int, int]]] = [[]]
    for block in run:
        if any(
            _is_structural_line(line, keywords)
            for line in block_content_lines(seg_list, *block)
        ):
            parts.append([])
            continue
        parts[-1].append(block)
    return [
        part
        for part in parts
        if len(part) >= FLATTENED_PARAGRAPH_MIN_RUN and run_is_crushed(seg_list, part)
    ]


def _is_structural_line(line: str, keywords: Keywords) -> bool:
    text = line.strip()
    return (
        _EQUATION_NUMBER_RE.match(text) is not None
        or _LIST_OPENER_RE.match(text) is not None
        or is_caption_label(text, keywords)
    )


def swallowed_prose(block: list[str]) -> bool:
    """True when a math span of `block` holds prose the recognition closed over."""
    return any(_span_swallowed_prose(span) for span in math_spans("\n".join(block)))


def _span_swallowed_prose(span: str) -> bool:
    return any(
        _reads_as_word(pair.group(1)) and _reads_as_word(pair.group(2))
        for pair in _PROSE_PAIR_RE.finditer(_bare_math(math_span_content(span)))
    )


def _reads_as_word(word: str) -> bool:
    """True when `word` carries a lower-case letter, the way a written word does.

    A formula writes its names in capitals (`$ABC DEF$`). A script with no case
    reads as a name.
    """
    return word != word.upper()


def _sound_spans_kept(
    old_text: str,
    new_text: str,
    opened: Callable[[str], bool] = _span_swallowed_prose,
) -> bool:
    """True when every span the route did not open comes back as it stood.

    The route's own check reads the whole text, which would let a sound
    formula change alongside the damaged one.
    """
    sound = Counter(span for span in math_spans(old_text) if not opened(span))
    return not (sound - Counter(math_spans(new_text)))


def _bare_math(content: str) -> str:
    """`content` with everything a formula is written out of read as a hole.

    Environments, then commands, then groups innermost outwards, so a group's
    braces go with it.
    """
    text = _MATH_ENVIRONMENT_RE.sub(_MATH_HOLE, content)
    text = _MATH_COMMAND_RE.sub(_MATH_HOLE, text)
    previous = ""
    while previous != text:
        previous = text
        text = _MATH_GROUP_RE.sub(_MATH_HOLE, text)
    return text


def broken_formula(block: list[str]) -> bool:
    """True when `block` holds a span the renderer refuses.

    Every delimiter has to pair first: this route may move one but never add
    one.
    """
    spans = math_spans("\n".join(block))
    if any(not _closed_span(span) for span in spans):
        return False
    return any(_broken_span(span) for span in spans)


def _closed_span(span: str) -> bool:
    return len(span) > 1 and span.endswith("$")


def _broken_span(span: str) -> bool:
    return not is_valid_math(math_span_content(span))


def _formula_renders(text: str) -> bool:
    return not any(_broken_span(span) for span in math_spans(text))


def _content_tokens(text: str) -> list[str]:
    """`text` read as content, with every token this route may move taken out.

    The delimiters go too, so a moved one leaves the sequence as it was; a
    `.` after a sizing command goes with it, being the invisible delimiter.
    """
    tokens: list[str] = []
    sized = False
    for token in _MARKUP_TOKEN_RE.findall(_MATH_ENVIRONMENT_RE.sub(" ", text)):
        if sized and token == ".":  # noqa: S105 -- `token` is a parsed markup token, not a credential
            sized = False
            continue
        sized = token in _SIZING_COMMANDS
        if token in _MARKUP_TOKENS:
            continue
        tokens.append(token)
    return tokens


def _bare_delimiters(text: str) -> int:
    return sum(1 for token in _MARKUP_TOKEN_RE.findall(text) if token == "$")  # noqa: S105 -- markup token, not a credential


def _runs_through(inner: list[str], outer: list[str]) -> bool:
    rest = iter(outer)
    return all(token in rest for token in inner)


def _prose_drawn_into_math(old_text: str, new_text: str) -> bool:
    """True when a span of the reply closed over prose no span of the zone held.

    That is the swallowed-prose defect, written by this route's repair.
    """
    old = Counter(span for span in math_spans(old_text) if _span_swallowed_prose(span))
    new = Counter(span for span in math_spans(new_text) if _span_swallowed_prose(span))
    return bool(new - old)


def _span_repaired_in_place(old_span: str, new_span: str) -> bool:
    """True when the reply repaired `old_span` where the span stood.

    The span's content comes back in order and may only gain: a delimiter moved
    inwards leaves raw LaTeX in the prose, and an order, unlike a count, stops
    two equal tokens from trading places across it. An environment name may
    only be one this span already declares.
    """
    if not _runs_through(
        _content_tokens(math_span_content(old_span)),
        _content_tokens(math_span_content(new_span)),
    ):
        return False
    named = set(_MATH_ENVIRONMENT_NAME_RE.findall(new_span))
    return named <= set(_MATH_ENVIRONMENT_NAME_RE.findall(old_span))


def _formula_markup_kept(old_text: str, new_text: str) -> bool:
    """True when the reply repaired markup and nothing else.

    The delimiter and span counts hold, every span the renderer accepted comes
    back as it stood, no span swallows new prose, each span is repaired in
    place, and the content survives token for token once markup is read away.
    """
    if _bare_delimiters(old_text) != _bare_delimiters(new_text):
        return False
    old_spans = math_spans(old_text)
    new_spans = math_spans(new_text)
    if len(old_spans) != len(new_spans):
        return False
    if not _sound_spans_kept(old_text, new_text, _broken_span):
        return False
    if _prose_drawn_into_math(old_text, new_text):
        return False
    if any(
        not _span_repaired_in_place(old_span, new_span)
        for old_span, new_span in zip(old_spans, new_spans, strict=True)
    ):
        return False
    return _content_tokens(old_text) == _content_tokens(new_text)


def zone_what(crushed: bool, swallowed: bool = False, markup: bool = False) -> str:
    """The zone's shape as the trace and the log name it."""
    names: list[str] = []
    if crushed:
        names.append(_CRUSHED_ZONE_NAME)
    if swallowed:
        names.append(_MATH_ZONE_NAME)
    if markup:
        names.append(_MARKUP_ZONE_NAME)
    return ", ".join(names)


# The prompt explains "read-only" once; a label only tells the parts apart.
_CONTEXT_ABOVE_LABEL = "Context above the zone (read-only, not the zone):\n"
_CONTEXT_BELOW_LABEL = "Context below the zone (read-only, not the zone):\n"


def _bounded_context(lines: list[str]) -> list[str] | None:
    if sum(len(line) for line in lines) > MAX_CONTEXT_CHARS:
        return None
    return lines


def context_before(seg_list: list[Segment], index: int) -> list[str] | None:
    """The plain block immediately above `index`, or None past a protected zone."""
    gap = index
    while gap > 0:
        line, protected = seg_list[gap - 1]
        if protected or line.strip():
            break
        gap -= 1
    if gap == 0 or seg_list[gap - 1][1]:
        return None
    start = gap
    while start > 0:
        prev_line, prev_protected = seg_list[start - 1]
        if prev_protected or not prev_line.strip():
            break
        start -= 1
    return _bounded_context([seg_list[k][0] for k in range(start, gap)])


def context_after(seg_list: list[Segment], end: int) -> list[str] | None:
    """The plain block immediately below `end`, or None past a protected zone."""
    gap = end
    while gap < len(seg_list):
        line, protected = seg_list[gap]
        if protected or line.strip():
            break
        gap += 1
    if gap >= len(seg_list) or seg_list[gap][1]:
        return None
    stop = block_end(seg_list, gap)
    return _bounded_context([seg_list[k][0] for k in range(gap, stop)])


def _context_parts(
    zone_text: str,
    before: list[str] | None,
    after: list[str] | None,
    label: str = "",
) -> list[TextPart]:
    """The request parts for one zone, in document order.

    Checks judge the zone alone, so a reply that folds context in reverts like
    any invented content; that keeps context read-only.
    """
    parts: list[TextPart] = []
    if before:
        parts.append(TextPart(_CONTEXT_ABOVE_LABEL + "\n".join(before)))
    parts.append(TextPart(label + zone_text))
    if after:
        parts.append(TextPart(_CONTEXT_BELOW_LABEL + "\n".join(after)))
    return parts


def process_zone(
    block: list[str],
    op: PostOperation,
    words: BodyWords,
    *,
    swallowed_math: bool = False,
    broken_markup: bool = False,
    context_before: list[str] | None = None,
    context_after: list[str] | None = None,
    trace: LlmTrace | None = None,
    what: str = "zone",
) -> ZoneOutcome:
    """Repair one damaged block.

    A zone is a crushed run unless `swallowed_math` or `broken_markup` says
    otherwise. A rejected reply gets one retry with the reason in a part of
    its own; an echo reverts at once. `words` attests hyphenation joins.
    """
    zone_text = "\n".join(block)
    if swallowed_math:
        label = _MATH_ZONE_LABEL
    elif broken_markup:
        label = _MARKUP_ZONE_LABEL
    else:
        label = _CRUSHED_ZONE_LABEL
    context_parts = _context_parts(zone_text, context_before, context_after, label)
    parts: list[TextPart] = context_parts
    refused: set[str] = set()
    unchanged = False
    for attempt in (1, 2):  # the initial attempt plus one retry
        try:
            reply = op.provider.generate(op.prompt, parts)
        except ProviderError as exc:
            # The zone is lost, not the stage.
            return ZoneOutcome(block, False, refused_joins=len(refused), failure=exc)
        if trace is not None:
            trace.record(TRACE_OP, what, parts, reply, attempt=attempt)
        candidate = _reply_lines(reply)
        verdict = _repaired_zone(
            block,
            candidate,
            words,
            delimiters_only=swallowed_math,
            markup_only=broken_markup,
        )
        refused.update(verdict.unattested)
        if verdict.lines is not None:
            return ZoneOutcome(verdict.lines, True, len(verdict.joins), len(refused))
        assert verdict.reason is not None  # every rejection branch below sets one
        unchanged = verdict.unchanged
        if unchanged:
            break  # an echo is terminal: a retry note has nothing to correct
        parts = [*context_parts, TextPart(retry_note(verdict.reason))]
    return ZoneOutcome(block, False, refused_joins=len(refused), unchanged=unchanged)


@dataclass(frozen=True)
class _ZoneVerdict:
    """The verdict on one reply: `lines` when accepted, `reason` when not.

    `joins` and `unattested` are reported either way: a join costs no token,
    so no other check sees it.
    """

    lines: list[str] | None
    reason: str | None
    joins: tuple[str, ...] = ()
    unattested: tuple[str, ...] = ()
    unchanged: bool = False


def _repaired_zone(
    original_lines: list[str],
    candidate: list[str],
    words: BodyWords,
    *,
    delimiters_only: bool = False,
    markup_only: bool = False,
) -> _ZoneVerdict:
    """Validate a reply for one zone.

    In order: not empty, not an echo, content preserved, rendered (for a
    markup zone), no protected zone, no invented grid (for a crushed run),
    joins attested, no finding left on re-cleaning, table width kept. The echo
    check is direct: this step opens zones the cleaner's detectors need not
    see. Re-cleaning then says whether the defect is gone, a letter-spaced run
    aside, which only the spacing route answers for. The width check reads the
    re-cleaned lines.
    """
    if not candidate:
        return _ZoneVerdict(None, _EMPTY_REPLY_REASON)
    if normalized_zone(candidate) == normalized_zone(original_lines):
        return _ZoneVerdict(None, _UNRESOLVED_REASON, unchanged=True)
    crushed = not delimiters_only and not markup_only
    if not _content_preserved(
        original_lines,
        candidate,
        delimiters_only=delimiters_only,
        markup_only=markup_only,
    ):
        reason = _preservation_reason(
            original_lines,
            candidate,
            delimiters_only=delimiters_only,
            markup_only=markup_only,
        )
        return _ZoneVerdict(None, reason)
    if markup_only and not _formula_renders("\n".join(candidate)):
        return _ZoneVerdict(None, _MARKUP_UNRENDERED_REASON)
    if any(protected for _, protected in segments("\n".join(candidate))):
        return _ZoneVerdict(None, _PROTECTED_ZONE_REASON)
    if crushed and any(has_cell_separator(line) for line in candidate):
        return _ZoneVerdict(None, _INVENTED_TABLE_REASON)
    made = _hyphen_joins(original_lines, candidate, gap_tolerant=crushed)
    joined = tuple(word for word, _ in made)
    unattested = tuple(word for word, seam in made if not words.attests(word, seam))
    if unattested:
        reason = _INVENTED_JOIN_REASON.format(word=unattested[0])
        return _ZoneVerdict(None, reason, joined, unattested)
    # No base_dir: post cannot fix a missing image, so links are not re-checked.
    recleaned = clean_with_report("\n".join(candidate))
    standing = [
        finding
        for finding in recleaned.findings
        if finding.kind != LETTER_SPACING_FINDING
    ]
    if not recleaned.body.strip() or standing:
        return _ZoneVerdict(None, _UNRESOLVED_REASON, joined)
    repaired_lines = recleaned.body.rstrip("\n").split("\n")
    if _row_off_table_width(repaired_lines):
        return _ZoneVerdict(None, _TABLE_WIDTH_REASON, joined)
    return _ZoneVerdict(repaired_lines, None, joined)


def _row_off_table_width(lines: list[str]) -> bool:
    """True when a table in `lines` holds a row off its own separator's width.

    The reply's own separator is the yardstick. A delimiter row counts only
    under a pipe-bearing line, and with a row below or a pipe of its own, so a
    setext underline or a thematic break is not read as one. No row has to
    agree with the separator: that is the shape this catches.
    """
    for index, line in enumerate(lines):
        if not is_table_separator(line.strip()):
            continue
        if index == 0 or "|" not in lines[index - 1]:
            continue
        rows: list[str] = []
        below = index + 1
        while below < len(lines) and lines[below].strip() and "|" in lines[below]:
            rows.append(lines[below])
            below += 1
        if not rows and "|" not in line:
            continue
        rows.append(lines[index - 1])
        width = len(table_cells(line))
        if any(len(table_cells(row)) != width for row in rows):
            return True
    return False


def _content_preserved(
    original: list[str],
    candidate: list[str],
    *,
    delimiters_only: bool = False,
    markup_only: bool = False,
) -> bool:
    """True when `candidate` keeps `original`'s words, punctuation, and math.

    A markup zone and a swallowed-prose zone are judged by their own
    invariants alone. A crushed run compares token multisets, since its repair
    reorders content; its math spans must match as their own multiset, since
    `$x+y$` into `$x$ + y` keeps every token.
    """
    old_text = "\n".join(original)
    new_text = "\n".join(candidate)
    if markup_only:
        return _formula_markup_kept(old_text, new_text)
    if delimiters_only:
        return math_delimiters_only_moved(old_text, new_text) and _sound_spans_kept(
            old_text, new_text
        )
    if Counter(math_spans(old_text)) != Counter(math_spans(new_text)):
        return False
    return Counter(_significant_tokens(original, gap_tolerant=True)) == Counter(
        _significant_tokens(candidate, gap_tolerant=True)
    )


def _preservation_reason(
    original: list[str],
    candidate: list[str],
    *,
    delimiters_only: bool = False,
    markup_only: bool = False,
) -> str:
    """Why `_content_preserved` rejected `candidate`, as a short category.

    Math first, as the check runs. A swallowed-prose or markup zone changes
    its spans by design, so its reason names the moved word or character
    instead, or the rule it broke.
    """
    old_text = "\n".join(original)
    new_text = "\n".join(candidate)
    if markup_only:
        clause = _token_clause(
            Counter(_content_tokens(old_text)), Counter(_content_tokens(new_text))
        )
        if not clause:
            return _MARKUP_KEPT_REASON
        return f"the formula's content changed ({clause})"
    if not delimiters_only and Counter(math_spans(old_text)) != Counter(
        math_spans(new_text)
    ):
        return "a formula's content changed; math spans must match the original exactly"
    crushed = not delimiters_only
    old_tokens = Counter(_significant_tokens(original, gap_tolerant=crushed))
    new_tokens = Counter(_significant_tokens(candidate, gap_tolerant=crushed))
    clause = _token_clause(old_tokens, new_tokens)
    if not clause:
        return _MATH_MOVE_REASON
    return f"words or punctuation changed ({clause})"


def _token_clause(old_tokens: Counter[str], new_tokens: Counter[str]) -> str:
    missing = sorted((old_tokens - new_tokens).elements())
    added = sorted((new_tokens - old_tokens).elements())
    clauses = []
    if missing:
        clauses.append(f"missing {', '.join(missing[:_REASON_TOKEN_LIMIT])}")
    if added:
        clauses.append(f"added {', '.join(added[:_REASON_TOKEN_LIMIT])}")
    return "; ".join(clauses)


def _reply_lines(reply: str) -> list[str]:
    """Split a model reply into lines, trimming surrounding blank lines."""
    lines = reply.replace("\r\n", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


class BodyWords:
    """The document's own words, asked whether they attest a hyphenation join.

    Built once from the body post receives, so no zone is judged against a
    word an earlier repair produced.
    """

    __slots__ = ("_sorted", "_words")

    def __init__(self, seg_list: list[Segment]) -> None:
        words: set[str] = set()
        for line, protected in seg_list:
            if protected:
                continue
            words.update(tokenize(line))
        self._words = words
        self._sorted = sorted(words)

    def attests(self, word: str, seam: int) -> bool:
        """True when the body backs `word`, split at offset `seam`.

        The word itself, or one agreeing past the split by the margin. A join
        shorter than that needs the word itself: `intonation` attests nothing
        about `into`.
        """
        if word in self._words:
            return True
        reach = seam + _JOIN_ATTEST_MARGIN
        if reach > len(word):
            return False
        prefix = word[:reach]
        index = bisect.bisect_left(self._sorted, prefix)
        return index < len(self._sorted) and self._sorted[index].startswith(prefix)


def _hyphen_joins(
    original: list[str], candidate: list[str], *, gap_tolerant: bool
) -> list[tuple[str, int]]:
    """The words `candidate` produced by closing a hyphen split of `original`.

    Each comes with the offset of its last split, which a witness must reach
    past. A split counts only when the joined word is among the reply's tokens.
    """
    prose, _ = _split_image_lines(original) if gap_tolerant else (original, [])
    pattern = _HYPHEN_GAP_SPLIT_RE if gap_tolerant else _HYPHEN_SPLIT_RE
    present = set(tokenize("\n".join(candidate)))
    joins: dict[tuple[str, int], None] = {}
    for match in pattern.finditer("\n".join(prose)):
        pieces = tokenize(match.group())
        if len(pieces) < 2:
            continue
        merged = "".join(pieces)
        if merged in present:
            joins[(merged, len(merged) - len(pieces[-1]))] = None
    return list(joins)


def _split_image_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """`lines` split into prose lines and image-only lines, order kept in each.

    A figure can sit between the halves of a split word in a crushed run.
    """
    prose: list[str] = []
    images: list[str] = []
    for line in lines:
        if IMAGE_RE.fullmatch(line.strip()):
            images.append(line)
        else:
            prose.append(line)
    return prose, images


def _significant_tokens(lines: list[str], *, gap_tolerant: bool = False) -> list[str]:
    """Reduce lines to their significant-token sequence for the preservation check.

    `gap_tolerant`, for an order-free comparison only, moves image lines after
    the prose so a join sees past them, and joins across blank lines. A
    separator or rule line gives no tokens and a cell pipe is dropped; every
    other mark is content.
    """
    image_tokens: list[str] = []
    if gap_tolerant:
        lines, images = _split_image_lines(lines)
        for image in images:
            image_tokens.extend(_TOKEN_RE.findall(image.lower()))
    hyphen_re = _HYPHEN_GAP_BREAK_RE if gap_tolerant else _HYPHEN_BREAK_RE
    text = hyphen_re.sub(r"\1", "\n".join(lines))
    tokens: list[str] = []
    for line in text.split("\n"):
        core = line.strip()
        if is_table_separator(core) or is_thematic_break(core):
            continue
        tokens.extend(
            token
            for token in _TOKEN_RE.findall(line.lower())
            if token != _TABLE_CELL_TOKEN
        )
    tokens.extend(image_tokens)
    return tokens
