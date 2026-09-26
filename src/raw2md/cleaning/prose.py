"""Rules that fix a converter's plain prose text, not its structure.

Early passes read a line at a time: alt-text paths, invisible characters,
junk lines, homoglyphs, glued emphasis, split numbers, heading spaces, page
anchors, and the page band. After the structural passes come the rules the
body's own spelling decides: hyphen rejoin, crushed paragraphs, letter-spaced
runs, whole-paragraph emphasis, and compound hyphens. `collapse_blanks` closes
every cleaning run.

`letter_spaced_runs` and `spacing_witness` export the spacing reading for the
findings report; `is_caption_label` exports the caption vocabulary.
"""

from __future__ import annotations

import logging
import re
import statistics
import string
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise

from raw2md.cleaning.segments import (
    CYRILLIC_LOWER,
    CYRILLIC_UPPER,
    LIST_ITEM_RE,
    WORD_RUN_RE,
    block_content_lines,
    block_continues,
    block_end,
    body_word_counts,
    display_block_lines,
    flattened_paragraph_runs,
    is_image_only_line,
    is_standalone,
    prose_reading,
    skip_hyphen_gap,
)
from raw2md.keywords import Keywords, word_pattern
from raw2md.mdtext.lines import (
    ATX_HEADING_RE,
    is_html_media_wrapper_line,
    is_setext_underline,
    is_structural_symbol_line,
)
from raw2md.mdtext.links import IMAGE_RE, mask_addresses
from raw2md.mdtext.math_spans import (
    is_math_only_line,
    mask_math,
    math_span_content,
    math_spans,
)
from raw2md.mdtext.pages import page_mark_number
from raw2md.mdtext.zones import Segment, html_table_lines, mask_inline_code, segments
from raw2md.source_text import BROKEN_WORD_RE, SourceText, hyphen_forms, tokenize

_logger = logging.getLogger("raw2md")

# Soft hyphen and the zero-width family, BOM included. Invisible mid-word,
# they still make a different token and break a search match.
_INVISIBLE_FORMAT_CHARS = (
    chr(0x00AD) + chr(0x200B) + chr(0x200C) + chr(0x200D) + chr(0xFEFF)
)
_INVISIBLE_FORMAT_RE = re.compile(f"[{_INVISIBLE_FORMAT_CHARS}]")

# Latin letters and their identical Cyrillic look-alikes, which OCR confuses
# letter by letter: `Tаблица` for `Таблица`.  # noqa: RUF003
# The map reads both ways: `MОDEL` for `MODEL`.  # noqa: RUF003
_HOMOGLYPH_LATIN_TO_CYRILLIC = {
    "A": chr(0x0410),
    "B": chr(0x0412),
    "E": chr(0x0415),
    "K": chr(0x041A),
    "M": chr(0x041C),
    "H": chr(0x041D),
    "O": chr(0x041E),
    "P": chr(0x0420),
    "C": chr(0x0421),
    "T": chr(0x0422),
    "X": chr(0x0425),
    "a": chr(0x0430),
    "e": chr(0x0435),
    "o": chr(0x043E),
    "p": chr(0x0440),
    "c": chr(0x0441),
    "y": chr(0x0443),
    "x": chr(0x0445),
}

# Proves no script. A Cyrillic letter outside this set, such as
# `б`, `л`, `и`, is an anchor that proves the word Cyrillic.  # noqa: RUF003
_HOMOGLYPH_AMBIGUOUS_CYRILLIC = frozenset(_HOMOGLYPH_LATIN_TO_CYRILLIC.values())

# Each look-alike maps to exactly one Latin letter, so the inverse is defined.
_HOMOGLYPH_CYRILLIC_TO_LATIN = {
    cyrillic: latin for latin, cyrillic in _HOMOGLYPH_LATIN_TO_CYRILLIC.items()
}

_LATIN_LETTERS = frozenset(string.ascii_letters)

# The unit that `_normalize_homoglyphs` judges whole. A hyphen or a digit
# breaks it, so a Latin letter hyphenated to a Cyrillic word is its own run.
_HOMOGLYPH_WORD_RE = re.compile(rf"[A-Za-z{CYRILLIC_UPPER}{CYRILLIC_LOWER}]+")

# `##Text` -> `## Text`; a lone `#` and seven or more `#` are no heading.
_HEADING_SPACE_RE = re.compile(r"^( {0,3}#{1,6})(?=[^#\s])")

# A drop cap or heavy type reads a word's head as bold: `**I**nterface`, or a
# Cyrillic initial `**А**` glued to its word.  # noqa: RUF003
# A digit or a space inside means no broken word: `**59**2` is a citation.
_GLUED_EMPHASIS_RE = re.compile(r"\*\*(?P<word>[^\W\d_]+)\*\*")

# A canonical roman numeral, so a rebuilt `V II` is checked against one.
_CANONICAL_ROMAN_RE = re.compile(
    r"(?=[IVXLCDM])M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$"
)

# Two roman runs split by a space before `.<digit>` (`Fig. V II.11`). The
# dotted number tells a split numeral from two numerals side by side. A split
# into three runs is left whole, so the rule stays idempotent.
_SPACED_ROMAN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?<![IVXLCDM] )([IVXLCDM]+) ([IVXLCDM]+)(?=\.\d)"
)

# `82. 1.` for `82.1.` at the head of a line, possibly bold; otherwise `82.`
# reads as a list marker. `p. 12` stays. A third `<digits>.` run at any
# spacing (`1. 2.  3.`) is an enumeration; a bare digit (`82. 1. 5 items`) is
# not a third run.
_SPLIT_ENTRY_NUMBER_RE = re.compile(
    r"^ {0,3}(?:\*\*)?\d{1,9}\. (\d{1,9}\.)(?!\s*\d{1,9}\.)(?=\*\*| |$)"
)

# marker's empty page anchor, dropped whole: it has no visible content.
_SPAN_ANCHOR_RE = re.compile(r'<span id="[^"]*">\s*</span>')

# `[text](#target)`, the other half of a page anchor; image links excluded.
_INTERNAL_LINK_RE = re.compile(r'(?<!!)\[([^\]]*)\]\(#[^)\s]*(?:\s+"[^"]*")?\)')

# Generous rather than exhaustive: any of them marks a file, not a caption.
_ALT_IMAGE_EXTENSIONS = r"png|jpe?g|gif|bmp|tiff?|webp|svg|emf|wmf|ico"

# A Windows drive, UNC, or POSIX absolute path to an image.
_ALT_ABSOLUTE_PATH_RE = re.compile(
    rf"^(?:[A-Za-z]:[\\/]|\\\\|/)[^\r\n]*\.(?:{_ALT_IMAGE_EXTENSIONS})$",
    re.IGNORECASE,
)

# Word's default caption for a picture with none set (`image1.png`).
_ALT_BARE_FILENAME_RE = re.compile(
    rf"^[^\\/\r\n]+\.(?:{_ALT_IMAGE_EXTENSIONS})$",
    re.IGNORECASE,
)

