"""A run without LLM options opens no network connection."""

from __future__ import annotations

import io
import socket
import subprocess
from pathlib import Path

import pytest
from conftest import make_run_config
from test_engines import _install_fake_engine, _make_fake_engine, _make_pdf

from raw2md import paths
from raw2md.engines import BundledEngine, ConvertOptions, EngineRegistry, PandocEngine
from raw2md.pipeline import FileResult, Outcome, RunContext, process_file
from raw2md.queue import QueueItem


class NetworkAttemptError(AssertionError):
    """Raised when code under test tries to open a connection."""


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(self: socket.socket, address: object) -> None:
        raise NetworkAttemptError(f"connect to {address!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)


def _run(source: Path, registry: EngineRegistry) -> FileResult:
    context = RunContext(
        config=make_run_config(source),
        registry=registry,
        log_stream=None,
        progress_stream=io.StringIO(),
    )
    return process_file(QueueItem(source=source, include_extension=False), context)


@pytest.mark.usefixtures("no_network")
def test_the_guard_refuses_a_connection() -> None:
    with pytest.raises(NetworkAttemptError), socket.socket() as sock:
        sock.connect(("127.0.0.1", 9))


@pytest.mark.usefixtures("no_network")
def test_docx_conversion_opens_no_connection(tmp_path: Path) -> None:
    if not PandocEngine().available():
        pytest.skip("pandoc is not available")
    draft = tmp_path / "draft.md"
    draft.write_text("# Heading\n\nA plain paragraph.\n", encoding="utf-8")
    source = tmp_path / "doc.docx"
    subprocess.run(
        ["pandoc", str(draft), "--output", str(source)], check=True
    )  # pandoc is a local tool; the fixture only builds the input

    result = _run(source, EngineRegistry([PandocEngine()]))

    assert result.outcome is Outcome.OK
    assert "A plain paragraph." in (tmp_path / "doc.md").read_text(encoding="utf-8")


@pytest.mark.usefixtures("no_network")
def test_pdf_conversion_opens_no_connection(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf(source, pages=2, text="A plain paragraph of invented text.")
    fake = _make_fake_engine(body="A plain paragraph of invented text.\n")

    with _install_fake_engine(fake):
        result = _run(source, EngineRegistry([BundledEngine(tmp_path)]))

    assert result.outcome is Outcome.OK
    assert (tmp_path / "doc.md").is_file()


def test_engine_models_load_with_a_device_and_the_weights_folder(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.pdf"
    _make_pdf(source, pages=1, text="Invented text.")
    fake = _make_fake_engine()

    with _install_fake_engine(fake):
        BundledEngine(tmp_path, cuda=False).convert(
            source, tmp_path / "doc", ConvertOptions()
        )

    fake.create_model_dict.assert_called_once_with(
        device="cpu", weights_dir=str(paths.models_dir())
    )
