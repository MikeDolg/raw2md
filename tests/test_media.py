"""Tests for media asset post-processing: dedup, furniture, pandoc, EMF, links."""

from __future__ import annotations

import io
import logging
import random
from collections.abc import Sequence
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from raw2md.media import (
    convert_emf_media,
    dedupe_repeated_images,
    drop_furniture_images,
    flatten_pandoc_media,
    rewrite_media_links,
)
from raw2md.output import OutputTarget, resolve_output_target


def _target(tmp_path: Path, name: str) -> OutputTarget:
    return resolve_output_target(tmp_path / name, output_dir=None)


def test_rewrite_media_links_flat_marker_name(tmp_path: Path) -> None:
    target = _target(tmp_path, "a.pdf")
    body = "![fig](_page_0_Picture_0.jpeg)\n"

    out = rewrite_media_links(body, target, ("_page_0_Picture_0.jpeg",))

    assert out == "![fig](a/_page_0_Picture_0.jpeg)\n"


def test_rewrite_media_links_pandoc_extract_path(tmp_path: Path) -> None:
    target = _target(tmp_path, "doc.docx")
    body = "![x](/abs/doc/media/image1.png)\n"

    out = rewrite_media_links(body, target, ("media/image1.png",))

    assert out == "![x](doc/media/image1.png)\n"


def test_rewrite_media_links_leaves_remote_urls(tmp_path: Path) -> None:
    target = _target(tmp_path, "a.pdf")
    body = "![x](https://example.com/fig.jpeg)\n"

    out = rewrite_media_links(body, target, ("fig.jpeg",))

    assert out == body


def test_rewrite_media_links_percent_encodes_space_in_folder_name(
    tmp_path: Path,
) -> None:
    target = _target(tmp_path, "My Book.pdf")
    body = "![fig](_page_0_Picture_0.jpeg)\n"

    out = rewrite_media_links(body, target, ("_page_0_Picture_0.jpeg",))

    assert out == "![fig](My%20Book/_page_0_Picture_0.jpeg)\n"


def test_rewrite_media_links_html_img_absolute_src(tmp_path: Path) -> None:
    # pandoc writes a sized docx image as `<img>` with an absolute src.
    target = _target(tmp_path, "doc.docx")
    body = (
        '<img src="D:\\out\\doc\\media\\image1.jpeg" style="width:1in;height:1in" />\n'
    )

    out = rewrite_media_links(body, target, ("media/image1.jpeg",))

    assert out == ('<img src="doc/media/image1.jpeg" style="width:1in;height:1in" />\n')


def test_rewrite_media_links_html_img_leaves_remote_urls(tmp_path: Path) -> None:
    target = _target(tmp_path, "doc.docx")
    body = '<img src="https://example.com/fig.jpeg" style="width:1in" />\n'

    out = rewrite_media_links(body, target, ("fig.jpeg",))

    assert out == body


def _png_bytes() -> bytes:
    """PNG bytes for a fixture named `.emf`/`.wmf`.

    `Image.open` sniffs content, not the name, so the Pillow round trip runs
    without a real WMF/EMF stream, which only Windows can render.
    """
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


_LOGO_RECT = pymupdf.Rect(10, 10, 60, 40)

# The same image bigger and moved: a logo blown up on the cover page.
_COVER_RECT = pymupdf.Rect(10, 10, 160, 90)


def _write_pdf_with_images(
    path: Path,
    pages: Sequence[bytes | None],
    *,
    rects: Sequence[pymupdf.Rect] | None = None,
    rotates: Sequence[int] | None = None,
) -> None:
    """Write a PDF with one page per entry, inserting the given PNG if any.

    Identical bytes on separate pages share one xref, as a reused picture does.
    `rects` and `rotates` place each page's image on its own.
    """
    doc = pymupdf.open()
    try:
        for i, png in enumerate(pages):
            page = doc.new_page()
            if png is not None:
                rect = rects[i] if rects is not None else _LOGO_RECT
                rotate = rotates[i] if rotates is not None else 0
                page.insert_image(rect, stream=png, rotate=rotate)
        doc.save(str(path))
    finally:
        doc.close()


def test_dedupe_repeated_images_collapses_a_logo_reused_across_pages(
    tmp_path: Path,
) -> None:
    logo = _png_bytes()
    source = tmp_path / "doc.pdf"
    _write_pdf_with_images(source, [logo, logo, logo])
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = (
        "_page_0_Picture_0.jpeg",
        "_page_1_Picture_0.jpeg",
        "_page_2_Picture_0.jpeg",
    )
    for asset in media:
        (media_dir / asset).write_bytes(logo)
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = dedupe_repeated_images(source, media_dir, media, body)

    assert new_media == ("_page_0_Picture_0.jpeg",)
    assert new_body == "![](_page_0_Picture_0.jpeg)\n" * 3
    assert (media_dir / "_page_0_Picture_0.jpeg").exists()
    assert not (media_dir / "_page_1_Picture_0.jpeg").exists()
    assert not (media_dir / "_page_2_Picture_0.jpeg").exists()


