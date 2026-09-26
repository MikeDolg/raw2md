"""Tests for temp-root selection (RAW2MD_TMP, ASCII gate, writability)."""

from __future__ import annotations

from pathlib import Path

import pytest

from raw2md import temp as temp_mod
from raw2md.temp import TempPathError, select_temp_root


def test_env_override_is_used_and_created(tmp_path: Path) -> None:
    target = tmp_path / "explicit"
    root = select_temp_root(env={"RAW2MD_TMP": str(target)})
    assert root == target.absolute()
    assert root.is_dir()


def test_existing_folder_is_reused(tmp_path: Path) -> None:
    target = tmp_path / "explicit"
    target.mkdir()
    assert select_temp_root(env={"RAW2MD_TMP": str(target)}) == target.absolute()


def test_non_ascii_env_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(TempPathError):
        select_temp_root(env={"RAW2MD_TMP": str(tmp_path / "café")})


def test_unwritable_env_path_is_rejected(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="ascii")
    with pytest.raises(TempPathError):
        select_temp_root(env={"RAW2MD_TMP": str(blocker / "under")})


def test_default_temp_dir_when_home_is_ascii(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = select_temp_root(env={})
    assert root == (tmp_path / ".raw2md" / "tmp").absolute()


def test_fallback_when_home_is_non_ascii(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "папка")
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(temp_mod, "_fallback_root", lambda: fallback)
    assert select_temp_root(env={}) == fallback.absolute()
