"""Fast corpus-fixture tests: structure counts and quality checks.

Each fixture must be in canonical form: cleaning leaves it unchanged, and the
quality evaluator raises no false positive on it.
"""

from __future__ import annotations

from raw2md.cleaner import clean, clean_in_place
from raw2md.header import ResultStatus
from raw2md.mdtext.links import local_image_path
from raw2md.quality.evaluator import CheckId, Evaluation, evaluate

from ._paths import CORPUS_DIR
from ._structure import count_structure


def _body(name: str) -> str:
    return (CORPUS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _fired(ev: Evaluation, check: CheckId) -> bool:
    return any(d.check is check for d in ev.defects)


# ---- structural counts: new fixtures ----------------------------------------


def test_nested_lists_structure() -> None:
    body = _body("nested_lists")
    counts = count_structure(body)
    assert counts.headings_by_level.get(1) == 1
    assert counts.headings_by_level.get(2) == 4
    assert counts.tables == 0
    assert counts.formulas_total == 0
    assert counts.images == 0
    assert clean_in_place(body) == body


def test_footnotes_structure() -> None:
    body = _body("footnotes")
    counts = count_structure(body)
    assert counts.headings_by_level.get(1) == 1
    assert counts.headings_by_level.get(2) == 3
    assert counts.tables == 0
    assert counts.formulas_total == 0
    # count_structure does not track footnotes.
    assert body.count("[^") >= 10  # 5 inline refs + 5 definitions


def test_multilang_structure() -> None:
    body = _body("multilang")
    counts = count_structure(body)
    assert counts.headings_by_level.get(1) == 1
    assert counts.headings_by_level.get(2) == 4
    assert counts.tables == 1
    assert counts.formulas_total == 0


def test_long_doc_structure() -> None:
    body = _body("long_doc")
    counts = count_structure(body)
    assert counts.headings_by_level.get(1) == 1
    assert counts.headings_by_level.get(2) == 6
    assert counts.tables == 0
    assert counts.formulas_total == 0


def test_engineering_prose_structure() -> None:
    """A handbook page: Latin standards/brands, a bold caption, a symbol legend.

    The page carries the legitimate form of shapes the prose rules key on, so none
    of them may fire.
    """
    body = _body("engineering_prose")
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1, 2: 4}
    assert counts.tables == 0
    assert counts.images == 0
    assert counts.display_formulas == 0
    assert counts.inline_formulas == 4
    ev = evaluate(body)
    assert ev.status is ResultStatus.OK, f"engineering_prose evaluates {ev.status!r}"
    for check in (
        CheckId.HEADINGS,
        CheckId.TABLES,
        CheckId.JUNK_LINES,
        CheckId.UNREADABLE_CHARS,
        CheckId.REPEATS,
    ):
        assert not _fired(ev, check), f"engineering_prose fired {check}"
    assert clean_in_place(body) == body


def test_math_legend_structure() -> None:
    """A calculation page: display equations beside a prose symbol legend.

    The page carries the legitimate form of shapes the math rules key on, so none
    of them may fire.
    """
    body = _body("math_legend")
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1, 2: 3}
    assert counts.tables == 0
    assert counts.images == 0
    assert counts.display_formulas == 3
    assert counts.inline_formulas == 5
    ev = evaluate(body)
    assert ev.status is ResultStatus.OK, f"math_legend evaluates {ev.status!r}"
    for check in (
        CheckId.FORMULAS,
        CheckId.RUNAWAY_MATH,
        CheckId.GREEK_UNITS,
        CheckId.HEADINGS,
    ):
        assert not _fired(ev, check), f"math_legend fired {check}"
    assert clean_in_place(body) == body


# ---- structural counts: tables.md, formulas.md, and headers.md --------------


def test_tables_edge_has_six_tables() -> None:
    body = _body("tables")
    counts = count_structure(body)
    assert counts.tables == 6
    ev = evaluate(body)
    assert not _fired(ev, CheckId.TABLES), (
        "tables.md edge tables (empty cells, centre alignment) "
        "must not fire the broken-table check"
    )


