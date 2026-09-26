"""Tests for the per-file pipeline: stages, routes, media links, isolation."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TextIO

import pymupdf
import pytest

from conftest import make_run_config
from raw2md.cleaner import CleanOptions, CleanResult, clean_with_report
from raw2md.config import RunConfig
from raw2md.engines import (
    ConversionError,
    ConversionResult,
    ConvertOptions,
    Engine,
    EngineRegistry,
)
from raw2md.header import ConversionMethod, ResultHeader, ResultStatus, from_yaml_block
from raw2md.llm.base import (
    AuthError,
    Availability,
    DocumentTooLargeError,
    MediaPart,
    Part,
    Provider,
    RateLimitError,
)
from raw2md.llm.chunking import DEFAULT_PAGES_PER_REQUEST
from raw2md.llm.inspection.common import InspectOperation
from raw2md.llm.ocr import OcrOperation
from raw2md.llm.post.common import PostOperation
from raw2md.mdtext.pages import lost_page_marker, page_mark
from raw2md.output import encode_link_path, resolve_output_target
from raw2md.pipeline import (
    FileResult,
    Outcome,
    RunContext,
    process_file,
)
from raw2md.quality.evaluator import CheckId
from raw2md.queue import QueueItem, readiness_hash, write_in_progress_stub
from raw2md.settings import ModelConfig

OK_BODY = "\n".join(["# Heading", "", "This is plain text for the check.", ""])


class StubEngine(Engine):
    """In-memory engine returning a fixed body, or raising on demand."""

    def __init__(
        self,
        *,
        extensions: frozenset[str],
        method: ConversionMethod = ConversionMethod.MARKER,
        body: str = OK_BODY,
        media: tuple[str, ...] = (),
        source_pages: int | None = None,
        available: bool = True,
        fail: bool = False,
        error: BaseException | None = None,
        assembled_pdf: bytes | None = None,
    ) -> None:
        self._extensions = extensions
        self._method = method
        self._body = body
        self._media = media
        self._source_pages = source_pages
        self._available = available
        self._fail = fail
        # `BaseException` lets a test raise KeyboardInterrupt past the guard.
        self._error = error
        # The djvu chain converts a pdf it assembled; these bytes stand in.
        self._assembled_pdf = assembled_pdf
        self.last_options: ConvertOptions | None = None
        self.last_source_pdf: Path | None = None

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
        self.last_options = options
        if self._error is not None:
            raise self._error
        if self._fail:
            raise ConversionError(f"stub failure: {source.name}")
        if self._media:
            media_dir.mkdir(parents=True, exist_ok=True)
            for name in self._media:
                (media_dir / name).parent.mkdir(parents=True, exist_ok=True)
                (media_dir / name).write_bytes(b"img")
        if self._assembled_pdf is not None and options.scratch_dir is not None:
            self.last_source_pdf = options.scratch_dir / "assembled.pdf"
            self.last_source_pdf.write_bytes(self._assembled_pdf)
        return ConversionResult(
            body=self._body,
            media=self._media,
            source_pages=self._source_pages,
            source_pdf=self.last_source_pdf,
        )


def make_context(registry: EngineRegistry, config: RunConfig) -> RunContext:
    # A StringIO progress stream keeps tqdm output out of the test report.
    return RunContext(
        config=config,
        registry=registry,
        log_stream=None,
        progress_stream=io.StringIO(),
    )


def run_one(source: Path, registry: EngineRegistry, **overrides: object) -> FileResult:
    config = make_run_config(source, **overrides)
    item = QueueItem(source=source, include_extension=False)
    return process_file(item, make_context(registry, config))


def read_header(md_path: Path) -> ResultHeader | None:
    return from_yaml_block(md_path.read_text(encoding="utf-8"))


def test_engine_route_writes_ok_result(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    result = run_one(src, registry)

    assert result.outcome is Outcome.OK
    assert result.status is ResultStatus.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.status is ResultStatus.OK
    assert header.engine == "marker"
    assert header.source == "a.pdf"


def test_a_body_cleaning_empties_out_is_still_written(tmp_path: Path) -> None:
    # The trim leaves nothing, and the report addresses a line that is gone;
    # the file is still written.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    loop = r"$$[\gamma_{xz}, \gamma_{yz}" + r", \gamma_{xz}" * 8 + "$$\n"
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=loop)])

    result = run_one(src, registry)

    assert result.outcome is Outcome.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert CheckId.LOST_FORMULAS.value in header.issues


def test_real_signatures_reach_their_engine(tmp_path: Path) -> None:
    pdf_engine = StubEngine(extensions=frozenset({"pdf"}))
    docx_engine = StubEngine(
        extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC
    )
    djvu_engine = StubEngine(
        extensions=frozenset({"djvu"}), method=ConversionMethod.DJVU_MARKER
    )
    pdf_src = tmp_path / "a.pdf"
    pdf_src.write_bytes(b"%PDF-1.4 real enough")
    docx_src = tmp_path / "b.docx"
    docx_src.write_bytes(b"PK\x03\x04 real enough")
    djvu_src = tmp_path / "c.djvu"
    djvu_src.write_bytes(b"AT&TFORM real enough")

    run_one(pdf_src, EngineRegistry([pdf_engine]))
    run_one(docx_src, EngineRegistry([docx_engine]))
    run_one(djvu_src, EngineRegistry([djvu_engine]))

    assert pdf_engine.last_options is not None
    assert docx_engine.last_options is not None
    assert djvu_engine.last_options is not None


def test_docx_with_rtf_content_stops_before_pandoc(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="raw2md")
    src = tmp_path / "memo.docx"
    src.write_bytes(rb"{\rtf1\ansi\deff0 An RTF body saved under a .docx name}")
    engine = StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC)

    result = run_one(src, EngineRegistry([engine]))

    assert result.outcome is Outcome.NO_RESULT
    assert engine.last_options is None  # never reached pandoc
    assert not (tmp_path / "memo.md").exists()
    assert "RTF" in caplog.text


def test_docx_with_ole2_content_stops_before_pandoc(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="raw2md")
    src = tmp_path / "old.docx"
    src.write_bytes(
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"an old .doc saved under a .docx name"
    )
    engine = StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC)

    result = run_one(src, EngineRegistry([engine]))

    assert result.outcome is Outcome.NO_RESULT
    assert engine.last_options is None
    assert not (tmp_path / "old.md").exists()
    assert "OLE2" in caplog.text


def test_pdf_without_pdf_header_stops_before_marker(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"this file is plainly not a pdf at all")
    engine = StubEngine(extensions=frozenset({"pdf"}))

    result = run_one(src, EngineRegistry([engine]))

    assert result.outcome is Outcome.NO_RESULT
    assert engine.last_options is None  # never reached marker
    assert not (tmp_path / "a.md").exists()
    assert "%PDF-" in caplog.text


def test_engine_route_marks_bad_on_defect(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body="x")])

    result = run_one(src, registry)

    assert result.outcome is Outcome.OK
    assert result.status is ResultStatus.BAD


def test_bad_result_records_issues_in_header(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body="x")])

    run_one(src, registry)

    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.issues == ("empty_body",)


def test_ok_result_header_has_no_issues(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    run_one(src, registry)

    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.issues == ()


def test_ok_result_records_an_issue_below_the_threshold(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    # One unbalanced span is recorded but not graded, so the result stays ok.
    body = OK_BODY + "A broken formula $a + {b$ in an otherwise readable line.\n"
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])

    result = run_one(src, registry)

    assert result.status is ResultStatus.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.issues == ("formulas",)
    assert "quality ok for a.pdf, below threshold: formulas" in caplog.text


def test_bad_result_warns_with_check_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body="x")])

    run_one(src, registry)

    assert "quality bad for a.pdf" in caplog.text
    assert "empty_body" in caplog.text


def test_bad_result_recommends_llm_ocr_on_recognition_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body="x")])

    run_one(src, registry)

    assert "consider --engine" in caplog.text
    # `<model>` comes from settings; the CLI does not take it literally.
    assert "<model>" not in caplog.text


def test_quality_log_names_the_measured_detail(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body="x")])

    run_one(src, registry)

    # The header keeps the bare check id; the measured value goes to the log.
    assert "empty_body (1 alphanumeric chars)" in caplog.text


def test_bad_result_recommends_llm_post_when_repairable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    _write_text_pdf(src, ["Body text of the source document."])
    # A missing image file is repairable; re-recognition would not help.
    body = OK_BODY + "\n![Figure 1](no-such-file.png)\n"
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])

    run_one(src, registry)

    assert "consider --llm-post" in caplog.text
    assert "consider --engine" not in caplog.text


def test_ok_result_logs_no_quality_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    # A readable pdf: a source the witness cannot open would log a warning.
    _write_text_pdf(src, ["Body text of the source document."])
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    run_one(src, registry)

    assert caplog.records == []


def test_conversion_failure_leaves_no_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), fail=True)])

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert result.status is None
    assert not (tmp_path / "a.md").exists()
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_unavailable_engine_skips_without_stub(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), available=False)]
    )

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert not (tmp_path / "a.md").exists()
    # An unsupported format still produced nothing, so it is an ERROR.
    assert [r.levelname for r in caplog.records] == ["ERROR"]


def test_unexpected_error_is_isolated_as_no_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # An OSError the route does not catch becomes a no-result, and the stub
    # goes.
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), error=OSError("disk error"))]
    )

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert result.status is None
    assert not (tmp_path / "a.md").exists()
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert error_records
    # exc_info lets the file handler render the traceback.
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[0] is OSError


def test_stub_write_failure_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("cannot write stub")

    monkeypatch.setattr("raw2md.pipeline.write_in_progress_stub", boom)

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert not (tmp_path / "a.md").exists()


def test_final_write_failure_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guard discards the stub already written.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("cannot write result")

    monkeypatch.setattr("raw2md.pipeline.write_md", boom)

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert not (tmp_path / "a.md").exists()


def test_unexpected_error_before_stub_keeps_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guard discards only its own stub, never a result it did not write.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    existing = tmp_path / "a.md"
    existing.write_text("valuable existing result\n", encoding="utf-8")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    def boom(_source: Path) -> str:
        raise RuntimeError("unexpected hash failure")

    # readiness_hash runs before the collision check and the stub write.
    monkeypatch.setattr("raw2md.pipeline.readiness_hash", boom)

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert existing.read_text(encoding="utf-8") == "valuable existing result\n"


def test_unexpected_error_with_non_utf8_target_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guard's stub check must not raise on a non-UTF-8 file there.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    existing = tmp_path / "a.md"
    existing.write_bytes(b"\xff\xfe not utf-8 \x00")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    def boom(_source: Path) -> str:
        raise RuntimeError("unexpected hash failure")

    monkeypatch.setattr("raw2md.pipeline.readiness_hash", boom)

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert existing.read_bytes() == b"\xff\xfe not utf-8 \x00"


def test_discard_result_swallows_unlink_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Cleanup runs on a failing path, so an unlink error is logged, not raised.
    from raw2md.pipeline import _discard_result

    stub = tmp_path / "a.md"
    stub.write_text("---\nraw2md_version: 1\n---\n", encoding="utf-8")
    target = resolve_output_target(tmp_path / "a.pdf", output_dir=None)

    def raising_unlink(self: Path, missing_ok: bool = False) -> None:
        raise OSError("directory is read-only")

    monkeypatch.setattr(Path, "unlink", raising_unlink)

    _discard_result(target)  # must not raise


def test_keyboard_interrupt_is_not_swallowed(tmp_path: Path) -> None:
    # Ctrl+C must stop the whole run, not count as a file failure.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), error=KeyboardInterrupt())]
    )

    with pytest.raises(KeyboardInterrupt):
        run_one(src, registry)


def test_vanished_source_is_skipped(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "gone.pdf"
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    result = run_one(src, registry)

    assert result.outcome is Outcome.SKIPPED
    assert result.status is None
    assert not (tmp_path / "gone.md").exists()
    assert [r.levelname for r in caplog.records] == ["WARNING"]


def test_foreign_md_at_the_result_name_is_no_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    (tmp_path / "a.md").write_text("existing\n", encoding="utf-8")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "existing\n"
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_own_result_is_replaced_without_a_flag(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=OK_BODY)])

    assert run_one(src, registry).outcome is Outcome.OK
    (tmp_path / "a").mkdir(exist_ok=True)
    (tmp_path / "a" / "stale.png").write_bytes(b"x")

    result = run_one(src, registry)

    assert result.outcome is Outcome.OK
    assert (tmp_path / "a.md").exists()
    # The media folder goes with the result it belonged to.
    assert not (tmp_path / "a" / "stale.png").exists()


def test_source_gone_bad_keeps_the_previous_result(tmp_path: Path) -> None:
    # Replacement is decided before conversion, so a rerun over a source gone
    # bad keeps the earlier result.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=OK_BODY)])
    assert run_one(src, registry).outcome is Outcome.OK
    before = (tmp_path / "a.md").read_text(encoding="utf-8")

    src.write_bytes(b"{\\rtf1 saved under the wrong extension}")
    result = run_one(src, registry)

    assert result.outcome is Outcome.NO_RESULT
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == before


def test_own_in_progress_stub_is_replaced(tmp_path: Path) -> None:
    # A crash leaves the tool's own stub, so a later run takes the name back.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    target = resolve_output_target(src)
    write_in_progress_stub(
        target,
        source_name=src.name,
        source_hash=readiness_hash(src),
    )
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=OK_BODY)])

    result = run_one(src, registry)

    assert result.outcome is Outcome.OK
    header = from_yaml_block(target.md_path.read_text(encoding="utf-8"))
    assert header is not None
    assert header.status is ResultStatus.OK


def test_md_route_recleans_with_clean_engine(tmp_path: Path) -> None:
    src = tmp_path / "note.md"
    src.write_text(
        "\n".join(["# Note", "", "", "", "Extra blank lines are removed.", ""]),
        encoding="utf-8",
    )
    registry = EngineRegistry([])  # md has no engine

    result = run_one(src, registry)

    assert result.outcome is Outcome.OK
    out = tmp_path / "note_cleaned.md"
    header = read_header(out)
    assert header is not None
    assert header.engine == "clean"
    assert header.source == "note.md"


def test_md_route_recomputes_issues_not_carried_over(tmp_path: Path) -> None:
    # Issues come from the fresh evaluation, not from the stale header.
    from raw2md.header import build_stub, render_result

    stale = build_stub("note.md", engine="clean", source_hash="stale-hash")
    stale.status = ResultStatus.BAD
    stale.issues = ("tables",)
    src = tmp_path / "note.md"
    src.write_text(render_result(stale, OK_BODY), encoding="utf-8")
    registry = EngineRegistry([])  # md has no engine

    result = run_one(src, registry)

    assert result.status is ResultStatus.OK
    header = read_header(tmp_path / "note_cleaned.md")
    assert header is not None
    assert header.issues == ()


def test_llm_flags_recorded_as_none_in_base_run(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    # Only operations resolved into the context count, and none are wired in.
    run_one(src, registry, llm_ocr="gemini_api", llm_post="claude_cli")
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "none"
    assert header.post == "none"
    assert "llm_ocr" not in (tmp_path / "a.md").read_text(encoding="utf-8")


def test_md_route_redirects_relative_links_for_output_dir(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "img.png").write_bytes(b"img")
    src = src_dir / "note.md"
    src.write_text(
        "\n".join(["![x](img.png)", "", "Text of sufficient length for scoring.", ""]),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_one(src, EngineRegistry([]), output_dir=out)
    result = (out / "note.md").read_text(encoding="utf-8")
    assert "](../src/img.png)" in result


def test_md_route_links_across_drives_by_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "img.png").write_bytes(b"img")
    src = src_dir / "note.md"
    src.write_text(
        "\n".join(["![x](img.png)", "", "Text of sufficient length for scoring.", ""]),
        encoding="utf-8",
    )

    # What Windows raises when the output folder sits on another drive.
    def no_relative_path(path: str, start: str) -> str:
        raise ValueError(f"path is on mount 'D:', start on mount 'C:': {path} {start}")

    monkeypatch.setattr("raw2md.pipeline.os.path.relpath", no_relative_path)
    out = tmp_path / "out"
    run_one(src, EngineRegistry([]), output_dir=out)

    result = (out / "note.md").read_text(encoding="utf-8")
    absolute = encode_link_path((src_dir / "img.png").absolute().as_posix())
    assert f"]({absolute})" in result


def test_md_route_redirects_html_image_links_for_output_dir(tmp_path: Path) -> None:
    # The pandoc route writes sized images as HTML tags; they are re-pointed
    # too.
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "img.png").write_bytes(b"img")
    src = src_dir / "note.md"
    src.write_text(
        "\n".join(
            [
                '<img src="img.png" style="width:3.9in;height:1.8in" alt="" />',
                "",
                "Text of sufficient length for scoring.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_one(src, EngineRegistry([]), output_dir=out)
    result = (out / "note.md").read_text(encoding="utf-8")
    assert 'src="../src/img.png"' in result
    assert 'style="width:3.9in;height:1.8in"' in result


def test_md_route_percent_encodes_redirected_link_with_space(tmp_path: Path) -> None:
    src_dir = tmp_path / "My Source"
    src_dir.mkdir()
    (src_dir / "img.png").write_bytes(b"img")
    src = src_dir / "note.md"
    src.write_text(
        "\n".join(["![x](img.png)", "", "Text of sufficient length for scoring.", ""]),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_one(src, EngineRegistry([]), output_dir=out)
    # The path crosses "My Source", so the space is percent-encoded.
    result = (out / "note.md").read_text(encoding="utf-8")
    assert "](../My%20Source/img.png)" in result


def test_md_route_redirect_does_not_double_encode_across_reruns(
    tmp_path: Path,
) -> None:
    src_dir = tmp_path / "My Source"
    src_dir.mkdir()
    (src_dir / "img.png").write_bytes(b"img")
    src = src_dir / "note.md"
    src.write_text(
        "\n".join(["![x](img.png)", "", "Text of sufficient length for scoring.", ""]),
        encoding="utf-8",
    )
    out1 = tmp_path / "out1"
    run_one(src, EngineRegistry([]), output_dir=out1)
    intermediate = out1 / "note.md"
    assert "](../My%20Source/img.png)" in intermediate.read_text(encoding="utf-8")

    out2 = tmp_path / "out2"
    run_one(intermediate, EngineRegistry([]), output_dir=out2)
    result = (out2 / "note.md").read_text(encoding="utf-8")
    assert "](../My%20Source/img.png)" in result
    assert "%25" not in result


def test_md_route_leaves_encoded_absolute_link_untouched(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "note.md"
    src.write_text(
        "\n".join(
            ["![x](%2Ftmp%2Fa.png)", "", "Text of sufficient length for scoring.", ""]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_one(src, EngineRegistry([]), output_dir=out)
    # Decoded, this is an absolute POSIX path; it is left alone.
    result = (out / "note.md").read_text(encoding="utf-8")
    assert "![x](%2Ftmp%2Fa.png)" in result


def test_md_route_leaves_encoded_drive_letter_link_untouched(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src = src_dir / "note.md"
    src.write_text(
        "\n".join(
            [
                "![x](C%3A%5Ctmp%5Ca.png)",
                "",
                "Text of sufficient length for scoring.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_one(src, EngineRegistry([]), output_dir=out)
    # Decoded, this is a Windows drive-absolute path; it must be left alone.
    result = (out / "note.md").read_text(encoding="utf-8")
    assert "![x](C%3A%5Ctmp%5Ca.png)" in result


def test_no_yaml_drops_header(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    run_one(src, registry, yaml_header=False)

    assert read_header(tmp_path / "a.md") is None


def test_density_failure_via_source_pages(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    # Many pages over a short body fall under the density floor.
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), source_pages=50)]
    )

    result = run_one(src, registry)

    assert result.status is ResultStatus.BAD


def test_density_failure_via_djvu_source_pages(tmp_path: Path) -> None:
    src = tmp_path / "a.djvu"
    src.write_bytes(b"AT&TFORM stub")
    # The engine counts the pages of the pdf it assembled.
    registry = EngineRegistry(
        [
            StubEngine(
                extensions=frozenset({"djvu"}),
                method=ConversionMethod.DJVU_MARKER,
                source_pages=50,
            )
        ]
    )

    result = run_one(src, registry)

    assert result.status is ResultStatus.BAD


# --- source text witness ------------------------------------------------------


def _capture_clean_options(
    monkeypatch: pytest.MonkeyPatch,
) -> list[CleanOptions | None]:
    """Record the options each cleaning call receives, cleaning as usual."""
    seen: list[CleanOptions | None] = []

    def spy(text: str, options: CleanOptions | None = None) -> CleanResult:
        seen.append(options)
        return clean_with_report(text, options)

    monkeypatch.setattr("raw2md.pipeline.clean_with_report", spy)
    return seen


def _write_text_pdf(path: Path, pages: Sequence[str]) -> None:
    doc = pymupdf.open()
    try:
        for text in pages:
            doc.new_page().insert_text((72, 72), text)
        doc.save(str(path))
    finally:
        doc.close()


def test_engine_route_hands_the_source_text_to_cleaning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "a.pdf"
    _write_text_pdf(src, ["Rated pressure of the pump."])
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    seen = _capture_clean_options(monkeypatch)

    run_one(src, registry)

    options = seen[0]
    assert options is not None
    assert options.source_text.has_layer is True
    assert options.source_text.has_token("pressure") is True


def test_engine_route_witness_is_empty_without_a_text_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An unreadable pdf leaves the rules with no witness, as a scan does.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    seen = _capture_clean_options(monkeypatch)

    result = run_one(src, registry)

    assert result.status is ResultStatus.OK
    options = seen[0]
    assert options is not None
    assert options.source_text.has_layer is False


def test_md_route_has_no_witness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "notes.md"
    src.write_text(OK_BODY, encoding="utf-8")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    seen = _capture_clean_options(monkeypatch)

    result = run_one(src, registry, output_dir=tmp_path / "out")

    assert result.status is ResultStatus.OK
    options = seen[0]
    assert options is not None
    assert options.source_text.has_layer is False


# --- source outline witness ---------------------------------------------------


def _write_outlined_pdf(path: Path, toc: Sequence[Sequence[object]]) -> None:
    doc = pymupdf.open()
    try:
        doc.new_page().insert_text((72, 72), "Body text of the only page.")
        doc.set_toc([list(entry) for entry in toc])
        doc.save(str(path))
    finally:
        doc.close()


def test_engine_route_takes_heading_levels_from_the_source_outline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "a.pdf"
    # A pdf outline opens at the first level, so the heading sits under a
    # chapter entry.
    _write_outlined_pdf(src, [[1, "Section", 1], [2, "Heading", 1]])
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    seen = _capture_clean_options(monkeypatch)

    result = run_one(src, registry)

    assert result.status is ResultStatus.OK
    options = seen[0]
    assert options is not None
    assert options.outline.level_for("Heading") == 2
    assert "## Heading" in (tmp_path / "a.md").read_text(encoding="utf-8")


def test_engine_route_outline_is_empty_without_bookmarks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "a.pdf"
    _write_text_pdf(src, ["Body text of the only page."])
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    seen = _capture_clean_options(monkeypatch)

    result = run_one(src, registry)

    assert result.status is ResultStatus.OK
    options = seen[0]
    assert options is not None
    assert options.outline.has_outline is False
    assert "# Heading" in (tmp_path / "a.md").read_text(encoding="utf-8")


def test_md_route_has_no_outline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "notes.md"
    src.write_text(OK_BODY, encoding="utf-8")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    seen = _capture_clean_options(monkeypatch)

    result = run_one(src, registry, output_dir=tmp_path / "out")

    assert result.status is ResultStatus.OK
    options = seen[0]
    assert options is not None
    assert options.outline.has_outline is False


# --- stage bar routing ---------------------------------------------------------


def _route_stage_names(source: Path, ctx: RunContext) -> tuple[str, ...]:
    from raw2md.pipeline import _route_stage_names as route_stage_names

    return route_stage_names(source, ctx)


def test_route_stages_base_run_is_three(tmp_path: Path) -> None:
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    ctx = make_context(registry, make_run_config(tmp_path / "a.pdf"))
    stages = _route_stage_names(tmp_path / "a.pdf", ctx)
    assert stages == ("conversion", "cleaning", "quality evaluation")


def test_route_stages_both_llm_steps_on_pdf_is_five(tmp_path: Path) -> None:
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    config = make_run_config(tmp_path / "a.pdf", llm_inspection="insp", llm_post="post")
    ctx = RunContext(
        config=config,
        registry=registry,
        inspection=InspectOperation(
            provider=FakeProvider([]), prompt="I", model_key="insp"
        ),
        post=PostOperation(provider=FakeProvider([]), prompt="P", model_key="post"),
    )
    stages = _route_stage_names(tmp_path / "a.pdf", ctx)
    assert stages == (
        "conversion",
        "cleaning",
        "quality evaluation",
        "inspection",
        "post-processing",
    )


def test_route_stages_inspection_excluded_for_docx(tmp_path: Path) -> None:
    # A docx has no scan for inspection; counting the stage would stall the
    # bar short of 100%.
    registry = EngineRegistry([StubEngine(extensions=frozenset({"docx"}))])
    config = make_run_config(tmp_path / "a.docx", llm_inspection="insp")
    ctx = RunContext(
        config=config,
        registry=registry,
        inspection=InspectOperation(
            provider=FakeProvider([]), prompt="I", model_key="insp"
        ),
    )
    stages = _route_stage_names(tmp_path / "a.docx", ctx)
    assert stages == ("conversion", "cleaning", "quality evaluation")


def test_route_stages_post_processing_applies_to_any_source(tmp_path: Path) -> None:
    # Post has no format restriction.
    registry = EngineRegistry([StubEngine(extensions=frozenset({"docx"}))])
    config = make_run_config(tmp_path / "a.docx", llm_post="post")
    ctx = RunContext(
        config=config,
        registry=registry,
        post=PostOperation(provider=FakeProvider([]), prompt="P", model_key="post"),
    )
    stages = _route_stage_names(tmp_path / "a.docx", ctx)
    assert stages == ("conversion", "cleaning", "quality evaluation", "post-processing")


# --- LLM post-processing integration -----------------------------------------

_FAKE_MODEL = ModelConfig(
    access="cli",
    model="fake",
    key_env=None,
    command="fake",
    rpm=None,
    tpm=None,
    rpd=None,
)


class FakeProvider(Provider):
    """Provider returning one queued reply per call; an Exception reply is raised."""

    def __init__(self, replies: Sequence[str | Exception]) -> None:
        super().__init__(_FAKE_MODEL)
        self._replies = list(replies)
        self.calls = 0
        self.parts: list[tuple[Part, ...]] = []

    def available(self) -> Availability:
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        self.calls += 1
        self.parts.append(tuple(parts))
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


# A table row off the width its separator declares; post reads it off the
# markup itself.
POST_BODY = "\n".join(
    [
        "# Heading",
        "",
        "The first part of the text stands before the table and reads as a paragraph.",
        "",
        "| A | B |",
        "| --- | --- |",
        "| x |",
        "",
    ]
)
ROW_FIX = '{"rows": [{"row": 3, "text": "| x |  |"}]}'

# Two damaged tables, so a refusal on the second keeps the first repair.
POST_TWO_ZONE_BODY = "\n".join(
    [
        "# Heading",
        "",
        "The first part of the text stands before the table and reads as a paragraph.",
        "",
        "| A | B |",
        "| --- | --- |",
        "| x |",
        "",
        "The second part of the text stands between the tables and reads as one too.",
        "",
        "| C | D |",
        "| --- | --- |",
        "| y |",
        "",
    ]
)


def run_with_post(
    source: Path,
    registry: EngineRegistry,
    provider: Provider,
    *,
    progress_stream: TextIO | None = None,
    **overrides: object,
) -> FileResult:
    config = make_run_config(source, llm_post="fake", **overrides)
    op = PostOperation(provider=provider, prompt="FIX", model_key="fake")
    ctx = RunContext(
        config=config,
        registry=registry,
        log_stream=None,
        progress_stream=progress_stream
        if progress_stream is not None
        else io.StringIO(),
        post=op,
    )
    item = QueueItem(source=source, include_extension=False)
    return process_file(item, ctx)


def test_post_repairs_a_broken_zone(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=POST_BODY)]
    )
    provider = FakeProvider([ROW_FIX])

    result = run_with_post(src, registry, provider)

    assert result.outcome is Outcome.OK
    assert result.status is ResultStatus.OK  # the row is back on its width
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.post == "fake"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "| x |  |" in text


def test_post_too_large_keeps_base_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=POST_BODY)]
    )
    provider = FakeProvider([DocumentTooLargeError("over the limit")])

    result = run_with_post(src, registry, provider)

    # An oversize request is a permanent skip: the result is kept, the step
    # failed.
    assert result.outcome is Outcome.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.post == "failed"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "| x |\n" in text  # not repaired
    assert "clean:flag" not in text  # cleaning writes no markup into the body
    assert caplog.records
    assert all(r.levelname == "WARNING" for r in caplog.records)


def test_post_provider_error_is_llm_error_with_base_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=POST_BODY)]
    )
    provider = FakeProvider([RateLimitError("429 exhausted")])

    result = run_with_post(src, registry, provider)

    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.post == "failed"
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_post_refused_access_sends_one_zone_and_fails(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=POST_TWO_ZONE_BODY)]
    )
    provider = FakeProvider([AuthError("bad key")])

    result = run_with_post(src, registry, provider)

    assert provider.calls == 1
    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.post == "failed"


def test_post_partial_keeps_the_repair_it_made_before_the_refusal(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=POST_TWO_ZONE_BODY)]
    )
    provider = FakeProvider([ROW_FIX, RateLimitError("429 exhausted")])

    result = run_with_post(src, registry, provider)

    # The zone answered before the refusal is kept; the refusal decides the
    # exit code.
    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.post == "partial (1/2)"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "| x |  |" in text  # the repair that landed
    assert "| y |\n" in text  # the zone the refusal cost
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_post_requested_without_anchors_records_model(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    provider = FakeProvider([])

    result = run_with_post(src, registry, provider)

    assert result.outcome is Outcome.OK
    # The stage ran without a call, so the field names the model.
    assert provider.calls == 0
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.post == "fake"


def test_post_requested_without_anchors_advances_progress_bar(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])
    provider = FakeProvider([])
    stream = io.StringIO()

    result = run_with_post(src, registry, provider, progress_stream=stream)

    assert result.outcome is Outcome.OK
    # An idle post run must still look different from a run without post.
    assert "post-processing" in stream.getvalue()


# --- inspection integration ------------------------------------------------

INSPECT_BODY = "\n".join(["# Heading", "", "A [unreadable] word stood here.", ""])

CRUSHED_ROW = (
    "Width 10 Height 20 Length 30 Diameter 40 Width 11 Height 21 "
    "Length 31 Diameter 41 Width 12 Height 22 Length 32 Diameter 42"
)
CRUSHED_BODY = "\n".join(["# Heading", "", CRUSHED_ROW, ""])

# A repair of `CRUSHED_ROW`: the same tokens in order, one pair per row. The
# preservation check ignores line breaks, so this passes.
CRUSHED_TABLE = "\n".join(
    [
        "| Width | 10 |",
        "| --- | --- |",
        "| Height | 20 |",
        "| Length | 30 |",
        "| Diameter | 40 |",
        "| Width | 11 |",
        "| Height | 21 |",
        "| Length | 31 |",
        "| Diameter | 41 |",
        "| Width | 12 |",
        "| Height | 22 |",
        "| Length | 32 |",
        "| Diameter | 42 |",
    ]
)

# A row off its separator's width; post opens it whether or not inspection
# ran.
OFF_WIDTH_TABLE_BODY = "\n".join(
    ["# Heading", "", "| A | B |", "| --- | --- |", "| x |", ""]
)
OFF_WIDTH_TABLE_FIX = '{"rows": [{"row": 3, "text": "| x |  |"}]}'


def run_with_inspection(
    source: Path,
    registry: EngineRegistry,
    inspect_provider: Provider,
    *,
    post_provider: Provider | None = None,
    pages_per_request: int = DEFAULT_PAGES_PER_REQUEST,
    temp_root: Path | None = None,
    progress_stream: TextIO | None = None,
    **overrides: object,
) -> FileResult:
    config = make_run_config(
        source,
        llm_inspection="insp",
        llm_post="post" if post_provider is not None else None,
        **overrides,
    )
    # A narrow page window puts a short fixture on the chunked path.
    inspection = InspectOperation(
        provider=inspect_provider,
        prompt="INSPECT",
        model_key="insp",
        pages_per_request=pages_per_request,
    )
    post = (
        PostOperation(provider=post_provider, prompt="FIX", model_key="post")
        if post_provider is not None
        else None
    )
    ctx = RunContext(
        config=config,
        registry=registry,
        log_stream=None,
        progress_stream=progress_stream
        if progress_stream is not None
        else io.StringIO(),
        inspection=inspection,
        post=post,
        temp_root=temp_root,
    )
    item = QueueItem(source=source, include_extension=False)
    return process_file(item, ctx)


def test_inspection_substitutes_marker(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=INSPECT_BODY)]
    )
    reply = json.dumps(
        {
            "edits": [
                {
                    "page": 1,
                    "line": 3,
                    "old": "A [unreadable] word stood here.",
                    "new": "A legible word stood here.",
                }
            ]
        }
    )
    provider = FakeProvider([reply])

    result = run_with_inspection(src, registry, provider)

    assert result.outcome is Outcome.OK
    assert result.status is ResultStatus.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "insp"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "[unreadable]" not in text
    assert "legible" in text


def test_engine_marks_pages_only_under_inspection(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    engine = StubEngine(extensions=frozenset({"pdf"}), body=INSPECT_BODY)
    registry = EngineRegistry([engine])

    run_with_inspection(src, registry, FakeProvider([json.dumps({"edits": []})]))
    assert engine.last_options is not None
    assert engine.last_options.mark_pages is True

    # Without inspection nothing addresses pages, so no marks are asked for.
    process_file(
        QueueItem(source=src, include_extension=False),
        RunContext(
            config=make_run_config(src),
            registry=registry,
            progress_stream=io.StringIO(),
        ),
    )
    assert engine.last_options.mark_pages is False


def test_page_marks_never_reach_the_written_result(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    body = "\n".join(
        [page_mark(1), "# Heading", "", page_mark(2), "Second paragraph.", ""]
    )
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])

    result = run_with_inspection(
        src, registry, FakeProvider([json.dumps({"edits": []})])
    )

    assert result.outcome is Outcome.OK
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "raw2md:page" not in text
    assert "Second paragraph." in text


def test_inspection_addresses_an_edit_by_its_page(tmp_path: Path) -> None:
    # An edit naming page 2 lands on that page's line, not on line 2.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    body = "\n".join(
        [
            page_mark(1),
            "# Heading",
            "",
            page_mark(2),
            "A [unreadable] word stood here.",
            "",
        ]
    )
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])
    reply = json.dumps(
        {
            "edits": [
                {
                    "page": 2,
                    "line": 1,
                    "old": "A [unreadable] word stood here.",
                    "new": "A legible word stood here.",
                }
            ]
        }
    )

    result = run_with_inspection(src, registry, FakeProvider([reply]))

    assert result.status is ResultStatus.OK
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "legible" in text
    assert "[unreadable]" not in text


def test_a_flag_of_the_reply_opens_no_post_zone(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    body = CRUSHED_BODY
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])
    # The model reports the line and repairs nothing; post sends only what its
    # own reading opens.
    inspect_reply = json.dumps(
        {"edits": [{"page": 1, "line": 3, "flag": "flattened-block"}]}
    )
    post_provider = FakeProvider([])

    result = run_with_inspection(
        src,
        registry,
        FakeProvider([inspect_reply]),
        post_provider=post_provider,
    )

    assert result.outcome is Outcome.OK
    assert post_provider.calls == 0
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "insp"
    assert header.post == "post"


def test_a_block_the_same_reply_rebuilt_costs_post_nothing(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=CRUSHED_BODY)]
    )
    # The report writes nothing; the rebuild lands, and post reads the result.
    inspect_reply = json.dumps(
        {
            "edits": [
                {"page": 1, "line": 3, "flag": "flattened-block"},
                {"page": 1, "line": 3, "old": CRUSHED_ROW, "new": CRUSHED_TABLE},
            ]
        }
    )
    post_provider = FakeProvider([])

    result = run_with_inspection(
        src,
        registry,
        FakeProvider([inspect_reply]),
        post_provider=post_provider,
    )

    assert result.outcome is Outcome.OK
    assert post_provider.calls == 0
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "| Width | 10 |" in text


def test_inspection_skipped_for_docx(tmp_path: Path) -> None:
    src = tmp_path / "a.docx"
    src.write_bytes(b"PK\x03\x04 stub")
    registry = EngineRegistry(
        [
            StubEngine(
                extensions=frozenset({"docx"}),
                method=ConversionMethod.PANDOC,
                body=INSPECT_BODY,
            )
        ]
    )
    provider = FakeProvider([])

    result = run_with_inspection(src, registry, provider)

    assert result.outcome is Outcome.OK
    assert provider.calls == 0
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "none"


def test_inspection_djvu_without_temp_root_is_failed_not_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.djvu"
    src.write_bytes(b"AT&TFORM stub")
    registry = EngineRegistry(
        [
            StubEngine(
                extensions=frozenset({"djvu"}),
                method=ConversionMethod.DJVU_MARKER,
                body=INSPECT_BODY,
            )
        ]
    )
    provider = FakeProvider([])

    # A djvu is applicable, so a failed assembly is `failed`, not `none`.
    result = run_with_inspection(src, registry, provider)

    assert result.outcome is Outcome.OK
    assert provider.calls == 0
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"
    assert (tmp_path / "a.md").exists()
    assert all(r.levelname == "WARNING" for r in caplog.records)


def test_inspection_djvu_build_error_is_failed_not_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.djvu"
    src.write_bytes(b"AT&TFORM stub")
    registry = EngineRegistry(
        [
            StubEngine(
                extensions=frozenset({"djvu"}),
                method=ConversionMethod.DJVU_MARKER,
                body=INSPECT_BODY,
            )
        ]
    )
    provider = FakeProvider([])

    def _fail_assembly(source: Path, temp_root: Path) -> bytes:
        raise ConversionError("djvu assembly stub failure")

    monkeypatch.setattr("raw2md.engines.djvu.djvu_to_pdf_bytes", _fail_assembly)

    result = run_with_inspection(src, registry, provider, temp_root=tmp_path)

    assert result.outcome is Outcome.OK
    assert provider.calls == 0
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"
    assert (tmp_path / "a.md").exists()
    assert all(r.levelname == "WARNING" for r in caplog.records)


def _assembling_djvu_engine(pdf: bytes) -> StubEngine:
    """A stub standing in for the djvu chain: it converts a pdf it assembled."""
    return StubEngine(
        extensions=frozenset({"djvu"}),
        method=ConversionMethod.DJVU_MARKER,
        body=INSPECT_BODY,
        assembled_pdf=pdf,
    )


def test_inspection_reads_the_pdf_the_djvu_route_assembled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Assembling a scanned book is expensive; inspection reuses the route's pdf.
    src = tmp_path / "a.djvu"
    src.write_bytes(b"AT&TFORM stub")
    engine = _assembling_djvu_engine(b"%PDF-assembled-by-the-route")
    provider = FakeProvider([json.dumps({"edits": []})])

    def _second_build(source: Path, temp_root: Path) -> bytes:
        raise AssertionError("the assembled pdf was rebuilt")

    monkeypatch.setattr("raw2md.engines.djvu.djvu_to_pdf_bytes", _second_build)

    result = run_with_inspection(
        src, EngineRegistry([engine]), provider, temp_root=tmp_path / "tmp"
    )

    assert result.outcome is Outcome.OK
    assert provider.calls == 1
    sent = [part for part in provider.parts[0] if isinstance(part, MediaPart)]
    assert [part.data for part in sent] == [b"%PDF-assembled-by-the-route"]
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "insp"


def test_assembled_pdf_is_gone_once_the_file_is_done(tmp_path: Path) -> None:
    # The pdf of a scanned book is huge: it lives as long as its queue item.
    src = tmp_path / "a.djvu"
    src.write_bytes(b"AT&TFORM stub")
    temp_root = tmp_path / "tmp"
    engine = _assembling_djvu_engine(b"%PDF-assembled-by-the-route")
    provider = FakeProvider([json.dumps({"edits": []})])

    run_with_inspection(src, EngineRegistry([engine]), provider, temp_root=temp_root)

    assert engine.last_source_pdf is not None
    assert not engine.last_source_pdf.exists()
    assert list(temp_root.iterdir()) == []


def test_engine_gets_a_scratch_dir_only_under_inspection(tmp_path: Path) -> None:
    src = tmp_path / "a.djvu"
    src.write_bytes(b"AT&TFORM stub")
    temp_root = tmp_path / "tmp"
    engine = _assembling_djvu_engine(b"%PDF-assembled-by-the-route")
    provider = FakeProvider([json.dumps({"edits": []})])

    run_with_inspection(src, EngineRegistry([engine]), provider, temp_root=temp_root)
    assert engine.last_options is not None
    assert engine.last_options.scratch_dir is not None
    assert engine.last_options.scratch_dir.parent == temp_root

    # Without inspection the engine gets no folder and disposes of the pdf.
    process_file(
        QueueItem(source=src, include_extension=False),
        RunContext(
            config=make_run_config(src),
            registry=EngineRegistry([engine]),
            progress_stream=io.StringIO(),
            temp_root=temp_root,
        ),
    )
    assert engine.last_options.scratch_dir is None


def test_inspection_too_large_keeps_base_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=INSPECT_BODY)]
    )
    provider = FakeProvider([DocumentTooLargeError("over the limit")])

    result = run_with_inspection(src, registry, provider)

    # An oversize request is a permanent skip: the result is kept, the step
    # failed.
    assert result.outcome is Outcome.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "[unreadable]" in text  # not substituted
    assert caplog.records
    assert all(r.levelname == "WARNING" for r in caplog.records)


def test_inspection_provider_error_is_llm_error_with_base_result(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=INSPECT_BODY)]
    )
    provider = FakeProvider([RateLimitError("429 exhausted")])

    result = run_with_inspection(src, registry, provider)

    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "[unreadable]" in text
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_inspection_refused_access_is_llm_error_and_failed(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=INSPECT_BODY)]
    )
    provider = FakeProvider([AuthError("bad key")])

    result = run_with_inspection(src, registry, provider)

    assert provider.calls == 1
    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"


def test_inspection_unusable_reply_is_llm_error_and_failed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=INSPECT_BODY)]
    )
    # An unusable reply is retried once, then fails; it is never a no-op.
    provider = FakeProvider(["totally not a JSON reply", "still not a JSON reply"])

    result = run_with_inspection(src, registry, provider)

    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "[unreadable]" in text  # base body kept, nothing substituted
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_inspection_empty_reply_is_llm_error_and_failed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=INSPECT_BODY)]
    )
    # An empty reply is not a verdict of "nothing to fix".
    provider = FakeProvider(["", ""])

    result = run_with_inspection(src, registry, provider)

    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "[unreadable]" in text  # base body kept, nothing substituted
    assert any(r.levelname == "ERROR" for r in caplog.records)


# Two pages: with a one-page window each page is its own request.
CHUNKED_INSPECT_BODY = "\n".join(
    [
        page_mark(1),
        "# Heading",
        "",
        "A [unreadable] word stood here.",
        "",
        page_mark(2),
        "The second paragraph takes a page of its own.",
        "",
    ]
)

PAGE_ONE_FIX = json.dumps(
    {
        "edits": [
            {
                "page": 1,
                "line": 3,
                "old": "A [unreadable] word stood here.",
                "new": "A legible word stood here.",
            }
        ]
    }
)


def _write_pdf_with_images(path: Path, pages: Sequence[bytes | None]) -> None:
    """Write a PDF with one blank or empty page per entry.

    A `None` entry needs no image; the chunked inspection tests below only
    need the page count.
    """
    doc = pymupdf.open()
    try:
        for png in pages:
            page = doc.new_page()
            if png is not None:
                page.insert_image(pymupdf.Rect(10, 10, 60, 40), stream=png)
        doc.save(str(path))
    finally:
        doc.close()


def _chunked_registry() -> EngineRegistry:
    return EngineRegistry(
        [StubEngine(extensions=frozenset({"pdf"}), body=CHUNKED_INSPECT_BODY)]
    )


def test_inspection_partial_keeps_the_edits_of_the_chunks_that_ran(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    _write_pdf_with_images(src, [None, None])
    # Page 1 is repaired, page 2 is refused.
    provider = FakeProvider([PAGE_ONE_FIX, RateLimitError("429 exhausted")])

    result = run_with_inspection(
        src, _chunked_registry(), provider, pages_per_request=1
    )

    assert provider.calls == 2
    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    # The field names the engine; coverage is the evaluator's entry.
    assert header.inspection == "insp"
    assert "inspection_coverage" in header.issues
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "legible" in text
    assert "[unreadable]" not in text
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_inspection_partial_is_a_skip_when_a_chunk_is_oversize(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.pdf"
    _write_pdf_with_images(src, [None, None])
    provider = FakeProvider([PAGE_ONE_FIX, DocumentTooLargeError("over the limit")])

    result = run_with_inspection(
        src, _chunked_registry(), provider, pages_per_request=1
    )

    # An oversize request is a deliberate skip in any chunk: not an LLM error.
    assert result.outcome is Outcome.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "insp"
    assert "inspection_coverage" in header.issues
    # Inspection logs its own ladder below WARNING, so the file's outcome is
    # the one line.
    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "a.pdf" in caplog.records[0].message
    assert "1 of 2 chunks were not inspected in full" in caplog.records[0].message


def test_inspection_first_chunk_failure_is_failed_not_partial(
    tmp_path: Path,
) -> None:
    src = tmp_path / "a.pdf"
    _write_pdf_with_images(src, [None, None])
    provider = FakeProvider([RateLimitError("429 exhausted")])

    result = run_with_inspection(
        src, _chunked_registry(), provider, pages_per_request=1
    )

    # No chunk completed, so there is no partial work to claim.
    assert provider.calls == 1
    assert result.outcome is Outcome.LLM_ERROR
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "failed"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "[unreadable]" in text  # base body kept


def test_inspection_full_chunked_pass_keeps_the_model_key(tmp_path: Path) -> None:
    # Nothing lost: the field is the model key, as for an unchunked run.
    src = tmp_path / "a.pdf"
    _write_pdf_with_images(src, [None, None])
    provider = FakeProvider([PAGE_ONE_FIX, json.dumps({"edits": []})])

    result = run_with_inspection(
        src, _chunked_registry(), provider, pages_per_request=1
    )

    assert provider.calls == 2
    assert result.outcome is Outcome.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "insp"
    assert header.status is ResultStatus.OK


def test_inspection_chunked_pass_shows_the_chunk_count(tmp_path: Path) -> None:
    # The stage bracket names the chunk in flight, so a slow pass moves.
    src = tmp_path / "a.pdf"
    _write_pdf_with_images(src, [None, None])
    provider = FakeProvider([PAGE_ONE_FIX, json.dumps({"edits": []})])
    stream = io.StringIO()

    result = run_with_inspection(
        src, _chunked_registry(), provider, pages_per_request=1, progress_stream=stream
    )

    assert result.outcome is Outcome.OK
    output = stream.getvalue()
    assert "chunk 1/2" in output
    assert "chunk 2/2" in output


def test_md_route_reads_a_result_inspected_in_part(tmp_path: Path) -> None:
    # A `partial` result is the tool's own: its header is stripped, and the
    # new run records its own steps.
    from raw2md.header import build_stub, render_result

    previous = build_stub(
        "a.pdf",
        inspection="partial",
        source_hash="prior-hash",
    )
    previous.status = ResultStatus.BAD
    src = tmp_path / "a.md"
    src.write_text(render_result(previous, OK_BODY), encoding="utf-8")

    result = run_one(src, EngineRegistry([]))  # md has no engine

    assert result.outcome is Outcome.OK
    out = tmp_path / "a_cleaned.md"
    header = read_header(out)
    assert header is not None
    assert header.engine == "clean"
    assert header.inspection == "none"
    assert out.read_text(encoding="utf-8").count("raw2md_version") == 1


def test_md_route_reads_a_result_with_failed_inspection(tmp_path: Path) -> None:
    # A `failed` source-build is the tool's own result too.
    from raw2md.header import build_stub, render_result

    previous = build_stub(
        "a.djvu",
        inspection="failed",
        source_hash="prior-hash",
    )
    previous.status = ResultStatus.BAD
    src = tmp_path / "a.md"
    src.write_text(render_result(previous, OK_BODY), encoding="utf-8")

    result = run_one(src, EngineRegistry([]))  # md has no engine

    assert result.outcome is Outcome.OK
    out = tmp_path / "a_cleaned.md"
    header = read_header(out)
    assert header is not None
    assert header.engine == "clean"
    assert header.inspection == "none"
    assert out.read_text(encoding="utf-8").count("raw2md_version") == 1


# --- LLM-OCR integration ----------------------------------------------------

# Two page rasters and their transcripts. Both pages clear the density floor
# (350 chars/page), and the sentences are numbered so cleaning does not trim
# them as a repetition loop.
OCR_PAGES = (b"png-1", b"png-2")
OCR_REPLIES = [
    "# Heading\n\n"
    + " ".join(f"The first page holds connected text {n}." for n in range(10)),
    " ".join(
        f"This is recognized text of sufficient length on the second page {n}."
        for n in range(10)
    ),
]


def _fake_render_pages(source: Path, **_: object) -> Iterator[bytes]:
    """Stand in for pymupdf.render_pages: yield fixed rasters, ignore the file."""
    yield from OCR_PAGES


def run_with_ocr(
    source: Path,
    registry: EngineRegistry,
    provider: Provider,
    *,
    temp_root: Path | None = None,
    **overrides: object,
) -> FileResult:
    config = make_run_config(source, llm_ocr="fake", **overrides)
    op = OcrOperation(provider=provider, prompt="OCR", model_key="fake")
    ctx = RunContext(
        config=config,
        registry=registry,
        log_stream=None,
        progress_stream=io.StringIO(),
        ocr=op,
        temp_root=temp_root,
    )
    item = QueueItem(source=source, include_extension=False)
    return process_file(item, ctx)


def test_ocr_replaces_engine_and_records_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    provider = FakeProvider(list(OCR_REPLIES))

    result = run_with_ocr(src, EngineRegistry([]), provider)

    assert result.outcome is Outcome.OK
    assert result.status is ResultStatus.OK
    assert provider.calls == len(OCR_PAGES)  # one request per page
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.engine == "fake"
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "recognized text" in text
    assert not resolve_output_target(src).media_dir.exists()


def test_ocr_djvu_route_records_the_model_like_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `source` carries the extension, so `engine` names the model alone.
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)

    def _fake_djvu_to_pdf(source: Path, dest_pdf: Path, temp_root: Path) -> None:
        dest_pdf.write_bytes(b"%PDF-fake")

    monkeypatch.setattr("raw2md.engines.djvu.djvu_to_pdf", _fake_djvu_to_pdf)
    src = tmp_path / "a.djvu"
    src.write_bytes(b"AT&TFORM stub")
    provider = FakeProvider(list(OCR_REPLIES))

    result = run_with_ocr(
        src, EngineRegistry([]), provider, temp_root=tmp_path / "scratch"
    )

    assert result.outcome is Outcome.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.engine == "fake"


def test_ocr_pdf_without_pdf_header_stops_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # OCR is the conversion here, so the signature gate runs too.
    caplog.set_level(logging.ERROR, logger="raw2md")

    def _unexpected_render(*_: object, **__: object) -> Iterator[bytes]:
        raise AssertionError("a mismatched signature must not reach rendering")
        yield b""  # unreachable; makes this a generator function

    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _unexpected_render)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"this file is plainly not a pdf at all")
    provider = FakeProvider([])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    assert result.outcome is Outcome.NO_RESULT
    assert provider.calls == 0
    assert not (tmp_path / "a.md").exists()
    assert "%PDF-" in caplog.text


def test_ocr_result_drops_fabricated_image_links_and_placeholders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # OCR extracts no media, so a fabricated image link must not survive.
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    fabricated_reply = (
        "# Heading\n\n"
        + "The first page holds connected text. " * 10
        + "\n\n![](img_p1.png)\n\n[Image of a belt conveyor]\n"
    )
    provider = FakeProvider([fabricated_reply, OCR_REPLIES[1]])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    assert result.outcome is Outcome.OK
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert "img_p1.png" not in text
    assert "Image of a belt conveyor" not in text
    assert "recognized text" in text


def test_ocr_rate_limit_is_llm_error_without_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    provider = FakeProvider([RateLimitError("429 exhausted")])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    assert result.outcome is Outcome.LLM_ERROR
    assert not (tmp_path / "a.md").exists()
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_ocr_oversize_is_conversion_error_without_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    provider = FakeProvider([DocumentTooLargeError("over the limit")])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    # An oversize page has no fallback under OCR.
    assert result.outcome is Outcome.NO_RESULT
    assert not (tmp_path / "a.md").exists()
    assert any(r.levelname == "ERROR" for r in caplog.records)


def _failing_render(source: Path, **_: object) -> Iterator[bytes]:
    """Stand in for render_pages on a malformed PDF: raise like PyMuPDF would."""
    raise RuntimeError("cannot open broken PDF")
    yield b""  # unreachable; makes this a generator function


def test_ocr_render_failure_is_conversion_error_without_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _failing_render)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"not a real pdf")
    provider = FakeProvider([])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    assert result.outcome is Outcome.NO_RESULT
    assert provider.calls == 0
    assert not (tmp_path / "a.md").exists()
    assert any(r.levelname == "ERROR" for r in caplog.records)


def test_ocr_lost_page_is_marked_in_the_written_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    # Page 1 stays empty over all three attempts; page 2 recognizes.
    provider = FakeProvider(["", "", "", OCR_REPLIES[1]])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    # A lost page does not fail the file; its marker survives, and the status
    # follows it.
    assert result.outcome is Outcome.OK
    assert result.status is ResultStatus.BAD
    text = (tmp_path / "a.md").read_text(encoding="utf-8")
    assert lost_page_marker(1) in text
    assert "1 pages lost" in caplog.text


def test_recognition_failure_not_recommended_after_llm_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="raw2md")
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    # OCR already ran, so recommending it again would be meaningless.
    provider = FakeProvider(["x", "x"])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    assert result.status is ResultStatus.BAD
    assert "quality bad for a.pdf" in caplog.text
    assert "--engine" not in caplog.text


def test_ocr_skipped_for_docx_converts_normally(tmp_path: Path) -> None:
    src = tmp_path / "a.docx"
    src.write_bytes(b"PK\x03\x04 stub")
    registry = EngineRegistry(
        [StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC)]
    )
    provider = FakeProvider([])

    result = run_with_ocr(src, registry, provider)

    assert result.outcome is Outcome.OK
    assert provider.calls == 0
    header = read_header(tmp_path / "a.md")
    assert header is not None
    # `engine` names what converted this file, not the --engine parameter.
    assert header.engine == "pandoc"


def test_recognition_failure_not_recommended_for_docx(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # docx has no LLM-OCR route, so the hint would name a useless flag.
    caplog.set_level(logging.WARNING, logger="raw2md")
    src = tmp_path / "a.docx"
    src.write_bytes(b"PK\x03\x04 stub")
    registry = EngineRegistry(
        [
            StubEngine(
                extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC, body="x"
            )
        ]
    )
    provider = FakeProvider([])

    result = run_with_ocr(src, registry, provider)

    assert result.status is ResultStatus.BAD
    assert "quality bad for a.docx" in caplog.text
    assert "--engine" not in caplog.text


def test_ocr_skipped_for_md_recleans_normally(tmp_path: Path) -> None:
    src = tmp_path / "note.md"
    src.write_text(
        "\n".join(["# Note", "", "A long enough text of the note.", ""]),
        encoding="utf-8",
    )
    provider = FakeProvider([])

    result = run_with_ocr(src, EngineRegistry([]), provider)

    assert result.outcome is Outcome.OK
    assert provider.calls == 0
    header = read_header(tmp_path / "note_cleaned.md")
    assert header is not None
    assert header.engine == "clean"


# --- debug output ------------------------------------------------------------


def test_debug_off_creates_no_debug_folder(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    result = run_one(src, registry)

    assert result.outcome is Outcome.OK
    assert not (tmp_path / "a.debug").exists()


def test_debug_off_leaves_a_stray_debug_folder_untouched(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    debug_dir = tmp_path / "a.debug"
    debug_dir.mkdir()
    (debug_dir / "unrelated.txt").write_text("keep me", encoding="utf-8")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}))])

    result = run_one(src, registry)

    # Without --debug the folder is not part of the collision check.
    assert result.outcome is Outcome.OK
    assert (debug_dir / "unrelated.txt").read_text(encoding="utf-8") == "keep me"


def test_debug_existing_folder_is_replaced(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    debug_dir = tmp_path / "a.debug"
    debug_dir.mkdir()
    (debug_dir / "unrelated.txt").write_text("stale", encoding="utf-8")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=OK_BODY)])

    result = run_one(src, registry, debug=True)

    # The folder carries no metadata, so it is rebuilt; snapshots of runs with
    # different stages never mix.
    assert result.outcome is Outcome.OK
    assert not (debug_dir / "unrelated.txt").exists()
    assert (debug_dir / "conversion.md").read_text(encoding="utf-8") == OK_BODY


def test_debug_omits_stages_not_run(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=OK_BODY)])

    result = run_one(src, registry, debug=True)

    assert result.outcome is Outcome.OK
    debug_dir = tmp_path / "a.debug"
    assert (debug_dir / "conversion.md").read_text(encoding="utf-8") == OK_BODY
    assert (debug_dir / "cleaning.md").exists()
    assert not (debug_dir / "inspection.md").exists()
    assert not (debug_dir / "acceptance.md").exists()
    assert not (debug_dir / "post.md").exists()


def test_debug_saves_every_active_stage(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    body = OFF_WIDTH_TABLE_BODY
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])
    inspect_reply = json.dumps(
        {"edits": [{"page": 1, "line": 5, "flag": "broken-table"}]}
    )
    post_reply = OFF_WIDTH_TABLE_FIX

    result = run_with_inspection(
        src,
        registry,
        FakeProvider([inspect_reply]),
        post_provider=FakeProvider([post_reply]),
        debug=True,
    )

    assert result.outcome is Outcome.OK
    debug_dir = tmp_path / "a.debug"
    assert (debug_dir / "conversion.md").read_text(encoding="utf-8") == body
    cleaned = (debug_dir / "cleaning.md").read_text(encoding="utf-8")
    # Both passes found nothing, and each still writes a snapshot: that tells
    # a stage that ran from one that did not.
    assert (debug_dir / "inspection.md").read_text(encoding="utf-8") == cleaned
    assert (debug_dir / "acceptance.md").read_text(encoding="utf-8") == cleaned
    assert "| x |  |" in (debug_dir / "post.md").read_text(encoding="utf-8")


def test_debug_inspection_alone_omits_post(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    body = CRUSHED_BODY
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])
    inspect_reply = json.dumps(
        {"edits": [{"page": 1, "line": 3, "flag": "flattened-block"}]}
    )

    result = run_with_inspection(
        src, registry, FakeProvider([inspect_reply]), debug=True
    )

    assert result.outcome is Outcome.OK
    debug_dir = tmp_path / "a.debug"
    cleaned = (debug_dir / "cleaning.md").read_text(encoding="utf-8")
    assert (debug_dir / "inspection.md").read_text(encoding="utf-8") == cleaned
    # Acceptance is scoped to inspection's edits, so it runs without post.
    assert (debug_dir / "acceptance.md").read_text(encoding="utf-8") == cleaned
    assert not (debug_dir / "post.md").exists()
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "insp"
    assert header.post == "none"


def test_debug_saves_llm_requests_and_replies(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    body = OFF_WIDTH_TABLE_BODY
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])
    inspect_reply = json.dumps(
        {"edits": [{"page": 1, "line": 5, "flag": "broken-table"}]}
    )
    post_reply = OFF_WIDTH_TABLE_FIX

    result = run_with_inspection(
        src,
        registry,
        FakeProvider([inspect_reply]),
        post_provider=FakeProvider([post_reply]),
        debug=True,
    )

    assert result.outcome is Outcome.OK
    llm_dir = tmp_path / "a.debug" / "llm"
    assert inspect_reply in (llm_dir / "inspection.txt").read_text(encoding="utf-8")
    assert post_reply in (llm_dir / "post.txt").read_text(encoding="utf-8")
    assert not (llm_dir / "ocr.txt").exists()


def test_debug_keeps_ocr_replies_of_a_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _fake_render_pages)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    # OCR is the conversion, so a rate limit on page 2 leaves no result.
    provider = FakeProvider([OCR_REPLIES[0], RateLimitError("429")])

    result = run_with_ocr(src, EngineRegistry([]), provider, debug=True)

    assert result.outcome is Outcome.LLM_ERROR
    assert not (tmp_path / "a.md").exists()
    # The paid-for reply outlives the discarded result.
    trace = (tmp_path / "a.debug" / "llm" / "ocr.txt").read_text(encoding="utf-8")
    assert "### page 1  attempt 1" in trace
    assert OCR_REPLIES[0] in trace


def test_debug_leaves_no_folder_when_ocr_fails_before_the_first_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _failing_render)
    src = tmp_path / "a.pdf"
    src.write_bytes(b"not a real pdf")
    provider = FakeProvider([])

    result = run_with_ocr(src, EngineRegistry([]), provider, debug=True)

    assert result.outcome is Outcome.NO_RESULT
    assert provider.calls == 0
    # No folder is left to block the next run as a collision.
    assert not (tmp_path / "a.debug").exists()


def test_debug_omits_inspection_not_applicable_to_source(tmp_path: Path) -> None:
    # A docx has no scan, so the header says `none` and no snapshot claims an
    # inspection pass.
    src = tmp_path / "a.docx"
    src.write_bytes(b"PK\x03\x04 stub")
    registry = EngineRegistry(
        [
            StubEngine(
                extensions=frozenset({"docx"}),
                method=ConversionMethod.PANDOC,
                body=OK_BODY,
            )
        ]
    )

    result = run_with_inspection(
        src, registry, FakeProvider([]), post_provider=FakeProvider([]), debug=True
    )

    assert result.outcome is Outcome.OK
    header = read_header(tmp_path / "a.md")
    assert header is not None
    assert header.inspection == "none"
    debug_dir = tmp_path / "a.debug"
    assert not (debug_dir / "inspection.md").exists()
    # Post does not need a scan and still ran, idle.
    assert (debug_dir / "post.md").exists()


def test_debug_repeat_run_does_not_mix_stages(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    body = CRUSHED_BODY
    registry = EngineRegistry([StubEngine(extensions=frozenset({"pdf"}), body=body)])
    inspect_reply = json.dumps(
        {"edits": [{"page": 1, "line": 3, "flag": "flattened-block"}]}
    )
    post_reply = CRUSHED_TABLE
    run_with_inspection(
        src,
        registry,
        FakeProvider([inspect_reply]),
        post_provider=FakeProvider([post_reply]),
        debug=True,
    )
    debug_dir = tmp_path / "a.debug"
    assert (debug_dir / "post.md").exists()

    # Snapshots of an earlier run's LLM steps must not look current.
    result = run_one(src, registry, debug=True)

    assert result.outcome is Outcome.OK
    assert (debug_dir / "conversion.md").exists()
    assert (debug_dir / "cleaning.md").exists()
    assert not (debug_dir / "inspection.md").exists()
    assert not (debug_dir / "post.md").exists()
