"""The engine copy holds no processor that only a switch can enable."""

from __future__ import annotations

from pathlib import Path

import pytest

import raw2md_engine

_MARKER = Path(raw2md_engine.__file__).parent / "marker"


@pytest.mark.parametrize("module", ["line_merge", "blank_page", "block_relabel"])
def test_removed_processor_module_is_gone(module: str) -> None:
    assert not (_MARKER / "processors" / f"{module}.py").exists()


@pytest.mark.parametrize(
    "name", ["LineMergeProcessor", "BlankPageProcessor", "BlockRelabelProcessor"]
)
def test_converter_does_not_name_a_removed_processor(name: str) -> None:
    source = (_MARKER / "converters" / "pdf.py").read_text(encoding="utf-8")
    assert name not in source
