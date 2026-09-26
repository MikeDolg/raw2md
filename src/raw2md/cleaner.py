"""Deterministic cleaning: in-place fixes, and a report of what stays broken.

Cleaning runs before any LLM step. An unambiguous defect is fixed in place
(`clean_in_place`); an ambiguous one is reported as a finding and left in the
body (`cleaning.findings`). `clean_with_report` returns both; `clean` returns
the body alone.

Protected zones pass through verbatim: front matter, fenced code, and HTML
tables. Three rules reach into an HTML table's cells but never its markup:
the alt-path strip, the LLM-OCR fabrication strip, and the math cell opening.

This module owns the order of the passes, the one thing about cleaning that
must be read as a whole. The rules live in the `cleaning` package.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from raw2md.cleaning import (
    CleanOptions,
    Finding,
    apply_outline_levels,
    classify_and_fix,
    clear_display_span_tail,
    close_section_level_gaps,
    close_unpaired_delimiters,
    collapse_blanks,
    collapse_unused_heading_levels,
    decompose_contents_table,
    defuse_false_math,
    drop_bodyless_table,
    drop_content_free_math_spans,
    drop_empty_table_columns,
    drop_orphan_sizers,
    drop_page_furniture,
    drop_paragraph_emphasis,
    drop_running_header_headings,
    drop_stray_bullet_glyph,
    fix_images_and_report,
    fix_table_math,
    fold_repeated_column_cycle,
    group_settled_headings,
    headings_settled_before_nesting,
    join_contents_entry_breaks,
    join_flattened_paragraphs,
    join_letter_spaced_headings,
    join_letter_spaced_runs,
    join_wrapped_contents_entries,
    keep_table_delimiter_under_header,
    lay_out_table_blocks,
    lift_prose_from_display_math,
    mend_pipe_block_missing_delimiter,
    normalize_heading_numbering,
    normalize_lists,
    normalize_math,
    normalize_repeated_heading_levels,
    normalize_unnumbered_heading_levels,
    open_math_html_cells,
    printed_outline,
    promote_dingbat_bullet,
    promote_paragraph_formula,
    reclose_runaway_display_spans,
    reclose_runaway_inline_spans,
    recut_periodic_stack,
    recut_swallowed_cells,
    rejoin_hyphenation,
    repair_attested_tokens,
    reunite_split_formulas,
    reunite_split_tables,
    separate_bold_list_marker,
    separate_glued_inline_spans,
    settle_compound_hyphens,
    split_glued_table_header,
    split_run_in_headings,
    spread_crushed_runs,
    strip_alt_file_paths,
    strip_heading_emphasis,
    strip_heading_leading_glyphs,
    strip_html_anchors,
    strip_math_span_html,
    strip_ocr_fabrications,
    strip_oversize_heading_markers,
    tag_equation_numbers,
    trim_repetition_loops,
    unwrap_single_glyph_math,
)
from raw2md.mdtext.zones import Segment, segments
from raw2md.source_outline import SourceOutline

# `CleanOptions` is re-exported: the options travel with the entry points.
__all__ = [
    "CleanOptions",
    "CleanResult",
    "clean",
    "clean_in_place",
    "clean_with_report",
]

# The two unnumbered-level rules can hand each other a fresh violation, so
# they alternate to a fixed point. The cap is defensive, not a proven bound:
# observed documents settle in one or two rounds. A missed fix beats a hang.
_HEADING_LEVEL_SETTLE_ROUNDS = 8

# The running-header drop reads levels that the later heading rules rewrite,
# and each drop changes their evidence, so the whole block repeats until
# nothing moves.
_HEADING_STRUCTURE_SETTLE_ROUNDS = 4

# A joined line carries the break of the line it absorbed, behind the walk.
_HYPHENATION_SETTLE_ROUNDS = 4


def clean_in_place(text: str, options: CleanOptions | None = None) -> str:
    """Apply the in-place fixes to LF `text` and return the cleaned markdown.

    The result ends with one newline, or is empty. Without `options` the
    route is unknown, which disables heading recovery.
    """
    if options is None:
        options = CleanOptions()
    text = strip_alt_file_paths(text)
    if options.llm_ocr:
        text = strip_ocr_fabrications(text, options.keywords)
    seg_list = classify_and_fix(text)
    seg_list = strip_html_anchors(seg_list)
    seg_list = strip_heading_emphasis(seg_list)
    # Before every rule that reads a heading's number: a stray leading glyph
    # hides the number, as emphasis does.
    seg_list = strip_heading_leading_glyphs(seg_list)
    seg_list = split_run_in_headings(seg_list)
    # Before every rule that compares titles: a letter-spaced title matches
    # nothing but itself.
    seg_list = join_letter_spaced_headings(seg_list)
    # Before every rule that reads a heading's level: an oversize "heading" is
    # mistagged prose or a crushed table and would feed a false section to
    # the level votes.
    seg_list = strip_oversize_heading_markers(seg_list)
    seg_list = drop_running_header_headings(seg_list)
    seg_list = drop_page_furniture(seg_list, options.keywords)
    seg_list = _settle_heading_structure(seg_list, options)
    # Before every span-scoped math rule: a glued-shut delimiter pairs with the
    # next formula's opener, and every span between reads as one runaway block.
    seg_list = reclose_runaway_display_spans(seg_list)
    seg_list = reclose_runaway_inline_spans(seg_list)
    seg_list = fix_table_math(seg_list)
    seg_list = defuse_false_math(seg_list)
    # Before the normalization: a piece of a cut formula balances only once
    # the pieces are joined.
    seg_list = reunite_split_formulas(seg_list)
    # Before every rule that reads span content, after the reunion so that it
    # reads whole spans.
    seg_list = strip_math_span_html(seg_list)
    seg_list = normalize_math(seg_list)
    # After the normalization, which decides what renders; before the tag fold,
    # which would read a legend entry's punctuation as a formula's.
    seg_list = lift_prose_from_display_math(seg_list)
    # Before the tag fold, so a number under a promoted formula folds in as
    # under any display block.
    seg_list = promote_paragraph_formula(seg_list)
    # After the reunion, which moves a number to the span's tail, and after the
    # normalization, which clears `\label{...}` and turns `\eqno` into a tag.
    seg_list = tag_equation_numbers(seg_list)
    seg_list = unwrap_single_glyph_math(seg_list)
    seg_list = drop_content_free_math_spans(seg_list)
    # Before the pairing fix: an orphan sizer would throw off its count.
    seg_list = drop_orphan_sizers(seg_list)
    seg_list = close_unpaired_delimiters(seg_list)
    # Last of the span rules: it moves every span bound after the insert.
    seg_list = separate_glued_inline_spans(seg_list)
    # Before list de-nesting, so the promoted items form a block.
    seg_list = promote_dingbat_bullet(seg_list)
    seg_list = normalize_lists(seg_list)
    seg_list = separate_bold_list_marker(seg_list)
    seg_list = drop_stray_bullet_glyph(seg_list)
    seg_list = split_glued_table_header(seg_list)
    # Before every grid rule: until folded, one column index names several
    # fields. After the header split, which leaves the title row to read.
    seg_list = fold_repeated_column_cycle(seg_list)
    # Before every rule that reads a table body whole: a half reads as a column
    # that no row fills.
    seg_list = reunite_split_tables(seg_list)
    # Before the bodyless collapse, which would claim the same table.
    seg_list = decompose_contents_table(seg_list)
    # Before the bodyless collapse: a body stacked in one header cell leaves no
    # data row, and the collapse would join it into prose.
    seg_list = recut_periodic_stack(seg_list)
    # Before the column rules: without rows, every header cell reads as a
    # column that no row fills.
    seg_list = drop_bodyless_table(seg_list)
    seg_list = drop_empty_table_columns(seg_list)
    # After the empty-column drop, which rewrites the column indices.
    seg_list = recut_swallowed_cells(seg_list)
    # After the recut: what is left is a run whose blanks leave a choice, which
    # only the table's own columns decide.
    seg_list = spread_crushed_runs(seg_list)
    # After every grid rule, which reads an in-cell break as a lost cell; a
    # break still standing is a wrapped contents entry.
    seg_list = join_contents_entry_breaks(seg_list, options.keywords)
    # After that join: a cell still stacking fragments defeats the column
    # comparison.
    seg_list = join_wrapped_contents_entries(seg_list, options.keywords)
    # After the table rules: collapsing a carrier table leaves its number or
    # picture behind the display closer.
    seg_list = clear_display_span_tail(seg_list)
    seg_list = _settle_hyphenation(seg_list, options)
    # After heading recovery: a bold title is a heading by now, so a wrap
    # still standing is noise around prose.
    seg_list = drop_paragraph_emphasis(seg_list)
    # After the rejoin: a fragment still ending in a break holds a split
    # nothing attested, and this rule leaves it.
    seg_list = join_flattened_paragraphs(seg_list)
    seg_list = join_letter_spaced_runs(seg_list)
    # After the rejoin, whose joined spellings the counts must weigh.
    seg_list = settle_compound_hyphens(seg_list)
    # Last of the body-count rules: every join above spells words it weighs.
    seg_list = repair_attested_tokens(seg_list, options.witness_min)
    # Postcondition on every table block: several passes drop a junk header
    # row and leave the separator first, where GFM reads no table. Before the
    # missing-delimiter mend, which would misread the rows under it.
    seg_list = keep_table_delimiter_under_header(seg_list)
    # Postcondition: a pipe block with no delimiter row renders as no table.
    seg_list = mend_pipe_block_missing_delimiter(seg_list)
    # Last segment pass, once no rule moves a cell: padding is billed, since
    # the chunk planner sizes a request by text length.
    seg_list = lay_out_table_blocks(seg_list)
    # Last of all: it writes blank lines inside a protected zone, which every
    # rule above reads as one line per table row.
    return open_math_html_cells(collapse_blanks(seg_list))


def _settle_heading_structure(
    seg_list: list[Segment], options: CleanOptions
) -> list[Segment]:
    """Run the heading rules until the structure they decide stops moving.

    A round drops running headers, then settles levels. A later round sees
    the drop against settled levels instead of the converter's guess. The
    level witness is read once: the heading that closes the contents zone
    moves between rounds, and a re-read would state a new ladder each time.
    """
    outline = _level_witness(seg_list, options)
    for _ in range(_HEADING_STRUCTURE_SETTLE_ROUNDS):
        fixed = _settle_heading_levels(
            drop_running_header_headings(seg_list), options, outline
        )
        if fixed == seg_list:
            break
        seg_list = fixed
    return seg_list


def _level_witness(seg_list: list[Segment], options: CleanOptions) -> SourceOutline:
    """The source outline when it has one, else the printed contents.

    The two are never merged: each numbers levels on its own scale.
    """
    if options.outline.has_outline:
        return options.outline
    return printed_outline(seg_list, options.keywords)


def _settle_heading_levels(
    seg_list: list[Segment], options: CleanOptions, outline: SourceOutline
) -> list[Segment]:
    """Decide every heading's level from the evidence the document itself gives."""
    seg_list, stated = apply_outline_levels(seg_list, outline)
    seg_list, stated = normalize_heading_numbering(seg_list, options.method, stated)
    # A settled group applies from the next round, since its vote reads levels
    # this round validates. A self-numbered series and repeated unnumbered
    # titles settle up front: the nesting rule has nothing to tell them.
    settled = headings_settled_before_nesting(seg_list, options.keywords, stated)
    for _ in range(_HEADING_LEVEL_SETTLE_ROUNDS):
        fixed = normalize_repeated_heading_levels(
            normalize_unnumbered_heading_levels(
                seg_list, options.keywords, stated, settled
            ),
            options.keywords,
            stated,
        )
        settled = group_settled_headings(fixed, options.keywords, stated)
        if fixed == seg_list:
            break
        seg_list = fixed
    # The whole-body collapse first: after a lift the unused rank is in use,
    # and the sections the lift missed keep their hole. The collapse is
    # monotonic, so the lift still sees the holes it would have seen.
    return close_section_level_gaps(
        collapse_unused_heading_levels(seg_list), stated, settled
    )


