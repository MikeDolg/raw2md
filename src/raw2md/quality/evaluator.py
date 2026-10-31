"""Quality evaluation: deterministic checks that score a body as ok or bad.

The evaluator never changes content. It returns an `Evaluation`: the total
score, the status, the defects that fired, and two log hints, `repairable`
and `recognition_failure`.

A graded check scores `100 * 2^(-x/h)`: `x` is its defect rate past a floor,
`h` the rate that halves the score. The total is the product of the check
scores, `100 * 2^(-sum(w * x/h))`, and the status is `ok` at `ok_score` or
above. A veto, a defect that no rate describes, sets the total to 0.
Repeated images and an inconsistent heading ladder are signals with no
score: a legitimate document shows those shapes too.

Structural checks read the final body; a lost formula, a split word, and a
crushed block leave no trace there, so they come from the cleaning report.
The order of the check groups, and of the checks in each, is that of `issues`.
"""

from __future__ import annotations

import logging
import re
import statistics
import unicodedata
from bisect import bisect_right
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
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
    count_headings,
    count_ladder_issues,
    flat_ladder_positions,
    heading_issue_positions,
    lost_chapter_entries,
)
from raw2md.source_outline import SourceOutline
from raw2md.source_text import SourceText, tokenize

_logger = logging.getLogger("raw2md")

# The status default: a single graded check at its halving rate stays `ok`.
DEFAULT_OK_SCORE = 50

# A check scoring below this, or a veto, is listed in `issues`.
_ISSUE_MAX_SCORE = 50

# A veto bound, a hint bound, or a defect share that halves the score. A
# failure share escalates to a likely recognition failure.
_DENSITY_MIN_CHARS_PER_PAGE = 350
_EMPTY_BODY_MIN_ALNUM = 20
_UNREADABLE_MIN_LETTERS = 200
_UNREADABLE_HALVING_SHARE = 0.15
_MOJIBAKE_MAX_ACCENTED_SHARE = 0.15
_MOJIBAKE_MIN_CYRILLIC_SHARE = 0.05
_JUNK_HALVING_SHARE = 0.02
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
# chunks answered it is a veto. Not size-scaled: it is already a share of the
# plan.
_INSPECTION_HALVING_SHARE = 0.5
_INSPECTION_VETO_DONE_SHARE = 0.5

# The excess past the floor that halves a check's score, as a floor plus a rate
# per 1000 body lines. Calibrated on scans: a nearly clean book had 3 heading
# jumps over 1500 lines, a damaged one 32 over 7900. Headings forgive one
# defect: on a short body the threshold is under one, and one jump would score
# near 0. The flat ladder, repeats, and tables have no floor. Formulas and lost
# formulas keep a floor of 2, half the escalation pair. The report-only checks
# run at twice that rate: unfinished repair work, not a proven loss. Tables
# were calibrated on broken-row rates of 0 to 22 per 1000 lines.
_HEADING_FLOOR = 1
_HEADING_HALVING_RATE_PER_1000_LINES = 2
_FLAT_LADDER_FLOOR = 0
_FLAT_LADDER_HALVING_RATE_PER_1000_LINES = 2
_REPEAT_FLOOR = 0
_REPEAT_HALVING_RATE_PER_1000_LINES = 1
_FORMULA_FLOOR = 2
_FORMULA_HALVING_RATE_PER_1000_LINES = 1
_LOST_FORMULA_FLOOR = 2
_LOST_FORMULA_HALVING_RATE_PER_1000_LINES = 1
_TABLE_FLOOR = 0
_TABLE_HALVING_RATE_PER_1000_LINES = 1
_REPORTED_FLOOR = 2
_REPORTED_HALVING_RATE_PER_1000_LINES = 2

# Bad images, Greek units, and OCR markers have no floor and no size scale:
# each defect halves the score.
_ONE_DEFECT = 1

# Weighed against the contents, not the body size. A quarter lost is the top
# rank gone; the floor keeps out a single title misread by a typo.
_LOST_CHAPTER_HALVING_SHARE = Fraction(1, 4)
_LOST_CHAPTER_FLOOR = 1

# A line repeating past this multiple of the minimum is a veto: a
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


