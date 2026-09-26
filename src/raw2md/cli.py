"""Command-line front-end: argument parsing, dispatch, and validation."""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from raw2md.config import (
    CliArgumentError,
    build_config,
    requests_llm,
    validate_latex_fix,
    validate_models_allowed,
)
from raw2md.exit_codes import ExitCode
from raw2md.header import get_version
from raw2md.init import run_init_command
from raw2md.keywords import run_keywords_command
from raw2md.paths import settings_file
from raw2md.prompts import run_prompts_command
from raw2md.queue import queue_path
from raw2md.service import MANAGEMENT_FAILURE
from raw2md.settings import SettingsError, load_settings, run_settings_command

# Reserved management subcommands; anything else is treated as an INPUT path,
# so a folder named like one is passed as `./resume`.
RESERVED_SUBCOMMANDS = frozenset(
    {"resume", "settings", "prompts", "keywords", "doctor", "init"}
)

# Shell convention for SIGINT (128 + 2); outside the run contract.
_INTERRUPTED = 130


@dataclass(frozen=True)
class Invocation:
    """Top-level dispatch decision: a subcommand, or INPUT processing.

    `subcommand` is None for INPUT processing; `args` is then the whole argv to
    feed the processing parser. For a subcommand, `args` is the remainder.
    """

    subcommand: str | None
    args: list[str]


def classify_invocation(argv: list[str]) -> Invocation:
    """Split argv into a management subcommand or an INPUT run."""
    if argv and argv[0] in RESERVED_SUBCOMMANDS:
        return Invocation(subcommand=argv[0], args=argv[1:])
    return Invocation(subcommand=None, args=argv)


def build_input_parser() -> argparse.ArgumentParser:
    """Build the parser for a processing run (INPUT plus options)."""
    parser = argparse.ArgumentParser(
        prog="raw2md",
        description="Convert raw documents (PDF, DOCX, DjVu) to cleaned Markdown.",
        # 36 keeps the longest option header and its help on one line.
        formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=36),
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"raw2md {get_version()}",
    )
    parser.add_argument(
        "input_path",
        metavar="INPUT",
        nargs="?",
        type=Path,
        default=Path(),
        help="file or folder to convert (default: the current folder)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        metavar="DIR",
        type=Path,
        default=None,
        help="output folder instead of the source folder",
    )
    parser.add_argument(
        "-s",
        "--skip-existing",
        action="store_true",
        help="keep a finished result already sitting at the result name",
    )
    parser.add_argument(
        "--no-yaml",
        action="store_false",
        dest="yaml_header",
        help="drop the YAML header from the result",
    )
    parser.add_argument(
        "--disable-image-extraction",
        action="store_false",
        dest="extract_images",
        help="do not extract media; keep textual captions, drop image links",
    )
    parser.add_argument(
        "-e",
        "--engine",
        metavar="ENGINE",
        default="marker",
        help="pdf/djvu conversion engine: marker (default), or an LLM model key "
        "from settings.json to recognize pages instead",
    )
    parser.add_argument(
        "-p",
        "--llm-post",
        metavar="MODEL",
        default="none",
        help="post-processing via an LLM model key from settings.json, or none",
    )
    parser.add_argument(
        "-i",
        "--llm-inspection",
        metavar="MODEL",
        default="none",
        help="inspection via an LLM model key from settings.json, or none",
    )
    parser.add_argument(
        "--llm-latex-fix",
        action="store_true",
        help="let inspection rewrite formulas (dangerous: an edit is unverifiable)",
    )
    parser.add_argument(
        "--cuda",
        choices=("on", "off"),
        default="on",
        help="CUDA mode in marker (default on)",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_false",
        dest="log_file",
        help="disable the detailed run log written by default",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="save intermediate per-stage output next to the result",
    )
    return parser


def _parse_resume_action(args: list[str]) -> str | None:
    """Parse `raw2md resume [show|path]`; bare `resume` resumes the batch.

    Run flags are rejected: resume replays the saved parameters.
    """
    parser = argparse.ArgumentParser(prog="raw2md resume")
    parser.add_argument("action", nargs="?", choices=("show", "path"), default=None)
    action = parser.parse_args(args).action
    return None if action is None else str(action)


def _run_resume_show(path: Path) -> int:
    if not path.exists():
        print(f"raw2md: {path} does not exist; nothing to resume", file=sys.stderr)
        return int(ExitCode.SUCCESS)
    try:
        print(path.read_text(encoding="utf-8"), end="")
    except OSError as error:
        print(f"raw2md: cannot read {path}: {error}", file=sys.stderr)
        return MANAGEMENT_FAILURE
    return int(ExitCode.SUCCESS)


def run_resume_command(args: list[str]) -> int:
    """Handle `raw2md resume [show|path]`."""
    action = _parse_resume_action(args)
    path = queue_path()
    if action == "path":
        print(path)
        return int(ExitCode.SUCCESS)
    if action == "show":
        return _run_resume_show(path)
    from raw2md.orchestrator import run_resume

    return run_resume()


def _dispatch_subcommand(name: str, args: list[str]) -> int:
    if name == "init":
        return run_init_command(args)
    if name == "settings":
        return run_settings_command(args)
    if name == "prompts":
        return run_prompts_command(args)
    if name == "keywords":
        return run_keywords_command(args)
    if name == "resume":
        return run_resume_command(args)
    if name == "doctor":
        from raw2md.doctor import run_doctor

        return run_doctor(args)
    raise AssertionError(f"unhandled subcommand: {name}")


def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch argv; Ctrl+C gives exit 130 instead of a traceback.

    The orchestrator releases the lock itself, and an interrupted batch stays
    in the queue for `resume`.
    """
    try:
        return _main(list(sys.argv[1:] if argv is None else argv))
    except KeyboardInterrupt:
        print("raw2md: interrupted", file=sys.stderr)
        return _INTERRUPTED


def _main(args: list[str]) -> int:
    invocation = classify_invocation(args)
    if invocation.subcommand is not None:
        return _dispatch_subcommand(invocation.subcommand, invocation.args)

    parser = build_input_parser()
    namespace = parser.parse_args(invocation.args)
    config = build_config(namespace)
    try:
        validate_latex_fix(config)
        # A broken settings.json never blocks a run without LLM operations.
        if requests_llm(config):
            settings = load_settings(settings_file())
            validate_models_allowed(config, settings.operations)
    except CliArgumentError as error:
        parser.error(str(error))  # prints usage and exits with code 2
    except SettingsError as error:
        print(f"raw2md: settings.json: {error}", file=sys.stderr)
        return int(ExitCode.ARGUMENT_ERROR)

    from raw2md.orchestrator import run

    return run(config)
