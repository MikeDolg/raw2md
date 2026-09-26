"""What an applied inspection edit is allowed to change.

The address confirms where `new` lands, not what it carries, so this guard is
what keeps model output from rewriting the body. Every edit passes the bans;
a line that reads as crushed structure may be rebuilt over several lines if its
content survives token for token, and a math span is open only when the tool
already condemns it. One shape is placed rather than refused: a single sentence
mark behind a display line's closing `$$`, which `display_tail_fold` moves
inside the span. `latex_fix` opens every span to a rewrite. Refusal is the cheap
side: a rejected edit leaves the engine's text, a wrong one a plausible falsehood.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable
from itertools import combinations, pairwise

from raw2md.cleaning.findings import block_shows_defect
from raw2md.mdtext.formulas import (
    is_broken_display_line,
    is_broken_math_span,
    math_delimiters_only_moved,
)
from raw2md.mdtext.lines import ATX_HEADING_RE, is_table_separator
from raw2md.mdtext.links import HTML_IMG_RE, IMAGE_RE
from raw2md.mdtext.math_spans import (
    RAW_LATEX_SPAN_RE,
    mask_math,
    math_span_content,
    math_span_ranges,
    math_spans,
)
from raw2md.mdtext.tables import cell_values, has_cell_separator, table_cells
from raw2md.mdtext.zones import mask_inline_code
from raw2md.source_text import SourceText, hyphen_forms, tokenize

# A JSON escape written out as text. The lookahead keeps `\nu` and `\times`
# out; an escape before a Latin letter is left to the backslash-command and
# math bans.
_LITERAL_ESCAPE_RE = re.compile(r"\\[nrt](?![A-Za-z])")

# Matched by its keys rather than by decoding, so a fragment is caught too.
_PROTOCOL_JSON_RE = re.compile(r'\{\s*"(?:line|old|new|flag)"\s*:')

# A line holding only one of these words is the tool's vocabulary leaking
# into the body.
DEFECT_TYPES = frozenset(
    {
        "broken-formula",
        "broken-image",
        "broken-table",
        "flattened-block",
        "flattened-paragraphs",
        "hyphenation",
        "hyphenation-gap",
        "run-in-heading",
    }
)

# A model composes a defect name to the pattern (`broken-block` is no real
# type), so the shape counts too. A single word is not enough: swapping a
# Cyrillic lookalike for a Latin unit is a repair.
_DEFECT_NAME_RE = re.compile(r"[a-z]+(?:-[a-z]+)+")

# Letters around a digit run are not compared, so the case of a part code
# stays open to a fix.
_DIGITS_RE = re.compile(r"\d+")

# Blanked to a space before delimiters are counted, so a printed `\$` is no
# delimiter while `\\$` still is. A space keeps the neighbours from closing up.
_ESCAPE_PAIR_RE = re.compile(r"\\.", re.DOTALL)

_DOLLAR_RUN_RE = re.compile(r"\$+")

# A letter, then a hyphen at the end of the line. A digit before the hyphen
# belongs to a range or a part code.
_LINE_BREAK_HYPHEN_RE = re.compile(r"[^\W\d_]-$")

# A run of letters (`\textsuperscript`) or one escaped character (`\$`, `\\`):
# outside math neither renders as anything.
_BACKSLASH_COMMAND_RE = re.compile(r"\\(?:[A-Za-z]+|.)")

# CommonMark has no sub/superscript syntax, so pandoc and marker write raw HTML
# (`CO<sub>2</sub>`, `mm<sup>2</sup>`); the tag is the only trace of the meaning.
_INLINE_MARKUP_RE = re.compile(r"</?su[bp]\b[^>]*>", re.IGNORECASE)

# `*m*`, `**n**`, `_p_`, `__q__`; a mismatched pair (`*m_`) does not count.
_ONE_LETTER_EMPHASIS_RE = re.compile(r"(?<!\w)(\*\*|__|\*|_)([^\W\d_])\1(?!\w)")

# Consecutive matches are checked pairwise: one combined pattern would consume
# a word and miss it as the first word of the next pair.
_WORD_RE = re.compile(r"\w+")

# Markup a crushed line may regain, stripped from both sides of the comparison.
_REBUILD_MARKUP_RE = re.compile(r"[|#*_`]")

# A token of separator characters (`---`, `:--:`) is structure, not content.
_SEPARATOR_TOKEN_RE = re.compile(r"^[-:]+$")

# The marks a sentence closes a display formula with; the cleaner folds the
# same set back inside a block.
_DISPLAY_TAIL_MARKS = frozenset(",.;")

# A renderer prints the equation number last, so a folded mark goes before it.
_TRAILING_TAG_RE = re.compile(r"\\tag\{[^{}]*\}\s*$")


def rejection_reason(
    old: str,
    new: str,
    source_text: SourceText | None = None,
    source_page: int | None = None,
    body_hyphens: frozenset[str] = frozenset(),
    latex_fix: bool = False,
) -> str | None:
    """Why substituting `new` for `old` must be refused, or None to allow it.

    `old` is the line as the body holds it, not the model's echo. `source_text`
    and `body_hyphens` witness a word coming apart; None attests nothing.
    `source_page` is the 0-based page of the address, which scopes the
    word-split witness. `latex_fix` opens every math span to a rewrite.
    """
    crushed = _reads_as_crushed(old)
    rebuild = crushed and _rebuild_keeps_content(old, new)
    # Order matters: the first ban that refuses names the reason in the log.
    bans: tuple[Callable[[], str | None], ...] = (
        lambda: _image_links_kept(old, new),
        lambda: _no_literal_escape(old, new),
        lambda: _no_protocol_json(old, new),
        lambda: _no_defect_name(old, new),
        lambda: _math_spans_kept(old, new, latex_fix),
        lambda: _digits_kept(old, new, latex_fix),
        lambda: _table_row_shape_kept(old, new, rebuild),
        lambda: _table_grid_kept(old, new),
        lambda: _no_cell_collision(old, new),
        lambda: _math_delimiter_parity_kept(old, new),
        lambda: _display_line_shape_kept(old, new),
        lambda: _no_span_duplicate_insertion(old, new),
        lambda: _line_break_hyphen_kept(old, new),
        lambda: _heading_marker_kept(old, new, rebuild),
        lambda: _inline_markup_kept(old, new, rebuild),
        lambda: _one_letter_emphasis_kept(old, new, rebuild),
        lambda: _no_new_backslash_commands(old, new),
    )
    for ban in bans:
        reason = ban()
        if reason is not None:
            return reason
    reason = _no_unattested_word_split(old, new, source_text, source_page)
    if reason is not None:
        return reason
    reason = _no_unattested_word_break(old, new, source_text, body_hyphens)
    if reason is not None:
        return reason
    return _rebuild_reason(old, new, crushed, rebuild)


def _no_unattested_word_split(
    old: str, new: str, source_text: SourceText | None, source_page: int | None
) -> str | None:
    """Refuse a replacement that inserts a space inside a token whole in `old`.

    The ban stands aside when the source's text layer on `source_page` holds
    both halves: two words a converter ran together. A pair `old` already
    carried is exempt by count. Joining stays free: a wrong join is still a
    real word, a wrong split invents one.
    """
    old_tokens = frozenset(tokenize(old))
    old_pairs = Counter(_adjacent_tokens(old))
    for pair in _adjacent_tokens(new):
        if old_pairs[pair] > 0:
            old_pairs[pair] -= 1
            continue
        first, second = pair
        if first + second not in old_tokens:
            continue
        if (
            source_text is not None
            and source_text.has_token(first, page=source_page)
            and source_text.has_token(second, page=source_page)
        ):
            continue
        return "word split without a source witness"
    return None


def _adjacent_tokens(text: str) -> list[tuple[str, str]]:
    """Adjacent word tokens of `text`, normalized as `SourceText.has_token` reads."""
    pairs: list[tuple[str, str]] = []
    for left, right in pairwise(_WORD_RE.finditer(text)):
        if not text[left.end() : right.start()].isspace():
            continue
        left_tok = tokenize(left.group())
        right_tok = tokenize(right.group())
        if len(left_tok) == 1 and len(right_tok) == 1:
            pairs.append((left_tok[0], right_tok[0]))
    return pairs


def _no_unattested_word_break(
    old: str,
    new: str,
    source_text: SourceText | None,
    body_hyphens: frozenset[str],
) -> str | None:
    """Refuse a replacement that breaks a token whole in `old` with a hyphen.

    The model reading the page brings back a typesetter's line break. A
    compound whose hyphen the conversion dropped is a real repair, so a form
    the body or the source's text layer spells passes. The break character is
    part of the spelling. Math is left out: there a dash is a minus.
    """
    old_prose = _outside_math(old)
    old_tokens = frozenset(tokenize(old_prose))
    old_forms = Counter(hyphen_forms(old_prose))
    for form in hyphen_forms(_outside_math(new)):
        if old_forms[form] > 0:
            old_forms[form] -= 1
            continue
        if "".join(tokenize(form)) not in old_tokens:
            continue
        if form in body_hyphens:
            continue
        if source_text is not None and source_text.has_hyphen_form(form):
            continue
        return "word break without a witness"
    return None


def _image_links_kept(old: str, new: str) -> str | None:
    """Refuse an edit that adds, drops, or repoints an image link.

    Compared in order: swapping two targets on one line keeps the multiset.
    """
    if _image_targets(old) != _image_targets(new):
        return "image links changed"
    return None


def _image_targets(text: str) -> list[str]:
    found = [(match.start(), match.group(2)) for match in IMAGE_RE.finditer(text)]
    found += [(match.start(), match.group(2)) for match in HTML_IMG_RE.finditer(text)]
    return [target for _, target in sorted(found)]


def _no_literal_escape(old: str, new: str) -> str | None:
    """Refuse a replacement that writes an escape sequence as two characters.

    Counted, so a line that already carries one can still be edited.
    """
    if _count(_LITERAL_ESCAPE_RE, new) > _count(_LITERAL_ESCAPE_RE, old):
        return "literal escape sequence"
    return None


def _no_protocol_json(old: str, new: str) -> str | None:
    """Refuse a replacement carrying the edit protocol itself into the body."""
    if _count(_PROTOCOL_JSON_RE, new) > _count(_PROTOCOL_JSON_RE, old):
        return "protocol object in the replacement"
    if _is_json_container(new) and not _is_json_container(old):
        return "replacement parses as json"
    return None


def _no_defect_name(old: str, new: str) -> str | None:
    """Refuse a replacement that is nothing but the name of a defect type.

    A model may answer a zone it cannot rebuild with the defect name, which
    then reads as prose downstream. Price: a line that is one hyphenated Latin
    word cannot be edited. A line that already was such a name stays open.
    """
    if not _is_defect_name(new) or _is_defect_name(old):
        return None
    return "defect name as the replacement"


def _is_defect_name(text: str) -> bool:
    stripped = text.strip()
    return stripped in DEFECT_TYPES or _DEFECT_NAME_RE.fullmatch(stripped) is not None


def _is_json_container(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return False
    try:
        return isinstance(json.loads(stripped), dict | list)
    except ValueError:
        return False


def _math_spans_kept(old: str, new: str, latex_fix: bool) -> str | None:
    """Refuse an edit that rewrites math the tool has no reason to doubt.

    Only a span `is_broken_math_span` condemns may change, and it must come
    out valid; the span count and the text around the spans must hold. A
    delimiter move is allowed. A formula cut into one broken span per line is
    judged whole. A `$$` pair on lines of its own leaves a content line with no
    delimiter, which reads here as prose.
    """
    old_spans = math_spans(old)
    new_spans = math_spans(new)
    if old_spans == new_spans or math_delimiters_only_moved(old, new):
        return None
    if len(old_spans) != len(new_spans):
        return "math span count changed"
    if not _outside_math_kept(old, new):
        return "edit changes math and the text around it"
    if _splits_one_formula(old):
        if is_broken_math_span(_joined_formula(new)):
            return "rebuilt math span still broken"
        return None
    for before, after in zip(old_spans, new_spans, strict=True):
        if before == after:
            continue
        if not latex_fix and not is_broken_math_span(before):
            return "valid math span changed"
        if is_broken_math_span(after):
            return "rebuilt math span still broken"
    return None


def _digits_kept(old: str, new: str, latex_fix: bool) -> str | None:
    """Refuse an edit that changes the line's numbers.

    Outside math the digit runs hold both ways. Inside a span, which may be
    rebuilt, no number it did not carry may appear; the halves are weighed
    apart, so a prose number cannot pay for a new index. A delimiter move is
    judged on the whole line. `latex_fix` drops the inside-math half.
    """
    if math_delimiters_only_moved(old, new):
        if _digit_runs(old) != _digit_runs(new):
            return "digit runs changed"
        return None
    if _digit_runs(_outside_math(old)) != _digit_runs(_outside_math(new)):
        return "digit runs changed"
    if not latex_fix and Counter(_math_digit_runs(new)) - Counter(
        _math_digit_runs(old)
    ):
        return "digit runs added"
    return None


def _digit_runs(text: str) -> list[str]:
    return _DIGITS_RE.findall(text)


def _math_digit_runs(text: str) -> list[str]:
    return _digit_runs("".join(math_spans(text)))


def _count(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text))


def _table_row_shape_kept(old: str, new: str, rebuild: bool) -> str | None:
    """Refuse an edit that changes a table row's cell count, delimiter included.

    The count measures the table's width for every row after it. Only a
    rebuild may change it; recutting a short row is post's route.
    """
    if rebuild:
        return None
    if "|" not in old:
        return None
    if len(table_cells(old)) != len(table_cells(new)):
        return "table cell count changed"
    return None


def _table_grid_kept(old: str, new: str) -> str | None:
    r"""Refuse an edit that dissolves a row's grid without changing its width.

    A one-cell row collapses into prose at an unchanged count, and a separator
    row can trade places with a data row. A rebuild is not exempt.
    """
    if has_cell_separator(old) and not has_cell_separator(new):
        return "table row lost its cells"
    if is_table_separator(old.strip()) != is_table_separator(new.strip()):
        return "table separator row changed"
    return None


def _no_cell_collision(old: str, new: str) -> str | None:
    """Refuse an edit that makes one cell of a row read the same as another.

    A value copied into its neighbour erases a distinction the row held on
    purpose, such as a printed error beside its correction. Only a pair `old`
    told apart is judged, padding stripped.
    """
    if "|" not in old or is_table_separator(old.strip()):
        return None
    old_cells = [cell.strip() for cell in table_cells(old)]
    new_cells = [cell.strip() for cell in table_cells(new)]
    if len(old_cells) != len(new_cells):
        return None
    for left, right in combinations(range(len(old_cells)), 2):
        if old_cells[left] == old_cells[right]:
            continue
        if new_cells[left] == new_cells[right]:
            return "edit made a row's cells match"
    return None


def _math_delimiter_parity_kept(old: str, new: str) -> str | None:
    r"""Refuse an edit that changes the address's unpaired math delimiters by an
    odd number, ``$$`` and ``$`` counted apart.

    A lone delimiter damages nothing on its own line but closes every later one
    against the wrong partner. An even change passes: a replacement may open
    and close its own block. What it does to the formula is `_math_spans_kept`'s.
    """
    old_delimiters = _unpaired_delimiters(old)
    new_delimiters = _unpaired_delimiters(new)
    for kind in ("$$", "$"):
        if (new_delimiters[kind] - old_delimiters[kind]) % 2 != 0:
            return "math delimiter parity changed"
    return None


def _unpaired_delimiters(text: str) -> Counter[str]:
    """The math delimiters of `text` that bound no span of their own, by kind.

    A region ending on a dollar is closed, a tail an escape cut short
    included; one ending elsewhere contributes its opener.
    """
    masked = mask_inline_code(text)
    counts: Counter[str] = Counter()
    last = 0
    for start, end in math_span_ranges(masked):
        counts += _loose_delimiters(masked[last:start])
        region = masked[start:end]
        if not region.endswith("$"):
            counts["$$" if region.startswith("$$") else "$"] += 1
        last = end
    counts += _loose_delimiters(masked[last:])
    return counts


def _loose_delimiters(text: str) -> Counter[str]:
    """The delimiters of a stretch that no math region covers, by kind.

    Two dollars are one display delimiter, unless glued between alphanumerics:
    `a$$b` is two inline ones, as the quality check reads it. Any other run
    counts as that many inline delimiters.
    """
    plain = _ESCAPE_PAIR_RE.sub(" ", text)
    counts: Counter[str] = Counter()
    for match in _DOLLAR_RUN_RE.finditer(plain):
        before = plain[match.start() - 1] if match.start() else ""
        after = plain[match.end()] if match.end() < len(plain) else ""
        if match.end() - match.start() == 2 and not (
            before.isalnum() and after.isalnum()
        ):
            counts["$$"] += 1
        else:
            counts["$"] += match.end() - match.start()
    return counts


def _display_line_shape_kept(old: str, new: str) -> str | None:
    """Refuse a replacement that leaves text behind a display line's closer.

    Text after the closing `$$` makes the parser read it as an opener, and the
    whole block shows as source. Held only where the line stood as one display
    formula; a mark `display_tail_fold` places is exempt.
    """
    old_shape = _one_display_span(old)
    if old_shape is None or old_shape[0].strip() or old_shape[2].strip():
        return None
    new_shape = _one_display_span(new)
    if new_shape is None or not new_shape[2].strip():
        return None
    if display_tail_fold(old, new) is not None:
        return None
    return "text behind the closing display delimiter"


def display_tail_fold(old: str, new: str) -> str | None:
    """`new` with the mark behind its closing `$$` folded inside the span.

    The caller applies it once the edit is allowed. Only a single `,`, `.`, or
    `;` behind a line that stood as one display formula is placed, in front of
    an equation number. None for anything else, a formula already ending in
    such a mark included: there the reply restates the span.
    """
    if "\n" in new:
        return None
    old_shape = _one_display_span(old)
    if old_shape is None or old_shape[0].strip() or old_shape[2].strip():
        return None
    new_shape = _one_display_span(new)
    if new_shape is None or new_shape[0].strip():
        return None
    indent, span, tail = new_shape
    mark = tail.strip()
    if mark not in _DISPLAY_TAIL_MARKS:
        return None
    content = span[2:-2]
    number = _TRAILING_TAG_RE.search(content)
    body = content[: number.start()] if number is not None else content
    if not body.strip() or body.rstrip()[-1] in _DISPLAY_TAIL_MARKS:
        return None
    tag = f" {content[number.start() :]}" if number is not None else ""
    return f"{indent}$${body.rstrip()}{mark}{tag}$$"


def _one_display_span(line: str) -> tuple[str, str, str] | None:
    """The text before `line`'s one closed display span, the span, and the rest."""
    ranges = math_span_ranges(line)
    if len(ranges) != 1:
        return None
    start, end = ranges[0]
    span = line[start:end]
    if not span.startswith("$$") or not span.endswith("$$"):
        return None
    return line[:start], span, line[end:]