# The graded checks weigh the same until a calibration against per-document
# scores sets them apart.
_CHECK_WEIGHTS = {
    CheckId.UNREADABLE_CHARS: 1.0,
    CheckId.FORMULAS: 1.0,
    CheckId.LOST_FORMULAS: 1.0,
    CheckId.GREEK_UNITS: 1.0,
    CheckId.HEADINGS: 1.0,
    CheckId.FLAT_LADDER: 1.0,
    CheckId.LOST_CHAPTERS: 1.0,
    CheckId.TABLES: 1.0,
    CheckId.JUNK_LINES: 1.0,
    CheckId.REPEATS: 1.0,
    CheckId.IMAGES: 1.0,
    CheckId.HYPHENATION: 1.0,
    CheckId.FLATTENED_BLOCKS: 1.0,
    CheckId.LLM_OCR_MARKERS: 1.0,
    CheckId.INSPECTION_COVERAGE: 1.0,
}


def _score(halvings: float) -> int:
    """The score `100 * 2^(-halvings)`, rounded to an integer from 0 to 100."""
    return round(100 * 2**-halvings)


@dataclass(frozen=True)
class Defect:
    """One fired check: a short detail for the log and its grade.

    `halvings` is `x/h`; each one halves the score. A veto scores 0 and sets
    the total to 0. A signal and a count within its floor carry no halvings.
    `places` counts where the defect can occur and `share` is `x` over them,
    for the log only; a veto-only check and a signal leave both None.
    `lines` are the body lines, counted from 1, where a check that reads the
    body found the defect; `entries` name what a check found missing, where
    no line holds it.
    """

    check: CheckId
    detail: str
    halvings: float = 0.0
    veto: bool = False
    places: int | None = None
    share: float | None = None
    lines: tuple[int, ...] = ()
    entries: tuple[str, ...] = ()

    @property
    def score(self) -> int:
        """The check score, an integer from 0 to 100."""
        return 0 if self.veto else _score(self.halvings)


def _scaled_threshold(
    floor: float, rate_per_1000_lines: float, body_lines: int
) -> float:
    """Scale a size-dependent threshold, floored at its small-file value."""
    return max(floor, rate_per_1000_lines * body_lines / 1000)


def _counted_defect(
    check: CheckId,
    detail: str,
    count: int,
    floor: float,
    threshold: float,
    places: int,
    *,
    lines: Sequence[int] = (),
    entries: Sequence[str] = (),
) -> Defect:
    """A count check's defect: `count` past `floor`, weighed against `threshold`.

    The threshold `T` is the excess that halves the score, so `x/h` is
    `excess / T`, and the number of places cancels out of the score. `T` is
    positive whenever a defect is counted: a body that holds one has a line.
    """
    excess = max(0.0, count - floor)
    return Defect(
        check,
        detail,
        halvings=excess / threshold if excess else 0.0,
        places=places,
        share=excess / places if places else None,
        lines=_body_lines(lines),
        entries=tuple(entries),
    )


def _body_lines(positions: Sequence[int]) -> tuple[int, ...]:
    """Body line numbers, from 1, of segment positions, from 0."""
    return tuple(position + 1 for position in positions)


@dataclass(frozen=True)
class Evaluation:
    """Outcome of a quality evaluation.

    `metrics` are never written to the final header. The two hints are
    independent and ignore the verdict. `defects` include every fired check,
    so an `ok` result can carry defects.
    """

    status: ResultStatus
    score: int
    defects: tuple[Defect, ...]
    repairable: bool
    recognition_failure: bool
    metrics: dict[str, float]

    @property
    def issues(self) -> tuple[str, ...]:
        """`CheckId` values of the vetoes and the checks below 50, in order."""
        return tuple(
            defect.check.value
            for defect in self.defects
            if defect.veto or defect.score < _ISSUE_MAX_SCORE
        )

    @property
    def scored_report(self) -> tuple[str, ...]:
        """`check (detail) score N` for the checks behind a `bad` verdict.

        The vetoes and the checks below 50 come first. A total under `ok_score`
        with no such check lists every check that lost a point.
        """
        issues = [
            defect
            for defect in self.defects
            if defect.veto or defect.score < _ISSUE_MAX_SCORE
        ]
        shown = issues or [defect for defect in self.defects if defect.halvings > 0]
        return tuple(
            f"{defect.check.value} ({defect.detail}) score {defect.score}"
            for defect in shown
        )

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
    one. `plain_positions` maps a line of `plain_text` to its segment position.
    """

    text: str
    structural: list[Segment]
    plain_text: str
    plain_positions: list[int]
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
    ok_score: int = DEFAULT_OK_SCORE,
) -> Evaluation:
    """Run the quality checks over `body`, score it, and decide `ok`/`bad`.

    The status is `ok` when no veto fired and the rounded total reaches
    `ok_score`. A check whose input is omitted is skipped. `source_pages`
    feeds density, `base_dir` the image checks, `source_text` the coverage
    metric.
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
        plain_positions=[
            position for position, (_, prot) in enumerate(structural) if not prot
        ],
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
    score = _total_score(defects)
    # A veto stays `bad` even at an `ok_score` of 0.
    vetoed = any(defect.veto for defect in defects)
    status = ResultStatus.BAD if vetoed or score < ok_score else ResultStatus.OK
    return Evaluation(
        status=status,
        score=score,
        defects=defects,
        repairable=any(group.repairable for group in groups),
        recognition_failure=any(group.recognition_failure for group in groups),
        metrics=metrics,
    )


