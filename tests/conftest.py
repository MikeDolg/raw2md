"""Pytest configuration for the test tree: opt-in markers, offline genai, fixtures."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from raw2md.config import RunConfig

# Markers gating heavy or multi-process tests; each is opt-in via `-m`.
_OPT_IN_MARKERS = ("roundtrip", "concurrency", "llm_live")

# The markers of the tests that run the real engine and need its weights.
_ENGINE_MARKERS = ("roundtrip", "llm_live")


@contextmanager
def _real_weights(request: pytest.FixtureRequest, test_home: Path) -> Iterator[None]:
    """Link the weights folder of a test home to the real one.

    An engine test then downloads the weights once, into the real folder, and
    reuses them across tests and runs. Windows takes a directory junction,
    which needs no privilege; Linux takes a symlink.
    """
    if not any(request.node.get_closest_marker(m) for m in _ENGINE_MARKERS):
        yield
        return
    real = Path.home() / ".raw2md" / "models"
    real.mkdir(parents=True, exist_ok=True)
    link = test_home / ".raw2md" / "models"
    link.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(real), str(link))
    else:
        link.symlink_to(real, target_is_directory=True)
    try:
        yield
    finally:
        # Removes the link only; the real folder keeps its files.
        link.unlink()


@pytest.fixture
def home(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    """Redirect ~/.raw2md to an empty tmp tree for the duration of a test.

    An engine test keeps the real weights folder.
    """
    with _real_weights(request, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        yield tmp_path


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


_FIXTURES = Path(__file__).parent / "fixtures"

# Fast-test defaults: every LLM stage off, isolation and safety flags on.
_DEFAULT_RUN_CONFIG = RunConfig(
    input_path=Path(),
    output_dir=None,
    skip_existing=False,
    yaml_header=True,
    extract_images=True,
    llm_ocr=None,
    llm_inspection=None,
    llm_post=None,
    llm_latex_fix=False,
    cuda=True,
    log_file=False,
    debug=False,
)


def make_run_config(input_path: Path, **overrides: object) -> RunConfig:
    """A RunConfig with fast-test defaults, overridden by keyword."""
    return replace(
        _DEFAULT_RUN_CONFIG,
        input_path=input_path,
        **overrides,  # type: ignore[arg-type]  # each override is field-typed at the caller, not here
    )


@contextmanager
def _home_with_config(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile: str,
) -> Iterator[Path]:
    raw2md = tmp_path / ".raw2md"
    raw2md.mkdir()
    source = _FIXTURES / profile
    shutil.copy(source / "settings.json", raw2md / "settings.json")
    shutil.copy(source / "prompts.yaml", raw2md / "prompts.yaml")
    with _real_weights(request, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        yield tmp_path


@pytest.fixture
def raw2md_home(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    """~/.raw2md preloaded with the deterministic offline test config.

    Providers are stubbed in-process, so the dummy key and command never run.
    """
    with _home_with_config(request, monkeypatch, tmp_path, "offline") as home:
        yield home


@pytest.fixture
def raw2md_home_real(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Path]:
    """~/.raw2md preloaded with the real-model config for opt-in round-trip.

    Credentials come from the environment (``key_env``).
    """
    with _home_with_config(request, monkeypatch, tmp_path, "real") as home:
        yield home
