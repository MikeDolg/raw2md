"""Single-line classifiers of markdown structure.

Each reads one stripped line and says whether it is structure, such as a
table separator, a thematic break, a fence border, a setext underline, or an
image wrapper tag, rather than prose or junk.
"""

from __future__ import annotations

import re

_TABLE_SEPARATOR_CHARS = frozenset("|:- \t")
_THEMATIC_BREAK_CHARS = "-*_"

# A setext underline makes a heading only under a paragraph.
_SETEXT_UNDERLINE_RE = re.compile(r"=+|-+")


ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")


def is_table_separator(core: str) -> bool:
    """True when `core` is a GFM table separator row (`|---|:--:|`)."""
    return "-" in core and all(ch in _TABLE_SEPARATOR_CHARS for ch in core)


def is_thematic_break(core: str) -> bool:
    """True when `core` is a thematic break (`---`, `***`, `___`)."""
    compact = core.replace(" ", "").replace("\t", "")
    return (
        len(compact) >= 3
        and compact[0] in _THEMATIC_BREAK_CHARS
        and all(ch == compact[0] for ch in compact)
    )


def is_fence_border(core: str) -> bool:
    """True when `core` is a bare code-fence border (``` or ~~~)."""
    return bool(re.fullmatch(r"`{3,}|~{3,}", core))


def is_math_delimiter(core: str) -> bool:
    """True when `core` is a standalone display-math delimiter (`$$`)."""
    return core == "$$"


def is_math_line_break(core: str) -> bool:
    """True when `core` is a standalone LaTeX row separator (`\\\\`, ...).

    pandoc puts it on its own line in a multi-line matrix. Only an even run is
    a whole token.
    """
    return len(core) >= 2 and len(core) % 2 == 0 and set(core) == {"\\"}


def is_structural_symbol_line(core: str) -> bool:
    """True when a symbol-only line is legitimate structure, not junk."""
    return (
        is_thematic_break(core)
        or is_table_separator(core)
        or is_fence_border(core)
        or is_math_delimiter(core)
        or is_math_line_break(core)
    )


_FIGURE_OPEN_RE = re.compile(r"^<figure\b[^>]*>$", re.IGNORECASE)
_FIGURE_CLOSE_RE = re.compile(r"^</figure\s*>$", re.IGNORECASE)
_STANDALONE_IMG_RE = re.compile(r"^<img\b[^>]*/?>$", re.IGNORECASE)


def is_html_media_wrapper_line(core: str) -> bool:
    """True when `core` is only an HTML image wrapper tag, not prose.

    pandoc repeats `<figure>` and `<img>` tags once per picture, which the
    repeat detector would read as a repeated line. One tag alone only.
    """
    return bool(
        _FIGURE_OPEN_RE.match(core)
        or _FIGURE_CLOSE_RE.match(core)
        or _STANDALONE_IMG_RE.match(core)
    )


def is_setext_underline(core: str, prev_core: str) -> bool:
    """True when `core` is a setext heading underline for the line above it.

    The line above must carry an alphanumeric and not be an ATX heading.
    """
    if _SETEXT_UNDERLINE_RE.fullmatch(core) is None:
        return False
    prev = prev_core.strip()
    return any(ch.isalnum() for ch in prev) and not prev.startswith("#")