def _total_score(defects: Sequence[Defect]) -> int:
    """The total, `100 * 2^(-sum(w * x/h))`; any veto makes it 0."""
    if any(defect.veto for defect in defects):
        return 0
    return _score(
        sum(
            _CHECK_WEIGHTS[defect.check] * defect.halvings
            for defect in defects
            if defect.halvings
        )
    )


def _text_checks(body: _Body, source_pages: int | None) -> _GroupResult:
    """Density, an empty body, and unreadable text.

    Low density, an empty body, mojibake, and unreadable text past its halving
    share each mean that recognition produced no usable text: a recognition
    failure, never repairable.
    """
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    failure = False
    if source_pages:
        density = len(body.text) / source_pages
        metrics["density"] = round(density, 1)
        if density < _DENSITY_MIN_CHARS_PER_PAGE:
            failure = True
            defects.append(
                Defect(CheckId.TEXT_DENSITY, f"{density:.0f} chars per page", veto=True)
            )

    alnum = sum(1 for ch in body.text if ch.isalnum())
    if alnum < _EMPTY_BODY_MIN_ALNUM:
        failure = True
        defects.append(
            Defect(CheckId.EMPTY_BODY, f"{alnum} alphanumeric chars", veto=True)
        )

    stats = _letter_stats(body.text)
    if stats.sample >= _UNREADABLE_MIN_LETTERS:
        metrics["unreadable_share"] = round(stats.unreadable_share, 3)
        mojibake = _is_mojibake(stats)
        failure = (
            failure or mojibake or stats.unreadable_share > _UNREADABLE_HALVING_SHARE
        )
        # Both signals mean unreadable text, so they share one defect.
        details: list[str] = []
        if stats.unreadable_share:
            details.append(_unreadable_detail(stats))
        if mojibake:
            metrics["mojibake_share"] = round(stats.accented_share, 3)
            details.append(f"{stats.accented_share:.0%} accented Latin over Cyrillic")
        if details:
            share = stats.unreadable_share
            defects.append(
                Defect(
                    CheckId.UNREADABLE_CHARS,
                    ", ".join(details),
                    halvings=share / _UNREADABLE_HALVING_SHARE,
                    # Mojibake breaks the whole text, not a countable share.
                    veto=mojibake,
                    places=stats.sample,
                    share=share,
                )
            )

    return _GroupResult(tuple(defects), metrics, recognition_failure=failure)


