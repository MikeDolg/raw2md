"""Each transformers module that the engine copy imports exists in transformers.

A minor release of transformers 5 removes a module now and then. The copy
then fails only when it loads a model, which the fast layer never does, so
this test reads the imports from the source instead.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

_PACKAGE = "transformers"


def _copy_root() -> Path:
    spec = importlib.util.find_spec("raw2md_engine")
    assert spec is not None
    assert spec.submodule_search_locations
    return Path(next(iter(spec.submodule_search_locations)))


def _imported_modules(root: Path) -> set[str]:
    modules: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            modules.update(
                name
                for name in names
                if name == _PACKAGE or name.startswith(_PACKAGE + ".")
            )
    return modules


def test_engine_copy_imports_existing_transformers_modules() -> None:
    modules = _imported_modules(_copy_root())
    assert _PACKAGE in modules
    missing = sorted(name for name in modules if importlib.util.find_spec(name) is None)
    assert missing == []
