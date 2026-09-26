"""Logging configuration for raw2md.

The console shows WARNING and above plus the INFO records flagged by
`screen_info` (the run start and the summary); other INFO stays in the file.
The file handler logs DEBUG to ~/.raw2md/logs/raw2md.log, rewritten each run.
Raw engine output never reaches the log: it would bury the records.

The console wraps each record to the terminal width, colors it on a tty
(honoring NO_COLOR), and drops tracebacks, which go to the file only. All
records go through the "raw2md" logger, not the root logger.
"""

from __future__ import annotations

import logging
import os
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import tqdm as _tqdm_mod

from raw2md.paths import logs_dir

_LOG_FILENAME = "raw2md.log"
_CONSOLE_FORMAT = "%(levelname)s: %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# LogRecord attribute that marks an INFO record for the console.
_SCREEN_ATTR = "screen"

# When neither COLUMNS nor the stream answers (output redirected).
_FALLBACK_TERMINAL_WIDTH = 80
_WRAP_INDENT = "  "

# Checked high to low: a level takes the first threshold it clears.
_LEVEL_COLORS: tuple[tuple[int, str], ...] = (
    (logging.ERROR, "\x1b[31m"),  # red
    (logging.WARNING, "\x1b[33m"),  # yellow
    (logging.INFO, "\x1b[36m"),  # cyan
)
_COLOR_RESET = "\x1b[0m"


class _ConsoleFormatter(logging.Formatter):
    """Formats without the exception traceback, even when `exc_info` is set.

    Handlers share one `LogRecord`, so `exc_info` and `exc_text` are restored
    for the file handler that runs next.
    """

    def format(self, record: logging.LogRecord) -> str:
        exc_info, record.exc_info = record.exc_info, None
        exc_text, record.exc_text = record.exc_text, None
        try:
            return super().format(record)
        finally:
            record.exc_info = exc_info
            record.exc_text = exc_text


def _level_color(levelno: int) -> str | None:
    for threshold, color in _LEVEL_COLORS:
        if levelno >= threshold:
            return color
    return None


def screen_info(logger: logging.Logger, msg: str, *args: object) -> None:
    """Log an INFO record that also reaches the console."""
    logger.info(msg, *args, extra={_SCREEN_ATTR: True})


class _ConsoleFilter(logging.Filter):
    """Admits WARNING and above, plus INFO flagged via `screen_info`."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or getattr(record, _SCREEN_ATTR, False)


def _console_width(stream: TextIO) -> int:
    """Terminal width for `stream`, the one the console handler writes to.

    `shutil.get_terminal_size()` always asks stdout, while this handler writes
    to stderr, which may be the only terminal.
    """
    try:
        columns = int(os.environ["COLUMNS"])
        if columns > 0:
            return columns
    except (KeyError, ValueError):
        pass
    try:
        columns = os.get_terminal_size(stream.fileno()).columns
    except (AttributeError, ValueError, OSError):
        return _FALLBACK_TERMINAL_WIDTH
    return columns or _FALLBACK_TERMINAL_WIDTH


def _wrap_console_message(message: str, width: int) -> list[str]:
    """Word-wrap `message` so every returned line fits in `width` columns.

    Each entry is one physical line: tqdm redraws its bars assuming one
    `tqdm.write` call takes one terminal row.
    """
    lines: list[str] = []
    for paragraph in message.split("\n"):
        wrapped = textwrap.wrap(
            paragraph,
            width=width,
            subsequent_indent=_WRAP_INDENT,
            break_long_words=True,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [""])
    return lines


# The generic base is for mypy only; the runtime base stays unparameterized.
if TYPE_CHECKING:
    _StreamHandlerBase = logging.StreamHandler[TextIO]
else:
    _StreamHandlerBase = logging.StreamHandler


class _TqdmStreamHandler(_StreamHandlerBase):
    """Console handler that writes through `tqdm.write` instead of the raw stream.

    A direct write races the bar redraw and clips the message (`WARNING`
    becomes `ARNING`). `tqdm.write` keeps the bars intact only when each call
    is one terminal row, so records are wrapped to the width first.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            color = self._color_for(record.levelno)
            for line in _wrap_console_message(msg, _console_width(self.stream)):
                text = f"{color}{line}{_COLOR_RESET}" if color is not None else line
                _tqdm_mod.tqdm.write(text, file=self.stream)
        except RecursionError:
            raise
        except Exception:  # noqa: BLE001 -- Handler.emit must not raise
            self.handleError(record)

    def _color_for(self, levelno: int) -> str | None:
        """The ANSI color for `levelno`; None off a tty or under NO_COLOR."""
        isatty = getattr(self.stream, "isatty", None)
        if isatty is None or not isatty() or "NO_COLOR" in os.environ:
            return None
        return _level_color(levelno)


def setup_logging(log_file: bool) -> TextIO | None:
    """Configure the raw2md logger; `log_file` adds the file handler.

    Always returns None: engine output is not written to the log. The return
    type keeps room for an engine output sink.
    """
    logger = logging.getLogger("raw2md")
    logger.setLevel(logging.DEBUG)
    # A repeated call (resume, tests) replaces the handlers.
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.propagate = False

    console = _TqdmStreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.addFilter(_ConsoleFilter())
    console.setFormatter(_ConsoleFormatter(_CONSOLE_FORMAT))
    logger.addHandler(console)

    if not log_file:
        return None

    log_dir: Path = logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / _LOG_FILENAME

    # FileHandler closes its file on close(), so reconfiguring leaks nothing.
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    logger.addHandler(file_handler)

    return None
