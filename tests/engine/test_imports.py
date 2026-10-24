"""The engine copy modules that the tests reach import without torch."""

from __future__ import annotations

import importlib
import sys

import pytest

from ._helpers import Loader, engine_copy

_TORCH_FREE = (
    "marker.settings",
    "marker.renderers",
    "marker.renderers.markdown",
    "marker.schema.text.line",
    "marker.schema.text.span",
    "marker.schema.blocks.sectionheader",
    "marker.processors.ignoretext",
    "marker.processors.list",
    "marker.processors.sectionheader",
    "pdftext.extraction",
    "pdftext.tables",
    "pdftext.pdf.links",
)


@pytest.mark.parametrize("name", _TORCH_FREE)
def test_module_imports_without_torch(engine: Loader, name: str) -> None:
    engine(name)


def test_table_processor_imports_with_surya_stubs(engine: Loader) -> None:
    table = engine("marker.processors.table")
    detection = engine("surya.detection")
    assert table.DetectionPredictor is detection.DetectionPredictor
    with pytest.raises(AssertionError, match="runs a model"):
        detection.DetectionPredictor()()


def test_surya_stub_exposes_the_real_schema(engine: Loader) -> None:
    recognition = engine("surya.recognition")
    schema = engine("surya.recognition.schema")
    assert recognition.TextLine is schema.TextLine


def test_torch_is_hidden(engine: Loader) -> None:
    with pytest.raises(ModuleNotFoundError, match="torch"):
        importlib.import_module("torch")
    settings = engine("marker.settings").settings
    with pytest.raises(ModuleNotFoundError, match="torch"):
        _ = settings.TORCH_DEVICE_MODEL


def test_block_restores_the_modules_and_finders() -> None:
    modules = dict(sys.modules)
    finders = list(sys.meta_path)
    with engine_copy() as load:
        load("marker.processors.table")
    assert all(sys.modules.get(name) is module for name, module in modules.items())
    added = sys.modules.keys() - modules
    assert not [n for n in added if n.split(".")[0] in {"raw2md_engine", "torch"}]
    assert sys.meta_path == finders
