"""Pandoc conversion engine for docx files.

The pandoc binary always runs as a subprocess under a timeout; pypandoc is
never consulted. The conversion is two calls: pandoc reads the docx into its
JSON tree, `pandoc_tables` folds the tables, and pandoc writes Markdown.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from raw2md.engines.base import (
    ConversionError,
    ConversionResult,
    ConvertOptions,
    Engine,
)
from raw2md.engines.pandoc_tables import flatten_table_cells
from raw2md.header import ConversionMethod

# A hung pandoc would block the batch; 2 minutes covers a large docx.
_PANDOC_TIMEOUT_S: int = 120

# gfm enables GitLab math, which takes priority over tex_math_dollars; the
# cleaner needs the dollar form. --wrap=none keeps a formula or a long <img>
# on one line inside a pipe-table cell: a wrap there leaves an unclosed fence.
_TARGET_FORMAT: str = "gfm-tex_math_gfm+tex_math_dollars"
_WRAP_ARG: str = "--wrap=none"

_AST_FORMAT: str = "json"

# tex_math_gfm, turned off by name above, appeared in pandoc 3.1.9; an older
# pandoc rejects the whole format string (exit 23).
_MIN_PANDOC_VERSION: tuple[int, ...] = (3, 1, 9)

_VERSION_LINE_RE = re.compile(r"^pandoc(?:\.exe)?\s+(\d+(?:\.\d+)*)", re.MULTILINE)


def _pandoc_bin() -> str | None:
    return shutil.which("pandoc")


def _parse_pandoc_version(version_output: str) -> tuple[int, ...] | None:
    """Parse the version tuple out of `pandoc --version`; None when unknown."""
    match = _VERSION_LINE_RE.search(version_output)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _pandoc_version(pandoc: str) -> tuple[int, ...] | None:
    """Run `pandoc --version` and return the parsed version, or None."""
    try:
        result = subprocess.run(
            [pandoc, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=_PANDOC_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return _parse_pandoc_version(result.stdout)


def _format_version(version: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in version)


def _version_problem(pandoc: str) -> str | None:
    """None when `pandoc`'s version meets the floor; else a message naming it."""
    version = _pandoc_version(pandoc)
    if version is not None and version >= _MIN_PANDOC_VERSION:
        return None
    found = _format_version(version) if version is not None else "unknown"
    return (
        f"pandoc {found} is older than raw2md needs "
        f"({_format_version(_MIN_PANDOC_VERSION)}+)"
    )


def _cleanup_media_dir(media_dir: Path, existed_before: bool) -> None:
    """Remove a media dir this call created, on failure.

    pandoc creates the folder itself, so a failed call may leave one; a folder
    that existed before is not ours.
    """
    if not existed_before and media_dir.exists():
        shutil.rmtree(media_dir, ignore_errors=True)


def _run_pandoc(args: list[str], pandoc: str, stdin: str | None = None) -> str:
    cmd = [pandoc, *args]
    try:
        result = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=_PANDOC_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"pandoc timed out after {_PANDOC_TIMEOUT_S}s") from exc
    if result.returncode != 0:
        raise ConversionError(
            f"pandoc failed (code {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _folded_tree(source: Path, extra_args: list[str], pandoc: str) -> str:
    """Read the source into pandoc's document tree, tables folded flat.

    The reader extracts media and rewrites each link to the extracted name.
    """
    tree = _run_pandoc([str(source), "-t", _AST_FORMAT, *extra_args], pandoc)
    try:
        doc: Any = json.loads(tree)
    except json.JSONDecodeError as exc:
        raise ConversionError("pandoc wrote an unreadable document tree") from exc
    if not isinstance(doc, dict):
        raise ConversionError("pandoc wrote a document tree of an unknown shape")
    flatten_table_cells(doc)
    # Escaped non-ASCII text would multiply the payload size.
    return json.dumps(doc, ensure_ascii=False)


def _write_markdown(tree: str, pandoc: str) -> str:
    """Write the document tree out as GitHub-Flavored Markdown."""
    return _run_pandoc(
        ["-f", _AST_FORMAT, "-t", _TARGET_FORMAT, _WRAP_ARG], pandoc, stdin=tree
    )


class PandocEngine(Engine):
    """Pandoc-based conversion engine for .docx files."""

    @property
    def method(self) -> ConversionMethod:
        return ConversionMethod.PANDOC

    @property
    def extensions(self) -> frozenset[str]:
        return frozenset({"docx"})

    def available(self) -> bool:
        """True when pandoc is on PATH and its version meets the floor."""
        pandoc = _pandoc_bin()
        return pandoc is not None and _version_problem(pandoc) is None

    def unavailable_reason(self) -> str | None:
        """Why `available()` is False, when pandoc's version is the cause."""
        pandoc = _pandoc_bin()
        if pandoc is None:
            return None
        return _version_problem(pandoc)

    def convert(
        self, source: Path, media_dir: Path, options: ConvertOptions
    ) -> ConversionResult:
        """Convert a .docx to GitHub-Flavored Markdown via pandoc.

        pandoc writes media into a nested `media/` subfolder, so `media` names
        carry that prefix (`media/image1.png`) until the pipeline lifts them
        flat. A source with no images leaves no folder.
        """
        pandoc = _pandoc_bin()
        if pandoc is None:
            raise ConversionError("pandoc binary not found")
        problem = _version_problem(pandoc)
        if problem is not None:
            raise ConversionError(problem)

        media_dir_existed = media_dir.exists()
        extra_args: list[str] = []
        if options.extract_media:
            extra_args += ["--extract-media", str(media_dir)]

        try:
            body = _write_markdown(_folded_tree(source, extra_args, pandoc), pandoc)
        except ConversionError:
            _cleanup_media_dir(media_dir, media_dir_existed)
            raise
        except Exception as exc:
            _cleanup_media_dir(media_dir, media_dir_existed)
            raise ConversionError(f"pandoc conversion failed: {exc}") from exc

        media: tuple[str, ...] = ()
        if options.extract_media and media_dir.exists():
            media = tuple(
                p.relative_to(media_dir).as_posix()
                for p in sorted(media_dir.rglob("*"))
                if p.is_file()
            )

        return ConversionResult(body=body, media=media)