def _no_span_duplicate_insertion(old: str, new: str) -> str | None:
    r"""Refuse an insertion beside an untouched span that repeats what it says.

    A value spelled inside a formula and again in the prose beside it passes
    every other ban. Only a run added flush against the edge of a span the edit
    leaves alone is read, against the span's rendered tokens with command
    names stripped, so `\left(x\right)` does not claim the word "left". The run
    must occur as a run: `40 mm` beside `40\,\mathrm{mm}` is caught.
    """
    if math_spans(old) != math_spans(new):
        return None
    old_ranges = math_span_ranges(old)
    new_ranges = math_span_ranges(new)
    for index, (old_range, new_range) in enumerate(
        zip(old_ranges, new_ranges, strict=True)
    ):
        span_tokens = _span_content_tokens(old[old_range[0] : old_range[1]])
        if not span_tokens:
            continue
        old_before_start = old_ranges[index - 1][1] if index else 0
        new_before_start = new_ranges[index - 1][1] if index else 0
        added_before = _appended_tokens(
            old[old_before_start : old_range[0]], new[new_before_start : new_range[0]]
        )
        if _holds_run(span_tokens, added_before):
            return "insertion duplicates a neighbouring span"
        old_after_end = (
            old_ranges[index + 1][0] if index + 1 < len(old_ranges) else len(old)
        )
        new_after_end = (
            new_ranges[index + 1][0] if index + 1 < len(new_ranges) else len(new)
        )
        added_after = _prepended_tokens(
            old[old_range[1] : old_after_end], new[new_range[1] : new_after_end]
        )
        if _holds_run(span_tokens, added_after):
            return "insertion duplicates a neighbouring span"
    return None


