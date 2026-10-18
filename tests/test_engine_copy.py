"""Checks on the bundled engine copy `src/raw2md_engine`."""

import ast
from pathlib import Path
from typing import TypeGuard

import pytest

_COPY = Path(__file__).resolve().parent.parent / "src" / "raw2md_engine"

_UPSTREAM_NAMES = frozenset({"marker", "surya", "pdftext"})

# The packages that load settings from the environment and from `local.env`.
_SETTINGS_LOADERS = frozenset({"pydantic_settings", "dotenv"})

# raw2md downloads the weights; the copy only reads them from disk.
_NETWORK_CLIENTS = frozenset({"requests", "httpx", "urllib3", "huggingface_hub"})

_ENVIRONMENT_NAMES = frozenset({"environ", "environb", "getenv", "getenvb"})

# The copy sets these variables for its libraries and reads none of them.
_WRITABLE_VARIABLES = frozenset(
    {"PYTORCH_ENABLE_MPS_FALLBACK", "TOKENIZERS_PARALLELISM"}
)


def _top_level_imports(tree: ast.Module) -> list[tuple[int, str]]:
    """Return the line and top-level module of each absolute import."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, a.name.split(".")[0]) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module.split(".")[0]))
    return found


def _allowed_writes(tree: ast.Module) -> set[int]:
    """Return the ids of `os.environ` nodes that only set an allowed variable."""
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value in _WRITABLE_VARIABLES
            ):
                allowed.add(id(target.value))
    return allowed


def _environment_reads(tree: ast.Module) -> list[int]:
    """Return the lines that load settings or touch the environment.

    A plain `os.environ[NAME] = value` for an allowed name is not a read.
    """
    allowed = _allowed_writes(tree)
    lines = [line for line, top in _top_level_imports(tree) if top in _SETTINGS_LOADERS]
    lines.extend(
        node.lineno
        for node in ast.walk(tree)
        if _touches_environment(node) and id(node) not in allowed
    )
    return sorted(lines)


def _touches_environment(
    node: ast.AST,
) -> TypeGuard[ast.Attribute | ast.ImportFrom]:
    """True for `os.environ`, `os.getenv`, and their import from `os`."""
    if isinstance(node, ast.Attribute):
        return (
            isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in _ENVIRONMENT_NAMES
        )
    if isinstance(node, ast.ImportFrom):
        return node.module == "os" and any(
            a.name in _ENVIRONMENT_NAMES for a in node.names
        )
    return False


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


def test_copy_imports_no_network_client() -> None:
    offenders = []
    for path in sorted(_COPY.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, top in _top_level_imports(tree):
            if top in _NETWORK_CLIENTS:
                offenders.append(f"{path.relative_to(_COPY)}:{line}")
    assert not offenders, offenders


def test_copy_reads_no_environment() -> None:
    offenders: list[str] = []
    for path in sorted(_COPY.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders.extend(
            f"{path.relative_to(_COPY)}:{line}" for line in _environment_reads(tree)
        )
    assert not offenders, offenders


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('os.environ["TOKENIZERS_PARALLELISM"] = "false"', []),
        ('os.environ["TORCH_DEVICE"] = "cpu"', [1]),
        ('device = os.environ["TORCH_DEVICE"]', [1]),
        ('device = os.environ.get("TORCH_DEVICE")', [1]),
        ('device = os.getenv("TORCH_DEVICE")', [1]),
        ("from os import environ", [1]),
        ("from pydantic_settings import BaseSettings", [1]),
        ("from dotenv import find_dotenv", [1]),
    ],
)
def test_environment_reads_finds_each_form(source: str, expected: list[int]) -> None:
    assert _environment_reads(ast.parse(source)) == expected
