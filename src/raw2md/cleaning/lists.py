"""Rules that restore a converter's demoted or misnested list markup.

`normalize_lists` and `separate_bold_list_marker` rewrite a block of adjacent
list-item lines. `drop_stray_bullet_glyph` and `promote_dingbat_bullet` read
one line at a time. A block that could be genuine nesting stays untouched.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise

from raw2md.cleaning.segments import LIST_ITEM_RE
from raw2md.mdtext.lines import is_thematic_break
from raw2md.mdtext.tables import has_cell_separator
from raw2md.mdtext.zones import Segment

# A demoted ordered marker as bullet text. The number ends at whitespace, so
# a version string like `2.text` does not match.
_NUMBER_TEXT_RE = re.compile(r"^(\d{1,9})([.)])(?=\s|$)")

_BULLET_MARKERS = frozenset("-*+")

# A numbered marker demoted to bold (`**10.**`) and glued to the first word.
# Only at the start of the content, where a marker sits. Punctuation after it
# (`**10.**,`) is ordinary typography.
_BOLD_NUMBER_MARKER_RE = re.compile(r"^(\*\*\d{1,9}[.)]\*\*)(?=\w)")


@dataclass(frozen=True)
class _ListItem:
    """A parsed list-item line: its raw text and its marker parts."""

    raw: str
    indent: int
    marker: str
    gap: str
    content: str


def _parse_list_item(line: str) -> _ListItem | None:
    """Parse `line` as a list item, or None for a non-item or thematic break."""
    if is_thematic_break(line.strip()):
        return None
    m = LIST_ITEM_RE.match(line)
    if m is None:
        return None
    return _ListItem(
        raw=line,
        indent=len(m.group(1)),
        marker=m.group(2),
        gap=m.group(3),
        content=m.group(4),
    )


def _walk_item_blocks(
    seg_list: list[Segment], fix: Callable[[list[_ListItem]], list[str]]
) -> list[Segment]:
    """Group adjacent item lines into blocks and rewrite each with `fix`.

    A rule needs the block's base indent: a deep item is a nested child when a
    shallower item vouches for it, and indented code otherwise.
    """
    out: list[Segment] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected or _parse_list_item(line) is None:
            out.append((line, protected))
            idx += 1
            continue
        block: list[_ListItem] = []
        while idx < count and not seg_list[idx][1]:
            item = _parse_list_item(seg_list[idx][0])
            if item is None:
                break
            block.append(item)
            idx += 1
        out.extend((fixed, False) for fixed in fix(block))
    return out


def normalize_lists(seg_list: list[Segment]) -> list[Segment]:
    """Restore marker's broken lists over each block of item lines.

    marker demotes a flat numbered list to alternately indented bullets whose
    text is the number, and strays a lone bullet one level deep. Both are
    valid CommonMark, so only the block shape shows them.
    """
    return _walk_item_blocks(seg_list, _fix_list_block)


def separate_bold_list_marker(seg_list: list[Segment]) -> list[Segment]:
    """Insert the space marker drops after a numbered marker demoted to bold."""
    return _walk_item_blocks(seg_list, _separate_bold_marker_block)


def _separate_bold_marker_block(items: list[_ListItem]) -> list[str]:
    """Rewrite one list block, adding a space at each glued bold marker.

    A block whose base indent is past three spaces is indented code.
    """
    base = min(it.indent for it in items)
    if base > 3:
        return [it.raw for it in items]
    out: list[str] = []
    for it in items:
        if _BOLD_NUMBER_MARKER_RE.match(it.content) is None:
            out.append(it.raw)
            continue
        content = _BOLD_NUMBER_MARKER_RE.sub(r"\1 ", it.content, count=1)
        out.append(f"{' ' * it.indent}{it.marker}{it.gap}{content}")
    return out


# A closed set of symbol-font bullets: an open class would prune real
# trailing punctuation, since the position check is permissive.
_BULLET_GLYPHS = "❚"

_TRAILING_BULLET_GLYPH_RE = re.compile(rf"^(?P<body>.*\S)\s+[{_BULLET_GLYPHS}]$")


def drop_stray_bullet_glyph(seg_list: list[Segment]) -> list[Segment]:
    """Drop a bullet glyph a converter left on the wrong line.

    Two positions only: trailing an item that opens with its own marker, and
    alone on a line. The same glyph elsewhere is content. A line indented
    past three spaces may be indented code and stays.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, protected))
            continue
        indent = len(line) - len(line.lstrip(" "))
        core = line.strip()
        if indent <= 3 and len(core) == 1 and core in _BULLET_GLYPHS:
            continue
        item = _parse_list_item(line)
        rewritten = line
        if item is not None and item.indent <= 3:
            match = _TRAILING_BULLET_GLYPH_RE.match(item.content)
            if match is not None:
                rewritten = (
                    f"{' ' * item.indent}{item.marker}{item.gap}{match.group('body')}"
                )
        out.append((rewritten, protected))
    return out


