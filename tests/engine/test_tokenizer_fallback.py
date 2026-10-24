"""The tokenizer builds from a flat list of special tokens, or from none."""

from __future__ import annotations

import importlib.machinery
import sys
import types
from pathlib import Path

import pytest
import transformers  # noqa: F401  # loads before the fixture hides torch

from ._helpers import Loader


@pytest.fixture
def tokenizer_class(engine: Loader) -> type:
    # The `__init__` of each package builds torch objects. A stub keeps the
    # real `__path__`, so the tokenizer and its schema load from disk.
    surya_file = engine("surya").__file__
    assert surya_file is not None
    # The settings module reads the device from torch; the tokenizer needs two
    # plain values.
    settings = types.ModuleType("raw2md_engine.surya.settings")
    settings.settings = types.SimpleNamespace(  # type: ignore[attr-defined]
        LOGLEVEL="WARNING", MODEL_DIR=None, FOUNDATION_MODEL_CHECKPOINT=""
    )
    sys.modules[settings.__name__] = settings
    root = Path(surya_file).parent / "common" / "surya"
    for name, path in (
        ("raw2md_engine.surya.common.surya", root),
        ("raw2md_engine.surya.common.surya.processor", root / "processor"),
    ):
        package = types.ModuleType(name)
        package.__path__ = [str(path)]
        package.__spec__ = importlib.machinery.ModuleSpec(name, None, is_package=True)
        sys.modules[name] = package
    module = engine("surya.common.surya.processor.tokenizer")
    tokenizer: type = module.GreedyMathUTF16Tokenizer
    return tokenizer


def test_flat_list_gets_consecutive_ids(tokenizer_class: type) -> None:
    tokenizer = tokenizer_class(
        math_vocab={"\\frac": 0}, special_tokens=["<a>", "<b>"], debug=False
    )

    assert tokenizer.special_to_absid == {"<a>": 65537, "<b>": 65538}
    assert tokenizer.LAYOUT_LABEL2ID == {}
    assert tokenizer.TABLE_STRUCTURE_LABEL2ID == {}


def test_no_special_tokens_gives_an_empty_table(tokenizer_class: type) -> None:
    tokenizer = tokenizer_class(math_vocab={"\\frac": 0})

    assert tokenizer.special_to_absid == {}
    assert tokenizer.specials_pattern is None
