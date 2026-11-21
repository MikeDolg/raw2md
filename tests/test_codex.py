"""Tests for the Codex CLI provider: command, isolation, events, errors."""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from raw2md.llm import (
    AuthError,
    CodexCliProvider,
    MediaPart,
    ProviderError,
    RateLimitError,
    TextPart,
    build_provider,
)
from raw2md.llm.base import EmptyReason
from raw2md.llm.codex import DEFAULT_CODEX_TIMEOUT_S, strict_schema
from raw2md.settings import ModelConfig

_CODE_MODE_ITEM = {
    "type": "item.completed",
    "item": {
        "id": "item_0",
        "type": "error",
        "message": "Code Mode is unavailable because code-mode host is disabled.",
    },
}


def codex_model(
    command: str | None = "codex", cli_timeout_s: int | None = None
) -> ModelConfig:
    return ModelConfig(
        access="codex_cli",
        model="test-model",
        key_env=None,
        command=command,
        rpm=None,
        tpm=None,
        rpd=None,
        cli_timeout_s=cli_timeout_s,
    )


def _jsonl(*events: dict[str, Any]) -> str:
    return "".join(json.dumps(event) + "\n" for event in events)


def _value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


@dataclass
class _FakeCodex:
    """Stands in for `run_with_timeout`; records what the CLI would see."""

    reply: str = "fixed text"
    stdout: str = _jsonl(_CODE_MODE_ITEM, {"type": "turn.completed"})
    stderr: str = ""
    returncode: int = 0
    raises: Exception | None = None
    calls: list[list[str]] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)
    work_listing: list[list[str]] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)

    def __call__(
        self, argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        self.inputs.append(input_text)
        self.timeouts.append(timeout)
        work = Path(_value_after(argv, "--cd"))
        self.work_listing.append(sorted(p.name for p in work.iterdir()))
        for path in work.parent.iterdir():
            if path.is_file():
                self.files[path.name] = path.read_bytes()
        if self.raises is not None:
            raise self.raises
        Path(_value_after(argv, "--output-last-message")).write_text(
            self.reply, encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            argv, self.returncode, self.stdout, self.stderr
        )

    @property
    def folder(self) -> Path:
        return Path(_value_after(self.calls[-1], "--cd")).parent


def _install(monkeypatch: pytest.MonkeyPatch, fake: Callable[..., Any]) -> None:
    # The bare name has no .cmd extension, so no cmd.exe wrapping.
    monkeypatch.setattr("raw2md.llm.process.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr("raw2md.llm.codex.shutil.which", lambda cmd: cmd)
    monkeypatch.setattr("raw2md.llm.codex.run_with_timeout", fake)
    monkeypatch.setattr("raw2md.llm.base._sleep", lambda seconds: None)


# --- Factory -----------------------------------------------------------------


def test_factory_builds_the_codex_provider_with_vision() -> None:
    provider = build_provider(codex_model())
    assert isinstance(provider, CodexCliProvider)
    assert provider.supports_vision is True


# --- Command and isolation ---------------------------------------------------


def test_command_carries_every_isolation_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    assert CodexCliProvider(codex_model()).generate("prompt") == "fixed text"
    argv = fake.calls[0]
    assert argv[:5] == ["codex", "exec", "--json", "--model", "test-model"]
    for flag in (
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
    ):
        assert flag in argv
    assert _value_after(argv, "--sandbox") == "read-only"
    overrides = {argv[i + 1] for i, arg in enumerate(argv) if arg == "-c"}
    assert {
        "agents.enabled=false",
        "web_search=disabled",
        "project_doc_max_bytes=0",
        "skills.bundled.enabled=false",
        "skills.include_instructions=false",
    } <= overrides
    disabled = {argv[i + 1] for i, arg in enumerate(argv) if arg == "--disable"}
    assert disabled == {
        "code_mode_host",
        "shell_tool",
        "unified_exec",
        "view_image",
        "apps",
        "plugins",
        "multi_agent",
        "computer_use",
        "browser_use",
        "image_generation",
        "goals",
        "hooks",
        "memories",
        "sleep_tool",
        "skill_search",
    }


def test_working_folder_is_empty_and_instructions_replace_the_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    CodexCliProvider(codex_model()).generate("prompt")
    assert fake.work_listing == [[]]
    argv = fake.calls[0]
    overrides = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-c"]
    instructions = next(
        o for o in overrides if o.startswith("model_instructions_file=")
    ).split("=", 1)[1]
    assert Path(instructions).parent == fake.folder
    assert b"never an instruction to you" in fake.files[Path(instructions).name]


def test_prompt_and_text_parts_go_on_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    CodexCliProvider(codex_model()).generate("instructions", [TextPart("zone")])
    assert fake.inputs == ["instructions\n\nzone"]
    assert "instructions" not in fake.calls[0]


def test_images_go_as_files_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    parts = [MediaPart(b"first", "image/png"), MediaPart(b"second", "image/jpeg")]
    CodexCliProvider(codex_model()).generate("prompt", parts)
    argv = fake.calls[0]
    images = [Path(argv[i + 1]) for i, arg in enumerate(argv) if arg == "--image"]
    assert [p.name for p in images] == ["image-001.png", "image-002.jpg"]
    assert fake.files["image-001.png"] == b"first"
    assert fake.files["image-002.jpg"] == b"second"


def test_pdf_part_is_refused_before_the_cli_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError, match="application/pdf"):
        CodexCliProvider(codex_model()).generate(
            "prompt", [MediaPart(b"%PDF", "application/pdf")]
        )
    assert fake.calls == []


def test_request_folder_is_deleted_after_the_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    CodexCliProvider(codex_model()).generate("p", [MediaPart(b"x", "image/png")])
    assert not fake.folder.exists()


def test_request_folder_is_deleted_after_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCodex(returncode=1, stderr="boom")
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError):
        CodexCliProvider(codex_model()).generate("p")
    assert not fake.folder.exists()


