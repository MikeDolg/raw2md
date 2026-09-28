"""The `doctor` subcommand: tool and settings readiness.

The exit code sums up four reports:

- engines: a missing marker is a missing dependency (exit 3); pandoc and the
  djvu chain are optional and only disable their format;
- the torch build, the GPU, and `recognition_batch_size`: informational only;
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
from typing import NamedTuple
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


class _CudaStatus(NamedTuple):
    torch_importable: bool
    # torch.version.cuda: None for a CPU build of torch.
    cuda_build: str | None
    # VRAM of device 0 in MB; None when no GPU is visible.
    vram_mb: int | None


def _cuda_status() -> _CudaStatus:
    """Probe the torch build and the GPU it sees.

    The import is guarded: the CI install of the fast test layer has no torch,
    and a broken install (a mismatched CUDA DLL) raises OSError or
    RuntimeError. Both read as "no torch" in this informational probe.
    """
    try:
        import torch
    except (ImportError, OSError, RuntimeError):
        return _CudaStatus(torch_importable=False, cuda_build=None, vram_mb=None)
    cuda_build = torch.version.cuda
    if cuda_build is None or not torch.cuda.is_available():
        return _CudaStatus(torch_importable=True, cuda_build=cuda_build, vram_mb=None)
    total_mb = int(torch.cuda.get_device_properties(0).total_memory // (1024 * 1024))
    return _CudaStatus(torch_importable=True, cuda_build=cuda_build, vram_mb=total_mb)


def _cuda_line(status: _CudaStatus) -> str:
    """Describe CUDA readiness, with the fix for each way it is missing.

    A CPU build and a missing driver look the same to marker, which silently
    runs on CPU, but they need different fixes: a reinstall of torch or a
    driver install.
    """
    if status.vram_mb is not None:
        return f"CUDA: available ({status.vram_mb} MB VRAM)"
    if not status.torch_importable:
        return "CUDA: not available (torch cannot be imported; falls back to CPU)"
    if status.cuda_build is None:
        return (
            "CUDA: not available (torch is a CPU build; falls back to CPU). "
            "For an install from PyPI, reinstall with the CUDA build: "
            "`uv tool install raw2md --torch-backend cu130 --reinstall`, or for "
            "pip `--extra-index-url https://download.pytorch.org/whl/cu130`. "
            "An install from the project source pins the CUDA build only on "
            "64-bit Intel and AMD machines"
        )
    return (
        f"CUDA: not available (torch is a CUDA {status.cuda_build} build, but "
        "it sees no GPU; falls back to CPU). Check that an NVIDIA GPU is "
        f"present and that its driver supports CUDA {status.cuda_build}"
    )


def _report_marker(settings: Settings) -> None:
    """Report the GPU marker would run on and the configured batch size.

    A batch size set without CUDA gets a warning: it was likely tuned for a
    GPU's VRAM.
    """
    print("marker:")
    status = _cuda_status()
    print(f"  {_cuda_line(status)}")
    batch_size = settings.marker_recognition_batch_size
    if batch_size is None:
        return
    print(f"  recognition_batch_size: {batch_size}")
    if status.vram_mb is None:
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
