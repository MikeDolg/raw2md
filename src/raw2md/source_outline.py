"""An outline of the document, exposed as a witness for the heading rules.

A converter infers heading levels from typography and fails where it is flat.
PDF bookmarks state the hierarchy as authored. `SourceOutline` maps each
title to its level, so a cleaning rule can take the level from the source. A
printed contents page, read by the cleaner, produces the same witness.

The witness holds no page numbers: it matches the body by title text only.
Titles compare as token sequences (`source_text.tokenize`), so numbering
punctuation, emphasis, and reflowed whitespace drop out while the words must
match exactly. An empty witness states nothing, and a rule that consults it
leaves the heading as it is.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path

from raw2md.source_text import tokenize

_logger = logging.getLogger("raw2md")

# Only pdf carries an outline this tool can read.
_PDF_EXTENSION = ".pdf"

# The title of an outline entry, reduced to what is compared.
_Key = tuple[str, ...]


class SourceOutline:
    """Heading levels a source states in its outline, or an empty witness."""

    __slots__ = ("_levels",)

    def __init__(self, entries: Sequence[tuple[int, str]] = ()) -> None:
        self._levels = _index(entries)

    @classmethod
    def empty(cls) -> SourceOutline:
        """A witness that states nothing -- the default for every route."""
        return cls()

    @classmethod
    def from_source(cls, source: Path) -> SourceOutline:
        """Read the outline of `source`, or return an empty witness.

        A read failure is logged, not silently equated with a document that
        has no outline.
        """
        if source.suffix.lower() != _PDF_EXTENSION:
            return cls.empty()
        # Lazy: a text-only route does not pay for loading PyMuPDF.
        from raw2md.engines import pymupdf

        try:
            entries = pymupdf.outline_entries(source)
        except (RuntimeError, OSError) as exc:
            # PyMuPDF raises RuntimeError subclasses, sometimes OSError, for a
            # malformed or encrypted document; the file still converts.
            _logger.warning("source outline unavailable for %s: %s", source.name, exc)
            return cls.empty()
        if not entries:
            return cls.empty()
        witness = cls(entries)
        _logger.info(
            "source outline in %s: %d entries, %d usable titles",
            source.name,
            len(entries),
            witness.title_count,
        )
        return witness

    @property
    def has_outline(self) -> bool:
        """True when the witness holds at least one usable title."""
        return bool(self._levels)

    @property
    def title_count(self) -> int:
        """Number of titles the witness can answer for (0 when it is empty)."""
        return len(self._levels)

    def level_for(self, title: str) -> int | None:
        """The outline level of `title`, or None when the outline does not state one.

        None also covers a title with no word and a title the outline places
        at two levels.
        """
        key = tuple(tokenize(title))
        if not key:
            return None
        return self._levels.get(key)

    def tokens_at(self, level: int) -> frozenset[tuple[str, ...]]:
        """Token sequence of every title the witness states `level` for.

        For a caller that compares more loosely than `found_titles`.
        """
        return frozenset(key for key, stated in self._levels.items() if stated == level)

    def found_titles(self, titles: Iterable[str], *, level: int | None = None) -> int:
        """How many distinct titles of the witness `titles` holds.

        Titles compare as in `level_for`. `level` narrows the count to the
        titles stated at that level.
        """
        if not self._levels:
            return 0
        keys = {tuple(tokenize(title)) for title in titles}
        if level is None:
            return len(keys & self._levels.keys())
        return sum(
            1 for key, stated in self._levels.items() if stated == level and key in keys
        )


def _index(entries: Sequence[tuple[int, str]]) -> dict[_Key, int]:
    """Map each usable outline title to its level.

    A title repeated at one level keeps it. A title repeated at two levels is
    dropped: the body cannot tell the occurrences apart. An entry with no word
    or with a level below 1 is dropped too.
    """
    levels: dict[_Key, int] = {}
    conflicting: set[_Key] = set()
    for level, title in entries:
        if level < 1:
            continue
        key = tuple(tokenize(title))
        if not key:
            continue
        known = levels.get(key)
        if known is None:
            levels[key] = level
        elif known != level:
            conflicting.add(key)
    for key in conflicting:
        del levels[key]
    return levels
