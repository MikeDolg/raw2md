"""The text tests at the seam of a cut paragraph, shared by engine and cleaning."""

from __future__ import annotations

import pytest

from raw2md.mdtext.seams import (
    closes_sentence,
    continues_without_case,
    first_half_runs_on,
    second_half_runs_on,
)

_IDEOGRAPHIC_STOP = chr(0x3002)
_FULLWIDTH_STOP = chr(0xFF0E)
_HALFWIDTH_STOP = chr(0xFF61)
_FULLWIDTH_EXCLAMATION = chr(0xFF01)
_FULLWIDTH_QUESTION = chr(0xFF1F)
_FULLWIDTH_COLON = chr(0xFF1A)
_FULLWIDTH_SEMICOLON = chr(0xFF1B)
_ELLIPSIS = chr(0x2026)
_HAN = chr(0x516C) + chr(0x53F8)
_FULLWIDTH_COMMA = chr(0xFF0C)
_FULLWIDTH_QUOTE = chr(0xFF02)
_FULLWIDTH_APOSTROPHE = chr(0xFF07)
_RIGHT_CORNER_BRACKET = chr(0x300D)
_RIGHT_DOUBLE_QUOTE = chr(0x201D)
_LEFT_GUILLEMET = chr(0x00AB)
_RIGHT_GUILLEMET = chr(0x00BB)
_IDEOGRAPHIC_COMMA = chr(0x3001)
_FULLWIDTH_RIGHT_PARENTHESIS = chr(0xFF09)
_PUMP_FIRST = f"每台水泵都有一个阀门。该泵在水箱压力低于设定值时启动{_FULLWIDTH_COMMA}"
_PUMP_SECOND = f"并在水箱满时停止{_FULLWIDTH_COMMA}然后等待下一个信号。"


@pytest.mark.parametrize(
    "text",
    [
        "The valve opens.",
        "Does the valve open?",
        "It opens!",
        "The values follow:",
        "the first value;",
        "and so on" + _ELLIPSIS,
        "and so on...",
        _HAN + _IDEOGRAPHIC_STOP,
        _HAN + _FULLWIDTH_STOP,
        _HAN + _HALFWIDTH_STOP,
        _HAN + _FULLWIDTH_EXCLAMATION,
        _HAN + _FULLWIDTH_QUESTION,
        _HAN + _FULLWIDTH_COLON,
        _HAN + _FULLWIDTH_SEMICOLON,
    ],
)
def test_sentence_mark_closes(text: str) -> None:
    assert closes_sentence(text)


@pytest.mark.parametrize(
    "text",
    [
        'He said "it opens."',
        "He said 'it opens.'",
        "(It opens.)",
        "[It opens.]",
        "It opens.)]",
        "He said " + _RIGHT_DOUBLE_QUOTE + "it opens." + _RIGHT_DOUBLE_QUOTE,
        _LEFT_GUILLEMET + "It opens." + _RIGHT_GUILLEMET,
        _HAN + _IDEOGRAPHIC_STOP + _RIGHT_CORNER_BRACKET,
        _HAN + _IDEOGRAPHIC_STOP + _FULLWIDTH_QUOTE,
        _HAN + _IDEOGRAPHIC_STOP + _FULLWIDTH_APOSTROPHE,
    ],
)
def test_quotes_and_brackets_after_the_mark_close(text: str) -> None:
    assert closes_sentence(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "the valve opens",
        "the valve opens,",
        "the valve opens -",
        "the valve (opens)",
        '"the valve opens"',
        _HAN,
        _HAN + _FULLWIDTH_COMMA,
        "The valve opens. ",
    ],
)
def test_text_without_a_final_mark_runs_on(text: str) -> None:
    assert not closes_sentence(text)


def test_brackets_alone_close_nothing() -> None:
    assert not closes_sentence(")]" + _RIGHT_DOUBLE_QUOTE)


@pytest.mark.parametrize(
    ("tail", "runs_on"),
    [
        ("the valve opens when the", True),
        ("the valve opens,", True),
        ("The valve opens.", False),
        ("", False),
    ],
)
def test_first_half_runs_on_without_a_sentence_mark(tail: str, runs_on: bool) -> None:
    assert first_half_runs_on(tail) is runs_on


@pytest.mark.parametrize(
    ("head", "runs_on"),
    [
        ("valve stays closed.", True),
        ("b.c. stands for the base case.", True),
        ("Valve stays closed.", False),
        ("b) Elongation as a decimal:", False),
        ("b. Elongation as a decimal:", False),
        (_PUMP_SECOND, False),
        ("", False),
    ],
)
def test_second_half_runs_on_from_a_lowercase_word(head: str, runs_on: bool) -> None:
    assert second_half_runs_on(head) is runs_on


@pytest.mark.parametrize(
    ("tail", "continues"),
    [
        (_PUMP_FIRST, True),
        (_PUMP_FIRST[:-1], True),
        (_PUMP_FIRST[:-1] + _IDEOGRAPHIC_COMMA, True),
        (_PUMP_FIRST[:-1] + ",", True),
        (_PUMP_FIRST[:-1] + _IDEOGRAPHIC_STOP, False),
        (_PUMP_FIRST[:-1] + _FULLWIDTH_COLON, False),
        (_PUMP_FIRST[:-1] + "3", False),
        ("水" * 19 + _FULLWIDTH_COMMA, True),
        ("水" * 18 + _FULLWIDTH_COMMA, False),
        ("水" * 10 + " " * 10 + "水" * 8 + _FULLWIDTH_COMMA, False),
    ],
)
def test_caseless_first_half_needs_twenty_characters_and_an_open_end(
    tail: str, continues: bool
) -> None:
    assert continues_without_case(tail, _PUMP_SECOND) is continues


@pytest.mark.parametrize(
    ("head", "continues"),
    [
        ("二号阀门在水箱满时关闭。", True),
        (f"二{_IDEOGRAPHIC_COMMA}水箱满时停止。", False),
        (f"十{_FULLWIDTH_RIGHT_PARENTHESIS}水箱满时停止。", False),
        ("3. The tank is full.", False),
        ("valve stays closed.", False),
    ],
)
def test_caseless_second_half_opens_with_a_caseless_letter_and_no_item(
    head: str, continues: bool
) -> None:
    assert continues_without_case(_PUMP_FIRST, head) is continues
