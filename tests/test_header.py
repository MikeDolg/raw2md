"""Tests for the YAML result header model."""

from __future__ import annotations

import datetime

import pytest

from raw2md.header import (
    HeaderParseError,
    ResultHeader,
    ResultStatus,
    build_stub,
    compute_source_hash,
    format_partial_stage,
    from_yaml_block,
    has_own_header,
    is_reserved_llm_field_value,
    render_result,
    strip_own_header,
    to_yaml_block,
)

# ---- Helpers -----------------------------------------------------------------


def _make_header(**overrides: object) -> ResultHeader:
    defaults: dict[str, object] = {
        "raw2md_version": "0.1.0",
        "source": "input.pdf",
        "engine": "marker",
        "inspection": "none",
        "post": "none",
        "converted_at": datetime.date(2026, 6, 18),
        "source_hash": "abc123",
        "status": ResultStatus.OK,
    }
    defaults.update(overrides)
    return ResultHeader(**defaults)  # type: ignore[arg-type]


# ---- compute_source_hash -----------------------------------------------------


def test_hash_is_base64url_safe() -> None:
    h = compute_source_hash(b"hello")
    assert "+" not in h
    assert "/" not in h
    assert "=" not in h


def test_hash_is_deterministic() -> None:
    assert compute_source_hash(b"data") == compute_source_hash(b"data")


def test_hash_differs_for_different_input() -> None:
    assert compute_source_hash(b"a") != compute_source_hash(b"b")


def test_hash_empty_bytes() -> None:
    h = compute_source_hash(b"")
    assert len(h) > 0


# ---- to_yaml_block / from_yaml_block round-trip ------------------------------


def test_round_trip_preserves_raw2md_version() -> None:
    header = _make_header()
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.raw2md_version == header.raw2md_version


def test_round_trip_all_permanent_fields() -> None:
    header = _make_header(status=ResultStatus.IN_PROGRESS)
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.source == "input.pdf"
    assert restored.engine == "marker"
    assert restored.inspection == "none"
    assert restored.post == "none"
    assert restored.converted_at == datetime.date(2026, 6, 18)
    assert restored.source_hash == "abc123"
    assert restored.status == ResultStatus.IN_PROGRESS


def test_round_trip_all_statuses() -> None:
    for status in ResultStatus:
        header = _make_header(status=status)
        restored = from_yaml_block(to_yaml_block(header))
        assert restored is not None
        assert restored.status == status


def test_round_trip_model_key_field() -> None:
    # PyYAML parses bare `none` as null.
    header = _make_header(engine="gemini_api", post="claude_cli")
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.engine == "gemini_api"
    assert restored.post == "claude_cli"


def test_round_trip_failed_field() -> None:
    header = _make_header(inspection="failed", post="failed")
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.inspection == "failed"
    assert restored.post == "failed"


def test_round_trip_partial_field() -> None:
    # The bare word still parses.
    header = _make_header(post="partial")
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.post == "partial"


def test_round_trip_partial_field_with_fraction() -> None:
    # A part-repaired result must not read as never repaired.
    header = _make_header(post=format_partial_stage(64, 65))
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.post == "partial (64/65)"


# ---- reserved LLM-field values -------------------------------------------


@pytest.mark.parametrize(
    "value", ["none", "failed", "partial", "partial (0/1)", "partial (64/65)"]
)
def test_reserved_values_are_reserved(value: str) -> None:
    assert is_reserved_llm_field_value(value)


@pytest.mark.parametrize(
    "value", ["gemini_api", "partial(1/2)", "partial (1/2", "partial (a/b)"]
)
def test_ordinary_model_keys_are_not_reserved(value: str) -> None:
    # A near-miss shape is an ordinary model key.
    assert not is_reserved_llm_field_value(value)


def test_block_starts_and_ends_with_delimiters() -> None:
    block = to_yaml_block(_make_header())
    assert block.startswith("---\n")
    assert block.endswith("---\n")


# ---- Extras (temporary quality-metric fields) --------------------------------


def test_extras_included_when_requested() -> None:
    header = _make_header(status=ResultStatus.IN_PROGRESS)
    header.extras["_temp_density"] = 450
    block = to_yaml_block(header, include_extras=True)
    assert "_temp_density" in block


