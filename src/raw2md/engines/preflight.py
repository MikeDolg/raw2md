"""Checks over the source itself, run before any engine opens it.

A refusal here names the defect of the input instead of an unrelated engine
failure, costs no model load, and lands before the previous result is
cleared, so a rerun over a broken source keeps the old result.

Every check is positive: it refuses only a defect it can prove and leaves an
unreadable answer to the engine. A second parser that disagrees with the
engine must never stop a healthy document.
"""

from __future__ import annotations

from pathlib import Path

from raw2md.engines.base import ConversionError, normalize_extension
from raw2md.engines.signature import check_signature


def check_source(source: Path) -> None:
    """Raise `ConversionError` for a defect settled before conversion starts.

    Cheapest first: length, signature, then the check that parses the file.
    """
    _check_not_empty(source)
    check_signature(source)
    _check_pdf_password(source)


def _check_not_empty(source: Path) -> None:
    """Refuse a source of zero length.

    The signature check passes an empty file: no bytes contradict the
    extension.
    """
    try:
        size = source.stat().st_size
    except OSError:
        return  # the engine reads the same file next and reports the failure
    if size == 0:
        raise ConversionError(f"{source.name}: the file is empty")


def _check_pdf_password(source: Path) -> None:
    """Refuse a pdf that opens only with a password.

    No password is ever supplied, and the engine reports encryption as its own
    load failure.
    """
    if normalize_extension(source) != "pdf":
        return
    # Lazy: a run that converts no pdf does not pay for the import.
    from raw2md.engines import pymupdf

    if pymupdf.needs_password(source):
        raise ConversionError(f"{source.name}: the pdf is password-protected")
