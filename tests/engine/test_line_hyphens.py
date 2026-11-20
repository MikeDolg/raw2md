"""A line-end hyphen becomes a soft hyphen, and a dash stays."""

from __future__ import annotations

import pytest

from ._helpers import Loader

_SOFT = chr(0x00AD)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("the rod -", "the rod "),
        ("the ro-", f"the ro{_SOFT}"),
        ("the rod¬", f"the rod{_SOFT}"),
        ("the rod —", "the rod —"),
        ("the rod—", "the rod—"),
    ],
)
def test_only_a_hyphen_is_marked_before_a_lowercase_line(
    engine: Loader, line: str, expected: str
) -> None:
    strip = engine("marker.schema.text.line").strip_trailing_hyphens
    assert strip(line, "and the plate", line) == expected


def test_hyphen_before_a_capital_line_stays(engine: Loader) -> None:
    strip = engine("marker.schema.text.line").strip_trailing_hyphens
    assert strip("the Anglo-", "Saxon plate", "the Anglo-") == "the Anglo-"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the ro-\nd and the plate", f"the ro{_SOFT}d and the plate"),
        ("the Anglo-\nSaxon plate", f"the Anglo{_SOFT}Saxon plate"),
    ],
)
def test_hyphenated_break_inside_a_span_is_marked(
    engine: Loader, text: str, expected: str
) -> None:
    span_class = engine("marker.schema.text.span").Span
    polygon = engine("marker.schema.polygon").PolygonBox.from_bbox([0, 0, 10, 10])
    span = span_class(
        text=text,
        formats=["plain"],
        polygon=polygon,
        font="Unknown",
        font_weight=0,
        font_size=0,
        minimum_position=0,
        maximum_position=0,
    )
    assert span.assemble_html(None, [], [], None) == expected
