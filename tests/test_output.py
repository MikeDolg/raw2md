"""Tests for the output writer: naming, collisions, links."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from urllib.parse import unquote

import pytest

from raw2md.header import build_stub, to_yaml_block
from raw2md.output import (
    OutputCollisionError,
    OutputTarget,
    _fsync_dir,
    atomic_write_text,
    debug_dir_for,
    encode_link_path,
    ensure_writable,
    existing_md,
    is_own_result,
    media_link,
    resolve_output_target,
    write_md,
)


def write_own_result(path: Path) -> None:
    """Write an md carrying raw2md's own header, as a prior run would leave."""
    stub = build_stub("x.pdf", source_hash="hash")
    path.write_text(to_yaml_block(stub) + "body\n", encoding="utf-8")


# ---- ensure_writable source protection --------------------------------------


def test_ensure_writable_refuses_to_delete_source(tmp_path: Path) -> None:
    src = tmp_path / "book.pdf"
    src.write_bytes(b"x")
    target = OutputTarget(
        md_path=tmp_path / "book.pdf.md", media_dir=tmp_path / "book.pdf"
    )
    with pytest.raises(OutputCollisionError):
        ensure_writable(target, protect=src)
    assert src.exists()


def test_ensure_writable_refuses_source_ancestor_dir(tmp_path: Path) -> None:
    # An ancestor output dir can target the source's own parent directory.
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    src = book_dir / "book.pdf"
    src.write_bytes(b"x")
    target = OutputTarget(md_path=tmp_path / "book.md", media_dir=book_dir)
    with pytest.raises(OutputCollisionError):
        ensure_writable(target, protect=src)
    assert src.exists()


# ---- resolve_output_target ---------------------------------------------------


def test_default_layout_next_to_source() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    assert target.md_path == Path("/docs/input.md")
    assert target.media_dir == Path("/docs/input")


def test_md_and_media_share_parent() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    assert target.md_path.parent == target.media_dir.parent


def test_name_preserves_source_case() -> None:
    target = resolve_output_target(Path("/docs/MyBook.PDF"))
    assert target.md_path == Path("/docs/MyBook.md")
    assert target.media_dir == Path("/docs/MyBook")


def test_output_dir_redirects_result() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"), output_dir=Path("/out"))
    assert target.md_path == Path("/out/input.md")
    assert target.media_dir == Path("/out/input")


def test_include_extension_folds_suffix_into_name() -> None:
    pdf = resolve_output_target(Path("/docs/input.pdf"), include_extension=True)
    docx = resolve_output_target(Path("/docs/input.docx"), include_extension=True)
    assert pdf.md_path == Path("/docs/input.pdf.md")
    assert pdf.media_dir == Path("/docs/input.pdf")
    assert docx.md_path == Path("/docs/input.docx.md")
    assert docx.media_dir == Path("/docs/input.docx")
    assert pdf.md_path != docx.md_path


def test_md_in_place_uses_cleaned_suffix() -> None:
    target = resolve_output_target(Path("/docs/notes.md"))
    assert target.md_path == Path("/docs/notes_cleaned.md")
    assert target.media_dir == Path("/docs/notes_cleaned")


def test_md_in_place_ignores_include_extension() -> None:
    # `_cleaned` already disambiguates, so no `notes.md_cleaned.md`.
    target = resolve_output_target(Path("/docs/notes.md"), include_extension=True)
    assert target.md_path == Path("/docs/notes_cleaned.md")
    assert target.media_dir == Path("/docs/notes_cleaned")


def test_md_extension_recognized_case_insensitively() -> None:
    target = resolve_output_target(Path("/docs/notes.MD"))
    assert target.md_path == Path("/docs/notes_cleaned.md")


def test_md_with_output_dir_keeps_plain_name() -> None:
    target = resolve_output_target(Path("/docs/notes.md"), output_dir=Path("/out"))
    assert target.md_path == Path("/out/notes.md")
    assert target.media_dir == Path("/out/notes")


def test_source_without_extension() -> None:
    target = resolve_output_target(Path("/docs/README"))
    assert target.md_path == Path("/docs/README.md")
    assert target.media_dir == Path("/docs/README")


