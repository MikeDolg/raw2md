"""Spacing route: every letter-spaced run of the body, sent as a run list.

All runs form one zone, split into parts only as the reply budget needs. A run
may close its own spaces and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby

from raw2md.cleaning.findings import LETTER_SPACING_FINDING
from raw2md.cleaning.prose import letter_spaced_runs, spacing_witness
from raw2md.cleaning.segments import prose_reading
from raw2md.llm.base import Part, ProviderError, TextPart
from raw2md.llm.post.common import (
    ENTRY_REPLY_OVERHEAD,
    LIST_WRAPPER_CHARS,
    MAX_CONTEXT_CHARS,
    MAX_REPLY_CHARS,
    TRACE_OP,
    PostOperation,
    log_unparsed_reply,
    parse_text_edits,
    retry_note,
    schema_reply,
)
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.zones import Segment

# All runs form one zone: a book can leave hundreds, and a request apiece
# would spend a day of free-tier quota on one document.
SPACED_ZONE_NAME = LETTER_SPACING_FINDING

# States the reply protocol: an older prompts.yaml asks for Markdown.
_SPACED_ZONE_LABEL = (
    "Letter-spacing zone to repair. A typesetter set a word here and there by "
    "spacing its letters apart, and the conversion read every letter as its "
    "own token, so each such word stands as single letters one space apart. "
    'Every run carries its own index as "N: ", and the line they stand in '
    'follows under "in: " as read-only context, once for the runs that share '
    "it. Close the spaces inside a run "
    "back into the word it spells, taking in the letter group standing at the "
    "run's own edge where the word runs on into it. Close a space and nothing "
    "else: no letter, digit, punctuation mark or markup of a run is added, "
    "dropped, replaced or reordered, and nothing outside the run itself is "
    "yours to write. Where the letters spell no word -- a list of "
    "designations, a line of symbols -- leave the run out of the reply "
    'entirely. Reply with the JSON run list -- {"runs": [{"run": N, "text": '
    '"<the run with its spaces closed>"}]} -- naming only the runs you close. '
    "Write each one back as it was shown, without its index prefix and with "
    "the letter group at its edge included, carrying only the closed spaces. "
    "Do not reply with Markdown.\n"
)

# The sentence around a run is what tells a word from a designation.
_SPACED_CONTEXT_LABEL = "in: "

_RUNS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "runs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "run": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["run", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["runs"],
}

_SPACING_REPLY_REASON = "the reply was not the JSON run list this zone asks for"
_SPACING_NO_EDIT_REASON = "the reply named no run whose spaces it closed"
_SPACING_KEPT_REASON = (
    "the reply did more than close the spaces of a letter-spaced run; a run "
    "comes back character for character except for the spaces that stood "
    "between its own letters, and no letter, digit, punctuation mark or "
    "markup of it may be changed, added or dropped"
)


@dataclass(frozen=True)
class _SpacedRun:
    """One letter-spaced run of the body, as the request shows it.

    `start` and `end` bound the run in `line`; `core` and `edge` are the spaces
    it licenses, in the same offsets.
    """

    position: int
    start: int
    end: int
    core: frozenset[int]
    edge: frozenset[int]
    line: str

    @property
    def text(self) -> str:
        return self.line[self.start : self.end]


def spaced_runs(seg_list: list[Segment]) -> list[_SpacedRun]:
    """Every letter-spaced run of the body, in the order it stands there.

    Read off each line's prose as the cleaner reads it, with the body's own
    spacing witness.
    """
    witness = spacing_witness(seg_list)
    runs: list[_SpacedRun] = []
    for position, ((line, _), prose) in enumerate(
        zip(seg_list, prose_reading(seg_list), strict=True)
    ):
        if prose is None:
            continue
        runs.extend(
            _SpacedRun(position, run.start, run.end, run.core, run.edge, line)
            for run in letter_spaced_runs(prose, witness)
        )
    return runs


def _spacing_parts(runs: list[_SpacedRun]) -> list[list[int]]:
    """The run indices split so each part's worst-case reply fits."""
    parts: list[list[int]] = []
    current: list[int] = []
    size = LIST_WRAPPER_CHARS
    for number, run in enumerate(runs, start=1):
        cost = ENTRY_REPLY_OVERHEAD + len(run.text)
        if current and size + cost > MAX_REPLY_CHARS:
            parts.append(current)
            current = []
            size = LIST_WRAPPER_CHARS
        current.append(number)
        size += cost
    if current:
        parts.append(current)
    return parts


def _spacing_request(runs: list[_SpacedRun], focus: list[int]) -> str:
    """The runs of one part as the model sees them: each behind its own index.

    The line follows its runs once as context, unless it is the run alone or
    too long: the reply budget does not bound the lines.
    """
    shown: list[str] = []
    for _, numbers in groupby(focus, key=lambda number: runs[number - 1].position):
        group = list(numbers)
        shown.extend(f"{number}: {runs[number - 1].text}" for number in group)
        context = runs[group[0] - 1].line.strip()
        if len(group) == 1 and context == runs[group[0] - 1].text:
            continue
        if len(context) <= MAX_CONTEXT_CHARS:
            shown.append(f"{_SPACED_CONTEXT_LABEL}{context}")
    return _SPACED_ZONE_LABEL + "\n".join(shown)


