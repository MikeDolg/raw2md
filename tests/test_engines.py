"""Tests for the conversion engine interface, registry, and PyMuPDF base."""

from __future__ import annotations

import importlib.machinery
import io
import json
import subprocess
import sys
import types
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

# Aliased because the engine module under test shares the library's name.
import pymupdf as pymupdf_lib
import pytest
from PIL import Image

from raw2md.engines import (
    ConversionError,
    ConversionResult,
    ConvertOptions,
    DjvuEngine,
    Engine,
    EngineNotFoundError,
    EngineRegistry,
    EngineUnavailableError,
    MarkerEngine,
    PandocEngine,
    check_signature,
    check_source,
    normalize_extension,
    pymupdf,
)
from raw2md.engines.base import condense_process_output
from raw2md.engines.djvu import djvu_to_pdf, page_texts
from raw2md.engines.pandoc import _parse_pandoc_version
from raw2md.engines.pandoc_tables import flatten_table_cells
from raw2md.header import ConversionMethod
from raw2md.mdtext.pages import page_mark, split_page_marks

# PNG file signature; render output must start with it.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class StubEngine(Engine):
    """In-memory engine for driving selection without a heavy dependency."""

    def __init__(
        self,
        *,
        method: ConversionMethod,
        extensions: frozenset[str],
        body: str = "stub",
        available: bool = True,
    ) -> None:
        self._method = method
        self._extensions = extensions
        self._body = body
        self._available = available

    @property
    def method(self) -> ConversionMethod:
        return self._method

    @property
    def extensions(self) -> frozenset[str]:
        return self._extensions

    def available(self) -> bool:
        return self._available

    def convert(
        self, source: Path, media_dir: Path, options: ConvertOptions
    ) -> ConversionResult:
        return ConversionResult(body=self._body)


def _make_pdf(path: Path, *, pages: int, text: str | None) -> None:
    """Write a minimal PDF with `pages` pages, each carrying `text` if given."""
    doc = pymupdf_lib.open()
    try:
        for _ in range(pages):
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        doc.save(str(path))
    finally:
        doc.close()


def test_normalize_extension_strips_dot_and_case() -> None:
    assert normalize_extension(Path("Report.PDF")) == "pdf"
    assert normalize_extension(Path("scan.Djvu")) == "djvu"


def test_select_matches_extension_case_insensitively() -> None:
    engine = StubEngine(method=ConversionMethod.MARKER, extensions=frozenset({"pdf"}))
    registry = EngineRegistry([engine])

    assert registry.select(Path("a.pdf")) is engine
    assert registry.select(Path("B.PDF")) is engine
    assert registry.select(Path("dir/C.Pdf")) is engine


def test_select_finds_engine_declaring_non_normalized_extension() -> None:
    # Registration normalizes claims, so `PDF`/`.pdf` stays selectable.
    engine = StubEngine(
        method=ConversionMethod.MARKER, extensions=frozenset({"PDF", ".djvu"})
    )
    registry = EngineRegistry([engine])

    assert registry.select(Path("a.pdf")) is engine
    assert registry.select(Path("b.DJVU")) is engine


def test_select_unknown_extension_raises_not_found() -> None:
    registry = EngineRegistry(
        [StubEngine(method=ConversionMethod.MARKER, extensions=frozenset({"pdf"}))]
    )
    with pytest.raises(EngineNotFoundError):
        registry.select(Path("notes.txt"))


def test_select_unavailable_engine_raises_unavailable() -> None:
    registry = EngineRegistry(
        [
            StubEngine(
                method=ConversionMethod.PANDOC,
                extensions=frozenset({"docx"}),
                available=False,
            )
        ]
    )
    with pytest.raises(EngineUnavailableError):
        registry.select(Path("memo.docx"))


def test_registry_rejects_two_engines_for_one_extension() -> None:
    first = StubEngine(method=ConversionMethod.MARKER, extensions=frozenset({"pdf"}))
    second = StubEngine(
        method=ConversionMethod.DJVU_MARKER, extensions=frozenset({"pdf", "djvu"})
    )
    with pytest.raises(ValueError, match="pdf"):
        EngineRegistry([first, second])


def test_unavailable_lists_each_engine_once() -> None:
    available = StubEngine(
        method=ConversionMethod.MARKER, extensions=frozenset({"pdf"})
    )
    # One engine handling two extensions must still appear once in the report.
    missing = StubEngine(
        method=ConversionMethod.DJVU_MARKER,
        extensions=frozenset({"djvu", "djv"}),
        available=False,
    )
    registry = EngineRegistry([available, missing])

    assert registry.unavailable() == (missing,)


def test_unavailable_empty_when_all_present() -> None:
    registry = EngineRegistry(
        [StubEngine(method=ConversionMethod.MARKER, extensions=frozenset({"pdf"}))]
    )
    assert registry.unavailable() == ()


# ---------------------------------------------------------------------------
# check_signature (pre-flight format check, ahead of engine selection)
# ---------------------------------------------------------------------------


def test_check_signature_accepts_real_pdf(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4\n%stub content")
    check_signature(source)  # must not raise


def test_check_signature_rejects_pdf_without_pdf_header(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"this is plainly not a pdf file at all")
    with pytest.raises(ConversionError, match="%PDF-"):
        check_signature(source)


def test_check_signature_accepts_pdf_header_after_a_short_preamble(
    tmp_path: Path,
) -> None:
    # PDF readers scan an initial window for the header, so a prepended BOM is
    # no mismatch.
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"\xef\xbb\xbf%PDF-1.7\nstub content")
    check_signature(source)  # must not raise


def test_check_signature_accepts_real_docx(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"PK\x03\x04 rest of a real zip archive")
    check_signature(source)


def test_check_signature_rejects_docx_containing_rtf(tmp_path: Path) -> None:
    source = tmp_path / "memo.docx"
    source.write_bytes(rb"{\rtf1\ansi\deff0 Some RTF body text}")
    with pytest.raises(ConversionError, match="RTF"):
        check_signature(source)


def test_check_signature_rejects_docx_containing_ole2(tmp_path: Path) -> None:
    source = tmp_path / "old.docx"
    source.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"rest of an old .doc")
    with pytest.raises(ConversionError, match="OLE2"):
        check_signature(source)


def test_check_signature_accepts_real_djvu(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"AT&TFORM" + b"\x00\x00\x01\x00DJVMrest")
    check_signature(source)


def test_check_signature_rejects_djvu_without_att_form(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"this is not a djvu file at all")
    with pytest.raises(ConversionError, match="AT&TFORM"):
        check_signature(source)


def test_check_signature_skips_md(tmp_path: Path) -> None:
    # md carries no signature; a path never created proves it is not read.
    check_signature(tmp_path / "note.md")


def test_check_signature_allows_empty_file_of_a_checked_extension(
    tmp_path: Path,
) -> None:
    # An empty source is the length check's call, not this one's.
    for suffix in (".pdf", ".docx", ".djvu"):
        source = tmp_path / f"empty{suffix}"
        source.write_bytes(b"")
        check_signature(source)


def test_check_signature_allows_file_shorter_than_its_magic(tmp_path: Path) -> None:
    # Fewer bytes than the magic is a short read, not a mismatch.
    for suffix, stub in ((".pdf", b"%PD"), (".docx", b"PK"), (".djvu", b"AT&T")):
        source = tmp_path / f"short{suffix}"
        source.write_bytes(stub)
        check_signature(source)


# ---------------------------------------------------------------------------
# check_source (the whole pre-flight, ahead of the engine)
# ---------------------------------------------------------------------------


def test_check_source_accepts_a_readable_pdf(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf(source, pages=1, text="Readable text.")
    check_source(source)  # must not raise


def test_check_source_rejects_an_empty_file(tmp_path: Path) -> None:
    for suffix in (".pdf", ".docx", ".djvu"):
        source = tmp_path / f"empty{suffix}"
        source.write_bytes(b"")
        with pytest.raises(ConversionError, match="empty"):
            check_source(source)


def test_check_source_still_reports_a_signature_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"this is plainly not a pdf file at all")
    with pytest.raises(ConversionError, match="%PDF-"):
        check_source(source)


