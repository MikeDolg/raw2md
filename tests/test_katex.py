"""Tests for the KaTeX judge of math-span validity."""

from __future__ import annotations

from pathlib import Path

import pytest

from raw2md import katex
from raw2md.mdtext.formulas import is_valid_math
from raw2md.quality.evaluator import _closed_math_span_contents

CORPUS_DIR = Path(__file__).parent / "corpus"


@pytest.fixture(autouse=True)
def _clear_judge_cache() -> None:
    # The cache lives for the process.
    katex.renders.cache_clear()


@pytest.mark.parametrize(
    "content",
    [
        r"\frac{1}{2",  # a brace the recognition ate
        r"a & b",  # an alignment marker outside any environment
        r"\begin{array}{cc} a & b",  # an environment left open
        r"\left  F \right",  # a sizing command with no delimiter to size
        r"x_{a}_{b}",  # a double index
        r"\<",  # markup that is not LaTeX at all
    ],
)
def test_span_the_renderer_refuses_is_broken(content: str) -> None:
    assert not is_valid_math(content)


@pytest.mark.parametrize(
    "content",
    [
        r"a + b",
        r"\frac{\partial u}{\partial t} = \alpha \nabla^2 u",
        r"\left\lvert x \right\rvert",
        r"\left\{ \begin{matrix} a \\ b \end{matrix} \right.",
        # The align family renders in display mode only; the judge asks about
        # the formula, not its delimiters.
        r"\begin{align} a &= b \\ c &= d \end{align}",
        # A Cyrillic letter in math mode is a KaTeX warning, not an error.
        r"\text{площадь } S",
    ],
)
def test_span_the_renderer_accepts_is_whole(content: str) -> None:
    assert is_valid_math(content)


def test_span_that_recurses_past_the_host_stack_is_broken() -> None:
    # A loop over a scope-opening command recurses until the sandbox aborts;
    # the abort is an answer, and the judge works on.
    assert not is_valid_math("M " + "\\textstyle " * 200)
    assert is_valid_math("x^2 + 1")


@pytest.mark.parametrize("content", ["", "   ", "\n\n"])
def test_empty_span_is_broken_without_asking_the_renderer(content: str) -> None:
    # KaTeX renders an empty span, so the answer cannot come from it.
    assert not is_valid_math(content)
    assert katex.renders.cache_info().misses == 0


def test_the_same_content_asks_the_renderer_once() -> None:
    # A document repeats its formulas, and rules ask about a span repeatedly.
    for _ in range(3):
        assert is_valid_math(r"E = mc^2")
    # Surrounding whitespace is stripped first.
    assert is_valid_math("  E = mc^2  ")
    info = katex.renders.cache_info()
    assert info.misses == 1
    assert info.hits == 3


@pytest.mark.parametrize(
    "fixture",
    # README.md documents the corpus and quotes a delimiter in prose.
    sorted(path.name for path in CORPUS_DIR.glob("*.md") if path.name != "README.md"),
)
def test_every_formula_in_the_reference_corpus_renders(fixture: str) -> None:
    # The corpus is known-good, so a refusal is the judge's error.
    body = (CORPUS_DIR / fixture).read_text(encoding="utf-8")
    refused = [
        content
        for content in _closed_math_span_contents(body)
        if not is_valid_math(content)
    ]
    assert refused == []
