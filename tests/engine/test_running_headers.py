"""A running header is ignored; a title that repeats in the text is kept."""

from __future__ import annotations

from types import SimpleNamespace

from ._helpers import Loader

_PAGES = 40
_CHAPTERS = ("Basic Terms", "Field Methods", "Sample Storage", "Final Notes")
_PAGE_HEIGHT = 1000.0
_HEADER_TOP = 50.0


def _block(page: int, text: str, top: float = _HEADER_TOP) -> SimpleNamespace:
    return SimpleNamespace(
        page_id=page,
        polygon=SimpleNamespace(y_start=top),
        raw_text=lambda document: text,
        ignore_for_output=False,
    )


def _document() -> SimpleNamespace:
    page = SimpleNamespace(polygon=SimpleNamespace(y_start=0.0, height=_PAGE_HEIGHT))
    return SimpleNamespace(get_page=lambda page_id: page)


def _filter(engine: Loader, blocks: list[SimpleNamespace]) -> list[bool]:
    processor = engine("marker.processors.ignoretext").IgnoreTextProcessor()
    processor.filter_common_elements(_document(), blocks)
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


def test_header_across_pages_without_text_blocks_is_kept(engine: Loader) -> None:
    # Pages 0, 10, 20, 30 hold the header; the pages between hold no block.
    blocks = [_block(page, "Instructions") for page in (0, 10, 20, 30)]
    blocks += [_block(page, f"Unique text {page}") for page in range(1, 40, 2)]
    blocks.sort(key=lambda b: b.page_id)

    flags = _filter(engine, blocks)

    header_flags = [
        flag
        for flag, block in zip(flags, blocks, strict=True)
        if block.raw_text(None) == "Instructions"
    ]

    assert header_flags == [False] * 4


def test_header_on_one_parity_needs_three_pages_in_a_row(engine: Loader) -> None:
    # Four repeats of a short header, but each parity holds only two in a row.
    texts = ["Short Header", "a", "Short Header", "b", "c", "d", "e", "f"]
    texts += ["g", "Short Header", "h", "Short Header", "i", "j", "k", "l"]
    texts += ["m", "n", "o", "p", "q", "r", "s", "t"]
    blocks = [_block(page, text) for page, text in enumerate(texts)]

    assert not any(_filter(engine, blocks))


def test_copies_at_one_height_are_ignored(engine: Loader) -> None:
    # The copies of a running header move by a few thousandths of the page.
    tops = [50.0, 52.0, 49.0, 51.0, 55.0, 50.0, 48.0, 53.0]
    blocks = [_block(page, "Annual Review", top) for page, top in enumerate(tops)]

    assert _filter(engine, blocks) == [True] * len(tops)


def test_title_that_moves_down_the_page_is_kept(engine: Loader) -> None:
    tops = [310.0, 450.0, 580.0, 710.0, 360.0, 620.0]
    blocks = [_block(page, "Main Ideas", top) for page, top in enumerate(tops)]

    assert not any(_filter(engine, blocks))


def test_copy_away_from_the_header_height_is_kept(engine: Loader) -> None:
    tops = [50.0, 50.0, 50.0, 50.0, 600.0]
    blocks = [_block(page, "Annual Review", top) for page, top in enumerate(tops)]

    assert _filter(engine, blocks) == [True, True, True, True, False]


def test_two_copies_at_a_height_are_too_few(engine: Loader) -> None:
    # Each copy at 100 has one other copy there; the rest stand alone.
    tops = [100.0, 100.0, 400.0, 600.0, 800.0]
    blocks = [_block(page, "Main Ideas", top) for page, top in enumerate(tops)]

    assert not any(_filter(engine, blocks))


def test_numbered_captions_at_one_height_are_kept(engine: Loader) -> None:
    blocks = [_block(page, f"Tab. 3.{page + 1}", 760.0) for page in range(8)]

    assert not any(_filter(engine, blocks))


def test_text_key_keeps_a_number_after_a_dot(engine: Loader) -> None:
    clean_text = engine("marker.processors.ignoretext").IgnoreTextProcessor.clean_text

    assert clean_text("Tab. 3.4") != clean_text("Tab. 3.6")
    assert clean_text("Page 12") == "Page"
    assert clean_text("Tab. 34") == "Tab."
