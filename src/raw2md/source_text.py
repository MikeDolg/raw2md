"""The source's own text layer, exposed as a witness for the deterministic rules.

Some defects are decidable only against the source: a line split at a hyphen
is a layout break in one document and a real hyphen in another. `SourceText`
lets a rule ask whether a form it wants to produce is attested by the source.

The witness is shallow: it answers whether a token occurs and whether the
source spells a word with a break inside it, and it hands out page text. It
has no page alignment with the body. An empty witness attests nothing, so a
rule that needs confirmation does not fire.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

_logger = logging.getLogger("raw2md")

# Formats that can carry a text layer: pdf (PyMuPDF) and djvu (djvutxt).
_PDF_EXTENSION = ".pdf"
_DJVU_EXTENSION = ".djvu"

# Punctuation splits a token: a word broken across two lines attests its
# halves, not the joined form.
_TOKEN_RE = re.compile(r"\w+")

# A soft hyphen belongs to the layout, not the word.
_SOFT_HYPHEN = "\u00ad"

# What can join two halves of one word: hyphens, dashes, the minus sign,
# zero-width characters, and non-whitespace C0 controls. A break with a space
# makes two words, which is a different question.
_WORD_BREAK_CLASS = (
    "[-\u00ad\u2010-\u2015\u2212\u200b-\u200d\ufeff\x00-\x08\x0e-\x1f\x7f]"
)

# A word with a break inside it (`cost-effective`). A hyphen at a line end
# does not match. Public: a rule that rewrites such a spelling must find it.
BROKEN_WORD_RE = re.compile(rf"\w+(?:{_WORD_BREAK_CLASS}+\w+)+")

# Keeps the breaks, so halves and breaks are normalized apart.
_WORD_BREAK_SPLIT_RE = re.compile(rf"({_WORD_BREAK_CLASS}+)")


class SourceText:
    """Per-page text layer of a source, or an empty witness when it has none."""

    __slots__ = ("_hyphen_forms", "_page_tokens", "_pages")

    def __init__(self, pages: Sequence[str] = ()) -> None:
        self._pages = tuple(pages)
        # Precomputed: a rule asks one word at a time.
        self._page_tokens = tuple(frozenset(tokenize(page)) for page in self._pages)
        # Held per document: a spelling is the document's convention.
        self._hyphen_forms = frozenset(
            form for page in self._pages for form in hyphen_forms(page)
        )

    @classmethod
    def empty(cls) -> SourceText:
        """A witness that attests nothing -- the default for every route."""
        return cls()

    @classmethod
    def from_source(cls, source: Path) -> SourceText:
        """Read the text layer of `source`, or return an empty witness.

        The text-layer detector decides whether a layer exists: a stray glyph
        on a scan must never pass for attestation. A false confirmation is
        irreversible; a missing one leaves the text as it is. A read failure
        is logged, not equated with a scan.
        """
        suffix = source.suffix.lower()
        if suffix == _PDF_EXTENSION:
            pages = _pdf_pages(source)
        elif suffix == _DJVU_EXTENSION:
            pages = _djvu_pages(source)
        else:
            return cls.empty()
        if pages is None:
            return cls.empty()
        _logger.info("source text layer in %s: %d pages", source.name, len(pages))
        return cls(pages)

    @property
    def pages(self) -> tuple[str, ...]:
        """Text of each source page, in page order, as the layer holds it."""
        return self._pages

    @property
    def page_count(self) -> int:
        """Number of pages the witness carries (0 when it is empty)."""
        return len(self._pages)

    @property
    def has_layer(self) -> bool:
        """True when at least one page yielded a token."""
        return any(self._page_tokens)

    def has_token(self, token: str, *, page: int | None = None) -> bool:
        """True when `token` occurs in the source text, case- and form-insensitively.

        `page` narrows the question to one 0-based page; out of range answers
        False. A query that is not exactly one token is not attested: matching
        part of a phrase would confirm more than the witness knows.
        """
        wanted = tokenize(token)
        if len(wanted) != 1:
            return False
        if page is None:
            return any(wanted[0] in tokens for tokens in self._page_tokens)
        if not 0 <= page < len(self._page_tokens):
            return False
        return wanted[0] in self._page_tokens[page]

    def has_hyphen_form(self, word: str) -> bool:
        """True when the source spells `word` with the same break inside it.

        `word` is normalized as `hyphen_forms` reads it. A word with no break,
        or with a space, is not attested. The whole document answers: a layout
        break at a line end never reaches the index.
        """
        forms = hyphen_forms(word)
        return len(forms) == 1 and forms[0] in self._hyphen_forms


def _pdf_pages(source: Path) -> list[str] | None:
    """Page texts of a pdf, or None when it yields no witness."""
    # Lazy: a text-only route does not pay for loading PyMuPDF.
    from raw2md.engines import pymupdf

    try:
        if not pymupdf.has_text_layer(source):
            _logger.info("no source text layer in %s", source.name)
            return None
        return pymupdf.page_texts(source)
    except (RuntimeError, OSError) as exc:
        # PyMuPDF raises RuntimeError subclasses, sometimes OSError, for a
        # malformed or encrypted document; the file still converts.
        _logger.warning("source text unavailable for %s: %s", source.name, exc)
        return None


def _djvu_pages(source: Path) -> list[str] | None:
    """Page texts of a djvu, or None when it yields no witness.

    The pdf text-layer floor decides here too.
    """
    from raw2md.engines import djvu, pymupdf
    from raw2md.engines.base import ConversionError

    try:
        pages = djvu.page_texts(source)
    except ConversionError as exc:
        # The file still converts through the render chain.
        _logger.warning("source text unavailable for %s: %s", source.name, exc)
        return None
    if not pymupdf.pages_bear_text(pages):
        _logger.info("no source text layer in %s", source.name)
        return None
    return pages


def tokenize(text: str) -> list[str]:
    """Split `text` into comparable tokens.

    NFKC folds ligatures and full-width forms of a PDF text layer; casefold
    makes the comparison case-insensitive. Every comparison against the
    source tokenizes both sides with this function.
    """
    normalized = unicodedata.normalize("NFKC", text.replace(_SOFT_HYPHEN, ""))
    return _TOKEN_RE.findall(normalized.casefold())


def hyphen_forms(text: str) -> list[str]:
    """The words `text` spells with a break inside them, in order.

    The halves are normalized as in `tokenize`; the break stays exactly as
    written, soft hyphen included: the joining character is the spelling, and
    NFKC would let the non-breaking hyphen attest the plain one.
    """
    forms: list[str] = []
    for match in BROKEN_WORD_RE.finditer(text):
        pieces = _WORD_BREAK_SPLIT_RE.split(match.group())
        # Odd positions are the breaks the split kept; even ones are the halves.
        forms.append(
            "".join(
                piece if index % 2 else unicodedata.normalize("NFKC", piece).casefold()
                for index, piece in enumerate(pieces)
            )
        )
    return forms
