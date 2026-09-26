"""Tests for the prompts.yaml schema, loader, defaults, and subcommand."""

from pathlib import Path

import pytest
import yaml

from raw2md.paths import prompts_file
from raw2md.prompts import (
    DEFAULT_PROMPTS,
    Prompts,
    PromptsError,
    PromptSet,
    _parse_prompts,
    default_prompts,
    default_prompts_text,
    load_prompts,
    resolve_prompt,
    run_prompts_command,
)

# --- Defaults ---------------------------------------------------------------


def test_default_prompts_parses() -> None:
    prompts = default_prompts()
    assert prompts.ocr.default
    assert prompts.inspection.default
    assert prompts.post.default
    assert prompts.post.overrides == {}


def test_inspection_default_instructs_math_repair() -> None:
    prompt = default_prompts().inspection.default
    assert r"\left" in prompt
    assert r"\right" in prompt
    assert "KaTeX" in prompt
    assert "$...$" in prompt
    assert "$$...$$" in prompt


def test_inspection_default_asks_for_one_edit_shape_only() -> None:
    # One old/new shape and no typed defect report; counted on the JSON keys,
    # since the prose names the fields too.
    prompt = default_prompts().inspection.default
    assert prompt.count('"old":') == 1
    assert prompt.count('"new":') == 1
    assert '"flag":' not in prompt


def test_inspection_default_asks_for_the_changed_part() -> None:
    # A quote must arrive byte for byte, and a fragment names its place only by
    # standing on the line once.
    prompt = default_prompts().inspection.default
    assert '"old": "<the part of the line that changes>"' in prompt
    assert "out of both fields" in prompt
    assert "stand there exactly once" in prompt
    assert "never inside a word" in prompt


def test_inspection_default_covers_the_recognition_loop() -> None:
    prompt = default_prompts().inspection.default
    assert "recognition loop" in prompt
    assert "formula as broken" in prompt


def test_inspection_default_names_the_masked_formula() -> None:
    # A sound span goes out as a placeholder and must come back as it went.
    prompt = default_prompts().inspection.default
    assert "⟦valid formula N⟧" in prompt
    assert "not yours to" in prompt
    assert "another number" in prompt


def test_inspection_default_holds_the_source_boundary() -> None:
    # A source edit and a homoglyph repair look alike; only the prompt holds
    # the boundary.
    prompt = default_prompts().inspection.default
    assert "do not correct the document" in prompt
    for term in ("misspell", "lower case", "punctuation", "alphabet"):
        assert term in prompt, f"the prompt does not name {term}"


def test_inspection_default_holds_the_layout_boundary() -> None:
    # A printed line break is layout; the witness check is only the backstop.
    prompt = default_prompts().inspection.default
    assert "layout" in prompt
    assert "line break" in prompt
    assert "hyphen" in prompt


def test_post_default_holds_the_formula_boundary() -> None:
    # Post has no source, so it may not change what a span holds.
    prompt = default_prompts().post.default
    assert "never change what is inside one" in prompt


def test_post_default_reads_the_defect_off_the_zone_label() -> None:
    # The label in front of a zone names the defect; no comment is taught.
    prompt = default_prompts().post.default
    assert "label in front of" in prompt
    assert "<!--" not in prompt


def test_post_default_licenses_the_markup_of_a_broken_formula() -> None:
    # The narrower licence: markup moves, characters do not, and an open sizing
    # command closes with the invisible delimiter.
    prompt = default_prompts().post.default
    assert "does not render" in prompt
    assert r"\right." in prompt
    assert "symbol, command or word is added, dropped or replaced" in prompt


def test_ocr_default_instructs_caption_only_for_figures() -> None:
    # The route extracts no media, so a figure's caption is transcribed.
    prompt = default_prompts().ocr.default
    assert "caption" in prompt
    assert "do not describe" in prompt.lower()
    assert "link" in prompt.lower()


def test_ocr_default_instructs_skip_page_furniture() -> None:
    # Cleaning cannot drop page furniture that OCR already wrote into the body.
    prompt = default_prompts().ocr.default
    assert "running header or footer" in prompt
    assert "page number" in prompt
    assert "rule" in prompt
    assert "none of it is the page's content" in prompt


def test_ocr_default_keeps_chapter_opening_heading() -> None:
    # A chapter opening sits where a running header would.
    prompt = default_prompts().ocr.default
    assert "repeats from page to page" in prompt
    assert "opens a chapter or a section on this page is not a running" in prompt
    assert "with its label and number" in prompt


def test_ocr_default_keeps_short_first_body_line() -> None:
    # A lone word ending the previous page's sentence looks like a header.
    prompt = default_prompts().ocr.default
    assert "a running\nheader never continues a sentence" in prompt
    assert "Keep the first line of the page" in prompt


def test_default_text_round_trips() -> None:
    loaded = yaml.safe_load(default_prompts_text())
    assert loaded == DEFAULT_PROMPTS


# --- Loading ----------------------------------------------------------------


