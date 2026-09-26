"""settings.json schema, loader, defaults, and the `settings` subcommand.

`models` describes each model once; `operations` lists the models allowed
for each operation. Model names come from settings.json, not from code. The
validation here is structural; checks that need the environment belong to
`doctor`.
"""

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from raw2md.exit_codes import ExitCode
from raw2md.header import is_reserved_llm_field_value
from raw2md.paths import settings_file
from raw2md.service import edit_file, parse_file_action, show_file

ACCESS_TYPES = ("api", "cli")
OPERATIONS = ("ocr", "inspection", "post")

# Built-in route names: a model key equal to one would make an --engine value
# ambiguous.
RESERVED_ENGINE_NAMES = frozenset({"marker", "pandoc", "djvu"})

# Operations that read page images and need vision.
VISION_OPERATIONS = frozenset({"ocr", "inspection"})

_TEMPERATURE_MIN = 0.0
_TEMPERATURE_MAX = 2.0

# "No override", written out so the knob shows in the template.
_MARKER_BATCH_SIZE_DEFAULT = "default"

# Below two occurrences a spelling is not the document's own.
_WITNESS_MIN_FLOOR = 2

# Both the file template and the in-memory fallback derive from this mapping.
# Values restate the code fallbacks so the template shows them:
# `pages_per_request` (llm.chunking), `max_request_bytes` (llm.base),
# `witness_min` (cleaning.ocr), `cli_timeout_s` (llm.claude). No temperature:
# the provider default holds.
DEFAULT_SETTINGS: dict[str, Any] = {
    "models": {
        "gemini_api": {
            "access": "api",
            "key_env": "GOOGLE_API_KEY",
            "model": "gemini-3.5-flash-lite",
            "rpm": 15,
            "tpm": 250000,
            "rpd": 500,
            "rpd_reset_zone": "America/Los_Angeles",
            "pages_per_request": 8,
            "max_request_bytes": 20971520,
        },
        "claude_cli": {
            "access": "cli",
            "command": "claude",
            "model": "claude-sonnet-5",
            "cli_timeout_s": 120,
        },
    },
    "operations": {
        "ocr": {"allowed": ["gemini_api"]},
        "inspection": {"allowed": ["gemini_api"]},
        "post": {"allowed": ["claude_cli", "gemini_api"]},
    },
    "marker": {
        "recognition_batch_size": "default",
    },
    "cleaning": {
        "witness_min": 20,
    },
    "log_file": True,
}


class SettingsError(Exception):
    """settings.json is missing a field, malformed, or has a wrong type."""


class UnknownZoneError(SettingsError):
    """A zone field (`rpd_reset_zone`) named a zone the system cannot resolve.

    Separate so `doctor` can blame a missing `tzdata`, under which no zone
    resolves.
    """


@dataclass(frozen=True)
class ModelConfig:
    """One entry of the `models` block.

    `key_env` and `temperature` are for `api` access; `command` and
    `cli_timeout_s` for `cli`. Optional fields left as None fall back to the
    defaults of the code that applies them: `rpd_reset_zone` (the IANA zone of
    the daily quota boundary) to the provider's zone, `pages_per_request` and
    `max_request_bytes` (the request window) to built-in limits,
    `cli_timeout_s` to a default timeout. An absent `temperature` is not sent.
    """

    access: str
    model: str
    key_env: str | None
    command: str | None
    rpm: int | None
    tpm: int | None
    rpd: int | None
    rpd_reset_zone: str | None = None
    pages_per_request: int | None = None
    max_request_bytes: int | None = None
    temperature: float | None = None
    cli_timeout_s: int | None = None


@dataclass(frozen=True)
class Settings:
    """Parsed settings.json.

    `log_file` can only be turned off by `--no-log-file`. None in
    `marker_recognition_batch_size` or `cleaning_witness_min` leaves the
    built-in default in force.
    """

    models: Mapping[str, ModelConfig]
    operations: Mapping[str, frozenset[str]]
    log_file: bool
    marker_recognition_batch_size: int | None = None
    cleaning_witness_min: int | None = None


def access_has_vision(access: str) -> bool:
    """Whether an access type can read images; a `cli` model has no vision."""
    return access == "api"


def model_can_serve(model: ModelConfig, operation: str) -> bool:
    """Whether `model` has the capability `operation` needs."""
    if operation in VISION_OPERATIONS:
        return access_has_vision(model.access)
    return True


def is_reserved_engine_name(value: str) -> bool:
    """True when `value` names one of the tool's built-in conversion routes."""
    return value in RESERVED_ENGINE_NAMES


def resolve_log_file(flag: bool, settings: Settings) -> bool:
    """Effective file logging: off when either the flag or settings.json says so."""
    return flag and settings.log_file


# --- Loading and schema validation -----------------------------------------


def default_settings() -> Settings:
    return parse_settings(DEFAULT_SETTINGS)


def default_settings_text() -> str:
    return json.dumps(DEFAULT_SETTINGS, indent=2, ensure_ascii=False) + "\n"