def test_trailing_dot_in_stem_is_stripped() -> None:
    # Win32 drops trailing dots and spaces at mkdir, so the name matches disk.
    target = resolve_output_target(Path("/docs/Ivanov A.V..pdf"))
    assert target.md_path == Path("/docs/Ivanov A.V.md")
    assert target.media_dir == Path("/docs/Ivanov A.V")


def test_trailing_spaces_in_stem_are_stripped() -> None:
    target = resolve_output_target(Path("/docs/input .pdf"))
    assert target.md_path == Path("/docs/input.md")
    assert target.media_dir == Path("/docs/input")


def test_ordinary_names_are_unchanged() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    assert target.md_path == Path("/docs/input.md")
    assert target.media_dir == Path("/docs/input")


def test_trailing_dot_stripped_with_include_extension() -> None:
    # include_extension uses the full name, where the trailing dot survives.
    target = resolve_output_target(Path("/docs/README."), include_extension=True)
    assert target.md_path == Path("/docs/README.md")
    assert target.media_dir == Path("/docs/README")


def test_trailing_dot_stripped_for_md_in_place() -> None:
    target = resolve_output_target(Path("/docs/notes. .md"))
    assert target.md_path == Path("/docs/notes_cleaned.md")
    assert target.media_dir == Path("/docs/notes_cleaned")


def test_collision_detection_uses_sanitized_name(tmp_path: Path) -> None:
    (tmp_path / "book.md").write_text("x")
    target = resolve_output_target(tmp_path / "book. .pdf")
    assert existing_md(target) is not None


def test_all_dots_stem_falls_back_instead_of_collapsing(tmp_path: Path) -> None:
    # An empty stem would make the media folder the output dir itself.
    out = tmp_path / "out"
    target = resolve_output_target(tmp_path / "....pdf", output_dir=out)
    assert target.media_dir != out
    assert target.media_dir.parent == out


# ---- media_link --------------------------------------------------------------


def test_media_link_is_relative_with_forward_slash() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    assert media_link(target, "img-1.png") == "input/img-1.png"


def test_media_link_normalizes_backslashes() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    assert media_link(target, "sub\\img-1.png") == "input/sub/img-1.png"


def test_media_link_strips_leading_slash() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    assert media_link(target, "/img-1.png") == "input/img-1.png"


def test_media_link_uses_cleaned_folder_for_md() -> None:
    target = resolve_output_target(Path("/docs/notes.md"))
    assert media_link(target, "img-1.png") == "notes_cleaned/img-1.png"


def test_media_link_percent_encodes_space_in_folder_name() -> None:
    target = resolve_output_target(Path("/docs/My Book.pdf"))
    assert media_link(target, "img-1.png") == "My%20Book/img-1.png"


def test_media_link_percent_encodes_parens_in_asset_name() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    assert media_link(target, "fig (1).png") == "input/fig%20%281%29.png"


def test_media_link_keeps_cyrillic_literal_and_readable() -> None:
    target = resolve_output_target(Path("/docs/input.pdf"))
    link = media_link(target, "рисунок.png")
    assert link == "input/рисунок.png"
    assert unquote(link) == link


# ---- encode_link_path ---------------------------------------------------------


def test_encode_link_path_preserves_slash_separator() -> None:
    assert encode_link_path("input/sub dir/img.png") == "input/sub%20dir/img.png"


def test_encode_link_path_escapes_literal_percent() -> None:
    # `path` is never pre-encoded, so a literal "%" is escaped and the name
    # round-trips under `unquote`.
    encoded = encode_link_path("a%2Fb.png")
    assert encoded == "a%252Fb.png"
    assert unquote(encoded) == "a%2Fb.png"


def test_encode_link_path_escapes_angle_brackets_and_parens() -> None:
    assert encode_link_path("fig<1>(a).png") == "fig%3C1%3E%28a%29.png"


def test_encode_link_path_escapes_control_bytes() -> None:
    assert encode_link_path("a\tb\nc") == "a%09b%0Ac"