# Like `mdtext.links.HTML_IMG_RE`, but for `alt` rather than `src`.
_HTML_IMG_ALT_RE = re.compile(r'(<img\b[^>]*?\salt=")([^"]*)(")', re.IGNORECASE)


def strip_alt_file_paths(text: str) -> str:
    """Drop an image `alt`/`descr` value that is a source file path, not a caption.

    Word stores the image's local path in `descr`, and pandoc maps it to the
    alt text. Markdown and HTML forms are both cleared; the target stays.
    Runs on raw text: an `<img>` inside an HTML table is fixed, while other
    protected lines stay verbatim.
    """
    seg_list = segments(text)
    in_table = html_table_lines(text)
    out: list[str] = []
    for (line, protected), table_line in zip(seg_list, in_table, strict=True):
        if protected and not table_line:
            out.append(line)
            continue
        fixed = IMAGE_RE.sub(_strip_markdown_alt_path, line)
        fixed = _HTML_IMG_ALT_RE.sub(_strip_html_alt_path, fixed)
        out.append(fixed)
    body = "\n".join(out)
    return f"{body}\n" if text.endswith("\n") else body


def _is_alt_file_path(alt: str) -> bool:
    """True when `alt`'s value is a file path or bare filename, not a caption."""
    value = alt.strip()
    if not value:
        return False
    return bool(
        _ALT_ABSOLUTE_PATH_RE.match(value) or _ALT_BARE_FILENAME_RE.match(value)
    )


def _strip_markdown_alt_path(match: re.Match[str]) -> str:
    alt = match.group(1)
    if not _is_alt_file_path(alt):
        return match.group(0)
    start, end = match.span(1)
    base = match.start()
    text = match.group(0)
    return text[: start - base] + text[end - base :]


def _strip_html_alt_path(match: re.Match[str]) -> str:
    prefix, alt, suffix = match.group(1), match.group(2), match.group(3)
    if not _is_alt_file_path(alt):
        return match.group(0)
    return f"{prefix}{suffix}"


def classify_and_fix(text: str) -> list[Segment]:
    """Classify via `segments`, then fix or drop each plain line in place.

    The previous line tells a setext underline from junk. A line of a
    multi-line display formula only loses noise: a matrix row of alignment
    marks (`& & . & \\\\`) would otherwise read as junk.
    """
    result: list[Segment] = []
    prev_line = ""
    seg_list = segments(text)
    in_formula = display_block_lines(seg_list)
    for (line, protected), formula_line in zip(seg_list, in_formula, strict=True):
        if protected:
            result.append((line, True))
            prev_line = line
            continue
        if formula_line:
            result.append((strip_line_noise(line), False))
            prev_line = line
            continue
        fixed = _fix_plain_line(line, prev_line)
        prev_line = line
        if fixed is None:
            continue
        result.append((fixed, False))
    return result


def strip_line_noise(line: str) -> str:
    """Drop invisible format characters and trailing whitespace from a line.

    It judges no word, so it is safe to rerun over a line an LLM rewrote.
    """
    return _INVISIBLE_FORMAT_RE.sub("", line).rstrip()


def _fix_plain_line(line: str, prev_line: str) -> str | None:
    """Apply per-line plain fixes; return the fixed line, or None to drop it."""
    stripped = strip_line_noise(line)
    if _is_junk_line(stripped, prev_line):
        return None
    stripped = _normalize_homoglyphs(stripped)
    stripped = _strip_glued_emphasis(stripped)
    stripped = _join_spaced_roman(stripped)
    stripped = _join_split_entry_number(stripped)
    return _HEADING_SPACE_RE.sub(r"\1 ", stripped)


def _strip_glued_emphasis(line: str) -> str:
    """Drop the `**` around a bold span glued to a letter outside it.

    A span set apart (`**787.4.**`) keeps its markers. Code and math are
    masked.
    """
    if "**" not in line:
        return line
    masked = mask_math(mask_addresses(line))
    spans = [
        match.span()
        for match in _GLUED_EMPHASIS_RE.finditer(masked)
        if (match.start() and line[match.start() - 1].isalpha())
        or (match.end() < len(line) and line[match.end()].isalpha())
    ]
    if not spans:
        return line
    out: list[str] = []
    last = 0
    for start, end in spans:
        out.append(line[last:start])
        out.append(line[start + 2 : end - 2])
        last = end
    out.append(line[last:])
    return "".join(out)


def _join_spaced_roman(line: str) -> str:
    """Close the space inside a roman figure number: `V II.11` -> `VII.11`.

    The joined runs must be a canonical numeral. Code and math are masked.
    """
    if "." not in line:
        return line
    masked = mask_math(mask_addresses(line))
    cuts = [
        match.span()
        for match in _SPACED_ROMAN_RE.finditer(masked)
        if _CANONICAL_ROMAN_RE.match(match.group(1) + match.group(2))
    ]
    if not cuts:
        return line
    out: list[str] = []
    last = 0
    for start, end in cuts:
        out.append(line[last:start])
        out.append(line[start:end].replace(" ", "", 1))
        last = end
    out.append(line[last:])
    return "".join(out)


def _join_split_entry_number(line: str) -> str:
    """Close the space inside a multi-level entry number: `82. 1.` -> `82.1.`."""
    match = _SPLIT_ENTRY_NUMBER_RE.match(line)
    if match is None:
        return line
    gap = match.start(1) - 1
    return line[:gap] + line[gap + 1 :]


def _is_junk_line(line: str, prev_line: str) -> bool:
    """A symbol-only line that should be dropped.

    A single symbol and every structural symbol line stay, and so does a
    setext underline under text.
    """
    core = line.strip()
    if len(core) <= 1:
        return False
    if any(ch.isalnum() for ch in core):
        return False
    if is_structural_symbol_line(core):
        return False
    return not is_setext_underline(core, prev_line)


def _normalize_homoglyphs(line: str) -> str:
    """Swap an OCR homoglyph for its same-script twin inside a mis-scripted word.

    Recognition picks a script per glyph, not per word. The result renders
    the same but misses a search match. Addresses and inline code are masked:
    rewriting one could repoint a link.
    """
    masked = mask_addresses(line)
    pieces: list[str] = []
    last = 0
    for match in _HOMOGLYPH_WORD_RE.finditer(masked):
        start, end = match.span()
        pieces.append(line[last:start])
        pieces.append(_normalize_homoglyph_word(line[start:end]))
        last = end
    pieces.append(line[last:])
    return "".join(pieces)


