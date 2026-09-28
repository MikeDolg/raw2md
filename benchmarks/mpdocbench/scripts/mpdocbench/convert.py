"""Convert the built PDFs with raw2md, and keep what the result has to state."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from typing import Any

from mpdocbench.pins import BenchmarkError, RunDir, dump_yaml, load_yaml, system_name

# raw2md stops before any document on these, so the run holds nothing to score.
_FATAL_EXIT_CODES = {2: "an argument error", 3: "a missing dependency"}


def raw2md_command(run: RunDir, llm: str | None) -> list[str]:
    """The conversion of one run. `-d` keeps the engine output as a stage file.

    `-s` makes a second call finish an interrupted run instead of starting over:
    a document whose result exists is not converted again.
    """
    command = [str(run.pdfs), "-o", str(run.outputs), "-d", "-s", "-e", "marker"]
    if llm is not None:
        command += ["-i", llm, "-p", llm]
    return command


def gpu_name() -> str | None:
    """The first GPU nvidia-smi reports, or None on a machine without one."""
    if shutil.which("nvidia-smi") is None:
        return None
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        check=False,
        capture_output=True,
        text=True,
    )
    lines = completed.stdout.strip().splitlines()
    return lines[0].strip() if completed.returncode == 0 and lines else None


def convert(run: RunDir, llm: str | None) -> dict[str, Any]:
    """Run raw2md over the run's PDFs and add the session to `run.yaml`."""
    if not run.record.is_file() or not any(run.pdfs.glob("*.pdf")):
        raise BenchmarkError(f"{run.root} holds no built PDFs; run build first")
    record = load_yaml(run.record)
    if record.get("llm", None) != llm and record.get("sessions"):
        raise BenchmarkError(
            f"{run.root} was converted with --llm {record.get('llm')}; a run holds"
            " one variant, so start another run folder"
        )
    arguments = raw2md_command(run, llm)
    # The interpreter of this script, not a `raw2md` on PATH: the version the
    # result names is the one importable here.
    command = [sys.executable, "-m", "raw2md", *arguments]
    print("raw2md " + " ".join(arguments), flush=True)
    started = time.monotonic()
    completed = subprocess.run(
        command, check=False, env=dict(os.environ, PYTHONIOENCODING="utf-8")
    )
    minutes = (time.monotonic() - started) / 60
    if completed.returncode in _FATAL_EXIT_CODES:
        raise BenchmarkError(
            f"raw2md stopped on {_FATAL_EXIT_CODES[completed.returncode]}"
            f" (exit code {completed.returncode})"
        )
    # Any other code still leaves a result for every document that converted;
    # the ones that did not are counted as failed when the run is scored.
    sessions = list(record.get("sessions") or [])
    sessions.append(
        {
            "finished": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "minutes": round(minutes, 1),
            "exit_code": completed.returncode,
        }
    )
    record.update(
        {
            "raw2md": importlib.metadata.version("raw2md"),
            "command": "raw2md <pdf> " + " ".join(arguments[3:]),
            "llm": llm,
            "gpu": gpu_name(),
            "platform": system_name(),
            "sessions": sessions,
        }
    )
    dump_yaml(run.record, record)
    return record
