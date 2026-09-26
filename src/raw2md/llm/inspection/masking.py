"""Mask sound math spans out of the request, and read a quote of one back.

No edit may rewrite a sound span, so showing it only pays for the reply
restating it. A formula always comes back from the body, never from the reply.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from itertools import pairwise

from raw2md.llm.chunking import PageIndex
from raw2md.llm.inspection.addressing import (
    Placement,
    address_miss,
    place_quote,
    resolve_address,
    strip_declared_address_prefix,
    wide_drift_anchor,
)
from raw2md.llm.inspection.common import SemanticEdit
from raw2md.mdtext.formulas import is_broken_math_span
from raw2md.mdtext.math_spans import math_span_content, math_span_ranges

_logger = logging.getLogger("raw2md")


# A sound math span in the request. The words keep the model from reporting
# the mask as a lost formula; the number is the span's position on its line,
# which unmasking reads back. The inspection prompt spells the same token.
_MASK_TEMPLATE = "⟦valid formula {number}⟧"


_MASK_RE = re.compile(r"⟦valid formula (\d+)⟧")


# Neither bracket occurs in a converted body, so a quote carrying one answers
# the request's own text; half a mask or a mangled number is caught too.
_MASK_BRACKETS = "⟦⟧"


@dataclass(frozen=True)
class MaskedBody:
    """The body as the request showed it, and what its placeholders stand for.

    `spans[i]` are the sound spans of line `i` in placeholder order; a formula
    always comes back from here, never from the reply.
    """

    lines: list[str]
    spans: list[list[str]]


@dataclass(frozen=True)
class _Slot:
    """One formula-shaped piece of a quote or of its replacement.

    `number` is the placeholder's, None for a math span written out.
    """

    start: int
    end: int
    number: int | None


@dataclass(frozen=True)
class Unmasked:
    """One placeholder-quoting edit read back against the body, or its refusal.

    `placed` is settled here, since the unmasked quote no longer says which
    occurrence it named. `refused` counts as a rejection; otherwise a failure
    is a missed match.
    """

    edit: SemanticEdit | None = None
    placed: Placement | None = None
    reason: str | None = None
    refused: bool = False


def masked_lines(lines: list[str], protected: list[bool]) -> MaskedBody:
    """`lines` with every sound math span replaced by its placeholder.

    No edit may rewrite such a span, so showing it only pays for the reply
    restating it. The mask keeps the line's address and prose. A protected
    zone and an unclosed `$`-region stay whole: the latter's missing closer is
    the damage.
    """
    out: list[str] = []
    spans: list[list[str]] = []
    masked = 0
    for line, is_protected in zip(lines, protected, strict=True):
        if is_protected:
            out.append(line)
            spans.append([])
            continue
        shown, line_spans = _mask_sound_spans(line)
        out.append(shown)
        spans.append(line_spans)
        masked += len(line_spans)
    if masked:
        _logger.info(
            "inspection: %d sound math span(s) masked out of the request", masked
        )
    return MaskedBody(out, spans)


def _mask_sound_spans(line: str) -> tuple[str, list[str]]:
    """`line` with its sound math spans masked, and the spans in placeholder order."""
    sound = [
        (start, end)
        for start, end in math_span_ranges(line)
        if _is_sound_span(line[start:end])
    ]
    shown = line
    # Right to left, so earlier offsets stay valid.
    for number, (start, end) in reversed(list(enumerate(sound, start=1))):
        shown = f"{shown[:start]}{_mask(number)}{shown[end:]}"
    return shown, [line[start:end] for start, end in sound]


def _mask(number: int) -> str:
    return _MASK_TEMPLATE.format(number=number)


def _is_sound_span(span: str) -> bool:
    """True when `span` is a closed math span the tool sees nothing wrong with.

    An unclosed region's content can read as sound while the closer is the
    damage.
    """
    content = math_span_content(span)
    if span not in (f"${content}$", f"$${content}$$"):
        return False
    return not is_broken_math_span(span)


def quotes_the_mask(edit: SemanticEdit) -> bool:
    return any(bracket in edit.old or bracket in edit.new for bracket in _MASK_BRACKETS)


def unmask_edit(edit: SemanticEdit, masked: MaskedBody, index: PageIndex) -> Unmasked:
    """Read an edit that quotes a placeholder back against the body it addresses.

    The quote is matched against the masked line, and the body's own span goes
    back into every masked slot on both sides: whatever the reply wrote there
    is thrown away. The replacement must answer with as many formulas as the
    quote held, in the same places, or the edit is refused. The model's version
    of a condemned span is kept for the edit guard. The placement is settled
    here: unmasked, the quote may stand twice on its line.
    """
    old_text = strip_declared_address_prefix(edit.old, edit.page, edit.line)
    quoted = _slots(old_text)
    answered = _slots(edit.new)
    if quoted is None or answered is None:
        return Unmasked(reason="a mask bracket outside a placeholder", refused=True)
    if all(slot.number is None for slot in quoted):
        return Unmasked(reason="a placeholder in the replacement alone", refused=True)
    if len(answered) != len(quoted):
        return Unmasked(
            reason=(
                f"the replacement answers {len(answered)} formula(s) where the "
                f"quote held {len(quoted)}"
            ),
            refused=True,
        )
    for want, got in zip(quoted, answered, strict=True):
        if got.number is None:
            continue
        if want.number is None:
            return Unmasked(
                reason="a placeholder where the quote held a formula", refused=True
            )
        if got.number != want.number:
            return Unmasked(
                reason="the replacement reorders the placeholders it quoted",
                refused=True,
            )
    addressed = resolve_address(index, edit.page, edit.line)
    idx0 = addressed
    if idx0 is None and index.mapped:
        idx0 = wide_drift_anchor(index, edit.page, edit.line)
    if idx0 is None:
        return Unmasked(reason=f"no such address: {address_miss(index, edit.page)}")
    placement, reason = place_quote(masked.lines, addressed, idx0, old_text, edit.new)
    if placement is None:
        return Unmasked(reason=reason or "no match against the masked line")
    spans = masked.spans[placement.index]
    if any(
        slot.number is not None and not 1 <= slot.number <= len(spans)
        for slot in quoted
    ):
        return Unmasked(reason="a placeholder names no span of the line")
    page, line = index.address(placement.index)
    return Unmasked(
        edit=replace(
            edit,
            page=page,
            line=line,
            old=_unmask_text(old_text, quoted, quoted, spans),
            new=_unmask_text(edit.new, answered, quoted, spans),
        ),
        placed=Placement(
            placement.index,
            _unmasked_span(masked.lines[placement.index], spans, placement.span),
        ),
    )


def _unmasked_span(
    masked_line: str, spans: list[str], span: tuple[int, int] | None
) -> tuple[int, int] | None:
    """`span`, read on the masked line, in the offsets of the body's own line."""
    if span is None:
        return None
    start, end = span
    return (
        _unmasked_offset(masked_line, spans, start),
        _unmasked_offset(masked_line, spans, end),
    )


