"""Checks on the bundled engine copy `src/raw2md_engine`."""

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeGuard

import pytest

_COPY = Path(__file__).resolve().parent.parent / "src" / "raw2md_engine"

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