def _span_content_tokens(span: str) -> list[str]:
    """The tokens a reader gets from `span`'s content, command names stripped."""
    content = _BACKSLASH_COMMAND_RE.sub(" ", math_span_content(span))
    return tokenize(content)


def _appended_tokens(old_segment: str, new_segment: str) -> list[str]:
    """Tokens `new_segment` adds after `old_segment`'s tokens kept as a prefix."""
    old_tokens = tokenize(old_segment)
    new_tokens = tokenize(new_segment)
    if new_tokens[: len(old_tokens)] != old_tokens:
        return []
    return new_tokens[len(old_tokens) :]


def _prepended_tokens(old_segment: str, new_segment: str) -> list[str]:
    """Tokens `new_segment` adds before `old_segment`'s tokens kept as a suffix."""
    old_tokens = tokenize(old_segment)
    new_tokens = tokenize(new_segment)
    if not old_tokens:
        return new_tokens
    if new_tokens[-len(old_tokens) :] != old_tokens:
        return []
    return new_tokens[: len(new_tokens) - len(old_tokens)]


def _holds_run(tokens: list[str], run: list[str]) -> bool:
    if not run:
        return False
    width = len(run)
    return any(
        tokens[start : start + width] == run for start in range(len(tokens) - width + 1)
    )