def test_encode_link_path_escapes_fragment_and_query_delimiters() -> None:
    # A renderer resolves the link as a URL, where `#` and `?` start a fragment
    # and a query.
    assert encode_link_path("fig#1.png") == "fig%231.png"
    assert encode_link_path("fig?a=1.png") == "fig%3Fa=1.png"


def test_encode_link_path_escapes_colon_before_first_slash() -> None:
    # A literal ":" reads as a URI scheme.
    assert encode_link_path("scan:v1/img.png") == "scan%3Av1/img.png"


def test_encode_link_path_escapes_unicode_whitespace() -> None:
    # Unicode whitespace ends an IMAGE_RE match too.
    assert encode_link_path("fig\xa01.png") == "fig%C2%A01.png"


def test_encode_link_path_leaves_other_ascii_punctuation_literal() -> None:
    # Punctuation that breaks nothing stays literal.
    assert encode_link_path("fig's,notes!@home;.png") == "fig's,notes!@home;.png"


# ---- existing_md / is_own_result / ensure_writable ----------------------------


def _target_in(tmp_path: Path, name: str = "input.pdf") -> OutputTarget:
    return resolve_output_target(tmp_path / name)


def test_no_entry_on_clean_directory(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    assert existing_md(target) is None
    ensure_writable(target)


def test_own_result_is_removed(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    write_own_result(target.md_path)
    ensure_writable(target)
    assert not target.md_path.exists()


def test_foreign_md_refuses_the_file(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    target.md_path.write_text("someone else's notes", encoding="utf-8")
    with pytest.raises(OutputCollisionError, match=r"input\.md"):
        ensure_writable(target)
    assert target.md_path.read_text(encoding="utf-8") == "someone else's notes"


def test_foreign_md_refuses_before_the_media_folder_is_cleared(
    tmp_path: Path,
) -> None:
    # The refusal is the whole file's, so nothing else is removed.
    target = _target_in(tmp_path)
    target.md_path.write_text("foreign", encoding="utf-8")
    target.media_dir.mkdir()
    with pytest.raises(OutputCollisionError):
        ensure_writable(target)
    assert target.media_dir.exists()


def test_media_dir_alone_never_blocks_the_file(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    target.media_dir.mkdir()
    (target.media_dir / "stale.png").write_bytes(b"x")
    ensure_writable(target)
    assert not target.media_dir.exists()


def test_md_matched_case_insensitively(tmp_path: Path) -> None:
    target = _target_in(tmp_path)  # input.md
    # A differently-cased name collides on Windows.
    (tmp_path / "INPUT.md").write_text("old", encoding="utf-8")
    match = existing_md(target)
    assert match is not None
    assert match.name == "INPUT.md"


def test_differently_cased_own_result_is_removed(tmp_path: Path) -> None:
    target = _target_in(tmp_path)  # input.md
    write_own_result(tmp_path / "INPUT.md")
    ensure_writable(target)
    assert existing_md(target) is None


def test_is_own_result_reads_the_header(tmp_path: Path) -> None:
    own = tmp_path / "own.md"
    write_own_result(own)
    foreign = tmp_path / "foreign.md"
    foreign.write_text("---\ntitle: notes\n---\n", encoding="utf-8")
    assert is_own_result(own) is True
    assert is_own_result(foreign) is False


def test_is_own_result_false_for_unreadable_bytes(tmp_path: Path) -> None:
    path = tmp_path / "binary.md"
    path.write_bytes(b"\xff\xfe\x00\x00not utf-8")
    assert is_own_result(path) is False


# ---- extra (--debug folder) handling -----------------------------------------


def test_debug_dir_named_after_result_stem(tmp_path: Path) -> None:
    target = _target_in(tmp_path)  # input.md / input/
    assert debug_dir_for(target) == tmp_path / "input.debug"


def test_extra_not_touched_when_omitted(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    debug_dir_for(target).mkdir()
    # Without `extra`, a same-named folder is not this call's concern.
    ensure_writable(target)
    assert debug_dir_for(target).exists()


def test_extra_folder_is_cleared(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    extra = debug_dir_for(target)
    extra.mkdir()
    (extra / "stale.md").write_text("old", encoding="utf-8")
    ensure_writable(target, extra=extra)
    assert not extra.exists()


# ---- write_md ----------------------------------------------------------------


def test_write_md_creates_file_with_content(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    write_md(target, "# Title\n\nText.\n")
    assert target.md_path.read_text(encoding="utf-8") == "# Title\n\nText.\n"


def test_write_md_no_bom_and_no_crlf(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    write_md(target, "a\nb\n")
    raw = target.md_path.read_bytes()
    assert raw == b"a\nb\n"  # exact bytes: no BOM, no CRLF translation


def test_write_md_creates_missing_output_dir(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "out"
    target = resolve_output_target(tmp_path / "input.pdf", output_dir=out)
    write_md(target, "x\n")
    assert target.md_path.read_text(encoding="utf-8") == "x\n"


def test_write_md_replaces_existing_target(tmp_path: Path) -> None:
    # The second write replaces the first in place, also on Windows, where a
    # plain rename refuses an existing target.
    target = _target_in(tmp_path)
    write_md(target, "stub\n")
    write_md(target, "final\n")
    assert target.md_path.read_text(encoding="utf-8") == "final\n"


def test_write_md_leaves_no_temp_file_after_success(tmp_path: Path) -> None:
    target = _target_in(tmp_path)
    write_md(target, "content\n")
    assert list(tmp_path.iterdir()) == [target.md_path]


def test_write_md_failure_leaves_previous_result_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _target_in(tmp_path)
    target.md_path.write_text("previous terminal result\n", encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> int:
        raise OSError("disk full")

    # Only the replace touches the target, so a failed write leaves it intact.
    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):  # noqa: PT011 -- the injected failure is any OSError; recovery does not depend on the subtype
        write_md(target, "new content\n")
    assert list(tmp_path.iterdir()) == [target.md_path]
    assert target.md_path.read_text(encoding="utf-8") == "previous terminal result\n"


def test_write_md_does_not_touch_a_file_named_like_a_fixed_temp_path(
    tmp_path: Path,
) -> None:
    target = _target_in(tmp_path)
    # The random-suffixed temp name never collides with a foreign `.tmp` file.
    foreign = target.md_path.with_name(target.md_path.name + ".tmp")
    foreign.write_text("someone else's file\n", encoding="utf-8")
    write_md(target, "content\n")
    assert foreign.read_text(encoding="utf-8") == "someone else's file\n"
    assert target.md_path.read_text(encoding="utf-8") == "content\n"


def test_atomic_write_text_creates_missing_parent_dir(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "out" / "file.txt"
    atomic_write_text(path, "hello\n")
    assert path.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_text_removes_temp_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.md"

    def boom(_self: Path, _target: object) -> None:
        raise OSError("target is locked")

    # A failed replace leaves no temp file either.
    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError):  # noqa: PT011 -- the injected failure is any OSError; recovery does not depend on the subtype
        atomic_write_text(path, "content\n")
    assert list(tmp_path.iterdir()) == []
    assert not path.exists()


def test_atomic_write_text_refuses_to_clobber_a_colliding_temp_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.md"
    colliding_name = f"{path.name}.deadbeef.tmp"
    (tmp_path / colliding_name).write_text("someone else's file\n", encoding="utf-8")
    # Exclusive creation refuses a colliding temp name.
    monkeypatch.setattr(secrets, "token_hex", lambda _n: "deadbeef")
    with pytest.raises(FileExistsError):
        atomic_write_text(path, "content\n")
    assert (tmp_path / colliding_name).read_text(encoding="utf-8") == (
        "someone else's file\n"
    )
    assert not path.exists()


def test_fsync_dir_tolerates_unsupported_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_fd: int) -> None:
        raise OSError("fsync not supported on this filesystem")

    # Some filesystems refuse fsync on a directory; the rename is durable
    # already.
    monkeypatch.setattr(os, "fsync", boom)
    _fsync_dir(tmp_path)  # must not raise


def test_fsync_dir_tolerates_unopenable_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_path: Path, _flags: int) -> int:
        raise OSError("cannot open directory")

    monkeypatch.setattr(os, "open", boom)
    _fsync_dir(tmp_path)  # must not raise
