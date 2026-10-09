"""End-to-end round-trip tests with real LLM providers.

Behind the ``llm_live`` marker; they need ``GOOGLE_API_KEY`` and/or the
``claude`` CLI, and some need ``marker``. Run explicitly::

    uv run pytest -m llm_live                   # full real-LLM suite
    uv run pytest -m llm_live -k smoke          # infrastructure smoke test only
    uv run pytest -m llm_live -k post           # post-operation tests only
    uv run pytest -m llm_live -k inspection     # inspection + combined tests
    uv run pytest -m llm_live -k ocr            # ocr (vision) tests only

Only the deterministic contract is asserted; word-level quality is graded by
a review of the output against its fixture.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

import pytest

from raw2md.config import RunConfig
from raw2md.exit_codes import ExitCode
from raw2md.header import ResultHeader, strip_own_header
from raw2md.llm.edit_guard import DEFECT_TYPES
from raw2md.mdtext.zones import segments
from raw2md.orchestrator import run as _run_orchestrator
from raw2md.output import resolve_output_target

from ._paths import CORPUS_DIR
from .roundtrip import TERMINAL_STATUSES, RoundtripResult, run_roundtrip

pytestmark = pytest.mark.llm_live


# ---------------------------------------------------------------------------
# Availability gates
# ---------------------------------------------------------------------------


def _skip_without(*requirements: str) -> None:
    """Skip when a tool or credential (``GOOGLE_API_KEY``) is absent."""
    for req in requirements:
        if req == "GOOGLE_API_KEY":
            if not os.environ.get("GOOGLE_API_KEY"):
                pytest.skip("GOOGLE_API_KEY not set in environment")
        elif req == "marker":
            if importlib.util.find_spec("marker") is None:
                pytest.skip("marker is not installed (heavy OCR/GPU dependency)")
        elif shutil.which(req) is None:
            pytest.skip(f"{req!r} is not in PATH")


# ---------------------------------------------------------------------------
# Shared contract checks
# ---------------------------------------------------------------------------


def _assert_contract(
    exit_code: int,
    output_md: Path | None,
    header: ResultHeader | None,
    body: str | None,
    *,
    context: str = "",
) -> None:
    """Deterministic LLM round-trip contract: exit 0, output written, clean body.

    No line of the body may be a bare defect type name leaked from a model reply.
    """
    ctx = f" for {context}" if context else ""
    assert exit_code == int(ExitCode.SUCCESS), f"expected exit 0, got {exit_code}{ctx}"
    assert output_md is not None, "no output file was written"
    assert output_md.exists(), "no output file was written"
    assert header is not None
    assert header.status in TERMINAL_STATUSES, (
        f"header status {header.status!r} is not terminal"
    )
    assert body is not None, "output body is empty"
    assert body.strip(), "output body is empty"
    leaked = [
        line
        for line, protected in segments(body)
        if not protected and line.strip() in DEFECT_TYPES
    ]
    assert leaked == [], f"defect type name(s) in final body: {leaked}"


def _assert_llm_result(result: RoundtripResult) -> None:
    """Assert the shared contract for a ``RoundtripResult`` from run_roundtrip."""
    _assert_contract(
        result.exit_code,
        result.output_md,
        result.header,
        result.output_body,
        context=f"{result.fmt}/{result.fixture.name}",
    )


# The body must neither collapse nor balloon against its source.
_BODY_MIN_FRACTION = 4  # delivered body >= reference_len // _BODY_MIN_FRACTION
_BODY_MAX_FACTOR = 3  # delivered body <= reference_len * _BODY_MAX_FACTOR


def _assert_body_band(body: str, reference_len: int, *, label: str) -> None:
    """Assert the delivered body length sits within the shared band of reference_len."""
    out_len = len(body)
    floor = reference_len // _BODY_MIN_FRACTION
    ceiling = reference_len * _BODY_MAX_FACTOR
    assert out_len >= floor, (
        f"body too short after {label}: {out_len} chars, expected >= {floor}"
    )
    assert out_len <= ceiling, (
        f"body too long after {label}: {out_len} chars, expected <= {ceiling}"
    )


def _real_config(
    input_path: Path,
    output_dir: Path,
    *,
    llm_ocr: str | None = None,
    llm_inspection: str | None = None,
    llm_post: str | None = None,
) -> RunConfig:
    """A RunConfig with the fixed defaults of the real-LLM layer, varying roles."""
    return RunConfig(
        input_path=input_path,
        output_dir=output_dir,
        skip_existing=False,
        yaml_header=True,
        extract_images=True,
        llm_ocr=llm_ocr,
        llm_inspection=llm_inspection,
        llm_post=llm_post,
        llm_latex_fix=False,
        cuda=False,
        log_file=False,
        debug=False,
    )


# ---------------------------------------------------------------------------
# Infrastructure smoke test
# ---------------------------------------------------------------------------


def test_smoke_post_claude_cli(raw2md_home_real: Path) -> None:
    """DOCX round-trip with --llm-post=claude_cli completes without crash.

    Checks the wiring only: a body with no damaged zone sends no request.
    """
    _skip_without("pandoc", "claude")
    result = run_roundtrip(
        CORPUS_DIR / "mixed.md",
        "docx",
        raw2md_home_real / "work",
        llm_post="claude_cli",
    )
    _assert_llm_result(result)


# ---------------------------------------------------------------------------
# Post operation (Claude CLI + Gemini)
# ---------------------------------------------------------------------------

# A row wider than its delimiter row makes post open a table zone.
_POST_INPUT = """\
# Post-operation test

Paragraph before the damaged zone - must survive post unchanged.

| Name | Value |
|---|---|
| alpha | 1 |
| beta | 2 | 3 |
| gamma | 4 |

