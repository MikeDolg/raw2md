"""Heading analysis of the quality evaluator: jumps, ladders, lost chapters.

The ladder checks read ATX headings only, so they agree on which lines are
headings. The lost-chapter check also reads setext titles: it asks whether
the body names a section at all, not where it stands.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from raw2md.cleaning import apply_outline_levels, printed_outline
from raw2md.keywords import Keywords
from raw2md.mdtext.lines import is_setext_underline
from raw2md.mdtext.zones import Segment
from raw2md.source_outline import SourceOutline
from raw2md.source_text import tokenize

# The contents ladder counts from its shallowest rank, the document's top one.
_CHAPTER_RANK = 1

# `_HEADING_NOSPACE_RE` catches a marker glued to its text.
HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:\s|$)")
_HEADING_NOSPACE_RE = re.compile(r"^ {0,3}#{1,6}(?=[^#\s])")

# Longer, a title is a paragraph tagged as a heading; the ladder check skips it.
_HEADING_TITLE_MAX_LENGTH = 200

# Strictly formed and upper case. A word of roman letters (`MIX`) still
# passes; the group bars below absorb it.
_ROMAN_NUMERAL = (
    r"(?=[IVXLCDM])M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
)

# A title opening a numbered series (`LECTURE 6`, `Chapter II`); the prefix
# starts with a letter. The number may not run on into a letter (`Model 100A`)
# or a further digit group (`Chapter 1.2`, `Part 1 000`).
_HEADING_SERIES_RE = re.compile(
    rf"^([^\W\d_][^\d]*?)[ \t]+(\d+|{_ROMAN_NUMERAL})(?![^\W_]|[.,\s]\d)"
)

# The section sign as the whole series name (`§ 12. Basics`).
_SECTION_SERIES_RE = re.compile(r"^(§)[ \t]*(\d+)(?![^\W_]|[.,\s]\d)")

# A rank word before a number (`Chapter 1`) may stand on one side only; the
# lost-chapter check drops it before comparing.
_RANK_WORD_TOKEN_RE = re.compile(r"^[^\W\d_]+$")
_NUMBER_TOKEN_RE = re.compile(rf"^(?:\d+|{_ROMAN_NUMERAL})$", re.IGNORECASE)

# A page number fused onto the last word of a contents title by a lost grid.
_GLUED_PAGE_RE = re.compile(r"^([^\W\d_]+)\d+$")

# Members and distinct numbers that prove a series. Short of them, exact
# repeats of one title count. A dotted numbering depth meets the same bars.
_LADDER_SERIES_MIN_SIZE = 3
_LADDER_SERIES_MIN_NUMBERS = 2
_LADDER_REPEAT_MIN_SIZE = 2

# A section number opening a title; its component count is the rank. A part
# code (`2-248`) or a suffix is not one. Read as cleaning reads it.
_TITLE_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)(?=\.?(?:\s|$))")

# `3.1` states a hierarchy; `1`, `2`, `3` state only peers.
_NUMBERING_MIN_DEPTH = 2

# Share of headings on one level, strictly past, for a flattened ladder; the
# observed loss puts 7 of 9 there.
_FLAT_LADDER_MIN_SHARE = Fraction(2, 3)

# Fewer headings have no ladder to lose.
_FLAT_LADDER_MIN_HEADINGS = 3

# Deeper numbering shares this level, as in the cleaner.
_MAX_HEADING_LEVEL = 6


def count_heading_issues(structural: list[Segment]) -> int:
    """Count headings with a missing space or a level jump greater than one."""
    issues = 0
    prev_level = 0
    for line, protected in structural:
        if protected:
            continue
        if _HEADING_NOSPACE_RE.match(line):
            issues += 1
            continue
        m = HEADING_RE.match(line)
        if m is None:
            continue
        level = len(m.group(1))
        if prev_level and level - prev_level > 1:
            issues += 1
        prev_level = level
    return issues


@dataclass(frozen=True)
class _LadderHeading:
    """One ATX heading as the ladder checks read it.

    `position` is the index in the segment list. `series` is the folded series
    name (`lecture` of `LECTURE 6`) and `number` its number; both empty when
    absent. `dotted` is an opening section number with a dot (`4.2.1`), else
    empty.
    """

    position: int
    level: int
    title: str
    series: str
    number: str
    dotted: str


def _ladder_headings(structural: list[Segment]) -> list[_LadderHeading]:
    """Every heading the two ladder checks read, in the body's own order.

    ATX only, like the jump check, so the checks agree on which lines are
    headings.
    """
    headings: list[_LadderHeading] = []
    for position, (line, protected) in enumerate(structural):
        if protected:
            continue
        m = HEADING_RE.match(line)
        if m is None:
            continue
        title = line[m.end() :].strip()
        if not title or len(title) > _HEADING_TITLE_MAX_LENGTH:
            continue
        series = _heading_series(title)
        headings.append(
            _LadderHeading(
                position,
                len(m.group(1)),
                title,
                series[0] if series else "",
                series[1] if series else "",
                _dotted_number(title),
            )
        )
    return headings


def _dotted_number(title: str) -> str:
    """The dotted section number a title opens with (`4.2.1`), or an empty string.

    A bare number (`3`) states only peers.
    """
    m = _TITLE_NUMBER_RE.match(title)
    if m is None or m.group(1).count(".") + 1 < _NUMBERING_MIN_DEPTH:
        return ""
    return m.group(1)


def _heading_series(title: str) -> tuple[str, str] | None:
    """A `LECTURE 6`-shaped title's series name and its number, or None.

    The name is folded and its spacing collapsed, so capitals or a doubled
    space do not split a series.
    """
    m = _SECTION_SERIES_RE.match(title) or _HEADING_SERIES_RE.match(title)
    if m is None:
        return None
    return " ".join(m.group(1).split()).casefold(), m.group(2)


def _ladder_vote_groups(members: list[_LadderHeading]) -> list[list[_LadderHeading]]:
    """The groups of one series name whose level the members settle between them.

    A series past the bars is one group; short of them, only exact repeats of
    one title group.
    """
    if (
        len(members) >= _LADDER_SERIES_MIN_SIZE
        and len({member.number for member in members}) >= _LADDER_SERIES_MIN_NUMBERS
    ):
        return [members]
    by_title: dict[str, list[_LadderHeading]] = {}
    for member in members:
        by_title.setdefault(member.title, []).append(member)
    return [
        group for group in by_title.values() if len(group) >= _LADDER_REPEAT_MIN_SIZE
    ]


def count_ladder_issues(structural: list[Segment]) -> int:
    """Headings standing off the level their own group settled on.

    A converter guessing typography page by page scatters one chain of
    sections over several levels without a jump. Groups: repeats of a title, a
    numbered series (`§ 12`, `CHAPTER II`), and one depth of dotted numbering.
    A group belongs at its most common level (a tie takes the shallower); each
    member elsewhere counts once.
    """
    groups: dict[tuple[bool, str], list[_LadderHeading]] = {}
    chains: dict[int, list[_LadderHeading]] = {}
    for heading in _ladder_headings(structural):
        # The flag keeps a title from matching a folded series name.
        key = (True, heading.series) if heading.series else (False, heading.title)
        groups.setdefault(key, []).append(heading)
        if heading.dotted:
            chains.setdefault(heading.dotted.count("."), []).append(heading)

    off: set[int] = set()
    for members in groups.values():
        for group in _ladder_vote_groups(members):
            off.update(_members_off_level(group))
    for members in chains.values():
        if (
            len(members) >= _LADDER_SERIES_MIN_SIZE
            and len({member.dotted for member in members}) >= _LADDER_SERIES_MIN_NUMBERS
        ):
            off.update(_members_off_level(members))
    return len(off)


def _members_off_level(group: Sequence[_LadderHeading]) -> list[int]:
    """Positions of the members off the group's most common level (a tie: shallower)."""
    counts = Counter(member.level for member in group)
    most = max(counts.values())
    mode = min(level for level, count in counts.items() if count == most)
    return [member.position for member in group if member.level != mode]


