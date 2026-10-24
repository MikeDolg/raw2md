"""A running header that alternates between even and odd pages is ignored."""

from __future__ import annotations

from types import SimpleNamespace

from ._helpers import Loader

_PAGES = 40
_CHAPTERS = ("Basic Terms", "Field Methods", "Sample Storage", "Final Notes")


def _block(page: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        page_id=page,
        raw_text=lambda document: text,
        ignore_for_output=False,
    )


def _filter(engine: Loader, blocks: list[SimpleNamespace]) -> list[bool]:
    processor = engine("marker.processors.ignoretext").IgnoreTextProcessor()
    processor.filter_common_elements(SimpleNamespace(), blocks)
    return [b.ignore_for_output for b in blocks]


def _chapter_header(page: int) -> str:
    # Ten pages a chapter: each chapter header shows on five odd pages, less
    # than the share of pages that makes a header common by its count.
    return f"{page + 1} {_CHAPTERS[page // 10]}"


def test_chapter_header_on_odd_pages_is_ignored(engine: Loader) -> None:
    blocks = [
        _block(page, _chapter_header(page) if page % 2 else f"Field Guide {page + 1}")
        for page in range(_PAGES)
    ]

    assert _filter(engine, blocks) == [True] * _PAGES


def test_header_on_one_parity_needs_three_pages_in_a_row(engine: Loader) -> None:
    # Four repeats of a short header, but each parity holds only two in a row.
    texts = ["Short Header", "a", "Short Header", "b", "c", "d", "e", "f"]
    texts += ["g", "Short Header", "h", "Short Header", "i", "j", "k", "l"]
    texts += ["m", "n", "o", "p", "q", "r", "s", "t"]
    blocks = [_block(page, text) for page, text in enumerate(texts)]

    assert not any(_filter(engine, blocks))
