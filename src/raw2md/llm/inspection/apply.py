"""Apply the placed edits under the edit guard and rebuild the body."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from raw2md.llm.acceptance import TouchedLines
from raw2md.llm.chunking import PageIndex
from raw2md.llm.edit_guard import display_tail_fold, rejection_reason
from raw2md.llm.inspection.addressing import (
    DisplayUnit,
    Placement,
    address_label,
    address_miss,
    body_lines,
    matches_unit,
    mismatch_kind,
    place_quote,
    resolve_address,
    sample,
    strip_declared_address_prefix,
    unit_text,
    wide_drift_anchor,
)
from raw2md.llm.inspection.common import InspectResult, SemanticEdit
from raw2md.llm.inspection.masking import MaskedBody, quotes_the_mask, unmask_edit
from raw2md.mdtext.formulas import math_delimiters_only_moved
from raw2md.mdtext.links import mask_addresses
from raw2md.mdtext.math_spans import mask_math, math_spans
from raw2md.mdtext.zones import segments
from raw2md.source_text import SourceText, hyphen_forms

_logger = logging.getLogger("raw2md")


@dataclass(frozen=True)
class Coverage:
    """How much of the source a pass actually saw, on its way into the result."""

    failure: Exception | None = None
    planned: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class _Queued:
    """One edit waiting to be applied; `placed` is set for an unmasked edit only."""

    edit: SemanticEdit
    placed: Placement | None = None


def apply_edits(  # noqa: C901, PLR0912, PLR0915 -- one gate chain per edit in a fixed order, sharing the line and fragment records
    body: str,
    semantic: list[SemanticEdit],
    flags: list[str],
    index: PageIndex,
    units: dict[int, DisplayUnit],
    masked: MaskedBody | None,
    coverage: Coverage,
    source_text: SourceText | None = None,
    latex_fix: bool = False,
) -> InspectResult:
    """Resolve each edit's page address to a body line, apply, and rebuild.

    `flags` are only counted. `masked` is None when nothing was masked; an
    unmasked edit is applied after the ordinary ones, onto the line they
    produced. `coverage` passes through to the result.
    """
    lines = body_lines(body)
    protected = [p for _, p in segments(body)]
    # The body's own hyphenated spellings, read before any edit lands and from
    # prose only: in math a dash is a minus.
    body_hyphens = frozenset(
        form
        for line, is_protected in zip(lines, protected, strict=True)
        if not is_protected
        for form in hyphen_forms(mask_math(mask_addresses(line)))
    )
    replacements: dict[int, str] = {}
    # Fragment substitutions per line, in the offsets of the line as it arrived,
    # so the next fragment splices past them.
    fragments: dict[int, list[tuple[tuple[int, int], str]]] = {}
    swallowed: set[int] = set()
    applied = skipped = rejected = 0

    _log_flags(flags)

    queue, unmask_skipped, unmask_rejected = _unmask_queue(semantic, masked, index)
    skipped += unmask_skipped
    rejected += unmask_rejected

    for queued in queue:
        edit = queued.edit
        address = address_label(edit.page, edit.line)
        if edit.old == edit.new:
            # Dropped before matching, where it would take a replacement slot.
            _logger.info(
                "inspection: drop semantic edit at %s (old equals new)", address
            )
            continue
        unit: DisplayUnit | None = None
        placement: Placement | None = queued.placed
        reason: str | None = None
        idx0: int | None
        if placement is not None:
            # Settled by `unmask_edit`; the unmasked quote may match twice.
            idx0 = placement.index
        else:
            addressed = resolve_address(index, edit.page, edit.line)
            idx0 = addressed
            if idx0 is None and index.mapped:
                # Without page marks an out-of-range line anchors nothing.
                idx0 = wide_drift_anchor(index, edit.page, edit.line)
            if idx0 is None:
                _logger.info(
                    "inspection: skip semantic edit at %s (no such address: %s)",
                    address,
                    address_miss(index, edit.page),
                )
                skipped += 1
                continue
            old_text = strip_declared_address_prefix(edit.old, edit.page, edit.line)
            if not old_text.strip():
                # Checked after stripping: an echoed address alone is empty.
                _logger.info(
                    "inspection: skip semantic edit at %s (empty old)", address
                )
                skipped += 1
                continue
            unit = units.get(addressed) if addressed is not None else None
            if unit is not None and not matches_unit(lines, unit, old_text):
                # A quote of one piece still names a line of the body.
                unit = None
            if unit is not None:
                placement = Placement(unit.start)
            else:
                placement, reason = place_quote(
                    lines, addressed, idx0, old_text, edit.new
                )
            if placement is None:
                if reason is not None:
                    _logger.info(
                        "inspection: skip semantic edit at %s (%s)", address, reason
                    )
                else:
                    kind, at = mismatch_kind(lines, idx0, old_text)
                    _logger.info(
                        "inspection: skip semantic edit at %s (no match, %s): "
                        "old %r against line %r",
                        address,
                        kind,
                        sample(old_text),
                        sample(lines[at]),
                    )
                skipped += 1
                continue
        idx = placement.index
        span = placement.span
        end = idx + 1 if unit is None else unit.end
        prior = fragments.get(idx, [])
        # Two fragments of one line both apply. A conflict is an edit that
        # would drop one already applied: a whole line over anything, a
        # fragment over a whole line, or two fragments naming one stretch.
        taken = any(
            line_index in swallowed
            or (
                line_index in replacements
                and (span is None or line_index not in fragments)
            )
            for line_index in range(idx, end)
        )
        overlaps = span is not None and any(
            start < span[1] and span[0] < stop for (start, stop), _ in prior
        )
        if taken or overlaps:
            _logger.info("inspection: skip semantic edit at %s (conflict)", address)
            skipped += 1
            continue
        replacement = (
            edit.new
            if span is None
            else _splice_written(lines[idx], [*prior, (span, edit.new)])
        )
        if unit is not None:
            _logger.info(
                "inspection: edit %s names a formula cut across %d lines, "
                "replacing it whole",
                address,
                len(unit.pieces),
            )
        elif idx != idx0:
            _logger.info(
                "inspection: line drift at edit %s, applying %s at line %d",
                address,
                "a fragment" if span is not None else "the line",
                idx + 1,
            )
        elif span is not None:
            _logger.info(
                "inspection: edit %s names a fragment, replacing it in place",
                address,
            )
        if protected[idx]:
            _logger.info(
                "inspection: skip semantic edit at %s (protected zone)", address
            )
            skipped += 1
            continue
        # The page the edit lands on, not the one declared: drift can move it.
        source_page = index.address(idx)[0] - 1
        # The guard judges the whole line after the splice, or the joined
        # formula, since every ban is a property of what is replaced.
        current = (
            _splice_written(lines[idx], prior)
            if unit is None
            else unit_text(lines, unit)
        )
        refusal = rejection_reason(
            current,
            replacement,
            source_text,
            source_page,
            body_hyphens,
            latex_fix,
        )
        if refusal is not None:
            _logger.info(
                "inspection: reject semantic edit at line %d (%s)", idx + 1, refusal
            )
            rejected += 1
            continue
        folded = display_tail_fold(current, replacement)
        if folded is not None:
            _logger.info(
                "inspection: fold the sentence mark behind the closing $$ at line %d",
                idx + 1,
            )
            replacement = folded
            # The fold rewrites the whole line, so a later fragment on it is a
            # conflict; left in place, the records would splice the mark out.
            span = None
            fragments.pop(idx, None)
        for before, after in _changed_math_spans(current, replacement):
            _logger.info(
                "inspection: math span changed at %s: %r -> %r", address, before, after
            )
        replacements[idx] = replacement
        if span is not None:
            fragments.setdefault(idx, []).append((span, edit.new))
        swallowed.update(range(idx + 1, end))
        applied += 1

    out: list[str] = []
    # Counted while rebuilding: a multi-line replacement shifts later lines.
    edited_lines: set[int] = set()
    for idx, line in enumerate(lines):
        if idx in swallowed:
            continue
        written = replacements.get(idx)
        if written is None:
            out.append(line)
            continue
        for piece in written.split("\n"):
            edited_lines.add(len(out))
            out.append(piece)
    rebuilt = "\n".join(out)
    return InspectResult(
        body=f"{rebuilt}\n" if rebuilt else "",
        applied=applied,
        skipped=skipped,
        rejected=rejected,
        format_flags=len(flags),
        failure=coverage.failure,
        chunks=coverage.planned,
        skipped_chunks=coverage.skipped,
        touched=TouchedLines(edited=frozenset(edited_lines)),
    )


def _unmask_queue(
    semantic: list[SemanticEdit], masked: MaskedBody | None, index: PageIndex
) -> tuple[list[_Queued], int, int]:
    """The edits in the order they are applied, and what was lost here.

    Placeholder edits go last, so a repair around a formula lands on the line
    the ordinary edits produced. Returns the queue and the unmasked edits
    skipped and rejected.
    """
    if masked is None:
        return [_Queued(edit) for edit in semantic], 0, 0
    ordinary = [_Queued(edit) for edit in semantic if not quotes_the_mask(edit)]
    queue = list(ordinary)
    skipped = rejected = 0
    for edit in semantic:
        if not quotes_the_mask(edit):
            continue
        unmasked = unmask_edit(edit, masked, index)
        if unmasked.edit is not None:
            queue.append(_Queued(unmasked.edit, unmasked.placed))
            continue
        _logger.info(
            "inspection: %s semantic edit at %s quoting a masked formula (%s)",
            "reject" if unmasked.refused else "skip",
            address_label(edit.page, edit.line),
            unmasked.reason,
        )
        if unmasked.refused:
            rejected += 1
        else:
            skipped += 1
    unmasked_count = len(queue) - len(ordinary)
    if unmasked_count:
        _logger.info(
            "inspection: %d edit(s) quoting a masked formula read back against "
            "the body's own spans",
            unmasked_count,
        )
    return queue, skipped, rejected


def _log_flags(flags: list[str]) -> None:
    """Log the reply's format flags by type; the count is all that is kept."""
    if not flags:
        return
    counted = sorted(Counter(flags).items())
    _logger.info(
        "inspection: %d format flag(s) reported, none written into the body (%s)",
        len(flags),
        ", ".join(f"{flag} x{count}" for flag, count in counted),
    )


def _changed_math_spans(old: str, new: str) -> list[tuple[str, str]]:
    """The (before, after) pairs where a math span's content actually changed.

    A rewritten formula is worth its own log line.
    """
    if math_delimiters_only_moved(old, new):
        return []
    old_spans = math_spans(old)
    new_spans = math_spans(new)
    if len(old_spans) != len(new_spans):
        return []
    return [
        (before, after)
        for before, after in zip(old_spans, new_spans, strict=True)
        if before != after
    ]


def _splice(line: str, span: tuple[int, int], new: str) -> str:
    """`line` with `span` replaced by `new` stripped, the rest byte for byte."""
    start, end = span
    return f"{line[:start]}{new.strip()}{line[end:]}"


def _splice_written(line: str, written: Sequence[tuple[tuple[int, int], str]]) -> str:
    """`line` with every fragment of `written` spliced in, from the right.

    The spans never overlap: an overlapping fragment is refused as a conflict.
    """
    text = line
    for span, new in sorted(written, key=lambda item: item[0], reverse=True):
        text = _splice(text, span, new)
    return text
