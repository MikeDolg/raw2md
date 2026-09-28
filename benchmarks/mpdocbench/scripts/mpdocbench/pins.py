"""The pins of the benchmark, the annotation, and the folders a run works in."""

from __future__ import annotations

import json
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

PINS_PATH = Path(__file__).resolve().parent.parent / "pins.yaml"

# The two sets a run can take. The benchmark itself is bilingual, and the
# cleaning rules of raw2md were never checked against Chinese text, so the
# English half is the set worth scoring on its own.
LANGUAGES = ("all", "english")


class BenchmarkError(Exception):
    """A phase cannot go on: a pin, a download, or an earlier phase is wrong."""


@dataclass(frozen=True)
class Pins:
    upstream_repo: str
    upstream_commit: str
    upstream_folder: str
    annotation_name: str
    dataset_url: str
    dataset_sha256: str
    dataset_documents: int
    renames: Mapping[str, str]
    slidevqa_repo: str
    slidevqa_revision: str
    slidevqa_files: str
    slidevqa_decks: Mapping[str, str]
    metrics: Mapping[str, list[str]]
    headline: Mapping[str, str]
    lower_is_better: frozenset[str]
    match_method: str
    metrics_off: Mapping[str, str]


def load_pins(path: Path = PINS_PATH) -> Pins:
    data = load_yaml(path)
    try:
        upstream = data["upstream"]
        dataset = data["dataset"]
        slidevqa = data["slidevqa"]
        return Pins(
            upstream_repo=str(upstream["repo"]),
            upstream_commit=str(upstream["commit"]),
            upstream_folder=str(upstream["folder"]),
            annotation_name=str(upstream["annotation"]),
            dataset_url=str(dataset["url"]),
            dataset_sha256=str(dataset["sha256"]),
            dataset_documents=int(dataset["documents"]),
            renames=dict(dataset.get("renames") or {}),
            slidevqa_repo=str(slidevqa["repo"]),
            slidevqa_revision=str(slidevqa["revision"]),
            slidevqa_files=str(slidevqa["files"]),
            slidevqa_decks=dict(slidevqa["decks"]),
            metrics={key: list(value) for key, value in data["metrics"].items()},
            headline=dict(data["headline"]),
            lower_is_better=frozenset(data["lower_is_better"]),
            match_method=str(data["match_method"]),
            metrics_off=dict(data.get("metrics_off") or {}),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BenchmarkError(
            f"{path} lacks a pin or holds a wrong one: {error}"
        ) from error


@dataclass(frozen=True)
class Document:
    name: str  # the stem of `image_path`, and the name of the PDF raw2md converts
    pages: tuple[str, ...]  # page file names, in the order of the annotation
    language: str


def read_annotation(path: Path, language: str = "all") -> list[Document]:
    """The annotated documents of one language set, sorted by name."""
    if language not in LANGUAGES:
        raise BenchmarkError(f"unknown language set {language!r}")
    try:
        entries: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkError(f"cannot read the annotation {path}: {error}") from error
    documents: dict[str, Document] = {}
    for entry in entries:
        page_info = entry["page_info"]
        name = PurePosixPath(page_info["image_path"]).stem
        # Two entries under one name would score one prediction twice and count
        # a document that no PDF stands for.
        if name in documents:
            raise BenchmarkError(f"the annotation names {name} twice")
        documents[name] = Document(
            name=name,
            pages=tuple(PurePosixPath(page).name for page in page_info["images_list"]),
            language=str(page_info["page_attribute"]["language"]),
        )
    chosen = [
        document
        for document in documents.values()
        if language in ("all", document.language)
    ]
    return sorted(chosen, key=lambda document: document.name)


def select_documents(
    documents: Sequence[Document], names: Sequence[str] | None
) -> list[Document]:
    """The named documents of the set, or the whole set when no name is given.

    A name outside the set stops the run: a smaller set than the one asked for
    would be scored as if it were that one.
    """
    if not names:
        return list(documents)
    known = {document.name for document in documents}
    unknown = sorted(set(names) - known)
    if unknown:
        raise BenchmarkError(f"the language set holds no document named {unknown}")
    wanted = set(names)
    return [document for document in documents if document.name in wanted]


@dataclass(frozen=True)
class DataDir:
    """What `fetch` downloads, shared by every run on this machine."""

    root: Path

    @property
    def upstream(self) -> Path:
        return self.root / "upstream"

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def record(self) -> Path:
        return self.root / "fetch.yaml"

    def harness(self, pins: Pins) -> Path:
        return self.upstream / pins.upstream_folder

    def annotation(self, pins: Pins) -> Path:
        return self.harness(pins) / pins.annotation_name


@dataclass(frozen=True)
class RunDir:
    """One run: its inputs, the output of raw2md, the scoring, the result."""

    root: Path

    @property
    def pdfs(self) -> Path:
        return self.root / "pdfs"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def scoring(self) -> Path:
        return self.root / "scoring"

    @property
    def record(self) -> Path:
        return self.root / "run.yaml"

    @property
    def results(self) -> Path:
        return self.root / "results.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise BenchmarkError(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise BenchmarkError(f"{path} does not hold a mapping")
    return data


def dump_yaml(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n": write_text would otherwise write CRLF on Windows, and a
    # result committed from there would differ from one written on Linux.
    path.write_text(
        yaml.safe_dump(dict(data), allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
        newline="\n",
    )


def system_name() -> str:
    """The operating system a phase runs on, as its distribution names itself.

    `platform.platform()` names the kernel, and in a container that is the
    kernel of the host, not of the image the run actually used.
    """
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        # No os-release file: not a Linux distribution, where the kernel string
        # is the best name there is.
        return platform.platform()
    return release.get("PRETTY_NAME") or platform.platform()
