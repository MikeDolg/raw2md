"""Tests for argument parsing, the subcommand/path dispatcher, and validation."""

from pathlib import Path

import pytest

from raw2md import cli
from raw2md.cli import (
    RESERVED_SUBCOMMANDS,
    build_input_parser,
    classify_invocation,
    main,
    run_resume_command,
)
from raw2md.config import (
    CliArgumentError,
    RunConfig,
    build_config,
    validate_latex_fix,
    validate_models_allowed,
)
from raw2md.exit_codes import ExitCode
from raw2md.queue import Queue, queue_path, save_queue
from raw2md.settings import default_settings


def parse_config(argv: list[str]) -> RunConfig:
    """Parse argv into a RunConfig the way a run does, without validation."""
    return build_config(build_input_parser().parse_args(argv))


# --- Parsing into RunConfig ------------------------------------------------


def test_defaults() -> None:
    config = parse_config(["input.pdf"])
    assert config.input_path == Path("input.pdf")
    assert config.output_dir is None
    assert config.skip_existing is False
    assert config.yaml_header is True
    assert config.extract_images is True
    assert config.llm_ocr is None
    assert config.llm_inspection is None
    assert config.llm_post is None
    assert config.llm_latex_fix is False
    assert config.cuda is True
    assert config.log_file is True
    assert config.debug is False


def test_all_flags() -> None:
    config = parse_config(
        [
            "doc.pdf",
            "--output-dir",
            "out",
            "--skip-existing",
            "--no-yaml",
            "--disable-image-extraction",
            "--engine",
            "gemini_api",
            "--llm-post",
            "claude_cli",
            "--llm-inspection",
            "gemini_api",
            "--llm-latex-fix",
            "--cuda",
            "off",
            "--no-log-file",
            "--debug",
        ]
    )
    assert config.input_path == Path("doc.pdf")
    assert config.output_dir == Path("out")
    assert config.skip_existing is True
    assert config.yaml_header is False
    assert config.extract_images is False
    assert config.llm_ocr == "gemini_api"
    assert config.llm_post == "claude_cli"
    assert config.llm_inspection == "gemini_api"
    assert config.llm_latex_fix is True
    assert config.cuda is False
    assert config.log_file is False
    assert config.debug is True


def test_llm_none_disables_operation() -> None:
    config = parse_config(["x.pdf", "--llm-post", "none"])
    assert config.llm_post is None


# --- --engine parsing --------------------------------------------------------


def test_engine_default_is_marker_route() -> None:
    config = parse_config(["x.pdf"])
    assert config.llm_ocr is None


def test_engine_explicit_marker_is_marker_route() -> None:
    config = parse_config(["x.pdf", "--engine", "marker"])
    assert config.llm_ocr is None


def test_engine_model_key_routes_to_llm_ocr() -> None:
    config = parse_config(["x.pdf", "--engine", "gemini_api"])
    assert config.llm_ocr == "gemini_api"


def test_removed_llm_ocr_flag_exits_2() -> None:
    # The removed spelling must fail loudly, not read as a positional.
    with pytest.raises(SystemExit) as exc_info:
        build_input_parser().parse_args(["x.pdf", "--llm-ocr", "gemini_api"])
    assert exc_info.value.code == 2


def test_no_log_file_flag_disables_logging() -> None:
    config = parse_config(["x.pdf", "--no-log-file"])
    assert config.log_file is False


def test_removed_overwrite_flag_exits_2_via_main() -> None:
    # Replacing the tool's own result is the default, so the flag fails.
    with pytest.raises(SystemExit) as exc_info:
        main(["x.pdf", "--overwrite"])
    assert exc_info.value.code == 2


def test_invalid_cuda_choice_is_argument_error() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_input_parser().parse_args(["x.pdf", "--cuda", "maybe"])
    assert exc_info.value.code == 2


def test_missing_input_defaults_to_current_folder() -> None:
    config = parse_config([])
    assert config.input_path == Path()


def test_short_flags_match_long_forms() -> None:
    long_config = parse_config(
        [
            "doc.pdf",
            "--output-dir",
            "out",
            "--skip-existing",
            "--engine",
            "gemini_api",
            "--llm-post",
            "claude_cli",
            "--llm-inspection",
            "gemini_api",
            "--debug",
        ]
    )
    short_config = parse_config(
        [
            "doc.pdf",
            "-o",
            "out",
            "-s",
            "-e",
            "gemini_api",
            "-p",
            "claude_cli",
            "-i",
            "gemini_api",
            "-d",
        ]
    )
    assert short_config == long_config


