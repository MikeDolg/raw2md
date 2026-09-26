"""Fixtures for the pipeline tests: fast-test RunConfig and ~/.raw2md profiles."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from raw2md.config import RunConfig

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


def _home_with_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profile: str
) -> Path:
    raw2md = tmp_path / ".raw2md"
    raw2md.mkdir()
    source = _FIXTURES / profile
    shutil.copy(source / "settings.json", raw2md / "settings.json")
    shutil.copy(source / "prompts.yaml", raw2md / "prompts.yaml")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def raw2md_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """~/.raw2md preloaded with the deterministic offline test config.

    Providers are stubbed in-process, so the dummy key and command never run.
    """
    return _home_with_config(monkeypatch, tmp_path, "offline")


@pytest.fixture
def raw2md_home_real(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """~/.raw2md preloaded with the real-model config for opt-in round-trip.

    Credentials come from the environment (``key_env``).
    """
    return _home_with_config(monkeypatch, tmp_path, "real")