def _normalize_homoglyph_word(word: str) -> str:
    """The homoglyph-normalized form of `word`, or `word` unchanged.

    To Cyrillic: the word has a Latin look-alike, no Latin anchor (`ISO`), and
    a Cyrillic anchor, since a word of look-alikes only may be Latin (`cop`).
    To Latin is the mirror image. The directions exclude each other. The
    anchor decides, not the majority of letters.
    """
    has_latin_doubler = False
    has_latin_anchor = False
    has_cyrillic_doubler = False
    has_cyrillic_anchor = False
    for ch in word:
        if ch in _LATIN_LETTERS:
            if ch in _HOMOGLYPH_LATIN_TO_CYRILLIC:
                has_latin_doubler = True
            else:
                has_latin_anchor = True
        elif ch in _HOMOGLYPH_AMBIGUOUS_CYRILLIC:
            has_cyrillic_doubler = True
        else:
            has_cyrillic_anchor = True
    if has_latin_doubler and not has_latin_anchor and has_cyrillic_anchor:
        return "".join(_HOMOGLYPH_LATIN_TO_CYRILLIC.get(ch, ch) for ch in word)
    if has_cyrillic_doubler and not has_cyrillic_anchor and has_latin_anchor:
        return "".join(_HOMOGLYPH_CYRILLIC_TO_LATIN.get(ch, ch) for ch in word)
    return word


