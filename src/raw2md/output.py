"""Output writer: result placement, naming, and collisions.

The result md sits next to the source under the same stem, with media in a
sibling folder of that name. Trailing dots and spaces are stripped on both
OSes, since Win32 drops them. Collisions are case-insensitive, as on Windows.

Collisions are checked before conversion. The md alone decides: this tool's
own result is replaced, an md without its header stops the file.
"""

from __future__ import annotations

import os
import secrets
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from raw2md.header import has_own_header

_CLEANED_SUFFIX = "_cleaned"
_MD_EXTENSION = ".md"


@dataclass(frozen=True)
class OutputTarget:
    """Resolved result locations for one source file; both share one parent."""

    md_path: Path
    media_dir: Path


class OutputCollisionError(Exception):
    """An existing entry at the result name must not be replaced.

    Raised for an md that is not this tool's own result, and for a result name
    that is the source itself.
    """


def resolve_output_target(
    source: Path,
    *,
    output_dir: Path | None = None,
    include_extension: bool = False,
) -> OutputTarget:
    """Compute the result md path and media folder for `source`.

    `include_extension` gives `input.pdf.md` for inputs that share a stem. An
    `md` re-cleaned in place gets the `_cleaned` suffix instead, which alone
    keeps it off the source; with `output_dir` it keeps the plain name.
    """
    base = output_dir if output_dir is not None else source.parent
    md_in_place = output_dir is None and source.suffix.lower() == _MD_EXTENSION
    if md_in_place:
        # Sanitized before the suffix, or a trailing dot would end up mid-name.
        name = f"{_sanitize_result_name(source.stem)}{_CLEANED_SUFFIX}"
    else:
        name = _sanitize_result_name(source.name if include_extension else source.stem)
    return OutputTarget(
        md_path=base / f"{name}{_MD_EXTENSION}",
        media_dir=base / name,
    )


def _sanitize_result_name(name: str) -> str:
    """Strip trailing dots and spaces Win32 silently drops from directory names.

    Unstripped, the media links would not match the folder on disk. A name of
    only dots and spaces is kept: an empty one would make `media_dir` the
    output directory itself, which the writer would then delete.
    """
    stripped = name.rstrip(" .")
    return stripped or name


def media_link(target: OutputTarget, asset_name: str) -> str:
    """Relative, ``/``-separated link from the md file to a media asset.

    `asset_name` is the raw name inside the media folder, not link text.
    """
    normalized = asset_name.replace("\\", "/").lstrip("/")
    return encode_link_path(f"{target.media_dir.name}/{normalized}")


_LINK_RESERVED_CHARS = frozenset("%<>()#?:")


def encode_link_path(path: str) -> str:
    """Percent-encode only what breaks a link target, keeping the rest readable.

    Escaped: any Unicode whitespace (`mdtext.links.IMAGE_RE` stops at it too),
    `<>()`, which end or nest a target, `#` and `?`, read as fragment and
    query, `:`, read as a URI scheme in the first segment (escaped everywhere
    for simplicity), control bytes, and `%`. Non-ASCII text stays readable.
    `path` must be raw: a caller holding link text `unquote`s it first, or an
    escape would be doubled. Every emitted link goes through here.
    """
    return "".join(quote(ch, safe="") if _needs_escape(ch) else ch for ch in path)


def _needs_escape(ch: str) -> bool:
    """True for the handful of bytes that break parsing or URL resolution."""
    return (
        ch in _LINK_RESERVED_CHARS or ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F
    )


def _existing_match(path: Path) -> Path | None:
    """Return the filesystem entry matching `path` case-insensitively, if any."""
    parent = path.parent
    if not parent.exists():
        return None
    wanted = path.name.lower()
    for entry in parent.iterdir():
        if entry.name.lower() == wanted:
            return entry
    return None


_DEBUG_SUFFIX = ".debug"


def debug_dir_for(target: OutputTarget) -> Path:
    """The sibling folder `--debug` saves this file's per-stage snapshots into."""
    return target.md_path.with_name(f"{target.md_path.stem}{_DEBUG_SUFFIX}")


def existing_md(target: OutputTarget) -> Path | None:
    """The entry holding `target`'s md name, in its on-disk casing, or None."""
    return _existing_match(target.md_path)


def is_own_result(path: Path) -> bool:
    """True when `path` is an md carrying raw2md's own header (a prior result).

    An unreadable or non-UTF-8 file reads as foreign: it may not be replaced.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return has_own_header(text)


def ensure_writable(
    target: OutputTarget,
    *,
    protect: Path | None = None,
    extra: Path | None = None,
) -> None:
    """Clear what this run rewrites and refuse what it must not touch.

    Only the md decides: an md without raw2md's header raises
    `OutputCollisionError`. The media folder and `extra` (the `--debug`
    folder) are cleared with their result. An entry that is `protect` (the
    source) or a directory holding it is refused.
    """
    md = existing_md(target)
    media = _existing_match(target.media_dir)
    debug = None if extra is None else _existing_match(extra)
    existing = [entry for entry in (md, media, debug) if entry is not None]
    if not existing:
        return
    if protect is not None:
        protected = protect.resolve()
        for entry in existing:
            resolved = entry.resolve()
            if resolved == protected or resolved in protected.parents:
                raise OutputCollisionError(
                    f"result name collides with the source: {entry}"
                )
    if md is not None and not is_own_result(md):
        raise OutputCollisionError(f"an existing md is not a raw2md result: {md}")
    for entry in existing:
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def write_md(target: OutputTarget, content: str) -> None:
    """Write the result markdown as UTF-8 without a BOM, atomically, LF only."""
    atomic_write_text(target.md_path, content)


def atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` so a crash leaves either the old file or the new.

    A temp sibling is written, `fsync`-ed, and moved over `path` with
    `os.replace`; on POSIX the directory is synced too. The temp name is random
    and opened exclusively, so it never truncates a user file. On a collision
    nothing was opened; on any other failure the temp file is removed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with tmp.open("x", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except FileExistsError:
        raise
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if sys.platform != "win32":
        _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of a directory.

    Network shares and some FUSE mounts refuse it; the write has already
    succeeded, so a refusal is not a failure.
    """
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)
