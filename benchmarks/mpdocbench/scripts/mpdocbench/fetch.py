"""Download the benchmark from its authors: the harness, the annotation, the pages.

Nothing of the benchmark is stored in this repository. The harness and the
annotation come from the pinned commit of the upstream repository, the page
images from the pinned archive on ModelScope, and the eleven documents that the
archive lacks from SlideVQA on the Hugging Face Hub.

A document that cannot be fetched does not stop the run. `fetch.yaml` names it
and the reason, and the result counts it as missing.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from mpdocbench.pins import (
    BenchmarkError,
    DataDir,
    Document,
    Pins,
    dump_yaml,
    load_yaml,
    read_annotation,
)

_ARCHIVE_NAME = "MPDocBench_data.zip"
_CHUNK = 1 << 20
# The only members of the archive a run reads. Anything else (a stray
# `.DS_Store`, a path that climbs out of the folder) is left inside the zip.
_PAGE_MEMBER = re.compile(r"^images/([^/.][^/]*)/([^/.][^/]*\.jpg)$")


def clone_upstream(pins: Pins, data: DataDir) -> None:
    """Put the upstream repository at the pinned commit under `data`."""
    if not (data.upstream / ".git").is_dir():
        data.root.mkdir(parents=True, exist_ok=True)
        _git(
            "clone",
            "--quiet",
            "--filter=blob:none",
            pins.upstream_repo,
            str(data.upstream),
        )
    _git("-C", str(data.upstream), "checkout", "--quiet", pins.upstream_commit)


def _git(*args: str) -> None:
    if shutil.which("git") is None:
        raise BenchmarkError("git is not on PATH, and the harness is a git clone")
    completed = subprocess.run(["git", *args], check=False)
    if completed.returncode != 0:
        raise BenchmarkError(
            f"git {' '.join(args[:2])} exited with {completed.returncode}"
        )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download_archive(pins: Pins, data: DataDir) -> Path:
    """Download the page archive, or reuse a copy whose hash matches the pin."""
    target = data.root / _ARCHIVE_NAME
    if target.is_file() and sha256_of(target) == pins.dataset_sha256:
        return target
    partial = target.with_suffix(".part")
    print(f"downloading {pins.dataset_url}", flush=True)
    try:
        with (
            urllib.request.urlopen(pins.dataset_url) as response,  # noqa: S310 -- the URL is a pin of pins.yaml
            partial.open("wb") as out,
        ):
            shutil.copyfileobj(response, out, _CHUNK)
    except (urllib.error.URLError, OSError) as error:
        partial.unlink(missing_ok=True)
        raise BenchmarkError(f"cannot download the page archive: {error}") from error
    actual = sha256_of(partial)
    if actual != pins.dataset_sha256:
        partial.unlink()
        raise BenchmarkError(
            f"the page archive hashes to {actual}, and the pin is {pins.dataset_sha256}"
        )
    partial.replace(target)
    return target


def extract_pages(archive: Path, images: Path, renames: Mapping[str, str]) -> int:
    """Write every page of the archive under `images/<document>/`. Return the count.

    `renames` maps `<document>/<page>` as the archive names it to the name the
    annotation uses, because the scorer reads the page list from the annotation.
    """
    count = 0
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.namelist():
            match = _PAGE_MEMBER.match(member)
            if match is None:
                continue
            relative = renames.get(f"{match[1]}/{match[2]}", f"{match[1]}/{match[2]}")
            target = images / PurePosixPath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))
            count += 1
    return count


def fetch_slidevqa(
    pins: Pins, images: Path, documents: Sequence[Document]
) -> str | None:
    """Write the SlideVQA decks the archive lacks. Return why it failed, or None.

    The dataset is gated, so a machine without an accepted token cannot have
    these pages; that is a missing document, not a broken run.
    """
    wanted = {doc.name: doc for doc in documents if doc.name in pins.slidevqa_decks}
    if not wanted:
        return None
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import HfHubHTTPError
        from pyarrow import (
            parquet,
        )
    except ImportError as error:
        return f"{error.name} is not installed"
    try:
        snapshot = Path(
            snapshot_download(
                pins.slidevqa_repo,
                repo_type="dataset",
                revision=pins.slidevqa_revision,
                allow_patterns=[pins.slidevqa_files],
                max_workers=4,
            )
        )
    except HfHubHTTPError as error:
        return f"the Hub refused the download: {error}"
    shards = sorted(snapshot.glob(pins.slidevqa_files))
    if not shards:
        return f"no file matched {pins.slidevqa_files} at the pinned revision"
    decks = collect_decks(
        [parquet.read_table(shard) for shard in shards],
        {pins.slidevqa_decks[name]: doc for name, doc in wanted.items()},
    )
    for name, pages in decks.items():
        folder = images / name
        folder.mkdir(parents=True, exist_ok=True)
        for page_name, page in zip(wanted[name].pages, pages, strict=False):
            (folder / page_name).write_bytes(page)
    return None


def collect_decks(
    tables: Sequence[Any], by_url: Mapping[str, Document]
) -> dict[str, list[bytes]]:
    """The stored JPEG bytes of each wanted deck, in page order.

    SlideVQA holds one row per question, so a deck repeats across rows with the
    same pages, and the first row wins. The bytes are written as stored: a
    decode and a re-encode would change the page the engine reads.
    """
    found: dict[str, list[bytes]] = {}
    for table in tables:
        columns = sorted(
            (name for name in table.column_names if re.fullmatch(r"page_\d+", name)),
            key=lambda name: int(name.split("_")[1]),
        )
        for row, url in enumerate(table.column("deck_url").to_pylist()):
            document = by_url.get(url)
            if document is None or document.name in found:
                continue
            pages: list[bytes] = []
            for column in columns[: len(document.pages)]:
                cell = table.column(column)[row].as_py()
                if cell is None:
                    break
                pages.append(cell["bytes"])
            found[document.name] = pages
    return found


def missing_documents(images: Path, documents: Sequence[Document]) -> list[str]:
    """Documents with at least one annotated page absent on disk."""
    return [
        document.name
        for document in documents
        if not all((images / document.name / page).is_file() for page in document.pages)
    ]


def needs_archive(
    previous: Mapping[str, Any],
    pins: Pins,
    images: Path,
    documents: Sequence[Document],
) -> bool:
    """Whether the archive must be fetched and extracted again.

    The archive is deleted after extraction, so a record of the pinned hash
    alone cannot restore a page that went missing later; SlideVQA holds only
    its own decks and would leave such a document missing for good.
    """
    if previous.get("archive_sha256") != pins.dataset_sha256:
        return True
    from_archive = [doc for doc in documents if doc.name not in pins.slidevqa_decks]
    return bool(missing_documents(images, from_archive))


def fetch(pins: Pins, data: DataDir) -> dict[str, Any]:
    """Run every download and write `fetch.yaml`. Return what it holds."""
    clone_upstream(pins, data)
    documents = read_annotation(data.annotation(pins))
    if len(documents) != pins.dataset_documents:
        raise BenchmarkError(
            f"the annotation names {len(documents)} documents, and the pin is"
            f" {pins.dataset_documents}"
        )
    previous = load_yaml(data.record) if data.record.is_file() else {}
    if needs_archive(previous, pins, data.images, documents):
        archive = download_archive(pins, data)
        pages = extract_pages(archive, data.images, pins.renames)
        print(f"extracted {pages} pages", flush=True)
        # The pages are what a run reads; the archive is 600 MB of the same.
        archive.unlink()

    slidevqa_error = None
    if missing_documents(data.images, documents):
        slidevqa_error = fetch_slidevqa(pins, data.images, documents)
    missing = missing_documents(data.images, documents)
    record = {
        "upstream_commit": pins.upstream_commit,
        "archive_url": pins.dataset_url,
        "archive_sha256": pins.dataset_sha256,
        "slidevqa_revision": pins.slidevqa_revision,
        "documents": len(documents),
        "missing": missing,
        "missing_reason": (slidevqa_error or "absent from the downloaded sources")
        if missing
        else None,
    }
    dump_yaml(data.record, record)
    return record