def test_dedupe_repeated_images_leaves_same_xref_different_placement(
    tmp_path: Path,
) -> None:
    # The cover shares the logo's xref but renders differently.
    logo = _png_bytes()
    source = tmp_path / "doc.pdf"
    _write_pdf_with_images(source, [logo, logo], rects=[_LOGO_RECT, _COVER_RECT])
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = ("_page_0_Picture_0.jpeg", "_page_1_Picture_0.jpeg")
    for asset in media:
        (media_dir / asset).write_bytes(logo)
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = dedupe_repeated_images(source, media_dir, media, body)

    assert new_media == media
    assert new_body == body
    assert (media_dir / "_page_0_Picture_0.jpeg").exists()
    assert (media_dir / "_page_1_Picture_0.jpeg").exists()


def test_dedupe_repeated_images_leaves_same_bbox_different_rotation(
    tmp_path: Path,
) -> None:
    # The bbox cannot tell an upside-down placement from an upright one.
    logo = _png_bytes()
    source = tmp_path / "doc.pdf"
    _write_pdf_with_images(source, [logo, logo], rotates=[0, 180])
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = ("_page_0_Picture_0.jpeg", "_page_1_Picture_0.jpeg")
    for asset in media:
        (media_dir / asset).write_bytes(logo)
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = dedupe_repeated_images(source, media_dir, media, body)

    assert new_media == media
    assert new_body == body
    assert (media_dir / "_page_0_Picture_0.jpeg").exists()
    assert (media_dir / "_page_1_Picture_0.jpeg").exists()


def test_dedupe_repeated_images_leaves_a_page_marker_split_into_two_crops(
    tmp_path: Path,
) -> None:
    # marker cut page 1 into two crops, and which one is the placement is
    # unknown.
    logo = _png_bytes()
    source = tmp_path / "doc.pdf"
    _write_pdf_with_images(source, [logo, logo])
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = (
        "_page_0_Picture_0.jpeg",
        "_page_1_Picture_0.jpeg",
        "_page_1_Picture_1.jpeg",
    )
    for asset in media:
        (media_dir / asset).write_bytes(logo)
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = dedupe_repeated_images(source, media_dir, media, body)

    assert new_media == media
    assert new_body == body
    for asset in media:
        assert (media_dir / asset).exists()


