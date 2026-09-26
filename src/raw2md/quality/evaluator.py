"""Quality evaluation: deterministic checks that decide ok vs bad.

The evaluator never changes content. It returns an `Evaluation`: the status,
the defects that fired, and two log hints, `repairable` (post could fix the
markup) and `recognition_failure` (recognize again through an LLM).

Structural checks read the body as the final write produces it. A lost
formula, a word split across a break, and a crushed block leave no trace in
the text, so they are counted from the cleaning report instead.

A fired check is not always `bad`. The eight small structural checks, and
lost chapters, are `minor` within a size-scaled threshold: kept in `issues`,
left out of the status. Repeated images and an inconsistent heading ladder
are always minor: a legitimate document shows those shapes too.

The checks run in fixed groups, and the order of the groups and of the checks
inside each is the order of `issues`.
"""

from __future__ import annotations

import logging
import re
import statistics
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

from PIL import Image

from raw2md.cleaning import Finding
from raw2md.header import ResultStatus
from raw2md.keywords import Keywords, default_keywords
from raw2md.mdtext.formulas import is_valid_math
from raw2md.mdtext.lines import (
    is_html_media_wrapper_line,
    is_setext_underline,
    is_structural_symbol_line,
    is_table_separator,
)
from raw2md.mdtext.links import HTML_IMG_RE, IMAGE_RE, is_local_target, local_image_path
from raw2md.mdtext.loops import math_repetition_loop
from raw2md.mdtext.math_spans import is_math_only_line, math_span_ranges
from raw2md.mdtext.pages import is_lost_page_marker
from raw2md.mdtext.tables import broken_table_details, has_cell_separator
from raw2md.mdtext.zones import Segment, mask_inline_code, segments
from raw2md.quality.headings import (
    HEADING_RE,
    count_flat_ladder,
    count_heading_issues,
    count_ladder_issues,
    count_lost_chapters,
)
from raw2md.source_outline import SourceOutline
from raw2md.source_text import SourceText, tokenize

_logger = logging.getLogger("raw2md")

# Firing and escalation thresholds. The lower value of a pair makes the status
# `bad`; the higher one escalates to a likely recognition failure.
_DENSITY_MIN_CHARS_PER_PAGE = 350
_EMPTY_BODY_MIN_ALNUM = 20
_UNREADABLE_MIN_LETTERS = 200
_UNREADABLE_MAX_OTHER_SHARE = 0.15
_MOJIBAKE_MAX_ACCENTED_SHARE = 0.15
_MOJIBAKE_MIN_CYRILLIC_SHARE = 0.05
_JUNK_REPAIRABLE_SHARE = 0.02
_JUNK_FAILURE_SHARE = 0.05
_REPEAT_MAX_LEN = 80
_REPEAT_CONNECTOR_MAX_LEN = 3
_IMAGE_MIN_BYTES = 512
_REPEATED_IMAGE_MIN_COUNT = 3

# Past either cap a display block is prose swallowed by an unclosed
# delimiter: real display math stays far below, a runaway block runs to
# hundreds of lines and tens of thousands of characters.
_MATH_BLOCK_MAX_LINES = 40
_MATH_BLOCK_MAX_CHARS = 3000

# Scaled with body size: a long clean book collects more residual defects
# without worse recognition. Each pair is a floor and a rate per 1000 lines.
_REPEAT_MIN_COUNT = 3
_REPEAT_MIN_RATE_PER_1000_LINES = 1
_FORMULA_FAILURE_COUNT = 5
_FORMULA_FAILURE_RATE_PER_1000_LINES = 2
_REPORTED_FAILURE_COUNT = 10
_REPORTED_FAILURE_RATE_PER_1000_LINES = 4
_GREEK_UNIT_FAILURE_COUNT = 5
_GREEK_UNIT_FAILURE_RATE_PER_1000_LINES = 2

# Any lost chunk fires, since nothing else records the loss; below half the
# chunks answered it decides the status. Not size-scaled: it is already a
# share of the plan.
_INSPECTION_COVERAGE_BAD_SHARE = 0.5

# Where the eight small structural checks start deciding the status, as a
# floor plus a rate per 1000 body lines. Calibrated on scans: a nearly clean
# book had 3 heading jumps over 1500 lines, a damaged one 32 over 7900.
# Headings, the flat ladder, repeats, and tables have no floor, so a short
# document earns no free defect. Formulas and lost formulas keep a floor of 2,
# half the escalation pair, so the bands stay ordered. The two report-only
# checks run at twice that rate, each on its own count: unfinished repair
# work, not a proven loss. Tables were calibrated on broken-row rates of 0 to
# 22 per 1000 lines: the worst bodies still decide, those with a handful do not.
_HEADING_BAD_COUNT = 0
_HEADING_BAD_RATE_PER_1000_LINES = 2
_FLAT_LADDER_BAD_COUNT = 0
_FLAT_LADDER_BAD_RATE_PER_1000_LINES = 2
_REPEAT_BAD_COUNT = 0
_REPEAT_BAD_RATE_PER_1000_LINES = 1
_FORMULA_BAD_COUNT = 2
_FORMULA_BAD_RATE_PER_1000_LINES = 1
_LOST_FORMULA_BAD_COUNT = 2
_LOST_FORMULA_BAD_RATE_PER_1000_LINES = 1
_TABLE_BAD_COUNT = 0
_TABLE_BAD_RATE_PER_1000_LINES = 1
_REPORTED_BAD_COUNT = 2
_REPORTED_BAD_RATE_PER_1000_LINES = 2