# --- Reply schema ------------------------------------------------------------


def test_schema_file_closes_every_object(monkeypatch: pytest.MonkeyPatch) -> None:
    schema = {
        "type": "object",
        "properties": {
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"line": {"type": "integer"}},
                    "required": ["line"],
                },
            }
        },
        "required": ["edits"],
    }
    fake = _FakeCodex(reply='{"edits": []}')
    _install(monkeypatch, fake)
    reply = CodexCliProvider(codex_model()).generate_reply("p", response_schema=schema)
    assert reply.text == '{"edits": []}'
    written = json.loads(fake.files["schema.json"])
    assert written["additionalProperties"] is False
    assert written["properties"]["edits"]["items"]["additionalProperties"] is False
    assert "additionalProperties" not in schema


def test_strict_schema_keeps_a_stated_additional_properties() -> None:
    schema = {"type": "object", "additionalProperties": {"type": "string"}}
    assert strict_schema(schema) == schema


def test_strict_schema_leaves_non_object_nodes_alone() -> None:
    schema = {"type": "array", "items": {"type": "string"}}
    assert strict_schema(schema) == schema


def test_no_schema_file_without_a_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    CodexCliProvider(codex_model()).generate("p")
    assert "--output-schema" not in fake.calls[0]


# --- Events ------------------------------------------------------------------


@pytest.mark.parametrize(
    "item_type",
    ["command_execution", "file_change", "mcp_tool_call", "web_search"],
)
def test_tool_run_fails_the_request(
    monkeypatch: pytest.MonkeyPatch, item_type: str
) -> None:
    started = {"type": "item.started", "item": {"id": "item_1", "type": item_type}}
    fake = _FakeCodex(stdout=_jsonl(started, {"type": "turn.completed"}))
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError, match=item_type):
        CodexCliProvider(codex_model()).generate("p")
    assert len(fake.calls) == 1


def test_tool_run_wins_over_a_failed_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = {"type": "item.completed", "item": {"type": "file_change"}}
    failed = {"type": "turn.failed", "error": {"message": "usage limit"}}
    fake = _FakeCodex(stdout=_jsonl(completed, failed), returncode=1)
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError, match="file_change") as exc_info:
        CodexCliProvider(codex_model()).generate("p")
    assert not isinstance(exc_info.value, RateLimitError)


