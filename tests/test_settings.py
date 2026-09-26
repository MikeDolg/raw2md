"""Tests for the settings.json schema, loader, defaults, and subcommand."""

import json
from pathlib import Path
from typing import Any

import pytest

from raw2md.cleaning import DEFAULT_WITNESS_MIN
from raw2md.paths import settings_file
from raw2md.settings import (
    DEFAULT_SETTINGS,
    ModelConfig,
    Settings,
    SettingsError,
    UnknownZoneError,
    default_settings,
    default_settings_text,
    load_settings,
    model_can_serve,
    parse_settings,
    resolve_log_file,
    run_settings_command,
)

# --- Defaults --------------------------------------------------------------


def test_default_settings_parses() -> None:
    settings = default_settings()
    assert settings.models["gemini_api"].access == "api"
    assert settings.models["gemini_api"].key_env == "GOOGLE_API_KEY"
    assert settings.models["claude_cli"].access == "cli"
    assert settings.models["claude_cli"].command == "claude"
    assert settings.operations["post"] == frozenset({"claude_cli", "gemini_api"})
    assert settings.log_file is True


def test_default_settings_states_the_request_window() -> None:
    # The template spells out the window, so a reader of settings.json sees it.
    settings = default_settings()
    assert settings.models["gemini_api"].pages_per_request == 8
    assert settings.models["gemini_api"].max_request_bytes == 20971520


def test_default_settings_states_the_cli_timeout() -> None:
    # Spelled out in the template like the request window.
    settings = default_settings()
    assert settings.models["claude_cli"].cli_timeout_s == 120


def test_default_settings_states_the_rpd_reset_zone() -> None:
    # Spelled out in the template like the request window.
    settings = default_settings()
    assert settings.models["gemini_api"].rpd_reset_zone == "America/Los_Angeles"


def test_default_settings_states_no_temperature() -> None:
    # The provider advises against overriding its default for these models.
    assert "temperature" not in DEFAULT_SETTINGS["models"]["gemini_api"]
    assert default_settings().models["gemini_api"].temperature is None


def test_default_settings_leaves_marker_batch_size_unset() -> None:
    # "default" in the template keeps marker's device-based default.
    assert default_settings().marker_recognition_batch_size is None


def test_default_text_round_trips() -> None:
    assert json.loads(default_settings_text()) == DEFAULT_SETTINGS


# --- Loading ---------------------------------------------------------------


def test_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "absent.json") == default_settings()


def test_valid_file_is_loaded(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(default_settings_text(), encoding="utf-8")
    assert load_settings(path).operations["ocr"] == frozenset({"gemini_api"})


def test_malformed_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(SettingsError):
        load_settings(path)


# --- Schema validation -----------------------------------------------------


def test_top_level_must_be_object() -> None:
    with pytest.raises(SettingsError):
        parse_settings([1, 2, 3])


def test_models_required() -> None:
    with pytest.raises(SettingsError):
        parse_settings({"operations": {}})


def test_models_must_be_nonempty() -> None:
    with pytest.raises(SettingsError):
        parse_settings({"models": {}})


def test_unknown_access_rejected() -> None:
    data = {"models": {"m": {"access": "rest", "model": "x"}}}
    with pytest.raises(SettingsError):
        parse_settings(data)


def test_api_model_requires_key_env() -> None:
    data = {"models": {"m": {"access": "api", "model": "x"}}}
    with pytest.raises(SettingsError):
        parse_settings(data)


def test_cli_model_requires_command() -> None:
    data = {"models": {"m": {"access": "cli", "model": "x"}}}
    with pytest.raises(SettingsError):
        parse_settings(data)


def test_empty_model_name_rejected() -> None:
    data = {"models": {"m": {"access": "cli", "command": "c", "model": ""}}}
    with pytest.raises(SettingsError):
        parse_settings(data)


@pytest.mark.parametrize("reserved", ["none", "failed", "partial", "partial (1/2)"])
def test_reserved_model_key_rejected(reserved: str) -> None:
    # A key equal to a header sentinel, bare or as a coverage fraction, would
    # hide the stage's outcome.
    data = {"models": {reserved: {"access": "cli", "command": "c", "model": "x"}}}
    with pytest.raises(SettingsError):
        parse_settings(data)


@pytest.mark.parametrize("engine", ["marker", "pandoc", "djvu"])
def test_reserved_engine_name_rejected_as_model_key(engine: str) -> None:
    # A key equal to an engine name would make --engine ambiguous.
    data = {"models": {engine: {"access": "cli", "command": "c", "model": "x"}}}
    with pytest.raises(SettingsError):
        parse_settings(data)


@pytest.mark.parametrize("engine", ["marker", "pandoc", "djvu"])
def test_reserved_engine_name_rejected_in_operations_allowed(engine: str) -> None:
    data = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "operations": {"post": {"allowed": ["m", engine]}},
    }
    with pytest.raises(SettingsError):
        parse_settings(data)