def strip_html_anchors(seg_list: list[Segment]) -> list[Segment]:
    """Remove marker's page anchors and unwrap internal links, in plain zones only.

    A page number means nothing once the source is markdown. Runs before the
    heading rules: an anchor after the marker hides the section number.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, True))
            continue
        fixed = _SPAN_ANCHOR_RE.sub("", line)
        fixed = _INTERNAL_LINK_RE.sub(r"\1", fixed)
        out.append((fixed, False))
    return out


# ---- page furniture ---------------------------------------------------------

# A margin holds a title and a number; a longer line is body prose.
_FURNITURE_MAX_LEN = 80

# One above a specification block, which restates a label and value three
# times inside one page.
_FURNITURE_MIN_PAIRS = 4

# A card label pairs with a number only by accident; a running header does
# on nearly every page.
_FURNITURE_MIN_PAIRED_SHARE = 0.5

# A page number travels with a short label ("Page ... of ..."); a sentence
# citing a table carries several times more.
_FURNITURE_LABEL_MAX_LETTERS = 24

# Neither a title nor a page number closes a sentence.
_FURNITURE_SENTENCE_STOPS = (".", ",", ";", ":", "!", "?")

# The number after a caption label whose title a column cut away. The
# leading dot belongs to a shortened label (`fig` for `Fig. 3`).
_CAPTION_NUMBER_TAIL = r"\.?[ \t]*\d+(?:[.\-]\d+)*\.?"

# Median gap between pairs, in lines. A band steps by a page, dozens of
# lines; a tighter pair repeats per card.
_FURNITURE_MIN_MEDIAN_GAP = 20


def is_caption_label(line: str, keywords: Keywords) -> bool:
    """True when `line` is a caption's label and number and nothing else.

    The labels come from `keywords.yaml`, section `caption_labels`.
    """
    return (
        _caption_label_line(keywords.caption_labels).fullmatch(line.strip()) is not None
    )


@lru_cache(maxsize=8)
def _caption_label_line(records: tuple[str, ...]) -> re.Pattern[str]:
    # One pattern, so `figure no.` is tried as well as `figure`.
    return re.compile(word_pattern(records).pattern + _CAPTION_NUMBER_TAIL)


def drop_page_furniture(seg_list: list[Segment], keywords: Keywords) -> list[Segment]:
    """Drop a page's header/footer band left standing as prose.

    Read by shape: a title-like line repeating verbatim, beside a line whose
    number changes with every copy, the pair recurring a page apart. Both
    lines of a confirmed pair go; a lone occurrence stays. The step of the
    numbers is not read: a lost header breaks the arithmetic. A candidate
    that fails any guard keeps both lines: a band left is a repeated line, a
    card label dropped is lost content. Runs before the outline pass, whose
    result keys line indices.
    """
    captions = word_pattern(keywords.caption_labels)
    doomed: set[int] = set()
    for occurrences in _furniture_candidates(seg_list).values():
        doomed |= _page_band_pairs(seg_list, occurrences, captions)
    if not doomed:
        return seg_list
    return [seg for idx, seg in enumerate(seg_list) if idx not in doomed]


def _furniture_candidates(seg_list: list[Segment]) -> dict[str, list[int]]:
    """Indices of each plain line repeating often enough to head a band."""
    positions: dict[str, list[int]] = {}
    for idx, (line, _protected) in enumerate(seg_list):
        core = line.strip()
        if not _is_band_at(seg_list, idx) or not _reads_as_a_title(core):
            continue
        positions.setdefault(core, []).append(idx)
    return {
        core: occurrences
        for core, occurrences in positions.items()
        if len(occurrences) >= _FURNITURE_MIN_PAIRS
    }


def _page_band_pairs(
    seg_list: list[Segment], occurrences: list[int], captions: re.Pattern[str]
) -> set[int]:
    """Indices to drop for the repeated line at `occurrences`, empty if not a band.

    The number stands below or above the title; the larger side wins.
    """
    pairs: list[tuple[int, int]] = []
    for side in (1, -1):
        group = _numbered_neighbours(seg_list, occurrences, side, captions)
        if len(group) > len(pairs):
            pairs = group
    if len(pairs) < _FURNITURE_MIN_PAIRS:
        return set()
    if len(pairs) < _FURNITURE_MIN_PAIRED_SHARE * len(occurrences):
        return set()
    gaps = [later - earlier for (earlier, _), (later, _) in pairwise(pairs)]
    if statistics.median(gaps) < _FURNITURE_MIN_MEDIAN_GAP:
        return set()
    return {idx for pair in pairs for idx in pair}


def _numbered_neighbours(
    seg_list: list[Segment],
    occurrences: list[int],
    side: int,
    captions: re.Pattern[str],
) -> list[tuple[int, int]]:
    """The `(line, neighbour)` pairs whose neighbour is one number line restated.

    Neighbours group by letters alone, since recognition swaps punctuation
    between pages. A neighbour text repeated case-blind ("200 MM", "200 mm")
    is a restated field, not a page number, and leaves the group.
    """
    groups: dict[str, list[tuple[int, int, str]]] = {}
    for idx in occurrences:
        neighbour = _neighbour_index(seg_list, idx, side)
        if neighbour is None:
            continue
        core = seg_list[neighbour][0].strip()
        if not _is_band_at(seg_list, neighbour):
            continue
        if not any(ch.isdigit() for ch in core):
            continue
        if _closes_a_sentence(core) or captions.search(core) is not None:
            continue
        label = _band_label(core)
        if len(label) > _FURNITURE_LABEL_MAX_LETTERS:
            continue
        groups.setdefault(label, []).append((idx, neighbour, core))
    if not groups:
        return []
    members = max(groups.values(), key=len)
    restated = Counter(text.casefold() for _, _, text in members)
    return [
        (idx, neighbour)
        for idx, neighbour, text in members
        if restated[text.casefold()] == 1
    ]


def _neighbour_index(seg_list: list[Segment], idx: int, side: int) -> int | None:
    """Index of the block neighbouring `idx` on `side`, or None.

    Blank lines are stepped over. A protected zone or a page mark ends the
    search: a band's two lines print on one page.
    """
    cursor = idx + side
    while 0 <= cursor < len(seg_list):
        line, protected = seg_list[cursor]
        if protected:
            return None
        if line.strip():
            return None if page_mark_number(line) is not None else cursor
        cursor += side
    return None


def _is_band_at(seg_list: list[Segment], idx: int) -> bool:
    """True when the line at `idx` could be one line of a page's margin band.

    A setext heading is left to the heading rules.
    """
    line, protected = seg_list[idx]
    if protected:
        return False
    core = line.strip()
    if not _is_band_line(core):
        return False
    following = idx + 1
    if following >= len(seg_list) or seg_list[following][1]:
        return True
    return not is_setext_underline(seg_list[following][0].strip(), core)


def _is_band_line(core: str) -> bool:
    """True when `core` reads as a page-margin line, on its own text alone."""
    if not core or len(core) > _FURNITURE_MAX_LEN:
        return False
    if not any(ch.isalnum() for ch in core):
        return False
    if core.startswith(("#", ">", "<")) or "|" in core:
        return False
    if LIST_ITEM_RE.match(core):
        return False
    return not (
        is_image_only_line(core)
        or is_math_only_line(core)
        or is_html_media_wrapper_line(core)
    )


def _reads_as_a_title(core: str) -> bool:
    """True when `core` reads as a title a margin restates rather than as prose.

    Refused: one word ("where"), a lowercase opening, and a sentence close.
    """
    if len(core.split()) < 2 or _closes_a_sentence(core):
        return False
    for ch in core:
        if ch.isalnum():
            return not ch.islower()
    return False


def _closes_a_sentence(core: str) -> bool:
    """True when `core` ends on punctuation that closes a sentence or opens a list."""
    return core.rstrip("*_ ").endswith(_FURNITURE_SENTENCE_STOPS)


def _band_label(core: str) -> str:
    """The letters of `core`, lowercased -- what stays put while its number moves."""
    return "".join(ch.lower() for ch in core if ch.isalpha())


# ---- hyphenation rejoin -----------------------------------------------------

# A digit matches here, so a code like `S7-200` reaches the explicit digit
# guard in `_try_rejoin`.
_TRAILING_WORD_RE = re.compile(r"(\w+)-\Z")
_LEADING_WORD_RE = re.compile(r"\A(\w+)")

# Emphasis markers that a converter closes and reopens across a line break.
_SEAM_MARKERS = "*_"

# Inflection makes a single coincidental hit unremarkable.
_MERGED_FORM_MIN_COUNT = 2

# From this many same-line occurrences, the hyphen is a convention of the
# document, and the rejoin is blocked.
_HYPHEN_FORM_BLOCK_THRESHOLD = 3


def rejoin_hyphenation(
    seg_list: list[Segment], source_text: SourceText
) -> list[Segment]:
    """Join a word a typesetter's hyphen split across two lines, where attested.

    The joined form must be in the source text layer or occur at least
    `_MERGED_FORM_MIN_COUNT` times in the body. Seam emphasis markers are read
    past. The adjacent pair is tried first, then the first prose line past a
    gap (`skip_hyphen_gap`). A figure from the gap moves after the joined
    line; a page mark moves to the next line that opens content. An
    unconfirmed pair stays for the findings report.
    """
    body_tokens = Counter(
        token
        for line, protected in seg_list
        if not protected
        for token in tokenize(line)
    )
    out: list[Segment] = []
    carried_marks: list[str] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        rejoined = (
            None
            if protected
            else _rejoin_at(seg_list, idx, line, body_tokens, source_text)
        )
        if rejoined is None:
            if protected or line.strip():
                _emit_marks(out, carried_marks)
            out.append((line, protected))
            idx += 1
            continue
        merged, gap_idx, cont_end = rejoined
        _emit_marks(out, carried_marks)
        out.append((merged, False))
        # The rest of the continuation's paragraph stays right behind it.
        out.extend((seg_list[k][0], False) for k in range(gap_idx + 1, cont_end))
        gap_lines = [seg_list[k][0] for k in range(idx + 1, gap_idx)]
        # A figure below a page mark opens the new page and travels with the
        # mark, or inspection would attribute it to the page before.
        first_mark = next(
            (
                pos
                for pos, gap in enumerate(gap_lines)
                if page_mark_number(gap) is not None
            ),
            len(gap_lines),
        )
        images = [gap for gap in gap_lines[:first_mark] if is_image_only_line(gap)]
        tail = [
            gap
            for gap in gap_lines[first_mark:]
            if page_mark_number(gap) is not None or is_image_only_line(gap)
        ]
        # A page that opens on a figure keeps its mark right above that figure.
        opens_on_a_figure = any(is_image_only_line(gap) for gap in tail)
        moved = images + tail if opens_on_a_figure else images
        if moved:
            out.append(("", False))
            out.extend((line, False) for line in moved)
        # Otherwise the mark waits for the next line that opens content; placed
        # elsewhere, its later removal would add or remove a blank line.
        if not opens_on_a_figure:
            carried_marks.extend(tail)
        idx = cont_end
    _emit_marks(out, carried_marks)
    return out


def _emit_marks(out: list[Segment], marks: list[str]) -> None:
    """Append the page marks and figures a rejoin carried, and clear the list.

    The blank before a figure goes in front of the whole run, not after the
    mark: the mark is removed later and would leave a double blank.
    """
    if not marks:
        return
    if any(is_image_only_line(line) for line in marks) and out and out[-1][0].strip():
        out.append(("", False))
    out.extend((line, False) for line in marks)
    if is_image_only_line(marks[-1]):
        # A figure glued to the next line would join its paragraph.
        out.append(("", False))
    marks.clear()


def _rejoin_at(
    seg_list: list[Segment],
    idx: int,
    line: str,
    body_tokens: Counter[str],
    source_text: SourceText,
) -> tuple[str, int, int] | None:
    """The rejoin for the hyphen candidate at `idx`, adjacent first, then gapped.

    Returns ``(merged, gap_idx, cont_end)``: the joined line, the absorbed
    continuation line, and the end of its paragraph; None when unconfirmed.
    """
    count = len(seg_list)
    if idx + 1 < count:
        next_line, next_protected = seg_list[idx + 1]
        if not next_protected:
            merged = _try_rejoin(line, next_line, seg_list, body_tokens, source_text)
            if merged is not None:
                return merged, idx + 1, idx + 2
    if not _TRAILING_WORD_RE.search(demark_seam_end(line)):
        return None
    gap_idx = skip_hyphen_gap(seg_list, idx + 1)
    if gap_idx is None:
        return None
    cont_line, cont_protected = seg_list[gap_idx]
    if cont_protected:
        return None
    merged = _try_rejoin(line, cont_line, seg_list, body_tokens, source_text)
    if merged is None:
        return None
    return merged, gap_idx, block_end(seg_list, gap_idx)


def _try_rejoin(
    line: str,
    next_line: str,
    seg_list: list[Segment],
    body_tokens: Counter[str],
    source_text: SourceText,
) -> str | None:
    """The joined line, when the split between `line` and `next_line` is attested.

    Markers outside the seam keep their place.
    """
    head = demark_seam_end(line)
    trailing = _TRAILING_WORD_RE.search(head)
    if trailing is None:
        return None
    frag1 = trailing.group(1)
    tail = demark_seam_start(next_line)
    if not _seam_markers_reopen(line, head, next_line, tail):
        return None
    leading = _LEADING_WORD_RE.match(tail)
    if leading is None:
        return None
    frag2 = leading.group(1)
    if frag2[0].isupper():
        return None
    if any(ch.isdigit() for ch in frag1) or any(ch.isdigit() for ch in frag2):
        return None
    merged_word = frag1 + frag2
    tokens = tokenize(merged_word)
    if len(tokens) != 1:
        return None
    if (
        _hyphenated_spelling_count(seg_list, frag1, frag2)
        >= _HYPHEN_FORM_BLOCK_THRESHOLD
    ):
        return None
    confirmed = source_text.has_token(merged_word) or (
        body_tokens[tokens[0]] >= _MERGED_FORM_MIN_COUNT
    )
    if not confirmed:
        return None
    prefix = head[: trailing.start()]
    suffix = tail[leading.end() :]
    return f"{prefix}{merged_word}{suffix}"


def _seam_markers_reopen(line: str, head: str, next_line: str, tail: str) -> bool:
    """True when the markers stepped over at the seam close and reopen one run.

    The join drops them. A marker on one side alone starts or ends a run, and
    dropping it would unbalance the paragraph. The reopening mirrors the close.
    """
    closing = line.rstrip()[len(head) :]
    rest = next_line.lstrip()
    opening = rest[: len(rest) - len(tail)]
    return closing[::-1] == opening


def _hyphenated_spelling_count(seg_list: list[Segment], frag1: str, frag2: str) -> int:
    """Count of `frag1-frag2` spelled out literally, same-line, in the plain body."""
    pattern = re.compile(rf"\b{re.escape(frag1)}-{re.escape(frag2)}\b", re.IGNORECASE)
    return sum(
        len(pattern.findall(line)) for line, protected in seg_list if not protected
    )


def demark_seam_end(line: str) -> str:
    """`line.rstrip()` with a trailing run of emphasis markers stepped over.

    `word-**` reads as `word-`. Markers inside code or math stay.
    """
    stripped = line.rstrip()
    if not stripped.endswith(("*", "_")):
        return stripped
    mask = mask_math(mask_inline_code(stripped))
    end = len(stripped)
    while end and mask[end - 1] in _SEAM_MARKERS:
        end -= 1
    return stripped[:end]


def demark_seam_start(line: str) -> str:
    """`line.lstrip()` with a leading run of emphasis markers stepped over.

    `**site` reads as `site`. Markers inside code or math stay.
    """
    rest = line.lstrip()
    if not rest.startswith(("*", "_")):
        return rest
    mask = mask_math(mask_inline_code(rest))
    start = 0
    while start < len(rest) and mask[start] in _SEAM_MARKERS:
        start += 1
    return rest[start:]


# ---- flattened paragraphs ---------------------------------------------------

_SEAM_WORD_RE = re.compile(r"\w+")

# One repeated word is an ordinary continuation ("of the" / "the same"); a
# phrase on both sides of the seam is a fragment emitted twice.
_SEAM_REPEAT_MIN_WORDS = 2

# A re-emitted copy sits at the seam; further out, a technical text repeats
# itself anyway.
_SEAM_REPEAT_MAX_WORDS = 8


def join_flattened_paragraphs(seg_list: list[Segment]) -> list[Segment]:
    """Join a paragraph a narrow column crushed into blank-separated fragments.

    Only inside a run that `flattened_paragraph_runs` attests, and per pair:
    a block that carries on the one before it joins it, and an entry opening
    with its own key stays apart. Known gap: a list whose entries all open in
    lowercase and end without punctuation reads as one clause. A fragment
    ending in a hyphen needs the attestation the rejoin did not find. A
    fragment repeating the words before the seam was emitted twice; joining
    would write the repetition into the body.
    """
    seams = _paragraph_seams(seg_list)
    if not seams:
        return seg_list
    out: list[Segment] = []
    for idx, (line, protected) in enumerate(seg_list):
        if idx not in seams:
            out.append((line, protected))
            continue
        while out and not out[-1][0].strip():
            out.pop()
        previous, _ = out.pop()
        out.append((f"{previous.rstrip()} {line.lstrip()}", False))
    _logger.info("flattened paragraphs joined: %d blocks", len(seams))
    return out


def _paragraph_seams(seg_list: list[Segment]) -> set[int]:
    """Line indices opening a block that joins onto the block before it.

    Each fragment is judged against the block the joins so far have built.
    """
    seams: set[int] = set()
    for run in flattened_paragraph_runs(seg_list):
        previous = block_content_lines(seg_list, *run[0])
        for start, end in run[1:]:
            following = block_content_lines(seg_list, start, end)
            if _joins_onto(previous, following):
                seams.add(start)
                previous = [
                    *previous[:-1],
                    f"{previous[-1].rstrip()} {following[0].lstrip()}",
                    *following[1:],
                ]
                continue
            previous = following
    return seams


def _joins_onto(previous: list[str], following: list[str]) -> bool:
    """True when `following` is the rest of a clause `previous` broke off."""
    if not block_continues(previous, following):
        return False
    if previous[-1].rstrip().endswith("-"):
        return False
    return not _repeats_at_the_seam(previous[-1], following[0])


def _repeats_at_the_seam(tail: str, head: str) -> bool:
    """True when the two sides of a join spell the same words twice over."""
    before = [word.casefold() for word in _SEAM_WORD_RE.findall(tail)]
    after = [word.casefold() for word in _SEAM_WORD_RE.findall(head)]
    before = before[-_SEAM_REPEAT_MAX_WORDS:]
    after = after[:_SEAM_REPEAT_MAX_WORDS]
    return any(
        before[-count:] == after[:count]
        for count in range(_SEAM_REPEAT_MIN_WORDS, min(len(before), len(after)) + 1)
    )


# ---- letter-spaced runs -----------------------------------------------------

# Not `\w`: a digit or an underscore is never spaced out for emphasis.
_SPACED_LETTER = r"[^\W\d_]"

# Emphasis by letter spacing, one space apart. The run ends at a letter
# boundary, so a longer group beside it (`ec` in `p r o b a b i l ec t y`) is
# not one of its letters. Punctuation closes the run.
_SPACED_RUN_RE = re.compile(
    rf"(?<!{_SPACED_LETTER})"
    rf"({_SPACED_LETTER}(?: {_SPACED_LETTER})+)"
    rf"(?!{_SPACED_LETTER})"
)

# The group exactly one space off either end, a part of the word that
# recognition kept together.
_SPACED_NEIGHBOUR_BEFORE_RE = re.compile(rf"{_SPACED_LETTER}+ \Z")
_SPACED_NEIGHBOUR_AFTER_RE = re.compile(rf" {_SPACED_LETTER}+")

# Two letters are a pair of one-letter words far more often than emphasis.
_SPACED_MIN_LETTERS = 3

# A single letter as its own word, bounded as a run's letters are.
_SOLO_LETTER_RE = re.compile(
    rf"(?<!{_SPACED_LETTER}){_SPACED_LETTER}(?!{_SPACED_LETTER})"
)

# Blanked before counting: the `cup` of `\cup` is no symbol.
_MATH_COMMAND_RE = re.compile(r"\\[A-Za-z]+|\\.")

# A one-letter function word stands in prose by the hundred and hardly ever
# in math; a symbol named in prose ("the axis x") stands in math as often.
# Measured over fourteen bodies, the sides differ by an order of magnitude.
_SPACING_WORD_MIN = 20
_SPACING_WORD_MATH_RATIO = 5

# Same order as the word bar: one occurrence is a recognition slip.
_SPACING_SYMBOL_MIN = 20

# One occurrence is usually the same defect on another page. Price: a name
# the document spells once stays spaced.
_SPACED_WITNESS_MIN = 2


def join_letter_spaced_runs(seg_list: list[Segment]) -> list[Segment]:
    """Join a run of letter-spaced single letters back into its own word.

    The shape alone does not say where the word ends, so the run is joined
    only into a spelling the body uses. The group one space off either end is
    offered too, and the longest attested reading wins. Headings are left to
    the heading rules.
    """
    prose = prose_reading(seg_list)
    counts = body_word_counts(prose)
    out: list[Segment] = []
    joined = 0
    for (line, protected), text in zip(seg_list, prose, strict=True):
        if text is None or ATX_HEADING_RE.match(text):
            out.append((line, protected))
            continue
        fixed, count = _join_spaced_line(line, text, counts)
        joined += count
        out.append((fixed, protected))
    if joined:
        # A joined run carries no mark, so the log is the only record.
        _logger.info("letter-spaced runs joined: %d", joined)
    return out


def _join_spaced_line(line: str, prose: str, counts: Counter[str]) -> tuple[str, int]:
    """`line` with every attested letter-spaced run joined, and how many joined.

    A mask blanks spans of at least three characters, so the single spaces of
    a run are the line's own.
    """
    edits: list[tuple[int, int, str]] = []
    for match in _spaced_run_matches(prose):
        span = _attested_word_span(prose, match, counts)
        if span is None:
            continue
        start, end = span
        # A group between two runs is offered to both; the left run has it.
        if edits and start < edits[-1][1]:
            continue
        edits.append((start, end, prose[start:end].replace(" ", "")))
    for start, end, word in reversed(edits):
        line = f"{line[:start]}{word}{line[end:]}"
    return line, len(edits)


def _attested_word_span(
    prose: str, run: re.Match[str], counts: Counter[str]
) -> tuple[int, int] | None:
    """The widest span around `run` the body spells as one word, or None.

    A neighbour group that the body uses as a word of its own is not offered:
    two real words can weld into a third that the body also spells.
    """
    left = _fragment_before(prose, run.start(), counts)
    right = _fragment_after(prose, run.end(), counts)
    spans = [(run.start(), run.end())]
    if left is not None:
        spans.append((left, run.end()))
    if right is not None:
        spans.append((run.start(), right))
    if left is not None and right is not None:
        spans.append((left, right))
    for start, end in sorted(spans, key=lambda span: span[0] - span[1]):
        word = prose[start:end].replace(" ", "")
        if counts[word.casefold()] >= _SPACED_WITNESS_MIN:
            return start, end
    return None


def _fragment_before(prose: str, start: int, counts: Counter[str]) -> int | None:
    """Where the group one space before `start` begins, when it is a fragment."""
    match = _SPACED_NEIGHBOUR_BEFORE_RE.search(prose[:start])
    if match is None or _is_a_word(match.group(), counts):
        return None
    return match.start()


def _fragment_after(prose: str, end: int, counts: Counter[str]) -> int | None:
    """Where the group one space after `end` ends, when it is a fragment."""
    match = _SPACED_NEIGHBOUR_AFTER_RE.match(prose, end)
    if match is None or _is_a_word(match.group(), counts):
        return None
    return match.end()


def _is_a_word(group: str, counts: Counter[str]) -> bool:
    """True when the body spells `group` as a word somewhere else of its own."""
    return counts[group.strip().casefold()] >= _SPACED_WITNESS_MIN


def _spaced_run_matches(prose: str) -> list[re.Match[str]]:
    """Every run of single letters long enough for either rule to read it."""
    return [
        match
        for match in _SPACED_RUN_RE.finditer(prose)
        if len(match.group().replace(" ", "")) >= _SPACED_MIN_LETTERS
    ]


@dataclass(frozen=True)
class SpacingWitness:
    """What the body says a single letter is: its own word, or a math symbol.

    Not complements: a letter may be in neither, and one written both ways
    is a symbol only.
    """

    words: frozenset[str]
    symbols: frozenset[str]

    def is_word(self, letter: str) -> bool:
        """True when the body writes `letter` as a word of its own language."""
        return letter.casefold() in self.words

    def is_symbol(self, letter: str) -> bool:
        """True when the body writes `letter` inside its own formulas."""
        return letter.casefold() in self.symbols


def spacing_witness(seg_list: list[Segment]) -> SpacingWitness:
    """Which single letters the body uses as words and which as math symbols.

    No word list can say: a letter is a conjunction in one document and a
    variable in the next. Letters of spaced runs are left out of the prose
    tally, or a spaced body would attest its whole alphabet.
    """
    words: Counter[str] = Counter()
    for text in prose_reading(seg_list):
        if text is None:
            continue
        runs = [match.span() for match in _spaced_run_matches(text)]
        words.update(
            match.group().casefold()
            for match in _SOLO_LETTER_RE.finditer(text)
            if not any(start <= match.start() < end for start, end in runs)
        )
    symbols: Counter[str] = Counter()
    for line, protected in seg_list:
        if protected:
            continue
        for span in math_spans(line):
            content = _MATH_COMMAND_RE.sub(" ", math_span_content(span))
            symbols.update(
                match.group().casefold() for match in _SOLO_LETTER_RE.finditer(content)
            )
    return SpacingWitness(
        frozenset(
            letter
            for letter, count in words.items()
            if count >= _SPACING_WORD_MIN
            and symbols[letter] * _SPACING_WORD_MATH_RATIO <= count
        ),
        frozenset(
            letter for letter, count in symbols.items() if count >= _SPACING_SYMBOL_MIN
        ),
    )


@dataclass(frozen=True)
class LetterSpacedRun:
    """One run of letters spaced apart, as the text and the spaces of a repair.

    `start` and `end` bound what a repair may rewrite, widened over the group
    at either end. `core` spaces sit between the run's own letters and close
    all together or not at all. `edge` spaces belong to the word only where it
    runs on into the group beside it, which only a reader can settle.
    """

    start: int
    end: int
    core: frozenset[int]
    edge: frozenset[int]


def letter_spaced_runs(prose: str, witness: SpacingWitness) -> list[LetterSpacedRun]:
    """Every letter-spaced run of `prose`, as the spaces it may close.

    Unlike the join, the body is not asked whether the run spells a word: a
    run left in a cleaned body is one the body could not settle, for a reader
    to repair. Two symbols joined by a one-letter word are no run. A
    one-letter word at an end of a longer run makes its space an edge, and the
    widening stops there.
    """
    runs: list[LetterSpacedRun] = []
    for match in _spaced_run_matches(prose):
        letters = match.group()[::2]
        if _is_an_enumeration(letters, witness):
            continue
        start, end = match.span()
        core = {offset for offset in range(start, end) if prose[offset] == " "}
        edges: set[int] = set()
        if _stands_on_its_own(letters[0], letters, witness):
            edges.add(min(core))
            core.discard(min(core))
        else:
            before = _SPACED_NEIGHBOUR_BEFORE_RE.search(prose[:start])
            if before is not None:
                edges.add(start - 1)
                start = before.start()
        if _stands_on_its_own(letters[-1], letters, witness):
            edges.add(max(core))
            core.discard(max(core))
        else:
            after = _SPACED_NEIGHBOUR_AFTER_RE.match(prose, end)
            if after is not None:
                edges.add(end)
                end = after.end()
        runs.append(LetterSpacedRun(start, end, frozenset(core), frozenset(edges)))
    return runs


def _is_an_enumeration(letters: str, witness: SpacingWitness) -> bool:
    """True when the run is two of the body's symbols joined by its own word."""
    return (
        len(letters) == 3
        and witness.is_word(letters[1])
        and witness.is_symbol(letters[0])
        and witness.is_symbol(letters[2])
    )


