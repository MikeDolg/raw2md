"""Claude CLI provider: text-only via `claude -p` print mode.

The CLI has no vision, so it serves post-processing only. The prompt goes on
stdin, which avoids the command-line length limit on a large zone.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Sequence
from contextlib import suppress

from raw2md.llm.base import (
    AuthError,
    Availability,
    MediaPart,
    Part,
    Provider,
    ProviderError,
    RateLimitError,
    TextPart,
)

# Substrings that mark a quota or rate-limit failure in the CLI's output.
_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "overloaded", "429", "quota")

# Substrings that mark a refused login, taken from the CLI's own wording
# (`claude -p` with no session prints this to stdout, not stderr).
_AUTH_ERROR_MARKERS = ("not logged in", "please run /login")

# A hung CLI would block the batch. 2 minutes covers an ordinary zone; a large
# one can run past it, so `cli_timeout_s` in settings.json overrides it.
DEFAULT_CLAUDE_TIMEOUT_S: int = 120

# `auth status` is a local check with no network call; a few seconds is
# generous headroom, not a measured ceiling.
_AUTH_STATUS_TIMEOUT_S: float = 10.0


def _spawn(argv: list[str], /) -> subprocess.Popen[str]:
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


def _kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        return
    with suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def _run_with_timeout(
    argv: list[str], input_text: str, timeout: float
) -> subprocess.CompletedProcess[str]:
    """Run `argv`; `subprocess.run(timeout=...)` would kill the child only."""
    process = _spawn(argv)
    try:
        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(process.pid)
        process.wait()
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _resolve_command(command: str) -> list[str]:
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


class ClaudeCliProvider(Provider):
    """Text generation through a `claude`-compatible CLI in print mode."""

    def available(self) -> Availability:
        command = self._model.command
        if not command or shutil.which(command) is None:
            return Availability(False, f"command '{command}' not found in PATH")
        return self._probe_login(command)

    def _probe_login(self, command: str) -> Availability:
        """Probe login with the CLI's free `auth status` check.

        A network failure has no way to happen here, unlike the API key
        probe: the check is local. A failure to run or to parse it still
        leaves the decision to the run's own requests, the same policy, so an
        unexpected CLI output does not fail a stage that may not need it.
        """
        argv = [*_resolve_command(command), "auth", "status"]
        try:
            completed = _run_with_timeout(argv, "", _AUTH_STATUS_TIMEOUT_S)
            status = json.loads(completed.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return Availability(True)
        if isinstance(status, dict) and status.get("loggedIn") is False:
            return Availability(False, f"'{command}' is not logged in")
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        # A media part means the caller bypassed the capability matrix.
        if any(isinstance(part, MediaPart) for part in parts):
            raise ValueError("claude CLI provider has no vision; got media parts")
        command = self._model.command
        if not command:
            raise ProviderError("no cli command configured")
        return self._send(lambda: self._request(command, prompt, parts))

    def _request(self, command: str, prompt: str, parts: Sequence[Part]) -> str:
        full = _compose(prompt, parts)
        argv = [*_resolve_command(command), "-p", "--model", self._model.model]
        self._reserve_rpd()
        timeout = self._model.cli_timeout_s or DEFAULT_CLAUDE_TIMEOUT_S
        try:
            completed = _run_with_timeout(argv, full, timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"'{command}' timed out after {timeout}s") from exc
        except OSError as exc:
            raise ProviderError(f"cannot run '{command}': {exc}") from exc
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            # A refused login prints to stdout, and a warning on stderr must
            # not hide it, so both streams are checked.
            for stream in (stderr, stdout):
                if _is_auth_error(stream):
                    raise AuthError(stream)
            detail = stderr or stdout
            if _is_rate_limit(detail):
                raise RateLimitError(detail or "rate limit")
            raise ProviderError(f"'{command}' exited {completed.returncode}: {detail}")
        return completed.stdout


def _compose(prompt: str, parts: Sequence[Part]) -> str:
    segments = [prompt]
    segments.extend(part.text for part in parts if isinstance(part, TextPart))
    return "\n\n".join(segments)


def _is_rate_limit(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


def _is_auth_error(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)