def test_check_source_rejects_a_password_protected_pdf(tmp_path: Path) -> None:
    source = tmp_path / "secret.pdf"
    doc = pymupdf_lib.open()
    try:
        doc.new_page()
        doc.save(str(source), encryption=pymupdf_lib.PDF_ENCRYPT_AES_256, user_pw="pw")
    finally:
        doc.close()

    with pytest.raises(ConversionError, match="password-protected"):
        check_source(source)


def test_check_source_leaves_a_damaged_pdf_to_the_engine(tmp_path: Path) -> None:
    # An unopenable file proves nothing about a password.
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4 not openable by anything")
    check_source(source)


def test_check_source_leaves_a_missing_file_to_the_engine(tmp_path: Path) -> None:
    # The engine reads the same path next and reports the real read failure.
    check_source(tmp_path / "gone.pdf")


def test_count_pages_returns_page_count(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf(source, pages=3, text="Page text content here.")
    assert pymupdf.count_pages(source) == 3


def test_has_text_layer_true_for_text_pdf(tmp_path: Path) -> None:
    source = tmp_path / "text.pdf"
    _make_pdf(source, pages=1, text="A line of recognizable text content.")
    assert pymupdf.has_text_layer(source) is True


def test_has_text_layer_false_for_empty_pdf(tmp_path: Path) -> None:
    source = tmp_path / "blank.pdf"
    _make_pdf(source, pages=2, text=None)
    assert pymupdf.has_text_layer(source) is False


def test_render_pages_yields_one_png_per_page(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf(source, pages=2, text="Some text.")
    rasters = list(pymupdf.render_pages(source, dpi=72))

    assert len(rasters) == 2
    assert all(raster.startswith(_PNG_MAGIC) for raster in rasters)


def _png(color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, format="PNG")
    return buf.getvalue()


_LOGO_RECT = pymupdf_lib.Rect(10, 10, 60, 40)

# The same image bigger and moved: a logo blown up on the cover page.
_COVER_RECT = pymupdf_lib.Rect(10, 10, 160, 90)


def _make_pdf_with_images(
    path: Path,
    pages: list[bytes | None],
    *,
    rects: list[pymupdf_lib.Rect] | None = None,
    rotates: list[int] | None = None,
) -> None:
    """Write a PDF with one page per list entry, each inserting the given PNG.

    Identical bytes on separate pages share one xref, as a reused picture does.
    `rects` and `rotates` place each page's image on its own.
    """
    doc = pymupdf_lib.open()
    try:
        for i, png in enumerate(pages):
            page = doc.new_page()
            if png is not None:
                rect = rects[i] if rects is not None else _LOGO_RECT
                rotate = rotates[i] if rotates is not None else 0
                page.insert_image(rect, stream=png, rotate=rotate)
        doc.save(str(path))
    finally:
        doc.close()


def test_image_placements_by_page_shares_placement_for_a_reused_image(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.pdf"
    logo = _png("red")
    _make_pdf_with_images(source, [logo, logo, logo])

    placements = pymupdf.image_placements_by_page(source)

    assert [len(page) for page in placements] == [1, 1, 1]
    assert placements[0][0] == placements[1][0] == placements[2][0]


def test_image_placements_by_page_distinct_images_get_distinct_xrefs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf_with_images(source, [_png("red"), _png("blue")])

    placements = pymupdf.image_placements_by_page(source)

    assert len(placements[0]) == 1
    assert len(placements[1]) == 1
    assert placements[0][0][0] != placements[1][0][0]


def test_image_placements_by_page_same_image_different_bbox_differs(
    tmp_path: Path,
) -> None:
    # Same xref, scaled up: a cover blow-up is no duplicate of the logo.
    logo = _png("red")
    source = tmp_path / "doc.pdf"
    _make_pdf_with_images(source, [logo, logo], rects=[_LOGO_RECT, _COVER_RECT])

    placements = pymupdf.image_placements_by_page(source)

    assert placements[0][0][0] == placements[1][0][0]  # same xref
    assert placements[0][0][1] != placements[1][0][1]  # different transform
    assert placements[0][0] != placements[1][0]


def test_image_placements_by_page_same_bbox_different_rotation_differs(
    tmp_path: Path,
) -> None:
    # Same xref and bbox; only the transform tells the rotated crop apart.
    logo = _png("red")
    source = tmp_path / "doc.pdf"
    _make_pdf_with_images(source, [logo, logo], rotates=[0, 180])

    placements = pymupdf.image_placements_by_page(source)

    assert placements[0][0][0] == placements[1][0][0]  # same xref
    assert placements[0][0] != placements[1][0]  # different transform


def test_image_placements_by_page_empty_page_yields_no_placements(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf_with_images(source, [None])

    assert pymupdf.image_placements_by_page(source) == [[]]


def _write_pdf_with_inline_image(path: Path) -> None:
    """Write a one-page PDF whose only image is a content-stream inline image.

    PyMuPDF has no API for `BI ... EI`, so the stream is built by hand;
    `get_image_info` resolves it to xref 0.
    """
    doc = pymupdf_lib.open()
    try:
        page = doc.new_page(width=200, height=200)
        page.draw_rect(pymupdf_lib.Rect(0, 0, 1, 1))  # force a content stream to exist
        content = (
            b"q 40 0 0 40 10 10 cm BI /W 2 /H 2 /CS /RGB /BPC 8 ID "
            + bytes([255, 0, 0] * 4)
            + b" EI Q"
        )
        doc.update_stream(page.get_contents()[0], content)
        doc.save(str(path))
    finally:
        doc.close()


def test_image_placements_by_page_drops_unresolvable_inline_images(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_with_inline_image(source)

    assert pymupdf.image_placements_by_page(source) == [[]]


# ---------------------------------------------------------------------------
# PandocEngine (docx route, stubbed)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _pandoc_new_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test below to a pandoc version past the floor."""
    monkeypatch.setattr(
        "raw2md.engines.pandoc._pandoc_version", lambda pandoc: (3, 10, 0)
    )


def _empty_tree() -> dict[str, Any]:
    return {"pandoc-api-version": [1, 23, 1, 2], "meta": {}, "blocks": []}


def _fake_pandoc(
    *,
    body: str = "## Title\n",
    tree: dict[str, Any] | None = None,
    on_read: Callable[[], None] | None = None,
) -> Callable[..., MagicMock]:
    """Stand in for the reader call and then the writer call of a conversion.

    `on_read` runs inside the reader call, for media on disk by collect time.
    """

    def run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        if "-f" in cmd:
            result.stdout = body
            return result
        if on_read is not None:
            on_read()
        result.stdout = json.dumps(tree if tree is not None else _empty_tree())
        return result

    return run


def _reader_call(sp: MagicMock) -> list[str]:
    """The command of the reader call, out of the two a conversion makes."""
    return list(sp.call_args_list[0].args[0])


def _ast_attr() -> list[Any]:
    return ["", [], []]


def _ast_para(*inlines: Any) -> dict[str, Any]:
    return {"t": "Para", "c": list(inlines)}


def _ast_str(text: str) -> dict[str, Any]:
    return {"t": "Str", "c": text}


def _ast_cell(*blocks: Any, row_span: int = 1, col_span: int = 1) -> list[Any]:
    """One cell holding the given blocks; a plain string means a paragraph."""
    content = [
        _ast_para(_ast_str(block)) if isinstance(block, str) else block
        for block in blocks
    ]
    return [_ast_attr(), {"t": "AlignDefault"}, row_span, col_span, content]


def _ast_table(
    body_rows: list[list[Any]],
    head_rows: list[list[Any]] | None = None,
    foot_rows: list[list[Any]] | None = None,
) -> dict[str, Any]:
    rows = [*(head_rows or []), *body_rows, *(foot_rows or [])]
    columns = max((len(row) for row in rows), default=0)
    return {
        "t": "Table",
        "c": [
            _ast_attr(),
            [None, []],
            [[{"t": "AlignDefault"}, {"t": "ColWidthDefault"}] for _ in range(columns)],
            [_ast_attr(), [[_ast_attr(), row] for row in head_rows or []]],
            [[_ast_attr(), 0, [], [[_ast_attr(), row] for row in body_rows]]],
            [_ast_attr(), [[_ast_attr(), row] for row in foot_rows or []]],
        ],
    }


def _body_cells(table: dict[str, Any]) -> list[Any]:
    return [cell for _attr, cells in table["c"][4][0][3] for cell in cells]


def test_pandoc_engine_method_and_extensions() -> None:
    engine = PandocEngine()
    assert engine.method is ConversionMethod.PANDOC
    assert engine.extensions == frozenset({"docx"})


def test_pandoc_engine_available_when_pandoc_in_path() -> None:
    with patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"):
        assert PandocEngine().available() is True


def test_pandoc_engine_unavailable_when_pandoc_missing() -> None:
    with patch("raw2md.engines.pandoc.shutil.which", return_value=None):
        assert PandocEngine().available() is False


def test_parse_pandoc_version_reads_plain_banner() -> None:
    output = "pandoc 3.1.9\nFeatures: +server\nUser data directory: ...\n"
    assert _parse_pandoc_version(output) == (3, 1, 9)


def test_parse_pandoc_version_reads_windows_exe_banner() -> None:
    # Confirmed against a live install: "pandoc.exe 3.10" on Windows,
    # "pandoc 3.10" elsewhere, both followed by the same feature lines.
    output = "pandoc.exe 3.10\nFeatures: +server +lua\n"
    assert _parse_pandoc_version(output) == (3, 10)


def test_parse_pandoc_version_returns_none_for_unrecognized_banner() -> None:
    assert _parse_pandoc_version("not a pandoc banner at all\n") is None


def test_parse_pandoc_version_returns_none_for_empty_output() -> None:
    assert _parse_pandoc_version("") is None


def test_pandoc_engine_unavailable_when_version_too_old() -> None:
    # Ubuntu 24.04's archive package (3.1.3) predates tex_math_gfm (3.1.9).
    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc._pandoc_version", return_value=(3, 1, 3)),
    ):
        assert PandocEngine().available() is False


def test_pandoc_engine_available_at_exactly_the_floor_version() -> None:
    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc._pandoc_version", return_value=(3, 1, 9)),
    ):
        assert PandocEngine().available() is True


def test_pandoc_engine_unavailable_when_version_cannot_be_read() -> None:
    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc._pandoc_version", return_value=None),
    ):
        assert PandocEngine().available() is False


def test_pandoc_engine_unavailable_reason_none_when_binary_missing() -> None:
    # doctor's plain "MISSING (optional)" already says this; no detail to add.
    with patch("raw2md.engines.pandoc.shutil.which", return_value=None):
        assert PandocEngine().unavailable_reason() is None


def test_pandoc_engine_unavailable_reason_none_when_version_is_fine() -> None:
    with patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"):
        assert PandocEngine().unavailable_reason() is None


def test_pandoc_engine_unavailable_reason_names_both_versions() -> None:
    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc._pandoc_version", return_value=(3, 1, 3)),
    ):
        reason = PandocEngine().unavailable_reason()

    assert reason is not None
    assert "3.1.3" in reason
    assert "3.1.9" in reason


def test_pandoc_engine_convert_raises_on_a_pandoc_too_old(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc._pandoc_version", return_value=(3, 1, 3)),
        patch("raw2md.engines.pandoc.subprocess.run") as sp,
        pytest.raises(ConversionError) as exc_info,
    ):
        PandocEngine().convert(source, media_dir, ConvertOptions())

    # The version is what a reader can act on; pandoc is never called.
    assert "3.1.9" in str(exc_info.value)
    sp.assert_not_called()


def test_pandoc_engine_converts_via_cli(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc.subprocess.run", side_effect=_fake_pandoc()) as sp,
    ):
        result = PandocEngine().convert(source, media_dir, ConvertOptions())

    assert result.body == "## Title\n"
    assert sp.call_count == 2

    read_cmd = _reader_call(sp)
    assert read_cmd[0] == "/usr/bin/pandoc"
    assert str(source) in read_cmd
    assert "-t" in read_cmd
    assert "json" in read_cmd
    # Media extraction belongs to the reader: it is what unpacks the files.
    assert "--extract-media" in read_cmd

    write_cmd: list[str] = sp.call_args_list[1].args[0]
    assert write_cmd[0] == "/usr/bin/pandoc"
    assert "-f" in write_cmd
    assert "json" in write_cmd
    assert "gfm-tex_math_gfm+tex_math_dollars" in write_cmd
    assert "--wrap=none" in write_cmd
    assert "--extract-media" not in write_cmd


def test_pandoc_engine_hands_the_folded_tree_to_the_writer(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")

    tree = _empty_tree()
    tree["blocks"] = [_ast_table([[_ast_cell("a"), _ast_cell("b")]])]

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch(
            "raw2md.engines.pandoc.subprocess.run", side_effect=_fake_pandoc(tree=tree)
        ) as sp,
    ):
        PandocEngine().convert(source, tmp_path / "doc", ConvertOptions())

    written = json.loads(sp.call_args_list[1].kwargs["input"])
    cell = _body_cells(written["blocks"][0])[0]
    assert [block["t"] for block in cell[4]] == ["Plain"]


def test_pandoc_engine_raises_when_the_tree_is_unreadable(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")

    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "not a document tree"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc.subprocess.run", return_value=completed),
        pytest.raises(ConversionError, match="unreadable document tree"),
    ):
        PandocEngine().convert(source, tmp_path / "doc", ConvertOptions())


def test_pandoc_engine_raises_when_the_tree_is_not_a_document(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")

    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = "[1, 2]"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc.subprocess.run", return_value=completed),
        pytest.raises(ConversionError, match="unknown shape"),
    ):
        PandocEngine().convert(source, tmp_path / "doc", ConvertOptions())


def test_pandoc_engine_cli_raises_conversion_error_on_nonzero(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    completed = MagicMock()
    completed.returncode = 1
    completed.stderr = "unknown format"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc.subprocess.run", return_value=completed),
        pytest.raises(ConversionError, match="pandoc failed"),
    ):
        PandocEngine().convert(source, media_dir, ConvertOptions())


def test_pandoc_engine_cli_raises_conversion_error_on_timeout(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])  # type: ignore[arg-type]

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc.subprocess.run", side_effect=fake_run),
        pytest.raises(ConversionError, match="pandoc timed out"),
    ):
        PandocEngine().convert(source, media_dir, ConvertOptions())


