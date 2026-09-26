"""Fast unit tests for the deterministic round-trip structure counters."""

from __future__ import annotations

from ._structure import StructureCounts, compare_structure, count_structure


def test_counts_headings_by_level() -> None:
    body = "\n".join(["# A", "## B", "## C", "### D", "text", ""])
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1, 2: 2, 3: 1}
    assert counts.headings_total == 4


def test_hash_without_space_is_not_a_heading() -> None:
    body = "\n".join(["#tag is not a heading", "# real heading", ""])
    assert count_structure(body).headings_by_level == {1: 1}


def test_counts_setext_h1_heading() -> None:
    body = "\n".join(["Title", "=====", "", "Body text.", ""])
    assert count_structure(body).headings_by_level == {1: 1}


def test_counts_setext_h2_heading() -> None:
    body = "\n".join(["Sub", "---", "", "Body text.", ""])
    assert count_structure(body).headings_by_level == {2: 1}


def test_bare_underline_without_preceding_text_is_not_a_heading() -> None:
    body = "\n".join(["", "---", "", "text", ""])
    assert count_structure(body).headings_by_level == {}


def test_setext_underline_under_atx_heading_is_not_double_counted() -> None:
    body = "\n".join(["# Title", "---", "", "text", ""])
    assert count_structure(body).headings_by_level == {1: 1}


def test_setext_underline_after_protected_block_is_not_a_heading() -> None:
    # `</table>` is protected, so the `===` below it is no setext underline.
    body = "\n".join(["<table><tr><td>x</td></tr></table>", "===", "", "text", ""])
    assert count_structure(body).headings_by_level == {}


def test_ignores_headings_and_pipes_in_fenced_code() -> None:
    body = "\n".join(
        [
            "# Title",
            "",
            "```",
            "# not a heading",
            "| a | b |",
            "| - | - |",
            "```",
            "",
        ]
    )
    counts = count_structure(body)
    assert counts.headings_by_level == {1: 1}
    assert counts.tables == 0


def test_counts_one_table_per_header_separator_pair() -> None:
    body = "\n".join(
        [
            "| col1 | col2 |",
            "| --- | --- |",
            "| a | b |",
            "| c | d |",
            "",
            "| x | y |",
            "|:-:|:-:|",
            "| 1 | 2 |",
            "",
        ]
    )
    assert count_structure(body).tables == 2


def test_counts_image_links() -> None:
    body = "\n".join(["![one](a.png)", "text", "![two](sub/b.png)", ""])
    assert count_structure(body).images == 2


def test_counts_html_img_tags() -> None:
    body = "\n".join(
        ["<img", 'src="media/x.png"', 'alt="One" />', "", "![two](b.png)", ""]
    )
    assert count_structure(body).images == 2


def test_ignores_images_in_fenced_code() -> None:
    body = "\n".join(
        ["![real](a.png)", "", "```", "![code](b.png)", "<img src=c.png>", "```", ""]
    )
    assert count_structure(body).images == 1


def _counts(
    headings_by_level: dict[int, int] | None = None,
    *,
    tables: int = 0,
    images: int = 0,
    display_formulas: int = 0,
    inline_formulas: int = 0,
) -> StructureCounts:
    """Build a StructureCounts with zero defaults for unspecified fields."""
    return StructureCounts(
        headings_by_level=headings_by_level or {},
        tables=tables,
        images=images,
        display_formulas=display_formulas,
        inline_formulas=inline_formulas,
    )


def test_compare_reports_per_level_heading_drift() -> None:
    reference = _counts(headings_by_level={2: 2, 3: 1})
    output = _counts(headings_by_level={2: 3})
    diffs = compare_structure(reference, output)
    kinds = {d.kind for d in diffs}
    assert kinds == {"headings_h2", "headings_h3"}


def test_compare_within_tolerance_is_clean() -> None:
    reference = _counts(headings_by_level={1: 1}, tables=2, images=3)
    output = _counts(headings_by_level={1: 1}, tables=2, images=2)
    diffs = compare_structure(reference, output)
    assert [d.kind for d in diffs] == ["images"]
    assert compare_structure(reference, output, image_tolerance=1) == []


def test_compare_exact_match_is_empty() -> None:
    counts = _counts(headings_by_level={1: 1, 2: 2}, tables=1, images=1)
    assert compare_structure(counts, counts) == []


# ---- formula counting --------------------------------------------------------


def test_counts_display_formulas() -> None:
    body = "\n".join(["$$x = 1.$$", "", "$$y = 2.$$", ""])
    counts = count_structure(body)
    assert counts.display_formulas == 2
    assert counts.inline_formulas == 0
    assert counts.formulas_total == 2


def test_counts_inline_formulas() -> None:
    body = "Let $a + b = c$ and also $x^2 = y$.\n"
    counts = count_structure(body)
    assert counts.inline_formulas == 2
    assert counts.display_formulas == 0
    assert counts.formulas_total == 2


def test_display_formulas_not_counted_as_inline() -> None:
    body = "$$\\int_0^{1} x \\, dx = \\frac{1}{2}.$$\n"
    counts = count_structure(body)
    assert counts.display_formulas == 1
    assert counts.inline_formulas == 0


def test_ignores_formulas_in_fenced_code() -> None:
    body = "\n".join(["# Title", "", "```", "$$formula$$", "$inline$", "```", ""])
    counts = count_structure(body)
    assert counts.display_formulas == 0
    assert counts.inline_formulas == 0


def test_compare_formula_tolerance() -> None:
    reference = _counts(display_formulas=4, inline_formulas=12)
    output = _counts(display_formulas=3, inline_formulas=11)
    diffs_strict = compare_structure(reference, output)
    assert {d.kind for d in diffs_strict} == {"display_formulas", "inline_formulas"}
    display_only = compare_structure(reference, output, display_formula_tolerance=1)
    assert {d.kind for d in display_only} == {"inline_formulas"}
    assert (
        compare_structure(
            reference, output, display_formula_tolerance=1, inline_formula_tolerance=1
        )
        == []
    )


def test_compare_can_skip_headings() -> None:
    reference = _counts(headings_by_level={2: 5, 3: 3}, tables=1)
    output = _counts(headings_by_level={2: 3, 4: 5}, tables=2)
    diffs = compare_structure(reference, output)
    assert any(d.kind.startswith("headings_") for d in diffs)
    skipped = compare_structure(reference, output, check_headings=False)
    assert [d.kind for d in skipped] == ["tables"]


def test_counts_gfm_fenced_math_block() -> None:
    body = "\n".join(
        [
            "Energy is $`E = mc^2`$ here.",
            "",
            "``` math",
            "\\int_0^1 x \\, dx",
            "```",
            "",
        ]
    )
    counts = count_structure(body)
    assert counts.display_formulas == 1
    assert counts.inline_formulas == 1
