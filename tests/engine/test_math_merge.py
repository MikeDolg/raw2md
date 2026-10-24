"""Merging of consecutive inline math spans keeps the minus between them."""

from __future__ import annotations

import pytest

from ._helpers import Loader


@pytest.mark.parametrize(
    "html",
    [
        "<math>a^2 -</math> <math>b^2 = c</math>",
        "<math>a^2 -</math><math>b^2 = c</math>",
        '<math>a^2 -</math> <math display="inline">b^2 = c</math>',
    ],
)
def test_trailing_minus_survives_the_merge(engine: Loader, html: str) -> None:
    renderer = engine("marker.renderers").BaseRenderer
    merged = renderer.merge_consecutive_math(html)
    assert "-" in merged
    assert merged.startswith("<math>a^2 - ")
    assert merged.endswith("b^2 = c</math>")
