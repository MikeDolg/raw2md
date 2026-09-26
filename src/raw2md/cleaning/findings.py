"""What cleaning finds and cannot fix, reported rather than written into the body.

`fix_images_and_report` runs after the in-place passes. It resolves unclosed
math environments first, so the detectors read the resolved text, then
resolves missing image links and reports a `Finding` per detected defect.
`trim_repetition_loops` runs after the detectors: the trim removes the
evidence that `broken-formula` records.

A finding is data for the stage report and the verdict. A mark in the body
would go stale as soon as a later stage rewrote the line.

`block_shows_defect` checks that a defect named off the source page has its
shape in the markdown. `drop_image_links` is shared with the pipeline.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from raw2md.cleaning.headings import detect_oversize_headings, detect_run_in_headings
from raw2md.cleaning.math import (
    collapse_repeated_spans,
    drop_loop_residue,
    resolve_unclosed_environment_spans,
)
from raw2md.cleaning.options import CleanOptions
from raw2md.cleaning.prose import (
    demark_seam_end,
    demark_seam_start,
    letter_spaced_runs,
    spacing_witness,
)
from raw2md.cleaning.segments import (
    FLATTEN_MAX_CHARS,
    FLATTEN_MIN_RUN,
    LIST_MARKER_RE,
    block_content_lines,
    block_end,
    blocks_are_adjacent,
    flattened_paragraph_runs,
    plain_blocks,
    prose_reading,
    skip_hyphen_gap,
)
from raw2md.mdtext.formulas import is_broken_math_span, math_unclosed_environment
from raw2md.mdtext.lines import is_thematic_break
from raw2md.mdtext.links import IMAGE_RE, is_local_target, local_image_path
from raw2md.mdtext.loops import collapse_repetition_loops, math_repetition_loop
from raw2md.mdtext.math_spans import RAW_LATEX_SPAN_RE, math_span_ranges
from raw2md.mdtext.tables import broken_table_details, has_cell_separator
from raw2md.mdtext.zones import Segment, mask_inline_code

# Post reads this kind back after re-cleaning: the spacing route answers for it.
LETTER_SPACING_FINDING = "letter-spacing"

# A word split across a break. Read on `demark_seam_end`, so a bold run that
# the converter reopens across the break does not hide the hyphen.
_HYPHEN_END_RE = re.compile(r"[^\W\d_]-\Z")

# Shortest line that reads as a row's cells crushed onto one line. No single
# fragment reaches it; measured, intact one-line blocks sit below it and
# crushed rows above.
_CRUSHED_LINE_MIN_CHARS = 4 * FLATTEN_MAX_CHARS

# Mirrors `mdtext.math_spans._DISPLAY_MATH_RE`; DOTALL to cross a multi-line formula.
_DISPLAY_MATH_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)


@dataclass(frozen=True)
class Finding:
    """One defect the cleaning stage found in the body and could not fix.

    `line` is 1-based in the body that cleaning writes, and goes stale once a
    later stage rewrites lines. `detail` is what the detector measured
    (`expected=3 got=2`), or empty.
    """

    kind: str
    line: int
    detail: str = ""

    def describe(self) -> str:
        """The finding as one line of a report: line, kind, then what it measured."""
        return f"line {self.line}: {self.kind} {self.detail}".rstrip()


def fix_images_and_report(
    seg_list: list[Segment], options: CleanOptions
) -> tuple[list[Segment], tuple[Finding, ...]]:
    """Resolve missing image links and report the defects left standing.

    Under `--disable-image-extraction` the removal runs first, so a promoted
    alt caption is read like any line and `clean` stays idempotent. A finding
    holds its index in the returned list; the caller renumbers it.
    """
    base_dir = options.base_dir
    if options.disable_image_extraction:
        seg_list = _strip_missing_image_lines(seg_list, base_dir)
    seg_list, unclosed_env_spans = resolve_unclosed_environment_spans(seg_list)
    hyphenated, hyphen_gaps = _detect_hyphenation(seg_list)
    broken_tables = broken_table_details(seg_list)
    flattened = _detect_flattened(seg_list) | detect_oversize_headings(
        seg_list, options.outline, options.keywords
    )
    broken_formulas = _detect_broken_formulas(seg_list) | unclosed_env_spans
    run_in_headings = detect_run_in_headings(seg_list, options.keywords)
    flattened_paragraphs = _detect_flattened_paragraphs(seg_list)
    letter_spacing = _detect_letter_spacing(seg_list)

    findings: list[Finding] = []
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        # After the removal above, only an extraction run reports one.
        missing = _missing_images(line, base_dir)
        findings.extend(
            Finding(kind, idx, detail)
            for kind, detail in _line_findings(
                idx,
                missing,
                hyphenated,
                hyphen_gaps,
                broken_tables,
                flattened,
                broken_formulas,
                run_in_headings,
                flattened_paragraphs,
                letter_spacing,
            )
        )
    return seg_list, tuple(findings)


def _strip_missing_image_lines(
    seg_list: list[Segment], base_dir: Path | None
) -> list[Segment]:
    """Remove missing-local image links from plain lines."""
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected or not _missing_images(line, base_dir):
            out.append((line, protected))
            continue
        out.extend((repl, False) for repl in _strip_missing_images(line, base_dir))
    return out


def _line_findings(
    idx: int,
    missing: list[re.Match[str]],
    hyphenated: set[int],
    hyphen_gaps: dict[int, int],
    broken_tables: dict[int, str],
    flattened: dict[int, int],
    broken_formulas: set[int],
    run_in_headings: set[int],
    flattened_paragraphs: dict[int, int],
    letter_spacing: set[int],
) -> list[tuple[str, str]]:
    """Kind and detail of every defect standing on line `idx`, one per kind."""
    found: list[tuple[str, str]] = []
    if missing:
        found.append(("broken-image", f"src={missing[0].group(2)}"))
    if idx in hyphenated:
        found.append(("hyphenation", ""))
    if idx in hyphen_gaps:
        found.append(("hyphenation-gap", f"blocks={hyphen_gaps[idx]}"))
    if idx in broken_tables:
        found.append(("broken-table", broken_tables[idx]))
    if idx in flattened:
        found.append(("flattened-block", f"lines={flattened[idx]}"))
    if idx in broken_formulas:
        found.append(("broken-formula", ""))
    if idx in run_in_headings:
        found.append(("run-in-heading", ""))
    if idx in flattened_paragraphs:
        found.append(("flattened-paragraphs", f"blocks={flattened_paragraphs[idx]}"))
    if idx in letter_spacing:
        found.append((LETTER_SPACING_FINDING, ""))
    return found


def trim_repetition_loops(
    seg_list: list[Segment],
) -> tuple[list[Segment], list[int]]:
    """Cut runaway repetition to one copy of the repeated unit.

    Largest unit first: identical blocks, identical lines in a block, whole
    inline spans, then loops inside a line. The content is lost, so an LLM step
    has nothing to rebuild it from. One copy stays, except a formula fragment
    that the cut leaves behind (`drop_loop_residue`): it would read as the
    document's own mathematics.

    Returns the trimmed list and, per index of `seg_list`, where that line
    landed, so that a finding moves with its line.
    """
    seg_list, landed = _cut_repeated_lines(_cut_repeated_blocks(seg_list))
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, protected))
            continue
        trimmed = collapse_repeated_spans(line)
        collapsed = collapse_repetition_loops(trimmed)
        if collapsed != trimmed:
            collapsed = drop_loop_residue(trimmed, collapsed)
        out.append((collapsed, False))
    return out, landed


# A page prints a unit twice on purpose; every observed two-copy run was
# real, and runaway runs reach a dozen to hundreds of copies.
_REPEATED_COPY_MIN_RUN = 3


def _cut_repeated_blocks(seg_list: list[Segment]) -> list[Segment]:
    """Blank every copy past the first in a run of identical blocks.

    Only blank lines may separate the copies: a document that returns to the
    same text has its own content in between. Copies are blanked, not
    removed, so that finding indices stay valid.
    """
    out = list(seg_list)
    blocks = plain_blocks(seg_list)
    idx = 0
    while idx < len(blocks):
        content = block_content_lines(seg_list, *blocks[idx])
        end = idx + 1
        while end < len(blocks) and _repeats_block(seg_list, blocks, end, content):
            end += 1
        if end - idx >= _REPEATED_COPY_MIN_RUN and _repeats_may_be_cut(content):
            for start, stop in blocks[idx + 1 : end]:
                for line_idx in range(start, stop):
                    out[line_idx] = ("", False)
        idx = end
    return out


def _repeats_block(
    seg_list: list[Segment],
    blocks: list[tuple[int, int]],
    idx: int,
    content: list[str],
) -> bool:
    """True when block `idx` repeats `content` and stands right after `idx - 1`."""
    start, end = blocks[idx]
    return block_content_lines(seg_list, start, end) == content and blocks_are_adjacent(
        seg_list, blocks[idx - 1][1], start
    )


def _cut_repeated_lines(seg_list: list[Segment]) -> tuple[list[Segment], list[int]]:
    """Cut every run of identical lines inside one block to one copy.

    Survivors move to the top of the block and the tail is blanked, so the
    block is not split. Also returns where each line landed; a dropped copy
    lands on its survivor.
    """
    out = list(seg_list)
    landed = list(range(len(seg_list)))
    for start, end in plain_blocks(seg_list):
        lines = block_content_lines(seg_list, start, end)
        kept = _without_repeats(lines, _display_span_interior(lines))
        if len(kept) == len(lines):
            continue
        for offset in range(end - start):
            out[start + offset] = (
                lines[kept[offset]] if offset < len(kept) else "",
                False,
            )
        landing = {source: offset for offset, source in enumerate(kept)}
        survivor = 0
        for offset in range(end - start):
            survivor = landing.get(offset, survivor)
            landed[start + offset] = start + survivor
    return out, landed


def _without_repeats(lines: Sequence[str], interior: set[int]) -> list[int]:
    """Offsets of `lines` that survive the cut; `interior` lines are exempt."""
    kept: list[int] = []
    idx = 0
    while idx < len(lines):
        end = idx + 1
        while end < len(lines) and lines[end] == lines[idx]:
            end += 1
        copies = end - idx
        if (
            copies >= _REPEATED_COPY_MIN_RUN
            and _repeats_may_be_cut([lines[idx]])
            and interior.isdisjoint(range(idx, end))
        ):
            copies = 1
        kept.extend(range(idx, idx + copies))
        idx = end
    return kept


def _display_span_interior(lines: Sequence[str]) -> set[int]:
    """Offsets inside a closed multi-line display formula.

    Identical rows of a matrix are what it states. An opener with no closer is
    truncation and does not count.
    """
    text = mask_inline_code("\n".join(lines))
    opens = [0]
    for line in lines[:-1]:
        opens.append(opens[-1] + len(line) + 1)
    interior: set[int] = set()
    for match in _DISPLAY_MATH_RE.finditer(text):
        first = bisect_right(opens, match.start()) - 1
        last = bisect_right(opens, match.end() - 1) - 1
        if last > first:
            interior.update(range(first, last + 1))
    return interior


def _repeats_may_be_cut(lines: Sequence[str]) -> bool:
    """False for table rows: identical rows, empty ones too, are table data."""
    return not any(has_cell_separator(line) for line in lines)


def _detect_broken_formulas(seg_list: list[Segment]) -> set[int]:
    """Indices of plain lines carrying a math span lost to recognition damage.

    Two shapes: a repetition loop that a length cap truncated, and an
    environment left open before its `\\end`. Only inspection, with the scan,
    can restore either. Detection is shared with the evaluator. The first line
    of a sound multi-line display formula looks the same line by line, so
    `_opens_a_sound_multiline_display_span` checks where it closes.
    """
    flagged: set[int] = set()
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        if not (math_repetition_loop(line) or math_unclosed_environment(line)):
            continue
        if _opens_a_sound_multiline_display_span(seg_list, idx):
            continue
        flagged.add(idx)
    return flagged


def _opens_a_sound_multiline_display_span(seg_list: list[Segment], idx: int) -> bool:
    """True when line `idx` opens a display formula that closes soundly below.

    The pair must start on line `idx`, end inside its block, and pass
    `is_broken_math_span`.
    """
    end = block_end(seg_list, idx)
    if end <= idx:
        return False
    run_text = "\n".join(seg_list[i][0] for i in range(idx, end))
    masked = mask_inline_code(run_text)
    line_end = len(seg_list[idx][0])
    for match in _DISPLAY_MATH_RE.finditer(masked):
        if match.start() >= line_end:
            break
        if match.end() > line_end and not is_broken_math_span(
            run_text[match.start() : match.end()]
        ):
            return True
    return False


def _detect_letter_spacing(seg_list: list[Segment]) -> set[int]:
    """Indices of lines carrying a letter-spaced run the body could not settle.

    A heading counts too: the title rule rebuilds nothing when the body cannot
    say where the words end. `spacing_witness` keeps out single-letter
    designations joined by a conjunction.
    """
    witness = spacing_witness(seg_list)
    return {
        idx
        for idx, text in enumerate(prose_reading(seg_list))
        if text is not None and letter_spaced_runs(text, witness)
    }


def _detect_hyphenation(seg_list: list[Segment]) -> tuple[set[int], dict[int, int]]:
    """Indices of lines that split a word the rejoin could not confirm.

    Returns adjacent splits, and gapped splits with the count of extra blocks
    that a repair must take in to reach the continuation.
    """
    adjacent: set[int] = set()
    gapped: dict[int, int] = {}
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        if not _HYPHEN_END_RE.search(demark_seam_end(line)):
            continue
        if idx + 1 < len(seg_list):
            next_line, next_protected = seg_list[idx + 1]
            if not next_protected and _looks_like_continuation(next_line):
                adjacent.add(idx)
                continue
        gap_idx = skip_hyphen_gap(seg_list, idx + 1)
        if gap_idx is None:
            continue
        cont_line, cont_protected = seg_list[gap_idx]
        if not cont_protected and _looks_like_continuation(cont_line):
            gapped[idx] = _block_span_count(seg_list, idx, gap_idx)
    return adjacent, gapped


def _looks_like_continuation(line: str) -> bool:
    """True when `line` opens with a lowercase letter, past an emphasis marker."""
    head = demark_seam_start(line)[:1]
    return bool(head) and head.isalpha() and head.islower()


def _block_span_count(seg_list: list[Segment], start: int, gap_idx: int) -> int:
    """Blocks past `start` through `gap_idx`'s block, as `post` groups zones.

    An image flush against the continuation is one block with it, not two.
    """
    target_end = block_end(seg_list, gap_idx)
    blocks = 0
    idx = start + 1
    while idx < target_end:
        line, protected = seg_list[idx]
        if protected or not line.strip():
            idx += 1
            continue
        blocks += 1
        idx = block_end(seg_list, idx)
    return blocks


def _detect_flattened(seg_list: list[Segment]) -> dict[int, int]:
    """First-line index -> run length for runs of short flat lines."""
    flagged: dict[int, int] = {}
    count = len(seg_list)
    idx = 0
    while idx < count:
        if seg_list[idx][1] or not _is_flatten_candidate(seg_list[idx][0]):
            idx += 1
            continue
        start = idx
        while (
            idx < count
            and not seg_list[idx][1]
            and _is_flatten_candidate(seg_list[idx][0])
        ):
            idx += 1
        run = idx - start
        if run >= FLATTEN_MIN_RUN:
            flagged[start] = run
    return flagged


def _is_flatten_candidate(line: str) -> bool:
    """A short, structureless line that could be part of a crushed table column.

    Math is excluded: the short rows of a multi-line formula are layout, not a
    crushed column.
    """
    core = line.strip()
    if not core or len(core) > FLATTEN_MAX_CHARS:
        return False
    if "|" in core or "![" in core or "$" in core:
        return False
    if core.startswith(("#", ">")):
        return False
    return not (is_thematic_break(core) or LIST_MARKER_RE.match(core))


def _block_splits_a_word(lines: Sequence[str]) -> bool:
    """True when a line of the block ends in a letter and a hyphen before content.

    The next line need not read as a continuation: a reader with the source
    page can tell a break from a real hyphen.
    """
    return any(
        _HYPHEN_END_RE.search(demark_seam_end(line)) and bool(lines[idx + 1].strip())
        for idx, line in enumerate(lines[:-1])
    )


def _block_is_crushed(lines: Sequence[str]) -> bool:
    """True when the block reads as text a narrow column or a table crushed.

    Either a run of short lines or a line too long for one fragment. A line
    with math counts for neither.
    """
    run = 0
    for line in lines:
        run = run + 1 if _is_flatten_candidate(line) else 0
        if run >= FLATTEN_MIN_RUN:
            return True
    return any(
        len(line.strip()) > _CRUSHED_LINE_MIN_CHARS and "$" not in line
        for line in lines
    )


# pandoc puts a display `\[` on its own line, so a block reader must cross
# line breaks.
_RAW_LATEX_BLOCK_RE = re.compile(RAW_LATEX_SPAN_RE.pattern, re.DOTALL)


def _block_holds_a_formula(lines: Sequence[str]) -> bool:
    """True when the block carries a math span at all, sound or not.

    A truncated formula can render like a whole one, so soundness is not
    asked. The lines are joined, so a multi-line display formula counts. Both
    dialects count: marker's `$` and pandoc's `\\(...\\)`. The cleaner's own
    finding is never re-judged here: its residue may be gone from the line.
    """
    masked = mask_inline_code("\n".join(lines))
    return bool(math_span_ranges(masked) or _RAW_LATEX_BLOCK_RE.search(masked))


def _block_holds_a_table(lines: Sequence[str]) -> bool:
    """True when the block shows tabular structure, whole or crushed.

    Either a pipe row or a crushed grid (`_block_is_crushed`). Elsewhere a
    repair would invent a grid that nothing in the document attests.
    """
    if any(has_cell_separator(line) for line in lines):
        return True
    return _block_is_crushed(lines)


# Each reader asks for the shape, not for the stricter detector's verdict: a
# reader of the page sees damage the markdown cannot prove. `broken-image` is
# a fact about the file, not the text.
_BLOCK_SHAPES: dict[str, Callable[[Sequence[str]], bool]] = {
    "hyphenation": _block_splits_a_word,
    "flattened-block": _block_is_crushed,
    "broken-formula": _block_holds_a_formula,
    "broken-table": _block_holds_a_table,
}


def block_shows_defect(kind: str, lines: Sequence[str]) -> bool:
    """True when `lines` carry the shape the defect `kind` names.

    A step working off the source page can name a defect the conversion
    already resolved or the page never held. The licence it buys must be
    grounded in the markdown. A kind with no shape reader passes.
    """
    check = _BLOCK_SHAPES.get(kind)
    if check is None:
        return True
    return check(lines)


def _detect_flattened_paragraphs(seg_list: list[Segment]) -> dict[int, int]:
    """First-line index -> extra block count, for a run of paragraph fragments.

    A repair needs the whole run in one request, so the detail counts the
    blocks past the first.
    """
    return {run[0][0]: len(run) - 1 for run in flattened_paragraph_runs(seg_list)}


def _is_missing_local_image(base_dir: Path, target: str) -> bool:
    """True when `target` is a local image link and it does not exist.

    A target that escapes `base_dir` is not ours to check.
    """
    if not is_local_target(target):
        return False
    path = local_image_path(base_dir, target)
    return path is not None and not path.exists()


def _missing_images(line: str, base_dir: Path | None) -> list[re.Match[str]]:
    """Image-link matches whose local target is missing; none without `base_dir`."""
    if base_dir is None:
        return []
    return [
        m
        for m in IMAGE_RE.finditer(line)
        if _is_missing_local_image(base_dir, m.group(2))
    ]


def _strip_missing_images(line: str, base_dir: Path | None) -> list[str]:
    """Replace `line`, dropping missing-image links and keeping meaningful alts."""
    if base_dir is None:
        return [line]
    return drop_image_links(
        line, lambda target: _is_missing_local_image(base_dir, target)
    )


def drop_image_links(line: str, is_dropped: Callable[[str], bool]) -> list[str]:
    """Replace `line`, dropping an image link whose target `is_dropped` accepts.

    An alt caption with an alphanumeric character becomes its own paragraph;
    an empty one goes with the link.
    """
    captions: list[str] = []

    def replace(match: re.Match[str]) -> str:
        if not is_dropped(match.group(2)):
            return match.group(0)
        alt = match.group(1).strip()
        if any(ch.isalnum() for ch in alt):
            captions.append(alt)
        return ""

    remainder = IMAGE_RE.sub(replace, line).strip()
    out: list[str] = []
    if any(ch.isalnum() for ch in remainder):
        out.append(remainder)
    out.extend(captions)
    return out