def test_pandoc_engine_raises_when_pandoc_binary_missing(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value=None),
        pytest.raises(ConversionError, match="pandoc binary not found"),
    ):
        PandocEngine().convert(source, media_dir, ConvertOptions())


def test_pandoc_engine_skips_extract_media_when_disabled(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch(
            "raw2md.engines.pandoc.subprocess.run",
            side_effect=_fake_pandoc(body="body\n"),
        ) as sp,
    ):
        result = PandocEngine().convert(
            source, media_dir, ConvertOptions(extract_media=False)
        )

    assert result.media == ()
    assert not media_dir.exists()
    assert "--extract-media" not in _reader_call(sp)


def test_pandoc_engine_collects_extracted_media(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    def extract() -> None:
        inner = media_dir / "media"
        inner.mkdir(parents=True, exist_ok=True)
        (inner / "img1.png").write_bytes(b"png1")
        (inner / "img2.png").write_bytes(b"png2")

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch(
            "raw2md.engines.pandoc.subprocess.run",
            side_effect=_fake_pandoc(
                body="![img](doc/media/img1.png)\n", on_read=extract
            ),
        ),
    ):
        result = PandocEngine().convert(source, media_dir, ConvertOptions())

    assert set(result.media) == {"media/img1.png", "media/img2.png"}


def test_pandoc_engine_does_not_precreate_media_dir(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch(
            "raw2md.engines.pandoc.subprocess.run",
            side_effect=_fake_pandoc(body="body without images\n"),
        ),
    ):
        result = PandocEngine().convert(source, media_dir, ConvertOptions())

    # A source with nothing to extract leaves no folder for pandoc to make.
    assert result.media == ()
    assert not media_dir.exists()


def test_pandoc_engine_cleans_up_media_dir_on_failure(tmp_path: Path) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / "media").mkdir()
        result = MagicMock()
        result.returncode = 1
        result.stderr = "conversion error"
        return result

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc.subprocess.run", side_effect=fake_run),
        pytest.raises(ConversionError),
    ):
        PandocEngine().convert(source, media_dir, ConvertOptions())

    # media_dir was created by this call and must be removed on failure.
    assert not media_dir.exists()


