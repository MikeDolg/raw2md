"""Media asset post-processing after conversion: pictures, not markup.

Runs right after the engine returns, in this order: furniture drop, xref
dedup, pandoc's nested `media/` lift, EMF/WMF render, then link rewrite. Each
step is a no-op on an empty media tuple, so a route with extraction disabled
or an engine that embeds no pictures pays nothing.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from PIL import Image

from raw2md.cleaning import drop_image_links
from raw2md.mdtext.links import HTML_IMG_RE, IMAGE_RE
from raw2md.output import OutputTarget, media_link

_logger = logging.getLogger("raw2md")

_PDF_EXTENSION = ".pdf"

# Word stores charts and diagrams as EMF, occasionally as the older WMF; pandoc
# extracts them as-is and no markdown target renders either format.
_EMF_EXTENSIONS = frozenset({".emf", ".wmf"})

# marker names a picture `_page_<n>_<BlockType>_<index>`.
_MARKER_IMAGE_PAGE_RE = re.compile(r"_page_(\d+)_")

# An 8x8 hash within 4 bits survives crop jitter between pages but keeps
# distinct figures of one size apart (calibrated on pdf and djvu bodies).
_FURNITURE_HASH_SIZE = 8
_FURNITURE_MAX_DISTANCE = 4
# Distinct pages for furniture; no content figure reached it in calibration.
_FURNITURE_MIN_PAGES = 5


def drop_furniture_images(
    media_dir: Path, media: tuple[str, ...], body: str
) -> tuple[str, tuple[str, ...]]:
    """Drop a picture repeated across many pages, as furniture.

    marker crops each placement anew, so a logo arrives as byte-distinct files
    per page. A difference hash grouped by Hamming distance finds them; a
    group on `_FURNITURE_MIN_PAGES` pages loses all files and links. Only
    marker names carry a page number, so docx pictures are untouched. Runs
    before `dedupe_repeated_images`.
    """
    pages_by_asset: dict[str, int] = {}
    for asset in media:
        match = _MARKER_IMAGE_PAGE_RE.search(Path(asset).stem)
        if match is not None:
            pages_by_asset[asset] = int(match.group(1))
    if len(pages_by_asset) < _FURNITURE_MIN_PAGES:
        return body, media

    fingerprints: dict[str, int] = {}
    for asset in pages_by_asset:
        fingerprint = _dhash(media_dir / asset)
        if fingerprint is not None:
            fingerprints[asset] = fingerprint

    furniture: set[str] = set()
    for group in _group_by_hamming_distance(fingerprints, _FURNITURE_MAX_DISTANCE):
        if len({pages_by_asset[asset] for asset in group}) >= _FURNITURE_MIN_PAGES:
            furniture.update(group)
    if not furniture:
        return body, media

    for asset in furniture:
        (media_dir / asset).unlink(missing_ok=True)
    new_media = tuple(asset for asset in media if asset not in furniture)
    return _drop_furniture_links(body, media, furniture), new_media


def _dhash(path: Path) -> int | None:
    """64-bit difference hash of the image at `path`, or None if unreadable."""
    try:
        with Image.open(path) as img:
            small = img.convert("L").resize(
                (_FURNITURE_HASH_SIZE + 1, _FURNITURE_HASH_SIZE),
                Image.Resampling.LANCZOS,
            )
            pixels = list(small.getdata())
    except (OSError, ValueError) as exc:
        _logger.info("furniture hash skipped for %s: %s", path.name, exc)
        return None
    width = _FURNITURE_HASH_SIZE + 1
    bits = 0
    for row in range(_FURNITURE_HASH_SIZE):
        offset = row * width
        for col in range(_FURNITURE_HASH_SIZE):
            bits = (bits << 1) | int(pixels[offset + col] > pixels[offset + col + 1])
    return bits


def _group_by_hamming_distance(
    fingerprints: dict[str, int], max_distance: int
) -> list[set[str]]:
    """Union assets whose dHash fingerprints sit within `max_distance` bits."""
    assets = list(fingerprints)
    parent = {asset: asset for asset in assets}

    def find(asset: str) -> str:
        while parent[asset] != asset:
            parent[asset] = parent[parent[asset]]
            asset = parent[asset]
        return asset

    for i, left in enumerate(assets):
        for right in assets[i + 1 :]:
            distance = (fingerprints[left] ^ fingerprints[right]).bit_count()
            if distance <= max_distance:
                root_left, root_right = find(left), find(right)
                if root_left != root_right:
                    parent[root_left] = root_right

    groups: dict[str, set[str]] = {}
    for asset in assets:
        groups.setdefault(find(asset), set()).add(asset)
    return list(groups.values())


def _drop_furniture_links(
    body: str, media: tuple[str, ...], furniture: set[str]
) -> str:
    """Remove every body link, markdown or HTML, targeting a furniture asset."""

    def is_furniture(target: str) -> bool:
        return _rewritable_asset(target, media) in furniture

    def strip_html(match: re.Match[str]) -> str:
        return "" if is_furniture(match.group(2)) else match.group(0)

    out: list[str] = []
    for raw_line in body.split("\n"):
        line = raw_line
        if HTML_IMG_RE.search(line):
            line = HTML_IMG_RE.sub(strip_html, line).strip()
        if not IMAGE_RE.search(line):
            out.append(line)
            continue
        out.extend(drop_image_links(line, is_furniture))
    return "\n".join(out)


def dedupe_repeated_images(
    source: Path, media_dir: Path, media: tuple[str, ...], body: str
) -> tuple[str, tuple[str, ...]]:
    """Collapse a pdf picture reused across pages to one extracted file.

    The key is the (xref, transform) pair read from the source pdf. Only a
    page with exactly one source image and exactly one crop takes part;
    otherwise which crop is which is unknown. Native pdf only: a djvu's
    assembled pages share no xref.
    """
    if not media or source.suffix.lower() != _PDF_EXTENSION:
        return body, media
    from raw2md.engines import pymupdf

    try:
        placements_by_page = pymupdf.image_placements_by_page(source)
    except (RuntimeError, OSError) as exc:
        _logger.warning("image dedup skipped for %s: %s", source.name, exc)
        return body, media

    page_by_asset: dict[str, int] = {}
    assets_per_page: dict[int, int] = {}
    for asset in media:
        match = _MARKER_IMAGE_PAGE_RE.search(Path(asset).stem)
        if match is None:
            continue
        page = int(match.group(1))
        page_by_asset[asset] = page
        assets_per_page[page] = assets_per_page.get(page, 0) + 1

    canonical_by_placement: dict[tuple[int, tuple[float, ...]], str] = {}
    duplicates: dict[str, str] = {}
    for asset in media:
        asset_page = page_by_asset.get(asset)
        if asset_page is None or assets_per_page[asset_page] != 1:
            continue
        if (
            asset_page >= len(placements_by_page)
            or len(placements_by_page[asset_page]) != 1
        ):
            continue
        placement = placements_by_page[asset_page][0]
        canonical = canonical_by_placement.setdefault(placement, asset)
        if canonical != asset:
            duplicates[asset] = canonical

    if not duplicates:
        return body, media
    for asset in duplicates:
        (media_dir / asset).unlink()
    new_media = tuple(asset for asset in media if asset not in duplicates)
    return _rename_media_links(body, media, duplicates), new_media


def flatten_pandoc_media(media_dir: Path, media: tuple[str, ...]) -> tuple[str, ...]:
    """Lift pandoc's `<media_dir>/media` nesting up to `<media_dir>` itself.

    The check is structural, so marker output passes unchanged. The body
    needs no edit: `rewrite_media_links` falls back to the basename. A name
    taken at the top level stays nested, with a log note.
    """
    nested = media_dir / "media"
    if not nested.is_dir():
        return media
    lifted: dict[str, str] = {}
    for asset in media:
        parts = Path(asset).parts
        if len(parts) < 2 or parts[0] != "media":
            continue
        rel = Path(*parts[1:])
        dest = media_dir / rel
        if dest.exists():
            _logger.warning(
                "could not flatten %s: %s already exists in %s",
                asset,
                rel.as_posix(),
                media_dir,
            )
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        (media_dir / asset).rename(dest)
        lifted[asset] = rel.as_posix()
    if not lifted:
        return media
    if not any(p.is_file() for p in nested.rglob("*")):
        shutil.rmtree(nested, ignore_errors=True)
    return tuple(lifted.get(asset, asset) for asset in media)


def convert_emf_media(
    media_dir: Path, media: tuple[str, ...], body: str
) -> tuple[str, tuple[str, ...]]:
    """Render extracted EMF/WMF assets (docx charts) to PNG in place.

    No markdown target displays EMF/WMF. Pillow renders them through GDI, so
    only on Windows; elsewhere, or for an undecodable file, the asset stays.
    Runs before `rewrite_media_links`, while links carry the raw asset paths.
    """
    if not media:
        return body, media
    renamed: dict[str, str] = {}
    for asset in media:
        if Path(asset).suffix.lower() not in _EMF_EXTENSIONS:
            continue
        new_asset = _render_to_png(media_dir / asset, asset)
        if new_asset is not None:
            renamed[asset] = new_asset
    if not renamed:
        return body, media
    new_media = tuple(renamed.get(asset, asset) for asset in media)
    return _rename_media_links(body, media, renamed), new_media


def _render_to_png(path: Path, asset: str) -> str | None:
    """Render one EMF/WMF file to a sibling `.png`, removing the original.

    Returns the new asset's relative path, or None when Pillow cannot render it.
    """
    dest = path.with_suffix(".png")
    try:
        with Image.open(path) as img:
            img.load()
            img.save(dest)
    except (OSError, ValueError) as exc:
        _logger.info("could not render %s to png: %s", asset, exc)
        return None
    path.unlink()
    return Path(asset).with_suffix(".png").as_posix()


def _rename_media_links(
    body: str, media: tuple[str, ...], renamed: dict[str, str]
) -> str:
    """Swap a renamed asset's name in its markdown and HTML links.

    Only the asset name changes; the path prefix stays verbatim.
    """

    def replace_markdown(match: re.Match[str]) -> str:
        alt, link_target = match.group(1), match.group(2)
        new_link = _renamed_link_target(link_target, media, renamed)
        if new_link is None:
            return match.group(0)
        return f"![{alt}]({new_link})"

    def replace_html_src(match: re.Match[str]) -> str:
        prefix, link_target, suffix = match.group(1), match.group(2), match.group(3)
        new_link = _renamed_link_target(link_target, media, renamed)
        if new_link is None:
            return match.group(0)
        return f"{prefix}{new_link}{suffix}"

    body = IMAGE_RE.sub(replace_markdown, body)
    return HTML_IMG_RE.sub(replace_html_src, body)


def _renamed_link_target(
    link_target: str, media: tuple[str, ...], renamed: dict[str, str]
) -> str | None:
    """The link text for `link_target` after its asset was renamed, or None.

    The lookup guarantees `link_target` ends with the old name, so only that
    tail is swapped.
    """
    asset = _rewritable_asset(link_target, media)
    if asset is None or asset not in renamed:
        return None
    return link_target[: -len(asset)] + renamed[asset]


def rewrite_media_links(body: str, target: OutputTarget, media: tuple[str, ...]) -> str:
    """Point body image links at the sibling media folder.

    The `src` of pandoc's HTML `<img>` (a sized docx image) is rewritten too.
    Only links to a known extracted asset change.
    """
    if not media:
        return body

    def replace_markdown(match: re.Match[str]) -> str:
        alt, link_target = match.group(1), match.group(2)
        asset = _rewritable_asset(link_target, media)
        if asset is None:
            return match.group(0)
        return f"![{alt}]({media_link(target, asset)})"

    def replace_html_src(match: re.Match[str]) -> str:
        prefix, link_target, suffix = match.group(1), match.group(2), match.group(3)
        asset = _rewritable_asset(link_target, media)
        if asset is None:
            return match.group(0)
        return f"{prefix}{media_link(target, asset)}{suffix}"

    body = IMAGE_RE.sub(replace_markdown, body)
    return HTML_IMG_RE.sub(replace_html_src, body)


def _rewritable_asset(link_target: str, media: tuple[str, ...]) -> str | None:
    """The extracted asset `link_target` refers to, or None if not rewritable."""
    if not is_rewritable_target(link_target):
        return None
    norm = link_target.replace("\\", "/").lstrip("/")
    norm = norm.removeprefix("./")
    return _match_asset(norm, media)


def is_rewritable_target(target: str) -> bool:
    """True when `target` is a local path eligible for media-link rewriting.

    A URL scheme carries ``://``; a drive letter (``C:``) does not. Shared
    with the md route's cross-drive link redirect, which classifies the same
    targets for a different destination.
    """
    if not target or target.startswith(("#", "//", "data:")):
        return False
    return "://" not in target


def _match_asset(norm: str, media: tuple[str, ...]) -> str | None:
    """Find the extracted asset a normalized link target refers to, if any."""
    # The full relative path first.
    for asset in media:
        if norm == asset or norm.endswith("/" + asset):
            return asset
    # Fall back to the basename, which is how marker references flat assets.
    base = norm.rsplit("/", 1)[-1]
    for asset in media:
        if base in (asset, asset.rsplit("/", 1)[-1]):
            return asset
    return None
