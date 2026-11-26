"""The rules that pick a layer line for a re-read and accept its new text."""

from __future__ import annotations

import types
from collections.abc import Iterator

import pytest

from ._helpers import Loader, engine_copy


@pytest.fixture
def ocr(engine_loader: Loader) -> types.ModuleType:
    return engine_loader("marker.builders.ocr")


@pytest.fixture
def engine_loader() -> Iterator[Loader]:
    with engine_copy() as load:
        yield load


def test_caret_marks_a_line(ocr: types.ModuleType) -> None:
    assert ocr.has_layer_mark("## ^ ^Jnstal1ati0n Gu1de^")


def test_replacement_char_marks_a_line(ocr: types.ModuleType) -> None:
    assert ocr.has_layer_mark(f"Setup {chr(0xFFFD)} guide")


def test_clean_line_is_not_marked(ocr: types.ModuleType) -> None:
    assert not ocr.has_layer_mark("Installation Guide 3.4-5")


def test_center_inside_a_block(ocr: types.ModuleType) -> None:
    blocks = [[0.0, 0.0, 100.0, 100.0]]
    assert ocr.bbox_center_in_blocks([40.0, 40.0, 60.0, 50.0], blocks)


def test_center_outside_with_edge_overlap(ocr: types.ModuleType) -> None:
    blocks = [[0.0, 0.0, 100.0, 100.0]]
    assert not ocr.bbox_center_in_blocks([90.0, 40.0, 130.0, 50.0], blocks)


def test_center_without_blocks(ocr: types.ModuleType) -> None:
    assert not ocr.bbox_center_in_blocks([0.0, 0.0, 10.0, 10.0], [])


def test_excluded_blocks_name_the_issue_types(ocr: types.ModuleType) -> None:
    names = {block.name for block in ocr.REREAD_EXCLUDED_BLOCKS}
    assert names == {"Picture", "Figure", "Table", "Form", "TableOfContents"}


@pytest.mark.parametrize(
    ("length", "limit"),
    [
        (0, 64),
        (5, 64),
        (6, 128),
        (26, 128),
        (27, 256),
        (69, 256),
        (70, 512),
        (154, 512),
        (155, 512),
        (2000, 512),
    ],
)
def test_token_limit_steps(ocr: types.ModuleType, length: int, limit: int) -> None:
    assert ocr.reread_token_limit("x" * length) == limit


def test_accepts_clean_text(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("## Installation Guide")


@pytest.mark.parametrize("text", ["", "   "])
def test_rejects_empty_text(ocr: types.ModuleType, text: str) -> None:
    assert not ocr.accept_reread(text)


@pytest.mark.parametrize("text", ["Guide ^ here", f"Guide {chr(0xFFFD)} here"])
def test_rejects_mark_outside_math(ocr: types.ModuleType, text: str) -> None:
    assert not ocr.accept_reread(text)


def test_accepts_caret_inside_math(ocr: types.ModuleType) -> None:
    text = 'Power <math display="inline">x^2 + y^3</math> of two'
    assert ocr.accept_reread(text)


def test_rejects_caret_after_math(ocr: types.ModuleType) -> None:
    text = "Power <math>x^2</math> then ^"
    assert not ocr.accept_reread(text)


def test_rejects_repeat_of_five(ocr: types.ModuleType) -> None:
    assert not ocr.accept_reread("Total " + "abc" * 5)


def test_accepts_repeat_of_four(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("Total " + "abc" * 4)


def test_accepts_short_group_repeated(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("Rule " + "ab" * 8)


def test_rejects_empty_group_inside_math(ocr: types.ModuleType) -> None:
    assert not ocr.accept_reread("Value <math>x_{}</math>")


def test_accepts_empty_group_outside_math(ocr: types.ModuleType) -> None:
    assert ocr.accept_reread("Set {} is empty")