def test_pandoc_engine_does_not_remove_preexisting_media_dir_on_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.docx"
    source.write_bytes(b"fake docx")
    media_dir = tmp_path / "doc"
    media_dir.mkdir()  # pre-existing before convert() is called

    completed = MagicMock()
    completed.returncode = 1
    completed.stderr = "conversion error"

    with (
        patch("raw2md.engines.pandoc.shutil.which", return_value="/usr/bin/pandoc"),
        patch("raw2md.engines.pandoc.subprocess.run", return_value=completed),
        pytest.raises(ConversionError),
    ):
        PandocEngine().convert(source, media_dir, ConvertOptions())

    # Caller owned media_dir; convert() must not delete it on failure.
    assert media_dir.exists()


# ---------------------------------------------------------------------------
# Table folding on pandoc's document tree
# ---------------------------------------------------------------------------

_BREAK = {"t": "RawInline", "c": ["html", "<br>"]}


def _folded(*blocks: Any) -> list[Any]:
    """Run the fold over a document made of `blocks` and return them back."""
    doc = {"pandoc-api-version": [1, 23, 1, 2], "meta": {}, "blocks": list(blocks)}
    flatten_table_cells(doc)
    return list(doc["blocks"])


def test_fold_makes_one_run_of_a_cell_of_paragraphs() -> None:
    table = _folded(_ast_table([[_ast_cell("left"), _ast_cell("right")]]))[0]

    assert [cell[4] for cell in _body_cells(table)] == [
        [{"t": "Plain", "c": [_ast_str("left")]}],
        [{"t": "Plain", "c": [_ast_str("right")]}],
    ]


def test_fold_keeps_a_printed_line_end_as_a_break() -> None:
    table = _folded(_ast_table([[_ast_cell("first", "second")]]))[0]

    assert _body_cells(table)[0][4] == [
        {"t": "Plain", "c": [_ast_str("first"), _BREAK, _ast_str("second")]}
    ]


def test_fold_rewrites_a_line_break_inside_a_paragraph() -> None:
    cell = _ast_cell(_ast_para(_ast_str("a"), {"t": "LineBreak"}, _ast_str("b")))
    table = _folded(_ast_table([[cell]]))[0]

    assert _body_cells(table)[0][4] == [
        {"t": "Plain", "c": [_ast_str("a"), _BREAK, _ast_str("b")]}
    ]


def test_fold_rewrites_a_line_break_under_an_inline() -> None:
    # A break inside emphasis or a footnote counts too.
    note = {"t": "Note", "c": [_ast_para(_ast_str("n"), {"t": "LineBreak"})]}
    emph = {"t": "Emph", "c": [_ast_str("a"), {"t": "LineBreak"}, _ast_str("b")]}
    table = _folded(_ast_table([[_ast_cell(_ast_para(emph, note))]]))[0]

    inlines = _body_cells(table)[0][4][0]["c"]
    assert inlines[0]["c"] == [_ast_str("a"), _BREAK, _ast_str("b")]
    assert inlines[1]["c"] == [_ast_para(_ast_str("n"), _BREAK)]


def test_fold_drops_an_empty_paragraph_without_a_break() -> None:
    cell = _ast_cell(_ast_para(), _ast_para(_ast_str("text")), _ast_para())
    table = _folded(_ast_table([[cell]]))[0]

    assert _body_cells(table)[0][4] == [{"t": "Plain", "c": [_ast_str("text")]}]


def test_fold_leaves_an_empty_cell_empty() -> None:
    table = _folded(_ast_table([[_ast_cell()]]))[0]

    assert _body_cells(table)[0][4] == []


def test_fold_reaches_the_head_and_the_foot() -> None:
    table = _folded(
        _ast_table(
            [[_ast_cell("body")]],
            head_rows=[[_ast_cell("head", "over two lines")]],
            foot_rows=[[_ast_cell("foot")]],
        )
    )[0]

    head_cell = table["c"][3][1][0][1][0]
    foot_cell = table["c"][5][1][0][1][0]
    assert head_cell[4][0]["c"] == [
        _ast_str("head"),
        _BREAK,
        _ast_str("over two lines"),
    ]
    assert foot_cell[4] == [{"t": "Plain", "c": [_ast_str("foot")]}]


def test_fold_keeps_a_table_with_a_spanning_cell() -> None:
    # A pipe table cannot state a span, so the writer prints HTML.
    spanning = _ast_cell("wide", col_span=2)
    table = _folded(_ast_table([[spanning], [_ast_cell("a", "b"), _ast_cell("c")]]))[0]

    assert [cell[4] for cell in _body_cells(table)] == [
        [_ast_para(_ast_str("wide"))],
        [_ast_para(_ast_str("a")), _ast_para(_ast_str("b"))],
        [_ast_para(_ast_str("c"))],
    ]


def test_fold_keeps_a_table_whose_cell_holds_more_than_text() -> None:
    quoted = _ast_cell({"t": "BlockQuote", "c": [_ast_para(_ast_str("q"))]})
    table = _folded(_ast_table([[quoted, _ast_cell("a", "b")]]))[0]

    assert _body_cells(table)[1][4] == [
        _ast_para(_ast_str("a")),
        _ast_para(_ast_str("b")),
    ]


def _ast_code(text: str) -> dict[str, Any]:
    return {"t": "Code", "c": [_ast_attr(), text]}


def _ast_math(kind: str, text: str) -> dict[str, Any]:
    return {"t": "Math", "c": [{"t": kind}, text]}


@pytest.mark.parametrize(
    "inline",
    [
        _ast_code("x|y"),
        _ast_math("InlineMath", "|x| = 1"),
        {"t": "RawInline", "c": ["html", "<b>a|b</b>"]},
        {"t": "Link", "c": [_ast_attr(), [_ast_str("t")], ["http://e/a|b", ""]]},
        {"t": "Emph", "c": [_ast_code("x|y")]},
    ],
)
def test_fold_keeps_a_table_whose_cell_writes_a_bare_pipe(inline: Any) -> None:
    # The writer does not escape this bar, so the row would outgrow its header.
    table = _folded(_ast_table([[_ast_cell(_ast_para(inline)), _ast_cell("a", "b")]]))[
        0
    ]

    assert _body_cells(table)[1][4] == [
        _ast_para(_ast_str("a")),
        _ast_para(_ast_str("b")),
    ]


def test_fold_takes_a_cell_whose_display_math_holds_a_pipe() -> None:
    # Cleaning escapes a display span on a pipe row, so folding costs nothing.
    display = _ast_math("DisplayMath", "|x| = 1")
    table = _folded(_ast_table([[_ast_cell(_ast_para(display)), _ast_cell("a", "b")]]))[
        0
    ]

    assert _body_cells(table)[1][4] == [
        {"t": "Plain", "c": [_ast_str("a"), _BREAK, _ast_str("b")]}
    ]


def test_fold_leaves_the_whole_subtree_of_a_table_it_keeps() -> None:
    # A nested table prints as HTML anyway and would lose its paragraphs.
    inner = _ast_table([[_ast_cell("x", "y")]])
    outer = _folded(_ast_table([[_ast_cell(inner), _ast_cell("a")]]))[0]

    assert _body_cells(inner)[0][4] == [
        _ast_para(_ast_str("x")),
        _ast_para(_ast_str("y")),
    ]
    assert _body_cells(outer)[1][4] == [_ast_para(_ast_str("a"))]


def test_fold_reaches_a_table_inside_another_block() -> None:
    item = [_ast_table([[_ast_cell("a", "b")]])]
    blocks = _folded({"t": "BulletList", "c": [item]})
    table = blocks[0]["c"][0][0]

    assert _body_cells(table)[0][4] == [
        {"t": "Plain", "c": [_ast_str("a"), _BREAK, _ast_str("b")]}
    ]


def test_fold_leaves_a_table_of_an_unknown_shape() -> None:
    # An unreadable table shape costs the fold and nothing else.
    table = _folded({"t": "Table", "c": [_ast_attr(), [None, []]]})[0]

    assert table["c"] == [_ast_attr(), [None, []]]


def test_fold_leaves_a_block_that_is_not_a_table() -> None:
    blocks = _folded(_ast_para(_ast_str("a"), {"t": "LineBreak"}, _ast_str("b")))

    assert blocks == [_ast_para(_ast_str("a"), {"t": "LineBreak"}, _ast_str("b"))]


# ---------------------------------------------------------------------------
# MarkerEngine (pdf route, marker mocked)
# ---------------------------------------------------------------------------


