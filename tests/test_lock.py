"""Tests for the single-run advisory lock (mutual exclusion, crash recovery)."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from raw2md.lock import LockHeldError, LockRecord, RunLock
from raw2md.paths import lock_file


def test_acquire_writes_own_record(tmp_path: Path) -> None:
    path = tmp_path / "lock"
    lock = RunLock(path)
    lock.acquire()
    try:
        record = LockRecord.from_text(path.read_text(encoding="utf-8"))
        assert record is not None
        assert record.pid == os.getpid()
    finally:
        lock.release()


def test_acquire_refused_while_held(tmp_path: Path) -> None:
    path = tmp_path / "lock"
    held = RunLock(path)
    held.acquire()
    try:
        with pytest.raises(LockHeldError) as excinfo:
            RunLock(path).acquire()
        assert excinfo.value.pid == os.getpid()
    finally:
        held.release()


def test_release_allows_reacquire(tmp_path: Path) -> None:
    path = tmp_path / "lock"
    first = RunLock(path)
    first.acquire()
    first.release()
    second = RunLock(path)
    second.acquire()
    second.release()


def test_context_manager_releases_on_exit(tmp_path: Path) -> None:
    path = tmp_path / "lock"
    with RunLock(path), pytest.raises(LockHeldError):
        RunLock(path).acquire()
    # Released on exit, so a fresh grab succeeds.
    reacquired = RunLock(path)
    reacquired.acquire()
    reacquired.release()


def test_release_without_acquire_is_noop(tmp_path: Path) -> None:
    RunLock(tmp_path / "lock").release()


@pytest.mark.concurrency
def test_lock_released_when_holder_process_dies(tmp_path: Path) -> None:
    # The OS drops the advisory lock on process death.
    path = tmp_path / "lock"
    code = (
        "import os, sys; from pathlib import Path; from raw2md.lock import RunLock; "
        "RunLock(Path(sys.argv[1])).acquire(); os._exit(0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(path)], timeout=60, check=False
    )
    assert result.returncode == 0
    lock = RunLock(path)
    lock.acquire()
    lock.release()


# A child that holds the lock until a release file appears; waiting on a file,
# not a timer, keeps the check deterministic.
_HOLDER_CODE = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from raw2md.lock import RunLock\n"
    "lock_path, held_marker, release_marker = sys.argv[1:4]\n"
    "lock = RunLock(Path(lock_path))\n"
    "lock.acquire()\n"
    "Path(held_marker).write_text('held')\n"
    "deadline = time.time() + 30\n"
    "while not Path(release_marker).exists() and time.time() < deadline:\n"
    "    time.sleep(0.02)\n"
    "lock.release()\n"
)


@pytest.mark.concurrency
def test_cross_process_mutual_exclusion(tmp_path: Path) -> None:
    # Two processes never both hold the lock.
    path = tmp_path / "lock"
    held = tmp_path / "held"
    release = tmp_path / "release"
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER_CODE, str(path), str(held), str(release)]
    )
    try:
        deadline = time.time() + 30
        while not held.exists() and proc.poll() is None and time.time() < deadline:
            time.sleep(0.02)
        assert held.exists(), "child did not acquire the lock"
        with pytest.raises(LockHeldError):
            RunLock(path).acquire()
        release.write_text("go")
        assert proc.wait(timeout=30) == 0
        reacquired = RunLock(path)
        reacquired.acquire()
        reacquired.release()
    finally:
        # A failed assertion must not leave the child blocking.
        release.write_text("go")
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)


def test_default_path_is_the_service_lock_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert RunLock().path == lock_file()