def _other_png_bytes() -> bytes:
    """A second real PNG, distinct in content from `_png_bytes`."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 100, 0)).save(buf, format="PNG")
    return buf.getvalue()


def test_dedupe_repeated_images_leaves_distinct_images(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_with_images(source, [_png_bytes(), _other_png_bytes()])
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = ("_page_0_Picture_0.jpeg", "_page_1_Picture_0.jpeg")
    for asset in media:
        (media_dir / asset).write_bytes(_png_bytes())
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = dedupe_repeated_images(source, media_dir, media, body)

    assert new_media == media
    assert new_body == body
    assert (media_dir / "_page_0_Picture_0.jpeg").exists()
    assert (media_dir / "_page_1_Picture_0.jpeg").exists()


def test_dedupe_repeated_images_no_media_is_noop(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    _write_pdf_with_images(source, [_png_bytes()])
    body = "no images here\n"

    new_body, new_media = dedupe_repeated_images(source, tmp_path / "doc", (), body)

    assert (new_body, new_media) == (body, ())


def test_dedupe_repeated_images_skips_on_unreadable_source(tmp_path: Path) -> None:
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF-1.4 stub")
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    asset = "_page_0_Picture_0.jpeg"
    (media_dir / asset).write_bytes(_png_bytes())
    body = f"![]({asset})\n"

    new_body, new_media = dedupe_repeated_images(source, media_dir, (asset,), body)

    assert (new_body, new_media) == (body, (asset,))
    assert (media_dir / asset).exists()


def _noise_png_bytes(seed: int, *, flip: tuple[int, int] | None = None) -> bytes:
    """A 32x32 grayscale PNG of seeded noise.

    `flip` inverts one pixel, like crop-box jitter: the bytes change, the dHash
    does not.
    """
    rng = random.Random(seed)  # noqa: S311 -- seeded for deterministic test fixtures, not security
    img = Image.new("L", (32, 32))
    pixels = img.load()
    for x in range(32):
        for y in range(32):
            pixels[x, y] = rng.randint(0, 255)
    if flip is not None:
        x, y = flip
        pixels[x, y] = (pixels[x, y] + 128) % 256
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_drop_furniture_images_drops_a_picture_repeated_across_pages(
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = tuple(f"_page_{i}_Picture_0.jpeg" for i in range(5))
    for i, asset in enumerate(media):
        flip = (i * 3 % 32, i * 5 % 32)
        (media_dir / asset).write_bytes(_noise_png_bytes(0, flip=flip))
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = drop_furniture_images(media_dir, media, body)

    assert new_media == ()
    assert new_body == ""
    for asset in media:
        assert not (media_dir / asset).exists()


def test_drop_furniture_images_leaves_a_single_picture(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    asset = "_page_0_Picture_0.jpeg"
    (media_dir / asset).write_bytes(_noise_png_bytes(0))
    body = f"![]({asset})\n"

    new_body, new_media = drop_furniture_images(media_dir, (asset,), body)

    assert (new_body, new_media) == (body, (asset,))
    assert (media_dir / asset).exists()


def test_drop_furniture_images_leaves_distinct_content_figures(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = tuple(f"_page_{i}_Picture_0.jpeg" for i in range(10))
    for i, asset in enumerate(media):
        (media_dir / asset).write_bytes(_noise_png_bytes(i + 1))
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = drop_furniture_images(media_dir, media, body)

    assert new_media == media
    assert new_body == body
    for asset in media:
        assert (media_dir / asset).exists()


def test_drop_furniture_images_below_page_threshold_is_kept(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = tuple(f"_page_{i}_Picture_0.jpeg" for i in range(4))
    for i, asset in enumerate(media):
        flip = (i * 3 % 32, i * 5 % 32)
        (media_dir / asset).write_bytes(_noise_png_bytes(0, flip=flip))
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = drop_furniture_images(media_dir, media, body)

    assert new_media == media
    assert new_body == body


def test_drop_furniture_images_ignores_assets_without_a_page_number(
    tmp_path: Path,
) -> None:
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = tuple(f"image{i}.png" for i in range(6))
    for asset in media:
        (media_dir / asset).write_bytes(_noise_png_bytes(0))
    body = "".join(f"![]({asset})\n" for asset in media)

    new_body, new_media = drop_furniture_images(media_dir, media, body)

    assert (new_body, new_media) == (body, media)


def test_drop_furniture_images_keeps_a_meaningful_alt_caption(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = tuple(f"_page_{i}_Picture_0.jpeg" for i in range(5))
    for i, asset in enumerate(media):
        flip = (i * 3 % 32, i * 5 % 32)
        (media_dir / asset).write_bytes(_noise_png_bytes(0, flip=flip))
    body = f"![Company logo]({media[0]})\n" + "".join(
        f"![]({asset})\n" for asset in media[1:]
    )

    new_body, new_media = drop_furniture_images(media_dir, media, body)

    assert new_media == ()
    assert new_body == "Company logo\n"


def test_drop_furniture_images_skips_an_unreadable_asset(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = tuple(f"_page_{i}_Picture_0.jpeg" for i in range(6))
    for i, asset in enumerate(media[:5]):
        flip = (i * 3 % 32, i * 5 % 32)
        (media_dir / asset).write_bytes(_noise_png_bytes(0, flip=flip))
    (media_dir / media[5]).write_bytes(b"not an image")
    body = "".join(f"![]({asset})\n" for asset in media)

    with caplog.at_level(logging.INFO):
        new_body, new_media = drop_furniture_images(media_dir, media, body)

    assert new_media == (media[5],)
    assert new_body == f"![]({media[5]})\n"
    assert (media_dir / media[5]).exists()
    for asset in media[:5]:
        assert not (media_dir / asset).exists()
    assert "furniture hash skipped" in caplog.text


def test_drop_furniture_images_drops_an_html_img_reference(tmp_path: Path) -> None:
    # Not reachable in practice, but an `<img>` must not dangle after removal.
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    media = tuple(f"_page_{i}_Picture_0.jpeg" for i in range(5))
    for i, asset in enumerate(media):
        flip = (i * 3 % 32, i * 5 % 32)
        (media_dir / asset).write_bytes(_noise_png_bytes(0, flip=flip))
    body = f'<img src="{media[0]}" width="100">\n' + "".join(
        f"![]({asset})\n" for asset in media[1:]
    )

    new_body, new_media = drop_furniture_images(media_dir, media, body)

    assert new_media == ()
    assert media[0] not in new_body
    assert "<img" not in new_body


def test_flatten_pandoc_media_lifts_nested_files(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    nested = media_dir / "media"
    nested.mkdir(parents=True)
    (nested / "image1.png").write_bytes(b"a")
    (nested / "image2.emf").write_bytes(b"b")

    new_media = flatten_pandoc_media(
        media_dir, ("media/image1.png", "media/image2.emf")
    )

    assert new_media == ("image1.png", "image2.emf")
    assert (media_dir / "image1.png").read_bytes() == b"a"
    assert (media_dir / "image2.emf").read_bytes() == b"b"
    assert not nested.exists()


def test_flatten_pandoc_media_collision_leaves_file_nested(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    media_dir = tmp_path / "doc"
    nested = media_dir / "media"
    nested.mkdir(parents=True)
    (media_dir / "image1.png").write_bytes(b"top-level")
    (nested / "image1.png").write_bytes(b"nested")
    (nested / "image2.png").write_bytes(b"lifts fine")

    with caplog.at_level(logging.WARNING):
        new_media = flatten_pandoc_media(
            media_dir, ("media/image1.png", "media/image2.png")
        )

    assert new_media == ("media/image1.png", "image2.png")
    assert (nested / "image1.png").read_bytes() == b"nested"
    assert (media_dir / "image1.png").read_bytes() == b"top-level"
    assert (media_dir / "image2.png").read_bytes() == b"lifts fine"
    assert "image1.png" in caplog.text


def test_flatten_pandoc_media_no_nested_media_is_noop(tmp_path: Path) -> None:
    # marker puts assets directly in media_dir, with no `media/` level.
    media_dir = tmp_path / "doc"
    media_dir.mkdir()
    (media_dir / "_page_0_Picture_0.jpeg").write_bytes(b"x")

    new_media = flatten_pandoc_media(media_dir, ("_page_0_Picture_0.jpeg",))

    assert new_media == ("_page_0_Picture_0.jpeg",)


def test_flatten_pandoc_media_missing_media_dir_is_noop(tmp_path: Path) -> None:
    # --disable-image-extraction: no media folder exists.
    media_dir = tmp_path / "doc"

    new_media = flatten_pandoc_media(media_dir, ())

    assert new_media == ()


def test_convert_emf_media_renders_and_renames(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    asset_path = media_dir / "media" / "image1.emf"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(_png_bytes())
    body = "![x](media/image1.emf)\n"

    new_body, new_media = convert_emf_media(media_dir, ("media/image1.emf",), body)

    assert new_media == ("media/image1.png",)
    assert new_body == "![x](media/image1.png)\n"
    assert not asset_path.exists()
    assert (media_dir / "media" / "image1.png").exists()


def test_convert_emf_media_html_img_src(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    asset_path = media_dir / "media" / "image1.wmf"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(_png_bytes())
    body = '<img src="media/image1.wmf" style="width:1in" />\n'

    new_body, new_media = convert_emf_media(media_dir, ("media/image1.wmf",), body)

    assert new_media == ("media/image1.png",)
    assert new_body == '<img src="media/image1.png" style="width:1in" />\n'


def test_convert_emf_media_unrenderable_leaves_file_and_link(tmp_path: Path) -> None:
    # No WMF/EMF renderer and a malformed file both raise OSError; the asset
    # stays.
    media_dir = tmp_path / "doc"
    asset_path = media_dir / "media" / "image1.emf"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"not a real image")
    body = "![x](media/image1.emf)\n"

    new_body, new_media = convert_emf_media(media_dir, ("media/image1.emf",), body)

    assert new_media == ("media/image1.emf",)
    assert new_body == body
    assert asset_path.exists()


def test_convert_emf_media_leaves_remote_urls(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    asset_path = media_dir / "media" / "image1.emf"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(_png_bytes())
    body = "![x](https://example.com/fig.emf)\n"

    new_body, new_media = convert_emf_media(media_dir, ("media/image1.emf",), body)

    # The remote link is a different target and stays untouched.
    assert new_body == body
    assert new_media == ("media/image1.png",)


def test_convert_emf_media_leaves_data_uri(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    asset_path = media_dir / "media" / "image1.wmf"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(_png_bytes())
    body = '<img src="data:image/emf;base64,AAA=" />\n'

    new_body, new_media = convert_emf_media(media_dir, ("media/image1.wmf",), body)

    assert new_body == body
    assert new_media == ("media/image1.png",)


def test_convert_emf_media_no_emf_assets_is_noop(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    body = "![x](media/image1.png)\n"

    new_body, new_media = convert_emf_media(media_dir, ("media/image1.png",), body)

    assert new_body == body
    assert new_media == ("media/image1.png",)


def test_convert_emf_media_no_media_is_noop(tmp_path: Path) -> None:
    media_dir = tmp_path / "doc"
    body = "no images here\n"

    new_body, new_media = convert_emf_media(media_dir, (), body)

    assert (new_body, new_media) == (body, ())