# Weighed against the contents, not the body size. A quarter lost is the top
# rank gone; the floor keeps out a single title misread by a typo.
_LOST_CHAPTER_BAD_SHARE = Fraction(1, 4)
_LOST_CHAPTER_BAD_COUNT = 1

# A line repeating past this multiple of the minimum decides the status: a
# loop swallowing a chapter is one distinct line. Legitimate repeats (a reused
# caption, a lecture's outline label) top out near five times the minimum.
_REPEAT_LOOP_MULTIPLE = 10

# Median gap, in lines, up to which repeats read as a loop: a loop puts its
# copies 1-2 lines apart, a template scatters them. Legitimate repeats measured
# a median gap of 4 to over 500.
_REPEAT_MAX_MEDIAN_GAP = 3

# LLM OCR markers; post must not touch them: recovering the word means
# inventing it.
_OCR_MARKERS = ("[unreadable]", "[?]")

# `\$` is escaped and neither opens nor closes a span.
_DISPLAY_MATH_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$([^\n]+?)(?<!\\)\$")

# A run of exactly two is the display delimiter the pairing check counts.
_DOLLAR_RUN_RE = re.compile(r"(?<!\\)\$+")

# Dropped whole from the coverage metric: attributes are not prose.
_HTML_IMG_TAG_RE = re.compile(r"<img\b[^>]*/?>", re.IGNORECASE)

# `\hbar` joins them: the same OCR misread of a Cyrillic unit produces it.
_GREEK_COMMAND_RE = re.compile(
    r"\\(?:hbar|varepsilon|vartheta|varpi|varrho|varsigma|varphi"
    r"|alpha|beta|gamma|delta|epsilon|zeta|eta|theta|iota|kappa"
    r"|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|chi|psi|omega"
    r"|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega)"
    r"(?![A-Za-z])"
)

# An integer, a spacer, and two or more glued Greek commands: OCR reading a
# Cyrillic unit (`55 кГ`) as Greek. One command is a real unit (`\Omega`), and
# real math juxtaposes without a spacer (`2\pi`).
_GREEK_UNIT_SPAN_RE = re.compile(
    rf"^\d+(?:\s|~)+((?:{_GREEK_COMMAND_RE.pattern}){{2,}})$"
)

# Micro-ohm, the one real SI unit of two glued Greek commands.
_LEGITIMATE_GREEK_UNIT_COMBOS = frozenset({r"\mu\Omega"})


# `str, Enum` rather than `StrEnum`: the two format differently, and this
# value reaches the result header. Moving it is a change of its own.
class CheckId(str, Enum):  # noqa: UP042
    """Identifier of a quality check; the value is its log/metric key."""

    TEXT_DENSITY = "text_density"
    EMPTY_BODY = "empty_body"
    UNREADABLE_CHARS = "unreadable_chars"
    FORMULAS = "formulas"
    LOST_FORMULAS = "lost_formulas"
    HEADINGS = "headings"
    HEADING_LADDER = "heading_ladder"
    FLAT_LADDER = "flat_ladder"
    LOST_CHAPTERS = "lost_chapters"
    TABLES = "tables"
    JUNK_LINES = "junk_lines"
    REPEATS = "repeats"
    IMAGES = "images"
    REPEATED_IMAGES = "repeated_images"
    HYPHENATION = "hyphenation"
    FLATTENED_BLOCKS = "flattened_blocks"
    LLM_OCR_MARKERS = "llm_ocr_markers"
    LOST_PAGES = "lost_pages"
    MATH_SPAN_DRIFT = "math_span_drift"
    RUNAWAY_MATH = "runaway_math"
    GREEK_UNITS = "greek_units"
    INSPECTION_COVERAGE = "inspection_coverage"


# The check that grades each kind of cleaning finding. Absent: a broken table
# and a missing image link, which `tables` and `images` read off the body with
# the same detector, and a letter-spaced run, which a list of designations
# resembles.
_FINDING_CHECKS = {
    "broken-formula": CheckId.LOST_FORMULAS,
    "hyphenation": CheckId.HYPHENATION,
    "hyphenation-gap": CheckId.HYPHENATION,
    # A heading run into the next line is the same damage as a crushed block.
    "flattened-block": CheckId.FLATTENED_BLOCKS,
    "flattened-paragraphs": CheckId.FLATTENED_BLOCKS,
    "run-in-heading": CheckId.FLATTENED_BLOCKS,
}

# Unfinished repair work, summed for the recognition-failure hint. Lost
# formulas are a final loss, not among them.
_REPORTED_DEFECT_CHECKS = (
    (CheckId.HYPHENATION, "words split across a break"),
    (CheckId.FLATTENED_BLOCKS, "blocks crushed out of shape"),
)


