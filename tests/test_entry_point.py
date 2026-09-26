"""Tests for the package entry point: --version and --help early-exit flags."""

import re
import sys
from unittest.mock import patch

import pytest

from raw2md.cli import main


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(sys, "argv", ["raw2md", "--version"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert re.search(r"raw2md\s+\d+\.\d+\.\d+", out)


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.object(sys, "argv", ["raw2md", "--help"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "raw2md" in out
