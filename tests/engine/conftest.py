"""Fixtures of the engine copy tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ._helpers import Loader, engine_copy


@pytest.fixture
def engine() -> Iterator[Loader]:
    """A loader of the engine copy modules, with torch hidden for the test."""
    with engine_copy() as load:
        yield load
