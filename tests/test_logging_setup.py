"""Tests for logging setup: handlers, log file creation, rewrite, and records."""

from __future__ import annotations

import io
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from raw2md import logging_setup
from raw2md.logging_setup import _wrap_console_message, screen_info, setup_logging


class _FakeStream(io.StringIO):
    """A stream double with a controllable `isatty()`.

    The handler asks its own stream whether to color, not `sys.stderr`.
    """

    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class _FakeStreamWithFileno(_FakeStream):
    """A `_FakeStream` whose `fileno()` resolves to a chosen sentinel fd."""

    def __init__(self, fd: int) -> None:
        super().__init__(tty=True)
        self._fd = fd

    def fileno(self) -> int:
        return self._fd


@pytest.fixture(autouse=True)
def _clean_raw2md_logger() -> Iterator[None]:
    """Remove all handlers from the raw2md logger before and after each test."""
    logger = logging.getLogger("raw2md")
    yield
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# No log file
# ---------------------------------------------------------------------------


def test_no_log_file_returns_none() -> None:
    result = setup_logging(log_file=False)
    assert result is None


def test_no_log_file_has_one_handler() -> None:
    setup_logging(log_file=False)
    logger = logging.getLogger("raw2md")
    assert len(logger.handlers) == 1


def test_no_log_file_handler_is_stderr() -> None:
    setup_logging(log_file=False)
    logger = logging.getLogger("raw2md")
    handler = logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr


def test_console_handler_routes_through_tqdm_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # tqdm.write keeps a record from clipping a line a live bar redraws.
    import tqdm

    calls: list[tuple[str, object]] = []
    original_write = tqdm.tqdm.write

    def spy_write(s: str, file: object = None, **kwargs: object) -> None:
        calls.append((s, file))
        original_write(s, file=file, **kwargs)

    monkeypatch.setattr(tqdm.tqdm, "write", staticmethod(spy_write))
    setup_logging(log_file=False)
    logger = logging.getLogger("raw2md")
    logger.warning("disk almost full")
    assert any("WARNING: disk almost full" in s for s, _ in calls)


def test_no_log_file_console_level_is_info() -> None:
    # The handler sits at INFO for screen_info; the filter keeps plain INFO off.
    setup_logging(log_file=False)
    logger = logging.getLogger("raw2md")
    assert logger.handlers[0].level == logging.INFO


# ---------------------------------------------------------------------------
# Screen-flagged INFO (`screen_info`, `_ConsoleFilter`)
# ---------------------------------------------------------------------------


def test_plain_info_does_not_reach_console(monkeypatch: pytest.MonkeyPatch) -> None:
    import tqdm

    calls: list[str] = []
    monkeypatch.setattr(
        tqdm.tqdm, "write", staticmethod(lambda s, file=None, **kw: calls.append(s))
    )
    setup_logging(log_file=False)
    logger = logging.getLogger("raw2md")
    logger.info("converting doc.pdf via marker")
    assert calls == []


def test_screen_info_reaches_console(monkeypatch: pytest.MonkeyPatch) -> None:
    import tqdm

    calls: list[str] = []
    monkeypatch.setattr(
        tqdm.tqdm, "write", staticmethod(lambda s, file=None, **kw: calls.append(s))
    )
    setup_logging(log_file=False)
    logger = logging.getLogger("raw2md")
    screen_info(logger, "raw2md: starting run of %d file(s)", 3)
    assert any("starting run of 3 file(s)" in s for s in calls)


def test_screen_info_still_reaches_log_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    logger = logging.getLogger("raw2md")
    setup_logging(log_file=True)
    screen_info(logger, "raw2md: finished %d file(s)", 3)
    for handler in logger.handlers:
        handler.flush()
    log_path = tmp_path / ".raw2md" / "logs" / "raw2md.log"
    assert "finished 3 file(s)" in log_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# With log file
# ---------------------------------------------------------------------------


def test_log_file_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert setup_logging(log_file=True) is None


def test_log_file_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    setup_logging(log_file=True)
    log_path = tmp_path / ".raw2md" / "logs" / "raw2md.log"
    assert log_path.exists()


def test_log_file_has_two_handlers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    setup_logging(log_file=True)
    logger = logging.getLogger("raw2md")
    assert len(logger.handlers) == 2


