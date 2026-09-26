"""Result header: YAML front-matter that carries per-file state.

The header starts as an `in_progress` stub and collects temporary metric
fields from the evaluator; the final write drops them. `issues`, the checks
behind a `bad` verdict, stays and is written only when non-empty.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any

import yaml


# `str, Enum` rather than `StrEnum`: the two format differently, and this
# value reaches the result header. Moving it is a change of its own.
class ResultStatus(str, Enum):  # noqa: UP042
    # No `failed` member: a failed source gets no result file.
    OK = "ok"
    BAD = "bad"
    IN_PROGRESS = "in_progress"


# `str, Enum` rather than `StrEnum`: the two format differently, and `.value`
# is read directly in a log line. Moving it is a change of its own.
class ConversionMethod(str, Enum):  # noqa: UP042
    """The route a file's body came from; internal, not written to the header.

    Cleaning's heading recovery reads it.
    """

    MARKER = "marker"
    PANDOC = "pandoc"
    DJVU_MARKER = "djvu+marker"
    LLM_OCR = "llm-ocr"
    DJVU_LLM_OCR = "djvu+llm-ocr"
    # A md input is re-cleaned, not converted.
    CLEAN = "clean"


# Identifies a raw2md-owned header; cleaning relies on this to distinguish
# its own header from arbitrary foreign front matter.
OWN_HEADER_KEY = "raw2md_version"

# The `--engine` default.
DEFAULT_ENGINE = ConversionMethod.MARKER.value

# Reserved values of `inspection` and `post`; any other value is a model key.
# `none`: not requested or not applicable. `failed`: requested but not
# completed. `partial`: post covered part of its zones, always written with its
# count (`format_partial_stage`). Inspection coverage is an `issues` entry
# instead.
LLM_FIELD_NONE = "none"
LLM_FIELD_FAILED = "failed"
LLM_FIELD_PARTIAL = "partial"


def format_partial_stage(done: int, total: int) -> str:
    """Header value for a stage that covered `done` of `total` units."""
    return f"{LLM_FIELD_PARTIAL} ({done}/{total})"


_PARTIAL_STAGE_RE = re.compile(r"^partial \(\d+/\d+\)$")


def is_reserved_llm_field_value(value: str) -> bool:
    """True when `value` collides with a reserved LLM-field value.

    Covers every shape of `format_partial_stage` too, so a model key never
    reads back as a coverage fraction.
    """
    return (
        value
        in (
            LLM_FIELD_NONE,
            LLM_FIELD_FAILED,
            LLM_FIELD_PARTIAL,
        )
        or _PARTIAL_STAGE_RE.match(value) is not None
    )


_KNOWN_FIELDS = frozenset(
    {
        "raw2md_version",
        "source",
        "engine",
        "inspection",
        "post",
        "converted_at",
        "source_hash",
        "status",
        "issues",
    }
)

# A front-matter block at the start; CRLF too, for files read with newline=''.
_FRONT_MATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.DOTALL)


@dataclass
class ResultHeader:
    """YAML header for a result md file; `extras` are dropped at the final write."""

    raw2md_version: str
    source: str  # source file name with extension
    engine: str  # "marker", "pandoc", "clean", or a model key: what converted the file
    inspection: str  # "none", "failed", or model key from settings.json
    post: str  # "none", "failed", "partial (done/total)", or model key
    converted_at: datetime.date
    source_hash: str  # SHA-256 of source bytes, base64url without padding
    status: ResultStatus
    # CheckId values of the checks that fired, in evaluator order; empty on `ok`.
    issues: tuple[str, ...] = field(default_factory=tuple)
    # Temporary quality-metric fields; stripped at the final write.
    extras: dict[str, Any] = field(default_factory=dict)


class HeaderParseError(Exception):
    """Raised when a raw2md YAML front-matter block is structurally invalid."""


def get_version() -> str:
    try:
        return pkg_version("raw2md")
    except PackageNotFoundError:
        return "unknown"


def compute_source_hash(data: bytes) -> str:
    """SHA-256 of `data` as base64url without padding: safe in YAML unquoted."""
    digest = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def build_stub(
    source: str,
    *,
    engine: str = DEFAULT_ENGINE,
    inspection: str | None = None,
    post: str | None = None,
    source_hash: str,
) -> ResultHeader:
    """Build an `in_progress` stub header before conversion starts."""
    return ResultHeader(
        raw2md_version=get_version(),
        source=source,
        engine=engine,
        inspection=inspection or LLM_FIELD_NONE,
        post=post or LLM_FIELD_NONE,
        converted_at=datetime.date.today(),  # noqa: DTZ011 -- local calendar date for the reader, not compared across zones
        source_hash=source_hash,
        status=ResultStatus.IN_PROGRESS,
    )


def to_yaml_block(header: ResultHeader, *, include_extras: bool = False) -> str:
    """Serialize `header` to a ``---``-delimited YAML front-matter block.

    `include_extras` is for the in-progress stub. `issues` is not an extra.
    """
    data: dict[str, Any] = {
        "raw2md_version": header.raw2md_version,
        "source": header.source,
        "engine": header.engine,
        "inspection": header.inspection,
        "post": header.post,
        "converted_at": header.converted_at,
        "source_hash": header.source_hash,
        "status": header.status.value,
    }
    if header.issues:
        data["issues"] = list(header.issues)
    if include_extras and header.extras:
        # An extra never overwrites a permanent field.
        safe = {k: v for k, v in header.extras.items() if k not in _KNOWN_FIELDS}
        data.update(safe)
    body = yaml.safe_dump(
        data, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    return f"---\n{body}---\n"


def _none_or_str(value: object) -> str:
    """Convert a YAML-loaded field to its string form; PyYAML reads `none` as null."""
    return "none" if value is None else str(value)


def _parse_issues(value: object) -> tuple[str, ...]:
    """Parse the optional `issues` field; absent means no check fired."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"issues must be a list of strings, got {value!r}")
    return tuple(value)


