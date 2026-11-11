"""The text fixer keeps fullwidth forms and curly quotes, and still repairs mojibake."""

from __future__ import annotations

import pytest

from ._helpers import Loader

# Ruff decodes a `\u` escape and flags the result, so the characters come by code point.
COMMA = chr(0xFF0C)
OPEN = chr(0xFF08)
CLOSE = chr(0xFF09)
LOW_QUOTE = chr(0x201E)
LEFT_DOUBLE = chr(0x201C)
LEFT_SINGLE = chr(0x2018)
RIGHT_SINGLE = chr(0x2019)
HAN = "".join(chr(code) for code in (0x516C, 0x53F8))


@pytest.mark.parametrize(
    "text",
    [
        f"{HAN}{COMMA}{OPEN}{HAN}{CLOSE}",
        f"{LOW_QUOTE}Zitat{LEFT_DOUBLE}",
        f"{LEFT_SINGLE}quoted{RIGHT_SINGLE} text",
    ],
)
def test_width_and_quotes_are_kept(engine: Loader, text: str) -> None:
    fix = engine("marker.util").fix_text_keep_width
    assert fix(text) == text


def test_mojibake_is_repaired(engine: Loader) -> None:
    fix = engine("marker.util").fix_text_keep_width
    broken = "The Mona Lisa doesn" + chr(0xE2) + chr(0x80) + chr(0x99) + "t."
    assert fix(broken) == f"The Mona Lisa doesn{RIGHT_SINGLE}t."


def test_math_takes_the_default_configuration(engine: Loader) -> None:
    fix = engine("marker.util").fix_text_keep_width
    assert fix(f"{OPEN}x{CLOSE}", math=True) == "(x)"
    assert fix(f"<math>{OPEN}x{RIGHT_SINGLE}{CLOSE}</math>") == "<math>(x')</math>"
    assert fix(f"{OPEN}a{CLOSE} <math>{OPEN}x{CLOSE}</math> {OPEN}b{CLOSE}") == (
        f"{OPEN}a{CLOSE} <math>(x)</math> {OPEN}b{CLOSE}"
    )