def test_extras_excluded_by_default() -> None:
    header = _make_header()
    header.extras["_temp_density"] = 450
    block = to_yaml_block(header)
    assert "_temp_density" not in block


def test_extras_round_trip_when_included() -> None:
    header = _make_header(status=ResultStatus.IN_PROGRESS)
    header.extras["_temp_density"] = 450
    block = to_yaml_block(header, include_extras=True)
    restored = from_yaml_block(block)
    assert restored is not None
    assert restored.extras["_temp_density"] == 450


def test_extras_empty_by_default_after_round_trip() -> None:
    header = _make_header()
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.extras == {}


# ---- issues (checks that fired) -----------------------------------------------


def test_issues_default_empty() -> None:
    assert _make_header().issues == ()


def test_issues_written_when_non_empty() -> None:
    block = to_yaml_block(_make_header(issues=("headings",)))
    assert "issues:" in block
    assert "headings" in block


def test_issues_absent_when_empty() -> None:
    block = to_yaml_block(_make_header())
    assert "issues:" not in block


def test_issues_round_trip() -> None:
    header = _make_header(issues=("headings", "formulas"))
    restored = from_yaml_block(to_yaml_block(header))
    assert restored is not None
    assert restored.issues == ("headings", "formulas")


def test_issues_written_regardless_of_include_extras() -> None:
    block = to_yaml_block(_make_header(issues=("tables",)), include_extras=True)
    assert "tables" in block


def test_stub_issues_empty() -> None:
    stub = build_stub(
        source="doc.pdf",
        source_hash="abc",
    )
    assert stub.issues == ()


def test_render_carries_issues_but_not_extras() -> None:
    header = _make_header(issues=("empty_body",))
    header.extras["_temp_x"] = 99
    result = render_result(header, "", emit_yaml=True)
    assert "empty_body" in result
    assert "_temp_x" not in result


def test_from_raises_on_invalid_issues_type() -> None:
    block = to_yaml_block(_make_header()).replace(
        "status: ok", "status: ok\nissues: not_a_list"
    )
    with pytest.raises(HeaderParseError):
        from_yaml_block(block)


# ---- has_own_header ----------------------------------------------------------


def test_has_own_header_true_for_own_block() -> None:
    block = to_yaml_block(_make_header())
    assert has_own_header(block) is True


def test_has_own_header_false_for_foreign_front_matter() -> None:
    foreign = "---\ntitle: Some Book\nauthor: Alice\n---\n# Body\n"
    assert has_own_header(foreign) is False


def test_has_own_header_false_for_plain_markdown() -> None:
    assert has_own_header("# Just a heading\n\nSome text.\n") is False


def test_has_own_header_false_for_empty_string() -> None:
    assert has_own_header("") is False


def test_has_own_header_false_for_unclosed_block() -> None:
    assert has_own_header("---\nraw2md_version: 0.1.0\n") is False


# ---- strip_own_header --------------------------------------------------------


def test_strip_returns_header_and_body() -> None:
    header = _make_header()
    body = "# Chapter\n\nSome text.\n"
    md = render_result(header, body)
    restored_header, restored_body = strip_own_header(md)
    assert restored_header is not None
    assert restored_header.raw2md_version == "0.1.0"
    assert restored_body == body


def test_strip_leaves_foreign_front_matter_intact() -> None:
    text = "---\ntitle: Nope\n---\n# Body\n"
    hdr, body = strip_own_header(text)
    assert hdr is None
    assert body == text


def test_strip_empty_body() -> None:
    header = _make_header(status=ResultStatus.IN_PROGRESS)
    md = to_yaml_block(header)  # no body appended
    restored_header, body = strip_own_header(md)
    assert restored_header is not None
    assert body == ""


def test_strip_body_with_own_dashes() -> None:
    header = _make_header()
    body = "# Title\n\n---\n\nSeparator above.\n"
    md = render_result(header, body)
    restored_header, restored_body = strip_own_header(md)
    assert restored_header is not None
    assert restored_body == body


# ---- render_result -----------------------------------------------------------