@dataclass(frozen=True)
class Defect:
    """One fired check, with a short detail for the log.

    A `minor` defect is reported but does not make the result `bad`.
    """

    check: CheckId
    detail: str
    minor: bool = False


def _scaled_threshold(
    floor: float, rate_per_1000_lines: float, body_lines: int
) -> float:
    """Scale a size-dependent threshold, floored at its small-file value."""
    return max(floor, rate_per_1000_lines * body_lines / 1000)


def _within_threshold(
    count: int, floor: float, rate_per_1000_lines: float, body_lines: int
) -> bool:
    """True when a fired check's count stays inside its size-scaled threshold."""
    return count <= _scaled_threshold(floor, rate_per_1000_lines, body_lines)


@dataclass(frozen=True)
class Evaluation:
    """Outcome of a quality evaluation.

    `metrics` are never written to the final header. The two hints are
    independent and ignore the verdict. `defects` include minor ones, so an
    `ok` result can carry defects.
    """

    status: ResultStatus
    defects: tuple[Defect, ...]
    repairable: bool
    recognition_failure: bool
    metrics: dict[str, float]

    @property
    def issues(self) -> tuple[str, ...]:
        """`CheckId` values of the fired defects, minor included, in evaluator order."""
        return tuple(defect.check.value for defect in self.defects)

    @property
    def defect_report(self) -> tuple[str, ...]:
        """`check (detail)` per fired defect, in evaluator order, for the log."""
        return tuple(
            f"{defect.check.value} ({defect.detail})" for defect in self.defects
        )


@dataclass(frozen=True)
class _Body:
    """The body as every group of checks reads it.

    `findings` counts the cleaning findings under the check that grades them;
    `finding_lines` is the size of the body they were measured on, not this
    one.
    """

    text: str
    structural: list[Segment]
    plain_text: str
    lines: int
    findings: Counter[CheckId]
    finding_lines: int


@dataclass(frozen=True)
class _GroupResult:
    """The defects and metrics of one group of checks, in the order they ran.

    Each group sets its own share of the two hints; `evaluate` joins them.
    """

    defects: tuple[Defect, ...] = ()
    metrics: dict[str, float] = field(default_factory=dict)
    repairable: bool = False
    recognition_failure: bool = False


def evaluate(  # noqa: PLR0913 -- each optional keyword input switches on its own check group
    body: str,
    *,
    source_pages: int | None = None,
    base_dir: Path | None = None,
    source_text: SourceText | None = None,
    source_outline: SourceOutline | None = None,
    math_spans_before: int | None = None,
    cleaning_findings: Sequence[Finding] = (),
    cleaning_body_lines: int | None = None,
    inspection_chunks: int | None = None,
    inspection_chunks_done: int | None = None,
    keywords: Keywords | None = None,
) -> Evaluation:
    """Run the quality checks over `body` and decide `ok`/`bad`.

    A check whose input is omitted is skipped. `source_pages` feeds density,
    `base_dir` the image checks, `source_text` the coverage metric.
    `source_outline` outranks the body's own ranks in the flat-ladder check.
    `math_spans_before` is the count before the LLM steps, for the drift
    check. `cleaning_findings` feed the lost-formula, hyphenation, and
    flattened-block checks, weighed against `cleaning_body_lines`, the size of
    the body they were measured on. Re-evaluations pass the same
    `inspection_chunks` pair, so lost coverage keeps deciding.
    """
    structural = segments(body)
    lines = len(structural)
    view = _Body(
        text=body,
        structural=structural,
        plain_text="\n".join(line for line, prot in structural if not prot),
        lines=lines,
        findings=_count_findings(cleaning_findings),
        # Without it, this is the cleaning-stage call, and the bodies are the same.
        finding_lines=lines if cleaning_body_lines is None else cleaning_body_lines,
    )
    # The order of the groups is the order of `issues` in the result header.
    groups = (
        _text_checks(view, source_pages),
        _math_checks(view, math_spans_before),
        _heading_checks(
            view, source_outline, default_keywords() if keywords is None else keywords
        ),
        _layout_checks(view),
        _media_checks(view, base_dir),
        _reported_checks(view),
        _llm_marker_checks(view, inspection_chunks, inspection_chunks_done),
        _coverage_metrics(view, source_text),
    )
    defects = tuple(defect for group in groups for defect in group.defects)
    metrics: dict[str, float] = {"body_lines": lines}
    for group in groups:
        metrics.update(group.metrics)
    status = (
        ResultStatus.BAD
        if any(not defect.minor for defect in defects)
        else ResultStatus.OK
    )
    return Evaluation(
        status=status,
        defects=defects,
        repairable=any(group.repairable for group in groups),
        recognition_failure=any(group.recognition_failure for group in groups),
        metrics=metrics,
    )


