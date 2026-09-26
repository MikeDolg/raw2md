"""Ladder route: the whole heading outline, sent as a level list.

Opened only when the outline itself states its levels are wrong. Each entry is
checked alone, then the ladder judges the entries whole against what the
document states about its own ranks.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from raw2md.cleaning.headings import (
    apply_outline_levels,
    heading_class,
    is_single_letter_roman,
    printed_outline,
)
from raw2md.keywords import Keywords
from raw2md.llm.base import Part, ProviderError, TextPart
from raw2md.llm.post.common import (
    JSON_FENCE_RE,
    REPLY_REASON_LIMIT,
    TRACE_OP,
    PostOperation,
    log_unparsed_reply,
    reply_number,
    retry_note,
    schema_reply,
)
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.lines import is_setext_underline
from raw2md.mdtext.zones import Segment

LADDER_ZONE_NAME = "heading-ladder"

# A marker glued to its text is the cleaner's repair, not a level to move.
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:\s|$)")

_MAX_HEADING_LEVEL = 6

# A converter scatters a chain of sections over three or four levels, so a
# repair moves a heading a rank or two; further is no longer read off the
# outline.
_MAX_LEVEL_SHIFT = 2

# Restates the reply shape, and twice that only changed levels are named: an
# outline read back grows with the document and gets cut off.
_LADDER_ZONE_LABEL = (
    "Heading ladder to repair. Every heading of this document stands below "
    'behind its own index as "N: ", written exactly as the body writes it, so '
    "the hashes say which level it sits at now, and the list is the whole "
    "outline in the document's own order. Give each heading the level its "
    "rank in that outline asks for: a section one step under the section that "
    "holds it, headings of one rank at one level, and no level skipped on the "
    "way down. A number standing in a title says that rank outright: 11.1 "
    "belongs one level under 11, and 11.1.2 one level under 11.1. "
    'Reply with the JSON level list -- {"headings": [{"heading": N, '
    '"level": L, "title": "<the title as it stands>"}]} -- naming only the '
    "headings whose level changes. Copy each title back exactly as it stands: "
    "a heading's text is never yours to change, and the title is what says "
    "the index you named is the heading you meant. A heading underlined with "
    "=== or --- instead of hashes holds its level that way; it is shown so "
    "you can read the ladder it belongs to, and its own level is not open to "
    "repair, so name it in no entry. A heading that keeps the level the body "
    "writes it at is named in no entry either: the list is what changes, not "
    "the outline read back. Do not reply with Markdown.\n"
)

# The title is required: it is what the named index is checked against.
_LEVELS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "headings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "integer"},
                    "level": {"type": "integer"},
                    "title": {"type": "string"},
                },
                "required": ["heading", "level", "title"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["headings"],
}

_LADDER_REPLY_REASON = "the reply was not the JSON level list this zone asks for"
_LADDER_NO_EDIT_REASON = (
    "the reply named no heading whose level differs from the level it was given"
)
_LADDER_SKIP_REASON = (
    "the outline that level leaves skips more levels than the one it was "
    "given; a level puts a heading at the rank it holds, it does not open a "
    "gap in the ladder"
)
_LADDER_CONFLICT_REASON = (
    "the outline that level leaves puts more titles at two levels at once than "
    "the one it was given; one title standing at two levels is the document "
    "contradicting itself about a section, which is what this ladder is sent "
    "to have settled"
)
_LADDER_FLATTEN_REASON = (
    "the outline that level leaves stands on fewer levels than the one it was "
    "given; a rank this document holds cannot be emptied out, since the "
    "sections at it are still one step under the sections that hold them"
)
_LADDER_CROWD_REASON = (
    "that level gathers more of the outline onto its most crowded level than "
    "the outline it was given carries there; a ladder is repaired by moving a "
    "section to the rank it holds, not by merging two ranks into one"
)

# A witnessed move may change a rank's population: where most of an outline
# stands at the rank the rest belongs to, every correct move reads as a merge
# (32 of one reply's 38 vetoes). The two shapes that open the zone stay.
_WITNESSED_REASONS = frozenset({_LADDER_FLATTEN_REASON, _LADDER_CROWD_REASON})

# A dotted-decimal section number (`4.1.3 Method`); its depth names the rank.
# A bare single number opens a list item or prose as often as a section.
_TITLE_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)+(?=\.?(?:\s|$))")

# Three cannot carry the share below against a single dissenter.
_SERIES_MIN_SIZE = 4

# A numbered chain carries well past two thirds even where a converter
# scattered part of it; the cleaning stage weighs headings by the same share.
_SERIES_MAJORITY = Fraction(2, 3)

# One number repeated is a running title, not a chain of sections.
_SERIES_MIN_NUMBERS = 2


@dataclass(frozen=True)
class _Heading:
    """One heading of the outline, as the ladder route reads it.

    `title` has its spacing collapsed for the reply's cross-check. `underline`
    is set for a setext heading, whose level is shown but not open to repair.
    """

    position: int
    level: int
    title: str
    line: str
    underline: str | None


def heading_outline(seg_list: list[Segment]) -> list[_Heading]:
    """Every heading of the body, in the order it stands there.

    A heading with no title is left out: the reply's index is checked by
    title. A setext heading is read, or its rank would read as a missing rung.
    """
    outline: list[_Heading] = []
    previous = ""
    for position, (line, protected) in enumerate(seg_list):
        if protected:
            previous = ""
            continue
        core = line.strip()
        match = _HEADING_RE.match(line)
        if match is not None:
            title = _collapsed(line[match.end() :])
            if title:
                outline.append(
                    _Heading(position, len(match.group(1)), title, line, None)
                )
        elif is_setext_underline(core, previous):
            outline.append(
                _Heading(
                    position - 1,
                    1 if core.startswith("=") else 2,
                    _collapsed(previous),
                    previous,
                    core,
                )
            )
        previous = line
    return outline


def _collapsed(title: str) -> str:
    """`title` with its ends trimmed and its inner spacing collapsed to a space."""
    return " ".join(title.split())


def _title_agrees(reply: str, title: str) -> bool:
    """Whether a reply's `title` names the heading carrying `title`.

    A model copying a title back copies the marker the request showed, and the
    marker is the level, not the text. One marker is dropped, from the reply
    only: a title may itself open with a hash.
    """
    collapsed = _collapsed(reply)
    if collapsed == title:
        return True
    match = _HEADING_RE.match(collapsed)
    return match is not None and _collapsed(collapsed[match.end() :]) == title


def ladder_needs_repair(outline: list[_Heading]) -> bool:
    """True when the outline itself states that its own levels are wrong.

    A skipped level, or one title at two levels. Neither measures how much is
    wrong: they only say the outline is worth the one request. An outline with
    no movable heading is never sent.
    """
    if all(heading.underline is not None for heading in outline):
        return False
    if _skipped_levels([heading.level for heading in outline]):
        return True
    settled: dict[str, int] = {}
    for heading in outline:
        if settled.setdefault(heading.title, heading.level) != heading.level:
            return True
    return False


def _skipped_levels(levels: Sequence[int]) -> int:
    """How many headings stand more than one level under the one before them."""
    skipped = 0
    previous = 0
    for level in levels:
        if previous and level - previous > 1:
            skipped += 1
        previous = level
    return skipped


def stated_ranks(
    outline: list[_Heading], seg_list: list[Segment], keywords: Keywords
) -> dict[int, int]:
    """The level the document states itself for a heading, by segment position.

    A numbered series, overlaid by the printed contents as the cleaning stage
    reads it: the contents page is the stronger statement. Neither reads the
    reply, so a reply cannot cite its own move.
    """
    ranks = _series_ranks(outline)
    ranks.update(_contents_ranks(outline, seg_list, keywords))
    return ranks


def _series_ranks(outline: list[_Heading]) -> dict[int, int]:
    """The rank each numbered series of the outline names for its own members.

    A series of enough members and numbers, most of them on one level, names
    that level for all of them.
    """
    members: dict[tuple[str, str], list[_Heading]] = {}
    numbers: dict[tuple[str, str], set[str]] = {}
    for heading in outline:
        found = _series_key(heading.title)
        if found is None:
            continue
        key, number = found
        members.setdefault(key, []).append(heading)
        numbers.setdefault(key, set()).add(number)
    ranks: dict[int, int] = {}
    for key, group in members.items():
        if len(group) < _SERIES_MIN_SIZE or len(numbers[key]) < _SERIES_MIN_NUMBERS:
            continue
        if key[0] == "class" and all(
            is_single_letter_roman(number) for number in numbers[key]
        ):
            # `Type C`, `Type D`, `Type M`: grade letters read as roman numerals
            # by coincidence; the cleaning stage sets such a class aside too.
            continue
        level, held = Counter(heading.level for heading in group).most_common(1)[0]
        if held > len(group) * _SERIES_MAJORITY:
            ranks.update({heading.position: level for heading in group})
    return ranks


def _series_key(title: str) -> tuple[tuple[str, str], str] | None:
    """The series the title's numbering puts it in and its own number in it.

    A dotted-decimal number names its depth; any other numbered title belongs
    to its prefix class (`§ 12`, `LECTURE 6`), read as the cleaning stage reads
    it.
    """
    match = _TITLE_NUMBER_RE.match(title)
    if match is not None:
        return ("depth", str(match.group().count(".") + 1)), match.group()
    found = heading_class(title)
    return None if found is None else (("class", found[0]), found[1])


def _contents_ranks(
    outline: list[_Heading], seg_list: list[Segment], keywords: Keywords
) -> dict[int, int]:
    """The rank the body's own printed contents states, by segment position."""
    contents = printed_outline(seg_list, keywords)
    if not contents.has_outline:
        return {}
    levelled, stated = apply_outline_levels(seg_list, contents)
    ranks: dict[int, int] = {}
    for heading in outline:
        if heading.position not in stated:
            continue
        match = _HEADING_RE.match(levelled[heading.position][0])
        if match is not None:
            ranks[heading.position] = len(match.group(1))
    return ranks


