"""Tests for the `init` subcommand: the ~/.raw2md service file creator."""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from raw2md.engines import weights
from raw2md.init import run_init_command
from raw2md.keywords import default_keywords_text
from raw2md.paths import keywords_file, models_dir, prompts_file, settings_file
from raw2md.prompts import default_prompts_text
from raw2md.settings import default_settings_text


@pytest.fixture(autouse=True)
def fetched(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Replace the download with a recorder; the tests never reach the network."""
    calls: list[tuple[str, ...]] = []

    def fake_fetch(weights_dir: Path, names: Sequence[str]) -> None:
        calls.append(tuple(names))

    monkeypatch.setattr(weights, "fetch", fake_fetch)
    return calls


# --- Creating what is missing ------------------------------------------------


def test_creates_every_missing_file(home: Path) -> None:
    assert run_init_command([]) == 0
    assert settings_file().read_text(encoding="utf-8") == default_settings_text()
    assert prompts_file().read_text(encoding="utf-8") == default_prompts_text()
    assert keywords_file().read_text(encoding="utf-8") == default_keywords_text()


def test_writes_the_request_window(home: Path) -> None:
    run_init_command([])
    written = json.loads(settings_file().read_text(encoding="utf-8"))
    gemini = written["models"]["gemini_api"]
    assert gemini["pages_per_request"] == 8
    assert gemini["max_request_bytes"] == 20971520


def test_writes_the_cli_timeout(home: Path) -> None:
    run_init_command([])
    written = json.loads(settings_file().read_text(encoding="utf-8"))
    assert written["models"]["claude_cli"]["cli_timeout_s"] == 120


def test_does_not_overwrite_settings(home: Path) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("sentinel", encoding="utf-8")
    assert run_init_command([]) == 0
    assert path.read_text(encoding="utf-8") == "sentinel"


def test_does_not_overwrite_prompts(home: Path) -> None:
    path = prompts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("sentinel", encoding="utf-8")
    assert run_init_command([]) == 0
    assert path.read_text(encoding="utf-8") == "sentinel"


def test_does_not_overwrite_keywords(home: Path) -> None:
    path = keywords_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("sentinel", encoding="utf-8")
    assert run_init_command([]) == 0
    assert path.read_text(encoding="utf-8") == "sentinel"


def test_keeps_the_comments_of_the_shipped_dictionary(home: Path) -> None:
    # A byte-for-byte copy keeps the section comments.
    run_init_command([])
    assert "#" in keywords_file().read_text(encoding="utf-8")


def test_creates_only_the_missing_file(home: Path) -> None:
    # init restores the missing file and leaves the existing one untouched.
    settings_file().parent.mkdir(parents=True, exist_ok=True)
    settings_file().write_text("sentinel", encoding="utf-8")
    assert run_init_command([]) == 0
    assert settings_file().read_text(encoding="utf-8") == "sentinel"
    assert prompts_file().read_text(encoding="utf-8") == default_prompts_text()


def test_reports_created_and_existing_files(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings_file().parent.mkdir(parents=True, exist_ok=True)
    settings_file().write_text("sentinel", encoding="utf-8")
    run_init_command([])
    captured = capsys.readouterr()
    assert str(prompts_file()) in captured.out
    assert f"{settings_file()} already exists" in captured.err


# --- Model-key arguments ------------------------------------------------------


def test_filters_models_and_operations(home: Path) -> None:
    run_init_command(["claude_cli"])
    written = json.loads(settings_file().read_text(encoding="utf-8"))
    assert set(written["models"]) == {"claude_cli"}
    assert written["operations"]["post"]["allowed"] == ["claude_cli"]
    assert written["operations"]["ocr"]["allowed"] == []
    assert written["operations"]["inspection"]["allowed"] == []


def test_no_arguments_keeps_every_shipped_model(home: Path) -> None:
    run_init_command([])
    written = json.loads(settings_file().read_text(encoding="utf-8"))
    assert set(written["models"]) == {"gemini_api", "claude_cli"}


def test_rejects_an_unknown_model_key(home: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_init_command(["not-a-real-model"])
    assert exc_info.value.code == 2


def test_arguments_have_no_effect_on_an_existing_settings_file(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("sentinel", encoding="utf-8")
    assert run_init_command(["gemini_api"]) == 0
    assert path.read_text(encoding="utf-8") == "sentinel"
    assert "were not applied" in capsys.readouterr().err


def test_no_arguments_note_without_model_keys(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("sentinel", encoding="utf-8")
    run_init_command([])
    assert "were not applied" not in capsys.readouterr().err


# --- Vision-gap warning --------------------------------------------------------


def test_warns_when_chosen_models_have_no_vision(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_init_command(["claude_cli"])
    stderr = capsys.readouterr().err
    assert "ocr" in stderr
    assert "inspection" in stderr


def test_no_vision_warning_with_a_vision_model(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_init_command(["gemini_api"])
    assert "no chosen model has vision" not in capsys.readouterr().err


def test_no_vision_warning_without_model_arguments(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_init_command([])
    assert "no chosen model has vision" not in capsys.readouterr().err


# --- Weights ------------------------------------------------------------------


def _stamp_complete_weights() -> None:
    folder = models_dir()
    for name in weights.FILES:
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    (folder / weights.STAMP_NAME).write_text(weights.REVISION, encoding="utf-8")


def test_downloads_the_missing_weights(
    home: Path, fetched: list[tuple[str, ...]]
) -> None:
    assert run_init_command([]) == 0
    assert fetched == [weights.FILES]


def test_downloads_only_the_missing_files(
    home: Path, fetched: list[tuple[str, ...]]
) -> None:
    _stamp_complete_weights()
    (models_dir() / weights.FILES[1]).unlink()
    assert run_init_command([]) == 0
    assert fetched == [(weights.FILES[1],)]


def test_complete_weights_make_no_download(
    home: Path, fetched: list[tuple[str, ...]], capsys: pytest.CaptureFixture[str]
) -> None:
    _stamp_complete_weights()
    assert run_init_command([]) == 0
    assert fetched == []
    assert "weights are in place" in capsys.readouterr().out


def test_failed_download_fails_init_and_keeps_the_service_files(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing_fetch(weights_dir: Path, names: Sequence[str]) -> None:
        raise weights.WeightsError("cannot download the engine weights")

    monkeypatch.setattr(weights, "fetch", failing_fetch)
    assert run_init_command([]) == 1
    assert settings_file().read_text(encoding="utf-8") == default_settings_text()
    assert prompts_file().is_file()
    assert keywords_file().is_file()
    assert "cannot download the engine weights" in capsys.readouterr().err
