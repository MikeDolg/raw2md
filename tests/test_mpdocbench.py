"""Tests for the MPDocBench runner under benchmarks/mpdocbench/scripts/."""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import yaml
from mpdocbench import cli, convert, fetch, pdfs, report, scoring
from mpdocbench.pins import (
    BenchmarkError,
    DataDir,
    Document,
    Pins,
    RunDir,
    dump_yaml,
    load_pins,
    read_annotation,
    select_documents,
    system_name,
)
from PIL import Image

_HEADER = """---
raw2md_version: 0.1.0
source: done.pdf
engine: marker
inspection: none
post: none
converted_at: 2026-09-18
source_hash: fX3kQ9wLm2Rt7vBn0sYd4Hc8JpZe6Ua1Gi5KoNq_T2w
status: ok
---
"""
_COLORS = [(220, 30, 30), (30, 220, 30), (30, 30, 220), (220, 220, 30)]


def _jpeg(index: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), _COLORS[index % len(_COLORS)]).save(
        buffer, format="JPEG", quality=90
    )
    return buffer.getvalue()


def _entry(name: str, pages: list[int], language: str = "english") -> dict[str, Any]:
    return {
        "page_info": {
            "image_path": f"{name}.pdf",
            "images_list": [f"images/{name}/page_{n}.jpg" for n in pages],
            "page_attribute": {"language": language, "data_source": "book"},
        }
    }


