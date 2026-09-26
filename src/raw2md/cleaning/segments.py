"""Predicates over a classified segment list, shared by the cleaning rules.

A rule uses these when its decision depends on where a line sits: whether it
is a paragraph of its own, where its block ends, what stands before it. The
segment list comes from `mdtext`, shared with the quality evaluator.

Each definition here has more than one reader, so the readers cannot drift
apart: a repair and the detector that reports what the repair left must see
the same block, the same flattened run, and the same body word counts.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

from raw2md.mdtext.lines import ATX_HEADING_RE, is_thematic_break
from raw2md.mdtext.links import IMAGE_RE, mask_addresses
from raw2md.mdtext.math_spans import mask_math
from raw2md.mdtext.pages import page_mark_number
from raw2md.mdtext.zones import Segment, mask_inline_code

# Indentation is spaces only, as marker writes it. A thematic break `- - -`
# also matches; the caller rejects it first.
LIST_ITEM_RE = re.compile(r"^( *)([-*+]|\d{1,9}[.)])( +)(.*)$")

# A line opening with a list marker is not a flattening candidate. The marker
# may be escaped (`\-`, `3\.`), as a converter writes a literal one; the line
# is still an entry of an enumeration, not a column artifact.
LIST_MARKER_RE = re.compile(r"(?:\\?[-*+]|\d+\\?[.)])\s")

# Cyrillic as character-class ranges. The basic alphabet is contiguous at
# U+0410..U+044F; IO sits outside it (U+0401, U+0451) and joins separately.
CYRILLIC_UPPER = f"{chr(0x0410)}-{chr(0x042F)}{chr(0x0401)}"
CYRILLIC_LOWER = f"{chr(0x0430)}-{chr(0x044F)}{chr(0x0451)}"

# Longest a line may run and still read as one line of a crushed column, and
# how many such lines in a row make the shape a pattern rather than a
# coincidence.
FLATTEN_MAX_CHARS = 25
FLATTEN_MIN_RUN = 6


def is_standalone(seg_list: list[Segment], idx: int) -> bool:
    """True when the line at `idx` is a paragraph of its own.

    File edges and protected lines count as blank: a paragraph cannot continue
    across front matter, a code fence, or an HTML table.
    """
    return is_standalone_span(seg_list, idx, idx)


def is_standalone_span(seg_list: list[Segment], start: int, end: int) -> bool:
    """True when the paragraph spanning `[start, end]` is one of its own."""
    return is_blank_at(seg_list, start - 1) and is_blank_at(seg_list, end + 1)


def is_blank_at(seg_list: list[Segment], idx: int) -> bool:
    """True when `idx` is past a file edge, protected, or blank."""
    if idx < 0 or idx >= len(seg_list):
        return True
    line, protected = seg_list[idx]
    return protected or not line.strip()


def prev_content_index(seg_list: list[Segment], start: int) -> int | None:
    """Index of the nearest non-blank line before `start`."""
    for idx in range(start - 1, -1, -1):
        if seg_list[idx][0].strip():
            return idx
    return None


def is_image_only_line(line: str) -> bool:
    """True when `line` is nothing but a markdown image link."""
    return IMAGE_RE.fullmatch(line.strip()) is not None


def block_end(seg_list: list[Segment], start: int) -> int:
    """Index past the run of plain, non-blank lines starting at `start`.

    This is the block boundary that `post` sends to the LLM as one zone.
    """
    idx = start
    while idx < len(seg_list) and not seg_list[idx][1] and seg_list[idx][0].strip():
        idx += 1
    return idx


# Enough for a blank gap and a figure with its own blank margins.
_HYPHEN_GAP_MAX_SKIP = 4


def skip_hyphen_gap(seg_list: list[Segment], start: int) -> int | None:
    """Index of the first prose line at/after `start`, past the gap of a split.

    The gap is blank lines, image-only lines, and page marks. Anything else
    ends the search. None when a protected zone intervenes, the document ends,
    the gap exceeds `_HYPHEN_GAP_MAX_SKIP` lines, or no gap was skipped (the
    adjacent case is the caller's).
    """
    idx = start
    skipped = 0
    saw_gap = False
    while idx < len(seg_list):
        line, protected = seg_list[idx]
        if protected:
            return None
        if page_mark_number(line) is not None:
            # A page mark is working markup, not a page line, so it spends no
            # budget; counted, the result would depend on whether inspection
            # runs.
            saw_gap = True
            idx += 1
            continue
        if not line.strip() or is_image_only_line(line):
            if skipped >= _HYPHEN_GAP_MAX_SKIP:
                return None
            saw_gap = True
            idx += 1
            skipped += 1
            continue
        return idx if saw_gap else None
    return None


# ---- flattened paragraphs ---------------------------------------------------

# Longest a block may run and still read as a narrow-column fragment. Wider
# than `FLATTEN_MAX_CHARS`: a fragment can be a whole clause that the column
# width cut short.
FLATTENED_PARAGRAPH_MAX_CHARS = 200

# A lower bar reads a few adjacent short paragraphs as a column artifact.
FLATTENED_PARAGRAPH_MIN_RUN = FLATTEN_MIN_RUN

# A block ending on these, or on a lowercase letter, broke off mid-clause. A
# full stop, a colon, a bracket, or a digit is where a list entry ends.
_UNFINISHED_TAIL_CHARS = ",-"

# A whole-line HTML comment, such as a page mark, is not prose. A page mark
# has no blank line under it, so without this guard it opens the next block.
_COMMENT_ONLY_LINE_RE = re.compile(r"^\s*<!--.*-->\s*$")

# A legend entry under a formula (`k =`, `dn / Dn =`). Its key is often
# lowercase, but a carried-on clause never declares a symbol.
_DEFINITION_HEAD_RE = re.compile(r"^[^=\s]{1,15}(?:\s*/\s*[^=\s]{1,15})?\s*=(?!=)")


def plain_blocks(seg_list: list[Segment]) -> list[tuple[int, int]]:
    """``[start, end)`` ranges of the blocks, as `post` groups them into zones."""
    blocks: list[tuple[int, int]] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected or not line.strip():
            idx += 1
            continue
        end = block_end(seg_list, idx)
        blocks.append((idx, end))
        idx = end
    return blocks


def block_content_lines(seg_list: list[Segment], start: int, end: int) -> list[str]:
    """The lines of the block ``[start, end)``."""
    return [seg_list[k][0] for k in range(start, end)]


def is_flat_paragraph_block(
    seg_list: list[Segment], start: int, end: int, *, allow_list_item: bool = False
) -> bool:
    """True when the block ``[start, end)`` reads as a short fragment of prose.

    Headings, list items, table rows, lone images, math, quotes, and comment
    lines are excluded. A short formula beside short prose is ordinary
    structure, not a column artifact.

    `allow_list_item` admits a block that opens with a list marker. The
    deterministic join cannot tell a broken entry from the next entry, so it
    keeps the default; an LLM step that reads the whole run can.
    """
    lines = block_content_lines(seg_list, start, end)
    if not lines:
        return False
    if any(_COMMENT_ONLY_LINE_RE.match(line) for line in lines):
        return False
    if sum(len(line) for line in lines) > FLATTENED_PARAGRAPH_MAX_CHARS:
        return False
    first = lines[0].lstrip()
    if ATX_HEADING_RE.match(lines[0]):
        return False
    if not allow_list_item and LIST_MARKER_RE.match(first):
        return False
    if len(lines) == 1 and is_image_only_line(lines[0]):
        return False
    if any("$" in line for line in lines):
        return False
    if any("|" in line for line in lines):
        return False
    return not any(
        line.lstrip().startswith(">") or is_thematic_break(line.strip())
        for line in lines
    )


def block_continues(previous: Sequence[str], following: Sequence[str]) -> bool:
    """True when `following` reads as the rest of a sentence `previous` cut off.

    The earlier block breaks off mid-clause and the later one opens in
    lowercase. A list of entries opens each block with its own key instead,
    and a legend entry declares a symbol.
    """
    tail = previous[-1].rstrip() if previous else ""
    head = following[0].lstrip() if following else ""
    if not tail or not head:
        return False
    if _DEFINITION_HEAD_RE.match(head):
        return False
    cut_off = tail[-1].islower() or tail[-1] in _UNFINISHED_TAIL_CHARS
    return cut_off and head[0].islower()


def blocks_are_adjacent(seg_list: list[Segment], end: int, next_start: int) -> bool:
    """True when no protected zone separates two blocks."""
    return not any(seg_list[k][1] for k in range(end, next_start))


def flattened_paragraph_runs(
    seg_list: list[Segment], *, allow_list_item: bool = False
) -> list[list[tuple[int, int]]]:
    """Runs of paragraph fragments that a narrow two-column layout crushed.

    A narrow column read line by line turns one sentence into several one-line
    paragraphs. A run of short blocks counts only when at least one block
    continues the one before it (`block_continues`); a list of short entries
    has no such continuation. `allow_list_item` widens the fragments but not
    the continuation test.
    """
    runs: list[list[tuple[int, int]]] = []
    blocks = plain_blocks(seg_list)
    i = 0
    while i < len(blocks):
        if not is_flat_paragraph_block(
            seg_list, *blocks[i], allow_list_item=allow_list_item
        ):
            i += 1
            continue
        j = i
        while j < len(blocks) and is_flat_paragraph_block(
            seg_list, *blocks[j], allow_list_item=allow_list_item
        ):
            if j > i and not blocks_are_adjacent(
                seg_list, blocks[j - 1][1], blocks[j][0]
            ):
                break
            j += 1
        run = blocks[i:j]
        if len(run) >= FLATTENED_PARAGRAPH_MIN_RUN and run_is_crushed(seg_list, run):
            runs.append(run)
        i = j
    return runs


def run_is_crushed(seg_list: list[Segment], run: Sequence[tuple[int, int]]) -> bool:
    """True when some block of `run` carries on the one before it."""
    contents = [block_content_lines(seg_list, *block) for block in run]
    return any(
        block_continues(previous, following)
        for previous, following in pairwise(contents)
    )


# ---- the body as its own witness ---------------------------------------------

# Counted per line to follow a display block whose `$$` stand on own lines.
_DISPLAY_MATH_DELIMITER_RE = re.compile(r"(?<!\\)\$\$")

# The same run that `source_text.tokenize` reads a token from.
WORD_RUN_RE = re.compile(r"\w+")


def prose_reading(seg_list: list[Segment]) -> list[str | None]:
    """The prose of each line, None where it carries none.

    Protected zones, page marks, and formulas read as nothing. Masks blank
    characters in place, so an offset in the reading addresses the original
    line. A line with an odd count of `$$` opens or closes a multi-line
    display block, and the block reads as nothing up to its partner.
    """
    prose: list[str | None] = []
    in_display = False
    for line, protected in seg_list:
        toggles = not protected and _toggles_display_math(line)
        prose.append(None if in_display or toggles else _line_prose(line, protected))
        if toggles:
            in_display = not in_display
    return prose


def display_block_lines(seg_list: list[Segment]) -> list[bool]:
    """True for each line of a display formula written over lines of its own.

    Both delimiter lines count, and both must stand in one paragraph. This is
    narrower than `prose_reading`: an unpaired `$$` is common in raw output,
    and parity alone would mark the rest of the document as math.
    """
    inside = [False] * len(seg_list)
    opener: int | None = None
    for idx, (line, protected) in enumerate(seg_list):
        if protected or not line.strip():
            opener = None
            continue
        if not _toggles_display_math(line):
            continue
        if opener is None:
            opener = idx
            continue
        for k in range(opener, idx + 1):
            inside[k] = True
        opener = None
    return inside


def body_word_counts(prose: Sequence[str | None]) -> Counter[str]:
    """How often the body spells each word, case-folded, over `prose_reading`.

    A rule that rewrites case-sensitively checks its candidate separately.
    """
    return Counter(
        word.casefold()
        for text in prose
        if text is not None
        for word in WORD_RUN_RE.findall(text)
    )


def _line_prose(line: str, protected: bool) -> str | None:
    """The prose of one line outside a display block, or None."""
    if protected:
        return None
    if page_mark_number(line) is not None:
        return None
    return mask_math(mask_addresses(line))


def _toggles_display_math(line: str) -> bool:
    """True when `line` holds an odd count of `$$` outside inline code.

    Only the `$` dialect is followed across lines: a lone `\\[` is
    indistinguishable from an escaped bracket.
    """
    delimiters = _DISPLAY_MATH_DELIMITER_RE.findall(mask_inline_code(line))
    return len(delimiters) % 2 == 1
