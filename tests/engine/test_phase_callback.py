"""The PDF converter names each of its steps to a phase callback."""

from __future__ import annotations

import types
from types import SimpleNamespace
from typing import Any

import pytest

from ._helpers import Loader


def _converter(
    module: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    processors: int,
) -> Any:
    """A converter whose builders, processors, and renderer only record a call."""
    converter = module.PdfConverter(artifact_dict={}, processor_list=[])

    def provider(filepath: str, config: object) -> str:
        events.append("provider")
        return filepath

    def document_builder(config: object) -> Any:
        def build(*builders: object) -> SimpleNamespace:
            events.append("document")
            return SimpleNamespace(pages=[])

        return build

    def record(event: str, result: object = None) -> Any:
        def call(document: object) -> object:
            events.append(event)
            return result

        return call

    monkeypatch.setattr(module, "PdfProvider", provider)
    monkeypatch.setattr(module, "DocumentBuilder", document_builder)
    resolved = {
        module.LayoutBuilder: object(),
        module.LineBuilder: object(),
        module.OcrBuilder: object(),
        module.StructureBuilder: record("structure built"),
        converter.renderer: record("rendered", "output"),
    }
    monkeypatch.setattr(converter, "resolve_dependencies", resolved.__getitem__)
    converter.processor_list = [
        record(f"processor {index}") for index in range(1, processors + 1)
    ]
    return converter


def test_callback_receives_each_step_before_it_runs(
    engine: Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = engine("marker.converters.pdf")
    events: list[str] = []
    converter = _converter(module, monkeypatch, events, processors=2)
    converter.phase_callback = lambda phase: events.append(f"phase {phase}")

    assert converter("doc.pdf") == "output"

    assert events == [
        "phase pages",
        "provider",
        "document",
        "phase structure",
        "structure built",
        "phase processors 1/2",
        "processor 1",
        "phase processors 2/2",
        "processor 2",
        "phase rendering",
        "rendered",
    ]


def test_converter_without_callback_runs_the_same_steps(
    engine: Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = engine("marker.converters.pdf")
    events: list[str] = []
    converter = _converter(module, monkeypatch, events, processors=2)

    assert converter.phase_callback is None
    assert converter("doc.pdf") == "output"
    assert events == [
        "provider",
        "document",
        "structure built",
        "processor 1",
        "processor 2",
        "rendered",
    ]


def test_callback_error_stops_the_conversion(
    engine: Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = engine("marker.converters.pdf")
    events: list[str] = []
    converter = _converter(module, monkeypatch, events, processors=1)

    def fail(phase: str) -> None:
        raise RuntimeError(phase)

    converter.phase_callback = fail

    with pytest.raises(RuntimeError, match="pages"):
        converter("doc.pdf")
    assert events == []