def count_flat_ladder(
    structural: list[Segment],
    source_outline: SourceOutline | None,
    keywords: Keywords,
) -> int:
    """Headings the crowded level swallowed, where the document states a rank.

    A hierarchy crushed flat has no jumps and no group off its level. A flat
    ladder alone is fine, so a witness (`_stated_ranks`) must state several
    ranks on the crowded level. Headings off the level's most common rank count
    (a tie: shallower); taking the shallowest would count a whole correct rank
    when one heading above was demoted.
    """
    headings = _ladder_headings(structural)
    if len(headings) < _FLAT_LADDER_MIN_HEADINGS:
        return 0
    counts = Counter(heading.level for heading in headings)
    most = max(counts.values())
    if most <= len(headings) * _FLAT_LADDER_MIN_SHARE:
        return 0
    # A tie is impossible past two thirds; the tie-break is kept for symmetry.
    crowded = min(level for level, count in counts.items() if count == most)
    ranks = _stated_ranks(headings, structural, source_outline, keywords)
    stated = Counter(
        ranks[heading.position]
        for heading in headings
        if heading.level == crowded and heading.position in ranks
    )
    if not stated:
        return 0
    held = max(stated.values())
    own = min(rank for rank, count in stated.items() if count == held)
    return sum(count for rank, count in stated.items() if rank != own)