def test_boolean_limit_rejected() -> None:
    data = {
        "models": {"m": {"access": "api", "key_env": "K", "model": "x", "rpm": True}}
    }
    with pytest.raises(SettingsError):
        parse_settings(data)


def test_request_window_fields_are_read() -> None:
    data = {
        "models": {
            "m": {
                "access": "api",
                "key_env": "K",
                "model": "x",
                "pages_per_request": 4,
                "max_request_bytes": 1024,
            }
        },
        "operations": {"inspection": {"allowed": ["m"]}},
    }
    model = parse_settings(data).models["m"]
    assert model.pages_per_request == 4
    assert model.max_request_bytes == 1024


def test_request_window_fields_are_optional() -> None:
    # Absent fields leave the built-in window in force.
    data = {
        "models": {"m": {"access": "api", "key_env": "K", "model": "x"}},
        "operations": {"inspection": {"allowed": ["m"]}},
    }
    model = parse_settings(data).models["m"]
    assert model.pages_per_request is None
    assert model.max_request_bytes is None


@pytest.mark.parametrize("field", ["pages_per_request", "max_request_bytes"])
@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_request_window_rejected(field: str, value: int) -> None:
    # A zero window is a typo, not a setting.
    data = {
        "models": {"m": {"access": "api", "key_env": "K", "model": "x", field: value}}
    }
    with pytest.raises(SettingsError, match="must be positive"):
        parse_settings(data)


def _api_model_data(**fields: Any) -> dict[str, Any]:
    return {
        "models": {"m": {"access": "api", "key_env": "K", "model": "x", **fields}},
        "operations": {"inspection": {"allowed": ["m"]}},
    }


def _cli_post_model_data(**fields: Any) -> dict[str, Any]:
    return {
        "models": {"m": {"access": "cli", "command": "c", "model": "x", **fields}},
        "operations": {"post": {"allowed": ["m"]}},
    }


@pytest.mark.parametrize("value", [0, 0.2, 2])
def test_temperature_is_read_as_a_float(value: float) -> None:
    # An integer temperature reaches the provider as a float.
    model = parse_settings(_api_model_data(temperature=value)).models["m"]
    assert model.temperature == float(value)


def test_temperature_is_optional() -> None:
    # An absent field sends nothing, so the provider's default holds.
    assert parse_settings(_api_model_data()).models["m"].temperature is None
    assert parse_settings(_api_model_data(temperature=0.2)).models["m"].temperature == (
        0.2
    )


@pytest.mark.parametrize("value", [-0.1, 2.1])
def test_temperature_outside_the_range_rejected(value: float) -> None:
    # Refused at load time, before any file is converted.
    with pytest.raises(SettingsError, match="between"):
        parse_settings(_api_model_data(temperature=value))


@pytest.mark.parametrize("value", ["0.2", True])
def test_non_numeric_temperature_rejected(value: object) -> None:
    # A boolean is an int subclass, so it passes a bare numeric check.
    with pytest.raises(SettingsError, match="must be a number"):
        parse_settings(_api_model_data(temperature=value))


def test_temperature_rejected_for_cli_access() -> None:
    # Print mode takes only a model name, so a temperature would be dropped.
    data = {
        "models": {
            "m": {
                "access": "cli",
                "command": "claude",
                "model": "x",
                "temperature": 0.2,
            }
        },
        "operations": {"post": {"allowed": ["m"]}},
    }
    with pytest.raises(SettingsError, match="'api' access only"):
        parse_settings(data)


# --- CLI timeout -------------------------------------------------------------


def test_cli_timeout_is_optional() -> None:
    # Absence leaves the provider's own fallback in force.
    assert parse_settings(_cli_post_model_data()).models["m"].cli_timeout_s is None