def test_render_with_yaml_starts_with_delimiter() -> None:
    result = render_result(_make_header(), "# Title\n", emit_yaml=True)
    assert result.startswith("---\n")
    assert "raw2md_version" in result


def test_render_with_yaml_body_appended_directly() -> None:
    body = "# Title\n"
    result = render_result(_make_header(), body, emit_yaml=True)
    assert result.endswith("# Title\n")


def test_render_no_yaml_returns_body_only() -> None:
    body = "# Title\n"
    result = render_result(_make_header(), body, emit_yaml=False)
    assert result == body
    assert "raw2md_version" not in result


def test_render_drops_extras() -> None:
    header = _make_header()
    header.extras["_temp_x"] = 99
    result = render_result(header, "", emit_yaml=True)
    assert "_temp_x" not in result


def test_render_empty_body_no_yaml() -> None:
    result = render_result(_make_header(), "", emit_yaml=False)
    assert result == ""


# ---- build_stub --------------------------------------------------------------


def test_stub_status_is_in_progress() -> None:
    stub = build_stub(
        source="doc.pdf",
        source_hash="abc",
    )
    assert stub.status == ResultStatus.IN_PROGRESS


def test_stub_llm_fields_default_to_none_string() -> None:
    stub = build_stub(
        source="doc.pdf",
        source_hash="abc",
    )
    assert stub.engine == "marker"
    assert stub.inspection == "none"
    assert stub.post == "none"


def test_stub_with_explicit_llm_models() -> None:
    stub = build_stub(
        source="doc.pdf",
        source_hash="abc",
        engine="gemini_api",
        post="claude_cli",
    )
    assert stub.engine == "gemini_api"
    assert stub.post == "claude_cli"
    assert stub.inspection == "none"


def test_stub_source_and_engine() -> None:
    stub = build_stub(
        source="book.djvu",
        source_hash="xyz",
        engine="gemini_api",
    )
    assert stub.source == "book.djvu"
    assert stub.engine == "gemini_api"
    assert stub.source_hash == "xyz"


def test_stub_extras_empty() -> None:
    stub = build_stub(
        source="doc.pdf",
        source_hash="abc",
    )
    assert stub.extras == {}


# ---- from_yaml_block error handling ------------------------------------------


def test_from_returns_none_for_no_front_matter() -> None:
    assert from_yaml_block("# No front matter\n") is None


def test_from_returns_none_for_foreign_front_matter() -> None:
    assert from_yaml_block("---\ntitle: no version here\n---\n") is None


def test_from_raises_on_invalid_status() -> None:
    block = to_yaml_block(_make_header()).replace("status: ok", "status: weird_value")
    with pytest.raises(HeaderParseError):
        from_yaml_block(block)


def test_from_returns_none_for_empty_string() -> None:
    assert from_yaml_block("") is None


def test_from_raises_on_missing_required_field() -> None:
    block = to_yaml_block(_make_header())
    block_no_inspection = (
        "\n".join(
            line for line in block.splitlines() if not line.startswith("inspection:")
        )
        + "\n"
    )
    with pytest.raises(HeaderParseError):
        from_yaml_block(block_no_inspection)


def test_from_raises_on_invalid_converted_at_type() -> None:
    block = to_yaml_block(_make_header()).replace(
        "converted_at: 2026-06-18", "converted_at: 42"
    )
    with pytest.raises(HeaderParseError):
        from_yaml_block(block)


def test_extras_collision_with_permanent_field_is_ignored() -> None:
    header = _make_header(status=ResultStatus.IN_PROGRESS)
    header.extras["status"] = "bad"  # attempt to overwrite permanent field
    block = to_yaml_block(header, include_extras=True)
    restored = from_yaml_block(block)
    assert restored is not None
    assert restored.status == ResultStatus.IN_PROGRESS


def test_crlf_front_matter_is_recognized() -> None:
    # A file opened with newline='' may carry CRLF.
    block_lf = to_yaml_block(_make_header())
    block_crlf = block_lf.replace("\n", "\r\n")
    restored = from_yaml_block(block_crlf)
    assert restored is not None
    assert restored.raw2md_version == "0.1.0"