def from_yaml_block(text: str) -> ResultHeader | None:
    """Parse the first YAML front-matter block in `text`.

    Returns `None` if no block is found or it lacks ``raw2md_version``.
    Raises `HeaderParseError` when the block is structurally malformed.
    """
    m = _FRONT_MATTER_RE.match(text)
    if m is None:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        raise HeaderParseError(f"malformed YAML in front-matter: {exc}") from exc
    if not isinstance(data, dict) or OWN_HEADER_KEY not in data:
        return None
    try:
        converted_at: object = data["converted_at"]
        if isinstance(converted_at, str):
            converted_at = datetime.date.fromisoformat(converted_at)
        # datetime is a subclass of date; the schema wants a date.
        if isinstance(converted_at, datetime.datetime) or not isinstance(
            converted_at, datetime.date
        ):
            # ValueError, so the handler below wraps it as HeaderParseError.
            raise ValueError(  # noqa: TRY004, TRY301
                f"converted_at must be a date, got {type(converted_at).__name__!r}"
            )
        return ResultHeader(
            raw2md_version=str(data[OWN_HEADER_KEY]),
            source=str(data["source"]),
            engine=str(data["engine"]),
            inspection=_none_or_str(data["inspection"]),
            post=_none_or_str(data["post"]),
            converted_at=converted_at,
            source_hash=str(data["source_hash"]),
            status=ResultStatus(data["status"]),
            issues=_parse_issues(data.get("issues")),
            extras={k: v for k, v in data.items() if k not in _KNOWN_FIELDS},
        )
    except (KeyError, ValueError) as exc:
        raise HeaderParseError(f"invalid header field: {exc}") from exc


def has_own_header(text: str) -> bool:
    """True when `text` begins with a raw2md-owned YAML front-matter block."""
    try:
        return from_yaml_block(text) is not None
    except HeaderParseError:
        return False


def strip_own_header(text: str) -> tuple[ResultHeader | None, str]:
    """Remove the raw2md header from `text` and return ``(header, body)``.

    Foreign front matter (no ``raw2md_version``) is left intact and returned
    as part of the body.
    """
    try:
        header = from_yaml_block(text)
    except HeaderParseError:
        return None, text
    if header is None:
        return None, text
    m = _FRONT_MATTER_RE.match(text)
    assert m is not None  # from_yaml_block already succeeded with the same regex
    return header, text[m.end() :]


def render_result(header: ResultHeader, body: str, *, emit_yaml: bool = True) -> str:
    """Produce the final md content: header (unless ``--no-yaml``) + body.

    ``extras`` (temporary fields) are always dropped regardless of `emit_yaml`.
    """
    if emit_yaml:
        return to_yaml_block(header) + body
    return body
