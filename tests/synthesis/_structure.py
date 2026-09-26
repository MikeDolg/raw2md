"""Deterministic structural counters for round-trip contract checks.

Counting reuses the `raw2md.mdtext` primitives, so a table or a protected zone
is recognized as the cleaner and the evaluator see it. Code fences are the
exception: only the harness needs their info string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from raw2md.mdtext.lines import is_setext_underline, is_table_separator
from raw2md.mdtext.links import IMAGE_RE
from raw2md.mdtext.zones import segments

# Only the harness needs the info string, so the product carries no fence reader.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

# Setext headings are recognised apart, through `is_setext_underline`.
_HEADING_RE = re.compile(r"^(#{1,6})\s")

# pandoc emits a sized image as raw `<img ... />`.
_IMG_TAG_RE = re.compile(r"<img\b", re.IGNORECASE)

# Display spans go first, so their inner `$` never reads as inline.
_DISPLAY_MATH_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$([^\n]+?)(?<!\\)\$")


def _fence_info_strings(text: str) -> list[str]:
    """Info strings of top-level fenced code blocks, in document order.

    pandoc writes display math as a fenced ``math`` block. A block closes on the
    first bare fence of the same kind and at least the same length (CommonMark).
    """
    infos: list[str] = []
    marker: str | None = None
    for line in text.split("\n"):
        m = _FENCE_RE.match(line)
        if marker is not None:
            fence = m.group(1) if m is not None else ""
            closes = (
                m is not None
                and fence[0] == marker[0]
                and len(fence) >= len(marker)
                and not m.group(2).strip()
            )
            if closes:
                marker = None
            continue
        if m is not None:
            marker = m.group(1)
            infos.append(m.group(2).strip())
    return infos


@dataclass(frozen=True)
class StructureCounts:
    """Structural shape of a markdown body for round-trip comparison."""

    headings_by_level: dict[int, int]
    tables: int
    images: int
    display_formulas: int
    inline_formulas: int

    @property
    def headings_total(self) -> int:
        return sum(self.headings_by_level.values())

    @property
    def formulas_total(self) -> int:
        return self.display_formulas + self.inline_formulas


@dataclass(frozen=True)
class StructureDiff:
    """A single structural mismatch between a reference and an output body."""

    kind: str
    expected: int
    actual: int


def count_structure(md_body: str) -> StructureCounts:
    """Count headings (by level), tables, image links, and formulas in `md_body`.

    Protected zones are skipped. Headings count in ATX and setext form; a setext
    underline needs an unprotected line above it. A table counts once, by its header
    and separator pair. Images count as markdown and as ``<img>``. Display spans,
    including a fenced ``math`` block, are removed before the inline scan.
    """
    seg = segments(md_body)
    headings: dict[int, int] = {}
    tables = 0
    images = 0
    count = len(seg)
    idx = 0
    while idx < count:
        line, protected = seg[idx]
        if protected:
            idx += 1
            continue
        images += len(IMAGE_RE.findall(line)) + len(_IMG_TAG_RE.findall(line))
        heading = _HEADING_RE.match(line)
        if heading is not None:
            level = len(heading.group(1))
            headings[level] = headings.get(level, 0) + 1
            idx += 1
            continue
        core = line.strip()
        prev_raw, prev_protected = seg[idx - 1] if idx > 0 else ("", True)
        if not prev_protected and is_setext_underline(core, prev_raw):
            level = 1 if core[0] == "=" else 2
            headings[level] = headings.get(level, 0) + 1
            idx += 1
            continue
        if "|" in line and line.strip() and idx + 1 < count:
            sep_line, sep_protected = seg[idx + 1]
            if not sep_protected and is_table_separator(sep_line.strip()):
                tables += 1
                idx += 2  # skip the header and separator; body rows are not tables
                continue
        idx += 1

    unprotected = "\n".join(line for line, protected in seg if not protected)
    # pandoc's fenced ``math`` block lands in a protected zone; count it too.
    math_fence_blocks = sum(
        1 for info in _fence_info_strings(md_body) if info.lower() == "math"
    )
    display_formulas = len(_DISPLAY_MATH_RE.findall(unprotected)) + math_fence_blocks
    inline_formulas = len(
        _INLINE_MATH_RE.findall(_DISPLAY_MATH_RE.sub("", unprotected))
    )

    return StructureCounts(
        headings_by_level=headings,
        tables=tables,
        images=images,
        display_formulas=display_formulas,
        inline_formulas=inline_formulas,
    )


def compare_structure(
    reference: StructureCounts,
    output: StructureCounts,
    *,
    heading_tolerance: int = 0,
    table_tolerance: int = 0,
    image_tolerance: int = 0,
    display_formula_tolerance: int = 0,
    inline_formula_tolerance: int = 0,
    check_headings: bool = True,
) -> list[StructureDiff]:
    """Return structural mismatches beyond the given per-kind tolerances.

    Headings compare per level, so a collapsed level is caught despite an equal
    total; ``check_headings=False`` skips them for marker on a born-digital PDF.
    Display and inline formulas have separate tolerances, since marker keeps
    display math but writes inline math as plain text.
    """
    diffs: list[StructureDiff] = []
    if check_headings:
        levels = set(reference.headings_by_level) | set(output.headings_by_level)
        for level in sorted(levels):
            expected = reference.headings_by_level.get(level, 0)
            actual = output.headings_by_level.get(level, 0)
            if abs(expected - actual) > heading_tolerance:
                diffs.append(StructureDiff(f"headings_h{level}", expected, actual))
    if abs(reference.tables - output.tables) > table_tolerance:
        diffs.append(StructureDiff("tables", reference.tables, output.tables))
    if abs(reference.images - output.images) > image_tolerance:
        diffs.append(StructureDiff("images", reference.images, output.images))
    if (
        abs(reference.display_formulas - output.display_formulas)
        > display_formula_tolerance
    ):
        diffs.append(
            StructureDiff(
                "display_formulas", reference.display_formulas, output.display_formulas
            )
        )
    if (
        abs(reference.inline_formulas - output.inline_formulas)
        > inline_formula_tolerance
    ):
        diffs.append(
            StructureDiff(
                "inline_formulas", reference.inline_formulas, output.inline_formulas
            )
        )
    return diffs