def _run_spelled(run: _SpacedRun, text: str) -> bool:
    """True when `text` is `run` as it stands with only its own spaces closed.

    Walked character by character, since closing a space changes every token.
    The core spaces close together or not at all; an edge space may close
    only with them.
    """
    old_text = run.text
    core = {offset - run.start for offset in run.core}
    edge = {offset - run.start for offset in run.edge}
    closed: set[int] = set()
    old_index = new_index = 0
    while old_index < len(old_text) and new_index < len(text):
        if old_text[old_index] == text[new_index]:
            old_index += 1
            new_index += 1
        elif old_text[old_index] == " " and old_index in core | edge:
            closed.add(old_index)
            old_index += 1
        else:
            return False
    if old_index != len(old_text) or new_index != len(text):
        return False
    return bool(closed & core) and core <= closed and closed <= core | edge


@dataclass(frozen=True)
class _SpacingVerdict:
    """The verdict on one run-list reply: `closed` when a run was accepted.

    `unchanged` marks a reply naming no closed run: this route's echo.
    """

    closed: dict[int, str]
    reason: str | None
    accepted: int = 0
    refused: int = 0
    unchanged: bool = False


def _respaced(
    runs: list[_SpacedRun], edits: dict[int, str] | None, focus: list[int]
) -> _SpacingVerdict:
    """The spellings a reply names that the run invariant accepts.

    A run left out, returned as it stood, or outside `focus` is no edit.
    """
    if edits is None:
        return _SpacingVerdict({}, _SPACING_REPLY_REASON)
    covered = set(focus)
    closed: dict[int, str] = {}
    refused = 0
    for number, text in sorted(edits.items()):
        if number not in covered:
            continue
        run = runs[number - 1]
        spelled = text.strip()
        if spelled == run.text:
            continue
        if not _run_spelled(run, spelled):
            refused += 1
            continue
        closed[number] = spelled
    if closed:
        return _SpacingVerdict(closed, None, len(closed), refused)
    if refused:
        return _SpacingVerdict({}, _SPACING_KEPT_REASON, refused=refused)
    return _SpacingVerdict({}, _SPACING_NO_EDIT_REASON, unchanged=True)


@dataclass(frozen=True)
class _PartRuns:
    """What one part of the spacing zone came back as, for the zone to sum up."""

    closed: dict[int, str]
    accepted: int
    refused: int
    unchanged: bool
    failure: ProviderError | None = None


def _repair_runs(
    runs: list[_SpacedRun],
    focus: list[int],
    op: PostOperation,
    *,
    trace: LlmTrace | None = None,
    what: str = "zone",
) -> _PartRuns:
    """Run one spacing request -- the whole zone, or one part of a split one."""
    request = TextPart(_spacing_request(runs, focus))
    parts: list[Part] = [request]
    refused = 0
    unchanged = False
    for attempt in (1, 2):  # the initial attempt plus one retry
        try:
            reply = schema_reply(op, parts, _RUNS_SCHEMA)
        except ProviderError as exc:
            # Runs an earlier attempt turned down were judged, not lost.
            return _PartRuns({}, 0, refused, unchanged, failure=exc)
        if trace is not None:
            trace.record(TRACE_OP, what, parts, reply.text, attempt=attempt)
        edits = parse_text_edits(reply.text, "runs", "run")
        if edits is None:
            log_unparsed_reply(reply, what, attempt=attempt, listing="run list")
        verdict = _respaced(runs, edits, focus)
        refused += verdict.refused
        if verdict.closed:
            return _PartRuns(verdict.closed, verdict.accepted, refused, False)
        assert verdict.reason is not None  # every rejection branch sets one
        unchanged = verdict.unchanged
        if unchanged:
            break  # an echo is terminal: a retry note has nothing to correct
        parts = [request, TextPart(retry_note(verdict.reason))]
    return _PartRuns({}, 0, refused, unchanged)


@dataclass(frozen=True)
class SpacingOutcome:
    """What the spacing zone came back as, for `post_process` to fold in.

    `lines` maps a segment position to the rewritten line.
    """

    lines: dict[int, str]
    accepted: int
    refused: int
    unchanged: bool
    failure: ProviderError | None = None


def process_spacing_zone(
    runs: list[_SpacedRun],
    op: PostOperation,
    *,
    trace: LlmTrace | None = None,
    what: str = "zone",
) -> SpacingOutcome:
    """Repair every letter-spaced run of the body from a run-indexed reply.

    Runs go in as many parts as their replies need and are judged one by one.
    One retry per part, none for a reply naming no closed run: leaving a run
    is the answer for designations.
    """
    parts = _spacing_parts(runs)
    closed: dict[int, str] = {}
    accepted = 0
    refused = 0
    unchanged = True
    failure: ProviderError | None = None
    for index, focus in enumerate(parts, start=1):
        label = f"{what} part {index}/{len(parts)}" if len(parts) > 1 else what
        part = _repair_runs(runs, focus, op, trace=trace, what=label)
        refused += part.refused
        if part.failure is not None:
            # The spellings earlier parts closed are kept.
            failure = part.failure
            break
        closed.update(part.closed)
        accepted += part.accepted
        if not part.unchanged:
            unchanged = False
    return SpacingOutcome(
        _respaced_lines(runs, closed), accepted, refused, unchanged, failure=failure
    )


def _respaced_lines(runs: list[_SpacedRun], closed: dict[int, str]) -> dict[int, str]:
    """The body lines the accepted spellings rewrite, by segment position.

    Folded in from the end of a line, so both runs of one line keep offsets.
    """
    lines: dict[int, str] = {}
    for number in sorted(closed, reverse=True):
        run = runs[number - 1]
        line = lines.get(run.position, run.line)
        lines[run.position] = f"{line[: run.start]}{closed[number]}{line[run.end :]}"
    return lines
