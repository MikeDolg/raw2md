"""Conversion engine interface and registry.

An engine declares its extensions and whether its external dependency is
present, and converts a source into a markdown body plus media. Selection is
by extension, case-insensitively. The registry tells "no engine for this
extension" from "dependency absent", so a missing dependency disables only
its formats and the rest of the batch runs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from raw2md.header import ConversionMethod

# A failing tool can repeat one line per page or per image strip, thousands of
# times, and bury the actual failure.
_MAX_OUTPUT_LINES: int = 20


class EngineError(Exception):
    """Base for engine-layer failures."""


class EngineNotFoundError(EngineError):
    """No registered engine handles the source's extension."""


class EngineUnavailableError(EngineError):
    """The engine for this format is present but its dependency is missing."""


class ConversionError(EngineError):
    """An engine could not convert a source; maps to exit code 4."""


@dataclass(frozen=True)
class ConvertOptions:
    """Per-file conversion options passed to every engine.

    `extract_media` is False under `--disable-image-extraction`. `on_phase`
    receives the current marker phase for the progress bar. `mark_pages` asks
    an engine that knows page boundaries to write a `mdtext.pages.page_mark` above
    each page, so inspection can address an edit by page; it is set only when
    inspection runs, so other runs stay unmarked. `scratch_dir` is a folder
    that lives as long as the file's processing: an engine that builds the pdf
    it converts (the djvu chain) leaves it there for inspection. An engine
    ignores an option it has no use for.
    """

    extract_media: bool = True
    on_phase: Callable[[str], None] | None = None
    mark_pages: bool = False
    scratch_dir: Path | None = None


@dataclass(frozen=True)
class ConversionResult:
    """Output of one conversion.

    `media` lists asset names relative to the media folder. `source_pages` is
    the page count of the pdf the engine converted (the source, or the
    assembled pdf of the djvu chain), the density denominator; None when there
    is no such count. `source_pdf` is the assembled pdf left in `scratch_dir`
    for inspection; None when the engine converted the source itself.
    """

    body: str
    media: tuple[str, ...] = ()
    source_pages: int | None = None
    source_pdf: Path | None = None


def _normalize_ext(extension: str) -> str:
    return extension.lower().lstrip(".")


def normalize_extension(source: Path) -> str:
    """Return `source`'s extension lower-cased and without the leading dot."""
    return _normalize_ext(source.suffix)


def condense_process_output(text: str, *, max_lines: int = _MAX_OUTPUT_LINES) -> str:
    """Shrink subprocess output for a log line or an error message.

    Consecutive identical lines collapse with a repeat count; the rest is
    capped at `max_lines`, which also bounds alternating repeats.
    """
    condensed: list[str] = []
    for line, group in groupby(text.splitlines()):
        count = sum(1 for _ in group)
        condensed.append(line if count == 1 else f"{line} (repeated {count} times)")
    if len(condensed) > max_lines:
        hidden = len(condensed) - max_lines
        condensed = [*condensed[:max_lines], f"... (+{hidden} more lines)"]
    return "\n".join(condensed)


class Engine(ABC):
    """One conversion route behind a common interface."""

    @property
    @abstractmethod
    def method(self) -> ConversionMethod:
        """The route this engine represents; route-gated cleaning rules read it."""

    @property
    @abstractmethod
    def extensions(self) -> frozenset[str]:
        """Lower-case extensions this engine handles, without the dot."""

    @abstractmethod
    def available(self) -> bool:
        """Whether the engine's external dependency is installed and usable."""

    def unavailable_reason(self) -> str | None:
        """Detail behind `available()` being False, for `doctor` to print.

        None when a plain "not found" says enough, or when the engine is
        available.
        """
        return None

    @abstractmethod
    def convert(
        self, source: Path, media_dir: Path, options: ConvertOptions
    ) -> ConversionResult:
        """Convert `source`, writing any extracted media into `media_dir`.

        Raises `ConversionError` when the source cannot be converted.
        """


class EngineRegistry:
    """Maps file extensions to engines and resolves the engine for a source."""

    def __init__(self, engines: Iterable[Engine]) -> None:
        self._by_extension: dict[str, Engine] = {}
        for engine in engines:
            for extension in engine.extensions:
                key = _normalize_ext(extension)
                if key in self._by_extension:
                    raise ValueError(f"extension '{key}' is claimed by two engines")
                self._by_extension[key] = engine

    def select(self, source: Path) -> Engine:
        """Return the engine for `source`, honoring case-insensitive extensions.

        Raises `EngineNotFoundError` when no engine handles the extension and
        `EngineUnavailableError` when the matching engine's dependency is absent.
        """
        extension = normalize_extension(source)
        engine = self._by_extension.get(extension)
        if engine is None:
            raise EngineNotFoundError(f"no engine for '.{extension}' files")
        if not engine.available():
            raise EngineUnavailableError(
                f"engine for '.{extension}' files is unavailable"
            )
        return engine

    def extensions(self) -> frozenset[str]:
        """All extensions claimed by registered engines (without the dot).

        `md` has no engine, so it is not among them.
        """
        return frozenset(self._by_extension)

    def unavailable(self) -> tuple[Engine, ...]:
        """Registered engines whose dependency is absent, each once."""
        seen: list[Engine] = []
        for engine in self._by_extension.values():
            if engine not in seen and not engine.available():
                seen.append(engine)
        return tuple(seen)