def _stands_on_its_own(letter: str, letters: str, witness: SpacingWitness) -> bool:
    """True when the letter at an end of `letters` may be a word of its own.

    A run of three is too short to tell its end from a word beside it.
    """
    return len(letters) > _SPACED_MIN_LETTERS and witness.is_word(letter)


# ---- compound hyphen --------------------------------------------------------

# Three to one; below that the document has no convention. It also floors
# the winning side at three occurrences.
_COMPOUND_MAJORITY_RATIO = 3


def settle_compound_hyphens(seg_list: list[Segment]) -> list[Segment]:
    """Settle a compound's hyphen mid-line by the spelling the body attests.

    A lost hyphen (`costeffective`) and a stray mid-line break (`continu-ation`)
    are both ordinary spellings. Each broken spelling is counted against its
    joined one, and a `_COMPOUND_MAJORITY_RATIO` majority settles the word
    either way. Prose only. A digit marks a code (`S7-200`); a joined spelling
    that two breaks claim attests nothing. The vote is case-blind, so each
    rewrite, with its own case, must be a spelling the body holds literally.
    """
    prose = prose_reading(seg_list)
    hyphenated: Counter[str] = Counter()
    joined: Counter[str] = Counter()
    literal_forms: set[str] = set()
    for text in prose:
        if text is None:
            continue
        hyphenated.update(hyphen_forms(text))
        joined.update(tokenize(text))
        literal_forms.update(_literal_word_forms(text))
    restore, drop = _compound_decisions(hyphenated, joined)
    if not restore and not drop:
        return seg_list
    out: list[Segment] = []
    restored = removed = 0
    for (line, protected), text in zip(seg_list, prose, strict=True):
        if text is None:
            out.append((line, protected))
            continue
        fixed, line_restored, line_removed = _settle_line(
            line, text, restore, drop, literal_forms
        )
        restored += line_restored
        removed += line_removed
        out.append((fixed, protected))
    if restored or removed:
        # A settled word carries no mark, so the log is the only record.
        _logger.info(
            "compound hyphens settled: %d restored, %d dropped", restored, removed
        )
    return out


