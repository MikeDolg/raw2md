"""A span is a superscript or a subscript only when its glyphs leave the line."""

from __future__ import annotations

from typing import Any

import pytest

from ._helpers import Loader

# pdfium gives a blank character a zero-height box on the baseline. The text
# spans of one font run from y 75 to y 89, and the baseline is at y 87.
_TOP, _BOTTOM, _BASELINE = 75.0, 89.0, 87.0


def _span(engine: Loader, text: str, bbox: list[float]) -> dict[str, Any]:
    return {"text": text, "bbox": engine("pdftext.schema").Bbox(bbox)}


def _blank(engine: Loader, text: str, x: float, y: float = _BASELINE) -> dict[str, Any]:
    return _span(engine, text, [x, y, x, y])


def _scripts(engine: Loader, spans: list[dict[str, Any]]) -> list[str]:
    bbox = spans[0]["bbox"]
    for span in spans[1:]:
        bbox = bbox.merge(span["bbox"])
    engine("pdftext.pdf.pages").assign_scripts(
        [{"spans": spans, "bbox": bbox}], height_threshold=0.7
    )
    marks = []
    for span in spans:
        if span.get("superscript"):
            marks.append(f"^{span['text']}")
        elif span.get("subscript"):
            marks.append(f"_{span['text']}")
    return marks


def test_one_letter_word_in_a_tall_line_stays_plain(engine: Loader) -> None:
    # A heading whose page number in a larger font joins its line.
    spans = [
        _span(engine, "a", [70.0, _TOP, 78.0, _BOTTOM]),
        _blank(engine, " ", 79.0),
        _span(engine, "word", [82.0, _TOP, 120.0, _BOTTOM]),
        _blank(engine, " ", 121.0),
        _span(engine, "b", [124.0, _TOP, 131.0, _BOTTOM]),
        _span(engine, " more words ", [131.0, _TOP, 220.0, _BOTTOM]),
        _span(engine, "3", [560.0, 58.0, 575.0, _BASELINE]),
        _blank(engine, "\n", 575.0),
    ]
    assert _scripts(engine, spans) == []


def test_lowered_digit_before_a_line_break_is_a_subscript(engine: Loader) -> None:
    spans = [
        _span(engine, "made of Al", [56.0, 153.7, 212.0, 163.7]),
        _span(engine, "2", [212.0, 158.5, 216.0, 165.0]),
        _span(engine, "O", [216.0, 153.7, 224.0, 163.7]),
        _span(engine, "3", [224.0, 158.5, 228.0, 165.0]),
        _blank(engine, "\n", 228.0, 163.8),
    ]
    assert _scripts(engine, spans) == ["_2", "_3"]


@pytest.mark.parametrize("trailing", [" ", "\n"])
def test_raised_digit_is_a_superscript(engine: Loader, trailing: str) -> None:
    spans = [
        _span(engine, "area in mm", [56.0, 153.7, 110.0, 163.7]),
        _span(engine, "2", [110.0, 151.0, 114.0, 158.0]),
        _blank(engine, trailing, 114.0, 163.0),
        _span(engine, "is small", [117.0, 153.7, 160.0, 163.7]),
    ]
    assert _scripts(engine, spans) == ["^2"]