def test_short_version_flag_matches_long_form(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as short_exit:
        build_input_parser().parse_args(["-v"])
    short_output = capsys.readouterr().out
    with pytest.raises(SystemExit) as long_exit:
        build_input_parser().parse_args(["--version"])
    long_output = capsys.readouterr().out
    assert short_exit.value.code == long_exit.value.code == 0
    assert short_output == long_output


def test_help_flag_is_still_h() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_input_parser().parse_args(["-h"])
    assert exc_info.value.code == 0


def test_removed_overwrite_flag_has_no_short_form() -> None:
    # A short alias would clash with -o/--output-dir under any spelling.
    with pytest.raises(SystemExit) as exc_info:
        build_input_parser().parse_args(["x.pdf", "-w"])
    assert exc_info.value.code == 2


def test_help_does_not_wrap_widest_option_header() -> None:
    # The widest option header must fit the help position.
    help_text = build_input_parser().format_help()
    for line in help_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("-i MODEL, --llm-inspection MODEL"):
            assert "inspection via an LLM model key" in line


# --- Validation ------------------------------------------------------------


def test_model_outside_allowed_raises() -> None:
    config = parse_config(["x.pdf", "--llm-post", "bad"])
    with pytest.raises(CliArgumentError):
        validate_models_allowed(config, {"post": frozenset({"good"})})


def test_model_inside_allowed_is_valid() -> None:
    config = parse_config(
        ["x.pdf", "--engine", "g", "--llm-post", "c", "--llm-inspection", "g"]
    )
    validate_models_allowed(
        config,
        {
            "ocr": frozenset({"g"}),
            "post": frozenset({"c"}),
            "inspection": frozenset({"g"}),
        },
    )


def test_engine_key_outside_ocr_allowed_raises() -> None:
    config = parse_config(["x.pdf", "--engine", "bad"])
    with pytest.raises(CliArgumentError):
        validate_models_allowed(config, {"ocr": frozenset({"good"})})


def test_engine_unknown_value_raises() -> None:
    # A value that names no model fails the same allowed-set check.
    config = parse_config(["x.pdf", "--engine", "not-a-real-model"])
    with pytest.raises(CliArgumentError):
        validate_models_allowed(config, {"ocr": frozenset({"gemini_api"})})


def test_latex_fix_without_inspection_raises() -> None:
    # The flag only widens the inspection guard.
    config = parse_config(["x.pdf", "--llm-latex-fix"])
    with pytest.raises(CliArgumentError):
        validate_latex_fix(config)


def test_latex_fix_with_inspection_is_valid() -> None:
    config = parse_config(["x.pdf", "--llm-inspection", "g", "--llm-latex-fix"])
    validate_latex_fix(config)


def test_latex_fix_without_inspection_exits_2_via_main() -> None:
    # Refused before settings.json is read.
    with pytest.raises(SystemExit) as exc_info:
        main(["x.pdf", "--llm-latex-fix"])
    assert exc_info.value.code == 2


def test_disabled_operations_skip_allowed_check() -> None:
    config = parse_config(["x.pdf"])
    validate_models_allowed(config, {})


# --- Subcommand / path dispatcher ------------------------------------------


@pytest.mark.parametrize("word", sorted(RESERVED_SUBCOMMANDS))
def test_reserved_words_dispatch_as_subcommands(word: str) -> None:
    invocation = classify_invocation([word])
    assert invocation.subcommand == word
    assert invocation.args == []


def test_subcommand_keeps_trailing_args() -> None:
    invocation = classify_invocation(["resume", "show"])
    assert invocation.subcommand == "resume"
    assert invocation.args == ["show"]


def test_reserved_word_as_path_is_input() -> None:
    invocation = classify_invocation(["./resume"])
    assert invocation.subcommand is None
    assert invocation.args == ["./resume"]


def test_file_path_is_input() -> None:
    invocation = classify_invocation(["input.pdf", "--skip-existing"])
    assert invocation.subcommand is None
    assert invocation.args == ["input.pdf", "--skip-existing"]


def test_empty_argv_is_input() -> None:
    invocation = classify_invocation([])
    assert invocation.subcommand is None
    assert invocation.args == []


# --- Dispatch into the orchestrator and doctor -----------------------------


def test_input_run_dispatches_to_orchestrator(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Path] = {}

    def fake_run(config: object, **_: object) -> int:
        captured["input"] = config.input_path  # type: ignore[attr-defined]
        return 7

    monkeypatch.setattr("raw2md.orchestrator.run", fake_run)
    assert main(["input.pdf"]) == 7
    assert captured["input"] == Path("input.pdf")


def test_run_without_input_dispatches_current_folder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Path] = {}

    def fake_run(config: object, **_: object) -> int:
        captured["input"] = config.input_path  # type: ignore[attr-defined]
        return 0

    monkeypatch.setattr("raw2md.orchestrator.run", fake_run)
    assert main([]) == 0
    assert captured["input"] == Path()