def test_cli_timeout_is_read() -> None:
    model = parse_settings(_cli_post_model_data(cli_timeout_s=300)).models["m"]
    assert model.cli_timeout_s == 300


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_cli_timeout_rejected(value: int) -> None:
    # A non-positive timeout is a typo, not a setting.
    with pytest.raises(SettingsError, match="must be positive"):
        parse_settings(_cli_post_model_data(cli_timeout_s=value))


@pytest.mark.parametrize("value", ["300", True, 1.5])
def test_non_integer_cli_timeout_rejected(value: object) -> None:
    # A boolean is an int subclass, so it passes a bare numeric check.
    with pytest.raises(SettingsError, match="must be an integer"):
        parse_settings(_cli_post_model_data(cli_timeout_s=value))


def test_cli_timeout_rejected_for_api_access() -> None:
    # An `api` request has its own transport timeout, so the value is refused.
    with pytest.raises(SettingsError, match="'cli' access only"):
        parse_settings(_api_model_data(cli_timeout_s=120))


# --- rpd reset zone ----------------------------------------------------------


def test_rpd_reset_zone_is_optional() -> None:
    # The provider applies its own default zone.
    assert parse_settings(_api_model_data()).models["m"].rpd_reset_zone is None


def test_rpd_reset_zone_is_read() -> None:
    model = parse_settings(
        _api_model_data(rpd_reset_zone="America/Los_Angeles")
    ).models["m"]
    assert model.rpd_reset_zone == "America/Los_Angeles"


def test_unknown_rpd_reset_zone_rejected() -> None:
    # Refused at load time; the type lets `doctor` tell a broken tzdata apart.
    with pytest.raises(UnknownZoneError, match="not a known time zone"):
        parse_settings(_api_model_data(rpd_reset_zone="Mars/Olympus_Mons"))


def test_non_string_rpd_reset_zone_rejected() -> None:
    with pytest.raises(SettingsError, match="must be a non-empty string"):
        parse_settings(_api_model_data(rpd_reset_zone=1))


@pytest.mark.parametrize("value", ["../UTC", "/UTC"])
def test_malformed_rpd_reset_zone_rejected(value: str) -> None:
    # A path-like key raises ValueError in zoneinfo; both land the same.
    with pytest.raises(SettingsError, match="not a known time zone"):
        parse_settings(_api_model_data(rpd_reset_zone=value))


# --- marker recognition batch size -----------------------------------------


def _cli_model_data(**marker: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "operations": {},
    }
    if marker:
        data["marker"] = marker
    return data


def test_marker_section_absent_leaves_batch_size_unset() -> None:
    assert parse_settings(_cli_model_data()).marker_recognition_batch_size is None


def test_marker_batch_size_default_string_leaves_it_unset() -> None:
    data = _cli_model_data(recognition_batch_size="default")
    assert parse_settings(data).marker_recognition_batch_size is None


def test_marker_batch_size_is_read() -> None:
    data = _cli_model_data(recognition_batch_size=4)
    assert parse_settings(data).marker_recognition_batch_size == 4


def test_marker_section_must_be_object() -> None:
    data = _cli_model_data()
    data["marker"] = ["not an object"]
    with pytest.raises(SettingsError, match="'marker'"):
        parse_settings(data)


@pytest.mark.parametrize("value", [0, -1])
def test_marker_batch_size_non_positive_rejected(value: int) -> None:
    # A non-positive batch is a typo, not a setting.
    data = _cli_model_data(recognition_batch_size=value)
    with pytest.raises(SettingsError, match="must be positive"):
        parse_settings(data)


@pytest.mark.parametrize("value", [8.5, "auto", True])
def test_marker_batch_size_invalid_value_rejected(value: object) -> None:
    # Only a positive integer or the literal "default" is read.
    data = _cli_model_data(recognition_batch_size=value)
    with pytest.raises(SettingsError, match="positive integer"):
        parse_settings(data)


def test_unknown_operation_rejected() -> None:
    data = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "operations": {"translate": {"allowed": ["m"]}},
    }
    with pytest.raises(SettingsError):
        parse_settings(data)


def test_allowed_must_be_list_of_strings() -> None:
    data = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "operations": {"post": {"allowed": "m"}},
    }
    with pytest.raises(SettingsError):
        parse_settings(data)


def test_log_file_must_be_bool() -> None:
    data = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "log_file": "yes",
    }
    with pytest.raises(SettingsError):
        parse_settings(data)


# --- Precedence and capability matrix --------------------------------------


