"""Text tests at the seam of a paragraph that a page, a column, or a figure cuts.

The bundled engine joins the halves by layout and the cleaning joins them in
the body; both read the same text evidence from this one definition. The
engine copy imports this module, so it imports no engine, model, or cleaning
code.
"""

from __future__ import annotations

import unicodedata

# A mark that closes a sentence: ASCII, the ellipsis, and the CJK and
# fullwidth forms of `.`, `!`, `?`, `:`, `;`.
_SENTENCE_END_CHARS = frozenset(
    ".!?:;"
    + "".join(
        chr(code)
        for code in (0x2026, 0x3002, 0xFF0E, 0xFF61, 0xFF01, 0xFF1F, 0xFF1A, 0xFF1B)
    )
)

# Read past after a sentence mark: closing quotes and brackets, and the
# straight and fullwidth quotes, which Unicode files as other punctuation.
_SENTENCE_TAIL_EXTRA = frozenset("\"'" + chr(0xFF02) + chr(0xFF07))
_SENTENCE_TAIL_CATEGORIES = frozenset({"Pe", "Pf", "Pi"})


def closes_sentence(text: str) -> bool:
    """True when `text` ends on a sentence mark, past closing quotes and brackets.

    A trailing space counts as text, so the caller strips it first.
    """
    end = len(text)
    while end and (
        text[end - 1] in _SENTENCE_TAIL_EXTRA
        or unicodedata.category(text[end - 1]) in _SENTENCE_TAIL_CATEGORIES
    ):
        end -= 1
    return end > 0 and text[end - 1] in _SENTENCE_END_CHARS