def _text_checks(body: _Body, source_pages: int | None) -> _GroupResult:
    """Density, an empty body, and unreadable letters.

    Each of them means recognition produced no usable text, so every defect
    here is a recognition failure and none is repairable.
    """
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    if source_pages:
        density = len(body.text) / source_pages
        metrics["density"] = round(density, 1)
        if density < _DENSITY_MIN_CHARS_PER_PAGE:
            defects.append(
                Defect(CheckId.TEXT_DENSITY, f"{density:.0f} chars per page")
            )

    alnum = sum(1 for ch in body.text if ch.isalnum())
    if alnum < _EMPTY_BODY_MIN_ALNUM:
        defects.append(Defect(CheckId.EMPTY_BODY, f"{alnum} alphanumeric chars"))

    stats = _letter_stats(body.text)
    if stats.total >= _UNREADABLE_MIN_LETTERS:
        metrics["unreadable_share"] = round(stats.other_share, 3)
        # Both signals mean unreadable text, so they share one defect.
        details: list[str] = []
        if stats.other_share > _UNREADABLE_MAX_OTHER_SHARE:
            details.append(f"{stats.other_share:.0%} non-Latin/Cyrillic")
        if _is_mojibake(stats):
            metrics["mojibake_share"] = round(stats.accented_share, 3)
            details.append(f"{stats.accented_share:.0%} accented Latin over Cyrillic")
        if details:
            defects.append(Defect(CheckId.UNREADABLE_CHARS, ", ".join(details)))

    return _GroupResult(tuple(defects), metrics, recognition_failure=bool(defects))


def _math_checks(body: _Body, math_spans_before: int | None) -> _GroupResult:
    """Invalid and lost formulas, span drift, runaway blocks, and Greek units.

    Only invalid formulas are repairable: a lost formula is a final loss, and
    post may not rebalance delimiters.
    """
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    invalid_formulas = _count_invalid_formulas(body.plain_text) + _count_formula_loops(
        body.structural
    )
    if invalid_formulas:
        metrics["invalid_formulas"] = invalid_formulas
        defects.append(
            Defect(
                CheckId.FORMULAS,
                f"{invalid_formulas} invalid",
                minor=_within_threshold(
                    invalid_formulas,
                    _FORMULA_BAD_COUNT,
                    _FORMULA_BAD_RATE_PER_1000_LINES,
                    body.lines,
                ),
            )
        )

    lost_formulas = body.findings[CheckId.LOST_FORMULAS]
    if lost_formulas:
        metrics["lost_formulas"] = lost_formulas
        defects.append(
            Defect(
                CheckId.LOST_FORMULAS,
                f"{lost_formulas} formulas lost",
                minor=_within_threshold(
                    lost_formulas,
                    _LOST_FORMULA_BAD_COUNT,
                    _LOST_FORMULA_BAD_RATE_PER_1000_LINES,
                    body.finding_lines,
                ),
            )
        )

    math_spans_now = _count_math_spans(body.plain_text, body.structural)
    metrics["math_spans"] = math_spans_now
    if math_spans_before is not None and math_spans_now != math_spans_before:
        defects.append(
            Defect(
                CheckId.MATH_SPAN_DRIFT,
                f"{math_spans_before} -> {math_spans_now} spans",
            )
        )

    runaway_math = _runaway_math_details(body.plain_text)
    if runaway_math:
        defects.append(Defect(CheckId.RUNAWAY_MATH, ", ".join(runaway_math)))

    greek_units = _count_greek_unit_suspects(body.structural)
    if greek_units:
        metrics["greek_units"] = greek_units
        defects.append(
            Defect(CheckId.GREEK_UNITS, f"{greek_units} greek LaTeX near integers")
        )

    formula_failure_threshold = _scaled_threshold(
        _FORMULA_FAILURE_COUNT, _FORMULA_FAILURE_RATE_PER_1000_LINES, body.lines
    )
    greek_unit_failure_threshold = _scaled_threshold(
        _GREEK_UNIT_FAILURE_COUNT, _GREEK_UNIT_FAILURE_RATE_PER_1000_LINES, body.lines
    )
    return _GroupResult(
        tuple(defects),
        metrics,
        repairable=invalid_formulas > 0,
        recognition_failure=(
            invalid_formulas > formula_failure_threshold
            # This many means the script is mismapped wholesale.
            or greek_units > greek_unit_failure_threshold
        ),
    )


def _heading_checks(
    body: _Body, source_outline: SourceOutline | None, keywords: Keywords
) -> _GroupResult:
    """Heading jumps, the ladder, a flattened ladder, and lost chapters.

    Only jumps and a missing space are repairable: post's heading route never
    opens on a flat ladder, and no LLM step writes a missing heading.
    """
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    heading_issues = count_heading_issues(body.structural)
    if heading_issues:
        metrics["heading_issues"] = heading_issues
        defects.append(
            Defect(
                CheckId.HEADINGS,
                f"{heading_issues} level/space issues",
                minor=_within_threshold(
                    heading_issues,
                    _HEADING_BAD_COUNT,
                    _HEADING_BAD_RATE_PER_1000_LINES,
                    body.lines,
                ),
            )
        )

    ladder_issues = count_ladder_issues(body.structural)
    if ladder_issues:
        metrics["heading_ladder_issues"] = ladder_issues
        defects.append(
            Defect(
                CheckId.HEADING_LADDER,
                f"{ladder_issues} headings off their group's level",
                minor=True,
            )
        )

    flat_ladder = count_flat_ladder(body.structural, source_outline, keywords)
    if flat_ladder:
        metrics["flat_ladder_headings"] = flat_ladder
        defects.append(
            Defect(
                CheckId.FLAT_LADDER,
                f"{flat_ladder} headings merged onto one level",
                minor=_within_threshold(
                    flat_ladder,
                    _FLAT_LADDER_BAD_COUNT,
                    _FLAT_LADDER_BAD_RATE_PER_1000_LINES,
                    body.lines,
                ),
            )
        )

    stated_chapters, lost_chapters = count_lost_chapters(body.structural, keywords)
    if lost_chapters:
        metrics["lost_chapters"] = lost_chapters
        defects.append(
            Defect(
                CheckId.LOST_CHAPTERS,
                f"{lost_chapters} of {stated_chapters} stated chapters unwritten",
                minor=lost_chapters <= _lost_chapter_threshold(stated_chapters),
            )
        )

    return _GroupResult(tuple(defects), metrics, repairable=heading_issues > 0)