def test_log_file_handler_level_is_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    setup_logging(log_file=True)
    logger = logging.getLogger("raw2md")
    file_handlers = [
        h
        for h in logger.handlers
        if isinstance(h, logging.StreamHandler) and h.stream is not sys.stderr
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].level == logging.DEBUG


def test_log_file_records_structured_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    logger = logging.getLogger("raw2md")
    setup_logging(log_file=True)
    logger.info("converting doc.pdf via marker")
    for handler in logger.handlers:
        handler.flush()
    log_path = tmp_path / ".raw2md" / "logs" / "raw2md.log"
    assert "converting doc.pdf via marker" in log_path.read_text(encoding="utf-8")


def test_log_file_rewritten_each_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    logger = logging.getLogger("raw2md")
    setup_logging(log_file=True)
    logger.info("first run record")
    for handler in logger.handlers:
        handler.flush()
    setup_logging(log_file=True)
    logger.info("second run record")
    for handler in logger.handlers:
        handler.flush()
    log_path = tmp_path / ".raw2md" / "logs" / "raw2md.log"
    text = log_path.read_text(encoding="utf-8")
    assert "second run record" in text
    assert "first run record" not in text


def test_setup_logging_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    setup_logging(log_file=True)
    setup_logging(log_file=True)
    logger = logging.getLogger("raw2md")
    assert len(logger.handlers) == 2


# ---------------------------------------------------------------------------
# Traceback isolation (`_ConsoleFormatter`, per-file broad catch)
# ---------------------------------------------------------------------------


def _log_with_exc_info(logger: logging.Logger) -> None:
    try:
        raise OSError("disk error")  # noqa: TRY301 -- raised to produce a real exc_info for the isolation test below
    except OSError:
        logger.exception("failed a.pdf: unexpected error: disk error")


def test_console_omits_traceback_even_with_exc_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    fake_stderr = _FakeStream(tty=False)
    monkeypatch.setattr(sys, "stderr", fake_stderr)
    logger = logging.getLogger("raw2md")
    setup_logging(log_file=True)
    _log_with_exc_info(logger)
    for handler in logger.handlers:
        handler.flush()
    console_text = fake_stderr.getvalue()
    assert "unexpected error: disk error" in console_text
    assert "Traceback" not in console_text
    assert "OSError" not in console_text


def test_log_file_keeps_traceback_with_exc_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    logger = logging.getLogger("raw2md")
    setup_logging(log_file=True)
    _log_with_exc_info(logger)
    for handler in logger.handlers:
        handler.flush()
    log_path = tmp_path / ".raw2md" / "logs" / "raw2md.log"
    text = log_path.read_text(encoding="utf-8")
    assert "Traceback" in text
    assert "OSError: disk error" in text


def test_console_formatter_restores_exc_info_for_later_handlers() -> None:
    # The file handler must still see exc_info after the console formatter.
    formatter = logging_setup._ConsoleFormatter("%(message)s")
    try:
        raise ValueError("boom")  # noqa: TRY301 -- raised to produce a real sys.exc_info() for the record below
    except ValueError:
        record = logging.LogRecord(
            "raw2md", logging.ERROR, __file__, 1, "boom", None, None
        )
        record.exc_info = sys.exc_info()
        formatter.format(record)
        assert record.exc_info is not None
        assert record.exc_info[0] is ValueError


# ---------------------------------------------------------------------------
# Terminal width (`_console_width`)
# ---------------------------------------------------------------------------


def test_console_width_prefers_columns_env_over_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COLUMNS", "42")
    assert logging_setup._console_width(_FakeStream(tty=False)) == 42


def test_console_width_measures_the_handlers_own_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # shutil.get_terminal_size() measures sys.__stdout__, not the stderr
    # handler. os.get_terminal_size is process-global and pytest calls it too,
    # so the fake passes other fds through.
    monkeypatch.delenv("COLUMNS", raising=False)
    real_get_terminal_size = os.get_terminal_size

    def fake_terminal_size(fd: int = -1) -> os.terminal_size:
        if fd == 7:
            return os.terminal_size((15, 24))
        try:
            return real_get_terminal_size(fd)
        except OSError:
            return os.terminal_size((80, 24))

    monkeypatch.setattr(os, "get_terminal_size", fake_terminal_size)
    assert logging_setup._console_width(_FakeStreamWithFileno(fd=7)) == 15


