"""Checks on the bundled engine copy `src/raw2md_engine`."""

import ast
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypeGuard

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
_COPY = _SRC / "raw2md_engine"

# The modules of raw2md that the copy may import: text tests over a string,
# which the cleaning reads too, so that both stages share one definition.
_TEXT_TEST_MODULES = frozenset({"raw2md.mdtext.seams", "raw2md.mdtext.tables"})

# A text test module reaches, directly or through another module, only the
# standard library, these packages, and the text primitives of raw2md.
_TEXT_TEST_PACKAGES = frozenset({"regex"})
_TEXT_PRIMITIVES = "raw2md.mdtext"

_UPSTREAM_NAMES = frozenset({"marker", "surya", "pdftext"})

# The packages that load settings from the environment and from `local.env`.
_SETTINGS_LOADERS = frozenset({"pydantic_settings", "dotenv"})

# raw2md downloads the weights; the copy only reads them from disk.
_NETWORK_CLIENTS = frozenset(
    {"requests", "httpx", "httpx2", "urllib3", "huggingface_hub"}
)

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


def _module_file(name: str) -> Path | None:
    """Return the source file of module `name` under `src/`, if there is one."""
    base = _SRC.joinpath(*name.split("."))
    for path in (base.with_suffix(".py"), base / "__init__.py"):
        if path.is_file():
            return path
    return None


def _package_of(path: Path) -> str:
    # The package of `pkg/__init__.py` and of `pkg/mod.py` is `pkg` alike.
    return ".".join(path.relative_to(_SRC).parts[:-1])