def _layout_checks(body: _Body) -> _GroupResult:
    """Broken tables, junk lines, and repeated lines; all of them repairable."""
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    # The cleaner's own reading: a grid collapsed into one cell keeps its width.
    broken_rows = len(broken_table_details(body.structural))
    if broken_rows:
        metrics["broken_tables"] = broken_rows
        defects.append(
            Defect(
                CheckId.TABLES,
                f"{broken_rows} broken rows",
                minor=_within_threshold(
                    broken_rows,
                    _TABLE_BAD_COUNT,
                    _TABLE_BAD_RATE_PER_1000_LINES,
                    body.lines,
                ),
            )
        )

    junk_share = _junk_share(body.structural)
    if junk_share > _JUNK_REPAIRABLE_SHARE:
        metrics["junk_share"] = round(junk_share, 3)
        defects.append(Defect(CheckId.JUNK_LINES, f"{junk_share:.0%} junk lines"))

    repeat_min_count = _scaled_threshold(
        _REPEAT_MIN_COUNT, _REPEAT_MIN_RATE_PER_1000_LINES, body.lines
    )
    repeat_counts = _repeat_counts(body.structural, repeat_min_count)
    repeats = len(repeat_counts)
    if repeats:
        metrics["repeats"] = repeats
        runaway = max(repeat_counts) > repeat_min_count * _REPEAT_LOOP_MULTIPLE
        defects.append(
            Defect(
                CheckId.REPEATS,
                f"{repeats} repeated lines",
                minor=not runaway
                and _within_threshold(
                    repeats,
                    _REPEAT_BAD_COUNT,
                    _REPEAT_BAD_RATE_PER_1000_LINES,
                    body.lines,
                ),
            )
        )

    return _GroupResult(
        tuple(defects),
        metrics,
        repairable=(
            broken_rows > 0 or junk_share > _JUNK_REPAIRABLE_SHARE or repeats > 0
        ),
        recognition_failure=junk_share > _JUNK_FAILURE_SHARE,
    )


def _media_checks(body: _Body, base_dir: Path | None) -> _GroupResult:
    """Defective and repeated images; only a missing link is repairable."""
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    missing_images, bad_images = _count_bad_images(body.structural, base_dir)
    if bad_images:
        metrics["bad_images"] = bad_images
        defects.append(Defect(CheckId.IMAGES, f"{bad_images} defective images"))

    repeated_images = _count_repeated_images(body.structural)
    if repeated_images:
        metrics["repeated_images"] = repeated_images
        # Always minor: a running logo after the xref dedup looks the same.
        defects.append(
            Defect(
                CheckId.REPEATED_IMAGES,
                f"{repeated_images} paths reused 3+ times",
                minor=True,
            )
        )

    return _GroupResult(tuple(defects), metrics, repairable=missing_images > 0)


def _reported_checks(body: _Body) -> _GroupResult:
    """The defects cleaning reported and left standing, each on its own count.

    The failure hint sums them: it asks about recognition as a whole.
    """
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    reported_defects = 0
    # Fixed order, whatever order the report lists its findings in.
    for check, detail in _REPORTED_DEFECT_CHECKS:
        count = body.findings[check]
        if not count:
            continue
        reported_defects += count
        metrics[check.value] = count
        defects.append(
            Defect(
                check,
                f"{count} {detail}",
                minor=_within_threshold(
                    count,
                    _REPORTED_BAD_COUNT,
                    _REPORTED_BAD_RATE_PER_1000_LINES,
                    body.finding_lines,
                ),
            )
        )

    finding_failure_threshold = _scaled_threshold(
        _REPORTED_FAILURE_COUNT,
        _REPORTED_FAILURE_RATE_PER_1000_LINES,
        body.finding_lines,
    )
    return _GroupResult(
        tuple(defects),
        metrics,
        repairable=reported_defects > 0,
        recognition_failure=reported_defects > finding_failure_threshold,
    )


