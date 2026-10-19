"""Tests for the engine weights: the disk check and the pinned download."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
from huggingface_hub._local_folder import write_download_metadata
from huggingface_hub.errors import HfHubHTTPError
from huggingface_hub.utils import httpx  # type: ignore[attr-defined]  # lazy export

from raw2md import paths
from raw2md.engines import weights

_SURYA_SETTINGS = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "raw2md_engine"
    / "surya"
    / "settings.py"
)


class FakeHub:
    """Stands in for `huggingface_hub.hf_hub_download` and records each call.

    A call writes the file into `local_dir`, as the real download does.
    `error` is raised instead, after the files before it arrived.
    """

    def __init__(
        self,
        error: Exception | None = None,
        fail_at: int = 0,
        commit_hash: str | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._error = error
        self._fail_at = fail_at
        self._commit_hash = commit_hash

    def __call__(self, repo_id: str, filename: str, **kwargs: Any) -> str:
        if self._error is not None and len(self.calls) == self._fail_at:
            raise self._error
        self.calls.append({"repo_id": repo_id, "filename": filename, **kwargs})
        target = Path(kwargs["local_dir"]) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"weights")
        write_download_metadata(
            local_dir=Path(kwargs["local_dir"]),
            filename=filename,
            commit_hash=self._commit_hash or kwargs["revision"],
            etag="etag",
        )
        return str(target)

    @property
    def filenames(self) -> list[str]:
        return [call["filename"] for call in self.calls]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> FakeHub:
        monkeypatch.setattr("huggingface_hub.hf_hub_download", self)
        return self


def fill_weights(weights_dir: Path, *, stamp: str | None = weights.REVISION) -> None:
    """Lay out every weights file, and the stamp unless it is None."""
    for name in weights.FILES:
        target = weights_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"weights")
    if stamp is not None:
        (weights_dir / weights.STAMP_NAME).write_text(stamp + "\n", encoding="utf-8")


def test_the_revision_is_a_full_commit_hash() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", weights.REVISION)


def test_the_folder_is_under_the_service_directory(home: Path) -> None:
    assert paths.models_dir() == home / ".raw2md" / "models"


def test_every_engine_checkpoint_has_its_files() -> None:
    tree = ast.parse(_SURYA_SETTINGS.read_text(encoding="utf-8"))
    checkpoints = {
        node.value.removeprefix("s3://")
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("s3://")
    }
    assert checkpoints
    for checkpoint in checkpoints:
        task, date = checkpoint.split("/")
        for name in ("manifest.json", "config.json", "model.safetensors"):
            assert f"{task}/surya-{date}/{name}" in weights.FILES


def test_the_files_are_unique() -> None:
    assert len(set(weights.FILES)) == len(weights.FILES)


def test_a_complete_folder_needs_nothing(home: Path) -> None:
    fill_weights(paths.models_dir())
    assert weights.missing_files(paths.models_dir()) == ()


def test_an_empty_home_needs_every_file(home: Path) -> None:
    assert weights.missing_files(paths.models_dir()) == weights.FILES


def test_only_the_missing_files_are_listed(home: Path) -> None:
    weights_dir = paths.models_dir()
    fill_weights(weights_dir)
    gone = (weights.FILES[3], weights.FILES[-1])
    for name in gone:
        (weights_dir / name).unlink()
    assert weights.missing_files(weights_dir) == gone


@pytest.mark.parametrize("stamp", [None, "0" * 40])
def test_a_folder_without_the_pinned_stamp_needs_every_file(
    home: Path, stamp: str | None
) -> None:
    fill_weights(paths.models_dir(), stamp=stamp)
    assert weights.missing_files(paths.models_dir()) == weights.FILES


def test_fetch_downloads_only_the_named_files_at_the_pinned_revision(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights_dir = paths.models_dir()
    fill_weights(weights_dir)
    gone = (weights.FILES[0], weights.FILES[5])
    for name in gone:
        (weights_dir / name).unlink()
    hub = FakeHub().install(monkeypatch)

    weights.fetch(weights_dir, weights.missing_files(weights_dir))

    assert hub.filenames == list(gone)
    for call in hub.calls:
        assert call["repo_id"] == weights.REPO_ID
        assert call["revision"] == weights.REVISION
        assert Path(call["local_dir"]) == weights_dir
    assert weights.missing_files(weights_dir) == ()


def test_fetch_restamps_a_folder_of_another_revision(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights_dir = paths.models_dir()
    fill_weights(weights_dir, stamp="0" * 40)
    hub = FakeHub().install(monkeypatch)

    weights.fetch(weights_dir, weights.missing_files(weights_dir))

    assert hub.filenames == list(weights.FILES)
    assert weights.stamp_revision(weights_dir) == weights.REVISION


def test_fetch_into_a_home_with_cyrillic_in_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "дом пользователя")
    weights_dir = paths.models_dir()
    FakeHub().install(monkeypatch)

    weights.fetch(weights_dir, weights.missing_files(weights_dir))

    assert weights.missing_files(weights_dir) == ()
    assert (weights_dir / weights.FILES[-1]).is_file()


def test_a_file_of_another_revision_is_not_stamped(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights_dir = paths.models_dir()
    FakeHub(commit_hash="0" * 40).install(monkeypatch)

    with pytest.raises(weights.WeightsError, match="cannot confirm"):
        weights.fetch(weights_dir, weights.FILES)

    assert weights.stamp_revision(weights_dir) is None


@pytest.mark.parametrize(
    "error",
    [
        HfHubHTTPError(
            "404 Client Error",
            response=httpx.Response(
                404, request=httpx.Request("GET", "https://hub.invalid/file")
            ),
        ),
        httpx.ReadError("Connection reset by peer"),
        OSError("No space left"),
        RuntimeError("Data processing error"),
    ],
)
def test_a_failed_download_raises_and_leaves_no_stamp(
    home: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    weights_dir = paths.models_dir()
    FakeHub(error=error, fail_at=2).install(monkeypatch)

    with pytest.raises(weights.WeightsError, match=weights.REPO_ID):
        weights.fetch(weights_dir, weights.FILES)

    assert weights.stamp_revision(weights_dir) is None
    # Without the stamp the next check asks for every file again; the real
    # download skips the files that arrived by their checksum.
    assert (weights_dir / weights.FILES[0]).is_file()
    assert weights.missing_files(weights_dir) == weights.FILES