def test_console_width_falls_back_when_stream_has_no_fileno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COLUMNS", raising=False)
    assert logging_setup._console_width(_FakeStream(tty=False)) == 80


# ---------------------------------------------------------------------------
# Console wrapping (`_wrap_console_message`)
# ---------------------------------------------------------------------------


def test_wrap_console_message_short_line_is_unchanged() -> None:
    assert _wrap_console_message("WARNING: short", width=80) == ["WARNING: short"]


def test_wrap_console_message_splits_long_line_on_word_boundary() -> None:
    message = "WARNING: " + " ".join(f"word{i}" for i in range(20))
    lines = _wrap_console_message(message, width=20)
    assert len(lines) > 1
    assert all(len(line) <= 20 for line in lines)
    assert all("\n" not in line for line in lines)


def test_wrap_console_message_indents_continuation_lines() -> None:
    message = "WARNING: " + " ".join(f"word{i}" for i in range(20))
    lines = _wrap_console_message(message, width=20)
    assert all(line.startswith("  ") for line in lines[1:])


def test_wrap_console_message_keeps_embedded_newlines_as_separate_lines() -> None:
    # Each traceback line is wrapped on its own.
    assert _wrap_console_message("first\nsecond", width=80) == ["first", "second"]


def test_long_console_record_emits_one_tqdm_write_per_wrapped_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tqdm

    # NO_COLOR fixes the line length; COLUMNS pins the width before any fd
    # lookup.
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "20")
    calls: list[str] = []
    original_write = tqdm.tqdm.write

    def spy_write(s: str, file: object = None, **kwargs: object) -> None:
        calls.append(s)
        original_write(s, file=file, **kwargs)

    monkeypatch.setattr(tqdm.tqdm, "write", staticmethod(spy_write))
    handler = logging_setup._TqdmStreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord(
        "raw2md",
        logging.WARNING,
        __file__,
        1,
        "quality checks failed: low_text_confidence unreadable_chars "
        "recognition_failure, consider rerunning with llm-ocr",
        None,
        None,
    )
    handler.emit(record)
    assert len(calls) > 1
    assert all(len(call) <= 20 for call in calls)
    assert all("\n" not in call for call in calls)


# ---------------------------------------------------------------------------
# Console color by level
# ---------------------------------------------------------------------------


def test_console_color_applied_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    stream = _FakeStream(tty=True)
    handler = logging_setup._TqdmStreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord(
        "raw2md", logging.WARNING, __file__, 1, "disk almost full", None, None
    )
    handler.emit(record)
    output = stream.getvalue()
    assert "\x1b[33m" in output  # yellow
    assert "\x1b[0m" in output


def test_console_color_matches_error_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    stream = _FakeStream(tty=True)
    handler = logging_setup._TqdmStreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord("raw2md", logging.ERROR, __file__, 1, "boom", None, None)
    handler.emit(record)
    assert "\x1b[31m" in stream.getvalue()  # red


def test_console_color_absent_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    stream = _FakeStream(tty=False)
    handler = logging_setup._TqdmStreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord(
        "raw2md", logging.WARNING, __file__, 1, "disk almost full", None, None
    )
    handler.emit(record)
    assert "\x1b[" not in stream.getvalue()


def test_console_color_absent_when_no_color_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    stream = _FakeStream(tty=True)
    handler = logging_setup._TqdmStreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    record = logging.LogRecord("raw2md", logging.ERROR, __file__, 1, "boom", None, None)
    handler.emit(record)
    assert "\x1b[" not in stream.getvalue()


def test_log_file_never_contains_ansi_even_when_console_is_tty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("NO_COLOR", raising=False)
    fake_stderr = _FakeStream(tty=True)
    monkeypatch.setattr(sys, "stderr", fake_stderr)
    logger = logging.getLogger("raw2md")
    setup_logging(log_file=True)
    logger.error("disk full")
    for handler in logger.handlers:
        handler.flush()
    log_path = tmp_path / ".raw2md" / "logs" / "raw2md.log"
    assert "\x1b[" not in log_path.read_text(encoding="utf-8")
    assert "\x1b[31m" in fake_stderr.getvalue()
