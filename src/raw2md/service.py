"""Actions shared by the ~/.raw2md service-file subcommands.

`settings`, `prompts`, and `keywords` answer the same actions over one file.
`path`, `show`, and `edit` do not depend on the file content, so they live
here; `check` stays with each file, next to its schema.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from raw2md.exit_codes import ExitCode

# Management subcommands sit outside the run contract: 0 on success, this
# generic code on an I/O failure that prevents the requested action.
MANAGEMENT_FAILURE = 1

FILE_ACTIONS = ("path", "show", "edit", "check")


def parse_file_action(prog: str, args: list[str]) -> str:
    """Parse the action argument of a service-file subcommand."""
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("action", choices=FILE_ACTIONS)
    return str(parser.parse_args(args).action)


def show_file(path: Path) -> int:
    """Print the file, or say it is missing.

    A missing file is not a failure: the built-in defaults apply until
    `raw2md init` writes one, so the exit code stays 0.
    """
    if not path.exists():
        print(
            f"raw2md: {path} does not exist; run `raw2md init`",
            file=sys.stderr,
        )
        return int(ExitCode.SUCCESS)
    try:
        print(path.read_text(encoding="utf-8"), end="")
    except OSError as error:
        print(f"raw2md: cannot read {path}: {error}", file=sys.stderr)
        return MANAGEMENT_FAILURE
    return int(ExitCode.SUCCESS)


def edit_file(path: Path) -> int:
    """Open the file in the platform editor and return its exit code."""
    editor = _editor_command()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run([editor, str(path)], check=False)
    except OSError as error:
        print(f"raw2md: cannot launch editor '{editor}': {error}", file=sys.stderr)
        return MANAGEMENT_FAILURE
    return completed.returncode


def _editor_command() -> str:
    return "notepad" if sys.platform == "win32" else "nano"