def test_table_formulas_structure() -> None:
    body = _body("table_formulas")
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1, 2: 2}
    assert counts.tables == 1
    assert counts.images == 1
    assert counts.display_formulas == 2
    assert counts.inline_formulas == 3
    ev = evaluate(body, base_dir=CORPUS_DIR)
    assert not _fired(ev, CheckId.FORMULAS), (
        "table_formulas.md formula-bearing table cells must not fire the "
        "broken-formula check"
    )
    assert not _fired(ev, CheckId.TABLES), (
        "table_formulas.md must not fire the broken-table check"
    )
    assert not _fired(ev, CheckId.IMAGES), (
        "table_formulas.md's sized image must resolve and not fire the "
        "broken-image check"
    )
    assert clean_in_place(body) == body


def test_table_math_pipes_structure() -> None:
    """The source writes a modulus as `\\lvert…\\rvert`, not a bare `\\left|…\\right|`.

    pandoc still turns it into a literal `|` through OMML, so the docx round-trip
    exercises the table-row math fix while the fixture passes markdownlint.
    """
    body = _body("table_math_pipes")
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1, 2: 1}
    assert counts.tables == 1
    assert counts.images == 0
    assert counts.display_formulas == 2
    assert counts.inline_formulas == 1
    ev = evaluate(body)
    assert not _fired(ev, CheckId.TABLES), (
        "table_math_pipes.md must not fire the broken-table check"
    )
    assert not _fired(ev, CheckId.FORMULAS), (
        "table_math_pipes.md must not fire the broken-formula check"
    )
    assert clean_in_place(body) == body


def test_chart_series_structure() -> None:
    body = _body("chart_series")
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1, 2: 3}
    assert counts.tables == 0
    assert counts.images == 3
    assert counts.display_formulas == 0
    assert counts.inline_formulas == 3
    ev = evaluate(body, base_dir=CORPUS_DIR)
    assert not _fired(ev, CheckId.REPEATS), (
        "chart_series.md's axis label repeated under each figure must not fire "
        "the repeat check"
    )
    assert ev.status is ResultStatus.OK, (
        f"chart_series.md must evaluate to ok, got {ev.status!r}"
    )
    assert clean_in_place(body) == body


def test_formulas_edge_display_count() -> None:
    body = _body("formulas")
    counts = count_structure(body)
    # Includes one form with each `$$` alone on its line.
    assert counts.display_formulas == 7
    # Escaped `\$100` and `\$200` must not count as inline spans.
    assert counts.inline_formulas == 12
    ev = evaluate(body)
    assert not _fired(ev, CheckId.FORMULAS), (
        "formulas.md edge cases (escaped \\$, deep \\frac, multiline $$, "
        "standalone $$ delimiters) must not fire the broken-formula check"
    )
    assert clean_in_place(body) == body


def test_headers_edge_setext_heading_count() -> None:
    body = _body("headers")
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1, 2: 4, 3: 6, 4: 2}
    ev = evaluate(body)
    assert not _fired(ev, CheckId.HEADINGS), (
        "headers.md setext H2 (text underlined with `---`) "
        "must not fire the heading check"
    )
    assert clean_in_place(body) == body


def test_percent_encoded_link_resolves_to_real_asset() -> None:
    """A percent-encoded target (space, parens) decodes to a real corpus asset.

    A separate snippet: a third image in the images fixture would trip the repeat
    check on pandoc's `</figure>` lines in the docx round-trip.
    """
    target = "assets/diagram%20%28v2%29.png"
    body = f"![Diagram v2]({target})\n"
    counts = count_structure(body)
    assert counts.images == 1
    resolved = local_image_path(CORPUS_DIR, target)
    assert resolved is not None
    assert resolved.is_file()
    assert resolved.name == "diagram (v2).png"
    ev = evaluate(body, base_dir=CORPUS_DIR)
    assert not _fired(ev, CheckId.IMAGES), (
        "a percent-encoded asset name (space and parens) must resolve to the "
        "real file, not fire the broken-image check"
    )


# ---- structural counts and cleaning: observed converter artifacts -------------
#
# Converter artifacts no generation chain reproduces, checked against the
# independent counting of count_structure.

# marker's page-anchor span before a heading, and a span with a link below it.
_SPAN_HEADING_TEXT = (
    '#### <span id="page-31-2"></span>4.2.1.1 Check interval\n'
    "\n"
    '<span id="page-31-3"></span>See Table [2,](#page-30-0) section\n'
    "\n"
    "### 4.2.1.2 Fitting tools\n"
)

_ORPHAN_SPLIT_FORMULA = (
    r"$$&\tau_{23} = \pm \frac{1}{2} (\sigma_2 - \sigma_3) \end{split}$$" + "\n"
)

