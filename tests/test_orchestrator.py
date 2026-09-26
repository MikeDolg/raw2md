"""Tests for the orchestrator: exit-code aggregation, lock, queue lifecycle."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from conftest import make_run_config

from raw2md.cleaning import DEFAULT_WITNESS_MIN
from raw2md.config import RunConfig
from raw2md.engines import (
    ConversionError,
    ConversionResult,
    ConvertOptions,
    Engine,
    EngineRegistry,
)
from raw2md.exit_codes import ExitCode
from raw2md.header import ConversionMethod, ResultStatus, from_yaml_block
from raw2md.keywords import default_keywords, load_keywords
from raw2md.llm.base import (
    DEFAULT_MAX_REQUEST_BYTES,
    Availability,
    DocumentTooLargeError,
    Part,
    Provider,
    ProviderError,
    RateLimitError,
)
from raw2md.llm.chunking import DEFAULT_PAGES_PER_REQUEST
from raw2md.llm.inspection.common import InspectOperation
from raw2md.lock import RunLock
from raw2md.orchestrator import (
    _load_run_settings,
    _provider_for,
    _resolve_inspection,
    _resolve_post,
    aggregate_exit_code,
    run,
    run_resume,
)
from raw2md.output import resolve_output_target
from raw2md.paths import keywords_file, queue_file
from raw2md.pipeline import FileResult, Outcome, RunContext
from raw2md.pipeline import process_file as _real_process_file
from raw2md.prompts import load_prompts as _real_load_prompts
from raw2md.queue import (
    Queue,
    QueueItem,
    readiness_hash,
    save_queue,
    write_in_progress_stub,
)
from raw2md.settings import ModelConfig
from raw2md.settings import load_settings as _real_load_settings
from raw2md.temp import TempPathError

OK_BODY = "\n".join(["# Heading", "", "This is plain text for the check.", ""])


class StubEngine(Engine):
    """Counting in-memory engine, optionally failing for all or named sources."""

    def __init__(
        self,
        *,
        extensions: frozenset[str] = frozenset({"pdf"}),
        method: ConversionMethod = ConversionMethod.MARKER,
        available: bool = True,
        fail: bool = False,
        fail_on: frozenset[str] = frozenset(),
        crash_on: frozenset[str] = frozenset(),
        interrupt_on: frozenset[str] = frozenset(),
        body: str = OK_BODY,
    ) -> None:
        self._extensions = extensions
        self._method = method
        self._available = available
        self._fail = fail
        self._fail_on = fail_on
        # An OSError the route does not catch; the per-file guard isolates it.
        self._crash_on = crash_on
        # Ctrl+C after one asset: no guard catches a BaseException, so the
        # stub and the partial media stay on disk.
        self._interrupt_on = interrupt_on
        self._body = body
        self.calls = 0

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
        self.calls += 1
        if self._fail or source.name in self._fail_on:
            raise ConversionError(f"stub failure: {source.name}")
        if source.name in self._crash_on:
            raise OSError(f"disk error: {source.name}")
        if source.name in self._interrupt_on:
            media_dir.mkdir(parents=True, exist_ok=True)
            (media_dir / "partial.png").write_bytes(b"partial")
            raise KeyboardInterrupt
        return ConversionResult(body=self._body)


def registry_for(*engines: Engine) -> EngineRegistry:
    return EngineRegistry(list(engines))


def _result(outcome: Outcome) -> FileResult:
    return FileResult(outcome, None)


# --- exit-code aggregation (pure) ------------------------------------------


def test_single_ok_is_success() -> None:
    code = aggregate_exit_code([_result(Outcome.OK)], single_file=True)
    assert code is ExitCode.SUCCESS


def test_single_no_result_is_conversion_error() -> None:
    code = aggregate_exit_code([_result(Outcome.NO_RESULT)], single_file=True)
    assert code is ExitCode.CONVERSION_ERROR


def test_single_llm_error_code() -> None:
    code = aggregate_exit_code([_result(Outcome.LLM_ERROR)], single_file=True)
    assert code is ExitCode.LLM_ERROR


def test_single_empty_is_success() -> None:
    assert aggregate_exit_code([], single_file=True) is ExitCode.SUCCESS


def test_batch_all_ok_is_success() -> None:
    results = [_result(Outcome.OK), _result(Outcome.OK)]
    assert aggregate_exit_code(results, single_file=False) is ExitCode.SUCCESS


def test_batch_any_failure_is_partial() -> None:
    results = [_result(Outcome.OK), _result(Outcome.NO_RESULT)]
    assert (
        aggregate_exit_code(results, single_file=False) is ExitCode.PARTIAL_BATCH_ERROR
    )


def test_batch_empty_is_success() -> None:
    assert aggregate_exit_code([], single_file=False) is ExitCode.SUCCESS


# --- end-to-end run with stub engines --------------------------------------


def test_run_single_file_ok(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert (home / "a.md").exists()
    assert not queue_file().exists()


def test_run_single_file_bad_is_success(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(make_run_config(src), registry=registry_for(StubEngine(body="x")))
    assert code == int(ExitCode.SUCCESS)


def test_run_single_file_conversion_error(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(make_run_config(src), registry=registry_for(StubEngine(fail=True)))
    assert code == int(ExitCode.CONVERSION_ERROR)
    assert not (home / "a.md").exists()


def test_run_single_file_unavailable_engine(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(make_run_config(src), registry=registry_for(StubEngine(available=False)))
    assert code == int(ExitCode.CONVERSION_ERROR)


def test_run_batch_all_ok(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.pdf").write_bytes(b"y")
    code = run(make_run_config(folder), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert (folder / "a.md").exists()
    assert (folder / "b.md").exists()
    assert not queue_file().exists()


def test_run_batch_mixed_failure_is_partial(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "bad.pdf").write_bytes(b"y")
    engine = StubEngine(fail_on=frozenset({"bad.pdf"}))
    code = run(make_run_config(folder), registry=registry_for(engine))
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)
    assert (folder / "a.md").exists()
    assert not (folder / "bad.md").exists()
    # A NO_RESULT item must not cost the whole batch its saved queue.
    assert queue_file().exists()


def test_resume_after_partial_batch_only_redoes_the_failure(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "bad.pdf").write_bytes(b"y")
    code = run(
        make_run_config(folder),
        registry=registry_for(StubEngine(fail_on=frozenset({"bad.pdf"}))),
    )
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)
    assert queue_file().exists()

    # Resume recognizes a.pdf's finished result by hash and skips it.
    engine = StubEngine()
    code = run_resume(registry=registry_for(engine))
    assert code == int(ExitCode.SUCCESS)
    assert engine.calls == 1
    assert (folder / "bad.md").exists()
    assert not queue_file().exists()


def test_run_batch_unexpected_error_is_isolated(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "boom.pdf").write_bytes(b"y")
    engine = StubEngine(crash_on=frozenset({"boom.pdf"}))
    code = run(make_run_config(folder), registry=registry_for(engine))
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)
    assert (folder / "a.md").exists()
    assert not (folder / "boom.md").exists()


class _VanishingEngine(StubEngine):
    """Deletes the source during conversion, then fails it.

    `single_file` must reflect INPUT at the start of the run.
    """

    def convert(
        self, source: Path, media_dir: Path, options: ConvertOptions
    ) -> ConversionResult:
        source.unlink()
        raise ConversionError(f"stub failure: {source.name}")


def test_single_file_exit_code_snapshotted_at_start(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(make_run_config(src), registry=registry_for(_VanishingEngine()))
    # The source was a file at the start, so the code stays single-file (4).
    assert code == int(ExitCode.CONVERSION_ERROR)
    assert not src.exists()


def test_run_save_queue_failure_exits_3(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")

    def boom(queue: Queue, path: Path | None = None) -> None:
        raise OSError("state directory is read-only")

    # Without a saved queue there is no crash safety, so the run is refused.
    monkeypatch.setattr("raw2md.orchestrator.save_queue", boom)
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.MISSING_DEPENDENCY)


def test_run_batch_unavailable_engine_is_partial(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.docx").write_bytes(b"y")
    # The docx engine's dependency is absent, so the batch is partial.
    registry = registry_for(
        StubEngine(),
        StubEngine(
            extensions=frozenset({"docx"}),
            method=ConversionMethod.PANDOC,
            available=False,
        ),
    )
    code = run(make_run_config(folder), registry=registry)
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)


def test_run_batch_empty_is_success(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "note.txt").write_text("x", encoding="utf-8")  # unsupported
    code = run(make_run_config(folder), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)


def test_skip_existing_skips_finished_file(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    assert run(make_run_config(src), registry=registry_for(engine)) == int(
        ExitCode.SUCCESS
    )
    assert engine.calls == 1
    code = run(make_run_config(src, skip_existing=True), registry=registry_for(engine))
    assert code == int(ExitCode.SUCCESS)
    assert engine.calls == 1


def test_rerun_without_flags_replaces_own_result(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    assert run(make_run_config(src), registry=registry_for(engine)) == int(
        ExitCode.SUCCESS
    )
    assert engine.calls == 1
    # Without --skip-existing the tool's own result is replaced silently.
    code = run(make_run_config(src), registry=registry_for(engine))
    assert code == int(ExitCode.SUCCESS)
    assert engine.calls == 2


def test_resume_skips_completed_and_processes_rest(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.pdf").write_bytes(b"y")
    engine = StubEngine()
    assert run(make_run_config(folder), registry=registry_for(engine)) == int(
        ExitCode.SUCCESS
    )
    assert engine.calls == 2
    # A crash left b unfinished with the whole queue saved.
    (folder / "b.md").unlink()
    save_queue(
        Queue(
            params=make_run_config(folder),
            items=(
                QueueItem(source=(folder / "a.pdf").resolve(), include_extension=False),
                QueueItem(source=(folder / "b.pdf").resolve(), include_extension=False),
            ),
        )
    )
    code = run_resume(registry=registry_for(engine))
    assert code == int(ExitCode.SUCCESS)
    assert engine.calls == 3
    assert (folder / "b.md").exists()


def test_resume_skips_vanished_source(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    save_queue(
        Queue(
            params=make_run_config(src),
            items=(QueueItem(source=src.resolve(), include_extension=False),),
        )
    )
    src.unlink()  # the queued source is gone before resume
    # A vanished source is skipped, not failed.
    code = run_resume(registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)


def test_foreign_md_stops_the_file_in_both_modes(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    foreign = home / "a.md"
    foreign.write_text("someone else's notes\n", encoding="utf-8")
    engine = StubEngine()
    # An md without the tool's header is never replaced and never skipped as
    # finished.
    for config in (make_run_config(src), make_run_config(src, skip_existing=True)):
        assert run(config, registry=registry_for(engine)) == int(
            ExitCode.CONVERSION_ERROR
        )
    assert engine.calls == 0
    assert foreign.read_text(encoding="utf-8") == "someone else's notes\n"


def test_unavailable_route_keeps_the_previous_result(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    assert run(make_run_config(src), registry=registry_for(StubEngine())) == int(
        ExitCode.SUCCESS
    )
    before = (home / "a.md").read_text(encoding="utf-8")
    # The route fails before the result name is cleared, so the result stays.
    code = run(make_run_config(src), registry=registry_for(StubEngine(available=False)))
    assert code == int(ExitCode.CONVERSION_ERROR)
    assert (home / "a.md").read_text(encoding="utf-8") == before


def test_run_absolutizes_relative_output_dir(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(home)
    src = home / "a.pdf"
    src.write_bytes(b"x")
    captured: dict[str, RunConfig] = {}

    def capturing_save(queue: Queue, path: Path | None = None) -> None:
        captured["params"] = queue.params
        save_queue(queue, path)

    monkeypatch.setattr("raw2md.orchestrator.save_queue", capturing_save)
    code = run(
        make_run_config(src, output_dir=Path("out")),
        registry=registry_for(StubEngine()),
    )
    assert code == int(ExitCode.SUCCESS)
    # Absolute paths make a resume from another cwd safe.
    assert captured["params"].input_path.is_absolute()
    saved_output = captured["params"].output_dir
    assert saved_output is not None
    assert saved_output.is_absolute()


def test_source_kept_when_output_dir_is_ancestor(home: Path) -> None:
    book_dir = home / "book"
    book_dir.mkdir()
    src = book_dir / "book.pdf"
    src.write_bytes(b"x")
    # The media folder would be the source's own directory.
    code = run(
        make_run_config(src, output_dir=home),
        registry=registry_for(StubEngine()),
    )
    assert code == int(ExitCode.CONVERSION_ERROR)
    assert src.exists()


def test_lock_held_refuses_run(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    lock = RunLock()
    lock.acquire()
    try:
        code = run(make_run_config(src), registry=registry_for(StubEngine()))
    finally:
        lock.release()
    assert code == int(ExitCode.MISSING_DEPENDENCY)


def test_temp_path_error_fails_fast(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")

    def boom() -> Path:
        raise TempPathError("temp path is not writable")

    # Without an injected registry the orchestrator selects a temp root.
    monkeypatch.setattr("raw2md.orchestrator.select_temp_root", boom)
    code = run(make_run_config(src))
    assert code == int(ExitCode.MISSING_DEPENDENCY)


# --- in-place output dir must not clobber the source -----------------------

MD_BODY = "\n".join(["# Document", "", "Document text for a second cleaning.", ""])


def test_in_place_md_via_output_dir_preserves_source(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    src = folder / "note.md"
    src.write_text(MD_BODY, encoding="utf-8")
    # An output dir equal to the source folder is in-place.
    config = make_run_config(src, output_dir=folder)
    code = run(config, registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert src.read_text(encoding="utf-8") == MD_BODY
    assert (folder / "note_cleaned.md").exists()


def test_in_place_sibling_pdf_does_not_clobber_source(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    md_src = folder / "note.md"
    md_src.write_text(MD_BODY, encoding="utf-8")
    pdf_src = folder / "note.pdf"
    pdf_src.write_bytes(b"x")
    # The pdf's media folder would be `note.pdf`, the source itself, so the
    # guard refuses that file.
    config = make_run_config(folder, output_dir=folder)
    code = run(config, registry=registry_for(StubEngine()))
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)
    assert md_src.read_text(encoding="utf-8") == MD_BODY
    assert pdf_src.read_bytes() == b"x"
    assert (folder / "note_cleaned.md").exists()


# --- resume ----------------------------------------------------------------


def test_resume_without_queue_is_argument_error(home: Path) -> None:
    assert run_resume() == int(ExitCode.ARGUMENT_ERROR)


def test_resume_refused_under_held_lock_keeps_queue(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    save_queue(
        Queue(
            params=make_run_config(src),
            items=(QueueItem(source=src, include_extension=False),),
        )
    )
    lock = RunLock()
    lock.acquire()
    try:
        code = run_resume(registry=registry_for(StubEngine()))
    finally:
        lock.release()
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    # The lock is taken before the queue is read.
    assert queue_file().exists()


def test_resume_replays_saved_queue(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    queue = Queue(
        params=make_run_config(src),
        items=(QueueItem(source=src, include_extension=False),),
    )
    save_queue(queue)

    code = run_resume(registry=registry_for(StubEngine()))

    assert code == int(ExitCode.SUCCESS)
    assert (home / "a.md").exists()
    assert not queue_file().exists()


def _result_status(path: Path) -> ResultStatus | None:
    header = from_yaml_block(path.read_text(encoding="utf-8"))
    return None if header is None else header.status


def _queue_for(source: Path, **overrides: object) -> None:
    save_queue(
        Queue(
            params=make_run_config(source, **overrides),
            items=(QueueItem(source=source, include_extension=False),),
        )
    )


def test_resume_keeps_the_original_run_s_no_log_file_choice(home: Path) -> None:
    # Resume replays the saved --no-log-file.
    src = home / "a.pdf"
    src.write_bytes(b"x")
    _queue_for(src, log_file=False)

    code = run_resume(registry=registry_for(StubEngine()))

    assert code == int(ExitCode.SUCCESS)
    assert not (home / ".raw2md" / "logs" / "raw2md.log").exists()


def test_resume_redoes_file_left_in_progress(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.pdf").write_bytes(b"y")
    with pytest.raises(KeyboardInterrupt):
        run(
            make_run_config(folder),
            registry=registry_for(StubEngine(interrupt_on=frozenset({"b.pdf"}))),
        )
    stub = folder / "b.md"
    assert _result_status(stub) is ResultStatus.IN_PROGRESS
    assert (folder / "b" / "partial.png").exists()

    engine = StubEngine()
    code = run_resume(registry=registry_for(engine))

    assert code == int(ExitCode.SUCCESS)
    assert _result_status(stub) in (ResultStatus.OK, ResultStatus.BAD)
    assert engine.calls == 1  # a already finished; only b is redone
    assert not (folder / "b" / "partial.png").exists()


def test_resume_refuses_foreign_result(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    foreign = home / "a.md"
    foreign.write_text("someone else's notes\n", encoding="utf-8")
    _queue_for(src)
    engine = StubEngine()

    code = run_resume(registry=registry_for(engine))

    assert code == int(ExitCode.CONVERSION_ERROR)
    assert foreign.read_text(encoding="utf-8") == "someone else's notes\n"
    assert engine.calls == 0


def test_resume_takes_over_an_in_progress_stub_of_another_source(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    target = resolve_output_target(src)
    # A stub for another source is nobody's result, so the name is taken
    # over; the hash only decides how the redo is logged.
    write_in_progress_stub(
        target,
        source_name="other.pdf",
        source_hash="hash-of-another-source",
    )
    _queue_for(src)
    engine = StubEngine()

    code = run_resume(registry=registry_for(engine))

    assert code == int(ExitCode.SUCCESS)
    assert _result_status(target.md_path) is ResultStatus.OK
    assert engine.calls == 1


def test_resume_redoes_a_finished_result_of_another_source(home: Path) -> None:
    # Resume tells done from undone by the source hash alone.
    src = home / "a.pdf"
    src.write_bytes(b"x")
    assert run(make_run_config(src), registry=registry_for(StubEngine())) == int(
        ExitCode.SUCCESS
    )
    src.write_bytes(b"y")  # the result's hash now names other bytes
    _queue_for(src)
    engine = StubEngine()

    code = run_resume(registry=registry_for(engine))

    assert code == int(ExitCode.SUCCESS)
    assert engine.calls == 1


def test_resume_clears_partial_debug_folder(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    target = resolve_output_target(src)
    write_in_progress_stub(
        target,
        source_name=src.name,
        source_hash=readiness_hash(src),
    )
    debug = home / "a.debug"
    debug.mkdir()
    (debug / "post.md").write_text(
        "snapshot of the interrupted run\n", encoding="utf-8"
    )
    _queue_for(src, debug=True)

    code = run_resume(registry=registry_for(StubEngine()))

    assert code == int(ExitCode.SUCCESS)
    # The redo owns the debug folder, so stale snapshots go.
    assert not (debug / "post.md").exists()
    assert (debug / "conversion.md").exists()


def test_skip_existing_still_redoes_an_own_stub(home: Path) -> None:
    # A crash stub is not a result, so even --skip-existing converts the file.
    src = home / "a.pdf"
    src.write_bytes(b"x")
    target = resolve_output_target(src)
    write_in_progress_stub(
        target,
        source_name=src.name,
        source_hash=readiness_hash(src),
    )
    engine = StubEngine()

    code = run(make_run_config(src, skip_existing=True), registry=registry_for(engine))

    assert code == int(ExitCode.SUCCESS)
    assert _result_status(target.md_path) is ResultStatus.OK
    assert engine.calls == 1


# --- run start and summary logging -------------------------------------------


def _spy_screen_info(calls: list[tuple[str, tuple[object, ...]]]) -> object:
    def fake(logger: object, msg: str, *args: object) -> None:
        calls.append((msg, args))

    return fake


def test_run_logs_start_and_summary(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("raw2md.orchestrator.screen_info", _spy_screen_info(calls))
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert len(calls) == 2  # start, then the finish summary
    start_msg, start_args = calls[0]
    assert "starting run" in start_msg
    assert start_args[0] == 1  # one queued file
    assert start_args[1] == src.absolute()  # the input the queue was built from
    finish_msg, finish_args = calls[1]
    assert "finished" in finish_msg
    files, _elapsed, _rate, errors, bad_quality = finish_args
    assert files == 1
    assert errors == 0
    assert bad_quality == 0


def test_run_logs_folder_and_queue_count_before_processing(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.pdf").write_bytes(b"y")
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("raw2md.orchestrator.screen_info", _spy_screen_info(calls))
    code = run(make_run_config(folder), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    start_msg, start_args = calls[0]
    assert "starting run" in start_msg
    assert start_args[0] == 2
    assert start_args[1] == folder.absolute()


def test_run_summary_counts_bad_quality_separately_from_errors(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("raw2md.orchestrator.screen_info", _spy_screen_info(calls))
    # A `bad` verdict is counted apart from errors.
    code = run(make_run_config(src), registry=registry_for(StubEngine(body="x")))
    assert code == int(ExitCode.SUCCESS)
    _, finish_args = calls[1]
    _files, _elapsed, _rate, errors, bad_quality = finish_args
    assert errors == 0
    assert bad_quality == 1


def test_run_summary_counts_no_result_as_error(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("raw2md.orchestrator.screen_info", _spy_screen_info(calls))
    code = run(make_run_config(src), registry=registry_for(StubEngine(fail=True)))
    assert code == int(ExitCode.CONVERSION_ERROR)
    _, finish_args = calls[1]
    _files, _elapsed, _rate, errors, bad_quality = finish_args
    assert errors == 1
    assert bad_quality == 0


def test_ctrl_c_prints_summary_for_files_completed_so_far(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.pdf").write_bytes(b"y")
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr("raw2md.orchestrator.screen_info", _spy_screen_info(calls))
    processed = {"n": 0}

    def flaky_process_file(item: QueueItem, ctx: RunContext) -> FileResult:
        if processed["n"] >= 1:
            raise KeyboardInterrupt
        processed["n"] += 1
        return _real_process_file(item, ctx)

    monkeypatch.setattr("raw2md.orchestrator.process_file", flaky_process_file)
    with pytest.raises(KeyboardInterrupt):
        run(make_run_config(folder), registry=registry_for(StubEngine()))
    # The summary reports on an aborted batch too.
    assert len(calls) == 2
    _, finish_args = calls[1]
    files, _elapsed, _rate, _errors, _bad_quality = finish_args
    assert files == 1
    assert queue_file().exists()


# --- LLM post-processing startup gate and end-to-end -------------------------

_FAKE_MODEL = ModelConfig(
    access="cli",
    model="fake",
    key_env=None,
    command="fake",
    rpm=None,
    tpm=None,
    rpd=None,
)

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


class FakeProvider(Provider):
    """Provider with a fixed availability, vision capability, and queued reply.

    `raises` fails `generate` per file while the startup gate still passes.
    """

    def __init__(
        self,
        *,
        available: bool,
        reply: str = "",
        vision: bool = False,
        raises: ProviderError | None = None,
        model: ModelConfig = _FAKE_MODEL,
    ) -> None:
        super().__init__(model)
        self._available = available
        self._reply = reply
        self._vision = vision
        self._raises = raises
        self.calls = 0

    @property
    def supports_vision(self) -> bool:
        return self._vision

    def available(self) -> Availability:
        return Availability(self._available, None if self._available else "not ready")

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._reply


def test_run_post_unavailable_provider_exits_3(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=False),
    )
    # A missing LLM tool is refused at startup, before any file.
    code = run(
        make_run_config(src, llm_post="claude_cli"), registry=registry_for(engine)
    )
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0
    assert not (home / "a.md").exists()


def test_run_post_unknown_model_exits_3(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    code = run(make_run_config(src, llm_post="ghost"), registry=registry_for(engine))
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0


def test_run_post_applied_end_to_end(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    provider = FakeProvider(available=True, reply=ROW_FIX)
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    code = run(
        make_run_config(src, llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=POST_BODY)),
    )
    assert code == int(ExitCode.SUCCESS)
    assert provider.calls == 1
    text = (home / "a.md").read_text(encoding="utf-8")
    assert "post: claude_cli" in text
    assert "| x |  |" in text


def test_provider_for_reuses_instance_per_model_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One provider per model key, so a shared model keeps one rpm throttle.
    built: list[Provider] = []

    def fake_build(model: ModelConfig) -> Provider:
        provider = FakeProvider(available=True, vision=True)
        built.append(provider)
        return provider

    monkeypatch.setattr("raw2md.orchestrator.build_provider", fake_build)
    cache: dict[str, Provider] = {}
    first = _provider_for("gemini_api", _FAKE_MODEL, cache)
    second = _provider_for("gemini_api", _FAKE_MODEL, cache)
    third = _provider_for("claude_cli", _FAKE_MODEL, cache)
    assert first is second
    assert third is not first
    assert len(built) == 2


def test_resolves_share_provider_for_one_model(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Inspection and post on one key share a provider and its throttle.
    calls = {"n": 0}

    def fake_build(model: ModelConfig) -> Provider:
        calls["n"] += 1
        return FakeProvider(available=True, vision=True)

    monkeypatch.setattr("raw2md.orchestrator.build_provider", fake_build)
    config = make_run_config(
        home / "a.pdf", llm_post="gemini_api", llm_inspection="gemini_api"
    )
    cache: dict[str, Provider] = {}
    run_settings = _load_run_settings(config)
    post = _resolve_post(config, cache, run_settings)
    inspection = _resolve_inspection(config, cache, run_settings)
    assert post is not None
    assert inspection is not None
    assert post.provider is inspection.provider
    assert calls["n"] == 1


def test_latex_fix_reaches_inspection_and_not_post(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The flag widens the inspection edit guard only; post takes no such
    # parameter.
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True, vision=True),
    )
    config = make_run_config(
        home / "a.pdf",
        llm_post="gemini_api",
        llm_inspection="gemini_api",
        llm_latex_fix=True,
    )
    run_settings = _load_run_settings(config)
    inspection = _resolve_inspection(config, {}, run_settings)
    post = _resolve_post(config, {}, run_settings)
    assert inspection is not None
    assert inspection.latex_fix is True
    assert post is not None
    assert not hasattr(post, "latex_fix")


def test_inspection_without_the_flag_stays_closed(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True, vision=True),
    )
    config = make_run_config(home / "a.pdf", llm_inspection="gemini_api")
    inspection = _resolve_inspection(config, {}, _load_run_settings(config))
    assert inspection is not None
    assert inspection.latex_fix is False


def _run_log(home: Path) -> str:
    return (home / ".raw2md" / "logs" / "raw2md.log").read_text(encoding="utf-8")


def test_run_with_latex_fix_warns(home: Path) -> None:
    # A rewritten formula renders as cleanly as the original, so the log is
    # the only record of the mode.
    src = home / "a.pdf"
    src.write_bytes(b"x")
    run(
        make_run_config(src, log_file=True, llm_latex_fix=True),
        registry=registry_for(StubEngine()),
    )
    log = _run_log(home)
    assert "WARNING" in log
    assert "--llm-latex-fix is on" in log


def test_run_without_latex_fix_does_not_warn(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    run(make_run_config(src, log_file=True), registry=registry_for(StubEngine()))
    assert "--llm-latex-fix" not in _run_log(home)


def _write_inspection_settings(home: Path, **window: int) -> None:
    """A settings.json whose single API model carries the given window fields."""
    raw2md = home / ".raw2md"
    raw2md.mkdir(exist_ok=True)
    data = {
        "models": {
            "gemini_api": {
                "access": "api",
                "key_env": "FAKE_KEY",
                "model": "fake",
                **window,
            }
        },
        "operations": {
            "inspection": {"allowed": ["gemini_api"]},
            "post": {"allowed": ["gemini_api"]},
        },
    }
    (raw2md / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def _resolve_inspection_with_settings(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> InspectOperation:
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True, vision=True, model=model),
    )
    config = make_run_config(
        home / "a.pdf", llm_post="gemini_api", llm_inspection="gemini_api"
    )
    operation = _resolve_inspection(config, {}, _load_run_settings(config))
    assert operation is not None
    return operation


def test_inspection_request_window_comes_from_settings(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inspection_settings(home, pages_per_request=3, max_request_bytes=4096)

    operation = _resolve_inspection_with_settings(home, monkeypatch)

    assert operation.pages_per_request == 3
    assert operation.max_request_bytes == 4096


def test_inspection_request_window_falls_back_to_defaults(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_inspection_settings(home)

    operation = _resolve_inspection_with_settings(home, monkeypatch)

    assert operation.pages_per_request == DEFAULT_PAGES_PER_REQUEST
    assert operation.max_request_bytes == DEFAULT_MAX_REQUEST_BYTES


def test_settings_and_prompts_loaded_once_per_run(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With all three LLM operations, each settings file is read once per run.
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _render_one_page)
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    settings_calls = {"n": 0}
    prompts_calls = {"n": 0}

    def counting_load_settings(path: Path) -> object:
        settings_calls["n"] += 1
        return _real_load_settings(path)

    def counting_load_prompts(path: Path) -> object:
        prompts_calls["n"] += 1
        return _real_load_prompts(path)

    monkeypatch.setattr("raw2md.orchestrator.load_settings", counting_load_settings)
    monkeypatch.setattr("raw2md.orchestrator.load_prompts", counting_load_prompts)
    # OCR and inspection share the one vision model, so one reply serves
    # both: empty edits are a harmless page body and an inspection no-op.
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True, vision=True, reply='{"edits": []}'),
    )
    code = run(
        make_run_config(
            src,
            llm_ocr="gemini_api",
            llm_inspection="gemini_api",
            llm_post="claude_cli",
        ),
        registry=registry_for(StubEngine()),
    )
    assert code == int(ExitCode.SUCCESS)
    assert settings_calls["n"] == 1
    assert prompts_calls["n"] == 1


INSPECT_BODY = "\n".join(["# Heading", "", "A [unreadable] word stood here.", ""])
INSPECT_REPLY = json.dumps(
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


def test_run_inspection_unavailable_provider_exits_3(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    # Vision-capable but not ready: the availability check, not the gate.
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=False, vision=True),
    )
    # A missing LLM tool is refused at startup, before any file.
    code = run(
        make_run_config(src, llm_inspection="gemini_api"), registry=registry_for(engine)
    )
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0
    assert not (home / "a.md").exists()


def test_run_inspection_unknown_model_exits_3(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    code = run(
        make_run_config(src, llm_inspection="ghost"), registry=registry_for(engine)
    )
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0


def test_run_inspection_non_vision_provider_exits_3(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    # A text-only model in `inspection` is refused at startup, not per file.
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True),
    )
    code = run(
        make_run_config(src, llm_inspection="gemini_api"), registry=registry_for(engine)
    )
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0


def test_run_inspection_applied_end_to_end(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    provider = FakeProvider(available=True, reply=INSPECT_REPLY, vision=True)
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    code = run(
        make_run_config(src, llm_inspection="gemini_api"),
        registry=registry_for(StubEngine(body=INSPECT_BODY)),
    )
    assert code == int(ExitCode.SUCCESS)
    assert provider.calls == 1
    text = (home / "a.md").read_text(encoding="utf-8")
    assert "inspection: gemini_api" in text
    assert "post: none" in text
    assert "[unreadable]" not in text
    assert "legible" in text


# --- LLM-OCR startup gate and end-to-end -------------------------------------

OCR_REPLY = "\n".join(["# Heading", "", "Recognized page text.", ""])


def _render_one_page(source: Path, **_: object) -> Iterator[bytes]:
    """Stand in for pymupdf.render_pages: one fixed raster, ignoring the file."""
    yield b"png"


def test_run_ocr_unavailable_provider_exits_3(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    # Vision-capable but not ready: the availability check, not the gate.
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=False, vision=True),
    )
    code = run(
        make_run_config(src, llm_ocr="gemini_api"), registry=registry_for(engine)
    )
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0
    assert not (home / "a.md").exists()


def test_run_ocr_unknown_model_exits_3(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    code = run(make_run_config(src, llm_ocr="ghost"), registry=registry_for(engine))
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0


def test_run_ocr_non_vision_provider_exits_3(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    engine = StubEngine()
    # A text-only model in the ocr role is refused at startup, not per file.
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True),
    )
    code = run(
        make_run_config(src, llm_ocr="gemini_api"), registry=registry_for(engine)
    )
    assert code == int(ExitCode.MISSING_DEPENDENCY)
    assert engine.calls == 0


def test_run_ocr_applied_end_to_end(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _render_one_page)
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    provider = FakeProvider(available=True, reply=OCR_REPLY, vision=True)
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    # The pdf engine queues the file, but OCR replaces it.
    engine = StubEngine()
    code = run(
        make_run_config(src, llm_ocr="gemini_api"), registry=registry_for(engine)
    )
    assert code == int(ExitCode.SUCCESS)
    assert provider.calls == 1
    assert engine.calls == 0  # the native engine did not run
    text = (home / "a.md").read_text(encoding="utf-8")
    assert "engine: gemini_api" in text
    assert "Recognized page text." in text


# --- CLI flag matrix ---------------------------------------------------------

# A local image link whose target is not on disk.
_IMAGE_BODY = "\n".join(
    ["# Document", "", "Document text.", "", "![fig](figure.png)", ""]
)


def test_output_dir_places_result_in_separate_dir(home: Path) -> None:
    out_dir = home / "out"
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(
        make_run_config(src, output_dir=out_dir), registry=registry_for(StubEngine())
    )
    assert code == int(ExitCode.SUCCESS)
    assert (out_dir / "a.md").exists()
    assert not (home / "a.md").exists()


def test_no_yaml_omits_front_matter(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(
        make_run_config(src, yaml_header=False), registry=registry_for(StubEngine())
    )
    assert code == int(ExitCode.SUCCESS)
    text = (home / "a.md").read_text(encoding="utf-8")
    assert not text.startswith("---")
    assert OK_BODY.splitlines()[0] in text  # body content still present


def test_disable_image_extraction_strips_missing_link(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(
        make_run_config(src, extract_images=False),
        registry=registry_for(StubEngine(body=_IMAGE_BODY)),
    )
    assert code == int(ExitCode.SUCCESS)
    text = (home / "a.md").read_text(encoding="utf-8")
    assert "figure.png" not in text
    assert "![" not in text


def test_extract_images_on_preserves_image_link(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(
        make_run_config(src), registry=registry_for(StubEngine(body=_IMAGE_BODY))
    )
    assert code == int(ExitCode.SUCCESS)
    text = (home / "a.md").read_text(encoding="utf-8")
    assert "figure.png" in text


def test_log_file_is_created(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(make_run_config(src, log_file=True), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    log_path = home / ".raw2md" / "logs" / "raw2md.log"
    assert log_path.exists()


def test_settings_log_file_false_disables_it_without_the_flag(home: Path) -> None:
    # log_file=True is the CLI default; settings.json's false still wins.
    src = home / "a.pdf"
    src.write_bytes(b"x")
    raw2md = home / ".raw2md"
    raw2md.mkdir(exist_ok=True)
    (raw2md / "settings.json").write_text(
        json.dumps(
            {
                "models": {
                    "gemini_api": {
                        "access": "api",
                        "key_env": "FAKE_KEY",
                        "model": "fake",
                    }
                },
                "operations": {},
                "log_file": False,
            }
        ),
        encoding="utf-8",
    )
    code = run(make_run_config(src, log_file=True), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert not (raw2md / "logs" / "raw2md.log").exists()


class _NoisyEngine(StubEngine):
    """Engine that floods stdout/stderr during convert, as marker/surya do."""

    def convert(
        self, source: Path, media_dir: Path, options: ConvertOptions
    ) -> ConversionResult:
        print("RAW MARKER BAR 33%")  # noqa: T201 -- simulates marker/surya console noise for the capture test
        print("SURYA STDERR NOISE", file=sys.stderr)  # noqa: T201 -- simulates marker/surya console noise for the capture test
        return super().convert(source, media_dir, options)


def test_log_file_excludes_raw_engine_output(home: Path) -> None:
    # The log keeps structured records only; engine output is discarded.
    src = home / "a.pdf"
    src.write_bytes(b"x")
    code = run(
        make_run_config(src, log_file=True), registry=registry_for(_NoisyEngine())
    )
    assert code == int(ExitCode.SUCCESS)
    text = (home / ".raw2md" / "logs" / "raw2md.log").read_text(encoding="utf-8")
    assert "RAW MARKER BAR" not in text
    assert "SURYA STDERR NOISE" not in text
    assert "converting a.pdf via marker" in text
    assert "converted a.pdf" in text


def test_cuda_off_reaches_registry_builder(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    captured: dict[str, object] = {}

    def fake_build(
        config: RunConfig,
        temp_root: Path,
        log_stream: object,
        *,
        recognition_batch_size: int | None = None,
    ) -> EngineRegistry:
        captured["cuda"] = config.cuda
        captured["recognition_batch_size"] = recognition_batch_size
        return registry_for(StubEngine())

    monkeypatch.setattr("raw2md.orchestrator.build_default_registry", fake_build)
    monkeypatch.setattr("raw2md.orchestrator.select_temp_root", lambda: home)
    code = run(make_run_config(src, cuda=False))
    assert code == int(ExitCode.SUCCESS)
    assert captured.get("cuda") is False
    # Without settings.json marker's own default stays in force.
    assert captured.get("recognition_batch_size") is None


def test_marker_batch_size_from_settings_reaches_registry_builder(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    raw2md = home / ".raw2md"
    raw2md.mkdir(exist_ok=True)
    (raw2md / "settings.json").write_text(
        json.dumps(
            {
                "models": {
                    "gemini_api": {
                        "access": "api",
                        "key_env": "FAKE_KEY",
                        "model": "fake",
                    }
                },
                "operations": {},
                "marker": {"recognition_batch_size": 8},
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_build(
        config: RunConfig,
        temp_root: Path,
        log_stream: object,
        *,
        recognition_batch_size: int | None = None,
    ) -> EngineRegistry:
        captured["recognition_batch_size"] = recognition_batch_size
        return registry_for(StubEngine())

    monkeypatch.setattr("raw2md.orchestrator.build_default_registry", fake_build)
    monkeypatch.setattr("raw2md.orchestrator.select_temp_root", lambda: home)
    code = run(make_run_config(src))
    assert code == int(ExitCode.SUCCESS)
    assert captured.get("recognition_batch_size") == 8


def test_cleaning_witness_bar_from_settings_reaches_the_run_context(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    raw2md = home / ".raw2md"
    raw2md.mkdir(exist_ok=True)
    (raw2md / "settings.json").write_text(
        json.dumps(
            {
                "models": {
                    "gemini_api": {
                        "access": "api",
                        "key_env": "FAKE_KEY",
                        "model": "fake",
                    }
                },
                "operations": {},
                "cleaning": {"witness_min": 5},
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def capturing_process_file(item: QueueItem, ctx: RunContext) -> FileResult:
        captured["witness_min"] = ctx.witness_min
        return _real_process_file(item, ctx)

    monkeypatch.setattr("raw2md.orchestrator.process_file", capturing_process_file)
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert captured.get("witness_min") == 5


def test_no_cleaning_section_leaves_the_rules_own_witness_bar(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    captured: dict[str, object] = {}

    def capturing_process_file(item: QueueItem, ctx: RunContext) -> FileResult:
        captured["witness_min"] = ctx.witness_min
        return _real_process_file(item, ctx)

    monkeypatch.setattr("raw2md.orchestrator.process_file", capturing_process_file)
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert captured.get("witness_min") == DEFAULT_WITNESS_MIN


# Every section present, and distinct from the shipped file.
_MINIMAL_KEYWORDS = """\
contents_heading:
  - contents