def _ladder_request(outline: list[_Heading]) -> str:
    """The outline as the model sees it: every heading behind its own index.

    Lines go as the body writes them, markers included, so the level is stated
    one way only. Indentation is dropped: markdown ignores it.
    """
    shown: list[str] = []
    for number, heading in enumerate(outline, start=1):
        shown.append(f"{number}: {heading.line.strip()}")
        if heading.underline is not None:
            shown.append(heading.underline)
    return _LADDER_ZONE_LABEL + "\n".join(shown)


@dataclass(frozen=True)
class LadderOutcome:
    """What the outline zone came back as, for `post_process` to fold in.

    `lines` maps a segment position to the rewritten heading line.
    """

    lines: dict[int, str]
    accepted: int
    refused: int
    vetoed: int
    unchanged: bool
    failure: ProviderError | None = None


def process_heading_zone(
    outline: list[_Heading],
    witness: Mapping[int, int],
    op: PostOperation,
    *,
    trace: LlmTrace | None = None,
    what: str = "zone",
) -> LadderOutcome:
    """Repair the document's heading ladder from a level-indexed reply.

    One request and one retry, none on an echo. `witness` is what the document
    states about its own ranks.
    """
    request = TextPart(_ladder_request(outline))
    parts: list[Part] = [request]
    refused = 0
    vetoed = 0
    unchanged = False
    for attempt in (1, 2):  # the initial attempt plus one retry
        try:
            reply = schema_reply(op, parts, _LEVELS_SCHEMA)
        except ProviderError as exc:
            # A refusal loses the ladder alone.
            return LadderOutcome({}, 0, refused, vetoed, False, failure=exc)
        if trace is not None:
            trace.record(TRACE_OP, what, parts, reply.text, attempt=attempt)
        edits = _parse_level_edits(reply.text)
        if edits is None:
            log_unparsed_reply(reply, what, attempt=attempt, listing="level list")
        verdict = _relevelled(outline, edits, witness)
        refused += verdict.refused
        vetoed += verdict.vetoed
        if verdict.lines is not None:
            return LadderOutcome(
                verdict.lines, verdict.accepted, refused, vetoed, False
            )
        assert verdict.reason is not None  # every rejection branch sets one
        unchanged = verdict.unchanged
        if unchanged:
            break  # an echo is terminal: a retry note has nothing to correct
        parts = [request, TextPart(retry_note(verdict.reason))]
    return LadderOutcome({}, 0, refused, vetoed, unchanged)


