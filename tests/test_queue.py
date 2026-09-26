"""Tests for queue building, persistence, resume, and skip/in-progress state."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from conftest import make_run_config
from raw2md.header import (
    ResultHeader,
    ResultStatus,
    compute_source_hash,
    to_yaml_block,
)
from raw2md.output import OutputTarget, resolve_output_target, write_md
from raw2md.paths import queue_file
from raw2md.queue import (
    QUEUE_VERSION,
    Queue,
    QueueError,
    QueueItem,
    build_queue,
    has_finished_result,
    is_complete,
    is_unfinished,
    load_queue,
    queue_path,
    readiness_hash,
    remove_queue,
    save_queue,
    write_in_progress_stub,
)

SUPPORTED = frozenset({"pdf", "docx", "djvu", "md"})


def write_result(
    target: OutputTarget,
    source_bytes: bytes,
    status: ResultStatus = ResultStatus.OK,
    *,
    source_name: str = "x.pdf",
) -> None:
    """Write a result md whose header carries the hash of `source_bytes`."""
    header = ResultHeader(
        raw2md_version="0.1.0",
        source=source_name,
        engine="marker",
        inspection="none",
        post="none",
        converted_at=datetime.date.today(),  # noqa: DTZ011 -- local calendar date, mirrors header.py's own converted_at
        source_hash=compute_source_hash(source_bytes),
        status=status,
    )
    write_md(target, to_yaml_block(header) + "body\n")


def write_own_header_md(path: Path, body: str = "body\n") -> None:
    """Write a md file carrying a raw2md result header (a prior result)."""
    header = ResultHeader(
        raw2md_version="0.1.0",
        source=path.name,
        engine="marker",
        inspection="none",
        post="none",
        converted_at=datetime.date.today(),  # noqa: DTZ011 -- local calendar date, mirrors header.py's own converted_at
        source_hash=compute_source_hash(body.encode("utf-8")),
        status=ResultStatus.OK,
    )
    path.write_text(to_yaml_block(header) + body, encoding="utf-8", newline="")


# --- Building --------------------------------------------------------------


def test_build_single_file(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    queue = build_queue(make_run_config(src), SUPPORTED)
    assert len(queue.items) == 1
    assert queue.items[0].source == src.resolve()
    assert queue.items[0].include_extension is False


def test_build_single_file_unsupported_still_queued(tmp_path: Path) -> None:
    # A named file is always queued; support is decided at conversion.
    src = tmp_path / "note.txt"
    src.write_bytes(b"x")
    queue = build_queue(make_run_config(src), SUPPORTED)
    assert [item.source for item in queue.items] == [src.resolve()]


def test_build_folder_filters_and_sorts(tmp_path: Path) -> None:
    (tmp_path / "b.pdf").write_bytes(b"x")
    (tmp_path / "a.docx").write_bytes(b"x")
    (tmp_path / "note.txt").write_bytes(b"x")  # unsupported, skipped
    (tmp_path / "sub").mkdir()  # not a file, skipped
    queue = build_queue(make_run_config(tmp_path), SUPPORTED)
    assert [item.source.name for item in queue.items] == ["a.docx", "b.pdf"]


def test_build_folder_is_not_recursive(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.pdf").write_bytes(b"x")
    queue = build_queue(make_run_config(tmp_path), SUPPORTED)
    assert queue.items == ()


def test_build_empty_folder_is_empty_queue(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    assert build_queue(make_run_config(folder), SUPPORTED).items == ()


def test_build_folder_with_nothing_convertible_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # A run that converts nothing exits 0, so the warning is the only signal.
    (tmp_path / "notes.txt").write_bytes(b"x")
    (tmp_path / "photo.jpg").write_bytes(b"x")
    with caplog.at_level("WARNING", logger="raw2md"):
        assert build_queue(make_run_config(tmp_path), SUPPORTED).items == ()
    record = next(r for r in caplog.records if "no convertible file" in r.message)
    assert "2 of an unsupported format" in record.message
    assert "0 result(s) of an earlier run" in record.message


def test_build_folder_with_only_own_results_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The skipped files are prior results, and the counts say so.
    write_own_header_md(tmp_path / "a.md")
    with caplog.at_level("WARNING", logger="raw2md"):
        assert build_queue(make_run_config(tmp_path), SUPPORTED).items == ()
    record = next(r for r in caplog.records if "no convertible file" in r.message)
    assert "1 result(s) of an earlier run" in record.message


def test_build_folder_with_a_source_does_not_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    with caplog.at_level("WARNING", logger="raw2md"):
        build_queue(make_run_config(tmp_path), SUPPORTED)
    assert not [r for r in caplog.records if "no convertible file" in r.message]


def test_build_nonexistent_input_raises(tmp_path: Path) -> None:
    with pytest.raises(QueueError):
        build_queue(make_run_config(tmp_path / "missing"), SUPPORTED)


def test_build_marks_stem_extension_collision(tmp_path: Path) -> None:
    (tmp_path / "report.pdf").write_bytes(b"x")
    (tmp_path / "report.docx").write_bytes(b"x")
    (tmp_path / "unique.pdf").write_bytes(b"x")
    queue = build_queue(make_run_config(tmp_path), SUPPORTED)
    flags = {item.source.name: item.include_extension for item in queue.items}
    assert flags == {
        "report.docx": True,
        "report.pdf": True,
        "unique.pdf": False,
    }


def test_build_in_place_md_source_forces_sibling_extension(tmp_path: Path) -> None:
    # `foo.md` cleans to `foo_cleaned.md`, so the pdf's default `foo.md` would
    # take the md source's name; the pdf folds in its extension.
    (tmp_path / "foo.md").write_text("# raw\n", encoding="utf-8")
    (tmp_path / "foo.pdf").write_bytes(b"x")
    queue = build_queue(make_run_config(tmp_path), SUPPORTED)
    flags = {item.source.name: item.include_extension for item in queue.items}
    assert flags["foo.pdf"] is True
    targets = {
        item.source.name: item.output_target(None).md_path.name for item in queue.items
    }
    assert targets["foo.pdf"] == "foo.pdf.md"
    assert targets["foo.md"] == "foo_cleaned.md"
    assert "foo.md" not in set(targets.values())


def test_build_cleaned_named_sibling_still_disambiguated(tmp_path: Path) -> None:
    # `a.md` and `a_cleaned.pdf` both default to `a_cleaned.md`.
    (tmp_path / "a.md").write_text("# raw\n", encoding="utf-8")
    (tmp_path / "a_cleaned.pdf").write_bytes(b"x")
    queue = build_queue(make_run_config(tmp_path), SUPPORTED)
    flags = {item.source.name: item.include_extension for item in queue.items}
    assert flags["a_cleaned.pdf"] is True
    targets = {
        item.source.name: item.output_target(None).md_path.name for item in queue.items
    }
    assert targets["a.md"] == "a_cleaned.md"
    assert targets["a_cleaned.pdf"] == "a_cleaned.pdf.md"


# --- In-place own-result guard ---------------------------------------------


def test_folder_in_place_excludes_own_results(tmp_path: Path) -> None:
    # In place, a prior result is skipped; a foreign md is still cleaned.
    (tmp_path / "a.pdf").write_bytes(b"x")
    write_own_header_md(tmp_path / "a.md")
    (tmp_path / "notes.md").write_text("# notes\n", encoding="utf-8")
    queue = build_queue(make_run_config(tmp_path), SUPPORTED)
    assert [item.source.name for item in queue.items] == ["a.pdf", "notes.md"]


def test_folder_with_output_dir_keeps_own_header_md(tmp_path: Path) -> None:
    # With a separate output folder results never reappear as inputs.
    sources = tmp_path / "in"
    sources.mkdir()
    write_own_header_md(sources / "a.md")
    queue = build_queue(
        make_run_config(sources, output_dir=tmp_path / "out"), SUPPORTED
    )
    assert [item.source.name for item in queue.items] == ["a.md"]


def test_folder_output_dir_equal_to_input_is_in_place(tmp_path: Path) -> None:
    sources = tmp_path / "in"
    sources.mkdir()
    write_own_header_md(sources / "a.md")
    queue = build_queue(make_run_config(sources, output_dir=sources), SUPPORTED)
    assert queue.items == ()


def test_explicit_own_header_file_is_always_queued(tmp_path: Path) -> None:
    # The guard is folder-only; a named file is processed.
    own = tmp_path / "a.md"
    write_own_header_md(own)
    queue = build_queue(make_run_config(own), SUPPORTED)
    assert [item.source.name for item in queue.items] == ["a.md"]


# --- Skip-existing ---------------------------------------------------------


def _folder_with_source(tmp_path: Path, data: bytes = b"payload") -> tuple[Path, Path]:
    """A scan folder holding one `a.pdf` plus a separate output dir."""
    sources = tmp_path / "in"
    sources.mkdir()
    src = sources / "a.pdf"
    src.write_bytes(data)
    return sources, tmp_path / "out"


def test_skip_existing_drops_finished(tmp_path: Path) -> None:
    sources, out = _folder_with_source(tmp_path)
    write_result(resolve_output_target(sources / "a.pdf", output_dir=out), b"payload")
    config = make_run_config(sources, output_dir=out, skip_existing=True)
    assert build_queue(config, SUPPORTED).items == ()
    assert (
        len(build_queue(make_run_config(sources, output_dir=out), SUPPORTED).items) == 1
    )


def test_skip_existing_keeps_in_progress(tmp_path: Path) -> None:
    sources, out = _folder_with_source(tmp_path)
    target = resolve_output_target(sources / "a.pdf", output_dir=out)
    write_result(target, b"payload", ResultStatus.IN_PROGRESS)
    config = make_run_config(sources, output_dir=out, skip_existing=True)
    assert [item.source.name for item in build_queue(config, SUPPORTED).items] == [
        "a.pdf"
    ]


def test_skip_existing_drops_result_of_another_source(tmp_path: Path) -> None:
    # A finished result at the name counts, whatever wrote it.
    sources, out = _folder_with_source(tmp_path, b"new-bytes")
    write_result(resolve_output_target(sources / "a.pdf", output_dir=out), b"old-bytes")
    config = make_run_config(sources, output_dir=out, skip_existing=True)
    assert build_queue(config, SUPPORTED).items == ()


def test_skip_existing_keeps_foreign_md(tmp_path: Path) -> None:
    # A foreign md stays queued and stops in the writable preflight.
    sources, out = _folder_with_source(tmp_path)
    out.mkdir()
    (out / "a.md").write_text("someone else's notes\n", encoding="utf-8")
    config = make_run_config(sources, output_dir=out, skip_existing=True)
    assert [item.source.name for item in build_queue(config, SUPPORTED).items] == [
        "a.pdf"
    ]


def test_skip_existing_names_the_result_it_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    sources, out = _folder_with_source(tmp_path)
    target = resolve_output_target(sources / "a.pdf", output_dir=out)
    write_result(target, b"payload")
    config = make_run_config(sources, output_dir=out, skip_existing=True)
    with caplog.at_level("INFO", logger="raw2md"):
        build_queue(config, SUPPORTED)
    record = next(r for r in caplog.records if "skip a.pdf" in r.message)
    assert str(target.md_path) in record.message
    # Without the console flag a skipped file leaves no visible trace.
    assert getattr(record, "screen", False) is True


def test_has_finished_result_reads_the_name_not_the_source(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    assert has_finished_result(target) is False
    write_result(target, b"other-source-bytes")
    assert has_finished_result(target) is True


def test_has_finished_result_false_for_headerless_md(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_md(target, "just a body, no header\n")
    assert has_finished_result(target) is False


# --- is_complete -----------------------------------------------------------


def test_is_complete_missing_result_false(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    assert is_complete(src, resolve_output_target(src)) is False


@pytest.mark.parametrize("status", [ResultStatus.OK, ResultStatus.BAD])
def test_is_complete_terminal_matching_true(
    tmp_path: Path, status: ResultStatus
) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_result(target, b"payload", status)
    assert is_complete(src, target) is True


def test_is_complete_in_progress_false(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_result(target, b"payload", ResultStatus.IN_PROGRESS)
    assert is_complete(src, target) is False


def test_is_complete_headerless_result_false(tmp_path: Path) -> None:
    # --no-yaml output has no header to match, so it is reconverted.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_md(target, "just a body, no header\n")
    assert is_complete(src, target) is False


def test_is_complete_hash_mismatch_false(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"new")
    target = resolve_output_target(src)
    write_result(target, b"old", ResultStatus.OK)
    assert is_complete(src, target) is False


def test_md_readiness_hash_uses_body_not_header(tmp_path: Path) -> None:
    # An md input hashes its body without the header, so it is idempotent.
    body = "# Title\n\ntext\n"
    expected = compute_source_hash(body.encode("utf-8"))
    bare = tmp_path / "bare.md"
    bare.write_text(body, encoding="utf-8")
    assert readiness_hash(bare) == expected
    header = ResultHeader(
        raw2md_version="0.1.0",
        source="bare.md",
        engine="marker",
        inspection="none",
        post="none",
        converted_at=datetime.date.today(),  # noqa: DTZ011 -- local calendar date, mirrors header.py's own converted_at
        source_hash=expected,
        status=ResultStatus.OK,
    )
    own = tmp_path / "own.md"
    own.write_text(to_yaml_block(header) + body, encoding="utf-8", newline="")
    assert readiness_hash(own) == expected


# --- in-progress stub ------------------------------------------------------


def test_in_progress_stub_is_not_complete(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_in_progress_stub(
        target,
        source_name=src.name,
        source_hash=compute_source_hash(src.read_bytes()),
    )
    assert "status: in_progress" in target.md_path.read_text(encoding="utf-8")
    assert is_complete(src, target) is False


# --- is_unfinished ---------------------------------------------------------


def test_is_unfinished_own_stub_true(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_in_progress_stub(
        target,
        source_name=src.name,
        source_hash=readiness_hash(src),
    )
    assert is_unfinished(target, readiness_hash(src)) is True


def test_is_unfinished_missing_result_false(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    assert is_unfinished(resolve_output_target(src), readiness_hash(src)) is False


@pytest.mark.parametrize("status", [ResultStatus.OK, ResultStatus.BAD])
def test_is_unfinished_terminal_result_false(
    tmp_path: Path, status: ResultStatus
) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_result(target, b"payload", status)
    assert is_unfinished(target, readiness_hash(src)) is False


def test_is_unfinished_hash_mismatch_false(tmp_path: Path) -> None:
    # An in-progress result of another source is a collision, not ours.
    src = tmp_path / "a.pdf"
    src.write_bytes(b"new")
    target = resolve_output_target(src)
    write_result(target, b"old", ResultStatus.IN_PROGRESS)
    assert is_unfinished(target, readiness_hash(src)) is False


def test_is_unfinished_foreign_md_false(tmp_path: Path) -> None:
    src = tmp_path / "a.pdf"
    src.write_bytes(b"payload")
    target = resolve_output_target(src)
    write_md(target, "someone else's notes\n")
    assert is_unfinished(target, readiness_hash(src)) is False


# --- Persistence and resume ------------------------------------------------


def test_save_load_round_trip(tmp_path: Path) -> None:
    config = make_run_config(
        tmp_path / "in",
        output_dir=tmp_path / "out",
        skip_existing=True,
        yaml_header=False,
        extract_images=False,
        llm_ocr="gemini_api",
        llm_inspection="gemini_api",
        llm_post="claude_cli",
        llm_latex_fix=True,
        cuda=False,
        log_file=True,
        debug=True,
    )
    queue = Queue(
        params=config,
        items=(
            QueueItem(source=tmp_path / "report.pdf", include_extension=True),
            QueueItem(source=tmp_path / "plain.docx", include_extension=False),
        ),
    )
    path = tmp_path / "queue.json"
    save_queue(queue, path)
    loaded = load_queue(path)
    assert loaded.params == config
    assert loaded.items == queue.items


def test_save_is_atomic_leaves_no_temp(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    save_queue(Queue(params=make_run_config(tmp_path / "in"), items=()), path)
    assert list(tmp_path.iterdir()) == [path]


def test_default_paths_under_state_dir(home: Path) -> None:
    assert queue_path() == queue_file()
    save_queue(Queue(params=make_run_config(home / "in"), items=()))
    assert queue_file().exists()
    assert load_queue().items == ()


def test_load_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(QueueError, match="no saved queue"):
        load_queue(tmp_path / "absent.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(QueueError, match="valid JSON"):
        load_queue(path)


def test_load_unsupported_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    payload = {"version": QUEUE_VERSION + 1, "params": {}, "items": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QueueError, match="unsupported queue version"):
        load_queue(path)


def test_load_missing_param_raises(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    payload = {"version": QUEUE_VERSION, "params": {"input_path": "x"}, "items": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QueueError, match="missing run parameter"):
        load_queue(path)


def test_pre_upgrade_queue_is_rejected_by_version_not_missing_param(
    tmp_path: Path,
) -> None:
    # An added run parameter bumps the version, which refuses the old queue
    # with a clear "start a new run".
    path = tmp_path / "queue.json"
    params = {
        "input_path": "x",
        "output_dir": None,
        "skip_existing": False,
        "overwrite": False,
        "yaml_header": True,
        "extract_images": True,
        "llm_ocr": None,
        "llm_inspection": None,
        "llm_post": None,
        "cuda": True,
        "log_file": False,
        # No "debug" key.
    }
    payload = {"version": QUEUE_VERSION - 1, "params": params, "items": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QueueError, match="unsupported queue version"):
        load_queue(path)


def test_pre_no_log_file_queue_is_rejected_despite_matching_shape(
    tmp_path: Path,
) -> None:
    # A changed meaning under the same key and type passes a shape check;
    # only the version refuses it.
    path = tmp_path / "queue.json"
    params = {
        "input_path": "x",
        "output_dir": None,
        "skip_existing": False,
        "overwrite": False,
        "yaml_header": True,
        "extract_images": True,
        "llm_ocr": None,
        "llm_inspection": None,
        "llm_post": None,
        "cuda": True,
        "log_file": False,
        "debug": False,
    }
    payload = {"version": QUEUE_VERSION - 1, "params": params, "items": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QueueError, match="unsupported queue version"):
        load_queue(path)


def test_pre_overwrite_removal_queue_is_rejected_despite_extra_key(
    tmp_path: Path,
) -> None:
    # The reader ignores an unknown key, so only the version refuses a removed
    # parameter.
    path = tmp_path / "queue.json"
    params = {
        "input_path": "x",
        "output_dir": None,
        "skip_existing": True,
        "overwrite": True,
        "yaml_header": True,
        "extract_images": True,
        "llm_ocr": None,
        "llm_inspection": None,
        "llm_post": None,
        "cuda": True,
        "log_file": True,
        "debug": False,
    }
    payload = {"version": QUEUE_VERSION - 1, "params": params, "items": []}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(QueueError, match="unsupported queue version"):
        load_queue(path)


def test_remove_queue(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    save_queue(Queue(params=make_run_config(tmp_path / "in"), items=()), path)
    remove_queue(path)
    assert not path.exists()
    remove_queue(path)  # no-op when already gone