def test_keyboard_interrupt_exits_130(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raise_interrupt(config: object, **_: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr("raw2md.orchestrator.run", raise_interrupt)
    assert main(["input.pdf"]) == 130
    assert "interrupted" in capsys.readouterr().err


def test_doctor_dispatches_to_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_doctor(args: object) -> int:
        captured["args"] = args
        return 9

    monkeypatch.setattr("raw2md.doctor.run_doctor", fake_doctor)
    assert main(["doctor"]) == 9
    assert captured["args"] == []


def test_init_dispatches_to_init_command(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_init(args: object) -> int:
        captured["args"] = args
        return 9

    monkeypatch.setattr(cli, "run_init_command", fake_init)
    assert main(["init", "gemini_api"]) == 9
    assert captured["args"] == ["gemini_api"]


def test_keywords_dispatches_to_keywords_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_keywords(args: object) -> int:
        captured["args"] = args
        return 9

    monkeypatch.setattr(cli, "run_keywords_command", fake_keywords)
    assert main(["keywords", "check"]) == 9
    assert captured["args"] == ["check"]


# --- Settings wiring in main -----------------------------------------------


def test_model_outside_allowed_exits_2_via_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda path: default_settings())
    with pytest.raises(SystemExit) as exc_info:
        main(["x.pdf", "--llm-post", "unlisted"])
    assert exc_info.value.code == 2


def test_engine_outside_ocr_allowed_exits_2_via_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda path: default_settings())
    with pytest.raises(SystemExit) as exc_info:
        main(["x.pdf", "--engine", "unlisted"])
    assert exc_info.value.code == 2


def test_engine_model_key_dispatches_via_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda path: default_settings())
    captured: dict[str, object] = {}

    def fake_run(config: RunConfig, **_: object) -> int:
        captured["config"] = config
        return 0

    monkeypatch.setattr("raw2md.orchestrator.run", fake_run)
    # A model allowed for ocr routes pdf and djvu to LLM-OCR.
    assert main(["x.pdf", "--engine", "gemini_api"]) == 0
    config = captured["config"]
    assert isinstance(config, RunConfig)
    assert config.llm_ocr == "gemini_api"


def test_allowed_model_passes_validation_via_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda path: default_settings())
    monkeypatch.setattr("raw2md.orchestrator.run", lambda config, **_: 0)
    assert main(["x.pdf", "--llm-post", "claude_cli"]) == 0


def test_inspection_alone_passes_validation_via_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda path: default_settings())
    captured: dict[str, object] = {}

    def fake_run(config: RunConfig, **_: object) -> int:
        captured["config"] = config
        return 0

    monkeypatch.setattr("raw2md.orchestrator.run", fake_run)
    assert main(["x.pdf", "--llm-inspection", "gemini_api"]) == 0
    config = captured["config"]
    assert isinstance(config, RunConfig)
    assert config.llm_inspection == "gemini_api"
    assert config.llm_post is None


# --- Resume subcommand -----------------------------------------------------


def _save_empty_queue() -> None:
    save_queue(Queue(params=parse_config(["x.pdf"]), items=()))


def test_resume_path_prints_queue_path(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_resume_command(["path"]) == int(ExitCode.SUCCESS)
    assert capsys.readouterr().out.strip() == str(queue_path())


def test_resume_show_without_queue_is_success(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_resume_command(["show"]) == int(ExitCode.SUCCESS)
    assert "nothing to resume" in capsys.readouterr().err


def test_resume_show_prints_saved_queue(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _save_empty_queue()
    assert run_resume_command(["show"]) == int(ExitCode.SUCCESS)
    assert '"version"' in capsys.readouterr().out


def test_bare_resume_without_queue_exits_2(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_resume_command([]) == int(ExitCode.ARGUMENT_ERROR)
    assert "no saved queue" in capsys.readouterr().err


def test_bare_resume_dispatches_to_orchestrator(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save_empty_queue()
    monkeypatch.setattr("raw2md.orchestrator.run_resume", lambda **_: 5)
    assert run_resume_command([]) == 5


def test_resume_rejects_run_flags(home: Path) -> None:
    # Resume cannot override the saved parameters.
    with pytest.raises(SystemExit) as exc_info:
        run_resume_command(["--skip-existing"])
    assert exc_info.value.code == 2