def _compound_decisions(
    hyphenated: Counter[str], joined: Counter[str]
) -> tuple[dict[str, tuple[str, str, str]], frozenset[str]]:
    """Joined spellings to break, mapped to their halves, and spellings to join."""
    spellings: dict[str, dict[str, tuple[str, str, str]]] = {}
    for form in hyphenated:
        parts = _compound_parts(form)
        if parts is None:
            continue
        left, _, right = parts
        if any(ch.isdigit() for ch in left) or any(ch.isdigit() for ch in right):
            continue
        spellings.setdefault(left + right, {})[form] = parts
    restore: dict[str, tuple[str, str, str]] = {}
    drop: set[str] = set()
    for word, forms in spellings.items():
        if len(forms) != 1:
            continue
        form, parts = next(iter(forms.items()))
        breaks = hyphenated[form]
        plain = joined[word]
        if plain >= _COMPOUND_MAJORITY_RATIO * breaks:
            drop.add(form)
        elif plain and breaks >= _COMPOUND_MAJORITY_RATIO * plain:
            restore[word] = parts
    return restore, frozenset(drop)


def _compound_parts(form: str) -> tuple[str, str, str] | None:
    """The two halves of `form` and the break between them, or None.

    None for a chain of breaks (`state-of-the-art`).
    """
    runs = list(WORD_RUN_RE.finditer(form))
    if len(runs) != 2:
        return None
    return form[: runs[0].end()], form[runs[0].end() : runs[1].start()], runs[1].group()


