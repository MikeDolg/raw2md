"""keywords.yaml: the structural vocabulary, its loader, and the subcommand.

Six rules recognize a part of a document by the word a page prints for it;
`raw2md.mdtext.words.word_pattern` turns a section's records into one
pattern. The words belong to the documents, not to the tool, so they live in
the shipped keywords.yaml.
`raw2md init` copies it to ~/.raw2md, and that copy replaces the shipped list
whole.

The file is read without the YAML 1.1 bool rule: `on` in the minor words
would otherwise load as True and be lost.
"""

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from raw2md.exit_codes import ExitCode
from raw2md.mdtext.words import PREFIX_MARKER
from raw2md.paths import keywords_file
from raw2md.service import edit_file, parse_file_action, show_file

# The sections of the file, one per rule that reads words.
SECTIONS = (
    "contents_heading",
    "contents_page_label",
    "top_level_sections",
    "heading_minor_words",
    "caption_labels",
    "image_placeholders",
)

_BUNDLED = Path(__file__).with_name("keywords.yaml")

_BOOL_TAG = "tag:yaml.org,2002:bool"


class KeywordsError(Exception):
    """keywords.yaml is malformed, or a section or record has a wrong shape."""


@dataclass(frozen=True)
class Keywords:
    """The records of each section, as the file writes them."""

    contents_heading: tuple[str, ...]
    contents_page_label: tuple[str, ...]
    top_level_sections: tuple[str, ...]
    heading_minor_words: tuple[str, ...]
    caption_labels: tuple[str, ...]
    image_placeholders: tuple[str, ...]

    def section(self, name: str) -> tuple[str, ...]:
        """The records of one section, addressed by its name in the file."""
        if name not in SECTIONS:
            raise KeyError(name)
        records: tuple[str, ...] = getattr(self, name)
        return records


class _StringLoader(yaml.SafeLoader):
    """SafeLoader that reads `on`, `off`, `yes`, and `no` as the words they are."""


# A fresh mapping: filtering the shared table in place would reach every
# SafeLoader.
_StringLoader.yaml_implicit_resolvers = {
    first: [(tag, pattern) for tag, pattern in resolvers if tag != _BOOL_TAG]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def default_keywords_text() -> str:
    """The shipped dictionary as it stands, the text `raw2md init` copies."""
    return _BUNDLED.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def default_keywords() -> Keywords:
    """The shipped dictionary, parsed once."""
    return _parse_keywords(_load_yaml(default_keywords_text(), _BUNDLED))


def load_keywords(path: Path) -> Keywords:
    """Load the dictionary from `path`, falling back to the shipped one.

    A missing file is not an error: the shipped list applies until `raw2md init`
    writes the copy. A present but malformed file raises `KeywordsError`.
    """
    if not path.exists():
        return default_keywords()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise KeywordsError(f"cannot read {path}: {error}") from error
    return _parse_keywords(_load_yaml(raw, path))


# --- Loading and schema validation -----------------------------------------


def _load_yaml(text: str, path: Path) -> Any:
    try:
        return yaml.load(text, Loader=_StringLoader)  # noqa: S506 -- a SafeLoader subclass
    except yaml.YAMLError as error:
        raise KeywordsError(f"invalid YAML in {path}: {error}") from error


def _parse_keywords(data: Any) -> Keywords:
    if not isinstance(data, dict):
        raise KeywordsError("top level must be a YAML mapping")
    for key in data:
        if key not in SECTIONS:
            raise KeywordsError(
                f"unknown section '{key}'; expected one of {list(SECTIONS)}"
            )
    return Keywords(
        contents_heading=_parse_section("contents_heading", data),
        contents_page_label=_parse_section("contents_page_label", data),
        top_level_sections=_parse_section("top_level_sections", data),
        heading_minor_words=_parse_section("heading_minor_words", data),
        caption_labels=_parse_section("caption_labels", data),
        image_placeholders=_parse_section("image_placeholders", data),
    )


def _parse_section(name: str, data: dict[Any, Any]) -> tuple[str, ...]:
    """The records of one section, checked.

    An empty section is allowed; a missing one is an error, since the copy
    replaces the shipped list whole and the rule would silently stop working.
    """
    if name not in data:
        raise KeywordsError(f"section '{name}' is missing")
    raw = data[name]
    # A key with no records reads as null: an empty section.
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise KeywordsError(f"section '{name}' must be a list of words")
    return tuple(_parse_record(name, entry) for entry in raw)


def _parse_record(section: str, entry: Any) -> str:
    if not isinstance(entry, str):
        raise KeywordsError(
            f"section '{section}': record {entry!r} must be a word, "
            f"not {type(entry).__name__}"
        )
    if entry != entry.strip() or not entry:
        raise KeywordsError(
            f"section '{section}': record {entry!r} must be a word "
            "with no leading or trailing space"
        )
    marks = entry.count(PREFIX_MARKER)
    if marks and (marks > 1 or not entry.endswith(PREFIX_MARKER)):
        raise KeywordsError(
            f"section '{section}': record {entry!r} may carry "
            f"'{PREFIX_MARKER}' at its end only, to state the beginning of a word"
        )
    if entry == PREFIX_MARKER:
        raise KeywordsError(f"section '{section}': record {entry!r} holds no word")
    return entry


# --- `keywords` subcommand -------------------------------------------------


def run_keywords_command(args: list[str]) -> int:
    """Handle `raw2md keywords <action>`."""
    action = parse_file_action("raw2md keywords", args)
    path = keywords_file()
    if action == "path":
        print(path)
        return int(ExitCode.SUCCESS)
    if action == "show":
        return show_file(path)
    if action == "check":
        return _run_check(path)
    return edit_file(path)  # action == "edit"


def _run_check(path: Path) -> int:
    """Validate YAML syntax and schema; report, do not fix.

    The word list is not compared with the shipped one: the copy is the
    user's to shorten.
    """
    if not path.exists():
        print(
            f"raw2md: {path} does not exist; the shipped dictionary applies",
            file=sys.stderr,
        )
        return int(ExitCode.SUCCESS)
    try:
        load_keywords(path)
    except KeywordsError as error:
        print(f"raw2md: {path}: invalid ({error})", file=sys.stderr)
        return int(ExitCode.ARGUMENT_ERROR)
    print(f"{path}: OK")
    return int(ExitCode.SUCCESS)
