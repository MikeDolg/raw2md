"""Progress reporting: batch bar and per-file stage bar.

Each bar is two stacked lines, a label and the bar beneath it, so both bars
share a left edge and a width whatever the filename length. Engine output is
redirected during a conversion call so marker and surya do not corrupt the
bars.
"""

from __future__ import annotations

import io
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Self, TextIO, cast

import tqdm as _tqdm_mod

# The pipeline stages in execution order; a route runs a subset. Re-evaluation
# after inspection or post stays under the stage that just ran.
STAGE_NAMES: tuple[str, ...] = (
    "conversion",
    "cleaning",
    "quality evaluation",
    "inspection",
    "post-processing",
)

# tqdm descriptions of marker and surya phases, matched as substrings of a
# redrawn line, and their bracket labels.
_MARKER_PHASES: tuple[tuple[str, str], ...] = (
    ("Detecting bboxes", "detection"),
    ("Recognizing Layout", "layout"),
    ("Running OCR Error Detection", "OCR check"),
    ("Recognizing Text", "OCR"),
    ("Recognizing tables", "tables"),
)

# Marks a tqdm progress line of an unnamed phase.
_TQDM_MARK = "%|"

# Bracket label for a recognized-but-unnamed engine progress line.
_GENERIC_PHASE = "marker"

# Fixed positions keep the four lines in a stable block.
_BATCH_LABEL_POS = 0
_BATCH_BAR_POS = 1
_FILE_LABEL_POS = 2
_FILE_BAR_POS = 3

_LABEL_BAR_FORMAT = "{desc}:"


def _marker_phase_label(line: str) -> str | None:
    """Map one line of redirected engine output to a bracket label, or None.

    Another tqdm line yields the generic ``marker``; a non-progress line None.
    """
    for needle, label in _MARKER_PHASES:
        if needle in line:
            return label
    if _TQDM_MARK in line:
        return _GENERIC_PHASE
    return None


def _bracket_bar_format(text: str) -> str:
    """A bar_format with `text` baked into a trailing bracket.

    tqdm's postfix always prepends ", ". The percentage reserves three columns,
    so the bar does not shift at 10% and 100%.
    """
    return "{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [" + text + "]"


class BatchProgress:
    """Batch-level progress bar (file count + throughput), owned by the orchestrator."""

    def __init__(self, total: int, *, file: TextIO | None = None) -> None:
        stream = file if file is not None else sys.stderr
        # leave=True would commit a finished bar at position 0, over its label.
        self._label: _tqdm_mod.tqdm[None] = _tqdm_mod.tqdm(
            total=1,
            desc="batch",
            file=stream,
            dynamic_ncols=True,
            bar_format=_LABEL_BAR_FORMAT,
            position=_BATCH_LABEL_POS,
            leave=False,
        )
        self._bar: _tqdm_mod.tqdm[None] = _tqdm_mod.tqdm(
            total=total,
            unit="file",
            file=stream,
            dynamic_ncols=True,
            bar_format=_bracket_bar_format("? files/min"),
            position=_BATCH_BAR_POS,
            leave=False,
        )

    def advance(self) -> None:
        self._bar.update(1)
        rate = self._bar.format_dict.get("rate")  # smoothed items/second, or None
        # Two decimals: a scanned book takes tens of minutes per file.
        label = f"{rate * 60:.2f} files/min" if rate else "? files/min"
        self._bar.bar_format = _bracket_bar_format(label)
        self._bar.refresh()

    def close(self) -> None:
        self._bar.close()
        self._label.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class FileProgress:
    """Per-file stage bar (names the current stage), owned by the pipeline.

    `stages` is the route this file runs, known before conversion, so the bar
    ends at exactly 100%.
    """

    def __init__(
        self, filename: str, stages: Sequence[str], *, file: TextIO | None = None
    ) -> None:
        self._seen: set[str] = set()
        stream = file if file is not None else sys.stderr
        # leave=False: the next file reuses the same two lines.
        self._label: _tqdm_mod.tqdm[None] = _tqdm_mod.tqdm(
            total=1,
            desc=filename,
            file=stream,
            dynamic_ncols=True,
            bar_format=_LABEL_BAR_FORMAT,
            position=_FILE_LABEL_POS,
            leave=False,
        )
        self._bar: _tqdm_mod.tqdm[None] = _tqdm_mod.tqdm(
            total=len(stages),
            file=stream,
            dynamic_ncols=True,
            bar_format=_bracket_bar_format(""),
            position=_FILE_BAR_POS,
            leave=False,
        )

    def update_stage(self, stage: str) -> None:
        """Label the bar with `stage`, advancing the count the first time it is seen.

        A stage may report more than once. The count never passes the total, so
        a stage outside the planned route stalls rather than overshoots.
        """
        self._bar.bar_format = _bracket_bar_format(stage)
        if stage in self._seen:
            self._bar.refresh()
            return
        self._seen.add(stage)
        if self._bar.n < self._bar.total:
            self._bar.update(1)
        # update() honors the redraw throttle, so a fast stage could pass unseen.
        self._bar.refresh()

    def set_phase(self, phase: str) -> None:
        """Relabel the bracket with a sub-stage phase, without advancing the count."""
        self._bar.bar_format = _bracket_bar_format(phase)
        self._bar.refresh()

    def close(self) -> None:
        self._bar.close()
        self._label.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class _NullWriter(io.TextIOBase):
    """Write-only sink that discards output; a StringIO would hold it all."""

    def write(self, s: str) -> int:
        return len(s)

    def writable(self) -> bool:
        return True


class _PhaseSniffer(io.TextIOBase):
    """A write sink that passes output through and lifts marker phases out of it.

    A label is reported only when it changes: tqdm redraws each phase many
    times. The bar writes to the stderr captured at its construction, so the
    callback does not re-enter `write`.
    """

    def __init__(self, underlying: TextIO, on_phase: Callable[[str], None]) -> None:
        self._underlying = underlying
        self._on_phase = on_phase
        self._last: str | None = None

    def write(self, s: str) -> int:
        written = self._underlying.write(s)
        # tqdm redraws with CR; one write may carry several redraws.
        for chunk in s.replace("\r", "\n").split("\n"):
            label = _marker_phase_label(chunk)
            if label is not None and label != self._last:
                self._last = label
                self._on_phase(label)
        return written

    def writable(self) -> bool:
        return True

    def flush(self) -> None:
        self._underlying.flush()


@contextmanager
def capture_engine_output(
    sink: TextIO | None = None,
    *,
    on_phase: Callable[[str], None] | None = None,
) -> Iterator[None]:
    """Redirect stdout and stderr during an engine call.

    `sink` receives the output; None discards it. `on_phase` receives each new
    marker phase. The tqdm bars hold the original stderr, so the redirect does
    not reach them.
    """
    target: TextIO = sink if sink is not None else cast(TextIO, _NullWriter())
    if on_phase is not None:
        target = cast(TextIO, _PhaseSniffer(target, on_phase))
    with redirect_stdout(target), redirect_stderr(target):
        yield
