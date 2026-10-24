"""A list item loses its leading bullet and keeps the dashes in its text."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ._helpers import Loader


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("- In - process loop", " In - process loop"),
        ("<b>\u2022 Kleiber - Serie</b>", "<b> Kleiber - Serie</b>"),
        ("\u2013 a \u2014 b - c", " a \u2014 b - c"),
        ("plain - text", "plain - text"),
    ],
)
def test_only_the_leading_bullet_is_removed(
    engine: Loader, html: str, expected: str
) -> None:
    module = engine("marker.schema.blocks.listitem")
    line = SimpleNamespace(
        id=SimpleNamespace(block_type=engine("marker.schema").BlockTypes.Line),
        children=[],
        html=html,
    )
    module.replace_bullets([line])
    assert line.html == expected
