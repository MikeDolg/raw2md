"""Tests for the cleaning coordinator itself.

Covered here: whitespace normalization, the protected zones, page marks, and
idempotency. Each rule is tested next to its module under `tests/cleaning/`.
"""

from __future__ import annotations

from pathlib import Path

from raw2md.cleaner import CleanOptions, clean, clean_in_place
from raw2md.header import ConversionMethod
from raw2md.mdtext.pages import page_mark, page_mark_number, split_page_marks


def _corpus_fixtures() -> list[Path]:
    # README.md documents the corpus and is not a fixture.
    return sorted(
        path for path in Path("tests/corpus").glob("*.md") if path.name != "README.md"
    )


# ---- blank lines -------------------------------------------------------------


def test_collapses_runs_of_blank_lines() -> None:
    assert clean_in_place("a\n\n\n\nb\n") == "a\n\nb\n"


def test_keeps_a_single_blank_between_paragraphs() -> None:
    assert clean_in_place("a\n\nb\n") == "a\n\nb\n"


def test_trims_leading_and_trailing_blank_lines() -> None:
    assert clean_in_place("\n\na\n\n\n") == "a\n"


def test_blank_only_input_becomes_empty() -> None:
    assert clean_in_place("\n\n   \n\t\n") == ""


def test_empty_input_stays_empty() -> None:
    assert clean_in_place("") == ""


def test_appends_a_single_trailing_newline() -> None:
    assert clean_in_place("a") == "a\n"


# ---- trailing spaces ---------------------------------------------------------


def test_strips_trailing_spaces() -> None:
    assert clean_in_place("abc   \n") == "abc\n"


def test_strips_trailing_tabs() -> None:
    assert clean_in_place("abc\t\t\n") == "abc\n"


def test_whitespace_only_line_collapses_as_blank() -> None:
    assert clean_in_place("a\n   \nb\n") == "a\n\nb\n"


# ---- protected zone: code fences ---------------------------------------------


def test_fence_content_is_kept_verbatim() -> None:
    text = "```\n##nospace\n   \n=====\n```\nafter   \n"
    # Inside the fence nothing is touched; the line after it is still cleaned.
    assert clean_in_place(text) == "```\n##nospace\n   \n=====\n```\nafter\n"


def test_tilde_fence_is_protected() -> None:
    text = "~~~\n##x\n~~~\n"
    assert clean_in_place(text) == text


def test_fence_close_needs_empty_info_string() -> None:
    # `\`\`\` x` carries an info string, so it is not a closer; the fence runs on.
    text = "```\na\n``` x\n=====\n```\nb\n"
    assert clean_in_place(text) == "```\na\n``` x\n=====\n```\nb\n"


def test_unclosed_fence_protects_to_end_of_file() -> None:
    assert clean_in_place("```\n=====\nmore\n") == "```\n=====\nmore\n"


# ---- protected zone: HTML tables ---------------------------------------------


def test_html_table_is_kept_verbatim() -> None:
    text = "<table>\n  <tr><td>a   </td></tr>\n  =====\n</table>\n"
    assert clean_in_place(text) == text


def test_single_line_html_table_is_protected() -> None:
    assert clean_in_place("<table><tr><td>x   </td></tr></table>   \n") == (
        "<table><tr><td>x   </td></tr></table>   \n"
    )


def test_content_after_table_is_cleaned() -> None:
    text = "<table>\n<tr><td>a</td></tr>\n</table>\nafter   \n"
    assert clean_in_place(text) == "<table>\n<tr><td>a</td></tr>\n</table>\nafter\n"


def test_nested_html_table_resumes_cleanup_after_outer_close() -> None:
    text = (
        "<table>\n"
        "<tr><td>\n"
        "<table>\n"
        "<tr><td>x   </td></tr>\n"
        "</table>\n"
        "</td></tr>\n"
        "</table>\n"
        "after   \n"
    )
    # Cleanup waits for the outer `</table>`.
    assert clean_in_place(text) == (
        "<table>\n"
        "<tr><td>\n"
        "<table>\n"
        "<tr><td>x   </td></tr>\n"
        "</table>\n"
        "</td></tr>\n"
        "</table>\n"
        "after\n"
    )


# ---- protected zone: leading front matter ------------------------------------


def test_leading_front_matter_is_kept_verbatim() -> None:
    text = "---\nraw2md_version: 0.1.0\nstatus:  in_progress  \n---\n##Body\n"
    # Header lines keep their trailing spaces; the body is still cleaned.
    assert clean_in_place(text) == (
        "---\nraw2md_version: 0.1.0\nstatus:  in_progress  \n---\n## Body\n"
    )