def _llm_marker_checks(
    body: _Body, inspection_chunks: int | None, inspection_chunks_done: int | None
) -> _GroupResult:
    """What the LLM steps left behind: OCR markers, lost pages, lost chunks.

    A lost page is a recognition failure: only recognizing the page again
    recovers it.
    """
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    ocr_markers = _count_ocr_markers(body.text)
    if ocr_markers:
        metrics["ocr_markers"] = ocr_markers
        defects.append(Defect(CheckId.LLM_OCR_MARKERS, f"{ocr_markers} OCR markers"))

    lost_pages = _count_lost_pages(body.structural)
    if lost_pages:
        metrics["lost_pages"] = lost_pages
        defects.append(Defect(CheckId.LOST_PAGES, f"{lost_pages} pages not recognized"))

    if inspection_chunks and inspection_chunks_done is not None:
        inspection_coverage = inspection_chunks_done / inspection_chunks
        metrics["inspection_coverage"] = round(inspection_coverage, 3)
        if inspection_chunks_done < inspection_chunks:
            defects.append(
                Defect(
                    CheckId.INSPECTION_COVERAGE,
                    f"{inspection_chunks_done} of {inspection_chunks} chunks inspected",
                    minor=inspection_coverage >= _INSPECTION_COVERAGE_BAD_SHARE,
                )
            )

    return _GroupResult(tuple(defects), metrics, recognition_failure=lost_pages > 0)


def _coverage_metrics(body: _Body, source_text: SourceText | None) -> _GroupResult:
    """The source coverage metric; it fires no defect and no hint."""
    if source_text is None:
        return _GroupResult()
    coverage = _source_coverage(body.text, source_text)
    if coverage is None:
        return _GroupResult()
    result_coverage, source_coverage = coverage
    _logger.info(
        "source coverage: %.0f%% of result attested by source, "
        "%.0f%% of source reached the result",
        result_coverage * 100,
        source_coverage * 100,
    )
    return _GroupResult(
        metrics={
            "result_coverage": round(result_coverage, 3),
            "source_coverage": round(source_coverage, 3),
        }
    )


@dataclass(frozen=True)
class _LetterStats:
    """Letter composition of a body, as shares of its total letter count.

    `other_share` is the OCR-garbage signal (neither Latin nor Cyrillic);
    `accented_share` and `cyrillic_share` together are the mojibake signal.
    """

    total: int
    other_share: float
    accented_share: float
    cyrillic_share: float


def _letter_stats(body: str) -> _LetterStats:
    """Classify the letters of `body` in a single pass."""
    total = 0
    other = 0
    accented = 0
    cyrillic = 0
    for ch in body:
        if not ch.isalpha():
            continue
        total += 1
        name = unicodedata.name(ch, "")
        if name.startswith("CYRILLIC"):
            cyrillic += 1
        elif name.startswith("LATIN"):
            # A decomposition means a diacritic.
            if unicodedata.decomposition(ch):
                accented += 1
        else:
            other += 1
    if total == 0:
        return _LetterStats(0, 0.0, 0.0, 0.0)
    return _LetterStats(total, other / total, accented / total, cyrillic / total)


def _is_mojibake(stats: _LetterStats) -> bool:
    """True when the letters look like a Cyrillic text decoded as Latin.

    A cp1251 font without a ToUnicode table yields accented Latin letters,
    which `other_share` cannot see: such garbage runs above 50% accented,
    real German or French near 2%. The Cyrillic guard keeps accented Latin
    documents out; the share is over all letters.
    """
    return (
        stats.cyrillic_share >= _MOJIBAKE_MIN_CYRILLIC_SHARE
        and stats.accented_share > _MOJIBAKE_MAX_ACCENTED_SHARE
    )


def _closed_math_span_contents(text: str) -> list[str]:
    """The content of every closed `$$...$$` / `$...$` pair in `text`, in order.

    Display spans go first and are removed, so inline spans cannot straddle
    them. A lone `$` (currency) is never among them.
    """
    contents: list[str] = []
    leftover: list[str] = []
    last = 0
    for match in _DISPLAY_MATH_RE.finditer(text):
        contents.append(match.group(1))
        leftover.append(text[last : match.start()])
        last = match.end()
    leftover.append(text[last:])
    contents.extend(m.group(1) for m in _INLINE_MATH_RE.finditer("".join(leftover)))
    return contents


def _count_invalid_formulas(text: str) -> int:
    """Count syntactically invalid math spans in `text`."""
    return sum(
        1 for content in _closed_math_span_contents(text) if not is_valid_math(content)
    )


def _count_math_spans(text: str, structural: list[Segment]) -> int:
    """Count math spans in `text`, including a damaged one missing its closer.

    Closed pairs count over the whole document, so line wrapping does not
    change the count. An unclosed tail (the closer degenerated into a stray
    backslash) counts per line, as the edit guard reads it: over the whole
    document a stray `$` would pair with a far backslash. An LLM step may
    close such a tail, which must not read as a new span. Known residual: a
    `$` and a later backslash on one line (a Windows path) read as a span.
    """
    closed = len(_closed_math_span_contents(text))
    tails = sum(
        len(math_span_ranges(line)) - len(_closed_math_span_contents(line))
        for line, protected in structural
        if not protected
    )
    return closed + tails


