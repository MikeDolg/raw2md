"""End-to-end round-trip tests: generate a format, convert, check the contract.

Behind the ``roundtrip`` marker; the docx branch needs only pandoc, the other
branches drive marker. Run explicitly::

    uv run pytest -m roundtrip                 # the whole suite
    uv run pytest -m roundtrip -k docx         # GPU-free docx only
    uv run pytest -m roundtrip -k pdf          # all born-digital PDF tests

Only the deterministic contract is asserted; the word-level grade stays with
the generation-analyst agent.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest
from PIL import Image

from raw2md.cleaner import clean
from raw2md.exit_codes import ExitCode
from raw2md.header import ResultStatus
from raw2md.mdtext.links import HTML_IMG_RE
from raw2md.mdtext.tables import table_cells
from raw2md.output import encode_link_path
from raw2md.quality.evaluator import CheckId, Evaluation

from ._paths import (
    CORPUS_DIR,
    FONTS_DIR,
    HANDWRITING_FONT_EXT,
    HANDWRITING_FONT_NAME,
)
from ._structure import compare_structure
from .roundtrip import TERMINAL_STATUSES, RoundtripResult, run_roundtrip

pytestmark = pytest.mark.roundtrip


def _require_tools(
    *,
    marker: bool = False,
    xelatex: bool = False,
    djvu: bool = False,
    img2pdf: bool = False,
    handwriting_font: bool = False,
) -> None:
    """Skip a round-trip test whose generation or conversion tool is absent.

    marker is probed with ``find_spec`` as the engine does, ``img2pdf`` on PATH,
    and the handwriting font as a file.
    """
    if shutil.which("pandoc") is None:
        pytest.skip("pandoc is not installed")
    if xelatex and shutil.which("xelatex") is None:
        pytest.skip("xelatex is not installed")
    if djvu and (
        shutil.which("c44") is None
        or shutil.which("djvm") is None
        or shutil.which("ddjvu") is None
    ):
        pytest.skip("DjVuLibre (c44/djvm/ddjvu) is not installed")
    if img2pdf and shutil.which("img2pdf") is None:
        pytest.skip("img2pdf is not installed")
    if handwriting_font:
        font = FONTS_DIR / f"{HANDWRITING_FONT_NAME}{HANDWRITING_FONT_EXT}"
        if not font.is_file():
            pytest.skip("handwriting font asset is absent")
    if marker and importlib.util.find_spec("marker") is None:
        pytest.skip("marker is not installed (heavy OCR/GPU dependency)")


def _assert_wrote_result(result: RoundtripResult) -> None:
    """The shared contract: a single-file run produced a well-formed result."""
    assert result.exit_code == int(ExitCode.SUCCESS), result
    assert result.output_md is not None
    assert result.output_md.exists()
    assert result.header is not None
    assert result.header.status in TERMINAL_STATUSES


# --- born-digital DOCX (GPU-free) ------------------------------------------


@pytest.mark.parametrize(
    "fixture",
    [
        "mixed",
        "headers",
        "tables",
        "table_formulas",
        "table_math_pipes",
        "chart_series",
        "images",
        "formulas",
        "multiline_display_math",
        "nested_lists",
        "footnotes",
        "multilang",
        "long_doc",
        "engineering_prose",
        "math_legend",
    ],
)
def test_docx_roundtrip_contract(home: Path, fixture: str) -> None:
    """DOCX round-trips through pandoc with a near-perfect structural match.

    Headings, tables, and images are exact. A formula tolerance of 1 covers a
    formula that a pandoc minor version reformats.
    """
    _require_tools()
    result = run_roundtrip(CORPUS_DIR / f"{fixture}.md", "docx", home / "work")
    _assert_wrote_result(result)
    assert result.header is not None
    assert result.header.engine == "pandoc"
    out_counts = result.output_counts
    assert out_counts is not None
    diffs = compare_structure(
        result.reference_counts,
        out_counts,
        display_formula_tolerance=1,
        inline_formula_tolerance=1,
    )
    assert diffs == [], f"structural drift in {fixture}.docx: {diffs}"


def test_docx_images_extracts_media(home: Path) -> None:
    """An image-bearing DOCX extracts healthy media and the result references it.

    The assets sit flat in the media folder, each is referenced in the body, and
    each is a real image, so the status is ``ok``.
    """
    _require_tools()
    result = run_roundtrip(CORPUS_DIR / "images.md", "docx", home / "work")
    _assert_wrote_result(result)
    assert result.output_md is not None
    media_dir = result.output_md.with_suffix("")
    assert not (media_dir / "media").exists(), "media stayed nested under media/"
    assets = [p for p in media_dir.rglob("*") if p.is_file()]
    assert assets, "no media was extracted from the docx"
    for asset in assets:
        assert asset.parent == media_dir, f"{asset} is not flat in {media_dir}"
    assert result.output_body is not None
    for asset in assets:
        assert asset.name in result.output_body, f"{asset.name} not referenced"
        size = asset.stat().st_size
        assert size >= 512, f"{asset.name} is too small ({size} bytes)"
        with Image.open(asset) as img:
            colors = img.convert("RGB").getcolors(maxcolors=1)
        assert colors is None, f"{asset.name} is single-color (blank or solid)"
    assert result.header is not None
    assert result.header.status is ResultStatus.OK, (
        f"images.docx round-trip status is {result.header.status!r}; "
        "expected ok with no defective images"
    )


def test_docx_table_formulas_image_link_is_portable(home: Path) -> None:
    """A DOCX image carrying explicit width/height gets a portable HTML `<img src>`.

    pandoc writes a sized image as raw HTML with an absolute ``--extract-media``
    path; the delivered body must not leak it.
    """
    _require_tools()
    result = run_roundtrip(CORPUS_DIR / "table_formulas.md", "docx", home / "work")
    _assert_wrote_result(result)
    assert result.output_body is not None
    matches = list(HTML_IMG_RE.finditer(result.output_body))
    assert matches, "no HTML <img> tag in the table_formulas docx round-trip output"
    for match in matches:
        src = match.group(2)
        assert not re.match(r"^[A-Za-z]:[\\/]", src), f"absolute path leaked: {src}"
        assert not src.startswith("/"), f"absolute path leaked: {src}"
    assert result.header is not None
    assert result.header.status is ResultStatus.OK, (
        f"table_formulas.docx round-trip status is {result.header.status!r}"
    )


def test_docx_table_math_pipes_repairs_bare_pipe_and_multiline(home: Path) -> None:
    """A DOCX round-trip of `table_math_pipes.md` repairs the table-row math defect.

    pandoc turns the modulus into a bare `|` and splits the cases formula over
    lines. The structural check cannot see a broken row, so the rows are checked
    directly: three cells each and the display delimiters intact.
    """
    _require_tools()
    result = run_roundtrip(CORPUS_DIR / "table_math_pipes.md", "docx", home / "work")
    _assert_wrote_result(result)
    assert result.header is not None
    assert result.header.status is ResultStatus.OK, (
        f"table_math_pipes.docx round-trip status is {result.header.status!r}"
    )
    assert result.output_body is not None
    rows = [
        line for line in result.output_body.splitlines() if line.strip().startswith("|")
    ]
    assert len(rows) == 4, f"expected header + separator + 2 data rows, got {rows}"
    modulus_cells = table_cells(rows[2])
    assert len(modulus_cells) == 3, f"a bare pipe split the row: {modulus_cells}"
    assert r"\|" in modulus_cells[2], f"the modulus pipe was not escaped: {rows[2]}"
    cases_cells = table_cells(rows[3])
    assert len(cases_cells) == 3, f"the row was split: {cases_cells}"
    assert cases_cells[2].count("$$") == 2, (
        f"the cases formula lost its display delimiters: {cases_cells[2]}"
    )


def test_docx_multiline_display_math_has_no_false_anchor(home: Path) -> None:
    """A DOCX round-trip of `multiline_display_math.md` carries no `broken-formula`.

    pandoc splits the system over several lines, so its first line alone looks
    like a truncated `\\begin`.
    """
    _require_tools()
    result = run_roundtrip(
        CORPUS_DIR / "multiline_display_math.md", "docx", home / "work"
    )
    _assert_wrote_result(result)
    assert result.header is not None
    assert result.header.status is ResultStatus.OK, (
        f"multiline_display_math.docx round-trip status is {result.header.status!r}"
    )
    assert result.output_body is not None
    assert result.output_body.count("$$") == 2, (
        f"the display formula lost its delimiters: {result.output_body}"
    )
    assert "\\begin{" in result.output_body, (
        f"the environment markers did not survive: {result.output_body}"
    )
    assert "\\end{" in result.output_body, (
        f"the environment markers did not survive: {result.output_body}"
    )
    assert clean(result.output_body) == result.output_body, (
        "cleaning an already-clean multi-line formula must be a no-op"
    )


def test_docx_single_glyph_math_unwraps_to_prose(home: Path) -> None:
    """A DOCX round-trip of `single_glyph_math.md` unwraps the equation-editor glyphs.

    Four of the seven inline spans become prose, so the inline tolerance is sized
    to that drop and every other kind still compares.
    """
    _require_tools()
    result = run_roundtrip(CORPUS_DIR / "single_glyph_math.md", "docx", home / "work")
    _assert_wrote_result(result)
    assert result.header is not None
    assert result.header.status is ResultStatus.OK, (
        f"single_glyph_math.docx round-trip status is {result.header.status!r}"
    )
    assert result.output_body is not None
    out_counts = result.output_counts
    assert out_counts is not None
    diffs = compare_structure(
        result.reference_counts, out_counts, inline_formula_tolerance=4
    )
    assert diffs == [], f"structural drift in single_glyph_math.docx: {diffs}"

    body = result.output_body
    assert "$R$" in body, f"genuine variable R lost its math span: {body!r}"
    assert "$D$" in body, f"genuine variable D lost its math span: {body!r}"
    assert r"$\theta$" in body, f"genuine variable theta lost its math span: {body!r}"
    assert "∅" in body, f"varnothing did not unwrap to the diameter sign: {body!r}"
    assert body.count("°") == 2, f"expected two unwrapped degree signs, got: {body!r}"
    assert "℃" in body, f"the bare degree-Celsius glyph is missing: {body!r}"
    for wrapped in (r"$\varnothing$", r"$\circ$", "$°$", "${^\\circ}$", "$℃$"):
        assert wrapped not in body, f"{wrapped!r} was not unwrapped: {body!r}"


# --- born-digital PDF via marker -------------------------------------------

# Calibrated on a GPU marker run: marker re-levels headings but keeps the total
# within 2, and renders inline math as plain text (up to 4 spans lost).
_PDF_HEADING_TOTAL_TOL = 2
_PDF_TABLE_TOL = 1
_PDF_IMAGE_TOL = 1
_PDF_DISPLAY_FORMULA_TOL = 0
_PDF_INLINE_FORMULA_TOL = 4


def _assert_born_digital_pdf_structure(result: RoundtripResult) -> None:
    """Shared born-digital PDF contract calibrated on a GPU marker run."""
    _assert_wrote_result(result)
    assert result.header is not None
    assert result.header.engine == "marker"
    out = result.output_counts
    assert out is not None
    ref = result.reference_counts
    assert abs(out.headings_total - ref.headings_total) <= _PDF_HEADING_TOTAL_TOL, (
        f"heading total drift: ref={ref.headings_total} out={out.headings_total}"
    )
    diffs = compare_structure(
        ref,
        out,
        check_headings=False,
        table_tolerance=_PDF_TABLE_TOL,
        image_tolerance=_PDF_IMAGE_TOL,
        display_formula_tolerance=_PDF_DISPLAY_FORMULA_TOL,
        inline_formula_tolerance=_PDF_INLINE_FORMULA_TOL,
    )
    assert diffs == [], f"structural drift: {diffs}"


@pytest.mark.parametrize(
    "fixture",
    [
        "mixed",
        "headers",
        "tables",
        "formulas",
        "images",
        "nested_lists",
        "multilang",
        "long_doc",
    ],
)
def test_pdf_born_digital_roundtrip_contract(home: Path, fixture: str) -> None:
    """Born-digital PDFs for each fixture convert through marker within tolerance."""
    _require_tools(marker=True, xelatex=True)
    result = run_roundtrip(CORPUS_DIR / f"{fixture}.md", "pdf", home / "work")
    _assert_born_digital_pdf_structure(result)


def test_pdf_source_filename_with_space_encodes_media_link(home: Path) -> None:
    """A source filename with a space still produces a resolvable media link.

    The space must reach the body percent-encoded, never raw, or CommonMark cuts
    the link target at it. Docx takes the same encoding route.
    """
    _require_tools(marker=True, xelatex=True)
    result = run_roundtrip(
        CORPUS_DIR / "images.md", "pdf", home / "work", stem="my book"
    )
    _assert_born_digital_pdf_structure(result)
    assert result.output_md is not None
    media_dir = result.output_md.with_suffix("")
    assert media_dir.name == "my book"
    assets = [p for p in media_dir.rglob("*") if p.is_file()]
    assert assets, "no media was extracted from the PDF"
    assert result.output_body is not None
    for asset in assets:
        link = encode_link_path(f"{media_dir.name}/{asset.name}")
        assert link in result.output_body, f"{link} not referenced"
        assert " " not in link, f"{link} carries a raw space"


# --- scans and handwriting via marker --------------------------------------

# Recognition-failure floors, tied to the quality thresholds.
_DENSITY_FLOOR = 350
_UNREADABLE_CEILING = 0.15


def _assert_scan_recovered_text_with_drifting_levels(
    result: RoundtripResult,
) -> Evaluation:
    """Shared scan contract: marker ran, the text came back, the levels drifted.

    The verdict is not pinned. The shape of marker's level damage varies with the
    engine build and the card; a ladder flattened upward looks like a short
    document's flat shape, so the same damage grades ``bad`` or ``ok``. The
    per-level drift is pinned instead.
    """
    _assert_wrote_result(result)
    assert result.header is not None
    assert result.header.engine == "marker"
    ev = result.evaluation
    assert ev is not None
    assert ev.recognition_failure is False
    # FLAT_LADDER needs the document to state its ranks; a raster states none.
    assert CheckId.FLAT_LADDER.value not in ev.issues
    # The fixtures print no contents page, so LOST_CHAPTERS has no witness.
    assert CheckId.LOST_CHAPTERS.value not in ev.issues
    assert ev.metrics.get("density", 0) > _DENSITY_FLOOR
    ref = result.reference_counts
    out = result.output_counts
    assert out is not None
    assert abs(out.headings_total - ref.headings_total) <= 3
    assert abs(out.tables - ref.tables) <= 1
    assert ref.headings_by_level != out.headings_by_level
    return ev


@pytest.mark.parametrize("fmt", ["scan", "scan_degraded"], ids=["clean", "degraded"])
def test_printed_scan_recovers_text_but_levels_drift(home: Path, fmt: str) -> None:
    """A printed scan recovers its text; the heading levels do not survive it.

    The mild synthetic degradation causes no recognition failure, so
    ``recognition_failure`` stays silent on both rasters.
    """
    _require_tools(marker=True, xelatex=True, img2pdf=True)
    result = run_roundtrip(CORPUS_DIR / "mixed.md", fmt, home / "work")
    ev = _assert_scan_recovered_text_with_drifting_levels(result)
    assert ev.metrics.get("unreadable_share", 0.0) < _UNREADABLE_CEILING


def test_handwriting_scan_recognition_failure_under_fires(
    home: Path,
) -> None:
    """A handwriting scan reads as garble; the LLM-OCR recommendation under-fires.

    Cyrillic misread as Latin is not unreadable, since both scripts are allowed,
    so the share stays under 15%. A known limit, pinned so a change is deliberate.
    """
    _require_tools(marker=True, xelatex=True, img2pdf=True, handwriting_font=True)
    result = run_roundtrip(
        CORPUS_DIR / "handwriting.md", "handwriting_scan", home / "work"
    )
    _assert_scan_recovered_text_with_drifting_levels(result)


# --- DjVu via ddjvu -> TIFF -> PDF -> marker --------------------------------


def test_djvu_roundtrip_contract(home: Path) -> None:
    """DjVu round-trips through ddjvu -> TIFF -> PDF -> marker within tolerance.

    Calibrated on a GPU marker run at 150 DPI: headings 3 (H3 shifts to H4),
    tables 1, formulas and images up to total loss. The headers fixture is left
    out: marker loses every H3 at this resolution.
    """
    _require_tools(marker=True, xelatex=True, djvu=True)
    result = run_roundtrip(CORPUS_DIR / "mixed.md", "djvu", home / "work")
    _assert_wrote_result(result)
    assert result.header is not None
    assert result.header.engine == "marker"
    out_counts = result.output_counts
    assert out_counts is not None
    ref = result.reference_counts
    # Display and inline are checked apart, so either may drop to zero.
    formula_tol = max(ref.display_formulas, ref.inline_formulas)
    diffs = compare_structure(
        ref,
        out_counts,
        heading_tolerance=3,
        table_tolerance=1,
        display_formula_tolerance=formula_tol,
        inline_formula_tolerance=formula_tol,
        image_tolerance=ref.images,
    )
    assert diffs == [], f"structural drift in mixed.djvu: {diffs}"