def count_lost_chapters(
    structural: list[Segment], keywords: Keywords
) -> tuple[int, int]:
    """Chapters the body's printed contents states, and how many it never writes.

    A lost chapter opening leaves no mark on the levels that remain. The
    witness is the printed contents, required; the source outline is not used:
    it lists front matter and indexes the body never writes as headings. A
    top-rank record is written when some heading carries its title, compared
    by tokens (`_chapter_is_written`). Returns `(stated, unwritten)`.
    """
    contents = printed_outline(structural, keywords)
    if not contents.has_outline:
        return 0, 0
    chapters = contents.tokens_at(_CHAPTER_RANK)
    if not chapters:
        return 0, 0
    written = _written_chapters(structural)
    found = sum(1 for chapter in chapters if _chapter_is_written(chapter, written))
    return len(chapters), len(chapters) - found


@dataclass(frozen=True)
class _WrittenChapters:
    """The titles the body writes, in the forms a contents entry meets them in.

    `past_rank_word` holds only headings that had a rank word, without it.
    """

    as_written: frozenset[tuple[str, ...]]
    past_rank_word: frozenset[tuple[str, ...]]


def _written_chapters(structural: list[Segment]) -> _WrittenChapters:
    """Every title the body writes as a heading, in both forms of the match."""
    titles = [tuple(tokenize(title)) for title in _body_heading_titles(structural)]
    titles.extend(_two_line_chapter_titles(structural))
    unranked = [_without_rank_word(tokens) for tokens in titles]
    return _WrittenChapters(
        as_written=frozenset(titles),
        past_rank_word=frozenset(
            short for short, full in zip(unranked, titles, strict=True) if short != full
        ),
    )


def _two_line_chapter_titles(structural: list[Segment]) -> list[tuple[str, ...]]:
    """A chapter title the source printed across two lines, read as one.

    A heading of exactly a rank word and a number, followed after blank lines
    only by the next heading, is joined with it. The rank word is read by form,
    not by a list: documents come in any language.
    """
    headings = _ladder_headings(structural)
    joined: list[tuple[str, ...]] = []
    for opener, closer in pairwise(headings):
        opener_tokens = tuple(tokenize(opener.title))
        if len(opener_tokens) != 2:
            continue
        if not (
            _RANK_WORD_TOKEN_RE.match(opener_tokens[0])
            and _NUMBER_TOKEN_RE.match(opener_tokens[1])
        ):
            continue
        between = structural[opener.position + 1 : closer.position]
        if any(line.strip() for line, _ in between):
            continue
        closer_tokens = tuple(tokenize(closer.title))
        if closer_tokens:
            joined.append(opener_tokens + closer_tokens)
    return joined


