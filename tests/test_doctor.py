"""Tests for the doctor subcommand: settings/tool readiness and exit codes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfoNotFoundError

import pytest

from raw2md.doctor import _cuda_status, _CudaStatus, run_doctor
from raw2md.exit_codes import ExitCode
from raw2md.paths import settings_file

_MISSING_CMD = "definitely-not-a-real-command-xyz"
_GPU = _CudaStatus(torch_importable=True, cuda_build="13.0", vram_mb=4096)
_CPU_BUILD = _CudaStatus(torch_importable=True, cuda_build=None, vram_mb=None)


def write_settings(data: Any) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data)
    path.write_text(text, encoding="utf-8")


def gemini_only(allowed: str = "gemini_api") -> dict[str, Any]:
    return {
        "models": {
            "gemini_api": {
                "access": "api",
                "key_env": "GOOGLE_API_KEY",
                "model": "gemini-2.5-flash",
            }
        },
        "operations": {
            "ocr": {"allowed": [allowed]},
            "inspection": {"allowed": [allowed]},
            "post": {"allowed": [allowed]},
        },
    }


def test_ready_settings_returns_success(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Readiness also needs the google-genai SDK.
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())
    assert run_doctor() == int(ExitCode.SUCCESS)


def test_missing_api_sdk_is_missing_dependency(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A missing SDK is a global exit-3 dependency.
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())
    assert run_doctor() == int(ExitCode.MISSING_DEPENDENCY)


def test_missing_settings_uses_defaults(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default settings need an API key that is unset.
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert run_doctor() == int(ExitCode.MISSING_DEPENDENCY)


def test_malformed_settings_is_argument_error(home: Path) -> None:
    write_settings("{ not valid json")
    assert run_doctor() == int(ExitCode.ARGUMENT_ERROR)


def test_reserved_engine_name_is_argument_error(home: Path) -> None:
    # doctor parses settings like a run does.
    data = {"models": {"djvu": {"access": "cli", "command": "c", "model": "x"}}}
    write_settings(data)
    assert run_doctor() == int(ExitCode.ARGUMENT_ERROR)


def test_unknown_model_is_argument_error(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    data = gemini_only()
    data["operations"]["post"]["allowed"] = ["ghost"]
    write_settings(data)
    assert run_doctor() == int(ExitCode.ARGUMENT_ERROR)


def test_cli_model_in_vision_role_is_argument_error(home: Path) -> None:
    data = {
        "models": {"local_cli": {"access": "cli", "command": "echo", "model": "m"}},
        "operations": {
            "ocr": {"allowed": ["local_cli"]},
            "inspection": {"allowed": []},
            "post": {"allowed": ["local_cli"]},
        },
    }
    write_settings(data)
    assert run_doctor() == int(ExitCode.ARGUMENT_ERROR)


def test_missing_api_key_is_missing_dependency(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    write_settings(gemini_only())
    assert run_doctor() == int(ExitCode.MISSING_DEPENDENCY)


def test_missing_cli_command_is_missing_dependency(home: Path) -> None:
    data = {
        "models": {
            "local_cli": {"access": "cli", "command": _MISSING_CMD, "model": "m"}
        },
        "operations": {
            "ocr": {"allowed": []},
            "inspection": {"allowed": []},
            "post": {"allowed": ["local_cli"]},
        },
    }
    write_settings(data)
    assert run_doctor() == int(ExitCode.MISSING_DEPENDENCY)


def test_missing_marker_is_missing_dependency(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # marker is required, so its absence is a dependency problem.
    monkeypatch.setattr("raw2md.engines.marker.find_spec", lambda name: None)
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())
    assert run_doctor() == int(ExitCode.MISSING_DEPENDENCY)


def test_missing_tzdata_is_missing_dependency(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A broken zone lookup would mis-time every daily quota reset.
    def _raise(key: str) -> None:
        raise ZoneInfoNotFoundError(key)

    monkeypatch.setattr("raw2md.doctor.ZoneInfo", _raise)
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())
    assert run_doctor() == int(ExitCode.MISSING_DEPENDENCY)


def test_missing_tzdata_with_default_settings_is_missing_dependency(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default settings state a zone, so parsing them hits the broken
    # database; that is no config mistake.
    def _raise(key: str) -> None:
        raise ZoneInfoNotFoundError(key)

    monkeypatch.setattr("raw2md.doctor.ZoneInfo", _raise)
    monkeypatch.setattr("raw2md.settings.ZoneInfo", _raise)
    assert run_doctor() == int(ExitCode.MISSING_DEPENDENCY)


def test_missing_tzdata_does_not_reclassify_unrelated_settings_errors(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A broken zone database must not mask an unrelated settings mistake.
    def _raise(key: str) -> None:
        raise ZoneInfoNotFoundError(key)

    monkeypatch.setattr("raw2md.doctor.ZoneInfo", _raise)
    data = gemini_only()
    data["models"]["gemini_api"]["access"] = "carrier-pigeon"
    write_settings(data)
    assert run_doctor() == int(ExitCode.ARGUMENT_ERROR)


def test_report_shows_tzdata_ok(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())
    run_doctor()
    assert "tzdata: OK" in capsys.readouterr().out


def test_missing_optional_engines_do_not_affect_exit_code(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pandoc and the djvu chain never change the exit code.
    monkeypatch.setattr(
        "raw2md.engines.pandoc.PandocEngine.available", lambda self: False
    )
    monkeypatch.setattr("raw2md.engines.djvu.DjvuEngine.available", lambda self: False)
    monkeypatch.setattr("raw2md.llm.gemini.find_spec", lambda name: object())
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())
    assert run_doctor() == int(ExitCode.SUCCESS)


def test_report_names_required_pandoc_version_when_too_old(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An old pandoc stays optional but names the version needed; otherwise it
    # reports ready until every docx fails.
    monkeypatch.setattr(
        "raw2md.engines.pandoc.shutil.which",
        lambda name: "/usr/bin/pandoc" if name == "pandoc" else None,
    )
    monkeypatch.setattr(
        "raw2md.engines.pandoc._pandoc_version", lambda pandoc: (3, 1, 3)
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())

    exit_code = run_doctor()

    out = capsys.readouterr().out
    assert exit_code == int(ExitCode.SUCCESS)
    assert "pandoc (docx): MISSING (optional): pandoc 3.1.3" in out
    assert "3.1.9" in out


def test_report_lists_engines(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "secret")
    write_settings(gemini_only())
    run_doctor()
    out = capsys.readouterr().out
    assert "engines:" in out
    assert "marker (pdf)" in out


def test_report_shows_cuda_available_with_vram(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("raw2md.doctor._cuda_status", lambda: _GPU)
    write_settings(gemini_only())
    run_doctor()
    out = capsys.readouterr().out
    assert "marker:" in out
    assert "CUDA: available (4096 MB VRAM)" in out


def test_report_shows_cuda_unavailable(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("raw2md.doctor._cuda_status", lambda: _CPU_BUILD)
    write_settings(gemini_only())
    run_doctor()
    assert "CUDA: not available" in capsys.readouterr().out


def _fake_torch(cuda_build: str | None, gpu_visible: bool) -> Any:
    device = SimpleNamespace(total_memory=4096 * 1024 * 1024)
    return SimpleNamespace(
        version=SimpleNamespace(cuda=cuda_build),
        cuda=SimpleNamespace(
            is_available=lambda: gpu_visible,
            get_device_properties=lambda index: device,
        ),
    )


def test_cuda_status_reads_a_cpu_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(None, gpu_visible=False))
    assert _cuda_status() == _CPU_BUILD


def test_cuda_status_reads_a_cuda_build_without_a_gpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch("13.0", gpu_visible=False))
    assert _cuda_status() == _CudaStatus(
        torch_importable=True, cuda_build="13.0", vram_mb=None
    )


def test_cuda_status_reads_a_visible_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch("13.0", gpu_visible=True))
    assert _cuda_status() == _GPU


def test_cuda_status_without_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    # A None entry makes the import raise ImportError.
    monkeypatch.setitem(sys.modules, "torch", None)
    assert _cuda_status() == _CudaStatus(
        torch_importable=False, cuda_build=None, vram_mb=None
    )


def test_report_points_a_cpu_build_to_a_reinstall(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("raw2md.doctor._cuda_status", lambda: _CPU_BUILD)
    write_settings(gemini_only())
    run_doctor()
    out = capsys.readouterr().out
    assert "torch is a CPU build" in out
    assert "--torch-backend cu130" in out
    assert "driver" not in out


def test_report_points_a_cuda_build_without_a_gpu_to_the_driver(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    status = _CudaStatus(torch_importable=True, cuda_build="13.0", vram_mb=None)
    monkeypatch.setattr("raw2md.doctor._cuda_status", lambda: status)
    write_settings(gemini_only())
    run_doctor()
    out = capsys.readouterr().out
    assert "torch is a CUDA 13.0 build" in out
    assert "driver supports CUDA 13.0" in out
    assert "--torch-backend" not in out


def test_report_omits_batch_size_line_when_unset(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("raw2md.doctor._cuda_status", lambda: _CPU_BUILD)
    write_settings(gemini_only())
    run_doctor()
    assert "recognition_batch_size" not in capsys.readouterr().out


def test_report_warns_batch_size_set_without_cuda(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A batch size tuned for VRAM deserves a flag on a run without CUDA.
    monkeypatch.setattr("raw2md.doctor._cuda_status", lambda: _CPU_BUILD)
    data = gemini_only()
    data["marker"] = {"recognition_batch_size": 8}
    write_settings(data)
    run_doctor()
    out = capsys.readouterr().out
    assert "recognition_batch_size: 8" in out
    assert "WARNING" in out


def test_report_no_warning_when_cuda_available_with_batch_size(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("raw2md.doctor._cuda_status", lambda: _GPU)
    data = gemini_only()
    data["marker"] = {"recognition_batch_size": 8}
    write_settings(data)
    run_doctor()
    out = capsys.readouterr().out
    assert "recognition_batch_size: 8" in out
    assert "WARNING" not in out


def test_doctor_rejects_unexpected_arguments(home: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_doctor(["bogus"])
    assert exc_info.value.code == 2


def test_doctor_help_exits_zero(home: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        run_doctor(["--help"])
    assert exc_info.value.code == 0