def _literal_word_forms(text: str) -> set[str]:
    """Every spelling `text` carries verbatim: NFKC-folded, case kept.

    Hyphenated compounds and bare word runs outside them, read as the vote
    reads them.
    """
    forms: set[str] = set()
    broken_spans: list[tuple[int, int]] = []
    for match in BROKEN_WORD_RE.finditer(text):
        forms.add(unicodedata.normalize("NFKC", match.group()))
        broken_spans.append(match.span())
    for match in WORD_RUN_RE.finditer(text):
        if any(start <= match.start() < end for start, end in broken_spans):
            continue
        forms.add(unicodedata.normalize("NFKC", match.group()))
    return forms


def _settle_line(
    line: str,
    prose: str,
    restore: dict[str, tuple[str, str, str]],
    drop: frozenset[str],
    literal_forms: set[str],
) -> tuple[str, int, int]:
    """`line` with its settled compounds rewritten, and the count of each side."""
    edits: list[tuple[int, int, str]] = []
    restored = removed = 0
    broken: list[tuple[int, int]] = []
    for match in BROKEN_WORD_RE.finditer(prose):
        broken.append((match.start(), match.end()))
        if hyphen_forms(match.group())[0] not in drop:
            continue
        word = line[match.start() : match.end()]
        joined_word = "".join(WORD_RUN_RE.findall(word))
        if unicodedata.normalize("NFKC", joined_word) not in literal_forms:
            continue
        edits.append((match.start(), match.end(), joined_word))
        removed += 1
    for match in WORD_RUN_RE.finditer(prose):
        # A half of a broken word is not a joined spelling.
        if any(start <= match.start() < end for start, end in broken):
            continue
        tokens = tokenize(match.group())
        if len(tokens) != 1:
            continue
        parts = restore.get(tokens[0])
        if parts is None:
            continue
        broken_form = _break_word(line[match.start() : match.end()], parts)
        if broken_form is None:
            continue
        if unicodedata.normalize("NFKC", broken_form) not in literal_forms:
            continue
        edits.append((match.start(), match.end(), broken_form))
        restored += 1
    for start, end, text in sorted(edits, reverse=True):
        line = f"{line[:start]}{text}{line[end:]}"
    return line, restored, removed