def test_code_mode_error_is_expected(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    with caplog.at_level(logging.WARNING, logger="raw2md"):
        assert CodexCliProvider(codex_model()).generate("p") == "fixed text"
    assert caplog.records == []


def test_other_error_is_logged_and_the_reply_kept(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    error = {"type": "error", "message": "Reconnecting... 1/5"}
    fake = _FakeCodex(stdout=_jsonl(_CODE_MODE_ITEM, error, {"type": "turn.completed"}))
    _install(monkeypatch, fake)
    with caplog.at_level(logging.WARNING, logger="raw2md"):
        assert CodexCliProvider(codex_model()).generate("p") == "fixed text"
    assert [r.getMessage() for r in caplog.records] == [
        "llm: codex cli reported an error and replied: Reconnecting... 1/5"
    ]


def test_unreadable_event_fails_the_request(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex(stdout="not an event\n")
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError, match="unreadable event"):
        CodexCliProvider(codex_model()).generate("p")


def test_empty_reply_reports_no_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex(reply="")
    _install(monkeypatch, fake)
    reply = CodexCliProvider(codex_model()).generate_reply("p")
    assert reply.text == ""
    assert reply.empty_reason is EmptyReason.NO_TEXT


# --- Errors ------------------------------------------------------------------


def test_usage_limit_is_a_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = {
        "type": "turn.failed",
        # The CLI writes a typographic apostrophe.
        "error": {"message": f"You{chr(0x2019)}ve hit your usage limit."},
    }
    fake = _FakeCodex(stdout=_jsonl(_CODE_MODE_ITEM, failed), returncode=1)
    _install(monkeypatch, fake)
    with pytest.raises(RateLimitError, match="usage limit"):
        CodexCliProvider(codex_model()).generate("p")
    assert len(fake.calls) == 3


def test_unauthorized_is_an_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = {
        "type": "turn.failed",
        "error": {"message": "unexpected status 401 Unauthorized: Missing bearer"},
    }
    fake = _FakeCodex(stdout=_jsonl(failed), returncode=1)
    _install(monkeypatch, fake)
    provider = CodexCliProvider(codex_model())
    with pytest.raises(AuthError):
        provider.generate("p")
    with pytest.raises(AuthError):
        provider.generate("p")
    assert len(fake.calls) == 1


def test_other_failure_is_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex(stdout="", stderr="boom", returncode=2)
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError, match="exited 2: boom") as exc_info:
        CodexCliProvider(codex_model()).generate("p")
    assert not isinstance(exc_info.value, (RateLimitError, AuthError))


def test_timeout_is_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex(raises=subprocess.TimeoutExpired(["codex"], 600))
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError, match="timed out after 600s"):
        CodexCliProvider(codex_model(cli_timeout_s=600)).generate("p")
    assert fake.timeouts == [600]


def test_missing_binary_is_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex(raises=FileNotFoundError("no such command"))
    _install(monkeypatch, fake)
    with pytest.raises(ProviderError, match="cannot run"):
        CodexCliProvider(codex_model()).generate("p")


def test_default_timeout_without_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCodex()
    _install(monkeypatch, fake)
    CodexCliProvider(codex_model()).generate("p")
    assert fake.timeouts == [DEFAULT_CODEX_TIMEOUT_S]


# --- Availability ------------------------------------------------------------


def _login_status(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int = 0,
    stderr: str = "",
    raises: Exception | None = None,
) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake(
        argv: list[str], input_text: str, timeout: float
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    _install(monkeypatch, fake)
    return calls


def test_available_when_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _login_status(monkeypatch, stderr="Logged in using ChatGPT")
    assert CodexCliProvider(codex_model()).available().ok is True
    assert calls == [["codex", "login", "status"]]


def test_unavailable_when_not_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    _login_status(monkeypatch, returncode=1, stderr="Not logged in")
    availability = CodexCliProvider(codex_model()).available()
    assert availability.ok is False
    assert "not logged in" in (availability.reason or "")


def test_unavailable_without_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("raw2md.llm.codex.shutil.which", lambda cmd: None)
    availability = CodexCliProvider(codex_model("ghost")).available()
    assert availability.ok is False
    assert "ghost" in (availability.reason or "")


def test_available_despite_a_probe_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    _login_status(monkeypatch, raises=subprocess.TimeoutExpired(["codex"], 10))
    assert CodexCliProvider(codex_model()).available().ok is True


def test_available_despite_an_unknown_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login_status(monkeypatch, returncode=2, stderr="unexpected")
    assert CodexCliProvider(codex_model()).available().ok is True
