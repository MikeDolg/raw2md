"""A docx cannot make pandoc write media outside the media folder."""

from __future__ import annotations

import base64
import re
import subprocess
import zipfile
from pathlib import Path

import pytest

from raw2md.engines import ConvertOptions, PandocEngine

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_IMAGE_TARGET = re.compile(rb'(relationships/image"[^>]*?Target=")[^"]*"')
_HOSTILE_TARGETS = [
    "media/../../../escaped.png",
    "../../escaped.png",
    "/../../escaped.png",
    "media/..\\..\\escaped.png",
]


def _docx_with_media_target(tmp_path: Path, target: str) -> Path:
    """Build a docx with one image whose relationship target is `target`."""
    draft = tmp_path / "draft.md"
    draft.write_text("![alt](image.png)\n", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(_PNG)
    base = tmp_path / "base.docx"
    subprocess.run(
        ["pandoc", str(draft), "--output", str(base)], check=True, cwd=tmp_path
    )  # pandoc is a local tool; the fixture only builds the input

    source = tmp_path / "doc.docx"
    with zipfile.ZipFile(base) as archive, zipfile.ZipFile(source, "w") as out:
        for name in archive.namelist():
            data = archive.read(name)
            if name.endswith("document.xml.rels"):
                data, count = _IMAGE_TARGET.subn(
                    lambda match: match.group(1) + target.encode("utf-8") + b'"',
                    data,
                )
                assert count == 1, "the image relationship was not found"
            out.writestr(name, data)
        out.writestr(f"word/{target}", _PNG)
    return source


@pytest.mark.parametrize("target", _HOSTILE_TARGETS)
def test_docx_media_names_stay_inside_the_media_folder(
    tmp_path: Path, target: str
) -> None:
    if not PandocEngine().available():
        pytest.skip("pandoc is not available")
    workdir = tmp_path / "work"
    workdir.mkdir()
    source = _docx_with_media_target(workdir, target)
    media_dir = tmp_path / "out" / "doc_media"
    media_dir.parent.mkdir()
    before = {p for p in tmp_path.rglob("*") if p.is_file()}

    result = PandocEngine().convert(source, media_dir, ConvertOptions())

    created = {p for p in tmp_path.rglob("*") if p.is_file()} - before
    # Pandoc may skip a target it cannot resolve; either way nothing leaves.
    for path in created:
        assert path.resolve().is_relative_to(media_dir.resolve()), path
    assert not (tmp_path / "escaped.png").exists()
    assert not (tmp_path.parent / "escaped.png").exists()
    assert all(".." not in Path(name).parts for name in result.media)
