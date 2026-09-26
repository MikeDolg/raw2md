"""Persisted counter for a model's declared `rpd` (requests per day).

The count survives a process restart, because the provider's quota does not
reset when raw2md does. It is keyed by the model's own name, not by its
settings entry: two entries that name one model share one quota. The day
boundary is an IANA zone that the caller resolves, and each model keeps its own
date, because two models in the file can declare different zones.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from raw2md.output import atomic_write_text
from raw2md.paths import rpd_file

# A version mismatch reads as "nothing spent today": the file is a safety
# margin against a quota overrun, not a ledger.
_VERSION = 2


def _now() -> datetime:
    """Current instant; a seam tests replace to control the day boundary."""
    return datetime.now(UTC)


def _today(zone: str) -> str:
    return _now().astimezone(ZoneInfo(zone)).date().isoformat()


def _load(path: Path) -> dict[str, dict[str, Any]]:
    """Per-model records; a missing, foreign, or unversioned file reads empty."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get("version") != _VERSION:
        return {}
    counts = data.get("counts")
    if not isinstance(counts, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for model, entry in counts.items():
        if not isinstance(entry, dict):
            continue
        date = entry.get("date")
        count = entry.get("count")
        if not isinstance(date, str):
            continue
        if not isinstance(count, int) or isinstance(count, bool):
            continue
        result[str(model)] = {"date": date, "count": count}
    return result


def _save(path: Path, counts: dict[str, dict[str, Any]]) -> None:
    envelope = {"version": _VERSION, "counts": counts}
    atomic_write_text(path, json.dumps(envelope, ensure_ascii=False))


def has_room(model: str, limit: int, zone: str, *, path: Path | None = None) -> bool:
    """Whether one more request still fits `model`'s daily budget.

    Read-only, so a caller can fail fast before any network work. The count is
    committed by `reserve_request` when a request is really sent.
    """
    target = path if path is not None else rpd_file()
    entry = _load(target).get(model)
    if entry is None or entry["date"] != _today(zone):
        return True
    return bool(entry["count"] < limit)


def reserve_request(
    model: str, limit: int, zone: str, *, path: Path | None = None
) -> bool:
    """Count one more request against `model`'s daily budget, if there is room.

    An entry from a previous day in `zone` starts back at zero. Returns False,
    and records nothing, once `limit` requests are spent today. The
    read-modify-write takes no lock of its own: the run lock serializes it.
    """
    target = path if path is not None else rpd_file()
    counts = _load(target)
    today = _today(zone)
    entry = counts.get(model)
    used = entry["count"] if entry is not None and entry["date"] == today else 0
    if used >= limit:
        return False
    counts[model] = {"date": today, "count": used + 1}
    _save(target, counts)
    return True
