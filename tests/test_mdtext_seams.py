"""The text tests at the seam of a cut paragraph, shared by engine and cleaning."""

from __future__ import annotations

import pytest

from raw2md.mdtext.seams import closes_sentence

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