def test_leading_dashes_without_close_are_a_thematic_break() -> None:
    # No closing `---`, so the opener is an ordinary thematic break, not a header.
    assert clean_in_place("---\n# Title\n") == "---\n# Title\n"


# ---- idempotency -------------------------------------------------------------


def test_cleaning_is_idempotent() -> None:
    text = (
        "---\nraw2md_version: 0.1.0\n---\n"
        "\n\n##Title\n\n\n=====\n## 1.1 A\n### 1.2 B\n"
        "trailing   \n```\n##keep\n```\n\n\n"
    )
    once = clean_in_place(text)
    assert clean_in_place(once) == once


def test_cleaning_reaches_a_fixed_point_on_every_corpus_fixture() -> None:
    # A rule that reads the whole document decides on what earlier rules left,
    # so leftover work of its own kind would grade a different document on the
    # second call.
    for path in _corpus_fixtures():
        for method in (None, ConversionMethod.MARKER, ConversionMethod.PANDOC):
            options = CleanOptions(method=method)
            once = clean(path.read_text(encoding="utf-8"), options)
            assert clean(once, options) == once, f"{path.name} / {method}"


def test_a_running_header_settles_in_one_pass() -> None:
    # Repeated running headers at different levels: one pass levels and drops
    # them together.
    text = "".join(
        f"{'#' * level} 2.2 Guide Rails\n\nPage {page} text.\n\n"
        for page, level in enumerate((2, 3, 2, 4, 3), start=1)
    )
    once = clean(text)
    assert once == (
        "## 2.2 Guide Rails\n\nPage 1 text.\n\nPage 2 text.\n\n"
        "Page 3 text.\n\nPage 4 text.\n\nPage 5 text.\n"
    )
    assert clean(once) == once


# ---- page marks --------------------------------------------------------------


def test_page_mark_survives_cleaning() -> None:
    # A mark the cleaner ate would take its page boundary with it.
    text = "\n".join(["# Title", "", page_mark(2), "Page two opens here.", ""])
    assert page_mark(2) in clean(text, CleanOptions())


def test_page_marks_do_not_change_what_cleaning_produces() -> None:
    # Marks exist only under inspection, so cleaning must reach the same body
    # either way.
    for path in _corpus_fixtures():
        plain = path.read_text(encoding="utf-8")
        lines = plain.split("\n")
        # A mark every eight lines, directly above its line.
        marked = "\n".join(
            f"{page_mark(index // 8 + 1)}\n{line}" if index % 8 == 0 else line
            for index, line in enumerate(lines)
        )
        cleaned_plain = clean(plain, CleanOptions())
        cleaned_marked, pages = split_page_marks(clean(marked, CleanOptions()))
        assert cleaned_marked == cleaned_plain, path.name
        assert pages, path.name


def test_split_page_marks_returns_the_map_of_the_stripped_body() -> None:
    text = "\n".join(["# Title", "", page_mark(2), "Second page.", ""])

    body, pages = split_page_marks(text)

    assert body == "\n".join(["# Title", "", "Second page.", ""])
    assert pages == ((2, 2),)


def test_split_page_marks_leaves_an_unmarked_body_alone() -> None:
    text = "# Title\n\nJust text.\n"

    assert split_page_marks(text) == (text, ())


def test_split_page_marks_reaches_into_a_protected_zone() -> None:
    # A mark inside a fence must never reach the written result.
    text = "\n".join(["```", "code line", page_mark(3), "more code", "```", ""])

    body, pages = split_page_marks(text)

    assert page_mark(3) not in body
    assert pages == ((2, 3),)


def test_page_mark_number_reads_only_a_mark_line() -> None:
    assert page_mark_number(page_mark(7)) == 7
    assert page_mark_number("<!-- a comment of another kind -->") is None
    assert page_mark_number("text about page 7") is None


def test_page_marks_do_not_change_cleaning_of_a_defective_body() -> None:
    # Every rule acts on this body; marks sit above lines that open a block,
    # as a route places them.
    plain = "\n".join(
        [
            "##Heading without a space",
            "",
            "**1.2. Bold paragraph title**",
            "",
            "A word split coeffi-",
            "cient across lines.",
            "",
            "| A | B |",
            "| --- | --- |",
            "| x |",
            "",
            "1. first",
            "3. third",
            "",
            "Trailing spaces here.   ",
            "",
        ]
    )
    lines = plain.split("\n")
    marked: list[str] = []
    page = 0
    for index, line in enumerate(lines):
        if line.strip() and (index == 0 or not lines[index - 1].strip()):
            page += 1
            marked.append(page_mark(page))
        marked.append(line)

    cleaned_marked, pages = split_page_marks(clean("\n".join(marked), CleanOptions()))

    assert cleaned_marked == clean(plain, CleanOptions())
    assert len(pages) == page