def _make_fake_marker(
    *,
    body: str = "BODY\n",
    images: dict[str, Any] | None = None,
    model_banner: str | None = None,
    convert_banner: tuple[str, str] | None = None,
    convert_error: Exception | None = None,
) -> SimpleNamespace:
    """Build mocks standing in for marker's library entry points.

    The banners make the fakes print, for output-isolation tests.
    `convert_error` is raised inside the converter call.
    """
    loaded_models: dict[str, Any] = {"loaded": True}

    def _create(device: Any = None) -> dict[str, Any]:
        if model_banner is not None:
            print(model_banner)  # noqa: T201 -- simulates the real engine's console output for the capture test
        return loaded_models

    create_model_dict = MagicMock(side_effect=_create)

    def _convert(filepath: str) -> str:
        if convert_banner is not None:
            print(convert_banner[0])  # noqa: T201 -- simulates the real engine's console output for the capture test
            print(convert_banner[1], file=sys.stderr)  # noqa: T201 -- simulates the real engine's console output for the capture test
        if convert_error is not None:
            raise convert_error
        return "RENDERED"

    converter_instance = MagicMock(side_effect=_convert)
    pdf_converter = MagicMock(return_value=converter_instance)
    text_from_rendered = MagicMock(return_value=(body, "md", images or {}))

    config_parser_instance = MagicMock()
    config_parser_instance.generate_config_dict.return_value = {"effective": True}
    config_parser_instance.get_processors.return_value = ["processor"]
    config_parser_instance.get_renderer.return_value = "renderer"
    config_parser = MagicMock(return_value=config_parser_instance)

    return SimpleNamespace(
        create_model_dict=create_model_dict,
        converter_instance=converter_instance,
        pdf_converter=pdf_converter,
        text_from_rendered=text_from_rendered,
        config_parser=config_parser,
        loaded_models=loaded_models,
    )


@contextmanager
def _install_fake_marker(fake: SimpleNamespace) -> Iterator[None]:
    """Register fake marker modules so the engine's lazy imports resolve.

    A real `__spec__` keeps `find_spec("marker")` truthy.
    """
    marker_mod: Any = types.ModuleType("marker")
    marker_mod.__spec__ = importlib.machinery.ModuleSpec("marker", None)
    models_mod: Any = types.ModuleType("marker.models")
    models_mod.create_model_dict = fake.create_model_dict
    converters_mod: Any = types.ModuleType("marker.converters")
    pdf_mod: Any = types.ModuleType("marker.converters.pdf")
    pdf_mod.PdfConverter = fake.pdf_converter
    output_mod: Any = types.ModuleType("marker.output")
    output_mod.text_from_rendered = fake.text_from_rendered
    config_mod: Any = types.ModuleType("marker.config")
    parser_mod: Any = types.ModuleType("marker.config.parser")
    parser_mod.ConfigParser = fake.config_parser
    marker_mod.models = models_mod
    marker_mod.converters = converters_mod
    converters_mod.pdf = pdf_mod
    marker_mod.output = output_mod
    marker_mod.config = config_mod
    config_mod.parser = parser_mod
    modules = {
        "marker": marker_mod,
        "marker.models": models_mod,
        "marker.converters": converters_mod,
        "marker.converters.pdf": pdf_mod,
        "marker.output": output_mod,
        "marker.config": config_mod,
        "marker.config.parser": parser_mod,
    }
    with patch.dict(sys.modules, modules):
        yield


def _write_pdf_bytes(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4 minimal")


def test_marker_engine_method_and_extensions(tmp_path: Path) -> None:
    engine = MarkerEngine(tmp_path)
    assert engine.method is ConversionMethod.MARKER
    assert engine.extensions == frozenset({"pdf"})


def test_marker_engine_available_when_package_present(tmp_path: Path) -> None:
    with patch("raw2md.engines.marker.find_spec", return_value=MagicMock()):
        assert MarkerEngine(tmp_path).available() is True


def test_marker_engine_unavailable_when_package_missing(tmp_path: Path) -> None:
    with patch("raw2md.engines.marker.find_spec", return_value=None):
        assert MarkerEngine(tmp_path).available() is False


def test_marker_engine_convert_raises_when_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    with (
        patch("raw2md.engines.marker.find_spec", return_value=None),
        pytest.raises(ConversionError, match="marker is not installed"),
    ):
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())


def test_marker_engine_convert_returns_body(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker(body="# Title\n")

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    assert result.body == "# Title\n"
    assert result.media == ()


def test_marker_engine_fills_source_pages_from_real_pdf(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf(source, pages=3, text="Page text content here.")
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    assert result.source_pages == 3


def test_marker_engine_source_pages_none_when_count_fails(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)  # not a real pdf: PyMuPDF cannot open it
    fake = _make_fake_marker(body="# Title\n")

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    # A failed page count does not sink an already-successful conversion.
    assert result.body == "# Title\n"
    assert result.source_pages is None


def test_marker_engine_builds_converter_through_config_parser(tmp_path: Path) -> None:
    # Config, processors, and renderer come from ConfigParser.
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())

    parser_options = fake.config_parser.call_args.args[0]
    assert parser_options.get("output_format") == "markdown"
    kwargs = fake.pdf_converter.call_args.kwargs
    assert kwargs["config"] == {"effective": True}
    assert kwargs["processor_list"] == ["processor"]
    assert kwargs["renderer"] == "renderer"
    assert kwargs["artifact_dict"] is fake.loaded_models


def test_marker_engine_redirects_output_to_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    log = io.StringIO()
    fake = _make_fake_marker(
        model_banner="MODEL LOADING",
        convert_banner=("MARKER STDOUT", "SURYA STDERR"),
    )

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path, log_stream=log).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    captured = capsys.readouterr()
    assert "MARKER STDOUT" not in captured.out
    assert "SURYA STDERR" not in captured.err
    log_text = log.getvalue()
    assert "MODEL LOADING" in log_text
    assert "MARKER STDOUT" in log_text
    assert "SURYA STDERR" in log_text


def test_marker_engine_discards_output_without_log(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker(convert_banner=("NOISE OUT", "NOISE ERR"))

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())

    captured = capsys.readouterr()
    assert "NOISE OUT" not in captured.out
    assert "NOISE ERR" not in captured.err


def test_marker_engine_loads_model_once_across_files(tmp_path: Path) -> None:
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    _write_pdf_bytes(first)
    _write_pdf_bytes(second)
    fake = _make_fake_marker()
    engine = MarkerEngine(tmp_path)

    with _install_fake_marker(fake):
        engine.convert(first, tmp_path / "a", ConvertOptions())
        engine.convert(second, tmp_path / "b", ConvertOptions())

    # One loaded model is shared across the queue.
    assert fake.create_model_dict.call_count == 1


def test_marker_engine_cuda_off_forces_cpu(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path, cuda=False).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    assert fake.create_model_dict.call_args.kwargs.get("device") == "cpu"


def test_marker_engine_cuda_on_auto_selects_device(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path, cuda=True).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    assert fake.create_model_dict.call_args.kwargs.get("device") is None


def test_marker_engine_ascii_source_passed_through(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())

    filepath = fake.converter_instance.call_args.args[0]
    assert filepath == str(source.resolve())