def _runaway_math_details(plain_text: str) -> list[str]:
    """Details of the runaway-math check on `plain_text`; empty when it is sound.

    An unclosed display delimiter turns everything up to the next formula into
    one math block. Signals: an odd delimiter count, a block holding document
    structure, a block past the size caps (not counted twice). Read over the
    inline-code mask: a quoted `$$` would shift every later pairing. No hint:
    post may not rebalance delimiters.
    """
    masked = mask_inline_code(plain_text)
    details: list[str] = []
    delimiters = _count_display_delimiters(masked)
    if delimiters % 2:
        details.append(f"{delimiters} display delimiters, one unpaired")
    over_structure = 0
    oversize = 0
    for match in _DISPLAY_MATH_RE.finditer(masked):
        content = match.group(1)
        if _holds_document_structure(content):
            over_structure += 1
        elif _is_oversize_math_block(content):
            oversize += 1
    if over_structure:
        details.append(f"{over_structure} display blocks over document structure")
    if oversize:
        details.append(f"{oversize} display blocks past the size cap")
    return details


def _count_display_delimiters(text: str) -> int:
    """Count the `$$` display delimiters of `text`.

    A run glued between alphanumerics (`a$$b`) is two inline delimiters. A
    longer run is ambiguous and not counted.
    """
    count = 0
    for match in _DOLLAR_RUN_RE.finditer(text):
        if match.end() - match.start() != 2:
            continue
        before = text[match.start() - 1] if match.start() else ""
        after = text[match.end()] if match.end() < len(text) else ""
        if before.isalnum() and after.isalnum():
            continue
        count += 1
    return count


def _holds_document_structure(content: str) -> bool:
    """True when a display block holds a heading, an image, or a table separator."""
    for line in content.split("\n"):
        if HEADING_RE.match(line):
            return True
        if IMAGE_RE.search(line) or HTML_IMG_RE.search(line):
            return True
        if is_table_separator(line.strip()):
            return True
    return False


def _is_oversize_math_block(content: str) -> bool:
    """True when a display block is longer than any formula plausibly is."""
    return (
        len(content) > _MATH_BLOCK_MAX_CHARS
        or content.count("\n") + 1 > _MATH_BLOCK_MAX_LINES
    )


def _count_greek_unit_suspects(structural: list[Segment]) -> int:
    """Count math spans that are just an integer glued to Greek commands.

    Only on lines with Cyrillic prose outside the span. Not a cleaner rule:
    the reverse mapping (`\\kappa\\Gamma` to `кГ`) has no safe table, so it is
    a signal for inspection. Read over the inline-code mask.
    """
    count = 0
    for line, protected in structural:
        if protected:
            continue
        masked = mask_inline_code(line)
        for start, end in math_span_ranges(masked):
            span = masked[start:end]
            if not (span.startswith("$") and span.endswith("$")):
                # An unclosed tail is not this shape.
                continue
            delims = 2 if span.startswith("$$") else 1
            content = span[delims : len(span) - delims].strip()
            match = _GREEK_UNIT_SPAN_RE.match(content)
            if match is None or match.group(1) in _LEGITIMATE_GREEK_UNIT_COMBOS:
                continue
            rest = masked[:start] + masked[end:]
            if any(
                unicodedata.name(ch, "").startswith("CYRILLIC")
                for ch in rest
                if ch.isalpha()
            ):
                count += 1
    return count


def _count_formula_loops(structural: list[Segment]) -> int:
    """Count plain lines whose math span degenerated into a repetition loop.

    Truncation often leaves the closing `$` looking escaped, so
    `_count_invalid_formulas` never sees the span. The cleaner trims the loops
    it finds, so this counts loops an LLM step wrote or a body graded outside
    the pipeline.
    """
    return sum(
        1
        for line, protected in structural
        if not protected and math_repetition_loop(line)
    )


def _lost_chapter_threshold(stated_chapters: int) -> Fraction:
    """How many chapters may go unwritten before the loss decides the status."""
    return max(
        Fraction(_LOST_CHAPTER_BAD_COUNT), _LOST_CHAPTER_BAD_SHARE * stated_chapters
    )


def _junk_share(structural: list[Segment]) -> float:
    """Share of plain non-blank lines made only of service symbols.

    Structural symbol lines and setext underlines are excluded, as the cleaner
    keeps them; the previous line is tracked as the cleaner tracks it.
    """
    total = 0
    junk = 0
    prev = ""
    for line, protected in structural:
        if protected:
            prev = line
            continue
        core = line.strip()
        if not core:
            prev = line
            continue
        total += 1
        if (
            not any(ch.isalnum() for ch in core)
            and not is_structural_symbol_line(core)
            and not is_setext_underline(core, prev)
        ):
            junk += 1
        prev = line
    return junk / total if total else 0.0