Paragraph after the damaged zone - must also survive post unchanged.
"""

_POST_BEFORE = "Paragraph before the damaged zone - must survive post unchanged."
_POST_AFTER = "Paragraph after the damaged zone - must also survive post unchanged."


def _run_post_roundtrip(
    content: str, llm_post: str, home: Path
) -> tuple[int, Path | None, ResultHeader | None, str | None]:
    """Convert crafted markdown with a real --llm-post provider.

    Returns ``(exit_code, output_md, header, body)``; the last three are None
    without a result file.
    """
    input_md = home / "work" / "input" / "post_input.md"
    input_md.parent.mkdir(parents=True, exist_ok=True)
    input_md.write_text(content, encoding="utf-8")
    out_dir = home / "work" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    config = _real_config(input_md, out_dir, llm_post=llm_post)
    exit_code = _run_orchestrator(config)
    target = resolve_output_target(input_md, output_dir=out_dir)
    if not target.md_path.exists():
        return exit_code, None, None, None
    text = target.md_path.read_text(encoding="utf-8")
    header, body = strip_own_header(text)
    return exit_code, target.md_path, header, body


def _assert_post_result(
    exit_code: int,
    output_md: Path | None,
    header: ResultHeader | None,
    body: str | None,
    *,
    reference_len: int,
) -> None:
    """Contract for a post-operation run: all shared checks plus a body-length band."""
    _assert_contract(exit_code, output_md, header, body)
    assert body is not None  # narrowed: _assert_contract would have raised
    _assert_body_band(body, reference_len, label="post")


@pytest.mark.parametrize(
    ("llm_post", "requirements"),
    [
        pytest.param("claude_cli", ("claude",), id="claude_cli"),
        pytest.param("gemini_api", ("GOOGLE_API_KEY",), id="gemini_api"),
    ],
)
def test_post_damaged_zone(
    raw2md_home_real: Path,
    llm_post: str,
    requirements: tuple[str, ...],
) -> None:
    """Post operation end-to-end on a zone the markup shows damaged.

    The paragraphs around the zone must come back unchanged.
    """
    _skip_without(*requirements)
    exit_code, out_md, header, body = _run_post_roundtrip(
        _POST_INPUT, llm_post, raw2md_home_real
    )
    _assert_post_result(exit_code, out_md, header, body, reference_len=len(_POST_INPUT))
    assert body is not None
    assert _POST_BEFORE in body, "content before the damaged zone was modified by post"
    assert _POST_AFTER in body, "content after the damaged zone was modified by post"


# ---------------------------------------------------------------------------
# Inspection + combination
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("llm_post", "requirements"),
    [
        pytest.param(
            "gemini_api",
            ("GOOGLE_API_KEY",),
            id="gemini_post",
        ),
        pytest.param(
            "claude_cli",
            ("GOOGLE_API_KEY", "claude"),
            id="claude_post",
        ),
    ],
)
def test_inspection_and_post(
    raw2md_home_real: Path,
    llm_post: str,
    requirements: tuple[str, ...],
) -> None:
    """PDF round-trip with --llm-inspection=gemini_api and a real --llm-post provider.

    The ``claude_post`` variant runs the two stages on different providers.
    """
    _skip_without("marker", "pandoc", "xelatex", *requirements)
    result = run_roundtrip(
        CORPUS_DIR / "mixed.md",
        "pdf",
        raw2md_home_real / "work",
        llm_inspection="gemini_api",
        llm_post=llm_post,
    )
    _assert_llm_result(result)


def test_inspection_without_post(raw2md_home_real: Path) -> None:
    """PDF round-trip with --llm-inspection alone; the header records `post: none`."""
    _skip_without("marker", "pandoc", "xelatex", "GOOGLE_API_KEY")
    result = run_roundtrip(
        CORPUS_DIR / "mixed.md",
        "pdf",
        raw2md_home_real / "work",
        llm_inspection="gemini_api",
    )
    _assert_llm_result(result)
    assert result.header is not None
    assert result.header.post == "none", (
        f"post should not have run: post={result.header.post!r}"
    )


# ---------------------------------------------------------------------------
# OCR (Gemini vision)
# ---------------------------------------------------------------------------


def test_ocr_non_vision_model_refused(raw2md_home_real: Path) -> None:
    """A CLI (text-only) model in the ocr role is refused at startup with exit 3.

    The gate fires before any page renders, so no live call is made.
    """
    work = raw2md_home_real / "work"
    work.mkdir(parents=True, exist_ok=True)
    dummy = work / "ocr_gate.pdf"
    dummy.write_bytes(b"%PDF-1.4 stub")
    config = _real_config(dummy, work / "out", llm_ocr="claude_cli")
    assert _run_orchestrator(config) == int(ExitCode.MISSING_DEPENDENCY)


def test_ocr_replaces_page(raw2md_home_real: Path) -> None:
    """OCR round-trip: Gemini vision recognizes a degraded scan, replacing marker.

    ``engine`` must record the gemini model, which proves recognition replaced
    the engine rather than being skipped.
    """
    _skip_without("pandoc", "xelatex", "img2pdf", "GOOGLE_API_KEY")
    result = run_roundtrip(
        CORPUS_DIR / "mixed.md",
        "scan_degraded",
        raw2md_home_real / "work",
        llm_ocr="gemini_api",
    )
    _assert_llm_result(result)
    assert result.header is not None
    assert result.header.engine == "gemini_api", (
        f"OCR did not run: engine={result.header.engine!r}"
    )
    assert result.output_body is not None  # narrowed: _assert_llm_result would raise
    _assert_body_band(result.output_body, len(result.reference_body), label="ocr")
