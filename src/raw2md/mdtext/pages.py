"""Page marks and lost-page markers in a body.

A page mark is working markup that carries a source page boundary through
cleaning and is removed when cleaning ends. A lost-page marker is visible text
that stands in for a page the recognizer could not read. Each writer lives
beside its reader, so the two cannot drift.
"""

from __future__ import annotations

import re

# Matched on a line of its own, so a mention inside prose is no loss.
_LOST_PAGE_RE = re.compile(r"^\[page \d+ not recognized\]$")

# Working markup above each source page, 1-based; removed when cleaning ends.
_PAGE_MARK_RE = re.compile(r"^<!-- raw2md:page (\d+) -->$")


def lost_page_marker(page: int) -> str:
    """The body line standing in for a source page LLM-OCR could not transcribe.

    Visible text, not a comment: it tells a reader which page to convert
    again. Shaped like the OCR prompt's `[unreadable]`; the page is 1-based.
    """
    return f"[page {page} not recognized]"


def is_lost_page_marker(line: str) -> bool:
    """True when `line` is a lost-page marker and nothing else."""
    return _LOST_PAGE_RE.match(line.strip()) is not None


def page_mark(page: int) -> str:
    """The line marking where source page `page` (1-based) starts in the body.

    Carries the page boundary through cleaning, which moves lines, for
    inspection. It sits right above the page's first line, so removing it
    restores the blank-line layout. `split_page_marks` removes it on every
    route.
    """
    return f"<!-- raw2md:page {page} -->"


def page_mark_number(line: str) -> int | None:
    """The 1-based page number of a page-mark line, or None if not one."""
    match = _PAGE_MARK_RE.match(line.strip())
    return int(match.group(1)) if match is not None else None


def split_page_marks(text: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    """Remove page marks from `text`, returning the body and the page map.

    The map pairs a 0-based line of the returned text with the 1-based page
    starting there. Marks inside protected zones go too.
    """
    out: list[str] = []
    pages: list[tuple[int, int]] = []
    for line in text.split("\n"):
        page = page_mark_number(line)
        if page is None:
            out.append(line)
            continue
        pages.append((len(out), page))
    return "\n".join(out), tuple(pages)
