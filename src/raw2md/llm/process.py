"""Process helpers shared by the CLI providers.

A CLI provider feeds the prompt on stdin and reads stdout. A hung CLI must
not outlive its timeout, and on Windows the command is often a script that
needs an interpreter, so both concerns live here.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from contextlib import suppress


def spawn(argv: list[str], /) -> subprocess.Popen[str]:
    """Start `argv` in its own process group so a timeout kills its whole tree.

    On Windows the command is often `cmd.exe /c <script>.cmd`, and killing only
    `cmd.exe` would leave the wrapped node process running.
    """
    if sys.platform == "win32":
        return subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        start_new_session=True,
    )


def kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        return
    with suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def run_with_timeout(
    argv: list[str], input_text: str, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run `argv`; `subprocess.run(timeout=...)` would kill the child only."""
    process = spawn(argv)
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process.pid)
        process.wait()
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def resolve_command(command: str) -> list[str]:
    """Return the argv prefix to invoke `command`.

    On Windows, CreateProcess cannot start a `.cmd`, `.bat`, or `.ps1` script,
    so the script gets its interpreter.
    """
    resolved = shutil.which(command) or command
    if sys.platform == "win32":
        lowered = resolved.lower()
        if lowered.endswith(".ps1"):
            return ["powershell", "-File", resolved]
        if lowered.endswith((".cmd", ".bat")):
            return ["cmd.exe", "/c", resolved]
    return [resolved]