def test_marker_engine_non_ascii_source_copied_to_ascii_temp(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source = src_dir / "файл.pdf"
    _write_pdf_bytes(source)
    temp_root = tmp_path / "asciitmp"
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(temp_root).convert(source, tmp_path / "out", ConvertOptions())

    filepath = fake.converter_instance.call_args.args[0]
    assert filepath != str(source.resolve())
    assert str(filepath).isascii()
    assert Path(filepath).name == "input.pdf"
    assert Path(filepath).is_relative_to(temp_root)


def test_marker_engine_cleans_temp_after_non_ascii(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source = src_dir / "файл.pdf"
    _write_pdf_bytes(source)
    temp_root = tmp_path / "asciitmp"
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(temp_root).convert(source, tmp_path / "out", ConvertOptions())

    # The per-call work folder is removed once conversion finishes.
    assert list(temp_root.glob("marker_*")) == []


def test_marker_engine_cleans_temp_on_failure(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source = src_dir / "файл.pdf"
    _write_pdf_bytes(source)
    temp_root = tmp_path / "asciitmp"
    fake = _make_fake_marker(convert_error=RuntimeError("boom"))

    with _install_fake_marker(fake), pytest.raises(ConversionError):
        MarkerEngine(temp_root).convert(source, tmp_path / "out", ConvertOptions())

    assert list(temp_root.glob("marker_*")) == []


def test_marker_engine_extracts_images(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    image = Image.new("RGB", (2, 2), "white")
    fake = _make_fake_marker(images={"fig_1.png": image, "fig_0.png": image})
    media_dir = tmp_path / "doc"

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(source, media_dir, ConvertOptions())

    assert result.media == ("fig_0.png", "fig_1.png")
    assert (media_dir / "fig_0.png").exists()
    assert (media_dir / "fig_1.png").exists()


def test_marker_engine_disable_image_extraction(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    image = Image.new("RGB", (2, 2), "white")
    fake = _make_fake_marker(images={"fig.png": image})
    media_dir = tmp_path / "doc"

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, media_dir, ConvertOptions(extract_media=False)
        )

    assert result.media == ()
    assert not media_dir.exists()
    # ConfigParser translates the flag into marker's effective config.
    parser_options = fake.config_parser.call_args.args[0]
    assert parser_options.get("disable_image_extraction") is True


def test_marker_engine_recognition_batch_size_reaches_config(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path, recognition_batch_size=8).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    parser_options = fake.config_parser.call_args.args[0]
    assert parser_options.get("recognition_batch_size") == 8


def test_marker_engine_no_recognition_batch_size_by_default(tmp_path: Path) -> None:
    # ConfigParser reads the key's presence, so it must be absent, not None.
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker()

    with _install_fake_marker(fake):
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())

    parser_options = fake.config_parser.call_args.args[0]
    assert "recognition_batch_size" not in parser_options


def _paginated(*blocks: str) -> str:
    """marker's paginated output: `{page}` plus the separator, blank-line wrapped."""
    return "\n\n" + "\n\n".join(blocks) + "\n"


def test_marker_engine_leaves_output_unpaginated_by_default(tmp_path: Path) -> None:
    # Page marks are inspection's addressing; without it none are written.
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    fake = _make_fake_marker(body="# Title\n\nBody text.\n")

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    parser_options = fake.config_parser.call_args.args[0]
    assert "paginate_output" not in parser_options
    assert result.body == "# Title\n\nBody text.\n"


def test_marker_engine_rewrites_page_separators_into_marks(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    body = _paginated(
        "{0}<!-- raw2md-page-break -->",
        "# Title",
        "First page text.",
        "{1}<!-- raw2md-page-break -->",
        "Second page text.",
    )
    fake = _make_fake_marker(body=body)

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions(mark_pages=True)
        )

    parser_options = fake.config_parser.call_args.args[0]
    assert parser_options.get("paginate_output") is True
    # marker counts pages from 0, the mark from 1; each mark sits directly
    # above its page's first line.
    assert result.body == "\n".join(
        [
            page_mark(1),
            "# Title",
            "",
            "First page text.",
            "",
            page_mark(2),
            "Second page text.",
        ]
    )


def test_marker_engine_holds_a_mark_out_of_a_block(tmp_path: Path) -> None:
    # A list crosses the page boundary; a mark inside it would read as a list
    # line, so it waits for the block to end.
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    body = _paginated(
        "{0}<!-- raw2md-page-break -->",
        "- first item",
        "- second item\n{1}<!-- raw2md-page-break -->\n- third item",
        "After the list.",
    )
    fake = _make_fake_marker(body=body)

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions(mark_pages=True)
        )

    lines = result.body.split("\n")
    assert lines[lines.index(page_mark(2)) + 1] == "After the list."
    assert page_mark(2) not in lines[: lines.index("- third item")]


def test_marker_engine_rejoins_a_paragraph_split_by_a_page_break(
    tmp_path: Path,
) -> None:
    # Paginated, marker splits a paragraph at the boundary; the rejoin keeps
    # the marked text equal to the unmarked one.
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    body = _paginated(
        "{0}<!-- raw2md-page-break -->",
        "A paragraph that runs ",
        "{1}<!-- raw2md-page-break -->",
        "across the page boundary.",
        "A later paragraph.",
    )
    fake = _make_fake_marker(body=body)

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions(mark_pages=True)
        )

    body_out, pages = split_page_marks(result.body)
    assert body_out == (
        "A paragraph that runs across the page boundary.\n\nA later paragraph."
    )
    # The second page opens mid-paragraph, so its mark waits for the next block.
    assert pages == ((0, 1), (2, 2))


def test_marker_engine_marks_a_block_that_runs_to_the_end(tmp_path: Path) -> None:
    # No later block to wait for, so the mark goes to the top of the block.
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    body = _paginated(
        "{0}<!-- raw2md-page-break -->",
        "Opening paragraph.",
        "- first item\n{1}<!-- raw2md-page-break -->\n- second item",
    )
    fake = _make_fake_marker(body=body)

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions(mark_pages=True)
        )

    body_out, pages = split_page_marks(result.body)
    assert body_out == "Opening paragraph.\n\n- first item\n- second item"
    assert pages == ((0, 1), (2, 2))


def test_marker_engine_drops_a_mark_with_no_line_to_address(tmp_path: Path) -> None:
    # A trailing blank page opens nothing, and leaving it out shifts nothing.
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    body = _paginated(
        "{0}<!-- raw2md-page-break -->",
        "Only page with text.",
        "{1}<!-- raw2md-page-break -->",
    )
    fake = _make_fake_marker(body=body)

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions(mark_pages=True)
        )

    assert result.body == f"{page_mark(1)}\nOnly page with text."


def test_marker_engine_stacks_marks_of_a_page_with_no_text(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)
    body = _paginated(
        "{0}<!-- raw2md-page-break -->",
        "First page text.",
        "{1}<!-- raw2md-page-break -->",
        "{2}<!-- raw2md-page-break -->",
        "Third page text.",
    )
    fake = _make_fake_marker(body=body)

    with _install_fake_marker(fake):
        result = MarkerEngine(tmp_path).convert(
            source, tmp_path / "doc", ConvertOptions(mark_pages=True)
        )

    body_out, pages = split_page_marks(result.body)
    assert body_out == "First page text.\n\nThird page text."
    # The empty page keeps its number and gets no lines of its own.
    assert pages == ((0, 1), (2, 2), (2, 3))


def test_marker_engine_wraps_conversion_failure(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf(source, pages=1, text="Readable text.")
    fake = _make_fake_marker(convert_error=RuntimeError("boom"))

    with (
        _install_fake_marker(fake),
        # The source opens, so the engine's own text stands.
        pytest.raises(ConversionError, match="boom"),
    ):
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())


def test_marker_engine_failure_names_a_pdf_that_does_not_open(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_bytes(source)  # %PDF- headed, but no pdf any reader can open
    fake = _make_fake_marker(convert_error=RuntimeError("boom"))

    with (
        _install_fake_marker(fake),
        pytest.raises(ConversionError, match="the pdf does not open"),
    ):
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())


