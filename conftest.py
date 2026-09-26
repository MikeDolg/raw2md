"""Pytest session configuration for the whole test tree."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Markers gating heavy or multi-process tests; each is opt-in via `-m`.
_OPT_IN_MARKERS = ("roundtrip", "concurrency", "llm_live")


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect ~/.raw2md to an empty tmp tree for the duration of a test."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


class _OfflineModels:
    def list(self) -> list[Any]:
        return []


class _OfflineGenaiClient:
    """Answers the key probe as a valid key; any other call fails loudly."""

    def __init__(self, **kwargs: Any) -> None:
        self.models = _OfflineModels()


@pytest.fixture(autouse=True)
def _offline_genai_client(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep the fast layer off the network: the Gemini key probe is real code."""
    if any(request.node.get_closest_marker(m) for m in _OPT_IN_MARKERS):
        return
    monkeypatch.setattr("google.genai.Client", _OfflineGenaiClient)


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip opt-in marked tests unless that marker is explicitly requested."""
    mark_expr: str = str(config.getoption("markexpr", default=""))
    for marker in _OPT_IN_MARKERS:
        if marker in mark_expr:
            continue  # explicitly requested — do not skip these
        skip = pytest.mark.skip(
            reason=f"{marker} tests are opt-in; run with: uv run pytest -m {marker}"
        )
        for item in items:
            if item.get_closest_marker(marker):
                item.add_marker(skip)
