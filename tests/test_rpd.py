"""Tests for the persisted daily request counter (`rpd`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from raw2md.llm.rpd import reserve_request
from raw2md.paths import rpd_file

_UTC = "UTC"


def test_reserve_allows_up_to_the_limit(tmp_path: Path) -> None:
    path = tmp_path / "rpd.json"
    assert reserve_request("model-a", 2, _UTC, path=path) is True
    assert reserve_request("model-a", 2, _UTC, path=path) is True
    assert reserve_request("model-a", 2, _UTC, path=path) is False


def test_reserve_does_not_leak_between_models(tmp_path: Path) -> None:
    path = tmp_path / "rpd.json"
    assert reserve_request("model-a", 1, _UTC, path=path) is True
    assert reserve_request("model-a", 1, _UTC, path=path) is False
    # model-b's budget is untouched by model-a's exhaustion in the same file.
    assert reserve_request("model-b", 1, _UTC, path=path) is True


def test_reserve_resets_on_a_new_day(tmp_path: Path) -> None:
    path = tmp_path / "rpd.json"
    path.write_text(
        json.dumps(
            {"version": 2, "counts": {"model-a": {"date": "2000-01-01", "count": 99}}}
        ),
        encoding="utf-8",
    )
    assert reserve_request("model-a", 1, _UTC, path=path) is True


def test_reserve_zone_controls_the_day_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 05:00 UTC on 2026-01-01 is a different date twelve hours west and
    # fourteen hours east.
    monkeypatch.setattr(
        "raw2md.llm.rpd._now",
        lambda: datetime(2026, 1, 1, 5, 0, tzinfo=UTC),
    )
    path = tmp_path / "rpd.json"
    path.write_text(
        json.dumps(
            {"version": 2, "counts": {"model-a": {"date": "2025-12-31", "count": 1}}}
        ),
        encoding="utf-8",
    )
    # West of UTC the local date is still 2025-12-31, so the budget stays spent.
    assert reserve_request("model-a", 1, "Etc/GMT+12", path=path) is False
    # East of UTC the local date already rolled to 2026-01-01, a fresh day.
    assert reserve_request("model-a", 1, "Pacific/Kiritimati", path=path) is True


def test_reserve_ignores_a_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "rpd.json"
    path.write_text("{not json", encoding="utf-8")
    assert reserve_request("model-a", 1, _UTC, path=path) is True


def test_reserve_ignores_an_unversioned_file(tmp_path: Path) -> None:
    path = tmp_path / "rpd.json"
    path.write_text(json.dumps({"counts": {"model-a": 99}}), encoding="utf-8")
    assert reserve_request("model-a", 1, _UTC, path=path) is True


def test_reserve_default_path_is_under_state_dir(home: Path) -> None:
    assert reserve_request("model-a", 1, _UTC) is True
    assert rpd_file().exists()


def test_reserve_is_atomic_leaves_no_temp(tmp_path: Path) -> None:
    path = tmp_path / "rpd.json"
    reserve_request("model-a", 1, _UTC, path=path)
    assert list(tmp_path.iterdir()) == [path]
