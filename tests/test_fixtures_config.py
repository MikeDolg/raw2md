"""The bundled test-config fixtures load and expose the expected shape.

A broken fixture would otherwise fail only in a later test, far from the cause.
"""

from pathlib import Path

from raw2md.paths import prompts_file, settings_file
from raw2md.prompts import default_prompts, load_prompts, resolve_prompt
from raw2md.settings import load_settings


def test_offline_fixture_loads(raw2md_home: Path) -> None:
    settings = load_settings(settings_file())
    assert set(settings.models) == {"test_api", "test_cli"}
    assert settings.models["test_api"].access == "gemini_api"
    assert settings.models["test_cli"].access == "claude_cli"
    assert settings.operations["ocr"] == frozenset({"test_api"})
    assert settings.engine_recognition_batch_size == 8

    prompts = load_prompts(prompts_file())
    # The per-model override path is exercised from a file, not just defaults.
    assert resolve_prompt(prompts, "post", "test_cli") != prompts.post.default
    assert resolve_prompt(prompts, "post", "test_api") == prompts.post.default


def test_real_fixture_loads(raw2md_home_real: Path) -> None:
    settings = load_settings(settings_file())
    assert set(settings.models) == {
        "gemini_api",
        "claude_cli",
        "codex_cli",
        "openrouter_api",
    }
    assert settings.models["gemini_api"].key_env == "GOOGLE_API_KEY"
    assert settings.models["openrouter_api"].key_env == "OPENROUTER_API_KEY"
    assert settings.operations["inspection"] == frozenset(
        {"gemini_api", "codex_cli", "openrouter_api"}
    )
    assert settings.engine_recognition_batch_size == 8

    # The real profile drives live models, so it carries the shipped prompts.
    assert load_prompts(prompts_file()) == default_prompts()