def _parse_level_edits(reply: str) -> dict[int, tuple[int, str | None]] | None:
    """The level edits a reply names, or None when it is not a level list at all.

    A missing title is kept as None, so the verdict can say why it refuses.
    """
    stripped = reply.strip()
    fenced = JSON_FENCE_RE.match(stripped)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data = data.get("headings", [])
    if not isinstance(data, list):
        return None
    edits: dict[int, tuple[int, str | None]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        number = reply_number(entry.get("heading"))
        level = reply_number(entry.get("level"))
        title = entry.get("title")
        if number is not None and level is not None:
            edits[number] = (level, title if isinstance(title, str) else None)
    return edits


@dataclass(frozen=True)
class _LadderVerdict:
    """The verdict on one ladder reply: `lines` when a level was accepted.

    `refused` entries were never usable; `vetoed` ones were usable on their
    face, but the outline as a whole could not take them.
    """

    lines: dict[int, str] | None
    reason: str | None
    accepted: int = 0
    refused: int = 0
    vetoed: int = 0
    unchanged: bool = False


def _relevelled(  # noqa: C901, PLR0912, PLR0915 -- per-entry checks, then the whole-ladder verdict, in one visible order
    outline: list[_Heading],
    edits: dict[int, tuple[int, str | None]] | None,
    witness: Mapping[int, int] = MappingProxyType({}),
) -> _LadderVerdict:
    """The heading lines the accepted level edits of a reply rewrite.

    Each entry is checked alone: its index, level, and title, and a shift of
    at most `_MAX_LEVEL_SHIFT` unless `witness` states that level. The title
    is the only check on the index; no heading text is written from the reply.
    The ladder then judges the entries whole; only a reply it turns down is
    taken apart greedily, entry by entry in outline order, dropping each entry
    that regresses. A witnessed entry is kept past a population veto and joins
    the outline later entries are measured against.
    """
    if edits is None:
        return _LadderVerdict(None, _LADDER_REPLY_REASON)
    proposed: list[tuple[int, _Heading, int]] = []
    notes: list[str] = []
    refused = 0
    vetoed = 0
    for number in sorted(edits):
        level, title = edits[number]
        if not 1 <= number <= len(outline):
            notes.append(f"heading {number} is not a heading of this document")
            refused += 1
            continue
        heading = outline[number - 1]
        if title is None:
            notes.append(
                f"heading {number} came back without the title that says which "
                "heading was meant"
            )
            refused += 1
            continue
        if not _title_agrees(title, heading.title):
            notes.append(
                f"heading {number} came back under another title; its own text "
                "is not open to repair here, and the title is what says the "
                "index names the heading you meant"
            )
            refused += 1
            continue
        if heading.underline is not None:
            notes.append(
                f"heading {number} states its level with an underline rather "
                "than hashes; it is shown as the rung it holds and its own "
                "level is not open to repair here"
            )
            refused += 1
            continue
        if not 1 <= level <= _MAX_HEADING_LEVEL:
            notes.append(
                f"heading {number}: level {level} is outside the 1 to "
                f"{_MAX_HEADING_LEVEL} a heading can hold"
            )
            refused += 1
            continue
        if (
            abs(level - heading.level) > _MAX_LEVEL_SHIFT
            and witness.get(heading.position) != level
        ):
            notes.append(
                f"heading {number} moves {abs(level - heading.level)} ranks "
                f"from where the body writes it, past the {_MAX_LEVEL_SHIFT} a "
                "scattered ladder is repaired within"
            )
            refused += 1
            continue
        if level == heading.level:
            continue
        proposed.append((number, heading, level))
    # The whole reply first: a branch moved down empties its rank until the
    # entry under it moves too.
    settled = {heading.position: heading.level for heading in outline}
    for _, heading, level in proposed:
        settled[heading.position] = level
    # Witnesses count here too, or edits landing with one read as a flattening.
    proposed_witnessed = {
        heading.position: level
        for _, heading, level in proposed
        if witness.get(heading.position) == level
    }
    if proposed and _ladder_regression(outline, settled, proposed_witnessed) is None:
        lines: dict[int, str] = {
            heading.position: _at_level(heading.line, level)
            for _, heading, level in proposed
        }
        return _LadderVerdict(lines, None, accepted=len(lines), refused=refused)
    lines = {}
    settled = {heading.position: heading.level for heading in outline}
    witnessed: dict[int, int] = {}
    for number, heading, level in proposed:
        settled[heading.position] = level
        confirmed = witness.get(heading.position) == level
        with_witness = dict(witnessed)
        if confirmed:
            with_witness[heading.position] = level
        regression = _ladder_regression(outline, settled, witnessed)
        if regression is None:
            # Recorded even without a regression, so later moves see it.
            witnessed = with_witness
            lines[heading.position] = _at_level(heading.line, level)
            continue
        # A witness answers for its own move only: measured again with it
        # counted, a state still regressing was carried by earlier edits.
        if (
            confirmed
            and regression in _WITNESSED_REASONS
            and _ladder_regression(outline, settled, with_witness) is None
        ):
            witnessed = with_witness
            lines[heading.position] = _at_level(heading.line, level)
            continue
        settled[heading.position] = heading.level
        notes.append(f"heading {number}: {regression}")
        vetoed += 1
    if not lines:
        reason = (
            "; ".join(notes[:REPLY_REASON_LIMIT]) if notes else _LADDER_NO_EDIT_REASON
        )
        return _LadderVerdict(
            None, reason, refused=refused, vetoed=vetoed, unchanged=not notes
        )
    return _LadderVerdict(
        lines, None, accepted=len(lines), refused=refused, vetoed=vetoed
    )


def _ladder_regression(
    outline: list[_Heading],
    settled: Mapping[int, int],
    witnessed: Mapping[int, int] = MappingProxyType({}),
) -> str | None:
    """What the accepted levels would leave worse than they found, if anything.

    Four vetoes against the outline given, not a sum: summed, closed gaps would
    pay for a contradiction. No more skipped levels, no more titles at two
    levels, no rank emptied, no more on the widest level. The last two stop a
    flattening while letting a whole branch shift, and count `witnessed`
    levels where the document puts them.
    """
    before = [heading.level for heading in outline]
    after = [settled[heading.position] for heading in outline]
    titles = [heading.title for heading in outline]
    if _skipped_levels(after) > _skipped_levels(before):
        return _LADDER_SKIP_REASON
    if _split_titles(titles, after) > _split_titles(titles, before):
        return _LADDER_CONFLICT_REASON
    ground = [witnessed.get(heading.position, heading.level) for heading in outline]
    if len(set(after)) < len(set(ground)):
        return _LADDER_FLATTEN_REASON
    if _widest_rank(after) > _widest_rank(ground):
        return _LADDER_CROWD_REASON
    return None


def _split_titles(titles: Sequence[str], levels: Sequence[int]) -> int:
    held: dict[str, set[int]] = {}
    for title, level in zip(titles, levels, strict=True):
        held.setdefault(title, set()).add(level)
    return sum(1 for at in held.values() if len(at) > 1)


def _widest_rank(levels: Sequence[int]) -> int:
    """How many headings stand at the level that holds the most of them."""
    return max(Counter(levels).values())


def _at_level(line: str, level: int) -> str:
    """`line` with its heading marker set to `level` and nothing else touched."""
    match = _HEADING_RE.match(line)
    assert match is not None  # only ever called on a line the outline read
    return f"{line[: match.start(1)]}{'#' * level}{line[match.end(1) :]}"