_REPETITION_LOOP_TEXT = (
    "Then $a_{1}" + "+a_{1}" * 7 + "$ ends the readable sentence here.\n"
)


def test_span_wrapped_heading_counts_and_cleans() -> None:
    """count_structure reads a heading through its anchor span, before and after."""
    assert count_structure(_SPAN_HEADING_TEXT).headings_by_level == {3: 1, 4: 1}
    cleaned = clean(_SPAN_HEADING_TEXT)
    assert cleaned == (
        "### 4.2.1.1 Check interval\n"
        "\n"
        "See Table 2, section\n"
        "\n"
        "### 4.2.1.2 Fitting tools\n"
    )
    assert count_structure(cleaned).headings_by_level == {3: 2}
    assert clean(cleaned) == cleaned


def test_orphan_split_formula_counts_as_one_display_span() -> None:
    """The stray environment markup does not split or drop the display span."""
    before = count_structure(_ORPHAN_SPLIT_FORMULA)
    assert before.display_formulas == 1
    assert before.inline_formulas == 0
    cleaned = clean(_ORPHAN_SPLIT_FORMULA)
    assert cleaned == r"$$\tau_{23} = \pm \frac{1}{2} (\sigma_2 - \sigma_3)$$" + "\n"
    after = count_structure(cleaned)
    assert after.display_formulas == 1
    assert after.inline_formulas == 0
    assert clean(cleaned) == cleaned


def test_repetition_loop_counts_as_one_inline_span() -> None:
    """A degenerate repeat stays one inline span once trimmed."""
    before = count_structure(_REPETITION_LOOP_TEXT)
    assert before.inline_formulas == 1
    assert before.display_formulas == 0
    trimmed = clean(_REPETITION_LOOP_TEXT)
    assert trimmed == "Then $a_{1}+a_{1}$ ends the readable sentence here.\n"
    after = count_structure(trimmed)
    assert after.inline_formulas == 1
    assert after.headings_by_level == {}
    assert after.tables == 0
    assert after.images == 0
    assert clean(trimmed) == trimmed


def test_observed_forms_combine_without_interaction() -> None:
    """The three forms above, in one document, clean without cross-interaction."""
    body = (
        _SPAN_HEADING_TEXT + "\n" + _ORPHAN_SPLIT_FORMULA + "\n" + _REPETITION_LOOP_TEXT
    )
    before = count_structure(body)
    assert before.headings_by_level == {3: 1, 4: 1}
    assert before.formulas_total == 2

    cleaned = clean(body)
    expected = (
        "### 4.2.1.1 Check interval\n"
        "\n"
        "See Table 2, section\n"
        "\n"
        "### 4.2.1.2 Fitting tools\n"
        "\n"
        r"$$\tau_{23} = \pm \frac{1}{2} (\sigma_2 - \sigma_3)$$"
        "\n"
        "\n"
        "Then $a_{1}+a_{1}$ ends the readable sentence here.\n"
    )
    assert cleaned == expected

    after = count_structure(cleaned)
    assert after.headings_by_level == {3: 2}
    assert after.formulas_total == 2
    assert clean(cleaned) == cleaned


# ---- quality checks: no false positives on corpus content --------------------


def test_multilang_does_not_trigger_unreadable_chars() -> None:
    """Latin identifiers in a Cyrillic doc must not fire the unreadable-chars check."""
    body = _body("multilang")
    ev = evaluate(body)
    assert not _fired(ev, CheckId.UNREADABLE_CHARS), (
        "multilang body should not trigger unreadable-chars: "
        "Latin and Cyrillic are both whitelisted by the unreadable-chars check"
    )


def test_long_doc_passes_density_floor() -> None:
    """A long document stays well above the 350-chars-per-page density floor."""
    body = _body("long_doc")
    ev = evaluate(body, source_pages=6)
    assert not _fired(ev, CheckId.TEXT_DENSITY), (
        f"long_doc should not trigger density check with 6 source pages; "
        f"density={ev.metrics.get('density')}"
    )


def test_long_doc_does_not_trigger_repeats() -> None:
    """A document with unique section headers must not fire the repeat check."""
    body = _body("long_doc")
    ev = evaluate(body)
    assert not _fired(ev, CheckId.REPEATS), (
        "long_doc should not trigger repeat detection; all section headers are unique"
    )
