"""Single-run lock for the queue and the GPU.

One run at a time: the workload is GPU-bound and `queue.json` is global. The
lock is taken by commands that mutate the queue or use the GPU (`INPUT`,
`resume`); read-only and management commands run without it.

An OS advisory lock (`fcntl.flock`, `msvcrt.locking`) gives exclusion; the
kernel releases it on exit, even on a crash, so there is no stale state. The
file content (owner PID, time) only lets a refused run name the owner. The
file is never deleted, which avoids an unlink/recreate race. Locking works on
the raw descriptor: `msvcrt.locking` acts on the OS file pointer, which a
buffered stream would diverge from.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from raw2md.paths import lock_file

if sys.platform == "win32":
    import msvcrt

    # A phantom byte far past the content: a Windows byte-range lock blocks
    # only its range, so a refused run can still read the record.
    _LOCK_OFFSET = 0x7FFFFFFF

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.lseek(fd, 0, os.SEEK_SET)

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class LockError(Exception):
    """Base for lock-layer failures."""


class LockHeldError(LockError):
    """Another live run already holds the lock."""

    def __init__(self, pid: int | None) -> None:
        if pid is None:
            super().__init__("another raw2md run is active")
        else:
            super().__init__(f"another raw2md run is active (pid {pid})")
        self.pid = pid


@dataclass(frozen=True)
class LockRecord:
    """Owner identity in the lock file, for diagnostics only."""

    pid: int
    created_at: str

    def to_json(self) -> str:
        return json.dumps({"pid": self.pid, "created_at": self.created_at})

    @classmethod
    def from_text(cls, text: str) -> LockRecord | None:
        try:
            data = json.loads(text)
            return cls(pid=int(data["pid"]), created_at=str(data["created_at"]))
        except (ValueError, KeyError, TypeError):
            return None


def _own_record() -> LockRecord:
    return LockRecord(
        pid=os.getpid(),
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


class RunLock:
    """Acquire/release the global run lock; usable as a context manager."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else lock_file()
        self._fd: int | None = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self) -> None:
        """Take the lock. Raises `LockHeldError` if another run holds it."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # No truncation: a refused run reads the owner PID from the record.
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        if not _try_lock(fd):
            owner = _read_owner(fd)
            os.close(fd)
            raise LockHeldError(owner)
        # A failed record write drops the lock, so neither fd nor lock leaks.
        held = False
        try:
            _write_record(fd, _own_record())
            self._fd = fd
            held = True
        finally:
            if not held:
                _unlock(fd)
                os.close(fd)

    def release(self) -> None:
        """Release the lock if held (no-op otherwise). The file is left in place."""
        if self._fd is None:
            return
        try:
            _unlock(self._fd)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


def _write_record(fd: int, record: LockRecord) -> None:
    data = record.to_json().encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    written = 0
    # os.write may write fewer bytes than requested.
    while written < len(data):
        written += os.write(fd, data[written:])


def _read_owner(fd: int) -> int | None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 65536)
    except OSError:
        return None
    record = LockRecord.from_text(raw.decode("utf-8", "replace"))
    return record.pid if record else None