def test_marker_engine_failure_names_a_pdf_with_no_page(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    # A pdf cut off before its pages opens but holds nothing.
    source.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
    fake = _make_fake_marker(convert_error=RuntimeError("boom"))

    with _install_fake_marker(fake), pytest.raises(ConversionError) as caught:
        MarkerEngine(tmp_path).convert(source, tmp_path / "doc", ConvertOptions())

    message = str(caught.value)
    assert "carries no readable page" in message
    # A damaged input does not prove the failure came from it.
    assert "boom" in message


# ---------------------------------------------------------------------------
# Subprocess output condensing
# ---------------------------------------------------------------------------


def test_condense_collapses_consecutive_duplicates() -> None:
    text = "start\n" + "same line\n" * 5 + "end"

    assert condense_process_output(text) == "start\nsame line (repeated 5 times)\nend"


def test_condense_keeps_distinct_lines_intact() -> None:
    text = "first\nsecond\nthird"

    assert condense_process_output(text) == text


def test_condense_caps_line_count() -> None:
    text = "\n".join(f"line {i}" for i in range(30))

    condensed = condense_process_output(text, max_lines=5)

    assert condensed.splitlines() == [
        "line 0",
        "line 1",
        "line 2",
        "line 3",
        "line 4",
        "... (+25 more lines)",
    ]


def test_condense_empty_output_stays_empty() -> None:
    assert condense_process_output("") == ""


# ---------------------------------------------------------------------------
# DjvuEngine (djvu chain, stubbed)
# ---------------------------------------------------------------------------


def _make_stub_marker_engine(
    *,
    available: bool = True,
    body: str = "# Converted\n",
    error: Exception | None = None,
) -> MagicMock:
    """Stand-in MarkerEngine for DjvuEngine chain tests."""
    marker = MagicMock(spec=MarkerEngine)
    marker.available.return_value = available
    if error is not None:
        marker.convert.side_effect = error
    else:
        marker.convert.return_value = ConversionResult(body=body)
    return marker


def _requested_pages(cmd: list[str], page_count: int) -> tuple[int, int]:
    """Page range a ddjvu command asks for, clamped to the document."""
    for arg in cmd:
        if arg.startswith("-page="):
            first_text, last_text = arg.removeprefix("-page=").split("-")
            return int(first_text), min(int(last_text), page_count)
    return 1, page_count


def _fake_djvu_run(
    page_count: int = 3,
    *,
    page_count_readable: bool = True,
    ddjvu_error: bytes | None = None,
    render: bool = True,
) -> Callable[..., MagicMock]:
    """subprocess.run stand-in for the djvu chain.

    djvused answers with the page count; ddjvu writes one TIFF per page, as
    `-eachpage` does.
    """

    def run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stdout = b""
        result.stderr = b""
        if cmd[0] == "djvused":
            if not page_count_readable:
                result.returncode = 1
                result.stderr = b"djvused: cannot open file"
            else:
                result.stdout = f"{page_count}\n".encode()
            return result
        if ddjvu_error is not None:
            result.returncode = 1
            result.stderr = ddjvu_error
            return result
        if render:
            first, last = _requested_pages(cmd, page_count)
            for page in range(first, last + 1):
                Path(cmd[-1] % page).write_bytes(b"fake tiff")
        return result

    return run


def _ddjvu_calls(sp: MagicMock) -> list[list[str]]:
    """Commands the mock received, ddjvu only (djvused probes filtered out)."""
    return [call.args[0] for call in sp.call_args_list if call.args[0][0] == "ddjvu"]


def test_djvu_engine_method_and_extensions(tmp_path: Path) -> None:
    engine = DjvuEngine(MagicMock(spec=MarkerEngine), tmp_path)
    assert engine.method is ConversionMethod.DJVU_MARKER
    assert engine.extensions == frozenset({"djvu"})


def test_djvu_engine_available_when_all_deps_present(tmp_path: Path) -> None:
    marker = _make_stub_marker_engine()
    with (
        patch("raw2md.engines.djvu.shutil.which", return_value="/usr/bin/ddjvu"),
        patch("raw2md.engines.djvu.find_spec", return_value=MagicMock()),
    ):
        assert DjvuEngine(marker, tmp_path).available() is True


def test_djvu_engine_unavailable_when_ddjvu_missing(tmp_path: Path) -> None:
    marker = _make_stub_marker_engine()
    with (
        patch("raw2md.engines.djvu.shutil.which", return_value=None),
        patch("raw2md.engines.djvu.find_spec", return_value=MagicMock()),
    ):
        assert DjvuEngine(marker, tmp_path).available() is False


def test_djvu_engine_unavailable_when_img2pdf_missing(tmp_path: Path) -> None:
    marker = _make_stub_marker_engine()
    with (
        patch("raw2md.engines.djvu.shutil.which", return_value="/usr/bin/ddjvu"),
        patch("raw2md.engines.djvu.find_spec", return_value=None),
    ):
        assert DjvuEngine(marker, tmp_path).available() is False


def test_djvu_engine_unavailable_when_marker_unavailable(tmp_path: Path) -> None:
    marker = _make_stub_marker_engine(available=False)
    with (
        patch("raw2md.engines.djvu.shutil.which", return_value="/usr/bin/ddjvu"),
        patch("raw2md.engines.djvu.find_spec", return_value=MagicMock()),
    ):
        assert DjvuEngine(marker, tmp_path).available() is False


def test_djvu_engine_calls_ddjvu_with_tiff_format(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()) as sp,
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    cmd: list[str] = _ddjvu_calls(sp)[0]
    assert "-format=tiff" in cmd
    # One file per page, so no TIFF hits the container's size cap.
    assert "-eachpage" in cmd
    assert cmd[-2] == str(source.resolve())


def test_djvu_engine_passes_page_tiffs_to_img2pdf(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run(3)),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    tiff_paths: list[str] = img2pdf_mock.convert.call_args.args[0]
    assert [Path(p).name for p in tiff_paths] == [
        "page0001.tiff",
        "page0002.tiff",
        "page0003.tiff",
    ]
    # A scan that needs per-page rendering is too large to assemble in memory.
    assert img2pdf_mock.convert.call_args.kwargs["outputstream"] is not None


def test_djvu_engine_passes_pdf_to_marker(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    pdf_arg: Path = marker.convert.call_args.args[0]
    assert pdf_arg.name == "assembled.pdf"


def test_djvu_engine_forwards_options_to_marker(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"
    opts = ConvertOptions(extract_media=False)

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, tmp_path).convert(source, tmp_path / "book", opts)

    assert marker.convert.call_args.args[2] is opts


def test_djvu_engine_returns_marker_result(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine(body="# DjVu result\n")
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        result = DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    assert result.body == "# DjVu result\n"


def test_djvu_engine_raises_on_ddjvu_failure(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    with (
        patch(
            "raw2md.engines.djvu.subprocess.run",
            side_effect=_fake_djvu_run(ddjvu_error=b"bad format"),
        ),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(ConversionError, match="ddjvu failed"),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )


def test_djvu_engine_raises_on_img2pdf_failure(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.side_effect = ValueError("unsupported format")

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(ConversionError, match="img2pdf assembly failed"),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )


def test_djvu_engine_temp_cleaned_up_on_success(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    temp_root = tmp_path / "tmp"
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, temp_root).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    assert list(temp_root.glob("raw2md_djvu_*")) == []


def test_djvu_engine_leaves_the_assembled_pdf_in_the_scratch_dir(
    tmp_path: Path,
) -> None:
    # Inspection reads this pdf, so it outlives the call.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    temp_root = tmp_path / "tmp"
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        result = DjvuEngine(marker, temp_root).convert(
            source, tmp_path / "book", ConvertOptions(scratch_dir=scratch)
        )

    assert result.source_pdf is not None
    assert result.source_pdf.parent == scratch
    assert result.source_pdf.is_file()
    assert marker.convert.call_args.args[0] == result.source_pdf
    # The per-page TIFFs go with their temp dir.
    assert list(temp_root.glob("raw2md_djvu_*")) == []


def test_djvu_engine_names_no_pdf_without_a_scratch_dir(tmp_path: Path) -> None:
    # Without a caller-owned folder the pdf dies with the temp dir, so it is
    # not named.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        result = DjvuEngine(marker, tmp_path / "tmp").convert(
            source, tmp_path / "book", ConvertOptions()
        )

    assert result.source_pdf is None


def test_djvu_engine_non_ascii_source_copied_to_temp(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source = src_dir / "книга.djvu"
    source.write_bytes(b"fake djvu")
    temp_root = tmp_path / "tmp"
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()) as sp,
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, temp_root).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    source_arg: str = _ddjvu_calls(sp)[0][-2]
    assert source_arg.isascii()
    assert source_arg != str(source.resolve())
    assert source_arg.endswith(".djvu")


def test_djvu_engine_raises_on_ddjvu_timeout(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])  # type: ignore[arg-type]

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=fake_run),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(ConversionError, match="ddjvu timed out"),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )


def test_djvu_engine_raises_on_ddjvu_not_found(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    with (
        patch(
            "raw2md.engines.djvu.subprocess.run",
            side_effect=FileNotFoundError("No such file"),
        ),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(
            ConversionError, match="ddjvu not found or could not be launched"
        ),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )


def test_djvu_to_pdf_wraps_copy_failure(tmp_path: Path) -> None:
    # A failed copy for ddjvu must be a ConversionError, not an OSError that
    # aborts the batch.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    source = src_dir / "книга.djvu"  # non-ASCII forces the copy path
    source.write_bytes(b"fake djvu")
    temp_root = tmp_path / "tmp"

    with (
        patch("raw2md.engines.djvu.shutil.copy2", side_effect=OSError("disk full")),
        pytest.raises(ConversionError, match="could not stage djvu source"),
    ):
        djvu_to_pdf(source, tmp_path / "out.pdf", temp_root)


def test_djvu_engine_temp_cleaned_up_on_failure(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    temp_root = tmp_path / "tmp"
    marker = _make_stub_marker_engine(error=ConversionError("marker failed"))
    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.return_value = b"%PDF-fake"

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run()),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(ConversionError),
    ):
        DjvuEngine(marker, temp_root).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    assert list(temp_root.glob("raw2md_djvu_*")) == []