def load_settings(path: Path) -> Settings:
    """Load settings from `path`, falling back to the built-in defaults.

    A missing file is not an error: defaults apply until `raw2md init` writes
    one. A present but malformed file raises `SettingsError`.
    """
    if not path.exists():
        return default_settings()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SettingsError(f"cannot read {path}: {error}") from error
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SettingsError(f"invalid JSON in {path}: {error}") from error
    return parse_settings(data)


def parse_settings(data: Any) -> Settings:
    if not isinstance(data, dict):
        raise SettingsError("top level must be a JSON object")
    return Settings(
        models=_parse_models(data.get("models")),
        operations=_parse_operations(data.get("operations")),
        log_file=_parse_log_file(data.get("log_file")),
        marker_recognition_batch_size=_parse_marker(data.get("marker")),
        cleaning_witness_min=_parse_cleaning(data.get("cleaning")),
    )


def _parse_models(raw: Any) -> dict[str, ModelConfig]:
    if not isinstance(raw, dict):
        raise SettingsError("'models' must be an object")
    if not raw:
        raise SettingsError("'models' must define at least one model")
    for name in raw:
        # A model key goes verbatim into the header's stage fields.
        if is_reserved_llm_field_value(name):
            raise SettingsError(
                f"model key '{name}' is reserved; it collides with a header "
                "LLM-field value (none/failed/partial)"
            )
        if is_reserved_engine_name(name):
            raise SettingsError(
                f"model key '{name}' is reserved; it collides with a built-in "
                "conversion engine name (marker/pandoc/djvu)"
            )
    return {name: _parse_model(name, spec) for name, spec in raw.items()}


def _parse_model(name: str, spec: Any) -> ModelConfig:
    if not isinstance(spec, dict):
        raise SettingsError(f"model '{name}' must be an object")
    access = spec.get("access")
    if access not in ACCESS_TYPES:
        raise SettingsError(
            f"model '{name}': 'access' must be one of {list(ACCESS_TYPES)}"
        )
    return ModelConfig(
        access=access,
        model=_require_str(name, spec, "model"),
        key_env=_require_str(name, spec, "key_env") if access == "api" else None,
        command=_require_str(name, spec, "command") if access == "cli" else None,
        rpm=_optional_int(name, spec, "rpm"),
        tpm=_optional_int(name, spec, "tpm"),
        rpd=_optional_int(name, spec, "rpd"),
        rpd_reset_zone=_optional_zone(name, spec, "rpd_reset_zone"),
        pages_per_request=_optional_positive_int(name, spec, "pages_per_request"),
        max_request_bytes=_optional_positive_int(name, spec, "max_request_bytes"),
        temperature=_optional_temperature(name, spec, access),
        cli_timeout_s=_optional_cli_timeout(name, spec, access),
    )


def _require_str(model_name: str, spec: dict[str, Any], field: str) -> str:
    value = spec.get(field)
    if not isinstance(value, str) or not value:
        raise SettingsError(
            f"model '{model_name}': '{field}' must be a non-empty string"
        )
    return value


def _optional_int(model_name: str, spec: dict[str, Any], field: str) -> int | None:
    value = spec.get(field)
    if value is None:
        return None
    # bool is an int subclass.
    if not isinstance(value, int) or isinstance(value, bool):
        raise SettingsError(f"model '{model_name}': '{field}' must be an integer")
    return value


def _optional_positive_int(
    model_name: str, spec: dict[str, Any], field: str
) -> int | None:
    """An optional integer that must be positive when present.

    Unlike a rate, a zero window has no reading: nothing could be sent.
    """
    value = _optional_int(model_name, spec, field)
    if value is not None and value <= 0:
        raise SettingsError(f"model '{model_name}': '{field}' must be positive")
    return value


def _optional_zone(model_name: str, spec: dict[str, Any], field: str) -> str | None:
    """An optional IANA zone name, checked at load time rather than mid-run."""
    value = spec.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise SettingsError(
            f"model '{model_name}': '{field}' must be a non-empty string"
        )
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        # ValueError: a malformed key, such as an absolute path.
        raise UnknownZoneError(
            f"model '{model_name}': '{field}' is not a known time zone ({value})"
        ) from error
    return value


def _optional_temperature(
    model_name: str, spec: dict[str, Any], access: str
) -> float | None:
    """An optional sampling temperature, accepted for `api` access only.

    The CLI route cannot carry one, so a value there is refused rather than
    silently dropped. The range is the widest the supported API accepts. The
    template states none: the provider advises keeping its default.
    """
    value = spec.get("temperature")
    if value is None:
        return None
    if access != "api":
        raise SettingsError(
            f"model '{model_name}': 'temperature' applies to 'api' access only"
        )
    # bool is an int subclass; an int temperature is fine.
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SettingsError(f"model '{model_name}': 'temperature' must be a number")
    if not _TEMPERATURE_MIN <= value <= _TEMPERATURE_MAX:
        raise SettingsError(
            f"model '{model_name}': 'temperature' must be between "
            f"{_TEMPERATURE_MIN} and {_TEMPERATURE_MAX}"
        )
    return float(value)