def _annotation(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _pages(images: Path, name: str, count: int) -> list[bytes]:
    folder = images / name
    folder.mkdir(parents=True)
    written = []
    for number in range(1, count + 1):
        data = _jpeg(number)
        (folder / f"page_{number}.jpg").write_bytes(data)
        written.append(data)
    return written


def _pins(**changes: Any) -> Pins:
    return replace(load_pins(), **changes)


# --- pins and annotation -------------------------------------------------------


def test_the_shipped_pins_load_and_name_known_metrics() -> None:
    pins = load_pins()
    assert pins.dataset_documents == 420
    assert len(pins.slidevqa_decks) == 11
    for names in pins.metrics.values():
        assert all(name in pins.headline for name in names)


def test_read_annotation_takes_one_language_and_sorts_by_name(tmp_path: Path) -> None:
    path = _annotation(
        tmp_path / "a.json",
        [
            _entry("b_eng", [1]),
            _entry("a_chn", [1, 2], "chinese"),
            _entry("a_eng", [2, 1]),
        ],
    )
    assert [d.name for d in read_annotation(path)] == ["a_chn", "a_eng", "b_eng"]
    english = read_annotation(path, "english")
    assert [d.name for d in english] == ["a_eng", "b_eng"]
    assert english[0].pages == ("page_2.jpg", "page_1.jpg")


def test_read_annotation_refuses_a_document_named_twice(tmp_path: Path) -> None:
    path = _annotation(tmp_path / "a.json", [_entry("doc", [1]), _entry("doc", [2])])
    with pytest.raises(BenchmarkError, match="twice"):
        read_annotation(path)


# --- fetch ---------------------------------------------------------------------


def _archive(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in members.items():
            bundle.writestr(name, data)
    return path


def test_extract_pages_applies_the_renames_and_skips_foreign_members(
    tmp_path: Path,
) -> None:
    archive = _archive(
        tmp_path / "data.zip",
        {
            "images/doc/page_1.jpg": b"one",
            "images/typo/paeg_1.jpg": b"two",
            "images/.DS_Store": b"junk",
            "images/../escape.jpg": b"out",
        },
    )
    images = tmp_path / "images"
    count = fetch.extract_pages(archive, images, {"typo/paeg_1.jpg": "typo/page_1.jpg"})
    assert count == 2
    assert (images / "doc" / "page_1.jpg").read_bytes() == b"one"
    assert (images / "typo" / "page_1.jpg").read_bytes() == b"two"
    assert not (images / "typo" / "paeg_1.jpg").exists()
    assert not (tmp_path / "escape.jpg").exists()


def test_download_archive_refuses_bytes_that_miss_the_pin(tmp_path: Path) -> None:
    source = _archive(tmp_path / "source.zip", {"images/doc/page_1.jpg": b"x"})
    data = DataDir(tmp_path / "data")
    data.root.mkdir()
    pins = _pins(dataset_url=source.as_uri(), dataset_sha256="0" * 64)
    with pytest.raises(BenchmarkError, match="hashes to"):
        fetch.download_archive(pins, data)
    assert not list(data.root.iterdir())


def test_download_archive_keeps_bytes_that_match_the_pin(tmp_path: Path) -> None:
    source = _archive(tmp_path / "source.zip", {"images/doc/page_1.jpg": b"x"})
    data = DataDir(tmp_path / "data")
    data.root.mkdir()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    pins = _pins(dataset_url=source.as_uri(), dataset_sha256=digest)
    assert fetch.download_archive(pins, data).read_bytes() == source.read_bytes()


def test_missing_documents_names_a_document_short_of_one_page(tmp_path: Path) -> None:
    images = tmp_path / "images"
    _pages(images, "whole", 2)
    _pages(images, "short", 1)
    documents = [
        Document("whole", ("page_1.jpg", "page_2.jpg"), "english"),
        Document("short", ("page_1.jpg", "page_2.jpg"), "english"),
        Document("absent", ("page_1.jpg",), "english"),
    ]
    assert fetch.missing_documents(images, documents) == ["short", "absent"]


def test_needs_archive_when_an_archive_page_is_gone_after_extraction(
    tmp_path: Path,
) -> None:
    images = tmp_path / "images"
    _pages(images, "book", 2)
    deck = next(iter(load_pins().slidevqa_decks))
    pins = _pins(dataset_sha256="a" * 64)
    documents = [
        Document("book", ("page_1.jpg", "page_2.jpg"), "english"),
        Document(deck, ("page_1.jpg",), "english"),
    ]
    record = {"archive_sha256": "a" * 64}
    assert not fetch.needs_archive(record, pins, images, documents)
    assert fetch.needs_archive({"archive_sha256": "b" * 64}, pins, images, documents)
    (images / "book" / "page_2.jpg").unlink()
    assert fetch.needs_archive(record, pins, images, documents)


class _Column:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def to_pylist(self) -> list[Any]:
        return self._values

    def __getitem__(self, index: int) -> Any:
        value = self._values[index]
        return type("Cell", (), {"as_py": lambda _self: value})()


class _Table:
    def __init__(self, columns: dict[str, list[Any]]) -> None:
        self._columns = columns
        self.column_names = list(columns)

    def column(self, name: str) -> _Column:
        return _Column(self._columns[name])


def test_collect_decks_takes_the_first_row_of_a_deck_in_page_order() -> None:
    table = _Table(
        {
            "deck_url": ["u-other", "u-deck", "u-deck"],
            "page_10": [None, {"bytes": b"p10"}, None],
            "page_2": [None, {"bytes": b"p2"}, {"bytes": b"later"}],
            "page_1": [None, {"bytes": b"p1"}, {"bytes": b"later"}],
        }
    )
    deck = Document("deck", ("page_1.jpg", "page_2.jpg"), "english")
    assert fetch.collect_decks([table], {"u-deck": deck}) == {"deck": [b"p1", b"p2"]}


def test_collect_decks_stops_at_the_first_empty_page() -> None:
    table = _Table(
        {
            "deck_url": ["u"],
            "page_1": [{"bytes": b"p1"}],
            "page_2": [None],
            "page_3": [None],
        }
    )
    deck = Document("deck", ("page_1.jpg", "page_2.jpg", "page_3.jpg"), "english")
    assert fetch.collect_decks([table], {"u": deck}) == {"deck": [b"p1"]}


# --- build ---------------------------------------------------------------------


def _embedded(pdf_path: Path) -> list[bytes]:
    with pymupdf.open(pdf_path) as document:
        return [
            document.extract_image(page.get_images(full=True)[0][0])["image"]
            for page in document
        ]


def test_build_keeps_the_page_bytes_in_annotation_order(tmp_path: Path) -> None:
    images = tmp_path / "images"
    written = _pages(images, "doc", 3)
    document = Document("doc", ("page_3.jpg", "page_1.jpg", "page_2.jpg"), "english")
    assert pdfs.build([document], images, tmp_path / "pdfs", []) == ["doc"]
    assert _embedded(tmp_path / "pdfs" / "doc.pdf") == [
        written[2],
        written[0],
        written[1],
    ]


def test_build_is_reproducible(tmp_path: Path) -> None:
    images = tmp_path / "images"
    _pages(images, "doc", 2)
    document = Document("doc", ("page_1.jpg", "page_2.jpg"), "english")
    pdfs.build([document], images, tmp_path / "first", [])
    pdfs.build([document], images, tmp_path / "second", [])
    assert (tmp_path / "first" / "doc.pdf").read_bytes() == (
        tmp_path / "second" / "doc.pdf"
    ).read_bytes()


def test_build_skips_the_missing_and_drops_a_stale_input(tmp_path: Path) -> None:
    images = tmp_path / "images"
    _pages(images, "doc", 1)
    out = tmp_path / "pdfs"
    out.mkdir()
    (out / "other_language.pdf").write_bytes(b"stale")
    documents = [
        Document("doc", ("page_1.jpg",), "english"),
        Document("gone", ("page_1.jpg",), "english"),
    ]
    assert pdfs.build(documents, images, out, ["gone"]) == ["doc"]
    assert sorted(path.name for path in out.iterdir()) == ["doc.pdf"]


def test_build_refuses_a_page_that_fetch_did_not_report(tmp_path: Path) -> None:
    images = tmp_path / "images"
    _pages(images, "doc", 1)
    document = Document("doc", ("page_1.jpg", "page_2.jpg"), "english")
    with pytest.raises(BenchmarkError, match=r"page_2\.jpg"):
        pdfs.build([document], images, tmp_path / "pdfs", [])


# --- convert -------------------------------------------------------------------


def test_raw2md_command_adds_the_llm_stages_only_when_asked(tmp_path: Path) -> None:
    run = RunDir(tmp_path)
    plain = convert.raw2md_command(run, None)
    assert plain[1:] == ["-o", str(run.outputs), "-d", "-s", "-e", "marker"]
    assert convert.raw2md_command(run, "gemini")[-4:] == [
        "-i",
        "gemini",
        "-p",
        "gemini",
    ]


def _built_run(tmp_path: Path, **record: Any) -> RunDir:
    run = RunDir(tmp_path / "run")
    run.pdfs.mkdir(parents=True)
    (run.pdfs / "doc.pdf").write_bytes(b"%PDF")
    dump_yaml(run.record, {"language": "english", **record})
    return run


def _fake_run(returncode: int) -> Any:
    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, returncode)

    return run


def test_convert_adds_a_session_to_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _built_run(tmp_path)
    monkeypatch.setattr("subprocess.run", _fake_run(1))
    monkeypatch.setattr(convert, "gpu_name", lambda: "Test GPU")
    record = convert.convert(run, None)
    assert record["command"] == "raw2md <pdf> -d -s -e marker"
    assert record["gpu"] == "Test GPU"
    assert [session["exit_code"] for session in record["sessions"]] == [1]
    convert.convert(run, None)
    assert len(yaml.safe_load(run.record.read_text(encoding="utf-8"))["sessions"]) == 2


def test_convert_stops_on_an_exit_code_that_converted_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _built_run(tmp_path)
    monkeypatch.setattr("subprocess.run", _fake_run(3))
    with pytest.raises(BenchmarkError, match="missing dependency"):
        convert.convert(run, None)


def test_convert_refuses_a_second_variant_in_one_run(tmp_path: Path) -> None:
    run = _built_run(tmp_path, llm=None, sessions=[{"minutes": 1.0}])
    with pytest.raises(BenchmarkError, match="one variant"):
        convert.convert(run, "gemini")


def test_convert_refuses_a_run_without_inputs(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkError, match="build first"):
        convert.convert(RunDir(tmp_path), None)


# --- score ---------------------------------------------------------------------

# Stands in for the harness: it reads its config, and writes an aggregate that
# depends on the prediction folder, so the engine and the result differ.
_FAKE_SCORER = """
import json, pathlib, sys, yaml
config = yaml.safe_load(open(sys.argv[2], encoding="utf-8"))
folder = pathlib.Path(config["end2end_eval"]["dataset"]["prediction"]["data_path"])
value = 0.5 if folder.name.endswith("result") else 0.25
out = pathlib.Path("result") / folder.name
out.mkdir(parents=True)
print("Time out for plain text match of a.pdf, match_gt2pred_simple will be used.")
json.dump({
    "text_block": {"all": {"Edit_dist": {"edit_whole": value, "ALL_page_avg": 9}}},
    "table": {"all": {"TEDS": {"all": value}}},
}, open(out / "metric_result.json", "w", encoding="utf-8"))
"""


def _scorable(tmp_path: Path) -> tuple[Pins, DataDir, RunDir]:
    pins = _pins(
        metrics={"text_block": ["Edit_dist"], "table": ["TEDS"], "head": ["HeadTEDS"]},
        metrics_off={"figure.FigureF1": "no box"},
    )
    data = DataDir(tmp_path / "data")
    harness = data.harness(pins)
    harness.mkdir(parents=True)
    (harness / "pdf_validation.py").write_text(_FAKE_SCORER, encoding="utf-8")
    _annotation(
        data.annotation(pins),
        [_entry("done", [1, 2]), _entry("failed", [1]), _entry("gone", [1])],
    )
    dump_yaml(data.record, {"missing": ["gone"], "missing_reason": "gated"})
    run = RunDir(tmp_path / "run")
    (run.outputs / "done.debug").mkdir(parents=True)
    (run.outputs / "done.debug" / "conversion.md").write_text(
        "engine\n", encoding="utf-8"
    )
    (run.outputs / "done.md").write_text(_HEADER + "result\n", encoding="utf-8")
    (run.outputs / "failed.debug").mkdir()
    (run.outputs / "failed.debug" / "conversion.md").write_text("x\n", encoding="utf-8")
    dump_yaml(
        run.record,
        {
            "language": "english",
            "raw2md": "0.1.0",
            "command": "raw2md <pdf> -d -s -e marker",
            "llm": None,
            "sessions": [{"minutes": 2.0}, {"minutes": 3.0}],
        },
    )
    return pins, data, run


def test_score_writes_both_columns_over_the_same_documents(tmp_path: Path) -> None:
    pins, data, run = _scorable(tmp_path)
    result = scoring.score(pins, data, run, Path(sys.executable))
    assert result["scores"]["text_block.Edit_dist"] == {"engine": 0.25, "result": 0.5}
    assert result["scores"]["head.HeadTEDS"] == {"engine": "n/a", "result": "n/a"}
    assert result["scores"]["figure.FigureF1"] == {"engine": "n/a", "result": "n/a"}
    documents = result["documents"]
    assert (documents["annotated"], documents["missing"], documents["failed"]) == (
        3,
        1,
        1,
    )
    assert documents["scored"] == 1
    assert documents["pages_scored"] == 2
    assert documents["missing_reason"] == "gated"
    assert documents["failed_list"] == ["failed"]
    assert documents["comparable_with_leaderboard"] is False
    assert result["time"]["conversion_minutes"] == 5.0
    assert any("fell back" in note for note in result["notes"])
    assert yaml.safe_load(run.results.read_text(encoding="utf-8")) == result


def test_score_strips_the_header_of_the_result(tmp_path: Path) -> None:
    pins, data, run = _scorable(tmp_path)
    scoring.score(pins, data, run, Path(sys.executable))
    folder = run.scoring / "result" / "run-result"
    assert (folder / "done.md").read_text(encoding="utf-8") == "result\n"
    assert sorted(path.name for path in folder.iterdir()) == ["done.md"]


def test_score_refuses_cdm_without_the_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pins, data, run = _scorable(tmp_path)
    pins = replace(pins, metrics={**pins.metrics, "display_formula": ["CDM"]})
    monkeypatch.setattr("shutil.which", lambda _name: None)
    with pytest.raises(BenchmarkError, match="skip-metric CDM"):
        scoring.score(pins, data, run, Path(sys.executable))
    result = scoring.score(pins, data, run, Path(sys.executable), ["CDM"])
    assert result["scores"]["display_formula.CDM"] == {"engine": "n/a", "result": "n/a"}
    assert "CDM" not in result["scores"]
    assert "| `display_formula`, CDM ↑ | n/a | n/a |" in report.render([result], pins)


def test_score_counts_the_stub_of_an_interrupted_conversion_as_failed(
    tmp_path: Path,
) -> None:
    pins, data, run = _scorable(tmp_path)
    (run.outputs / "failed.md").write_text(
        _HEADER.replace("status: ok", "status: in_progress"), encoding="utf-8"
    )
    documents = scoring.score(pins, data, run, Path(sys.executable))["documents"]
    assert documents["failed_list"] == ["failed"]
    assert documents["scored"] == 1


def test_score_counts_only_the_documents_a_trial_run_chose(tmp_path: Path) -> None:
    pins, data, run = _scorable(tmp_path)
    record = yaml.safe_load(run.record.read_text(encoding="utf-8"))
    dump_yaml(run.record, {**record, "documents": ["done"]})
    documents = scoring.score(pins, data, run, Path(sys.executable))["documents"]
    assert (documents["annotated"], documents["missing"], documents["failed"]) == (
        1,
        0,
        0,
    )
    assert documents["chosen"] == ["done"]


def test_select_documents_refuses_a_name_outside_the_set() -> None:
    documents = [Document("a", (), "english"), Document("b", (), "english")]
    assert select_documents(documents, None) == documents
    assert [d.name for d in select_documents(documents, ["b"])] == ["b"]
    with pytest.raises(BenchmarkError, match="no document named"):
        select_documents(documents, ["c"])


def test_active_metrics_turns_one_metric_off_per_element() -> None:
    pins = _pins(
        metrics={
            "table": ["TEDS"],
            "table_relation": ["Relation_F1"],
            "text": ["Relation_F1"],
        },
        metrics_off={"table_relation.Relation_F1": "html only"},
    )
    assert scoring.active_metrics(pins) == {"table": ["TEDS"], "text": ["Relation_F1"]}


def test_scorer_config_filters_by_language_only_for_a_subset(tmp_path: Path) -> None:
    def config(language: str, annotation: Path) -> dict[str, Any]:
        return scoring.scorer_config(
            {"table": ["TEDS"]},
            annotation=annotation,
            predictions=tmp_path,
            match_method="m",
            language=language,
        )

    whole = config("all", tmp_path / "a.json")
    assert "filter" not in whole["end2end_eval"]["dataset"]
    english = config("english", tmp_path / "a.json")
    assert english["end2end_eval"]["dataset"]["filter"] == {"language": "english"}
    with pytest.raises(BenchmarkError, match="absolute"):
        config("all", Path("a.json"))


def test_count_llm_requests_reads_the_debug_traffic(tmp_path: Path) -> None:
    trace = tmp_path / "doc.debug" / "llm"
    trace.mkdir(parents=True)
    (trace / "post.txt").write_text(
        "-- request (1)\nbody\n-- request (2)\n", encoding="utf-8"
    )
    documents = [Document("doc", (), "english"), Document("none", (), "english")]
    assert scoring.count_llm_requests(tmp_path, documents) == 2


# --- report and CLI ------------------------------------------------------------


def test_report_prints_one_row_per_metric_with_its_direction(tmp_path: Path) -> None:
    pins, data, run = _scorable(tmp_path)
    result = scoring.score(pins, data, run, Path(sys.executable))
    table = report.render([result], pins)
    assert "1 of 3 documents scored (1 missing, 1 failed)." in table
    assert "| `text_block`, Edit_dist ↓ | 0.250 | 0.500 |" in table
    assert "| `head`, HeadTEDS ↑ | n/a | n/a |" in table


def test_report_puts_each_result_in_its_own_pair_of_columns(tmp_path: Path) -> None:
    pins, data, run = _scorable(tmp_path)
    scored = scoring.score(pins, data, run, Path(sys.executable))
    whole, english = {**scored, "language": "all"}, {**scored, "language": "english"}
    table = report.render([whole, english], pins)
    assert (
        "| Element, metric | Whole set, engine | Whole set, raw2md"
        " | English, engine | English, raw2md |"
    ) in table
    assert "| `text_block`, Edit_dist ↓ | 0.250 | 0.500 | 0.250 | 0.500 |" in table
    assert table.count("documents scored") == 2


def test_cli_report_reads_a_result_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pins, data, run = _scorable(tmp_path)
    scoring.score(pins, data, run, Path(sys.executable))
    assert cli.main(["report", str(run.results)]) == 0
    assert "| Element, metric | Engine | raw2md |" in capsys.readouterr().out


def test_cli_build_asks_for_fetch_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["build", "--data", str(tmp_path / "d"), "--run", str(tmp_path / "r")]
    )
    assert code == 1
    assert "run fetch first" in capsys.readouterr().err


def test_system_name_takes_the_distribution_name_over_the_kernel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "platform.freedesktop_os_release",
        lambda: {"NAME": "Ubuntu", "PRETTY_NAME": "Ubuntu 22.04.5 LTS"},
    )
    monkeypatch.setattr("platform.platform", lambda: "Linux-6.8.0-generic-x86_64")
    assert system_name() == "Ubuntu 22.04.5 LTS"


def test_system_name_falls_back_to_the_platform_without_os_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing() -> dict[str, str]:
        raise OSError("no os-release file")

    monkeypatch.setattr("platform.freedesktop_os_release", missing)
    monkeypatch.setattr("platform.platform", lambda: "Windows-10-10.0.19045-SP0")
    assert system_name() == "Windows-10-10.0.19045-SP0"
