"""The lines of one block join without a space where Han, kana, or fullwidth
signs meet, and with a space in a script that spaces its words."""

from __future__ import annotations

import pytest
from PIL import Image

from ._helpers import Loader

_PAGE = (0.0, 0.0, 600.0, 800.0)
_PUMP = "该泵在水箱压力低于设定值时"
_START = "启动" + chr(0xFF0C)
_STOP = "并在水箱满时停止。"
_SOFT = chr(0x00AD)


def _render(engine: Loader, lines: list[tuple[str, list[str]]]) -> str:
    polygon = engine("marker.schema.polygon").PolygonBox.from_bbox
    page = engine("marker.schema.groups.page").PageGroup(
        polygon=polygon(list(_PAGE)), page_id=0, structure=[]
    )
    page.lowres_image = Image.new("RGB", (600, 800), "white")
    page.highres_image = Image.new("RGB", (600, 800), "white")
    box = polygon([50.0, 100.0, 550.0, 100.0 + 20 * len(lines)])
    block = page.add_full_block(
        engine("marker.schema.blocks").Text(polygon=box, page_id=0)
    )
    page.add_structure(block)
    for index, (text, formats) in enumerate(lines):
        line_box = polygon([50.0, 100.0 + 20 * index, 550.0, 118.0 + 20 * index])
        line = page.add_full_block(
            engine("marker.schema.text.line").Line(polygon=line_box, page_id=0)
        )
        span = page.add_full_block(
            engine("marker.schema.text.span").Span(
                text=text + "\n",
                formats=formats,
                polygon=line_box,
                page_id=0,
                font="Unknown",
                font_weight=0,
                font_size=0,
                minimum_position=0,
                maximum_position=0,
            )
        )
        line.add_structure(span)
        block.add_structure(line)
    document = engine("marker.schema.document").Document(
        filepath="invented.pdf", pages=[page]
    )
    renderer = engine("marker.renderers.markdown").MarkdownRenderer({})
    return str(renderer(document).markdown).strip()


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        (_PUMP, _START + _STOP, _PUMP + _START + _STOP),
        (_PUMP + _START, _STOP, _PUMP + _START + _STOP),
        ("ポンプは水位が低いと", "動き出す。", "ポンプは水位が低いと動き出す。"),
        ("펌프는 수위가 낮으면", "작동한다.", "펌프는 수위가 낮으면 작동한다."),
        (
            "The valve opens when the",
            "pressure rises.",
            "The valve opens when the pressure rises.",
        ),
        ("该泵的型号是", "AB-200 pump.", "该泵的型号是 AB-200 pump."),
        ("The pump type is AB-200", "型水泵。", "The pump type is AB-200 型水泵。"),
        ("the ro-", "d and the plate", f"the ro{_SOFT}d and the plate"),
        ("the Anglo-", "Saxon plate", "the Anglo-Saxon plate"),
    ],
)
def test_lines_of_one_block(
    engine: Loader, first: str, second: str, expected: str
) -> None:
    lines = [(first, ["plain"]), (second, ["plain"])]

    assert _render(engine, lines) == expected


def test_line_that_ends_in_a_format_joins_without_a_space(engine: Loader) -> None:
    lines = [("该泵的型号", ["bold"]), ("在铭牌上。", ["plain"])]

    assert _render(engine, lines) == "**该泵的型号**在铭牌上。"