def _optional_cli_timeout(
    model_name: str, spec: dict[str, Any], access: str
) -> int | None:
    """An optional CLI subprocess timeout in seconds, accepted for `cli` access only.

    An `api` request has its own transport timeout, so a value there would go
    unused.
    """
    value = spec.get("cli_timeout_s")
    if value is None:
        return None
    if access != "cli":
        raise SettingsError(
            f"model '{model_name}': 'cli_timeout_s' applies to 'cli' access only"
        )
    return _optional_positive_int(model_name, spec, "cli_timeout_s")


def _parse_operations(raw: Any) -> dict[str, frozenset[str]]:
    if not isinstance(raw, dict):
        raise SettingsError("'operations' must be an object")
    result: dict[str, frozenset[str]] = {}
    for name, spec in raw.items():
        if name not in OPERATIONS:
            raise SettingsError(
                f"unknown operation '{name}'; expected one of {list(OPERATIONS)}"
            )
        result[name] = _parse_allowed(name, spec)
    return result


def _parse_allowed(operation: str, spec: Any) -> frozenset[str]:
    if not isinstance(spec, dict):
        raise SettingsError(f"operation '{operation}' must be an object")
    allowed = spec.get("allowed")
    if not isinstance(allowed, list) or not all(isinstance(m, str) for m in allowed):
        raise SettingsError(
            f"operation '{operation}': 'allowed' must be a list of strings"
        )
    for model_key in allowed:
        if is_reserved_engine_name(model_key):
            raise SettingsError(
                f"operation '{operation}': 'allowed' names '{model_key}', a "
                "reserved conversion engine name, not a model key"
            )
    return frozenset(allowed)


def _parse_log_file(raw: Any) -> bool:
    if raw is None:
        return True
    if not isinstance(raw, bool):
        raise SettingsError("'log_file' must be a boolean")
    return raw


def _parse_marker(raw: Any) -> int | None:
    """Parse the optional `marker` section into a recognition batch size.

    Absence and `"default"` leave marker's device default; only a positive
    integer overrides it.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SettingsError("'marker' must be an object")
    value = raw.get("recognition_batch_size", _MARKER_BATCH_SIZE_DEFAULT)
    if value == _MARKER_BATCH_SIZE_DEFAULT:
        return None
    # bool is an int subclass.
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError(
            "'marker.recognition_batch_size' must be a positive integer or "
            f"'{_MARKER_BATCH_SIZE_DEFAULT}'"
        )
    if value <= 0:
        raise SettingsError("'marker.recognition_batch_size' must be positive")
    return value


def _parse_cleaning(raw: Any) -> int | None:
    """Parse the optional `cleaning` section into a witness bar.

    A bar under `_WITNESS_MIN_FLOOR` would license a repair on no evidence.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SettingsError("'cleaning' must be an object")
    value = raw.get("witness_min")
    if value is None:
        return None
    # bool is an int subclass.
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError("'cleaning.witness_min' must be an integer")
    if value < _WITNESS_MIN_FLOOR:
        raise SettingsError(
            f"'cleaning.witness_min' must be at least {_WITNESS_MIN_FLOOR}"
        )
    return value


# --- `settings` subcommand -------------------------------------------------


def run_settings_command(args: list[str]) -> int:
    """Handle `raw2md settings <action>`."""
    action = parse_file_action("raw2md settings", args)
    path = settings_file()
    if action == "path":
        print(path)
        return int(ExitCode.SUCCESS)
    if action == "show":
        return show_file(path)
    if action == "check":
        return _run_check(path)
    return edit_file(path)  # action == "edit"


def _run_check(path: Path) -> int:
    """Validate syntax, schema, and cross-references; report, do not fix.

    A missing file is not a failure: the defaults apply. Environment checks
    belong to `doctor`.
    """
    if not path.exists():
        print(
            f"raw2md: {path} does not exist; built-in defaults apply",
            file=sys.stderr,
        )
        return int(ExitCode.SUCCESS)
    try:
        settings = load_settings(path)
    except SettingsError as error:
        print(f"raw2md: {path}: invalid ({error})", file=sys.stderr)
        return int(ExitCode.ARGUMENT_ERROR)
    problems = _unknown_model_references(settings)
    if problems:
        for problem in problems:
            print(f"raw2md: {path}: {problem}", file=sys.stderr)
        return int(ExitCode.ARGUMENT_ERROR)
    print(f"{path}: OK")
    return int(ExitCode.SUCCESS)


def _unknown_model_references(settings: Settings) -> list[str]:
    """Operation `allowed` entries naming a model absent from `models`."""
    return [
        f"operation '{operation}' references unknown model '{model_key}'"
        for operation in OPERATIONS
        for model_key in sorted(settings.operations.get(operation, frozenset()))
        if model_key not in settings.models
    ]