def _break_word(word: str, parts: tuple[str, str, str]) -> str | None:
    """`word` with the break of `parts` put back between its halves, or None.

    The split point is searched, not counted: a ligature normalizes to a
    different length.
    """
    left, brk, right = parts
    positions = [
        index
        for index in range(1, len(word))
        if tokenize(word[:index]) == [left] and tokenize(word[index:]) == [right]
    ]
    if len(positions) != 1:
        return None
    return f"{word[: positions[0]]}{brk}{word[positions[0] :]}"


# ---- whole-paragraph emphasis ---------------------------------------------

# Indent, core, trailing whitespace; matches any line.
_PARAGRAPH_CORE_RE = re.compile(r"^( {0,3})(.*?)([ \t]*)$")

# Non-greedy, so several runs on a line match one by one.
_BOLD_RUN_RE = re.compile(r"(\*\*|__)(.+?)\1")

# Read for coverage only. `*` may sit mid-word, as a scan sets a unit apart;
# `_` needs a word boundary, since `a_b` is a token.
_ITALIC_RUN_RE = re.compile(
    r"\*(?!\s)[^*]+?(?<!\s)\*|(?<!\w)_(?!\s)[^_]+?(?<!\s)_(?!\w)"
)

# An abbreviation before a capital ("Fig. 5") also counts; that only raises
# the tally, which the strip tolerates.
_SENTENCE_BREAK_RE = re.compile(rf"[.!?][\"')\]»”]?\s+(?=[A-Z{CYRILLIC_UPPER}])")

_SENTENCE_CLOSERS = "\"')]»”"

# A caption, a note, or a callout falls well short; a body paragraph clears
# it easily.
_WHOLE_PARAGRAPH_EMPHASIS_MIN_CHARS = 120

# A caption has none, one bold statement has one.
_WHOLE_PARAGRAPH_EMPHASIS_MIN_SENTENCES = 2

# Bounds on the unmarked prose outside every emphasis run. A real bold
# phrase inside prose fails both.
_WHOLE_PARAGRAPH_EMPHASIS_MIN_COVERAGE = 0.9
_WHOLE_PARAGRAPH_EMPHASIS_MAX_ISLAND = 32


def drop_paragraph_emphasis(seg_list: list[Segment]) -> list[Segment]:
    """Drop a bold run that wraps a whole body paragraph.

    Heavy type reads as bold, and a wrap around a paragraph drowns out real
    emphasis. The wrap may be broken by an italic island (a unit set in
    italics), which counts as covered; only the bold markers go. The paragraph
    must stand alone and clear the length and sentence floors, which keep a
    caption (`**Fig. VII.108**`) or a note out. Headings are skipped.
    """
    out: list[Segment] = []
    dropped = 0
    for idx, (line, protected) in enumerate(seg_list):
        if protected or ATX_HEADING_RE.match(line) or not is_standalone(seg_list, idx):
            out.append((line, protected))
            continue
        fixed = _strip_whole_paragraph_emphasis(line)
        if fixed != line:
            dropped += 1
        out.append((fixed, protected))
    if dropped:
        # A stripped paragraph carries no mark, so the log is the only record.
        _logger.info("whole-paragraph emphasis dropped: %d", dropped)
    return out


def _emphasis_coverage(masked: str, bold_runs: list[re.Match[str]]) -> int:
    """Characters of the core that carry emphasis of any kind, bold or italic.

    Bold runs are blanked before the italic search, so a `*` of a `**` pair
    is never an italic end.
    """
    covered = bytearray(len(masked))
    for run in bold_runs:
        covered[run.start() : run.end()] = b"\x01" * (run.end() - run.start())
    gaps = "".join(
        " " if flag else ch for ch, flag in zip(masked, covered, strict=True)
    )
    for run in _ITALIC_RUN_RE.finditer(gaps):
        covered[run.start() : run.end()] = b"\x01" * (run.end() - run.start())
    return sum(covered)


def _strip_whole_paragraph_emphasis(line: str) -> str:
    """`line` with a whole-paragraph bold wrap removed, or `line` unchanged."""
    match = _PARAGRAPH_CORE_RE.match(line)
    if match is None:  # unreachable: the pattern matches any line
        return line
    indent, core, trailing = match.groups()
    # A `**` quoted in a code span is shown, not worn; the mask keeps offsets.
    masked = mask_inline_code(core)
    runs = list(_BOLD_RUN_RE.finditer(masked))
    if not runs:
        return line
    covered = _emphasis_coverage(masked, runs)
    if covered < _WHOLE_PARAGRAPH_EMPHASIS_MIN_COVERAGE * len(core):
        return line
    if len(core) - covered > _WHOLE_PARAGRAPH_EMPHASIS_MAX_ISLAND:
        return line
    demarked = core
    demarked_mask = masked
    for run in reversed(runs):
        inner = core[run.start(2) : run.end(2)]
        demarked = f"{demarked[: run.start()]}{inner}{demarked[run.end() :]}"
        inner_mask = masked[run.start(2) : run.end(2)]
        demarked_mask = (
            f"{demarked_mask[: run.start()]}{inner_mask}{demarked_mask[run.end() :]}"
        )
    if "**" in demarked_mask or "__" in demarked_mask:
        # An unpaired marker: not a clean wrap.
        return line
    if not any(ch.isalpha() for ch in demarked):
        return line
    if len(demarked) < _WHOLE_PARAGRAPH_EMPHASIS_MIN_CHARS:
        return line
    if _sentence_count(demarked) < _WHOLE_PARAGRAPH_EMPHASIS_MIN_SENTENCES:
        return line
    return f"{indent}{demarked}{trailing}"


def _sentence_count(text: str) -> int:
    """How many sentences `text` reads as: interior breaks plus a closed tail."""
    interior = len(_SENTENCE_BREAK_RE.findall(text))
    closed = text.rstrip().rstrip(_SENTENCE_CLOSERS).endswith((".", "!", "?"))
    return interior + int(closed)


def collapse_blanks(seg_list: list[Segment]) -> str:
    """Collapse blank-line runs to one and trim leading/trailing blanks.

    Blank lines inside a protected zone stay. The result ends with a newline.
    """
    out: list[str] = []
    pending_blank = False
    seen_content = False
    for line, protected in seg_list:
        if not protected and not line.strip():
            if seen_content:
                pending_blank = True
            continue
        if pending_blank:
            out.append("")
            pending_blank = False
        out.append(line)
        seen_content = True
    body = "\n".join(out)
    return f"{body}\n" if body else ""
