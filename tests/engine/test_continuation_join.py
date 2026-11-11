"""A paragraph cut by a page keeps a dash and joins CJK text without a space."""

from __future__ import annotations

import pytest

from ._helpers import Loader

_HAN = chr(0x516C) + chr(0x53F8)
_HAN_TAIL = chr(0x6D4B) + chr(0x8BD5)
_FULL_COMMA = chr(0xFF0C)
_HANGUL = chr(0xD55C) + chr(0xAE00)
_HANGUL_TAIL = chr(0xB2E4) + chr(0xC74C)


def _render(engine: Loader, first: str, second: str) -> str:
    renderer = engine("marker.renderers.markdown").Markdownify(
        paginate_output=False,
        page_separator="-" * 48,
        inline_math_delimiters=("$", "$"),
        block_math_delimiters=("$$", "$$"),
        html_tables_in_markdown=False,
        escape_dollars=True,
    )
    html = (
        '<p block-type="Text" class="has-continuation">'
        f'{first}</p><p block-type="Text">{second}</p>'
    )
    return str(renderer.convert(html))


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("the ro-", "d and the plate", "the rod and the plate"),
        ("the ro¬", "d and the plate", "the rod and the plate"),
        ("the rod —", "and the plate", "the rod — and the plate"),
        ("the rod—", "and the plate", "the rod— and the plate"),
        (_HAN, _HAN_TAIL, _HAN + _HAN_TAIL),
        (_HAN + _FULL_COMMA, _HAN_TAIL, _HAN + _FULL_COMMA + _HAN_TAIL),
        (_HANGUL, _HANGUL_TAIL, f"{_HANGUL} {_HANGUL_TAIL}"),
        ("the rod", "and the plate", "the rod and the plate"),
    ],
)
def test_join_of_a_paragraph_cut_by_a_page(
    engine: Loader, first: str, second: str, expected: str
) -> None:
    assert _render(engine, first, second).strip() == expected