# U+2022 at the head of a line, within three spaces of the margin. Mid-line
# the same glyph is a separator.
_DINGBAT_BULLET_RE = re.compile(r"^( {0,3})•[ \t]+(?=\S)")


def promote_dingbat_bullet(seg_list: list[Segment]) -> list[Segment]:
    """Rewrite a line opening with a literal `•` glyph as a `-` bullet item.

    marker carries a symbol-font bullet into the body as the character. A
    table row keeps the glyph as cell data. Runs before list de-nesting, so
    the promoted items form a block.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        rewritten = line
        if not protected and not has_cell_separator(line):
            rewritten = _DINGBAT_BULLET_RE.sub(r"\1- ", line, count=1)
        out.append((rewritten, protected))
    return out


def _fix_list_block(items: list[_ListItem]) -> list[str]:
    """Rewrite one list block with one of two exclusive, conservative repairs.

    Restore a demoted numbered list (`_is_demoted_numbered`), or else flatten a
    lone spurious child (`_lone_child_index`). A real sub-list of two or more
    items stays; the ordered-marker guard keeps re-cleaning a no-op.
    """
    if len(items) < 2:
        return [it.raw for it in items]
    base = min(it.indent for it in items)
    # CommonMark puts a top-level marker within three spaces of the margin.
    # Deeper is indented code, which is not a protected zone.
    if base > 3:
        return [it.raw for it in items]
    if _is_demoted_numbered(items, base):
        return _restore_numbered_block(items, base)
    flatten = _lone_child_index(items, base)
    if flatten is not None:
        return [
            f"{' ' * base}{it.marker}{it.gap}{it.content}" if k == flatten else it.raw
            for k, it in enumerate(items)
        ]
    return [it.raw for it in items]


def _deeper_runs(items: list[_ListItem], base: int) -> list[tuple[int, int]]:
    """Index spans `[start, end)` past `base` that the outer count skips.

    A stretch past `base` with two or more items at its own shallowest depth
    is a nested list, which may restart at 1. A lone item there is a zigzag
    continuation of the outer count, so only its descendants form a span.
    """
    spans: list[tuple[int, int]] = []
    idx = 0
    count = len(items)
    while idx < count:
        if items[idx].indent <= base:
            idx += 1
            continue
        start = idx
        while idx < count and items[idx].indent > base:
            idx += 1
        stretch = items[start:idx]
        inner_base = min(it.indent for it in stretch)
        siblings = sum(1 for it in stretch if it.indent == inner_base)
        if siblings >= 2:
            spans.append((start, idx))
        elif idx - start > 1:
            spans.append((start + 1, idx))
    return spans


def _is_demoted_numbered(items: list[_ListItem], base: int) -> bool:
    """True when the block is marker's demoted numbered list, not real nesting.

    At least two bullets carry a number as text, one of them at the base
    indent, and the numbers are consecutive. A gap (`2023.`, `2025.`) is bullet
    text: an ordered list would renumber it. Nested runs (`_deeper_runs`) are
    left out of the count.
    """
    skip = {k for start, end in _deeper_runs(items, base) for k in range(start, end)}
    numbers: list[int] = []
    at_base = False
    for k, it in enumerate(items):
        if k in skip or it.marker not in _BULLET_MARKERS:
            continue
        m = _NUMBER_TEXT_RE.match(it.content)
        if m is None:
            continue
        numbers.append(int(m.group(1)))
        if it.indent == base:
            at_base = True
    if len(numbers) < 2 or not at_base:
        return False
    return all(b == a + 1 for a, b in pairwise(numbers))


def _restore_numbered_block(items: list[_ListItem], base: int) -> list[str]:
    """Rewrite a confirmed demoted numbered block, recursing into deeper runs.

    A nested run is restored only if its own numbers qualify, and otherwise
    stays untouched; the flatten path and the indented-code guard do not apply
    inside a confirmed list. A restored marker changes width (`- ` to `1. `),
    so its descendants shift by the same delta to stay valid CommonMark.
    """
    items = list(items)
    spans = _deeper_runs(items, base)
    out: list[str] = []
    span_idx = 0
    idx = 0
    count = len(items)
    while idx < count:
        if span_idx < len(spans) and spans[span_idx][0] == idx:
            start, end = spans[span_idx]
            run = items[start:end]
            run_base = min(it.indent for it in run)
            if _is_demoted_numbered(run, run_base):
                out.extend(_restore_numbered_block(run, run_base))
            else:
                out.extend(it.raw for it in run)
            idx = end
            span_idx += 1
            continue
        it = items[idx]
        original_indent = it.indent
        new_line, shift = _restore_item(it, base)
        if shift:
            _shift_descendants(items, idx + 1, original_indent, shift)
        out.append(new_line)
        idx += 1
    return out


def _restore_item(it: _ListItem, base: int) -> tuple[str, int]:
    """Rewrite one item of a demoted numbered block; return its line and shift.

    A number-as-text bullet becomes an ordered marker at the base level. Any
    other item stays. `shift` is the change in prefix width.
    """
    if it.marker in _BULLET_MARKERS:
        m = _NUMBER_TEXT_RE.match(it.content)
        if m is not None:
            rest = it.content[m.end() :]
            gap_len = len(rest) - len(rest.lstrip(" "))
            old_prefix = it.indent + len(it.marker) + len(it.gap)
            new_prefix = base + len(m.group(1)) + len(m.group(2)) + gap_len
            return (
                f"{' ' * base}{m.group(1)}{m.group(2)}{rest}",
                new_prefix - old_prefix,
            )
    return it.raw, 0


def _reindent(it: _ListItem, delta: int) -> _ListItem:
    """Return `it` shifted by `delta` columns, its raw line rewritten to match."""
    new_indent = max(0, it.indent + delta)
    return _ListItem(
        raw=f"{' ' * new_indent}{it.marker}{it.gap}{it.content}",
        indent=new_indent,
        marker=it.marker,
        gap=it.gap,
        content=it.content,
    )


def _shift_descendants(
    items: list[_ListItem], start: int, parent_indent: int, delta: int
) -> None:
    """Shift in place each item from `start` deeper than `parent_indent`."""
    idx = start
    count = len(items)
    while idx < count and items[idx].indent > parent_indent:
        items[idx] = _reindent(items[idx], delta)
        idx += 1


def _lone_child_index(items: list[_ListItem], base: int) -> int | None:
    """Index of a single spurious child to flatten, or None.

    Exactly one item sits deeper than the base, after at least two base items.
    A block with an ordered marker keeps its nesting, which also keeps a
    restored list stable. A child with a number as text is a real subpoint.
    """
    if any(it.marker not in _BULLET_MARKERS for it in items):
        return None
    deeper = [k for k, it in enumerate(items) if it.indent > base]
    if len(deeper) != 1:
        return None
    child = deeper[0]
    if _NUMBER_TEXT_RE.match(items[child].content):
        return None
    flush_before = sum(1 for k in range(child) if items[k].indent == base)
    return child if flush_before >= 2 else None
