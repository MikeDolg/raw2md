"""Temp-path selection for conversions.

marker breaks on non-ASCII paths through its dependencies, so every source is
staged in an ASCII, writable temp folder. The root is, in order: the
`RAW2MD_TMP` environment variable; `tmp/` inside `~/.raw2md` when its absolute
path is ASCII; a fixed fallback (`/tmp/raw2md` on Linux, `C:\\raw2md-tmp` on
Windows). A root that is non-ASCII or not writable stops the run before
conversion. Only the temp folder carries this constraint.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from raw2md.paths import default_temp_dir

_TMP_ENV = "RAW2MD_TMP"


class TempPathError(Exception):
    """The chosen temp root is non-ASCII or not writable."""


def _fallback_root() -> Path:
    if sys.platform == "win32":
        return Path("C:/raw2md-tmp")
    return Path("/tmp/raw2md")  # noqa: S108 -- the ASCII fallback root


def _is_ascii(path: Path) -> bool:
    return str(path.absolute()).isascii()


def select_temp_root(env: Mapping[str, str] | None = None) -> Path:
    """Return the validated, absolute temp root, creating it if needed.

    Raises `TempPathError` when the chosen path is non-ASCII or not writable.
    """
    environ = os.environ if env is None else env
    explicit = environ.get(_TMP_ENV)
    if explicit:
        candidate = Path(explicit)
    else:
        default = default_temp_dir()
        # An explicit choice is taken as-is and validated below.
        candidate = default if _is_ascii(default) else _fallback_root()

    root = candidate.absolute()
    if not str(root).isascii():
        raise TempPathError(f"temp path is not ASCII: {root}")
    _ensure_writable(root)
    return root


def _ensure_writable(root: Path) -> None:
    probe = root / f".raw2md-write-test-{os.getpid()}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
    except OSError as error:
        raise TempPathError(f"temp path is not writable: {root} ({error})") from error