def test_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    assert load_prompts(tmp_path / "absent.yaml") == default_prompts()


def test_valid_file_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    path.write_text(default_prompts_text(), encoding="utf-8")
    assert load_prompts(path).ocr.default == default_prompts().ocr.default


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "prompts.yaml"
    path.write_text(": invalid: yaml: [\n", encoding="utf-8")
    with pytest.raises(PromptsError):
        load_prompts(path)


# --- Schema validation ------------------------------------------------------


def test_top_level_must_be_mapping() -> None:
    with pytest.raises(PromptsError):
        _parse_prompts(["ocr", "inspection", "post"])


def test_unknown_operation_rejected() -> None:
    data = {
        "ocr": {"default": "x"},
        "inspection": {"default": "x"},
        "post": {"default": "x"},
        "translation": {"default": "x"},
    }
    with pytest.raises(PromptsError):
        _parse_prompts(data)


def test_missing_operation_raises() -> None:
    data = {
        "ocr": {"default": "x"},
        "inspection": {"default": "x"},
        # post is absent
    }
    with pytest.raises(PromptsError):
        _parse_prompts(data)


def test_operation_must_be_mapping() -> None:
    data = {
        "ocr": "just a string",
        "inspection": {"default": "x"},
        "post": {"default": "x"},
    }
    with pytest.raises(PromptsError):
        _parse_prompts(data)


def test_default_must_be_nonempty_string() -> None:
    data = {
        "ocr": {"default": ""},
        "inspection": {"default": "x"},
        "post": {"default": "x"},
    }
    with pytest.raises(PromptsError):
        _parse_prompts(data)


def test_override_must_be_nonempty_string() -> None:
    data = {
        "ocr": {"default": "x"},
        "inspection": {"default": "x"},
        "post": {"default": "x", "claude_cli": 42},
    }
    with pytest.raises(PromptsError):
        _parse_prompts(data)


def test_override_key_must_be_nonempty_string() -> None:
    data = {
        "ocr": {"default": "x"},
        "inspection": {"default": "x"},
        "post": {"default": "x", 123: "y"},
    }
    with pytest.raises(PromptsError):
        _parse_prompts(data)


def test_override_empty_string_key_rejected() -> None:
    data = {
        "ocr": {"default": "x"},
        "inspection": {"default": "x"},
        "post": {"default": "x", "": "y"},
    }
    with pytest.raises(PromptsError):
        _parse_prompts(data)


# --- Layers and overrides ---------------------------------------------------


def test_resolve_returns_default_when_no_override() -> None:
    prompts = default_prompts()
    result = resolve_prompt(prompts, "ocr", "gemini_api")
    assert result == prompts.ocr.default


def test_resolve_returns_override_when_present() -> None:
    custom = "custom post prompt\n"
    post_set = PromptSet(default="default\n", overrides={"claude_cli": custom})
    prompts = Prompts(
        ocr=PromptSet(default="ocr\n", overrides={}),
        inspection=PromptSet(default="insp\n", overrides={}),
        post=post_set,
    )
    assert resolve_prompt(prompts, "post", "claude_cli") == custom
    assert resolve_prompt(prompts, "post", "gemini_api") == "default\n"


def test_override_loaded_from_yaml(tmp_path: Path) -> None:
    content = (
        "ocr:\n  default: ocr default\n"
        "inspection:\n  default: insp default\n"
        "post:\n  default: post default\n  claude_cli: post override\n"
    )
    path = tmp_path / "prompts.yaml"
    path.write_text(content, encoding="utf-8")
    prompts = load_prompts(path)
    assert resolve_prompt(prompts, "post", "claude_cli") == "post override"
    assert resolve_prompt(prompts, "post", "gemini_api") == "post default"


# --- `prompts` subcommand ---------------------------------------------------


def test_path_prints_location(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_prompts_command(["path"]) == 0
    assert capsys.readouterr().out.strip() == str(prompts_file())


def test_show_prints_contents(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = prompts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_prompts_text(), encoding="utf-8")
    assert run_prompts_command(["show"]) == 0
    assert capsys.readouterr().out == default_prompts_text()


def test_show_missing_file_hints(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_prompts_command(["show"]) == 0
    assert "raw2md init" in capsys.readouterr().err


def test_unknown_action_is_argument_error(home: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_prompts_command(["nonsense"])
    assert exc_info.value.code == 2


# --- `prompts check` ----------------------------------------------------------


def test_check_missing_file_is_not_error(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_prompts_command(["check"]) == 0
    assert "does not exist" in capsys.readouterr().err


def test_check_valid_file_is_ok(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = prompts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_prompts_text(), encoding="utf-8")
    assert run_prompts_command(["check"]) == 0
    assert "OK" in capsys.readouterr().out


def test_check_malformed_yaml_is_argument_error(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = prompts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(": invalid: yaml: [\n", encoding="utf-8")
    assert run_prompts_command(["check"]) == 2
    assert "invalid" in capsys.readouterr().err