def _unmasked_offset(masked_line: str, spans: list[str], offset: int) -> int:
    """`offset` on the masked line, moved to where the body's own line holds it.

    A token whose number names no span of the line is the body's own text.
    """
    moved = offset
    for match in _MASK_RE.finditer(masked_line):
        if match.end() > offset:
            break
        number = int(match.group(1))
        if 1 <= number <= len(spans):
            moved += len(spans[number - 1]) - len(match.group())
    return moved


def _slots(text: str) -> list[_Slot] | None:
    """The formula slots of `text` in order: placeholders and math spans.

    None for a stray bracket or a placeholder a `$`-region swallowed.
    """
    masks = [
        _Slot(match.start(), match.end(), int(match.group(1)))
        for match in _MASK_RE.finditer(text)
    ]
    if any(bracket in _MASK_RE.sub("", text) for bracket in _MASK_BRACKETS):
        return None
    slots = sorted(
        masks + [_Slot(start, end, None) for start, end in math_span_ranges(text)],
        key=lambda slot: slot.start,
    )
    if any(before.end > after.start for before, after in pairwise(slots)):
        return None
    return slots


def _unmask_text(
    text: str, slots: list[_Slot], quoted: list[_Slot], spans: list[str]
) -> str:
    """`text` with the body's own span standing in every slot the quote masked.

    `slots` are this text's own, `quoted` the quote's, read position by position.
    """
    out = text
    for slot, want in reversed(list(zip(slots, quoted, strict=True))):
        if want.number is None:
            continue
        out = f"{out[: slot.start]}{spans[want.number - 1]}{out[slot.end :]}"
    return out