contents_page_label:
  - page
top_level_sections:
  - appendix*
heading_minor_words:
  - of
caption_labels:
  - fig.
image_placeholders:
  - image*
"""


def test_keywords_from_file_reaches_the_run_context(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    raw2md = home / ".raw2md"
    raw2md.mkdir(exist_ok=True)
    (raw2md / "keywords.yaml").write_text(_MINIMAL_KEYWORDS, encoding="utf-8")
    captured: dict[str, object] = {}

    def capturing_process_file(item: QueueItem, ctx: RunContext) -> FileResult:
        captured["keywords"] = ctx.keywords
        return _real_process_file(item, ctx)

    monkeypatch.setattr("raw2md.orchestrator.process_file", capturing_process_file)
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert captured.get("keywords") == load_keywords(keywords_file())
    assert captured.get("keywords") != default_keywords()


def test_no_keywords_file_leaves_the_shipped_dictionary(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    captured: dict[str, object] = {}

    def capturing_process_file(item: QueueItem, ctx: RunContext) -> FileResult:
        captured["keywords"] = ctx.keywords
        return _real_process_file(item, ctx)

    monkeypatch.setattr("raw2md.orchestrator.process_file", capturing_process_file)
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert captured.get("keywords") == default_keywords()


def test_invalid_keywords_warns_but_does_not_block_a_plain_run(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    raw2md = home / ".raw2md"
    raw2md.mkdir(exist_ok=True)
    (raw2md / "keywords.yaml").write_text(
        "contents_heading: [unclosed\n", encoding="utf-8"
    )

    code = run(make_run_config(src), registry=registry_for(StubEngine()))

    assert code == int(ExitCode.SUCCESS)
    assert "keywords.yaml is invalid" in capsys.readouterr().err


def test_invalid_settings_warns_but_does_not_block_a_plain_run(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The batch size reaches every pdf route, so a broken settings.json must
    # warn on the console while the run proceeds.
    src = home / "a.pdf"
    src.write_bytes(b"x")
    raw2md = home / ".raw2md"
    raw2md.mkdir(exist_ok=True)
    (raw2md / "settings.json").write_text("{ not json", encoding="utf-8")

    code = run(make_run_config(src), registry=registry_for(StubEngine()))

    assert code == int(ExitCode.SUCCESS)
    assert "settings.json is invalid" in capsys.readouterr().err


# --- conversion modes --------------------------------------------------------


def test_single_pdf_engine_is_marker(home: Path) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    run(make_run_config(src), registry=registry_for(StubEngine()))
    assert "engine: marker" in (home / "a.md").read_text(encoding="utf-8")


def test_single_docx_engine_is_pandoc(home: Path) -> None:
    src = home / "a.docx"
    src.write_bytes(b"x")
    engine = StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC)
    run(make_run_config(src), registry=registry_for(engine))
    assert "engine: pandoc" in (home / "a.md").read_text(encoding="utf-8")


def test_single_djvu_engine_is_marker(home: Path) -> None:
    # `source` names the .djvu extension, so `engine` says "marker".
    src = home / "a.djvu"
    src.write_bytes(b"x")
    engine = StubEngine(
        extensions=frozenset({"djvu"}), method=ConversionMethod.DJVU_MARKER
    )
    run(make_run_config(src), registry=registry_for(engine))
    assert "engine: marker" in (home / "a.md").read_text(encoding="utf-8")


def test_single_md_engine_is_clean(home: Path) -> None:
    src = home / "a.md"
    src.write_text(MD_BODY, encoding="utf-8")
    run(make_run_config(src), registry=registry_for(StubEngine()))
    # In-place md gets the _cleaned suffix.
    assert "engine: clean" in (home / "a_cleaned.md").read_text(encoding="utf-8")


def test_batch_no_recursion(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    sub = folder / "sub"
    sub.mkdir()
    (sub / "b.pdf").write_bytes(b"x")
    engine = StubEngine()
    code = run(make_run_config(folder), registry=registry_for(engine))
    assert code == int(ExitCode.SUCCESS)
    assert engine.calls == 1
    assert (folder / "a.md").exists()
    assert not (sub / "b.md").exists()


def test_batch_mixed_types_succeed(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.docx").write_bytes(b"x")
    registry = registry_for(
        StubEngine(extensions=frozenset({"pdf"}), method=ConversionMethod.MARKER),
        StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC),
    )
    code = run(make_run_config(folder), registry=registry)
    assert code == int(ExitCode.SUCCESS)
    assert (folder / "a.md").exists()
    assert (folder / "b.md").exists()


def test_stem_collision_folds_extension(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "doc.pdf").write_bytes(b"x")
    (folder / "doc.docx").write_bytes(b"x")
    out_dir = home / "out"
    registry = registry_for(
        StubEngine(extensions=frozenset({"pdf"}), method=ConversionMethod.MARKER),
        StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC),
    )
    # Without an output dir the media folders would clash with the sources.
    code = run(make_run_config(folder, output_dir=out_dir), registry=registry)
    assert code == int(ExitCode.SUCCESS)
    assert (out_dir / "doc.pdf.md").exists()
    assert (out_dir / "doc.docx.md").exists()
    assert not (out_dir / "doc.md").exists()


def test_case_insensitive_collision_folds_extension(home: Path) -> None:
    folder = home / "in"
    folder.mkdir()
    # Doc.pdf and doc.docx collide on "doc.md" regardless of case.
    (folder / "Doc.pdf").write_bytes(b"x")
    (folder / "doc.docx").write_bytes(b"x")
    out_dir = home / "out"
    registry = registry_for(
        StubEngine(extensions=frozenset({"pdf"}), method=ConversionMethod.MARKER),
        StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC),
    )
    code = run(make_run_config(folder, output_dir=out_dir), registry=registry)
    assert code == int(ExitCode.SUCCESS)
    assert (out_dir / "Doc.pdf.md").exists()
    assert (out_dir / "doc.docx.md").exists()
    assert not (out_dir / "Doc.md").exists()
    assert not (out_dir / "doc.md").exists()


def test_uppercase_extension_recognized(home: Path) -> None:
    src = home / "a.PDF"
    src.write_bytes(b"x")
    code = run(make_run_config(src), registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert (home / "a.md").exists()


def test_md_with_output_dir_keeps_plain_name(home: Path) -> None:
    out_dir = home / "out"
    src = home / "note.md"
    src.write_text(MD_BODY, encoding="utf-8")
    code = run(
        make_run_config(src, output_dir=out_dir), registry=registry_for(StubEngine())
    )
    assert code == int(ExitCode.SUCCESS)
    # The _cleaned suffix applies only in place.
    assert (out_dir / "note.md").exists()
    assert not (out_dir / "note_cleaned.md").exists()


# --- LLM runtime failures and combinations -----------------------------------
#
# Per-file failures after the startup gate passed.

# --- post runtime failures ---------------------------------------------------


def test_post_rate_limit_is_llm_error_exits_5(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True, raises=RateLimitError("quota")),
    )
    code = run(
        make_run_config(src, llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=POST_BODY)),
    )
    assert code == int(ExitCode.LLM_ERROR)
    assert (home / "a.md").exists()


def test_post_provider_error_exits_5(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(
            available=True, raises=ProviderError("connection refused")
        ),
    )
    code = run(
        make_run_config(src, llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=POST_BODY)),
    )
    assert code == int(ExitCode.LLM_ERROR)


def test_batch_llm_error_keeps_queue(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.pdf").write_bytes(b"y")
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(
            available=True, raises=ProviderError("connection refused")
        ),
    )
    code = run(
        make_run_config(folder, llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=POST_BODY)),
    )
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)
    # One LLM_ERROR item must not drop the queue.
    assert queue_file().exists()


def test_post_oversize_keeps_base_result_and_exits_0(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    provider = FakeProvider(available=True, raises=DocumentTooLargeError("too big"))
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    # An oversize body is a permanent skip: the base result is kept.
    code = run(
        make_run_config(src, llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=POST_BODY)),
    )
    assert code == int(ExitCode.SUCCESS)
    # Without a zone the oversize path would not run.
    assert provider.calls >= 1
    text = (home / "a.md").read_text(encoding="utf-8")
    assert "| x |\n" in text  # the row is not repaired (post was skipped)
    assert "post: failed" in text


def test_post_llm_error_in_batch_is_partial(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    (folder / "b.pdf").write_bytes(b"y")
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(available=True, raises=RateLimitError("quota")),
    )
    code = run(
        make_run_config(folder, llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=POST_BODY)),
    )
    # LLM errors in a batch collapse to exit 1, not 5.
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)


def test_post_field_records_model_when_no_anchors(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"x")
    provider = FakeProvider(available=True, reply="ignored")
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    # Post ran without a call, so the header names the model, not `none`.
    code = run(
        make_run_config(src, llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=OK_BODY)),
    )
    assert code == int(ExitCode.SUCCESS)
    assert provider.calls == 0
    assert "post: claude_cli" in (home / "a.md").read_text(encoding="utf-8")


# --- inspection runtime failures ---------------------------------------------


def test_inspection_rate_limit_is_llm_error_exits_5(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(
            available=True, vision=True, raises=RateLimitError("quota")
        ),
    )
    code = run(
        make_run_config(src, llm_inspection="gemini_api"),
        registry=registry_for(StubEngine(body=INSPECT_BODY)),
    )
    # The good conversion finished before the LLM stage, so it is kept.
    assert code == int(ExitCode.LLM_ERROR)
    assert (home / "a.md").exists()


def test_inspection_oversize_skips_and_exits_0(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    provider = FakeProvider(
        available=True, vision=True, raises=DocumentTooLargeError("too big")
    )
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    # An oversize source PDF is a permanent skip: `inspection: failed`.
    code = run(
        make_run_config(src, llm_inspection="gemini_api"),
        registry=registry_for(StubEngine(body=INSPECT_BODY)),
    )
    assert code == int(ExitCode.SUCCESS)
    assert provider.calls >= 1  # provider was called; DocumentTooLargeError was raised
    assert "inspection: failed" in (home / "a.md").read_text(encoding="utf-8")


def test_inspection_skipped_for_non_pdf_source(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.docx"
    src.write_bytes(b"x")
    engine = StubEngine(extensions=frozenset({"docx"}), method=ConversionMethod.PANDOC)
    provider = FakeProvider(available=True, vision=True, reply=INSPECT_REPLY)
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    # A docx has no scan, so inspection is skipped silently.
    code = run(
        make_run_config(src, llm_inspection="gemini_api"),
        registry=registry_for(engine),
    )
    assert code == int(ExitCode.SUCCESS)
    assert provider.calls == 0
    assert "inspection: none" in (home / "a.md").read_text(encoding="utf-8")


# --- OCR runtime failures ----------------------------------------------------


def test_ocr_rate_limit_is_llm_error_exits_5(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _render_one_page)
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(
            available=True, vision=True, raises=RateLimitError("quota")
        ),
    )
    code = run(
        make_run_config(src, llm_ocr="gemini_api"),
        registry=registry_for(StubEngine()),
    )
    # OCR is the conversion, so no result; the source was fine, hence exit 5.
    assert code == int(ExitCode.LLM_ERROR)
    assert not (home / "a.md").exists()


def test_resume_after_ocr_llm_error_reconverts_the_file(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _render_one_page)
    folder = home / "in"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"%PDF-1.4 stub")
    (folder / "b.pdf").write_bytes(b"%PDF-1.4 stub")
    failing = FakeProvider(available=True, vision=True, raises=RateLimitError("quota"))
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: failing)
    code = run(
        make_run_config(folder, llm_ocr="gemini_api"),
        registry=registry_for(StubEngine()),
    )
    assert code == int(ExitCode.PARTIAL_BATCH_ERROR)
    assert queue_file().exists()
    assert not (folder / "a.md").exists()
    assert not (folder / "b.md").exists()

    # OCR discards its stub, so resume redoes both files.
    provider = FakeProvider(available=True, vision=True, reply=OCR_REPLY)
    monkeypatch.setattr("raw2md.orchestrator.build_provider", lambda model: provider)
    code = run_resume(registry=registry_for(StubEngine()))
    assert code == int(ExitCode.SUCCESS)
    assert (folder / "a.md").exists()
    assert (folder / "b.md").exists()
    assert not queue_file().exists()


def test_ocr_oversize_exits_4(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.engines.pymupdf.render_pages", _render_one_page)
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")
    monkeypatch.setattr(
        "raw2md.orchestrator.build_provider",
        lambda model: FakeProvider(
            available=True, vision=True, raises=DocumentTooLargeError("too big")
        ),
    )
    # The document is the problem, so exit 4, not 5.
    code = run(
        make_run_config(src, llm_ocr="gemini_api"),
        registry=registry_for(StubEngine()),
    )
    assert code == int(ExitCode.CONVERSION_ERROR)
    assert not (home / "a.md").exists()


# --- post + inspection combination -------------------------------------------

# Inspection reports a flag, and post runs after it over the same body.

_COMBO_INSPECT_REPLY = json.dumps(
    {"edits": [{"page": 1, "line": 3, "flag": "hyphenation"}]}
)
_COMBO_POST_REPLY = "This is plain text for the check."


def test_inspection_plus_post_combined(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = home / "a.pdf"
    src.write_bytes(b"%PDF-1.4 stub")

    def _dispatch(model: ModelConfig) -> FakeProvider:
        if model.access == "api":
            return FakeProvider(available=True, vision=True, reply=_COMBO_INSPECT_REPLY)
        return FakeProvider(available=True, reply=_COMBO_POST_REPLY)

    monkeypatch.setattr("raw2md.orchestrator.build_provider", _dispatch)
    code = run(
        make_run_config(src, llm_inspection="gemini_api", llm_post="claude_cli"),
        registry=registry_for(StubEngine(body=OK_BODY)),
    )
    assert code == int(ExitCode.SUCCESS)
    text = (home / "a.md").read_text(encoding="utf-8")
    assert "inspection: gemini_api" in text
    assert "post: claude_cli" in text