def _repeat_counts(structural: list[Segment], min_count: float) -> list[int]:
    """Occurrence counts of the short lines repeating `min_count` times or more.

    Excluded as repeating by design: HTML image wrappers, math-only lines (an
    axis label under each plot), headings, a single short connective word
    between formulas, and table rows. So is a line whose occurrences spread
    evenly, like a template field per product card.
    """
    positions: dict[str, list[int]] = {}
    for index, (line, protected) in enumerate(structural):
        if protected:
            continue
        core = line.strip()
        if not core or len(core) > _REPEAT_MAX_LEN:
            continue
        if not any(ch.isalnum() for ch in core):
            continue
        words = core.split()
        if (
            is_html_media_wrapper_line(core)
            or is_math_only_line(core)
            or HEADING_RE.match(line)
            or (len(words) == 1 and len(core) <= _REPEAT_CONNECTOR_MAX_LEN)
            or has_cell_separator(core)
        ):
            continue
        positions.setdefault(core, []).append(index)
    return [
        len(occurrences)
        for occurrences in positions.values()
        if len(occurrences) >= min_count and _repeats_in_a_cluster(occurrences)
    ]


def _repeats_in_a_cluster(occurrences: list[int]) -> bool:
    """True when the median gap between occurrences reads as a loop.

    The repeat minimum is at least 3, so there is always a gap to weigh.
    """
    gaps = [later - earlier for earlier, later in pairwise(occurrences)]
    return statistics.median(gaps) <= _REPEAT_MAX_MEDIAN_GAP


def _count_bad_images(
    structural: list[Segment], base_dir: Path | None
) -> tuple[int, int]:
    """Return ``(missing_links, defective_total)`` for local image links.

    Defective: missing, under 512 bytes, or single-color. Only a missing link
    is repairable. Markdown and HTML links both count.
    """
    if base_dir is None:
        return 0, 0
    missing = 0
    defective = 0
    for line, protected in structural:
        if protected:
            continue
        targets = [m.group(2) for m in IMAGE_RE.finditer(line)]
        targets += [m.group(2) for m in HTML_IMG_RE.finditer(line)]
        for target in targets:
            if not is_local_target(target):
                continue
            path = local_image_path(base_dir, target)
            if path is None:
                # Escapes base_dir once decoded; not ours to check.
                continue
            if not path.exists():
                missing += 1
                defective += 1
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size < _IMAGE_MIN_BYTES or _is_single_color(path):
                defective += 1
    return missing, defective


def _is_single_color(path: Path) -> bool:
    """True when every pixel of the image at `path` is the same color.

    An undecodable file is not judged single-color.
    """
    try:
        with Image.open(path) as img:
            # None once the color count exceeds maxcolors.
            colors = img.convert("RGB").getcolors(maxcolors=1)
    except (OSError, ValueError):
        return False
    return colors is not None


def _count_repeated_images(structural: list[Segment]) -> int:
    """Count distinct local image paths linked 3 or more times across the body.

    A signal only: after the xref dedup a running logo is one path linked from
    every page.
    """
    counts: dict[str, int] = {}
    for line, protected in structural:
        if protected:
            continue
        targets = [m.group(2) for m in IMAGE_RE.finditer(line)]
        targets += [m.group(2) for m in HTML_IMG_RE.finditer(line)]
        for target in targets:
            if not is_local_target(target):
                continue
            counts[target] = counts.get(target, 0) + 1
    return sum(1 for count in counts.values() if count >= _REPEATED_IMAGE_MIN_COUNT)


def _count_findings(findings: Sequence[Finding]) -> Counter[CheckId]:
    """Count the cleaning findings under the check that grades each kind."""
    return Counter(
        check
        for finding in findings
        if (check := _FINDING_CHECKS.get(finding.kind)) is not None
    )


def _count_ocr_markers(body: str) -> int:
    """Count LLM-OCR uncertainty markers inserted into `body`."""
    return sum(body.count(marker) for marker in _OCR_MARKERS)


def _strip_media_targets(text: str) -> str:
    """Drop image links before tokenizing, keeping a markdown image's alt text.

    Paths and attributes are pipeline output and would lower
    `result_coverage`; alt text is often the page's caption.
    """
    text = IMAGE_RE.sub(lambda m: m.group(1), text)
    return _HTML_IMG_TAG_RE.sub("", text)


def _source_coverage(body: str, source_text: SourceText) -> tuple[float, float] | None:
    """Return ``(result_coverage, source_coverage)`` against `source_text`.

    Each is the share of one side's token occurrences whose word occurs
    anywhere on the other side; there is no page alignment. Markdown syntax
    never tokenizes. None when either side has no tokens.
    """
    if not source_text.has_layer:
        return None
    result_tokens = Counter(tokenize(_strip_media_targets(body)))
    if not result_tokens:
        return None
    source_tokens: Counter[str] = Counter()
    for page in source_text.pages:
        source_tokens.update(tokenize(page))
    if not source_tokens:
        return None
    source_words = source_tokens.keys()
    result_words = result_tokens.keys()
    result_matched = sum(n for word, n in result_tokens.items() if word in source_words)
    source_matched = sum(n for word, n in source_tokens.items() if word in result_words)
    return (
        result_matched / result_tokens.total(),
        source_matched / source_tokens.total(),
    )


def _count_lost_pages(structural: list[Segment]) -> int:
    """Count pages LLM OCR marked as not recognized, outside protected zones."""
    return sum(
        1
        for line, protected in structural
        if not protected and is_lost_page_marker(line)
    )
