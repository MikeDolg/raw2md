"""The pattern that matches the records of a vocabulary section as words.

A section of keywords.yaml lists the words a page prints for a part of a
document. The cleaning and the engine copy read them through one pattern, so
a record means the same word to both.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Ends a stem record (`table*`). An abbreviation (`fig.`) needs no marker.
PREFIX_MARKER = "*"

# The rest of a stem's word: letters only, no digit or underscore.
_WORD_TAIL = r"[^\W\d_]*"

# An empty section matches nothing.
_MATCHES_NOTHING = r"(?!)"


@lru_cache(maxsize=32)
def word_pattern(records: tuple[str, ...], *, stem_guard: str = "") -> re.Pattern[str]:
    """One alternation matching any record of a section, whatever its case.

    A word is bounded at both ends. A stem (`table*`) is bounded at its head
    and runs through the rest of its word. A boundary goes only beside a word
    character, so an abbreviation (`fig.`) ends at its dot. Spaces match any
    whitespace run; the rest is literal. `stem_guard` is a lookaround the rule
    adds after a stem. Case blindness covers the records only, not the guard,
    which may mean the case it writes.
    """
    sources = [_record_source(record, stem_guard) for record in records]
    if not sources:
        return re.compile(_MATCHES_NOTHING)
    return re.compile(f"(?:{'|'.join(sources)})")


def _record_source(record: str, stem_guard: str) -> str:
    """The regex source of one record, in whichever of the three forms it takes."""
    if record.endswith(PREFIX_MARKER):
        stem = record[:-1]
        return rf"(?i:{_boundary(stem[:1])}{_literal(stem)}{_WORD_TAIL}){stem_guard}"
    return f"(?i:{_boundary(record[:1])}{_literal(record)}{_boundary(record[-1:])})"


def _boundary(edge: str) -> str:
    """`\\b` beside a word character, nothing beside punctuation."""
    return r"\b" if edge.isalnum() or edge == "_" else ""


def _literal(text: str) -> str:
    """`text` escaped, with each space in it matching a run of whitespace."""
    return r"\s+".join(re.escape(part) for part in text.split())
