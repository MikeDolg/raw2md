"""The `init` subcommand: creates the missing ~/.raw2md service files.

Every service file that raw2md ships a template for is created when missing;
an existing file is never touched.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from raw2md.exit_codes import ExitCode
from raw2md.keywords import default_keywords_text
from raw2md.paths import keywords_file, prompts_file, settings_file
from raw2md.prompts import default_prompts_text
from raw2md.service import MANAGEMENT_FAILURE
from raw2md.settings import (
    DEFAULT_SETTINGS,
    OPERATIONS,
    VISION_OPERATIONS,
    default_settings_text,
)


def run_init_command(args: list[str]) -> int:
    """Handle `raw2md init [MODEL ...]`."""
    model_keys = _parse_init_args(args)
    settings_template = _settings_template(model_keys)
    settings_path = settings_file()
    settings_text = (
        default_settings_text()
        if not model_keys
        else json.dumps(settings_template, indent=2, ensure_ascii=False) + "\n"
    )

    # Files are copied as shipped, not dumped from a parsed form: a dump would
    # drop the comments the user reads.
    register = (
        (settings_path, settings_text),
        (prompts_file(), default_prompts_text()),
        (keywords_file(), default_keywords_text()),
    )
    statuses: dict[Path, str] = {}
    for path, text in register:
        status = _create_service_file(path, text)
        if status is None:
            return MANAGEMENT_FAILURE
        _report_status(path, status)
        statuses[path] = status

    if model_keys:
        if statuses[settings_path] == "exists":
            print(
                f"raw2md: {settings_path} already exists; the model "
                "arguments were not applied",
                file=sys.stderr,
            )
        else:
            _warn_vision_gap(settings_template)
    return int(ExitCode.SUCCESS)


def _parse_init_args(args: list[str]) -> tuple[str, ...]:
    parser = argparse.ArgumentParser(prog="raw2md init")
    # The keys are checked below instead of through `choices=`: argparse before
    # 3.12 validates the empty default of a `nargs="*"` positional against the
    # choice set, which rejects the bare `raw2md init` on the supported floor.
    parser.add_argument(
        "models",
        nargs="*",
        metavar="MODEL",
        help="shipped model keys to keep in settings.json (default: all)",
    )
    known = tuple(DEFAULT_SETTINGS["models"])
    models = tuple(parser.parse_args(args).models)
    for model in models:
        if model not in known:
            choices = ", ".join(repr(key) for key in known)
            parser.error(
                f"argument MODEL: invalid choice: {model!r} (choose from {choices})"
            )
    return models


def _settings_template(model_keys: tuple[str, ...]) -> dict[str, Any]:
    """The settings.json template: `DEFAULT_SETTINGS`, or filtered to `model_keys`."""
    if not model_keys:
        return DEFAULT_SETTINGS
    selected = set(model_keys)
    return {
        **DEFAULT_SETTINGS,
        "models": {
            key: spec
            for key, spec in DEFAULT_SETTINGS["models"].items()
            if key in selected
        },
        "operations": {
            operation: {"allowed": [key for key in spec["allowed"] if key in selected]}
            for operation, spec in DEFAULT_SETTINGS["operations"].items()
        },
    }


def _warn_vision_gap(settings_template: dict[str, Any]) -> None:
    """Warn when the chosen models leave a vision operation with none allowed.

    A model without vision (the CLI access type) cannot serve OCR or
    inspection.
    """
    empty = [
        operation
        for operation in OPERATIONS
        if operation in VISION_OPERATIONS
        and not settings_template["operations"][operation]["allowed"]
    ]
    if empty:
        print(
            f"raw2md: no chosen model has vision; {', '.join(empty)} were "
            "left with no allowed model in settings.json",
            file=sys.stderr,
        )


def _create_service_file(path: Path, text: str) -> str | None:
    """Create `path` with `text` if missing; report an I/O failure as None.

    Exclusive create never overwrites, even under a race or a dangling
    symlink at the target.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError:
        return "exists"
    except OSError as error:
        print(f"raw2md: cannot write {path}: {error}", file=sys.stderr)
        return None
    return "created"


def _report_status(path: Path, status: str) -> None:
    if status == "created":
        print(f"created {path}")
    else:
        print(f"raw2md: {path} already exists; not overwritten", file=sys.stderr)