def _chapter_is_written(entry: tuple[str, ...], written: _WrittenChapters) -> bool:
    """Whether some heading of the body names the chapter `entry` states.

    A rank word is read past on one side at a time: on both, `Drive 1 Data`
    and `Valve 1 Data` would both match one heading. A glued page is read past
    on the entry only.
    """
    forms = (entry, _without_glued_page(entry))
    if any(form in written.as_written for form in forms):
        return True
    if any(_without_rank_word(form) in written.as_written for form in forms):
        return True
    return any(form in written.past_rank_word for form in forms)


def _without_rank_word(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """`tokens`, without a leading rank word standing right before its number.

    The number stays: it tells apart chapters with the same name.
    """
    if (
        len(tokens) >= 2
        and _RANK_WORD_TOKEN_RE.match(tokens[0])
        and _NUMBER_TOKEN_RE.match(tokens[1])
    ):
        return tokens[1:]
    return tokens


def _without_glued_page(tokens: tuple[str, ...]) -> tuple[str, ...]:
    """`tokens`, with a page number fused onto the last word split back off.

    The shape may be a designation (`ISO9001`), so only the entry side is
    split.
    """
    if not tokens:
        return tokens
    match = _GLUED_PAGE_RE.match(tokens[-1])
    if match is None:
        return tokens
    return (*tokens[:-1], match.group(1))


def _body_heading_titles(structural: list[Segment]) -> list[str]:
    """Every title the body writes as a heading, underlined as well as marked.

    Unlike the ladder checks, setext counts: the question is whether the body
    names the section at all.
    """
    titles = [heading.title for heading in _ladder_headings(structural)]
    previous = ""
    for line, protected in structural:
        if protected:
            previous = ""
            continue
        if is_setext_underline(line.strip(), previous):
            title = previous.strip()
            if len(title) <= _HEADING_TITLE_MAX_LENGTH:
                titles.append(title)
        previous = line
    return titles


def _stated_ranks(
    headings: list[_LadderHeading],
    structural: list[Segment],
    source_outline: SourceOutline | None,
    keywords: Keywords,
) -> dict[int, int]:
    """The rank the document states for a heading itself, by segment position.

    One witness, never a merge, since each has its own scale: the source
    outline, else the printed contents, else the title's own dotted number.
    The choice matches the cleaner's. Ranks past markdown's six levels merge,
    as in the result.
    """
    if source_outline is not None and source_outline.has_outline:
        return _witness_ranks(headings, structural, source_outline)
    contents = printed_outline(structural, keywords)
    if contents.has_outline:
        return _witness_ranks(headings, structural, contents)
    return _numbering_ranks(headings)


def _witness_ranks(
    headings: list[_LadderHeading], structural: list[Segment], witness: SourceOutline
) -> dict[int, int]:
    """The rank an outline witness states, by segment position.

    Taken from the cleaner's own pass (`apply_outline_levels`), not read a
    second way. A title the witness does not name is left out.
    """
    levelled, stated = apply_outline_levels(structural, witness)
    ranks: dict[int, int] = {}
    for heading in headings:
        if heading.position not in stated:
            continue
        m = HEADING_RE.match(levelled[heading.position][0])
        if m is not None:
            ranks[heading.position] = len(m.group(1))
    return ranks


def _numbering_ranks(headings: list[_LadderHeading]) -> dict[int, int]:
    """The rank each numbered title states in its own number, by position.

    Empty when no number is dotted. Depths map to levels as the cleaner maps
    them: the shallowest is lifted as high as the depth run allows, and depths
    past level 6 share it.
    """
    depths: dict[int, int] = {}
    for heading in headings:
        m = _TITLE_NUMBER_RE.match(heading.title)
        if m is not None:
            depths[heading.position] = m.group(1).count(".") + 1
    if max(depths.values(), default=0) < _NUMBERING_MIN_DEPTH:
        return {}
    top = min(depths.values())
    base = max(1, _MAX_HEADING_LEVEL - (max(depths.values()) - top))
    return {
        position: min(_MAX_HEADING_LEVEL, base + depth - top)
        for position, depth in depths.items()
    }
