"""The weights of the engine: one pinned revision of the raw2md-models repository.

The files keep the layout of the repository under `paths.models_dir()`. A stamp
file there names the revision of the files on disk. The check reads the disk
only, so a complete folder of the pinned revision makes no network request. A
new revision comes with a new raw2md release.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

REPO_ID = "MikeDolg/raw2md-models"

# The full commit hash: a branch name would let the files change under a release.
REVISION = "c8fc81af13eef85e4c56d99555e958362902ab82"

STAMP_NAME = "revision"

# The checkpoint folders of the engine and their files, as each manifest.json
# lists them.
_CHECKPOINTS: dict[str, tuple[str, ...]] = {
    "layout/surya-2025_09_23": (
        ".gitattributes",
        "README.md",
        "config.json",
        "manifest.json",
        "model.safetensors",
        "preprocessor_config.json",
        "processor_config.json",
        "special_tokens_map.json",
        "specials.json",
        "specials_dict.json",
        "tokenizer_config.json",
        "training_args.bin",
        "vocab_math.json",
    ),
    "ocr_error_detection/surya-2025_02_18": (
        ".gitattributes",
        "README.md",
        "config.json",
        "manifest.json",
        "model.safetensors",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ),
    "table_recognition/surya-2025_02_18": (
        ".gitattributes",
        "README.md",
        "config.json",
        "manifest.json",
        "model.safetensors",
        "preprocessor_config.json",
    ),
    "text_detection/surya-2025_05_07": (
        ".gitattributes",
        "README.md",
        "config.json",
        "manifest.json",
        "model.safetensors",
        "preprocessor_config.json",
        "training_args.bin",
    ),
    "text_recognition/surya-2025_09_23": (
        ".gitattributes",
        "README.md",
        "config.json",
        "manifest.json",
        "model.safetensors",
        "preprocessor_config.json",
        "processor_config.json",
        "special_tokens_map.json",
        "specials.json",
        "specials_dict.json",
        "tokenizer_config.json",
        "training_args.bin",
        "vocab_math.json",
    ),
}

# The license travels with the weights it governs.
FILES: tuple[str, ...] = (
    "DATALAB_MODEL_LICENSE",
    *(f"{folder}/{name}" for folder, names in _CHECKPOINTS.items() for name in names),
)


class WeightsError(Exception):
    """The weights could not be downloaded."""


def stamp_revision(weights_dir: Path) -> str | None:
    """The revision that the stamp names, or None without a stamp."""
    try:
        return (weights_dir / STAMP_NAME).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None


def missing_files(weights_dir: Path) -> tuple[str, ...]:
    """The files to download, in the order of `FILES`.

    A stamp of another revision makes every file stale. The download then
    skips the unchanged ones by their checksum.
    """
    if stamp_revision(weights_dir) != REVISION:
        return FILES
    return tuple(name for name in FILES if not (weights_dir / name).is_file())


def _require_pinned(weights_dir: Path, name: str) -> None:
    """Fail when the file on disk is not the pinned revision.

    With the Hub unreachable, the download returns an existing file of any
    revision instead of failing. Its metadata record names the real revision.
    """
    from huggingface_hub._local_folder import read_download_metadata

    record = read_download_metadata(weights_dir, name)
    if record is None or record.commit_hash != REVISION:
        raise WeightsError(
            f"cannot confirm that {name} is at revision {REVISION} of {REPO_ID}: "
            "the Hub may be unreachable"
        )


def fetch(weights_dir: Path, names: Sequence[str]) -> None:
    """Download `names` at the pinned revision, then stamp the folder.

    Raises `WeightsError` when a download fails. The stamp is written only
    after every file arrived, so an interrupted run resumes at the next check.
    """
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import HfHubHTTPError

    try:
        weights_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            hf_hub_download(REPO_ID, name, revision=REVISION, local_dir=weights_dir)
            _require_pinned(weights_dir, name)
        (weights_dir / STAMP_NAME).write_text(REVISION + "\n", encoding="utf-8")
    # The Xet backend reports a transport failure as RuntimeError.
    except (HfHubHTTPError, OSError, RuntimeError) as exc:
        raise WeightsError(
            f"cannot download the engine weights from {REPO_ID} "
            f"into {weights_dir}: {exc}"
        ) from exc