def _heading_marker_kept(old: str, new: str, rebuild: bool) -> str | None:
    """Refuse an edit that adds or removes a line's ATX heading marker.

    The `#` count stays free. Both ways, since losing a heading and inventing
    one are the same loss. A rebuild is exempt: it may move the marker.
    """
    if rebuild:
        return None
    had_marker = ATX_HEADING_RE.match(old) is not None
    has_marker = ATX_HEADING_RE.match(new) is not None
    if had_marker == has_marker:
        return None
    if had_marker:
        return "heading marker removed"
    return "heading marker added"


def _inline_markup_kept(old: str, new: str, rebuild: bool) -> str | None:
    """Refuse an edit that moves, adds, or drops a `<sub>`/`<sup>` tag.

    `CO<sub>2</sub>` and `CO2` read the same to every other ban. A model often
    flattens the tags while it fixes another word on the line. Each tag is
    compared with where it sits: `CO<sub>2</sub>, SO2` into `CO2, SO<sub>2</sub>`
    keeps count and order. A rebuild is exempt.
    """
    if rebuild:
        return None
    if _inline_markup_context(new) != _inline_markup_context(old):
        return "inline markup changed"
    return None


def _touching_word(text: str, index: int, *, forward: bool) -> str:
    """The run of word characters touching `text[index]` with no gap, or ""."""
    if forward:
        match = re.match(r"\w*", text[index:])
    else:
        match = re.search(r"\w*$", text[:index])
    return match.group() if match else ""


