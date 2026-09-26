"""File-signature check that runs before a source reaches its engine.

Engine selection trusts the extension. A `.docx` that is really RTF or an old
OLE2 `.doc` reaches pandoc, which reports an unrelated broken-archive error.
This check compares the leading bytes with what the extension promises and
names the mismatch.

Only pdf, docx, and djvu are checked; `md` is not converted. A file too short
to carry the magic bytes is left to the engine. A detected RTF is refused, not
converted: the check does not widen the set of accepted formats.
"""

from __future__ import annotations

from pathlib import Path

from raw2md.engines.base import ConversionError, normalize_extension

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_DJVU_MAGIC = b"AT&TFORM"
_RTF_MAGIC = b"{\\rtf1"
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# The longest magic checked at byte 0 (OLE2, djvu) is 8 bytes.
_HEAD_LEN = 8

# PDF readers accept the %PDF- header after a short preamble (a BOM, bytes a
# tool prepended) and scan the first 1024 bytes for it.
_PDF_SCAN_WINDOW = 1024


def check_signature(source: Path) -> None:
    """Raise `ConversionError` when the bytes of `source` contradict its extension.

    A read failure is left to the engine, which reads the same file next.
    """
    extension = normalize_extension(source)
    if extension not in ("pdf", "docx", "djvu"):
        return
    read_len = _PDF_SCAN_WINDOW if extension == "pdf" else _HEAD_LEN
    try:
        with source.open("rb") as f:
            head = f.read(read_len)
    except OSError:
        return
    if extension == "pdf":
        _check_pdf(source, head)
    elif extension == "docx":
        _check_docx(source, head)
    else:
        _check_djvu(source, head)


def _check_pdf(source: Path, head: bytes) -> None:
    if len(head) < len(_PDF_MAGIC):
        return  # too short to carry the header either way
    if _PDF_MAGIC not in head:
        raise ConversionError(f"{source.name}: missing the %PDF- signature")


def _check_djvu(source: Path, head: bytes) -> None:
    if len(head) < len(_DJVU_MAGIC):
        return
    if not head.startswith(_DJVU_MAGIC):
        raise ConversionError(f"{source.name}: missing the AT&TFORM djvu signature")


def _check_docx(source: Path, head: bytes) -> None:
    if len(head) < 4:
        return
    if any(head.startswith(magic) for magic in _ZIP_MAGICS):
        return
    if head.startswith(_RTF_MAGIC):
        raise ConversionError(f"{source.name}: is RTF, not a docx (zip) archive")
    if head.startswith(_OLE2_MAGIC):
        raise ConversionError(
            f"{source.name}: is an OLE2 document (an old .doc), not a docx"
            " (zip) archive"
        )
    raise ConversionError(f"{source.name}: does not look like a docx (zip) archive")