def _settle_hyphenation(
    seg_list: list[Segment], options: CleanOptions
) -> list[Segment]:
    """Rejoin hyphenated line splits until no further join is attested.

    Rounds count a chain of breaks, not joins; a page does not produce a
    chain longer than two. Each changing round shrinks the body.
    """
    for _ in range(_HYPHENATION_SETTLE_ROUNDS):
        joined = rejoin_hyphenation(seg_list, options.source_text)
        if joined == seg_list:
            break
        seg_list = joined
    return seg_list


@dataclass(frozen=True)
class CleanResult:
    """What the cleaning stage produced: the body, and what it could not fix.

    Each finding is addressed by its line in `body`.
    """

    body: str
    findings: tuple[Finding, ...]

    def counts(self) -> dict[str, int]:
        """How many findings of each kind, ordered by kind."""
        return {kind: len(group) for kind, group in _by_kind(self.findings).items()}


def _by_kind(findings: tuple[Finding, ...]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = {}
    for finding in sorted(findings, key=lambda f: (f.kind, f.line)):
        grouped.setdefault(finding.kind, []).append(finding)
    return grouped


def clean(text: str, options: CleanOptions | None = None) -> str:
    """Fully clean `text` and return the body, dropping the report."""
    return clean_with_report(text, options).body


def clean_with_report(text: str, options: CleanOptions | None = None) -> CleanResult:
    """Fully clean `text`: in-place fixes, then a report of what stays broken.

    Idempotent in both halves. Repetition loops are trimmed after the
    detectors, since the trim removes the evidence of a lost formula; only the
    run that made the cut records it. Findings are renumbered onto the
    returned body.
    """
    if options is None:
        options = CleanOptions()
    fixed = clean_in_place(text, options)
    seg_list = segments(fixed)
    seg_list, findings = fix_images_and_report(seg_list, options)
    seg_list, landed = trim_repetition_loops(seg_list)
    numbers = _final_line_numbers(seg_list)
    return CleanResult(
        collapse_blanks(seg_list),
        tuple(
            replace(finding, line=numbers[landed[finding.line]]) for finding in findings
        ),
    )


def _final_line_numbers(seg_list: list[Segment]) -> list[int]:
    """Line number in the collapsed body for each segment, 1-based.

    Mirrors `collapse_blanks`. A dropped line takes the number of the next
    line, else the last line, else 1 for an empty body.
    """
    numbers: list[int | None] = []
    written = 0
    pending_blank = False
    seen_content = False
    for line, protected in seg_list:
        if not protected and not line.strip():
            pending_blank = seen_content
            numbers.append(None)
            continue
        if pending_blank:
            written += 1
            pending_blank = False
        written += 1
        seen_content = True
        numbers.append(written)
    settled: list[int] = [0] * len(numbers)
    follower = max(written, 1)
    for idx in range(len(numbers) - 1, -1, -1):
        number = numbers[idx]
        if number is None:
            settled[idx] = follower
        else:
            settled[idx] = number
            follower = number
    return settled
