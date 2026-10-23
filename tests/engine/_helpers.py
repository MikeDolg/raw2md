"""A clean import of the engine copy with torch hidden, as in the CI fast layer.

The CI install leaves torch out. `engine_copy` hides it here too, so a test of
the copy passes or fails the same way on a machine that has torch.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import types
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn
from unittest.mock import patch

_ENGINE = "raw2md_engine"
_HIDDEN = ("torch", _ENGINE)

# The `__init__` of each package imports torch for its predictor. The stub
# keeps the real `__path__`, so the submodules, such as `schema`, load from
# disk.
_SURYA_PREDICTORS = {
    "detection": "DetectionPredictor",
    "recognition": "RecognitionPredictor",
    "table_rec": "TableRecPredictor",
}

Loader = Callable[[str], types.ModuleType]


class _TorchBlocker(importlib.abc.MetaPathFinder):
    """Fails each import of torch as an environment without the package does."""

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        if fullname == "torch" or fullname.startswith("torch."):
            msg = f"No module named {fullname!r}"
            raise ModuleNotFoundError(msg, name=fullname)
        return None


class _StubPredictor:
    """Stands in for a model predictor of surya."""

    def __call__(self, *args: object, **kwargs: object) -> NoReturn:
        msg = f"{type(self).__name__} runs a model, which an engine test has not"
        raise AssertionError(msg)


def _is_hidden(name: str) -> bool:
    return any(name == top or name.startswith(top + ".") for top in _HIDDEN)


def _copy_root() -> Path:
    spec = importlib.util.find_spec(_ENGINE)
    if spec is None or not spec.submodule_search_locations:
        msg = f"{_ENGINE} is not installed"
        raise ModuleNotFoundError(msg, name=_ENGINE)
    return Path(next(iter(spec.submodule_search_locations)))


def _register_surya_stubs(root: Path) -> None:
    for package, predictor in _SURYA_PREDICTORS.items():
        name = f"{_ENGINE}.surya.{package}"
        stub = types.ModuleType(name)
        stub.__path__ = [str(root / "surya" / package)]
        stub.__spec__ = importlib.machinery.ModuleSpec(name, None, is_package=True)
        sys.modules[name] = stub
        schema = importlib.import_module(f"{name}.schema")
        for key, value in vars(schema).items():
            if isinstance(value, type) and value.__module__ == schema.__name__:
                setattr(stub, key, value)
        setattr(stub, predictor, type(predictor, (_StubPredictor,), {}))


@contextmanager
def engine_copy() -> Iterator[Loader]:
    """Yield a loader of `raw2md_engine.<name>` modules without torch.

    Every module of the copy imports afresh inside the block. On exit, the
    modules of the copy and of torch and the import finders are as they were
    before. Other modules stay loaded: a C extension cannot load twice.
    """
    root = _copy_root()
    saved = {n: m for n, m in sys.modules.items() if _is_hidden(n)}
    with patch.object(sys, "meta_path", [_TorchBlocker(), *sys.meta_path]):
        try:
            for name in saved:
                del sys.modules[name]
            _register_surya_stubs(root)
            yield lambda name: importlib.import_module(f"{_ENGINE}.{name}")
        finally:
            for name in [n for n in sys.modules if _is_hidden(n)]:
                del sys.modules[name]
            sys.modules.update(saved)