def _imported_modules(tree: ast.Module, package: str) -> list[tuple[int, str]]:
    """Return the line and the full name of each module that `tree` imports.

    `from M import x` names `M.x` when that is a module under `src/`, else `M`.
    A relative import resolves against `package`.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                parent = parts[: len(parts) - node.level + 1]
                base = ".".join([*parent, base] if base else parent)
            for alias in node.names:
                sub = f"{base}.{alias.name}"
                found.append((node.lineno, sub if _module_file(sub) else base))
    return found


def _is_raw2md(name: str) -> bool:
    return name == "raw2md" or name.startswith("raw2md.")


def _text_test_may_import(name: str) -> bool:
    top = name.split(".", maxsplit=1)[0]
    return (
        top in sys.stdlib_module_names
        or top in _TEXT_TEST_PACKAGES
        or name in {"raw2md", _TEXT_PRIMITIVES}
        or name.startswith(_TEXT_PRIMITIVES + ".")
    )


def _with_parents(name: str) -> list[str]:
    """Return `name` and each package that importing it imports first."""
    parts = name.split(".")
    return [".".join(parts[: n + 1]) for n in range(len(parts))]


def _text_test_offenders(start: Iterable[str]) -> list[str]:
    """Return each import outside the allowed set that `start` reaches in raw2md."""
    offenders: list[str] = []
    queue = [parent for name in start for parent in _with_parents(name)]
    seen: set[str] = set()
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        path = _module_file(module)
        if path is None:
            offenders.append(f"{module}: no source file")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, name in _imported_modules(tree, _package_of(path)):
            if not _text_test_may_import(name):
                offenders.append(f"{module}:{line} {name}")
            elif _is_raw2md(name):
                queue.extend(_with_parents(name))
    return sorted(offenders)


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


def test_copy_imports_only_text_tests_of_raw2md() -> None:
    offenders = []
    for path in sorted(_COPY.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, name in _imported_modules(tree, _package_of(path)):
            if _is_raw2md(name) and name not in _TEXT_TEST_MODULES:
                offenders.append(f"{path.relative_to(_COPY)}:{line} {name}")
    assert not offenders, offenders


def test_text_tests_reach_no_engine_or_model() -> None:
    assert _text_test_offenders(_TEXT_TEST_MODULES) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import re", []),
        ("import regex", []),
        ("from __future__ import annotations", []),
        ("from raw2md.mdtext.zones import blank_match", []),
        ("from raw2md.mdtext import zones", []),
        ("import torch", ["torch"]),
        ("import surya", ["surya"]),
        ("from transformers import AutoModel", ["transformers"]),
        ("from raw2md_engine.marker.util import x", ["raw2md_engine.marker.util"]),
        ("from raw2md import keywords", ["raw2md.keywords"]),
        ("import yaml", ["yaml"]),
    ],
)
def test_text_test_import_rule_names_each_offender(
    source: str, expected: list[str]
) -> None:
    names = [n for _, n in _imported_modules(ast.parse(source), "raw2md.mdtext")]
    assert [n for n in names if not _text_test_may_import(n)] == expected


def test_relative_import_resolves_against_the_package() -> None:
    tree = ast.parse("from . import zones\nfrom ..cleaning import prose")
    assert _imported_modules(tree, "raw2md.mdtext") == [
        (1, "raw2md.mdtext.zones"),
        (2, "raw2md.cleaning.prose"),
    ]


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


def _torch() -> Any:
    # The CI install of the fast layer leaves torch out.
    return pytest.importorskip("torch", reason="torch is not installed")


def _buffer_builders() -> dict[str, Callable[[], Any]]:
    """Return a small instance of each module that owns a non-persistent buffer."""
    from raw2md_engine.surya.common.adetr.decoder import SuryaADETRDecoderModel
    from raw2md_engine.surya.common.surya.decoder import Qwen2RotaryEmbedding
    from raw2md_engine.surya.common.surya.decoder.config import SuryaDecoderConfig
    from raw2md_engine.surya.ocr_error.model.config import DistilBertConfig
    from raw2md_engine.surya.ocr_error.model.encoder import Embeddings
    from raw2md_engine.surya.table_rec.model.config import SuryaTableRecDecoderConfig

    table_config = SuryaTableRecDecoderConfig(
        num_hidden_layers=1,
        hidden_size=16,
        intermediate_size=32,
        encoder_hidden_size=16,
        num_attention_heads=2,
        num_key_value_heads=1,
    )
    text_config = SuryaDecoderConfig(
        hidden_size=16, num_attention_heads=2, max_position_embeddings=64
    )
    ocr_config = DistilBertConfig(vocab_size=10, dim=8, max_position_embeddings=16)
    return {
        "table decoder": lambda: SuryaADETRDecoderModel(table_config),
        "text rotary": lambda: Qwen2RotaryEmbedding(text_config),
        "ocr embeddings": lambda: Embeddings(ocr_config),
    }


def _non_persistent(model: Any) -> dict[str, tuple[Any, str]]:
    found = {}
    for prefix, module in model.named_modules():
        for name in module._non_persistent_buffers_set:
            found[f"{prefix}.{name}"] = (module, name)
    return found


@pytest.mark.parametrize("damage", ["garbage", "meta"])
@pytest.mark.parametrize("name", ["table decoder", "text rotary", "ocr embeddings"])
def test_restore_rebuilds_buffers(name: str, damage: str) -> None:
    torch = _torch()
    from raw2md_engine.surya.common.load import restore_buffers

    model = _buffer_builders()[name]()
    owners = _non_persistent(model)
    assert owners
    expected = {key: getattr(m, n).clone() for key, (m, n) in owners.items()}
    for module, buffer_name in owners.values():
        buffer = getattr(module, buffer_name)
        if damage == "garbage":
            broken = torch.full_like(buffer, 7)
        else:
            broken = torch.empty_like(buffer, device="meta")
        setattr(module, buffer_name, broken)
        if hasattr(module, "original_inv_freq"):
            module.original_inv_freq = broken

    restore_buffers(model)

    for key, (module, buffer_name) in owners.items():
        buffer = getattr(module, buffer_name)
        assert buffer.device.type == "cpu", key
        assert buffer.dtype == expected[key].dtype, key
        assert torch.equal(buffer, expected[key]), key
        if hasattr(module, "original_inv_freq"):
            assert module.original_inv_freq is buffer, key


def test_vision_rotary_builds_on_cpu_under_meta() -> None:
    torch = _torch()
    from raw2md_engine.surya.common.surya.encoder import (
        Qwen2_5_VisionRotaryEmbedding,
    )

    with torch.device("meta"):
        rotary = Qwen2_5_VisionRotaryEmbedding(8)
    assert rotary.inv_freq.device.type == "cpu"
    assert torch.equal(rotary.inv_freq, Qwen2_5_VisionRotaryEmbedding(8).inv_freq)


def test_text_rotary_default_frequencies() -> None:
    torch = _torch()
    from raw2md_engine.surya.common.surya.decoder import Qwen2RotaryEmbedding
    from raw2md_engine.surya.common.surya.decoder.config import SuryaDecoderConfig

    config = SuryaDecoderConfig(hidden_size=16, num_attention_heads=2, rope_theta=100.0)
    rotary = Qwen2RotaryEmbedding(config)

    expected = 1.0 / (100.0 ** (torch.tensor([0.0, 2.0, 4.0, 6.0]) / 8))
    assert torch.equal(rotary.inv_freq, expected)
    assert rotary.attention_scaling == 1.0


def test_encoder_head_mask() -> None:
    torch = _torch()
    from raw2md_engine.surya.ocr_error.model.config import DistilBertConfig
    from raw2md_engine.surya.ocr_error.model.encoder import DistilBertModel

    config = DistilBertConfig(
        vocab_size=10,
        dim=8,
        n_heads=2,
        hidden_dim=16,
        n_layers=1,
        max_position_embeddings=16,
    )
    model = DistilBertModel(config)

    assert model.get_head_mask(None, 3) == [None, None, None]
    mask = model.get_head_mask(torch.tensor([1.0, 0.0]), 3)
    assert mask.shape == (3, 1, 2, 1, 1)
    assert mask.dtype == model.dtype
