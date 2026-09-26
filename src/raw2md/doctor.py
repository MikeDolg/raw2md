"""The `doctor` subcommand: tool and settings readiness.

The exit code sums up four reports:

- engines: a missing marker is a missing dependency (exit 3); pandoc and the
  djvu chain are optional and only disable their format;
- the GPU and `recognition_batch_size`: informational only;
- `zoneinfo`: required, because the daily quota boundary needs an IANA zone
  and Windows has no system zone database;
- settings.json: a schema error, an unknown model, or a vision operation on
  a cli model is exit 2; an unusable configured model is exit 3.

Model readiness comes from the provider `available()`, the same check a run
does.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from raw2md.engines import DjvuEngine, MarkerEngine, PandocEngine
from raw2md.exit_codes import ExitCode
from raw2md.llm import build_provider
from raw2md.paths import default_temp_dir, settings_file
from raw2md.settings import (
    OPERATIONS,
    Settings,
    SettingsError,
    UnknownZoneError,
    load_settings,
    model_can_serve,
)


def run_doctor(args: Sequence[str] | None = None) -> int:
    """Report engine and settings readiness; return the matching exit code.

    The parser runs only to answer `--help` and refuse extra tokens.
    """
    if args is not None:
        argparse.ArgumentParser(
            prog="raw2md doctor",
            description="Check conversion tools and settings readiness.",
        ).parse_args(args)
    print("raw2md doctor")
    engine_problems = _report_engines()
    tzdata_problems = _report_tzdata()
    try:
        settings = load_settings(settings_file())
    except UnknownZoneError as exc:
        print(f"settings.json: INVALID ({exc})")
        if tzdata_problems:
            # Without a zone database no zone resolves, so this is the missing
            # dependency reported above, not a settings mistake.
            return int(ExitCode.MISSING_DEPENDENCY)
        return int(ExitCode.ARGUMENT_ERROR)
    except SettingsError as exc:
        print(f"settings.json: INVALID ({exc})")
        return int(ExitCode.ARGUMENT_ERROR)

    _report_marker(settings)
    config_problems, dependency_problems = _report_settings(settings)
    if config_problems:
        return int(ExitCode.ARGUMENT_ERROR)
    if dependency_problems or engine_problems or tzdata_problems:
        return int(ExitCode.MISSING_DEPENDENCY)
    return int(ExitCode.SUCCESS)


def _report_engines() -> int:
    """List each engine and return the count of missing required ones.

    `available()` ignores the temp root, so any path serves here.
    """
    temp_root = default_temp_dir()
    marker = MarkerEngine(temp_root)
    # columns: label, engine, required
    engines = [
        ("marker (pdf)", marker, True),
        ("pandoc (docx)", PandocEngine(), False),
        ("djvu chain", DjvuEngine(marker, temp_root), False),
    ]
    print("engines:")
    dependency_problems = 0
    for label, engine, required in engines:
        if engine.available():
            status = "OK"
        else:
            status = "MISSING (required)" if required else "MISSING (optional)"
            reason = engine.unavailable_reason()
            if reason is not None:
                status += f": {reason}"
            if required:
                dependency_problems += 1
        print(f"  {label}: {status}")
    return dependency_problems


def _tzdata_available() -> bool:
    """Whether `zoneinfo` can resolve the zone of the default quota reset."""
    try:
        ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        return False
    return True


def _report_tzdata() -> int:
    """Report zoneinfo readiness; return the dependency-problem count (0 or 1)."""
    if _tzdata_available():
        print("tzdata: OK")
        return 0
    print(
        "tzdata: MISSING (required): zoneinfo cannot resolve a time zone; "
        "install the tzdata package"
    )
    return 1


def _cuda_status() -> tuple[bool, int | None]:
    """Whether CUDA is available and, if so, the VRAM of device 0 in MB.

    The import is guarded: the CI install of the fast test layer has no torch,
    and a broken install (a mismatched CUDA DLL) raises OSError or
    RuntimeError. Both read as "no CUDA" in this informational probe.
    """
    try:
        import torch
    except (ImportError, OSError, RuntimeError):
        return False, None
    if not torch.cuda.is_available():
        return False, None
    total_mb = int(torch.cuda.get_device_properties(0).total_memory // (1024 * 1024))
    return True, total_mb


def _report_marker(settings: Settings) -> None:
    """Report the GPU marker would run on and the configured batch size.

    A batch size set without CUDA gets a warning: it was likely tuned for a
    GPU's VRAM.
    """
    print("marker:")
    cuda_available, vram_mb = _cuda_status()
    if cuda_available:
        print(f"  CUDA: available ({vram_mb} MB VRAM)")
    else:
        print("  CUDA: not available (falls back to CPU)")
    batch_size = settings.marker_recognition_batch_size
    if batch_size is None:
        return
    print(f"  recognition_batch_size: {batch_size}")
    if not cuda_available:
        print(
            "  WARNING: recognition_batch_size is set but CUDA is unavailable; "
            "the value was likely tuned against a GPU's VRAM"
        )


def _report_settings(settings: Settings) -> tuple[int, int]:
    """Report each operation's allowed models; return (config, dependency) counts."""
    print("settings:")
    config_problems = 0
    dependency_problems = 0
    for operation in OPERATIONS:
        allowed = settings.operations.get(operation, frozenset())
        for model_key in sorted(allowed):
            model = settings.models.get(model_key)
            if model is None:
                print(f"  {operation}: unknown model '{model_key}'")
                config_problems += 1
                continue
            if not model_can_serve(model, operation):
                print(
                    f"  {operation}: model '{model_key}' has no vision "
                    "(cli access cannot serve ocr/inspection)"
                )
                config_problems += 1
                continue
            availability = build_provider(model).available()
            if availability.ok:
                print(f"  {operation}: model '{model_key}' OK")
            else:
                print(f"  {operation}: model '{model_key}' {availability.reason}")
                dependency_problems += 1
    return config_problems, dependency_problems