def _inline_markup_context(text: str) -> list[tuple[str, str, str]]:
    """`text`'s <sub>/<sup> tags, each paired with a signature of where it sits.

    The word touching a tag is its anchor, so an edit elsewhere cannot reach
    it. With no word on a side, the one character outside stands in: it tells
    the edge of the line from prose.
    """
    contexts = []
    for match in _INLINE_MARKUP_RE.finditer(text):
        before = (
            _touching_word(text, match.start(), forward=False)
            or text[max(0, match.start() - 1) : match.start()]
        )
        after = (
            _touching_word(text, match.end(), forward=True)
            or text[match.end() : match.end() + 1]
        )
        contexts.append((before, match.group(), after))
    return contexts


def _one_letter_emphasis_kept(old: str, new: str, rebuild: bool) -> str | None:
    """Refuse an edit that drops the emphasis around a one-letter token, or
    swaps the letter it wraps for one of a different alphabet.

    Such a letter is a variable. Italic Cyrillic prints `т` shaped like a Latin
    `m`, so a model reading the page swaps the script with the wrap standing.
    Counted by alphabet, so a fix within one alphabet stays free. Read outside
    math, where `*` and `_` are no wrap. A rebuild is exempt.
    """
    if rebuild:
        return None
    old_prose = mask_math(old)
    old_matches = _ONE_LETTER_EMPHASIS_RE.findall(old_prose)
    if not old_matches:
        return None
    new_prose = mask_math(new)
    new_matches = _ONE_LETTER_EMPHASIS_RE.findall(new_prose)
    old_alphabets = Counter(_letter_alphabet(letter) for _, letter in old_matches)
    new_alphabets = Counter(_letter_alphabet(letter) for _, letter in new_matches)
    if not old_alphabets - new_alphabets:
        return None
    if any(letter in new_prose for _, letter in old_matches):
        return "one-letter token lost its emphasis"
    return "one-letter token changed alphabet"