def _math_checks(body: _Body, math_spans_before: int | None) -> _GroupResult:
    """Invalid and lost formulas, span drift, runaway blocks, and Greek units.

    Only invalid formulas are repairable: a lost formula is a final loss, and
    post may not rebalance delimiters.
    """
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    math_spans_now = _count_math_spans(body.plain_text, body.structural)
    invalid_positions = [
        _plain_position(body, offset)
        for offset in _invalid_formula_offsets(body.plain_text)
    ]
    invalid_positions += _formula_loop_positions(body.structural)
    invalid_formulas = len(invalid_positions)
    if invalid_formulas:
        metrics["invalid_formulas"] = invalid_formulas
        defects.append(
            _counted_defect(
                CheckId.FORMULAS,
                f"{invalid_formulas} invalid",
                invalid_formulas,
                _FORMULA_FLOOR,
                _scaled_threshold(
                    _FORMULA_FLOOR, _FORMULA_HALVING_RATE_PER_1000_LINES, body.lines
                ),
                math_spans_now,
                lines=invalid_positions,
            )
        )

    lost_formulas = body.findings[CheckId.LOST_FORMULAS]
    if lost_formulas:
        metrics["lost_formulas"] = lost_formulas
        defects.append(
            _counted_defect(
                CheckId.LOST_FORMULAS,
                f"{lost_formulas} formulas lost",
                lost_formulas,
                _LOST_FORMULA_FLOOR,
                _scaled_threshold(
                    _LOST_FORMULA_FLOOR,
                    _LOST_FORMULA_HALVING_RATE_PER_1000_LINES,
                    body.finding_lines,
                ),
                # The lost formulas are no longer in the body.
                math_spans_now + lost_formulas,
            )
        )

    metrics["math_spans"] = math_spans_now
    if math_spans_before is not None and math_spans_now != math_spans_before:
        defects.append(
            Defect(
                CheckId.MATH_SPAN_DRIFT,
                f"{math_spans_before} -> {math_spans_now} spans",
                veto=True,
            )
        )

    runaway_math, runaway_offsets = _runaway_math_details(body.plain_text)
    if runaway_math:
        defects.append(
            Defect(
                CheckId.RUNAWAY_MATH,
                ", ".join(runaway_math),
                veto=True,
                lines=_body_lines(
                    [_plain_position(body, offset) for offset in runaway_offsets]
                ),
            )
        )

    greek_positions = _greek_unit_positions(body.structural)
    greek_units = len(greek_positions)
    if greek_units:
        metrics["greek_units"] = greek_units
        defects.append(
            _counted_defect(
                CheckId.GREEK_UNITS,
                f"{greek_units} greek LaTeX near integers",
                greek_units,
                0,
                _ONE_DEFECT,
                math_spans_now,
                lines=greek_positions,
            )
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
    headings = count_headings(body.structural)
    heading_positions = heading_issue_positions(body.structural)
    heading_issues = len(heading_positions)
    if heading_issues:
        metrics["heading_issues"] = heading_issues
        defects.append(
            _counted_defect(
                CheckId.HEADINGS,
                f"{heading_issues} level/space issues",
                heading_issues,
                _HEADING_FLOOR,
                _scaled_threshold(
                    _HEADING_FLOOR, _HEADING_HALVING_RATE_PER_1000_LINES, body.lines
                ),
                headings,
                lines=heading_positions,
            )
        )

    ladder_issues = count_ladder_issues(body.structural)
    if ladder_issues:
        metrics["heading_ladder_issues"] = ladder_issues
        defects.append(
            Defect(
                CheckId.HEADING_LADDER,
                f"{ladder_issues} headings off their group's level",
            )
        )

    flat_positions = flat_ladder_positions(body.structural, source_outline, keywords)
    flat_ladder = len(flat_positions)
    if flat_ladder:
        metrics["flat_ladder_headings"] = flat_ladder
        defects.append(
            _counted_defect(
                CheckId.FLAT_LADDER,
                f"{flat_ladder} headings merged onto one level",
                flat_ladder,
                _FLAT_LADDER_FLOOR,
                _scaled_threshold(
                    _FLAT_LADDER_FLOOR,
                    _FLAT_LADDER_HALVING_RATE_PER_1000_LINES,
                    body.lines,
                ),
                headings,
                lines=flat_positions,
            )
        )

    stated_chapters, lost_entries = lost_chapter_entries(body.structural, keywords)
    lost_chapters = len(lost_entries)
    if lost_chapters:
        metrics["lost_chapters"] = lost_chapters
        defects.append(
            _counted_defect(
                CheckId.LOST_CHAPTERS,
                f"{lost_chapters} of {stated_chapters} stated chapters unwritten",
                lost_chapters,
                _LOST_CHAPTER_FLOOR,
                float(
                    max(
                        Fraction(_LOST_CHAPTER_FLOOR),
                        _LOST_CHAPTER_HALVING_SHARE * stated_chapters,
                    )
                ),
                stated_chapters,
                entries=lost_entries,
            )
        )

    return _GroupResult(tuple(defects), metrics, repairable=heading_issues > 0)


def _layout_checks(body: _Body) -> _GroupResult:
    """Broken tables, junk lines, and repeated lines; all of them repairable."""
    defects: list[Defect] = []
    metrics: dict[str, float] = {}
    # The cleaner's own reading: a grid collapsed into one cell keeps its width.
    broken_positions = sorted(broken_table_details(body.structural))
    broken_rows = len(broken_positions)
    if broken_rows:
        metrics["broken_tables"] = broken_rows
        defects.append(
            _counted_defect(
                CheckId.TABLES,
                f"{broken_rows} broken rows",
                broken_rows,
                _TABLE_FLOOR,
                _scaled_threshold(
                    _TABLE_FLOOR, _TABLE_HALVING_RATE_PER_1000_LINES, body.lines
                ),
                _count_table_rows(body.structural),
                lines=broken_positions,
            )
        )

    junk_positions, text_lines = _junk_lines(body.structural)
    junk_share = len(junk_positions) / text_lines if text_lines else 0.0
    if junk_share:
        metrics["junk_share"] = round(junk_share, 3)
        defects.append(
            Defect(
                CheckId.JUNK_LINES,
                f"{junk_share:.0%} junk lines",
                halvings=junk_share / _JUNK_HALVING_SHARE,
                places=text_lines,
                share=junk_share,
                lines=_body_lines(junk_positions),
            )
        )

    repeat_min_count = _scaled_threshold(
        _REPEAT_MIN_COUNT, _REPEAT_MIN_RATE_PER_1000_LINES, body.lines
    )
    repeat_groups = _repeat_groups(body.structural, repeat_min_count)
    repeats = len(repeat_groups)
    if repeats:
        metrics["repeats"] = repeats
        defect = _counted_defect(
            CheckId.REPEATS,
            f"{repeats} repeated lines",
            repeats,
            _REPEAT_FLOOR,
            _scaled_threshold(
                _REPEAT_FLOOR, _REPEAT_HALVING_RATE_PER_1000_LINES, body.lines
            ),
            body.lines,
            lines=[group[0] for group in repeat_groups],
        )
        if (
            max(len(group) for group in repeat_groups)
            > repeat_min_count * _REPEAT_LOOP_MULTIPLE
        ):
            defect = replace(defect, veto=True)
        defects.append(defect)

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
    images = _count_bad_images(body.structural, base_dir)
    defective = len(images.defective_positions)
    if defective:
        metrics["bad_images"] = defective
        defects.append(
            _counted_defect(
                CheckId.IMAGES,
                f"{defective} defective images",
                defective,
                0,
                _ONE_DEFECT,
                images.links,
                lines=images.defective_positions,
            )
        )

    repeated_images = _count_repeated_images(body.structural)
    if repeated_images:
        metrics["repeated_images"] = repeated_images
        # A signal: a running logo after the image dedup looks the same.
        defects.append(
            Defect(CheckId.REPEATED_IMAGES, f"{repeated_images} paths reused 3+ times")
        )

    return _GroupResult(tuple(defects), metrics, repairable=images.missing > 0)


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
            _counted_defect(
                check,
                f"{count} {detail}",
                count,
                _REPORTED_FLOOR,
                _scaled_threshold(
                    _REPORTED_FLOOR,
                    _REPORTED_HALVING_RATE_PER_1000_LINES,
                    body.finding_lines,
                ),
                body.finding_lines,
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
    marker_positions = _ocr_marker_positions(body.structural)
    ocr_markers = len(marker_positions)
    if ocr_markers:
        metrics["ocr_markers"] = ocr_markers
        defects.append(
            _counted_defect(
                CheckId.LLM_OCR_MARKERS,
                f"{ocr_markers} OCR markers",
                ocr_markers,
                0,
                _ONE_DEFECT,
                body.lines,
                lines=marker_positions,
            )
        )

    lost_positions = _lost_page_positions(body.structural)
    lost_pages = len(lost_positions)
    if lost_pages:
        metrics["lost_pages"] = lost_pages
        defects.append(
            Defect(
                CheckId.LOST_PAGES,
                f"{lost_pages} pages not recognized",
                veto=True,
                lines=_body_lines(lost_positions),
            )
        )

    if inspection_chunks and inspection_chunks_done is not None:
        inspection_coverage = inspection_chunks_done / inspection_chunks
        metrics["inspection_coverage"] = round(inspection_coverage, 3)
        if inspection_chunks_done < inspection_chunks:
            undone = 1 - inspection_coverage
            defects.append(
                Defect(
                    CheckId.INSPECTION_COVERAGE,
                    f"{inspection_chunks_done} of {inspection_chunks} chunks inspected",
                    halvings=undone / _INSPECTION_HALVING_SHARE,
                    veto=inspection_coverage < _INSPECTION_VETO_DONE_SHARE,
                    places=inspection_chunks,
                    share=undone,
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


_LATIN = "LATIN"
_CYRILLIC = "CYRILLIC"
_CJK = "CJK"

# Name prefixes whose script group is not the first word of the name. Kana,
# hangul, and CJK ideographs are one group: Japanese mixes kana with
# ideographs, Korean hangul with them, so each alone would read as foreign.
_SCRIPT_NAME_PREFIXES: tuple[tuple[str, str], ...] = (
    ("FULLWIDTH LATIN", _LATIN),
    ("HIRAGANA", _CJK),
    ("KATAKANA", _CJK),
    ("HALFWIDTH KATAKANA", _CJK),
    ("HANGUL", _CJK),
    ("HALFWIDTH HANGUL", _CJK),
    ("BOPOMOFO", _CJK),
    ("IDEOGRAPHIC", _CJK),
)

# Shown in the defect text, by count.
_UNREADABLE_DETAIL_MAX_SCRIPTS = 3


def _script_group(letter: str) -> str:
    """The script group of `letter`: the first word of its Unicode name.

    `unicodedata` has no Script property, but a letter's name opens with its
    script (`LATIN`, `GREEK`, `ARABIC`, `CJK`); the prefix table merges the
    rest.
    """
    name = unicodedata.name(letter, "")
    for prefix, group in _SCRIPT_NAME_PREFIXES:
        if name.startswith(prefix):
            return group
    return name.split(" ", 1)[0]


def _is_impossible(ch: str) -> bool:
    """True for a char that no readable text holds.

    These are the replacement mark, a private use or unassigned code point,
    and a control code other than a tab or a line break.
    """
    if ch == chr(0xFFFD):
        return True
    category = unicodedata.category(ch)
    if category == "Cc":
        return ch not in "\t\n\r"
    return category in ("Co", "Cn")


@dataclass(frozen=True)
class _LetterStats:
    """Letter composition of a body.

    The OCR-garbage signal is `unreadable_share`: letters foreign to the main
    script plus impossible chars, over letters plus impossible chars. Latin is
    never foreign, and Cyrillic is not foreign to a Latin body. The shares of
    accented Latin and of Cyrillic, over letters alone, are the mojibake
    signal.
    """

    letters: int
    impossible: int
    main_script: str
    # Letter counts of the foreign script groups, the largest first.
    foreign: tuple[tuple[str, int], ...]
    accented_share: float
    cyrillic_share: float

    @property
    def sample(self) -> int:
        return self.letters + self.impossible

    @property
    def unreadable_share(self) -> float:
        if not self.sample:
            return 0.0
        foreign = sum(count for _, count in self.foreign)
        return (foreign + self.impossible) / self.sample


def _letter_stats(body: str) -> _LetterStats:
    """Classify the letters and impossible chars of `body`."""
    scripts: Counter[str] = Counter()
    impossible = 0
    accented = 0
    for ch, count in Counter(body).items():
        if not ch.isalpha():
            if _is_impossible(ch):
                impossible += count
            continue
        group = _script_group(ch)
        scripts[group] += count
        # A decomposition means a diacritic. The name, not the group, keeps
        # a fullwidth letter out: it decomposes to its narrow form.
        named_latin = unicodedata.name(ch, "").startswith(_LATIN)
        if named_latin and unicodedata.decomposition(ch):
            accented += count
    letters = scripts.total()
    if not letters:
        return _LetterStats(0, impossible, "", (), 0.0, 0.0)
    main_script = scripts.most_common(1)[0][0]
    own = {main_script, _LATIN}
    if main_script == _LATIN:
        own.add(_CYRILLIC)
    foreign = tuple(
        (group, count) for group, count in scripts.most_common() if group not in own
    )
    return _LetterStats(
        letters=letters,
        impossible=impossible,
        main_script=main_script,
        foreign=foreign,
        accented_share=accented / letters,
        cyrillic_share=scripts[_CYRILLIC] / letters,
    )


def _unreadable_detail(stats: _LetterStats) -> str:
    """The defect text: the share, the main script, and what is unreadable."""
    found = [
        f"{count} {group} letters"
        for group, count in stats.foreign[:_UNREADABLE_DETAIL_MAX_SCRIPTS]
    ]
    if stats.impossible:
        found.append(f"{stats.impossible} impossible chars")
    where = f" in a {stats.main_script} body" if stats.main_script else ""
    return f"{stats.unreadable_share:.0%} unreadable{where}: " + ", ".join(found)


def _is_mojibake(stats: _LetterStats) -> bool:
    """True when the letters look like a Cyrillic text decoded as Latin.

    A cp1251 font without a ToUnicode table yields accented Latin letters,
    which `unreadable_share` cannot see: such garbage runs above 50% accented,
    real German or French near 2%. The Cyrillic guard keeps accented Latin
    documents out; the share is over all letters.
    """
    return (
        stats.cyrillic_share >= _MOJIBAKE_MIN_CYRILLIC_SHARE
        and stats.accented_share > _MOJIBAKE_MAX_ACCENTED_SHARE
    )


def _closed_math_spans(text: str) -> list[tuple[str, int]]:
    """Every closed `$$...$$` / `$...$` pair in `text` as `(content, offset)`.

    Display spans go first and are removed, so inline spans cannot straddle
    them. A lone `$` (currency) is never among them. The offset is that of
    the opening delimiter in `text`.
    """
    spans: list[tuple[str, int]] = []
    # Each piece of the leftover with its offset in `text`.
    pieces: list[tuple[int, str]] = []
    last = 0
    for match in _DISPLAY_MATH_RE.finditer(text):
        spans.append((match.group(1), match.start()))
        pieces.append((last, text[last : match.start()]))
        last = match.end()
    pieces.append((last, text[last:]))
    joined = "".join(piece for _, piece in pieces)
    # Joined offset of each piece start, for a bisect per inline match.
    starts: list[int] = []
    total = 0
    for _, piece in pieces:
        starts.append(total)
        total += len(piece)
    for match in _INLINE_MATH_RE.finditer(joined):
        index = bisect_right(starts, match.start()) - 1
        origin = pieces[index][0]
        spans.append((match.group(1), origin + match.start() - starts[index]))
    return spans


def _closed_math_span_contents(text: str) -> list[str]:
    """The content of every closed math pair in `text`, display spans first."""
    return [content for content, _ in _closed_math_spans(text)]


def _invalid_formula_offsets(text: str) -> list[int]:
    """Offsets in `text` of the syntactically invalid math spans."""
    return [
        offset
        for content, offset in _closed_math_spans(text)
        if not is_valid_math(content)
    ]


def _plain_position(body: _Body, offset: int) -> int:
    """The segment position of the line of `body.plain_text` holding `offset`."""
    return body.plain_positions[body.plain_text.count("\n", 0, offset)]


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


def _runaway_math_details(plain_text: str) -> tuple[list[str], list[int]]:
    """Details of the runaway-math check on `plain_text`, and the offsets.

    Both are empty when the text is sound. An offset is that of an unpaired
    delimiter, or of the opening of a block that holds structure or is
    oversize.

    An unclosed display delimiter turns everything up to the next formula into
    one math block. Signals: an odd delimiter count, a block holding document
    structure, a block past the size caps (not counted twice). Read over the
    inline-code mask: a quoted `$$` would shift every later pairing. No hint:
    post may not rebalance delimiters.
    """
    masked = mask_inline_code(plain_text)
    details: list[str] = []
    offsets: list[int] = []
    delimiters, last_delimiter = _display_delimiters(masked)
    if delimiters % 2:
        details.append(f"{delimiters} display delimiters, one unpaired")
        offsets.append(last_delimiter)
    over_structure = 0
    oversize = 0
    for match in _DISPLAY_MATH_RE.finditer(masked):
        content = match.group(1)
        if _holds_document_structure(content):
            over_structure += 1
            offsets.append(match.start())
        elif _is_oversize_math_block(content):
            oversize += 1
            offsets.append(match.start())
    if over_structure:
        details.append(f"{over_structure} display blocks over document structure")
    if oversize:
        details.append(f"{oversize} display blocks past the size cap")
    return details, offsets


def _display_delimiters(text: str) -> tuple[int, int]:
    """Count the `$$` display delimiters of `text`; give the offset of the last.

    A run glued between alphanumerics (`a$$b`) is two inline delimiters. A
    longer run is ambiguous and not counted.
    """
    count = 0
    last = 0
    for match in _DOLLAR_RUN_RE.finditer(text):
        if match.end() - match.start() != 2:
            continue
        before = text[match.start() - 1] if match.start() else ""
        after = text[match.end()] if match.end() < len(text) else ""
        if before.isalnum() and after.isalnum():
            continue
        count += 1
        last = match.start()
    return count, last


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


def _greek_unit_positions(structural: list[Segment]) -> list[int]:
    """Positions of the math spans that are an integer glued to Greek commands.

    Only on lines with Cyrillic prose outside the span. Not a cleaner rule:
    the reverse mapping (`\\kappa\\Gamma` to `кГ`) has no safe table, so it is
    a signal for inspection. Read over the inline-code mask.
    """
    positions: list[int] = []
    for position, (line, protected) in enumerate(structural):
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
                positions.append(position)
    return positions


def _formula_loop_positions(structural: list[Segment]) -> list[int]:
    """Positions of the plain lines whose math span became a repetition loop.

    Truncation often leaves the closing `$` looking escaped, so
    `_count_invalid_formulas` never sees the span. The cleaner trims the loops
    it finds, so this counts loops an LLM step wrote or a body graded outside
    the pipeline.
    """
    return [
        position
        for position, (line, protected) in enumerate(structural)
        if not protected and math_repetition_loop(line)
    ]


def _count_table_rows(structural: list[Segment]) -> int:
    """Count the plain lines that carry a table cell separator."""
    return sum(
        1
        for line, protected in structural
        if not protected and has_cell_separator(line.strip())
    )


def _junk_lines(structural: list[Segment]) -> tuple[list[int], int]:
    """Return ``(junk positions, total)`` of the plain non-blank lines.

    A junk line holds service symbols only.

    Structural symbol lines and setext underlines are excluded, as the cleaner
    keeps them; the previous line is tracked as the cleaner tracks it.
    """
    total = 0
    junk: list[int] = []
    prev = ""
    for position, (line, protected) in enumerate(structural):
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
            junk.append(position)
        prev = line
    return junk, total


def _repeat_groups(structural: list[Segment], min_count: float) -> list[list[int]]:
    """Positions of each short line repeating `min_count` times or more.

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
        occurrences
        for occurrences in positions.values()
        if len(occurrences) >= min_count and _repeats_in_a_cluster(occurrences)
    ]


def _repeats_in_a_cluster(occurrences: list[int]) -> bool:
    """True when the median gap between occurrences reads as a loop.

    The repeat minimum is at least 3, so there is always a gap to weigh.
    """
    gaps = [later - earlier for earlier, later in pairwise(occurrences)]
    return statistics.median(gaps) <= _REPEAT_MAX_MEDIAN_GAP


@dataclass(frozen=True)
class _ImageCounts:
    """Local image links checked, missing, and the positions of defective ones.

    A missing link is defective too. A line with two defective links is listed
    twice.
    """

    links: int = 0
    missing: int = 0
    defective_positions: tuple[int, ...] = ()


def _count_bad_images(structural: list[Segment], base_dir: Path | None) -> _ImageCounts:
    """Count the local image links and the defective ones among them.

    Defective: missing, under 512 bytes, or single-color. Only a missing link
    is repairable. Markdown and HTML links both count.
    """
    if base_dir is None:
        return _ImageCounts()
    links = 0
    missing = 0
    defective: list[int] = []
    for position, (line, protected) in enumerate(structural):
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
            links += 1
            if not path.exists():
                missing += 1
                defective.append(position)
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size < _IMAGE_MIN_BYTES or _is_single_color(path):
                defective.append(position)
    return _ImageCounts(links, missing, tuple(defective))


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

    A signal only: after the image dedup a running logo is one path linked from
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


def _ocr_marker_positions(structural: list[Segment]) -> list[int]:
    """Positions of the LLM-OCR uncertainty markers, one entry for each marker.

    Protected zones count: a marker there is still in the result.
    """
    return [
        position
        for position, (line, _) in enumerate(structural)
        for marker in _OCR_MARKERS
        for _ in range(line.count(marker))
    ]


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


def _lost_page_positions(structural: list[Segment]) -> list[int]:
    """Positions of the pages LLM OCR marked as lost, outside protected zones."""
    return [
        position
        for position, (line, protected) in enumerate(structural)
        if not protected and is_lost_page_marker(line)
    ]
