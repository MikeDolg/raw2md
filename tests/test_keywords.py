"""Tests for the structural dictionary and the `keywords` subcommand."""

from dataclasses import fields
from pathlib import Path

import pytest

from raw2md.keywords import (
    SECTIONS,
    Keywords,
    KeywordsError,
    default_keywords,
    default_keywords_text,
    load_keywords,
    run_keywords_command,
)
from raw2md.paths import keywords_file

# A minimal file with every section present, for the schema tests to vary.
_MINIMAL = """\
contents_heading:
  - contents
contents_page_label:
  - page
top_level_sections:
  - appendix*
heading_minor_words:
  - on
  - "no"
caption_labels:
  - рис.
image_placeholders:
  - изображен*
"""


def write_keywords(home: Path, text: str) -> Path:
    path = keywords_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- The shipped dictionary --------------------------------------------------


def test_shipped_file_parses() -> None:
    keywords = default_keywords()
    for name in SECTIONS:
        assert keywords.section(name), f"section '{name}' ships empty"


def test_shipped_file_keeps_its_comments() -> None:
    # A byte-for-byte copy keeps the section comments the user reads.
    text = default_keywords_text()
    for name in SECTIONS:
        assert f"\n{name}:" in text
    assert text.count("#") > len(SECTIONS)


def test_shipped_file_reads_the_yaml_bool_words_as_words() -> None:
    # YAML 1.1 resolves `on` to True unless the bool rule is dropped.
    assert "on" in default_keywords().heading_minor_words


def test_the_named_sections_are_the_fields_of_the_parsed_file() -> None:
    assert tuple(field.name for field in fields(Keywords)) == SECTIONS
    with pytest.raises(KeyError):
        default_keywords().section("not_a_section")


# --- Loading ------------------------------------------------------------------


def test_a_missing_file_falls_back_to_the_shipped_list(home: Path) -> None:
    assert load_keywords(keywords_file()) == default_keywords()


def test_a_copy_replaces_the_shipped_list_whole(home: Path) -> None:
    path = write_keywords(home, _MINIMAL)
    keywords = load_keywords(path)
    assert keywords.contents_heading == ("contents",)
    assert keywords.caption_labels == ("рис.",)


def test_bool_words_load_as_words(home: Path) -> None:
    path = write_keywords(home, _MINIMAL)
    assert load_keywords(path).heading_minor_words == ("on", "no")


def test_a_section_emptied_of_its_records_is_allowed(home: Path) -> None:
    # An empty key turns a rule's vocabulary off.
    path = write_keywords(home, _MINIMAL.replace("  - page\n", ""))
    assert load_keywords(path).contents_page_label == ()


def test_an_empty_list_of_records_is_allowed(home: Path) -> None:
    path = write_keywords(
        home,
        _MINIMAL.replace(
            "contents_page_label:\n  - page\n", "contents_page_label: []\n"
        ),
    )
    assert load_keywords(path).contents_page_label == ()


def test_broken_yaml_is_reported(home: Path) -> None:
    path = write_keywords(home, "contents_heading: [unclosed\n")
    with pytest.raises(KeywordsError, match="invalid YAML"):
        load_keywords(path)


# --- Schema -------------------------------------------------------------------


def test_top_level_must_be_a_mapping(home: Path) -> None:
    path = write_keywords(home, "- contents\n")
    with pytest.raises(KeywordsError, match="mapping"):
        load_keywords(path)


def test_an_unknown_section_is_rejected(home: Path) -> None:
    path = write_keywords(home, _MINIMAL + "chapter_words:\n  - chapter\n")
    with pytest.raises(KeywordsError, match="unknown section"):
        load_keywords(path)


def test_a_missing_section_is_rejected(home: Path) -> None:
    path = write_keywords(home, _MINIMAL.replace("caption_labels:\n  - рис.\n", ""))
    with pytest.raises(KeywordsError, match="'caption_labels' is missing"):
        load_keywords(path)


def test_a_section_must_be_a_list(home: Path) -> None:
    path = write_keywords(
        home,
        _MINIMAL.replace(
            "contents_page_label:\n  - page\n", "contents_page_label: page\n"
        ),
    )
    with pytest.raises(KeywordsError, match="must be a list"):
        load_keywords(path)


def test_a_record_must_be_a_word(home: Path) -> None:
    # An unquoted number resolves to a float.
    path = write_keywords(home, _MINIMAL.replace("  - page\n", "  - 1.2\n"))
    with pytest.raises(KeywordsError, match="must be a word"):
        load_keywords(path)


def test_a_record_with_surrounding_space_is_rejected(home: Path) -> None:
    path = write_keywords(home, _MINIMAL.replace("  - page\n", '  - " page"\n'))
    with pytest.raises(KeywordsError, match="no leading or trailing space"):
        load_keywords(path)


def test_an_empty_record_is_rejected(home: Path) -> None:
    path = write_keywords(home, _MINIMAL.replace("  - page\n", '  - ""\n'))
    with pytest.raises(KeywordsError, match="no leading or trailing space"):
        load_keywords(path)


def test_a_prefix_marker_inside_a_record_is_rejected(home: Path) -> None:
    path = write_keywords(home, _MINIMAL.replace("  - page\n", "  - pa*ge\n"))
    with pytest.raises(KeywordsError, match="at its end only"):
        load_keywords(path)


def test_a_record_of_the_marker_alone_is_rejected(home: Path) -> None:
    path = write_keywords(home, _MINIMAL.replace("  - page\n", '  - "*"\n'))
    with pytest.raises(KeywordsError, match="holds no word"):
        load_keywords(path)


# --- The subcommand -----------------------------------------------------------


def test_path_prints_the_path(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_keywords_command(["path"]) == 0
    assert capsys.readouterr().out.strip() == str(keywords_file())


def test_show_prints_the_file(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_keywords(home, _MINIMAL)
    assert run_keywords_command(["show"]) == 0
    assert "contents_heading" in capsys.readouterr().out


def test_show_reports_a_missing_file(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_keywords_command(["show"]) == 0
    assert "does not exist" in capsys.readouterr().err


def test_check_accepts_a_sound_file(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_keywords(home, _MINIMAL)
    assert run_keywords_command(["check"]) == 0
    assert "OK" in capsys.readouterr().out


def test_check_rejects_a_broken_file(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_keywords(home, _MINIMAL.replace("  - page\n", "  - pa*ge\n"))
    assert run_keywords_command(["check"]) == 2
    assert "invalid" in capsys.readouterr().err


def test_check_on_a_missing_file_says_the_shipped_list_applies(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_keywords_command(["check"]) == 0
    assert "shipped dictionary" in capsys.readouterr().err


def test_an_unknown_action_is_an_argument_error(home: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_keywords_command(["reset"])
    assert exc_info.value.code == 2
