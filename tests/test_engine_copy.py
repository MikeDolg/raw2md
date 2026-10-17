"""Checks on the bundled engine copy `src/raw2md_engine`."""

import ast
from pathlib import Path

_COPY = Path(__file__).resolve().parent.parent / "src" / "raw2md_engine"

_UPSTREAM_NAMES = frozenset({"marker", "surya", "pdftext"})


def _top_level_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """Return the line and top-level module of each absolute import."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, a.name.split(".")[0]) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module.split(".")[0]))
    return found


def test_copy_has_python_files() -> None:
    assert any(_COPY.rglob("*.py"))


def test_copy_imports_no_upstream_package() -> None:
    offenders = []
    for path in sorted(_COPY.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, top in _top_level_imports(tree):
            if top in _UPSTREAM_NAMES:
                offenders.append(f"{path.relative_to(_COPY)}:{line}")
    assert not offenders, offenders
