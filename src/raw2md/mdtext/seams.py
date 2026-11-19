"""Text tests at the seam of a paragraph that a page, a column, or a figure cuts.

The bundled engine joins the halves by layout and the cleaning joins them in
the body; both read the same text evidence from this one definition. The
engine copy imports this module, so it imports no engine, model, or cleaning
code.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache

# The Unicode classes come from `regex`, as in the engine: the tables of
# `unicodedata` follow the Python version and miss the numeric value of Han.
import regex  # type: ignore[import-untyped]  # regex ships no type stubs

from raw2md.mdtext.words import word_pattern

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


_LOWERCASE_START = regex.compile(r"^\p{Ll}")
# A lowercase letter that opens an item, as in `a)` or `b. `, starts no word.
_ITEM_LETTER = regex.compile(r"^\p{Ll}(?:\)|\.\s)")
# A script without letter case gives no lowercase start. Its evidence is a
# first half that ends in a letter or a comma and a second half that opens
# with a letter without case. A label, a table value, or a piece of a formula
# read as text holds 1 to 19 characters without spaces; a cut half holds more.
_CASELESS_START = regex.compile(r"^\p{Lo}")
_CASELESS_MIN_CHARS = 20
_VISIBLE = regex.compile(r"\S")
_LETTER = regex.compile(r"\p{L}")
# A numeral of any script before an item separator opens an item; a Han
# numeral carries a numeric value as well.
_ITEM_NUMBER = regex.compile(
    r"^[\p{N}\p{Numeric_Type=Numeric}]+[" + chr(0x3001) + r".)" + chr(0xFF09) + "]"
)


def first_half_runs_on(tail: str) -> bool:
    """True when `tail`, the stripped end of a first half, breaks off a sentence."""
    return bool(tail) and not closes_sentence(tail)


def second_half_runs_on(head: str) -> bool:
    """True when `head` opens in lowercase and starts no item like `a)` or `b. `."""
    return _LOWERCASE_START.match(head) is not None and _ITEM_LETTER.match(head) is None


def continues_without_case(tail: str, head: str) -> bool:
    """True when the halves of a script without letter case read as one sentence.

    `tail` is the stripped end of the first half, `head` the stripped start of
    the second. The text alone does not tell such a cut from two paragraphs,
    so the caller asks only at a break of the page or the column.
    """
    if not first_half_runs_on(tail):
        return False
    if len(_VISIBLE.findall(tail)) < _CASELESS_MIN_CHARS:
        return False
    # A comma of any width or script is a sign that Unicode names a comma.
    last = tail[-1]
    is_comma = unicodedata.category(last) == "Po" and "COMMA" in (
        unicodedata.name(last, "")
    )
    if not (_LETTER.match(last) or is_comma):
        return False
    return bool(_CASELESS_START.match(head) and not _ITEM_NUMBER.match(head))


# Fullwidth Latin letters and digits are words and keep their spaces.
_UNSPACED = regex.compile(
    r"[\p{Han}\p{Hiragana}\p{Katakana}　-〿]|(?![\p{L}\p{N}])[＀-￯]"
)


def joins_without_space(text: str, following: str) -> bool:
    """Whether `text` and the `following` text meet without a space.

    Han, kana, and fullwidth punctuation are written without spaces; Hangul
    and Latin words are not.
    """
    last = text.rstrip()[-1:]
    first = following.lstrip()[:1]
    return bool(last and first and _UNSPACED.match(last) and _UNSPACED.match(first))


# A label outside the vocabulary: a capitalized word of up to 12 letters, as
# in `Probl. 2.43`.
_CAPITALIZED_LABEL = r"\p{Lu}\p{L}{0,11}(?!\p{L})"
# The number after a label: arabic with its sections, or a roman chapter
# number, as in `Fig. IV.2`.
_CAPTION_NUMBER = r"\.?\s*(?:\d+(?:\.\d+)*|[IVXL]+\b)"


def caption_label_end(
    text: str, labels: tuple[str, ...], *, capitalized: bool = True
) -> int | None:
    """The end of the label and number that open `text`, or None.

    A label is a word of `labels`, the `caption_labels` section of
    keywords.yaml, or, when `capitalized`, a capitalized word of up to 12
    letters. What may follow the number is the caller's test.
    """
    found = _caption_label(labels, capitalized).match(text)
    return None if found is None else int(found.end())


@lru_cache(maxsize=8)
def _caption_label(labels: tuple[str, ...], capitalized: bool) -> regex.Pattern:
    label = word_pattern(labels).pattern
    if capitalized:
        label = f"{label}|{_CAPITALIZED_LABEL}"
    return regex.compile(f"(?:{label}){_CAPTION_NUMBER}")