@pytest.mark.parametrize(
    ("flag", "configured", "expected"),
    [
        # flag=True is RunConfig.log_file's CLI default (no --no-log-file);
        # flag=False is --no-log-file, which can only turn logging off.
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_log_file_precedence(flag: bool, configured: bool, expected: bool) -> None:
    settings = Settings(models={}, operations={}, log_file=configured)
    assert resolve_log_file(flag, settings) is expected


def test_missing_log_file_field_defaults_to_on() -> None:
    data = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "operations": {},
    }
    assert parse_settings(data).log_file is True


def _model(access: str) -> ModelConfig:
    return ModelConfig(
        access=access,
        model="x",
        key_env="K" if access == "api" else None,
        command="c" if access == "cli" else None,
        rpm=None,
        tpm=None,
        rpd=None,
    )


@pytest.mark.parametrize("operation", ["ocr", "inspection"])
def test_cli_model_cannot_serve_vision(operation: str) -> None:
    assert model_can_serve(_model("api"), operation) is True
    assert model_can_serve(_model("cli"), operation) is False


def test_any_model_can_serve_post() -> None:
    assert model_can_serve(_model("api"), "post") is True
    assert model_can_serve(_model("cli"), "post") is True


# --- `settings` subcommand -------------------------------------------------


def test_path_prints_location(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_settings_command(["path"]) == 0
    assert capsys.readouterr().out.strip() == str(settings_file())


def test_show_prints_contents(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_settings_text(), encoding="utf-8")
    assert run_settings_command(["show"]) == 0
    assert capsys.readouterr().out == default_settings_text()


def test_show_missing_file_hints(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_settings_command(["show"]) == 0
    assert "raw2md init" in capsys.readouterr().err


def test_unknown_action_is_argument_error(home: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_settings_command(["nonsense"])
    assert exc_info.value.code == 2


# --- `settings check` --------------------------------------------------------


def test_check_missing_file_is_not_error(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_settings_command(["check"]) == 0
    assert "does not exist" in capsys.readouterr().err


def test_check_valid_file_is_ok(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_settings_text(), encoding="utf-8")
    assert run_settings_command(["check"]) == 0
    assert "OK" in capsys.readouterr().out


def test_check_malformed_json_is_argument_error(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    assert run_settings_command(["check"]) == 2
    assert "invalid" in capsys.readouterr().err


def test_check_unknown_model_reference_is_argument_error(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The schema parses the two sections apart; check catches the reference.
    data = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "operations": {"post": {"allowed": ["m", "ghost"]}},
    }
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert run_settings_command(["check"]) == 2
    err = capsys.readouterr().err
    assert "post" in err
    assert "ghost" in err


def test_check_reserved_engine_name_is_argument_error(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data = {"models": {"pandoc": {"access": "cli", "command": "c", "model": "x"}}}
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert run_settings_command(["check"]) == 2
    assert "pandoc" in capsys.readouterr().err


# --- cleaning witness bar --------------------------------------------------


def _cleaning_data(**cleaning: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "models": {"m": {"access": "cli", "command": "c", "model": "x"}},
        "operations": {},
    }
    if cleaning:
        data["cleaning"] = cleaning
    return data


def test_cleaning_section_absent_leaves_the_witness_bar_unset() -> None:
    assert parse_settings(_cleaning_data()).cleaning_witness_min is None


def test_cleaning_witness_bar_is_read() -> None:
    assert parse_settings(_cleaning_data(witness_min=5)).cleaning_witness_min == 5


def test_default_settings_state_the_cleaning_witness_bar() -> None:
    # The template spells the bar out: the one cleaning threshold a document
    # can need tuned.
    assert default_settings().cleaning_witness_min == DEFAULT_WITNESS_MIN


def test_cleaning_section_must_be_object() -> None:
    data = _cleaning_data()
    data["cleaning"] = ["not an object"]
    with pytest.raises(SettingsError, match="'cleaning'"):
        parse_settings(data)


@pytest.mark.parametrize("value", [1, 0, -3])
def test_cleaning_witness_bar_below_the_floor_rejected(value: int) -> None:
    # A bar of one would license a repair on no evidence.
    with pytest.raises(SettingsError, match="at least"):
        parse_settings(_cleaning_data(witness_min=value))


@pytest.mark.parametrize("value", [5.5, "many", True])
def test_cleaning_witness_bar_non_integer_rejected(value: object) -> None:
    with pytest.raises(SettingsError, match="must be an integer"):
        parse_settings(_cleaning_data(witness_min=value))
