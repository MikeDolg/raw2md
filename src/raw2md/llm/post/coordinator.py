"""The post pass over one body: the routes in their order, and the tally.

A refusal costs its own zone and the pass goes on; a spent budget or a refused
access stops the sending, and the zones after it count as lost. Only a pass
that delivered nothing raises.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from raw2md.keywords import Keywords, default_keywords
from raw2md.llm.base import ProviderError, run_answers_for, stops_sending
from raw2md.llm.post.blocks import (
    BodyWords,
    broken_formula,
    context_after,
    context_before,
    crushed_runs,
    process_zone,
    swallowed_prose,
    zone_what,
)
from raw2md.llm.post.common import PostOperation, ZoneOutcome, block_end
from raw2md.llm.post.ladder import (
    LADDER_ZONE_NAME,
    LadderOutcome,
    heading_outline,
    ladder_needs_repair,
    process_heading_zone,
    stated_ranks,
)
from raw2md.llm.post.spacing import (
    SPACED_ZONE_NAME,
    SpacingOutcome,
    process_spacing_zone,
    spaced_runs,
)
from raw2md.llm.post.tables import (
    TABLE_ZONE_NAME,
    TableZone,
    process_table_zone,
    table_zone,
)
from raw2md.llm.trace import LlmTrace
from raw2md.mdtext.zones import Segment, segments


@dataclass(frozen=True)
class PostResult:
    """Outcome of a post-processing pass over one file.

    `repaired` and `reverted` count zones. `unchanged` is the part of
    `reverted` whose last attempt echoed the zone. The row, heading, and run
    counters say how much of a list reply landed; `vetoed_headings` are level
    edits the ladder itself dropped, and a run left out of a reply counts as
    neither. `joins` and `refused_joins` count hyphenation joins. `lost`
    crosses the zone counts: a zone sent in parts can be repaired and lost.
    `failure` is the refusal the run answers for.
    """

    body: str
    repaired: int
    reverted: int
    unchanged: int = 0
    joins: int = 0
    refused_joins: int = 0
    repaired_rows: int = 0
    refused_rows: int = 0
    repaired_headings: int = 0
    refused_headings: int = 0
    vetoed_headings: int = 0
    repaired_runs: int = 0
    refused_runs: int = 0
    planned: int = 0
    lost: int = 0
    failure: ProviderError | None = None


@dataclass
class _Tally:
    """What the pass planned, what came back, and whether it still sends.

    `lost` counts zones refused or left unsent. `judged` is the first refusal
    the run answers for, `first` the first of any kind. A spent budget or a
    refused access stops `sending`, and the zones after it count as lost. A
    zone neither repaired nor refused is `reverted`.
    """

    planned: int = 0
    lost: int = 0
    judged: ProviderError | None = None
    first: ProviderError | None = None
    sending: bool = True
    repaired: int = 0
    reverted: int = 0
    unchanged: int = 0
    joins: int = 0
    refused_joins: int = 0
    repaired_rows: int = 0
    refused_rows: int = 0

    def open_zone(self) -> int:
        self.planned += 1
        return self.planned

    def skip_zone(self) -> None:
        self.planned += 1
        self.lost += 1

    def settle(
        self, *, accepted: bool, unchanged: bool, failure: ProviderError | None
    ) -> None:
        """Count one sent zone; a zone sent in parts can be refused and repaired."""
        if failure is not None:
            self._refused(failure)
        if accepted:
            self.repaired += 1
        elif failure is None:
            self.reverted += 1
            if unchanged:
                self.unchanged += 1

    def settle_zone(self, outcome: ZoneOutcome) -> None:
        self.settle(
            accepted=outcome.accepted,
            unchanged=outcome.unchanged,
            failure=outcome.failure,
        )
        self.joins += outcome.joins
        self.refused_joins += outcome.refused_joins
        self.repaired_rows += outcome.repaired_rows
        self.refused_rows += outcome.refused_rows

    def _refused(self, failure: ProviderError) -> None:
        self.lost += 1
        if self.first is None:
            self.first = failure
        if self.judged is None and run_answers_for(failure):
            self.judged = failure
        if stops_sending(failure):
            self.sending = False

    def failed_outright(self) -> ProviderError | None:
        """The refusal to raise when the stage delivered nothing at all.

        A zone sent in parts can be both lost and repaired, so `repaired`
        counts too. The refusal the run answers for leads.
        """
        if self.repaired or not self.planned or self.lost < self.planned:
            return None
        return self.judged or self.first


def post_process(
    body: str,
    op: PostOperation,
    trace: LlmTrace | None = None,
    keywords: Keywords | None = None,
) -> PostResult:
    """Repair the damaged zones of `body` and return the rebuilt markdown.

    Order: the heading ladder first, since a level change touches nothing the
    block route reads; then each damaged block or table in body order; the
    letter-spaced runs last, read off the rebuilt body so no two routes answer
    for one line. `keywords` is the run's vocabulary, shared with cleaning.
    """
    vocabulary = default_keywords() if keywords is None else keywords
    tally = _Tally()
    seg_list, ladder = _repair_ladder(segments(body), op, tally, vocabulary, trace)
    blocks = _repair_blocks(seg_list, op, tally, vocabulary, trace)
    # Read off the rebuilt body: a repaired zone may have moved a run's line.
    out_segments = segments("\n".join(blocks))
    spacing = _repair_spacing(out_segments, op, tally, trace)
    outright = tally.failed_outright()
    if outright is not None:
        raise outright
    rebuilt = "\n".join(
        spacing.lines.get(position, line)
        for position, (line, _) in enumerate(out_segments)
    )
    return PostResult(
        body=f"{rebuilt}\n" if rebuilt else "",
        repaired=tally.repaired,
        reverted=tally.reverted,
        unchanged=tally.unchanged,
        joins=tally.joins,
        refused_joins=tally.refused_joins,
        repaired_rows=tally.repaired_rows,
        refused_rows=tally.refused_rows,
        repaired_headings=ladder.accepted,
        refused_headings=ladder.refused,
        vetoed_headings=ladder.vetoed,
        repaired_runs=spacing.accepted,
        refused_runs=spacing.refused,
        planned=tally.planned,
        lost=tally.lost,
        failure=tally.judged,
    )


def _repair_ladder(
    seg_list: list[Segment],
    op: PostOperation,
    tally: _Tally,
    vocabulary: Keywords,
    trace: LlmTrace | None,
) -> tuple[list[Segment], LadderOutcome]:
    """The body with the repaired heading levels folded in, and the outcome."""
    outline = heading_outline(seg_list)
    if not ladder_needs_repair(outline):
        return seg_list, LadderOutcome({}, 0, 0, 0, False)
    number = tally.open_zone()
    ladder = process_heading_zone(
        outline,
        stated_ranks(outline, seg_list, vocabulary),
        op,
        trace=trace,
        what=f"zone {number} ({LADDER_ZONE_NAME})",
    )
    tally.settle(
        accepted=bool(ladder.lines),
        unchanged=ladder.unchanged,
        failure=ladder.failure,
    )
    if ladder.lines:
        seg_list = [
            (ladder.lines.get(position, line), protected)
            for position, (line, protected) in enumerate(seg_list)
        ]
    return seg_list, ladder


@dataclass(frozen=True)
class _BlockZone:
    """A damaged block, `lines` from `start` to `end`, by the repair it needs."""

    start: int
    end: int
    lines: list[str]
    crushed: bool
    swallowed: bool
    markup: bool


def _body_zones(
    seg_list: list[Segment], crushed_ends: dict[int, int]
) -> Iterator[list[str] | TableZone | _BlockZone]:
    """The body in order: plain lines as they are, and the zones to repair."""
    index = 0
    while index < len(seg_list):
        line, protected = seg_list[index]
        if protected or not line.strip():
            yield [line]
            index += 1
            continue
        table = table_zone(seg_list, index)
        if table is not None and table.repairable:
            yield table
            index = table.end
            continue
        crushed = index in crushed_ends
        end = crushed_ends[index] if crushed else block_end(seg_list, index)
        block = [seg_list[k][0] for k in range(index, end)]
        # A zone keeps the repair that opened it, since the routes' checks
        # refuse each other's edits; a table has its own route.
        swallowed = not crushed and table is None and swallowed_prose(block)
        markup = (
            not crushed and not swallowed and table is None and broken_formula(block)
        )
        if crushed or swallowed or markup:
            yield _BlockZone(index, end, block, crushed, swallowed, markup)
        else:
            yield block
        index = end


def _repair_blocks(
    seg_list: list[Segment],
    op: PostOperation,
    tally: _Tally,
    vocabulary: Keywords,
    trace: LlmTrace | None,
) -> list[str]:
    """The body lines with each damaged block and table repaired in body order."""
    words = BodyWords(seg_list)
    out_lines: list[str] = []
    for zone in _body_zones(seg_list, crushed_runs(seg_list, vocabulary)):
        if isinstance(zone, list):
            out_lines.extend(zone)
            continue
        if not tally.sending:
            tally.skip_zone()
            out_lines.extend(zone.lines)
            continue
        number = tally.open_zone()
        if isinstance(zone, TableZone):
            outcome = process_table_zone(
                zone, op, trace=trace, what=f"zone {number} ({TABLE_ZONE_NAME})"
            )
        else:
            what = zone_what(zone.crushed, zone.swallowed, zone.markup)
            outcome = process_zone(
                zone.lines,
                op,
                words,
                swallowed_math=zone.swallowed,
                broken_markup=zone.markup,
                context_before=context_before(seg_list, zone.start),
                context_after=context_after(seg_list, zone.end),
                trace=trace,
                what=f"zone {number} ({what})",
            )
        out_lines.extend(outcome.lines)
        tally.settle_zone(outcome)
    return out_lines


def _repair_spacing(
    out_segments: list[Segment],
    op: PostOperation,
    tally: _Tally,
    trace: LlmTrace | None,
) -> SpacingOutcome:
    spaced = spaced_runs(out_segments)
    if not spaced:
        return SpacingOutcome({}, 0, 0, False)
    if not tally.sending:
        tally.skip_zone()
        return SpacingOutcome({}, 0, 0, False)
    number = tally.open_zone()
    spacing = process_spacing_zone(
        spaced, op, trace=trace, what=f"zone {number} ({SPACED_ZONE_NAME})"
    )
    tally.settle(
        accepted=bool(spacing.lines),
        unchanged=spacing.unchanged,
        failure=spacing.failure,
    )
    return spacing