def _letter_alphabet(letter: str) -> str:
    """The alphabet of `letter`: the first word of its Unicode name."""
    try:
        name = unicodedata.name(letter)
    except ValueError:
        return ""
    return name.split(" ", 1)[0]


def _no_new_backslash_commands(old: str, new: str) -> str | None:
    """Refuse a replacement that introduces a backslash command outside math.

    `\\textsuperscript{...}` or a `\\\\` break renders as literal text. A
    command absent from `old` is refused even at an unchanged count. Raw LaTeX
    zones (pandoc's `\\(...\\)`) are cut from the count only while `new` holds
    no more of them than `old`; a zone dropped and another opened elsewhere
    reads as unchanged, a gap accepted.
    """
    old_prose = _outside_math(old)
    new_prose = _outside_math(new)
    if len(RAW_LATEX_SPAN_RE.findall(new_prose)) <= len(
        RAW_LATEX_SPAN_RE.findall(old_prose)
    ):
        old_prose = RAW_LATEX_SPAN_RE.sub("", old_prose)
        new_prose = RAW_LATEX_SPAN_RE.sub("", new_prose)
    old_commands = Counter(_BACKSLASH_COMMAND_RE.findall(old_prose))
    new_commands = Counter(_BACKSLASH_COMMAND_RE.findall(new_prose))
    if new_commands - old_commands:
        return "backslash command added outside math"
    return None