def test_djvu_renders_pages_in_bounded_groups(tmp_path: Path) -> None:
    # A whole large scan in one call can outrun a single timeout window.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    with (
        patch(
            "raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run(40)
        ) as sp,
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    ranges = [
        arg for cmd in _ddjvu_calls(sp) for arg in cmd if arg.startswith("-page=")
    ]
    assert ranges == ["-page=1-16", "-page=17-32", "-page=33-40"]
    tiff_paths: list[str] = img2pdf_mock.convert.call_args.args[0]
    assert len(tiff_paths) == 40


def test_djvu_pages_are_assembled_in_page_order(tmp_path: Path) -> None:
    # The assembled order comes from page numbers, not file order.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=_fake_djvu_run(20)),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    tiff_paths: list[str] = img2pdf_mock.convert.call_args.args[0]
    assert [Path(p).name for p in tiff_paths[:2]] == ["page0001.tiff", "page0002.tiff"]
    assert Path(tiff_paths[-1]).name == "page0020.tiff"


def test_djvu_page_order_is_numeric_not_lexicographic() -> None:
    from raw2md.engines.djvu import _page_number

    names = ["page0002.tiff", "page0010.tiff", "page9.tiff", "page1.tiff"]
    ordered = sorted((Path(name) for name in names), key=_page_number)

    assert [p.name for p in ordered] == [
        "page1.tiff",
        "page0002.tiff",
        "page9.tiff",
        "page0010.tiff",
    ]


def test_djvu_renders_whole_document_when_page_count_unreadable(
    tmp_path: Path,
) -> None:
    # djvused is optional: without a page count the render is one call.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    with (
        patch(
            "raw2md.engines.djvu.subprocess.run",
            side_effect=_fake_djvu_run(5, page_count_readable=False),
        ) as sp,
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    calls = _ddjvu_calls(sp)
    assert len(calls) == 1
    assert not any(arg.startswith("-page=") for arg in calls[0])
    assert len(img2pdf_mock.convert.call_args.args[0]) == 5


def test_djvu_raises_when_no_page_was_rendered(tmp_path: Path) -> None:
    # ddjvu succeeding with no output must not reach img2pdf.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()

    with (
        patch(
            "raw2md.engines.djvu.subprocess.run",
            side_effect=_fake_djvu_run(3, render=False),
        ),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(ConversionError, match="rendered no pages"),
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    img2pdf_mock.convert.assert_not_called()


def test_djvu_error_message_collapses_repeated_stderr(tmp_path: Path) -> None:
    # libtiff repeats a write error per strip; the log keeps one line.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    marker = _make_stub_marker_engine()
    img2pdf_mock = MagicMock()
    stderr = b"Maximum TIFF file size exceeded.\n" * 900

    with (
        patch(
            "raw2md.engines.djvu.subprocess.run",
            side_effect=_fake_djvu_run(ddjvu_error=stderr),
        ),
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(ConversionError) as excinfo,
    ):
        DjvuEngine(marker, tmp_path).convert(
            source, tmp_path / "book", ConvertOptions()
        )

    message = str(excinfo.value)
    assert "Maximum TIFF file size exceeded. (repeated 900 times)" in message
    assert len(message.splitlines()) == 1


def test_djvu_partial_pdf_is_removed_when_assembly_fails(tmp_path: Path) -> None:
    # A half-written PDF left behind would be handed to marker as if complete.
    from raw2md.engines.djvu import _assemble_pdf

    img2pdf_mock = MagicMock()
    img2pdf_mock.convert.side_effect = ValueError("unsupported format")
    output = tmp_path / "assembled.pdf"

    with (
        patch.dict(sys.modules, {"img2pdf": img2pdf_mock}),
        pytest.raises(ConversionError, match="img2pdf assembly failed"),
    ):
        _assemble_pdf([tmp_path / "page0001.tiff"], output)

    assert not output.exists()


def _fake_djvutxt_run(
    pages: list[str], *, page_count_readable: bool = True
) -> Callable[..., MagicMock]:
    """subprocess.run stand-in for djvused + djvutxt.

    djvutxt closes every printed page with a form feed and prints nothing for
    a page without a text chunk.
    """

    def run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stdout = b""
        result.stderr = b""
        if cmd[0] == "djvused":
            if not page_count_readable:
                result.returncode = 1
                result.stderr = b"djvused: cannot open file"
            else:
                result.stdout = f"{len(pages)}\n".encode()
            return result
        selected = [arg for arg in cmd if arg.startswith("-page=")]
        asked = (
            pages
            if not selected
            else [pages[int(selected[0].removeprefix("-page=")) - 1]]
        )
        result.stdout = "".join(f"{text}\f" for text in asked if text).encode()
        return result

    return run


def _djvutxt_calls(sp: MagicMock) -> list[list[str]]:
    """Commands the mock received, djvutxt only (djvused probes filtered out)."""
    return [call.args[0] for call in sp.call_args_list if call.args[0][0] == "djvutxt"]


def test_djvu_page_texts_read_a_recognized_book_in_one_call(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")

    with patch(
        "raw2md.engines.djvu.subprocess.run",
        side_effect=_fake_djvutxt_run(["First page.", "Second page."]),
    ) as sp:
        pages = page_texts(source)

    assert pages == ["First page.", "Second page."]
    # One chunk per page leaves no ambiguity, so no page is read again.
    assert len(_djvutxt_calls(sp)) == 1


def test_djvu_page_texts_of_an_image_only_scan_are_empty(tmp_path: Path) -> None:
    source = tmp_path / "scan.djvu"
    source.write_bytes(b"fake djvu")

    with patch(
        "raw2md.engines.djvu.subprocess.run",
        side_effect=_fake_djvutxt_run(["", "", ""]),
    ) as sp:
        pages = page_texts(source)

    assert pages == ["", "", ""]
    assert len(_djvutxt_calls(sp)) == 1


def test_djvu_page_texts_stay_aligned_when_only_some_pages_are_recognized(
    tmp_path: Path,
) -> None:
    # djvutxt separates the pages it printed, not the document's pages.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")

    with patch(
        "raw2md.engines.djvu.subprocess.run",
        side_effect=_fake_djvutxt_run(["", "Second page.", ""]),
    ) as sp:
        pages = page_texts(source)

    assert pages == ["", "Second page.", ""]
    per_page = [cmd[1] for cmd in _djvutxt_calls(sp)[1:]]
    assert per_page == ["-page=1", "-page=2", "-page=3"]


def test_djvu_page_texts_fail_when_the_page_count_is_unreadable(tmp_path: Path) -> None:
    # Without the page count the dump cannot be aligned to the document.
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")

    with (
        patch(
            "raw2md.engines.djvu.subprocess.run",
            side_effect=_fake_djvutxt_run(["First page."], page_count_readable=False),
        ),
        pytest.raises(ConversionError, match="could not count pages"),
    ):
        page_texts(source)


def test_djvu_page_texts_fail_when_djvutxt_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    fake = _fake_djvutxt_run(["First page."])

    def run(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[0] == "djvutxt":
            raise OSError("No such file or directory: 'djvutxt'")
        return fake(cmd, **kwargs)

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=run),
        pytest.raises(ConversionError, match="djvutxt not found"),
    ):
        page_texts(source)


def test_djvu_page_texts_fail_when_djvutxt_reports_an_error(tmp_path: Path) -> None:
    source = tmp_path / "book.djvu"
    source.write_bytes(b"fake djvu")
    fake = _fake_djvutxt_run(["First page."])

    def run(cmd: list[str], **kwargs: object) -> MagicMock:
        result = fake(cmd, **kwargs)
        if cmd[0] == "djvutxt":
            result.returncode = 1
            result.stderr = b"djvutxt: cannot open file"
        return result

    with (
        patch("raw2md.engines.djvu.subprocess.run", side_effect=run),
        pytest.raises(ConversionError, match="cannot open file"),
    ):
        page_texts(source)