def _line_break_hyphen_kept(old: str, new: str) -> str | None:
    """Refuse an edit that drops the hyphen carrying a word into the line below.

    The other half is on a line this substitution cannot reach, so dropping the
    hyphen hides the split from every later repair.
    """
    if _LINE_BREAK_HYPHEN_RE.search(old.rstrip()) is None:
        return None
    if new.rstrip().endswith("-"):
        return None
    return "line-break hyphen dropped"


def table_values_kept(old: str, new: str) -> bool:
    """True when the two rows carry the same non-empty values in the same order.

    The invariant of post's row repair, made without the source page: pipes,
    padding, empty cells, and in-cell breaks move freely, but a value under a
    different header crossed a column on a guess.
    """
    return cell_values(old) == cell_values(new)


def _reads_as_crushed(old: str) -> bool:
    """True when the line itself reads as structure recognition crushed.

    A line with a border pipe at either end, or a separator row, is a standing
    row whatever its length: recutting it is post's route.
    """
    core = old.strip()
    if core.startswith("|") or core.endswith("|") or is_table_separator(core):
        return False
    return block_shows_defect("flattened-block", old.split("\n"))


def _rebuild_keeps_content(old: str, new: str) -> bool:
    """True when `new` only adds line breaks and markup to a crushed line."""
    old_tokens = _content_tokens(_INLINE_MARKUP_RE.sub("", old), _REBUILD_MARKUP_RE)
    new_tokens = _content_tokens(_INLINE_MARKUP_RE.sub("", new), _REBUILD_MARKUP_RE)
    return old_tokens == new_tokens


def _content_tokens(text: str, markup: re.Pattern[str]) -> list[str]:
    return [
        token
        for token in markup.sub(" ", text).split()
        if _SEPARATOR_TOKEN_RE.match(token) is None
    ]


def _outside_math_kept(old: str, new: str) -> bool:
    """True when the text around the math came through as the edit's shape allows.

    Byte for byte, except for a formula cut into one span per line, where only
    tokens count: the breaks between the spans are the repair's to place.
    """
    if _splits_one_formula(old):
        return _outside_math(old).split() == _outside_math(new).split()
    return _outside_math(old) == _outside_math(new)


def _splits_one_formula(text: str) -> bool:
    """True when `text` is one display formula cut into a damaged span per line."""
    lines = [line for line in text.split("\n") if line.strip()]
    return len(lines) >= 2 and all(is_broken_display_line(line) for line in lines)


def _joined_formula(text: str) -> str:
    """The one display span `text`'s spans make when read as a single formula."""
    return f"$${' '.join(math_span_content(span) for span in math_spans(text))}$$"


def _outside_math(text: str) -> str:
    parts: list[str] = []
    last = 0
    for start, end in math_span_ranges(text):
        parts.append(text[last:start])
        last = end
    parts.append(text[last:])
    return "".join(parts)


def _rebuild_reason(old: str, new: str, crushed: bool, rebuild: bool) -> str | None:
    """Why the shape of the replacement refuses this edit, or None to allow it.

    Several lines are licensed by a rebuild, or by a formula cut into one span
    per line, whose lines are the lines `old` spans.
    """
    if "\r" in new:
        # The body is newline-normalized, so a CR is a stray character.
        return "carriage return in the replacement"
    if "\n" not in new or _splits_one_formula(old):
        return None
    if not crushed:
        return "multi-line replacement"
    if not rebuild:
        return "rebuild changes the line's content"
    return None
