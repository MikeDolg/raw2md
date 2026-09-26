"""Rules that repair the heading structure a converter made of the source.

The coordinator runs them in this order: strip a whole-title emphasis wrap and
a leading ornament glyph, split a run-in heading from its paragraph, rebuild a
letter-spaced title, demote an oversize heading, drop a running header
restated as a heading, take levels from the source outline or the printed
contents, level by numbering depth and recover headings lost to plain text,
nest unnumbered headings under their section, level repeats and numbered
series to one level, and close the gaps in the ladder. Two detectors only
report: an oversize recovered heading and a run-in heading the strict split
declines.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from raw2md.cleaning.segments import (
    CYRILLIC_LOWER,
    CYRILLIC_UPPER,
    LIST_ITEM_RE,
    body_word_counts,
    is_standalone,
    is_standalone_span,
    prev_content_index,
    prose_reading,
)
from raw2md.header import ConversionMethod
from raw2md.keywords import Keywords, word_pattern
from raw2md.mdtext.lines import ATX_HEADING_RE, is_setext_underline, is_table_separator
from raw2md.mdtext.tables import CELL_BREAK_RE, CELL_SEPARATOR_RE, table_cells
from raw2md.mdtext.zones import Segment
from raw2md.source_outline import SourceOutline
from raw2md.source_text import tokenize

# The lookahead keeps a run-on like `4.1.3Foo` from reading as a section number.
_HEADING_NUM_RE = re.compile(r"^( {0,3})(#{1,6})\s+(\d+(?:\.\d+)*)(?=\.?(?:\s|$))")

# A plain line opening with a multi-level section number: `6.1.3.1 Scope`. A
# single-level number is not accepted: prose opens that way too often.
_LOST_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)+)\.?[ \t]+(\S.*)$")

# ATX stops at six levels, so a numbering depth can never map past it.
_MAX_HEADING_LEVEL = 6

# A section word written as a stem must not run into a lowercase word:
# `Appendix materials` merely opens with it. A word written in full needs no
# such guard.
_TOP_LEVEL_STEM_GUARD = rf"(?![ \t]*[a-z{CYRILLIC_LOWER}])"

# Longest a heading candidate may run, in characters, and still read as a title
# a human wrote. Past it an ATX heading is demoted, nesting skips it, and
# recovery does not promote it.
_HEADING_MAX_LENGTH = 200

# The bold lead of a demoted oversize heading with prose glued on after it.
# Lazy, so the wrap closes at its first marker; a wrap that reaches the line end
# is a long bold title and does not match.
_OVERSIZE_HEADING_LEAD_RE = re.compile(r"^(\*\*|__)(.+?)\1[ \t]+(\S.*)$")

# A numbered heading that runs into its paragraph:
# `#### 3.1 Load Cases. The first case applies...`. Groups:
# marker and number, a Title Case title, the tail. A period glued onto a word
# (`Mr.`) ends the title run, so the split lands on the first period after a
# title word.
_RUN_IN_HEADING_RE = re.compile(
    r"^( {0,3}#{1,6}[ \t]+\d+(?:\.\d+)*\.?[ \t]+)"
    rf"([A-Z{CYRILLIC_UPPER}][^\s.]*(?:[ \t]+[A-Z{CYRILLIC_UPPER}][^\s.]*)*)"
    r"\.[ \t]+"
    rf"([A-Z{CYRILLIC_UPPER}].*)$"
)

# Longest a run-in title may run, in characters; a longer Title Case run is a
# title of its own.
_RUN_IN_TITLE_MAX_LENGTH = 60

# Shortest the title's last word may be: an abbreviation (`Dr.`, `Fig.`,
# `Vol.`) is shorter, and would otherwise take the split.
_RUN_IN_LAST_WORD_MIN_LENGTH = 4

# `_RUN_IN_HEADING_RE` without the capital on interior title words
# (`Design for Thermal Loads`); `_is_run_in_title_word` checks each
# word once the match succeeds.
_RUN_IN_HEADING_LOOSE_RE = re.compile(
    r"^( {0,3}#{1,6}[ \t]+\d+(?:\.\d+)*\.?[ \t]+)"
    rf"([A-Z{CYRILLIC_UPPER}][^\s.]*(?:[ \t]+[^\s.]+)*?)"
    r"\.[ \t]+"
    rf"([A-Z{CYRILLIC_UPPER}].*)$"
)

# An ATX heading whose whole text is one emphasis run. `.+` is greedy, so a
# partial run does not match, and two separate runs leave the marker inside the
# capture, which the caller rejects.
_HEADING_EMPHASIS_RE = re.compile(r"^( {0,3}#{1,6}\s+)(\*\*|__|\*|_)(.+)\2$")

# A glyph run between a heading's marker and its number (`## • 1.2 Foo`).
# `_is_heading_ornament` decides whether the run is an ornament.
_HEADING_GLYPH_RE = re.compile(r"^( {0,3}#{1,6}[ \t]+)([^\w\s]+)[ \t]*(?=\d)")

# No hyphen: in front of a number it is a sign far more often than a bullet.
_HEADING_BULLET_GLYPHS = frozenset("•·‣∙")

# Unicode blocks of pictographs. Blocks rather than the `So` category, which
# also holds marks that state a number or a measure (`№ 5`, `⌀ 20 mm`, `℃`).
_HEADING_ORNAMENT_BLOCKS = (
    (0x25A0, 0x25FF),
    (0x2600, 0x26FF),
    (0x2700, 0x27BF),
    (0x2B00, 0x2BFF),
    (0x1F000, 0x1FAFF),
)

# A paragraph whose whole text is one bold run: `**1.2. Foo**`. Greedy like
# `_HEADING_EMPHASIS_RE`. Italics are not a convention recovery relies on.
_WRAPPED_PARAGRAPH_RE = re.compile(r"^ {0,3}(\*\*|__)(.+)\1[ \t]*$")

# Two runs of one marker with only whitespace between them: a run Word split.
# The whitespace is kept, since without a lexicon a mid-word split and a word
# boundary look the same.
_ADJACENT_EMPHASIS_RE = re.compile(r"(\*\*|__)(.+?)\1([ \t]+)\1(.+?)\1")

# pandoc's hard line break; a doubled backslash is an escaped literal.
_HARD_BREAK_RE = re.compile(r"(?<!\\)\\\Z")

# An ATX heading with indent and marker captured, to rewrite the `#` count.
_ATX_LEVEL_RE = re.compile(r"^( {0,3})(#{1,6})(?=\s|$)")

# How many consecutive siblings make a ladder. Two numbers in a row turn up by
# chance; three, each its own paragraph under the same wrap, do not.
_LADDER_MIN = 3

# Heading recovery runs on text-converter routes only: on a recognized page an
# all-caps line is as likely a running head or OCR debris. An allow list, so an
# unknown route is closed.
_HEADING_RECOVERY_METHODS = frozenset({ConversionMethod.PANDOC, ConversionMethod.CLEAN})

# All-caps paragraphs that prove the convention; one or two are emphasis.
_CAPS_SEED_MIN = 3

# All-caps sections carry no depth; level 1 is left to the document's title.
_CAPS_HEADING_LEVEL = 2

# Longest all-caps paragraph that reads as a title, in characters; it clears
# long multi-clause section titles, and a capitalized prose paragraph runs past.
_CAPS_MAX_LENGTH = 150

# A strictly formed upper-case roman numeral. An all-roman word (`MIX`) still
# passes; the class bars below keep such a one-off out.
_ROMAN_NUMERAL = (
    r"(?=[IVXLCDM])M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
)

# A heading opening with a word prefix and a bare serial number: the shape of a
# document's own series (`LECTURE 6`, `Chapter II`). A bare number needs a space
# before it and no letter or further digit group after it, which keeps out an
# article code (`RSK6`, `Model 100A`) and a dotted number, whose depth the
# numbering rule settles.
_HEADING_CLASS_RE = re.compile(
    rf"^([^\W\d_][^\d]*?)[ \t]+(\d+|{_ROMAN_NUMERAL})(?![^\W_]|[.,\s]\d)"
)

# The same class with the section sign as its whole name: `§ 12`.
_SECTION_CLASS_RE = re.compile(r"^(§)[ \t]*(\d+)(?![^\W_]|[.,\s]\d)")

# Members that prove a class: two headings sharing a first word and a number
# turn up by chance, three are a series.
_HEADING_CLASS_MIN_SIZE = 3

# Share of the outline the body must print as headings before the outline is
# read as its skeleton. Documents with a real outline print 0.72 to 0.80 of its
# titles; accidental matches stay far below half.
_OUTLINE_SKELETON_MIN_SHARE = 0.5

# ...and at least this many titles: one or two matches are a coincidence.
_OUTLINE_SKELETON_MIN_TITLES = 3

# A leading section number (`1.2`) or roman folio (`II`), with an optional
# trailing dot, that a contents heading carries ahead of its word.
_CONTENTS_TITLE_NUMBER_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*"
    r"|m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3}))\.?\s+",
    re.IGNORECASE,
)

# The head of a crushed contents line: the label ends at the first mark the page
# punctuated it off with. A section merely named after the word follows it with
# a space, not a mark.
_CONTENTS_TITLE_HEAD_RE = re.compile(r"^(.+?)[.:;][ \t]+\S")

# How many spaced-out single characters read as one letter-spaced word rather
# than an initialism. Same floor the spaced-title rebuild keeps.
_CONTENTS_SPACED_MIN_LETTERS = 3

# A page cell: a number, a chapter-page pair (`2-16`), or a roman folio. The
# body heading does not print it, so it must not reach the title.
_CONTENTS_PAGE_RE = re.compile(
    r"^(?:\d+(?:[-–]\d+)?|[ivxlcdm]+)$",  # noqa: RUF001 -- printed en dash
    re.IGNORECASE,
)

# The dot leader a typesetter runs between an entry's title and its page. Two
# leader characters at the least, so a single dot -- the one that closes a
# section number, `1.1` -- is left where it stands.
_CONTENTS_LEADER_RE = re.compile(r"(?:[.·•…_][ 	]*){2,}")

# Longest contents entry, in characters; past it the converter crushed a column
# of entries into one cell.
_CONTENTS_ENTRY_MAX_LENGTH = 200

# The number ahead of a contents title. A dotted number states its rank; a
# single-level one is judged over the zone (`_record_rank`).
_CONTENTS_ENTRY_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?(?=\s)")

# A cell holding only a rank word (`Chapter`, `Cap.`); the page split it from
# its number in the next cell.
_CONTENTS_RANK_WORD_RE = re.compile(r"^[^\W\d_][^\d]*$")

# The number in the cell after a rank word, arabic or roman.
_CONTENTS_RANK_NUMBER_RE = re.compile(rf"^(\d+|{_ROMAN_NUMERAL})\.?$")

# Distinct grid depths a contents table needs to state a hierarchy; one depth
# would flatten that stretch. Records ranked by their own number are exempt.
_CONTENTS_MIN_DEPTHS = 2

# Shallowest numbering depth that may anchor the depth-to-level map. A
# single-level number names no parent, and a catalogue page prints many that
# name no section (`2-248`, `Fig. 5.4`).
_NUMBER_ANCHOR_MIN_DEPTH = 2

# Headings a depth needs to anchor the map: three are a habit, two a chance.
_NUMBER_ANCHOR_MIN_HEADINGS = 3

# Distinct numbers a class needs: one number repeated is no series.
_HEADING_CLASS_MIN_NUMBERS = 2

# Class members that must open a dotted number of the body before that
# numbering ranks the class. One can do so by coincidence: a caption
# `Figure 12` beside sections numbered `12.3`.
_HEADING_STEM_MIN_MEMBERS = 3

# Share of a numbered group on one level that outweighs its members' ancestors.
# Strictly past two thirds: a document's own series carries more (91 of 129),
# while a split that a differing ancestor explains stays below.
_ANCHORED_VOTE_MAJORITY = Fraction(2, 3)

# Smallest numbered group that can outvote a dissenter: two of three is not
# past two thirds.
_ANCHORED_VOTE_MIN_SIZE = 4

# Copies of an unnumbered title that rank it by their own mode, with no share
# required: the ancestors of its copies state nothing about it. Observed bodies
# scatter such titles over two to four levels, below the share above (84 of
# 149, 19 of 86).
_REPEATED_TITLE_MIN_COPIES = 3


def strip_heading_emphasis(seg_list: list[Segment]) -> list[Segment]:
    """Strip emphasis that wraps an ATX heading's whole text, outside protected zones.

    The wrap hides a numbered heading's digits from `_HEADING_NUM_RE`, so this
    runs before numbering. A partial or double run keeps its markup.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, True))
            continue
        out.append((_strip_whole_heading_emphasis(line), False))
    return out


def _strip_whole_heading_emphasis(line: str) -> str:
    m = _HEADING_EMPHASIS_RE.match(line)
    if m is None:
        return line
    prefix, marker, inner = m.group(1), m.group(2), m.group(3)
    if marker in inner:
        return line
    return f"{prefix}{inner}"


def _is_heading_ornament(ch: str) -> bool:
    """True for a printed bullet or a pictograph.

    Any other non-word character carries meaning a strip would lose: it opens an
    inline span, signs or encloses the number, or states a rank of its own.
    """
    if ch in _HEADING_BULLET_GLYPHS:
        return True
    point = ord(ch)
    return any(low <= point <= high for low, high in _HEADING_ORNAMENT_BLOCKS)


def strip_heading_leading_glyphs(seg_list: list[Segment]) -> list[Segment]:
    """Strip ornament glyphs standing in front of a heading's own number.

    Recognition reads a printed ornament as part of the title, which hides the
    number from every rule that reads it. Only a run that a number follows and
    that is ornament throughout is stripped. Runs after the emphasis strip and
    before every level rule.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, True))
            continue
        m = _HEADING_GLYPH_RE.match(line)
        if m is None or not all(_is_heading_ornament(ch) for ch in m.group(2)):
            out.append((line, False))
            continue
        prefix = m.group(1)
        out.append((f"{prefix}{line[m.end() :]}", False))
    return out


def strip_oversize_heading_markers(seg_list: list[Segment]) -> list[Segment]:
    """Demote a heading too long for a title to a paragraph, its text unchanged.

    A converter can mark a crushed table, form, or prose run as a heading, which
    then swallows everything down to the next heading, so this runs before every
    level rule. The length is measured on the title without markers, and a
    nested marker (`## # Foo`) goes too. A bold lead covering only the line's
    head is the crushed form's caption and becomes a paragraph of its own.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected or ATX_HEADING_RE.match(line) is None:
            out.append((line, protected))
            continue
        text = _heading_text(line)
        if len(text.strip()) <= _HEADING_MAX_LENGTH:
            out.append((line, protected))
            continue
        while ATX_HEADING_RE.match(text) is not None:
            text = _heading_text(text)
        split = _split_crushed_form_caption(text)
        if split is None:
            out.append((text, False))
            continue
        caption, body = split
        out.append((caption, False))
        out.append(("", False))
        out.append((body, False))
    return out


def _split_crushed_form_caption(text: str) -> tuple[str, str] | None:
    """The `(caption, body)` split of an oversize heading's bold lead, or None."""
    m = _OVERSIZE_HEADING_LEAD_RE.match(text)
    if m is None:
        return None
    marker, caption, body = m.group(1), m.group(2), m.group(3)
    return f"{marker}{caption}{marker}", body


# ---- letter-spaced titles ---------------------------------------------------

# A run of letters, the group a spaced-out title is broken into. A digit is not
# one: a heading's number is not part of the words its title spells.
_TITLE_LETTER_RUN_RE = re.compile(r"[^\W\d_]+")

# Minimum share of single-space gaps to letters in a spaced title. An ordinary
# title stays at a fifth or less; a spaced one has a gap after nearly every
# letter.
_SPACED_TITLE_MIN_GAP_SHARE = 0.5

# Groups a title and each spaced region need: two groups one space apart are
# usually two short words.
_SPACED_TITLE_MIN_GROUPS = 3

# Body spellings a rebuilt word needs. One is enough: the gap share already
# settled that the title is spaced, and the body only says where words end.
_SPACED_TITLE_WITNESS_MIN = 1


def join_letter_spaced_headings(seg_list: list[Segment]) -> list[Segment]:
    """Rebuild a title whose letters a typesetter spaced apart.

    Each spaced region splits into the fewest words the body attests, and only
    when that split is unique; otherwise the region stays as it is. Runs before
    every rule that compares titles, since a spaced title matches nothing but
    itself.
    """
    prose = prose_reading(seg_list)
    counts = body_word_counts(prose)
    out: list[Segment] = []
    for (line, protected), text in zip(seg_list, prose, strict=True):
        gaps = set() if text is None else _closable_title_gaps(text, counts)
        if not gaps:
            out.append((line, protected))
            continue
        out.append(
            ("".join(ch for i, ch in enumerate(line) if i not in gaps), protected)
        )
    return out


def _closable_title_gaps(masked: str, counts: Counter[str]) -> set[int]:
    """Offsets of the spaces to close in a spaced title; empty for a non-heading.

    `masked` is the prose reading of the line: a formula counts no letters or
    gaps, and the offsets still address the line.
    """
    marker = ATX_HEADING_RE.match(masked)
    if marker is None:
        return set()
    groups = [
        match.span() for match in _TITLE_LETTER_RUN_RE.finditer(masked, marker.end())
    ]
    if not _is_spaced_title(masked, groups):
        return set()
    gaps: set[int] = set()
    for region in _spaced_regions(masked, groups):
        if len(region) < _SPACED_TITLE_MIN_GROUPS:
            continue
        cuts = _fewest_words([masked[start:end] for start, end in region], counts)
        if cuts is None:
            continue
        for opening, closing in pairwise(cuts):
            gaps.update(end for _, end in region[opening : closing - 1])
    return gaps


def _is_spaced_title(masked: str, groups: list[tuple[int, int]]) -> bool:
    """True when the title's letters carry more spacing than words ever do."""
    if len(groups) < _SPACED_TITLE_MIN_GROUPS:
        return False
    letters = sum(end - start for start, end in groups)
    gaps = sum(
        1 for (_, end), (start, _) in pairwise(groups) if masked[end:start] == " "
    )
    return gaps >= letters * _SPACED_TITLE_MIN_GAP_SHARE


def _spaced_regions(
    masked: str, groups: list[tuple[int, int]]
) -> list[list[tuple[int, int]]]:
    """Maximal runs of groups exactly one space apart.

    Anything else between two groups ends a region, since a word never spans it.
    """
    regions: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    for span in groups:
        if current and masked[current[-1][1] : span[0]] == " ":
            current.append(span)
            continue
        regions.append(current)
        current = [span]
    regions.append(current)
    return regions


def _fewest_words(groups: list[str], counts: Counter[str]) -> list[int] | None:
    """Cut points of the fewest attested words covering `groups`, or None.

    None when the fewest is not unique. A single group always covers itself, so
    a covering always exists.
    """
    total = len(groups)
    words: list[int] = [0] * (total + 1)
    ways: list[int] = [0] * (total + 1)
    cut: list[int] = [0] * (total + 1)
    ways[total] = 1
    for start in range(total - 1, -1, -1):
        fewest = -1
        reached = 0
        for end in range(start + 1, total + 1):
            joined = "".join(groups[start:end])
            if (
                end > start + 1
                and counts[joined.casefold()] < _SPACED_TITLE_WITNESS_MIN
            ):
                continue
            covering = words[end] + 1
            if fewest < 0 or covering < fewest:
                fewest, reached, cut[start] = covering, ways[end], end
            elif covering == fewest:
                reached += ways[end]
        words[start] = fewest
        # Capped: only whether the fewest covering is unique is ever asked, and
        # the number of coverings itself grows exponentially.
        ways[start] = min(reached, 2)
    if ways[0] != 1:
        return None
    cuts = [0]
    while cuts[-1] < total:
        cuts.append(cut[cuts[-1]])
    return cuts


@dataclass(frozen=True)
class _HeadingIdentity:
    """What a heading names past one page's spelling of it.

    `number` is the printed section number or None; `title` is folded
    (`_fold_heading_title`).
    """

    number: tuple[int, ...] | None
    title: str

    def restated_by(self, arriving: _HeadingIdentity) -> bool:
        """True when `arriving` restates this heading.

        A copy without a number restates a numbered heading. The reverse is not
        a restatement: the number states something this heading never did.
        """
        if self.title != arriving.title:
            return False
        return arriving.number is None or arriving.number == self.number


def _heading_identity(line: str) -> _HeadingIdentity:
    """The identity `line` states: its number, and its title past the fold."""
    number = _HEADING_NUM_RE.match(line)
    if number is None:
        return _HeadingIdentity(None, _fold_heading_title(_heading_text(line)))
    title = line[number.end(3) :].removeprefix(".")
    return _HeadingIdentity(
        _section_number(number.group(3)), _fold_heading_title(title)
    )


def _fold_heading_title(title: str) -> str:
    """`title` with letter spacing closed, diacritics dropped, and case folded."""
    words = " ".join(title.split())
    return _drop_diacritics(_close_letter_spacing(words)).casefold()


def drop_running_header_headings(seg_list: list[Segment]) -> list[Segment]:
    """Drop a heading that restates the still-open heading of its level.

    A layout model reads a page's running header as a heading, so one section
    recurs once per page. The match is on identity (level, number, and folded
    title), not on bytes, since pages spell the header with and without its
    number. Only a repeat of a numbered slot is dropped: a document can repeat
    an unnumbered heading on purpose. Every heading opens a slot at its level
    and closes the deeper ones, except a restatement, so a two-line header
    (title, then subsection number) drops as a pair.

    Runs after the run-in split, so the first copy is already cut to its bare
    title. Runs before the outline pass, whose `stated` indices would shift, and
    before numbering, whose depth vote would merge the levels this match reads.
    """
    open_by_level: dict[int, _HeadingIdentity] = {}
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, True))
            continue
        heading = _ATX_LEVEL_RE.match(line)
        if heading is None:
            out.append((line, False))
            continue
        level = len(heading.group(2))
        identity = _heading_identity(line)
        open_here = open_by_level.get(level)
        if open_here is not None and open_here.restated_by(identity):
            if open_here.number is not None:
                continue
            out.append((line, False))
            continue
        open_by_level = {lvl: i for lvl, i in open_by_level.items() if lvl < level}
        open_by_level[level] = identity
        out.append((line, False))
    return out


def split_run_in_headings(seg_list: list[Segment]) -> list[Segment]:
    """Split a numbered heading that runs into its paragraph at the title's full stop.

    Runs before the outline and numbering passes, which match on the title alone.
    """
    out: list[Segment] = []
    for line, protected in seg_list:
        if protected:
            out.append((line, True))
            continue
        split = _split_run_in_heading(line)
        if split is None:
            out.append((line, False))
            continue
        heading, paragraph = split
        out.append((heading, False))
        out.append(("", False))
        out.append((paragraph, False))
    return out


def _split_run_in_heading(line: str) -> tuple[str, str] | None:
    """The `(heading, paragraph)` split for `line`, or None if it does not apply."""
    m = _RUN_IN_HEADING_RE.match(line)
    if m is None:
        return None
    prefix, title, tail = m.group(1), m.group(2), m.group(3)
    if len(title) > _RUN_IN_TITLE_MAX_LENGTH:
        return None
    if len(title.split()[-1]) < _RUN_IN_LAST_WORD_MIN_LENGTH:
        return None
    if not _run_in_tail_is_prose(tail):
        return None
    return f"{prefix}{title}", tail


def _run_in_tail_is_prose(tail: str) -> bool:
    """True when `tail` holds a word that does not open with a capital letter.

    A Title Case phrase can run on past an abbreviation
    (`Mr. Smith's Approach To The Problem`); a sentence carries a lowercase word
    almost at once.
    """
    for word in tail.split():
        letter = next((ch for ch in word if ch.isalpha()), None)
        if letter is not None and letter.islower():
            return True
    return False


def detect_run_in_headings(seg_list: list[Segment], keywords: Keywords) -> set[int]:
    """Indices of numbered headings fused with their paragraph, loosely shaped.

    The title holds a minor word, so the strict split declines the line. A
    guessed split has nothing to check it against, so the line is reported for
    `post`, whose token check cannot lose or invent a word.
    """
    minor = word_pattern(keywords.heading_minor_words)
    flagged: set[int] = set()
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        if _split_run_in_heading(line) is not None:
            continue
        m = _RUN_IN_HEADING_LOOSE_RE.match(line)
        if m is None:
            continue
        title, tail = m.group(2), m.group(3)
        if len(title) > _RUN_IN_TITLE_MAX_LENGTH:
            continue
        words = title.split()
        if not all(_is_run_in_title_word(word, minor) for word in words):
            continue
        if len(words[-1]) < _RUN_IN_LAST_WORD_MIN_LENGTH:
            continue
        if not _run_in_tail_is_prose(tail):
            continue
        flagged.add(idx)
    return flagged


def _is_run_in_title_word(word: str, minor: re.Pattern[str]) -> bool:
    """True for a capitalized word or a minor word a Title Case title lowercases.

    The minor list stays short, so the loose title still stops at the first
    sentence.
    """
    return word[:1].isupper() or minor.fullmatch(word) is not None


def printed_outline(seg_list: list[Segment], keywords: Keywords) -> SourceOutline:
    """The heading levels the body's own printed table of contents states.

    A converter renders a printed contents page as a table whose columns keep
    the entries' indentation; that staircase is read into the same witness as a
    PDF outline. The rows are only read, never promoted. One depth-to-level map
    covers the whole zone, so a page that lost its columns cannot put a chapter
    on level 1, and a table that states no ranks is dropped alone. Empty when
    the body has no contents heading or no readable table under it.
    """
    page_labels = word_pattern(keywords.contents_page_label)
    entries: list[tuple[int, str]] = []
    for start, end in contents_zones(seg_list, keywords, through_running_heads=True):
        blocks = [
            _contents_records(seg_list, block_start, block_end, page_labels)
            for block_start, block_end in _table_blocks(seg_list, start, end)
        ]
        stems = _numbered_stems(blocks)
        named = _named_ranks(blocks)
        zone: list[tuple[int, str]] = []
        for block in blocks:
            zone.extend(_ranked_records(block, stems, named))
        ladder = _contents_ladder([depth for depth, _ in zone])
        entries.extend((ladder[depth], title) for depth, title in zone)
    if not entries:
        return SourceOutline.empty()
    return SourceOutline(entries)


def _contents_ladder(depths: list[int]) -> dict[int, int]:
    """Depth to level over one zone; the shallowest depth is level 1."""
    return {
        depth: min(rank + 1, _MAX_HEADING_LEVEL)
        for rank, depth in enumerate(sorted(set(depths)))
    }


def _numbered_stems(blocks: list[list[_ContentsRecord]]) -> frozenset[int]:
    """The chapter numbers the zone's dotted records open (`6` of `6.1.3`).

    Such a number ranks its own single-level record at the top. Read over the
    zone, since a chapter and its sections often fall on different pages.
    """
    return frozenset(
        record.number[0]
        for block in blocks
        for record in block
        if record.number is not None and len(record.number) > 1
    )


def _named_ranks(blocks: list[list[_ContentsRecord]]) -> frozenset[str]:
    """The distinct rank words the zone prints in a cell of their own.

    Folded, and without an abbreviation's dot: `Cap.` and `Cap` are one rank.
    """
    return frozenset(
        _fold_heading_title(record.rank_word).rstrip(".")
        for block in blocks
        for record in block
        if record.rank_word is not None
    )


def _ranked_records(
    records: list[_ContentsRecord], stems: frozenset[int], named: frozenset[str]
) -> list[tuple[int, str]]:
    """`(depth, title)` of one table's records, or empty when its grid is no tree.

    The staircase and minimum-depth guards judge the grid, so a record ranked by
    its own number stands outside them.
    """
    ranks = [_record_rank(record, stems, named) for record in records]
    if not _is_staircase(ranks):
        return []
    read_by_grid = any(not rank.stated for rank in ranks)
    if read_by_grid and len({rank.depth for rank in ranks}) < _CONTENTS_MIN_DEPTHS:
        return []
    return [
        (rank.depth, record.title) for rank, record in zip(ranks, records, strict=True)
    ]


def _record_rank(
    record: _ContentsRecord, stems: frozenset[int], named: frozenset[str]
) -> _RecordRank:
    """The rank one record stands at.

    A dotted number states it. A single-level number states the top rank where
    the zone opens its sections, or where a rank word names it and the zone uses
    one rank word only: two words (`Parte`, `Cap.`) do not say which outranks
    the other. Otherwise the column is the rank.
    """
    number = record.number
    if number is None:
        return _RecordRank(record.column, stated=False)
    if len(number) > 1:
        return _RecordRank(len(number) - 1, stated=True)
    if (record.rank_word is not None and len(named) == 1) or number[0] in stems:
        return _RecordRank(0, stated=True)
    return _RecordRank(record.column, stated=False)


def contents_zones(
    seg_list: list[Segment],
    keywords: Keywords,
    *,
    through_running_heads: bool = False,
) -> list[tuple[int, int]]:
    """Every span from a contents heading to the next heading.

    Under `through_running_heads`, a heading whose title the body repeats is a
    running header and does not close the zone. The price is a first section
    with a repeated title, whose tables are then read as contents. A caller that
    rewrites the zone takes the strict boundary, since nothing would undo a
    wrong rewrite. The heading is read up to its first cell separator, because
    a converter can merge the table's header line onto it.
    """
    contents = word_pattern(keywords.contents_heading)
    repeated = _repeated_heading_titles(seg_list)
    zones: list[tuple[int, int]] = []
    opened: int | None = None
    for idx, (line, protected) in enumerate(seg_list):
        if protected or _ATX_LEVEL_RE.match(line) is None:
            continue
        title = _heading_title(line)
        if _is_contents_title(title, contents):
            if opened is not None:
                zones.append((opened, idx))
            opened = idx
            continue
        if opened is None:
            continue
        if through_running_heads and title in repeated:
            continue
        zones.append((opened, idx))
        opened = None
    if opened is not None:
        zones.append((opened, len(seg_list)))
    return zones


def _heading_title(line: str) -> str:
    """The heading's own text, without a row a converter merged onto its line."""
    return CELL_SEPARATOR_RE.split(_heading_text(line), maxsplit=1)[0].strip()


def _repeated_heading_titles(seg_list: list[Segment]) -> frozenset[str]:
    """Titles the body carries at more than one heading, whatever their level.

    The converter guesses a running header's level page by page.
    """
    counts = Counter(
        _heading_title(line)
        for line, protected in seg_list
        if not protected and _ATX_LEVEL_RE.match(line) is not None
    )
    return frozenset(title for title, count in counts.items() if count > 1)


def _is_contents_title(title: str, contents: re.Pattern[str]) -> bool:
    """True when `title` opens the body's printed contents.

    On a crushed line, the head up to the first closing mark is read as well. A
    section merely named after the word has no such mark.
    """
    stripped = title.strip(" *_")
    if contents.fullmatch(_fold_contents_word(stripped)) is not None:
        return True
    head = _CONTENTS_TITLE_HEAD_RE.match(stripped)
    if head is None:
        return False
    return contents.fullmatch(_fold_contents_word(head.group(1))) is not None


def _fold_contents_word(text: str) -> str:
    """`text` past a leading number or folio, letter spacing closed, no diacritics.

    A scanned contents page prints the word spaced out or without accents.
    """
    core = _close_letter_spacing(text)
    core = _CONTENTS_TITLE_NUMBER_RE.sub("", core, count=1).strip()
    return _drop_diacritics(core).casefold()


def _close_letter_spacing(text: str) -> str:
    """Join a title spelled one spaced character at a time into one word."""
    tokens = text.split()
    if len(tokens) >= _CONTENTS_SPACED_MIN_LETTERS and all(
        len(token) == 1 for token in tokens
    ):
        return "".join(tokens)
    return text


def _drop_diacritics(text: str) -> str:
    """`text` with every combining mark removed (`matieres` for `matières`)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _table_blocks(
    seg_list: list[Segment], start: int, end: int
) -> list[tuple[int, int]]:
    """Every run of table rows in the zone; a converter emits one per printed page."""
    blocks: list[tuple[int, int]] = []
    idx = start
    while idx < end:
        line, protected = seg_list[idx]
        if protected or "|" not in line:
            idx += 1
            continue
        block_start = idx
        while idx < end and not seg_list[idx][1] and "|" in seg_list[idx][0]:
            idx += 1
        blocks.append((block_start, idx))
    return blocks


def _contents_records(
    seg_list: list[Segment], start: int, end: int, page_labels: re.Pattern[str]
) -> list[_ContentsRecord]:
    """Every readable record of one contents table, in reading order.

    The row above the separator is read only when it ends on a page number;
    otherwise it holds column labels. Of a heading merged onto a row, only the
    cells count. A page-word column (`_label_column`) is blanked in every row,
    since a bad scan turns the word into noise further down.
    """
    body = _body_start(seg_list, start, end)
    if body is None:
        return []
    header = _row_cells(seg_list, body - 2) if body - 2 >= start else None
    label_column = None if header is None else _label_column(header, page_labels)
    records: list[_ContentsRecord] = []
    for idx in range(start, end):
        core = _row_core(seg_list, idx)
        if core is None or is_table_separator(core):
            continue
        cells = _clean_cells(table_cells(core))
        if idx < body and not _ends_on_a_page(cells):
            continue
        if label_column is not None and label_column < len(cells):
            cells[label_column] = ""
        record = _contents_entry(cells)
        if record is not None:
            records.append(record)
    return records


def _row_core(seg_list: list[Segment], idx: int) -> str | None:
    """Row `idx` past a heading merged onto its line, or None where it is none."""
    line, protected = seg_list[idx]
    if protected:
        return None
    return _row_of(line.strip())


def _row_cells(seg_list: list[Segment], idx: int) -> list[str] | None:
    """The cleaned cells of row `idx`, or None where it carries no row at all."""
    core = _row_core(seg_list, idx)
    return None if core is None else _clean_cells(table_cells(core))


def _label_column(header: list[str], page_labels: re.Pattern[str]) -> int | None:
    """The column before the page that holds a page word (`pag. 1`), or None.

    Read from the row above the separator, where the word survives a bad scan.
    A real title never reads as a page word alone.
    """
    if len(header) < 3:
        return None
    column = len(header) - 2
    word = _drop_diacritics(header[column].strip(". ")).casefold()
    return column if page_labels.fullmatch(word) is not None else None


def _row_of(core: str) -> str | None:
    """The table row `core` carries, or None when it carries none."""
    if _ATX_LEVEL_RE.match(core) is None:
        return core
    parts = CELL_SEPARATOR_RE.split(core, maxsplit=1)
    return parts[1] if len(parts) > 1 else None


def _ends_on_a_page(cells: list[str]) -> bool:
    """True when the row's last filled cell is the page an entry points at."""
    filled = [text for text in cells if text]
    return bool(filled) and _CONTENTS_PAGE_RE.match(filled[-1]) is not None


def _body_start(seg_list: list[Segment], start: int, end: int) -> int | None:
    """The row the table body opens on; None for rows without a separator."""
    for idx in range(start, end):
        if is_table_separator(seg_list[idx][0].strip()):
            return idx + 1
    return None


def _is_staircase(ranks: list[_RecordRank]) -> bool:
    """True when the ranks the grid states deepen one step at a time.

    A deeper jump means the columns state something other than rank, such as
    centered chapter titles right of the section marks, so the table is
    dropped. A continuation page that opens deep in the tree is lost too: a
    missed witness is the safer error. A record's own number is exempt.
    """
    if not ranks:
        return False
    opened = min(rank.depth for rank in ranks)
    for rank in ranks:
        if not rank.stated and rank.depth > opened + 1:
            return False
        opened = max(opened, rank.depth)
    return True


@dataclass(frozen=True)
class _ContentsRecord:
    """One readable record of a printed contents, as the row states it.

    `column` is the column of the first filled cell. `rank_word` is a leading
    cell's word that names `number` a rank (`Cap. I`).
    """

    title: str
    column: int
    number: tuple[int, ...] | None
    rank_word: str | None = None


@dataclass(frozen=True)
class _RecordRank:
    """A record's depth; `stated` when its own number named it, not its column."""

    depth: int
    stated: bool


def _contents_entry(cells: list[str]) -> _ContentsRecord | None:
    """The record one cleaned contents row states, or None when it is unreadable.

    Unreadable: no word, longer than a title, or a page number still glued to
    the title, since the lost grid no longer says which number is the page. A
    glued roman folio passes: roman numerals also number parts and spell words.
    A rank word and its number in separate cells stay in the title, since the
    body heading prints both.
    """
    filled = [(col, text) for col, text in enumerate(cells) if text]
    if not filled:
        return None
    if _CONTENTS_PAGE_RE.match(filled[-1][1]):
        filled = filled[:-1]
    if not filled:
        return None
    title = " ".join(text for _, text in filled)
    if len(title) > _CONTENTS_ENTRY_MAX_LENGTH:
        return None
    tokens = tokenize(title)
    if not any(any(ch.isalpha() for ch in token) for token in tokens):
        return None
    if tokens[-1].isdigit():
        return None
    rank_value = _rank_word_number(filled)
    if rank_value is not None:
        return _ContentsRecord(
            title=title,
            column=filled[0][0],
            number=(rank_value,),
            rank_word=filled[0][1],
        )
    number = _CONTENTS_ENTRY_NUMBER_RE.match(title)
    return _ContentsRecord(
        title=title,
        column=filled[0][0],
        number=None if number is None else _section_number(number.group(1)),
    )


def _rank_word_number(filled: list[tuple[int, str]]) -> int | None:
    """The number a leading rank word and the cell after it state together.

    A page aligned into columns without a real grid can give a chapter's rank
    word and its number a column each; the word ranks the number the way a
    dotted prefix does inside one cell.
    """
    if len(filled) < 2:
        return None
    if _CONTENTS_RANK_WORD_RE.match(filled[0][1]) is None:
        return None
    number = _CONTENTS_RANK_NUMBER_RE.match(filled[1][1])
    if number is None:
        return None
    digits = number.group(1)
    return int(digits) if digits.isdigit() else _roman_to_int(digits)


def _clean_cells(cells: list[str]) -> list[str]:
    """The row's cells without dot leaders, with cell breaks read as spaces."""
    cleaned: list[str] = []
    for cell in cells:
        text = _CONTENTS_LEADER_RE.sub(" ", CELL_BREAK_RE.sub(" ", cell)).strip()
        cleaned.append(text)
    return cleaned


@dataclass(frozen=True)
class _OutlineMatch:
    """A heading the outline states a level for: where it sits and what it says."""

    idx: int
    indent: str
    marker: str
    title: str
    level: int


def apply_outline_levels(
    seg_list: list[Segment], outline: SourceOutline
) -> tuple[list[Segment], frozenset[int]]:
    """Take each heading's level from the source outline where it states one.

    Returns the lines the outline spoke for; numbering neither rewrites them nor
    treats them as a guess. Where the body prints enough of the outline to read
    it as its skeleton, the printed ladder is lifted to the top and every other
    heading hangs one step under its nearest stated one. Only an existing ATX
    heading is a candidate: a printed contents repeats every title, and
    promoting those lines would duplicate the section tree.
    """
    if not outline.has_outline:
        return seg_list, frozenset()
    matches = _outline_matches(seg_list, outline)
    ladder = _outline_ladder(matches, outline)
    result = list(seg_list)
    for match in matches:
        # An outline nesting deeper than ATX lands on `######`.
        want = min(ladder.get(match.level, match.level), _MAX_HEADING_LEVEL)
        if want == len(match.marker):
            continue
        line, protected = result[match.idx]
        rest = line[len(match.indent) + len(match.marker) :]
        result[match.idx] = (f"{match.indent}{'#' * want}{rest}", protected)
    stated = frozenset(match.idx for match in matches)
    if not ladder:
        return result, stated
    return _nest_under_outline(result, stated), stated


def _outline_matches(
    seg_list: list[Segment], outline: SourceOutline
) -> list[_OutlineMatch]:
    """Every ATX heading of the plain zones the outline states a level for."""
    matches: list[_OutlineMatch] = []
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        m = _ATX_LEVEL_RE.match(line)
        if m is None:
            continue
        title = _heading_text(line)
        level = outline.level_for(title)
        if level is None:
            continue
        matches.append(_OutlineMatch(idx, m.group(1), m.group(2), title, level))
    return matches


def _outline_ladder(
    matches: list[_OutlineMatch], outline: SourceOutline
) -> dict[int, int]:
    """Outline level to the level it stands at; empty when there is no skeleton.

    The outline levels the body prints are ranked onto levels 1, 2, 3, so an
    outline rung nothing was printed for closes instead of leaving a hole.
    """
    found = outline.found_titles(match.title for match in matches)
    if (
        found < _OUTLINE_SKELETON_MIN_TITLES
        or found < outline.title_count * _OUTLINE_SKELETON_MIN_SHARE
    ):
        return {}
    printed = sorted({match.level for match in matches})
    return {level: rank + 1 for rank, level in enumerate(printed)}


def _nest_under_outline(
    seg_list: list[Segment], stated: frozenset[int]
) -> list[Segment]:
    """Hang every heading outside the outline one step under its nearest stated one.

    A heading above the first stated one keeps its level, and so does one too
    long to read as a title. The step is clamped to `######`.
    """
    result = list(seg_list)
    ancestor: int | None = None
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        m = _ATX_LEVEL_RE.match(line)
        if m is None:
            continue
        level = len(m.group(2))
        if idx in stated:
            ancestor = level
            continue
        if ancestor is None or len(_heading_text(line)) > _HEADING_MAX_LENGTH:
            continue
        want = min(_MAX_HEADING_LEVEL, ancestor + 1)
        if want == level:
            continue
        indent = m.group(1)
        rest = line[len(indent) + level :]
        result[idx] = (f"{indent}{'#' * want}{rest}", protected)
    return result


@dataclass(frozen=True)
class _NumberedHeading:
    """A numbered ATX heading: where it sits, its markup, and its section number."""

    idx: int
    indent: str
    level: int
    number: tuple[int, ...]


def normalize_heading_numbering(
    seg_list: list[Segment],
    method: ConversionMethod | None = None,
    stated: frozenset[int] = frozenset(),
) -> tuple[list[Segment], frozenset[int]]:
    """Level numbered headings by numbering depth, restoring the ones marker lost.

    Only a heading's `#` count changes. A lost heading may carry its paragraph,
    which is split off, so `stated` is returned renumbered. A body with no
    heading at all, on a route that allows it, first gets its unstyled headings
    recovered; `stated` is then empty, since the outline pass matched nothing.
    Lines in `stated` keep their level and anchor the depth-to-level map, so the
    headings the outline said nothing about land on the levels of the ones it
    did.
    """
    if not _has_heading(seg_list) and _recovers_headings(method):
        seg_list = _recover_unstyled_headings(seg_list)
    headings = _numbered_headings(seg_list)
    if len(headings) < 2:
        return seg_list, stated
    target = _target_levels(headings, stated)

    result = list(seg_list)
    tails: dict[int, str] = {}
    for idx, level in _lost_headings(seg_list, headings, target).items():
        promotion = _promote_lost_heading(result[idx][0], level)
        if promotion is None:
            continue
        heading_line, tail = promotion
        result[idx] = (heading_line, False)
        if tail:
            tails[idx] = tail
    for heading in headings:
        want = target[len(heading.number)]
        if want == heading.level or heading.idx in stated:
            continue
        line, protected = result[heading.idx]
        rest = line[len(heading.indent) + heading.level :]
        result[heading.idx] = (f"{heading.indent}{'#' * want}{rest}", protected)
    if not tails:
        return result, stated
    return _detach_promoted_tails(result, tails, stated)


def _promote_lost_heading(line: str, level: int) -> tuple[str, str] | None:
    """The heading `line` becomes at `level`, and the paragraph fused onto it.

    The run-in split runs on the promoted line, since the ATX split ran before
    the line was a heading. None when the unsplit line is past
    `_HEADING_MAX_LENGTH`: it is a paragraph opening with a number. A loosely
    shaped run-in is then neither promoted nor reported, which is deliberate:
    promoting it would leave a paragraph-long heading whenever the repair is
    refused.
    """
    promoted = f"{'#' * level} {line}"
    split = _split_run_in_heading(promoted)
    if split is not None:
        return split
    if len(line) > _HEADING_MAX_LENGTH:
        return None
    return promoted, ""


def _detach_promoted_tails(
    seg_list: list[Segment], tails: dict[int, str], stated: frozenset[int]
) -> tuple[list[Segment], frozenset[int]]:
    """Put each cut-off paragraph on its own lines below its heading.

    Each split inserts two lines, so `stated` is renumbered.
    """
    out: list[Segment] = []
    moved: set[int] = set()
    for idx, segment in enumerate(seg_list):
        if idx in stated:
            moved.add(len(out))
        out.append(segment)
        tail = tails.get(idx)
        if tail is not None:
            out.append(("", False))
            out.append((tail, False))
    return out, frozenset(moved)


def _numbered_headings(seg_list: list[Segment]) -> list[_NumberedHeading]:
    """The numbered headings of the plain zones, in document order."""
    out: list[_NumberedHeading] = []
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        m = _HEADING_NUM_RE.match(line)
        if m is None:
            continue
        out.append(
            _NumberedHeading(
                idx=idx,
                indent=m.group(1),
                level=len(m.group(2)),
                number=_section_number(m.group(3)),
            )
        )
    return out


def _section_number(text: str) -> tuple[int, ...]:
    """Split a dotted-decimal number into its components: `4.1.` is `(4, 1)`."""
    return tuple(int(part) for part in text.split(".") if part)


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(numeral: str) -> int:
    """The integer a canonical roman numeral (`_ROMAN_NUMERAL`) spells out."""
    total = 0
    previous = 0
    for letter in reversed(numeral):
        value = _ROMAN_VALUES[letter]
        total += value if value >= previous else -value
        previous = value
    return total


def _levels_by_depth(
    headings: list[_NumberedHeading], stated: frozenset[int] | None = None
) -> dict[int, list[int]]:
    """The levels carried at each numbering depth, in document order.

    `stated` narrows the tally to those lines; an empty set yields an empty
    tally, so the caller falls back to the full one.
    """
    by_depth: dict[int, list[int]] = {}
    for heading in headings:
        if stated is not None and heading.idx not in stated:
            continue
        by_depth.setdefault(len(heading.number), []).append(heading.level)
    return by_depth


def _target_levels(
    headings: list[_NumberedHeading], stated: frozenset[int] = frozenset()
) -> dict[int, int]:
    """The heading level of each numbering depth present, one level per depth.

    The map is anchored at `_anchor_depth`, at the level most of its headings
    carry (a tie favors the shallower), and the other depths are projected from
    there. Where `stated` holds lines, the anchor is read from them alone: the
    outline is the document's word, and only the guesses move. The projection is
    clamped to ATX's six levels at both ends.
    """
    levels_by_depth = _levels_by_depth(headings)
    evidence = _levels_by_depth(headings, stated) or levels_by_depth
    anchor = _anchor_depth(evidence)
    counts = Counter(evidence[anchor])
    most = max(counts.values())
    anchor_level = min(level for level, count in counts.items() if count == most)

    top = min(levels_by_depth)
    spread = max(levels_by_depth) - top
    base = min(
        max(1, anchor_level - (anchor - top)),
        max(1, _MAX_HEADING_LEVEL - spread),
    )
    return {
        depth: min(_MAX_HEADING_LEVEL, base + depth - top) for depth in levels_by_depth
    }


def _anchor_depth(evidence: dict[int, list[int]]) -> int:
    """The depth the ladder is projected from.

    The shallowest depth that names a parent and carries enough headings. A
    converter keeps shallow headings apart and crushes deep ones onto one
    marker, so a deep majority is the weakest evidence. Falls back to the depth
    with the most headings, the shallower on a tie.
    """
    for depth in sorted(evidence):
        if (
            depth >= _NUMBER_ANCHOR_MIN_DEPTH
            and len(evidence[depth]) >= _NUMBER_ANCHOR_MIN_HEADINGS
        ):
            return depth
    return max(evidence, key=lambda depth: (len(evidence[depth]), -depth))


def _lost_headings(
    seg_list: list[Segment],
    headings: list[_NumberedHeading],
    target: dict[int, int],
) -> dict[int, int]:
    """Line index to level, for the plain lines that are really lost headings.

    A leading number alone proves nothing: a figure label, a numeric table row,
    and a sentence citing a section open the same way. So headings of its depth
    exist and the number fits between them, its parent section is a heading,
    its title holds a letter, and the line stands alone. A missed heading is
    cheaper than an invented one.
    """
    numbers = {heading.number for heading in headings}
    by_depth: dict[int, list[_NumberedHeading]] = {}
    for heading in headings:
        by_depth.setdefault(len(heading.number), []).append(heading)

    promoted: dict[int, int] = {}
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        m = _LOST_HEADING_RE.match(line)
        if m is None:
            continue
        number = _section_number(m.group(1))
        level = target.get(len(number))
        if level is None:
            continue
        if not any(ch.isalpha() for ch in m.group(2)):
            continue
        if number[:-1] not in numbers:
            continue
        if not is_standalone(seg_list, idx):
            continue
        if not _fits_sequence(by_depth[len(number)], idx, number):
            continue
        promoted[idx] = level
    return promoted


def _fits_sequence(
    siblings: list[_NumberedHeading], idx: int, number: tuple[int, ...]
) -> bool:
    """True when `number` sits strictly between its same-depth heading neighbors.

    A missing side is unbounded. A number a neighbor already carries is a
    cross-reference, not a second heading.
    """
    before = [heading.number for heading in siblings if heading.idx < idx]
    after = [heading.number for heading in siblings if heading.idx > idx]
    if before and before[-1] >= number:
        return False
    return not (after and after[0] <= number)


@dataclass(frozen=True)
class _HeadingViolation:
    """An unnumbered heading that does not stand one level below its section.

    `floor` is the open section's corrected level; the repair is `floor + 1`.
    """

    idx: int
    indent: str
    level: int
    floor: int
    title: str


@dataclass(frozen=True)
class _HeadingOccurrence:
    """A non-settled ATX heading reached while walking the open-section stack.

    `anchored` is whether a settled ancestor is open above it; only then does
    `floor` rest on evidence. An unanchored heading's `floor` is its own level.
    """

    idx: int
    indent: str
    level: int
    title: str
    anchored: bool
    floor: int


@dataclass(frozen=True)
class _OpenSection:
    """One entry of the open-section stack.

    `level` is the heading's written level, which every pop compares against;
    `corrected` is its level after repair, which a nested heading is measured
    against. `anchored` is whether settled evidence stands up the stack, and
    `settled` marks a numbered or outline-stated heading, the only kind a
    same-level successor is checked against rather than closed by.
    """

    level: int
    corrected: int
    anchored: bool
    settled: bool


def _unnumbered_heading_occurrences(
    seg_list: list[Segment],
    keywords: Keywords,
    stated: frozenset[int] = frozenset(),
    group_settled: frozenset[int] = frozenset(),
) -> list[_HeadingOccurrence]:
    """Every unnumbered, non-outline-stated heading, walked as open sections.

    A same-level successor closes an unnumbered section and is checked against a
    settled one, so repeated sibling subsections land on one level. A title
    opening with a top-level section word (`keywords.yaml`) closes every open
    section and is not reported. A heading in `group_settled` opens an ordinary
    section at its own level and is not reported. Callers judge the length and
    the level of each occurrence.
    """
    top_level = word_pattern(
        keywords.top_level_sections, stem_guard=_TOP_LEVEL_STEM_GUARD
    )
    settled = {heading.idx for heading in _numbered_headings(seg_list)} | stated
    stack: list[_OpenSection] = []
    found: list[_HeadingOccurrence] = []
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        m = _ATX_LEVEL_RE.match(line)
        if m is None:
            continue
        level = len(m.group(2))
        is_settled = idx in settled
        while stack:
            top = stack[-1]
            if top.settled and top.level == level and not is_settled:
                break
            if top.level < level:
                break
            stack.pop()
        if is_settled:
            stack.append(_OpenSection(level, level, True, True))
            continue
        title = _heading_text(line).strip()
        if top_level.match(title):
            stack.clear()
            continue
        anchored = bool(stack) and stack[-1].anchored
        if idx in group_settled:
            # The group settled this level: what nests under it is measured
            # against it, but it opens no settled section, since its rank says
            # nothing about a neighbor at that rank.
            stack.append(_OpenSection(level, level, anchored, False))
            continue
        if not anchored:
            found.append(
                _HeadingOccurrence(idx, m.group(1), level, title, False, level)
            )
            stack.append(_OpenSection(level, level, False, False))
            continue
        floor = stack[-1].corrected
        want = min(_MAX_HEADING_LEVEL, floor + 1)
        found.append(_HeadingOccurrence(idx, m.group(1), level, title, True, floor))
        stack.append(_OpenSection(level, want, True, False))
    return found


def _unnumbered_headings_at_parent_level(
    seg_list: list[Segment],
    keywords: Keywords,
    stated: frozenset[int] = frozenset(),
    group_settled: frozenset[int] = frozenset(),
) -> list[_HeadingViolation]:
    """Anchored unnumbered headings that do not stand exactly at `floor + 1`.

    At `floor`, a flat per-page guess made a subsection a sibling; past
    `floor + 1`, the guess landed too deep. Unanchored headings are left to the
    repeat rules.
    """
    return [
        _HeadingViolation(occ.idx, occ.indent, occ.level, occ.floor, occ.title)
        for occ in _unnumbered_heading_occurrences(
            seg_list, keywords, stated, group_settled
        )
        if occ.anchored and occ.level != min(_MAX_HEADING_LEVEL, occ.floor + 1)
    ]


def normalize_unnumbered_heading_levels(
    seg_list: list[Segment],
    keywords: Keywords,
    stated: frozenset[int],
    group_settled: frozenset[int] = frozenset(),
) -> list[Segment]:
    """Nest an unnumbered heading one level under the settled section holding it.

    Only the `#` count changes, clamped to `######`. A candidate past
    `_HEADING_MAX_LENGTH` is a paragraph with a marker, not a title, and is left
    for `detect_oversize_headings`. A heading in `group_settled` stays: its group
    outvoted the section, and correcting it back would undo that every round.
    """
    result = list(seg_list)
    for violation in _unnumbered_headings_at_parent_level(
        seg_list, keywords, stated, group_settled
    ):
        if len(violation.title) > _HEADING_MAX_LENGTH:
            continue
        want = min(_MAX_HEADING_LEVEL, violation.floor + 1)
        line, protected = result[violation.idx]
        rest = line[len(violation.indent) + violation.level :]
        result[violation.idx] = (f"{violation.indent}{'#' * want}{rest}", protected)
    return result


def heading_class(title: str) -> tuple[str, str] | None:
    """A `LECTURE 6`-shaped title's class prefix and number, or None.

    The prefix is case-folded with its spacing collapsed, so one series survives
    a member set in capitals. The number is returned as written.
    """
    m = _SECTION_CLASS_RE.match(title) or _HEADING_CLASS_RE.match(title)
    if m is None:
        return None
    return " ".join(m.group(1).split()).casefold(), m.group(2)


def is_single_letter_roman(number: str) -> bool:
    """True when `number` is one bare roman letter (`C`, `D`, `M`, ...).

    Grade letters (`Type C`, `Type D`, `Type M`) supply distinct numbers by
    coincidence; a real roman series proves itself once a member reaches `II`.
    """
    return len(number) == 1 and not number.isdigit()


def _is_numbered_series(occurrences: list[_HeadingOccurrence]) -> bool:
    """True when one prefix's members read as a series the document numbers.

    Enough members and distinct numbers, not all of them single roman letters.
    """
    numbers = {found[1] for occ in occurrences if (found := heading_class(occ.title))}
    return (
        len(occurrences) >= _HEADING_CLASS_MIN_SIZE
        and len(numbers) >= _HEADING_CLASS_MIN_NUMBERS
        and not all(is_single_letter_roman(number) for number in numbers)
    )


def _repeat_vote_groups(
    occurrences: list[_HeadingOccurrence],
) -> list[list[_HeadingOccurrence]]:
    """The groups of one class prefix that get a level vote of their own.

    A series votes whole; otherwise repeats of one exact title, two or more,
    vote per title.
    """
    if _is_numbered_series(occurrences):
        return [occurrences]
    by_title: dict[str, list[_HeadingOccurrence]] = {}
    for occ in occurrences:
        by_title.setdefault(occ.title, []).append(occ)
    return [group for group in by_title.values() if len(group) >= 2]


def _keyed_occurrences(
    occurrences: list[_HeadingOccurrence],
) -> list[list[_HeadingOccurrence]]:
    """`occurrences` gathered by class prefix, or by their own text without one."""
    # The flag keeps a title that reads like a folded prefix out of that class.
    keyed: dict[tuple[bool, str], list[_HeadingOccurrence]] = {}
    for occ in occurrences:
        found = heading_class(occ.title)
        key = (True, found[0]) if found else (False, occ.title)
        keyed.setdefault(key, []).append(occ)
    return list(keyed.values())


def _vote_groups(
    occurrences: list[_HeadingOccurrence],
) -> list[list[_HeadingOccurrence]]:
    """Every group of `occurrences` that gets a level vote of its own."""
    return [
        group
        for members in _keyed_occurrences(occurrences)
        for group in _repeat_vote_groups(members)
    ]


def _series_groups(
    occurrences: list[_HeadingOccurrence],
) -> list[list[_HeadingOccurrence]]:
    """Only the groups a document's own numbering runs through as one series."""
    return [
        members
        for members in _keyed_occurrences(occurrences)
        if _is_numbered_series(members)
    ]


def _numbered_vote_groups(
    occurrences: list[_HeadingOccurrence],
) -> list[list[_HeadingOccurrence]]:
    """The vote groups whose titles carry a number the document wrote."""
    return [
        group
        for group in _vote_groups(occurrences)
        if heading_class(group[0].title) is not None
    ]


def _repeated_title_groups(
    occurrences: list[_HeadingOccurrence],
) -> list[list[_HeadingOccurrence]]:
    """The copies of one exact unnumbered title, when enough and one is anchored.

    With no anchored copy there is no ancestor to outweigh, and the plain vote
    of `_levels_voted_by_repeat` decides.
    """
    by_title: dict[str, list[_HeadingOccurrence]] = {}
    for occ in occurrences:
        if heading_class(occ.title) is not None:
            continue
        by_title.setdefault(occ.title, []).append(occ)
    return [
        group
        for group in by_title.values()
        if len(group) >= _REPEATED_TITLE_MIN_COPIES
        and any(occ.anchored for occ in group)
    ]


def _group_mode(group: list[_HeadingOccurrence]) -> tuple[int, int]:
    """The level most of `group` carries and its count; a tie takes the shallower."""
    counts = Counter(occ.level for occ in group)
    most = max(counts.values())
    return min(level for level, count in counts.items() if count == most), most


def _repeat_level(group: list[_HeadingOccurrence]) -> int:
    """The level most copies of one repeated title carry, the deepest on a tie.

    On an even split the shallower level would make a title that names no rank
    the parent of the section holding half of its copies.
    """
    counts = Counter(occ.level for occ in group)
    most = max(counts.values())
    return max(level for level, count in counts.items() if count == most)


def _levels_settled_by_group(
    occurrences: list[_HeadingOccurrence],
) -> dict[int, int]:
    """The level a numbered group settles for its members over their ancestors.

    A deeper ancestor explains a deeper member while a group is small; a group
    of `_ANCHORED_VOTE_MIN_SIZE` or more agreeing past `_ANCHORED_VOTE_MAJORITY`
    outvotes it. Every member is returned, those already on the level included,
    so the reading survives its own repair on the next round.
    """
    return _levels_settled(_numbered_vote_groups(occurrences))


def _levels_settled_by_repeat(
    occurrences: list[_HeadingOccurrence],
) -> dict[int, int]:
    """The one level the copies of an unnumbered repeated title settle on.

    Such a title is a running label, not a rank, so no ancestor of a copy states
    anything about it and the copies rank it themselves (`_repeat_level`). Every
    copy is returned, as in the group vote.
    """
    settled: dict[int, int] = {}
    for group in _repeated_title_groups(occurrences):
        level = _repeat_level(group)
        for occ in group:
            settled[occ.idx] = level
    return settled


def _levels_settled(groups: list[list[_HeadingOccurrence]]) -> dict[int, int]:
    """The level each of `groups` settles for its members, where one is settled."""
    settled: dict[int, int] = {}
    for group in groups:
        if len(group) < _ANCHORED_VOTE_MIN_SIZE:
            continue
        if not any(occ.anchored for occ in group):
            continue
        mode, most = _group_mode(group)
        if Fraction(most, len(group)) <= _ANCHORED_VOTE_MAJORITY:
            continue
        for occ in group:
            settled[occ.idx] = mode
    return settled


def _levels_by_stem(
    occurrences: list[_HeadingOccurrence], headings: list[_NumberedHeading]
) -> dict[int, int]:
    """The level the body's dotted numbering gives a class standing over it.

    A member numbered `12` over headings `12.3` and `12.3.3` is their parent, so
    it moves one level above the shallowest of them, clamped to `#`; a member
    already higher keeps its level. The class needs the series bars and
    `_HEADING_STEM_MIN_MEMBERS` members with such a ladder. Only arabic
    single-level numbers match, and a section counts only inside its member's
    own stretch (`_member_stretches`): outside it the number is a coincidence.
    """
    ranked: dict[int, int] = {}
    for members in _keyed_occurrences(occurrences):
        if not _is_numbered_series(members):
            continue
        under = {
            occ.idx: shallowest
            for occ, end in _member_stretches(members)
            if (shallowest := _shallowest_numbered_under(occ, headings, end))
            is not None
        }
        if len(under) < _HEADING_STEM_MIN_MEMBERS:
            continue
        for occ in members:
            shallowest = under.get(occ.idx)
            if shallowest is not None:
                ranked[occ.idx] = min(occ.level, max(1, shallowest - 1))
    return ranked


def _member_stretches(
    members: list[_HeadingOccurrence],
) -> list[tuple[_HeadingOccurrence, int | None]]:
    """Each member paired with the line its stretch ends on; None for the last."""
    ordered = sorted(members, key=lambda occ: occ.idx)
    ends: list[int | None] = [*(occ.idx for occ in ordered[1:]), None]
    return list(zip(ordered, ends, strict=True))


def _shallowest_numbered_under(
    occ: _HeadingOccurrence, headings: list[_NumberedHeading], end: int | None
) -> int | None:
    """The shallowest level of the dotted headings `occ` opens in its own stretch."""
    found = heading_class(occ.title)
    if found is None or not found[1].isdigit():
        return None
    stem = int(found[1])
    levels = [
        heading.level
        for heading in headings
        if occ.idx < heading.idx
        and (end is None or heading.idx < end)
        and len(heading.number) > 1
        and heading.number[0] == stem
    ]
    if not levels:
        return None
    return min(levels)


def _settled_levels(
    seg_list: list[Segment], occurrences: list[_HeadingOccurrence]
) -> dict[int, int]:
    """Every level settled over an occurrence's own ancestors, strongest last.

    A group vote and a repeated title never speak about one heading. Where the
    numbering under a class speaks about the same heading as a vote, the
    numbering wins: the document wrote it.
    """
    levels = _levels_settled_by_group(occurrences)
    levels.update(_levels_settled_by_repeat(occurrences))
    levels.update(_levels_by_stem(occurrences, _numbered_headings(seg_list)))
    return levels


def _levels_voted_by_repeat(
    occurrences: list[_HeadingOccurrence],
) -> dict[int, int]:
    """The level each group's own mode gives every member of it."""
    voted: dict[int, int] = {}
    for group in _vote_groups(occurrences):
        mode, _ = _group_mode(group)
        for occ in group:
            voted[occ.idx] = mode
    return voted


def group_settled_headings(
    seg_list: list[Segment], keywords: Keywords, stated: frozenset[int]
) -> frozenset[int]:
    """The headings a group of their own has settled a level for.

    The nesting rule leaves such a heading where it stands and measures what
    nests under it against its level; otherwise the two rules pull against each
    other every round. The caller feeds this into the next round: a vote taken
    after nesting reads levels the settled sections have validated.
    """
    occurrences = _level_vote_occurrences(seg_list, keywords, stated)
    return frozenset(_settled_levels(seg_list, occurrences))


def headings_settled_before_nesting(
    seg_list: list[Segment], keywords: Keywords, stated: frozenset[int]
) -> frozenset[int]:
    """The headings a group of their own settles before any nesting runs.

    Nesting corrects each member of a series against a different ancestor, and
    the agreement the series arrived with is gone before the vote, so a series
    settles first. The copies of a repeated title settle here too: nesting moves
    a copy, and the vote would then depend on the previous round. A numbered
    group short of a series waits: a deeper parent can legitimately hold a
    deeper copy.
    """
    occurrences = _level_vote_occurrences(seg_list, keywords, stated)
    levels = _levels_settled(_series_groups(occurrences))
    levels.update(_levels_settled_by_repeat(occurrences))
    return frozenset(levels)


def _level_vote_occurrences(
    seg_list: list[Segment], keywords: Keywords, stated: frozenset[int]
) -> list[_HeadingOccurrence]:
    """The occurrences a level vote reads: unsettled, and short enough to be titles."""
    return [
        occ
        for occ in _unnumbered_heading_occurrences(seg_list, keywords, stated)
        if len(occ.title) <= _HEADING_MAX_LENGTH
    ]


def normalize_repeated_heading_levels(
    seg_list: list[Segment], keywords: Keywords, stated: frozenset[int]
) -> list[Segment]:
    """Level every repeat of one heading's text to the group's own mode.

    First `_settled_levels` speaks for anchored and unanchored headings alike.
    The residue votes among unanchored headings only: two anchored repeats at
    different levels are explained by different parents. A vote groups repeats
    of one exact title, or the members of one numbered class
    (`_HEADING_CLASS_RE`), and takes the mode, the shallower on a tie. A title
    past `_HEADING_MAX_LENGTH` does not vote. Only the `#` count changes.
    """
    occurrences = _level_vote_occurrences(seg_list, keywords, stated)
    levels = _settled_levels(seg_list, occurrences)
    levels.update(
        _levels_voted_by_repeat(
            [occ for occ in occurrences if not occ.anchored and occ.idx not in levels]
        )
    )

    result = list(seg_list)
    for occ in occurrences:
        want = levels.get(occ.idx)
        if want is None or want == occ.level:
            continue
        line, protected = result[occ.idx]
        rest = line[len(occ.indent) + occ.level :]
        result[occ.idx] = (f"{occ.indent}{'#' * want}{rest}", protected)
    return result


@dataclass(frozen=True)
class _LadderRung:
    """One heading as a rung of the ladder.

    A setext rung (`atx` False, empty `indent`) holds a level but is never
    rewritten.
    """

    idx: int
    indent: str
    level: int
    atx: bool


def _ladder_rungs(seg_list: list[Segment]) -> list[_LadderRung]:
    """Every heading of the plain zones in order, ATX and setext alike."""
    rungs: list[_LadderRung] = []
    previous = ""
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            previous = ""
            continue
        m = _ATX_LEVEL_RE.match(line)
        core = line.strip()
        if m is not None:
            rungs.append(_LadderRung(idx, m.group(1), len(m.group(2)), True))
        elif is_setext_underline(core, previous):
            rungs.append(_LadderRung(idx, "", 1 if core.startswith("=") else 2, False))
        previous = line
    return rungs


def _heading_levels(seg_list: list[Segment]) -> set[int]:
    """Every level the document's headings actually stand on, ATX and setext."""
    return {rung.level for rung in _ladder_rungs(seg_list)}


# Ranks between a section and its shallowest heading that read as a gap: two,
# with one rank free. At three, two ranks are free and nothing says which was
# meant.
_SECTION_LEVEL_GAP = 2


def close_section_level_gaps(
    seg_list: list[Segment],
    stated: frozenset[int] = frozenset(),
    group_settled: frozenset[int] = frozenset(),
) -> list[Segment]:
    """Move up one rank a section whose headings skip the rank under it.

    The whole section moves, since moving only the heading at the hole opens a
    hole under it. A section that prints the skipped rank uses it and stays. A
    section holding a heading in `stated` or `group_settled`, or a setext one,
    stays too. Runs last of the heading rules, after the collapse; the walk
    repeats because a moved section can leave a hole one rank further down.
    """
    for _ in range(_MAX_HEADING_LEVEL):
        fixed = _close_section_level_gaps_once(seg_list, stated, group_settled)
        if fixed == seg_list:
            break
        seg_list = fixed
    return seg_list


def _close_section_level_gaps_once(
    seg_list: list[Segment], stated: frozenset[int], group_settled: frozenset[int]
) -> list[Segment]:
    """One walk of the ladder, moving up every section that skips a rank."""
    rungs = _ladder_rungs(seg_list)
    result = list(seg_list)
    settled = stated | group_settled
    done = 0
    for pos, parent in enumerate(rungs):
        if pos < done:
            continue
        stretch = _section_stretch(rungs, pos)
        if not _section_skips_a_rank(parent, stretch):
            continue
        if any(not rung.atx or rung.idx in settled for rung in stretch):
            continue
        for rung in stretch:
            line, protected = seg_list[rung.idx]
            rest = line[len(rung.indent) + rung.level :]
            marker = "#" * (rung.level - 1)
            result[rung.idx] = (f"{rung.indent}{marker}{rest}", protected)
        # A section moved in this walk is done for the round: its subsections
        # would otherwise read as gapped and lose two ranks for one hole.
        done = pos + 1 + len(stretch)
    return result


def _section_stretch(rungs: list[_LadderRung], parent: int) -> list[_LadderRung]:
    """The headings the section at `parent` holds, up to the next one at its rank."""
    stretch: list[_LadderRung] = []
    for rung in rungs[parent + 1 :]:
        if rung.level <= rungs[parent].level:
            break
        stretch.append(rung)
    return stretch


def _section_skips_a_rank(parent: _LadderRung, stretch: list[_LadderRung]) -> bool:
    """Whether the section opens a rank below the one right under its parent."""
    if not stretch:
        return False
    return min(rung.level for rung in stretch) - parent.level == _SECTION_LEVEL_GAP


def collapse_unused_heading_levels(seg_list: list[Segment]) -> list[Segment]:
    """Close a level the document's headings never stand on.

    The outline or the numbering can name a level the body never prints
    (`1`, then `1.1.1`), and every step across that hole reads as a jump; the
    levels past it move up until the ladder is dense. The shallowest level stays,
    since a document whose top heading is `##` breaks no step. Runs after every
    level rule and before the section lift, which would hide an unused rank.
    """
    ladder = sorted(_heading_levels(seg_list))
    target = {level: ladder[0] + rank for rank, level in enumerate(ladder)}
    if all(level == want for level, want in target.items()):
        return seg_list
    result = list(seg_list)
    for idx, (line, protected) in enumerate(seg_list):
        if protected:
            continue
        m = _ATX_LEVEL_RE.match(line)
        if m is None:
            continue
        indent, marker = m.group(1), m.group(2)
        want = target[len(marker)]
        if want == len(marker):
            continue
        rest = line[len(indent) + len(marker) :]
        result[idx] = (f"{indent}{'#' * want}{rest}", protected)
    return result


def detect_oversize_headings(
    seg_list: list[Segment], outline: SourceOutline, keywords: Keywords
) -> dict[int, int]:
    """Heading index to 1, for an unnumbered heading too long to be a title.

    What reaches here is a heading recovery built past the length after the
    oversize strip ran. It feeds the flattened-block finding, whose repair may
    reshape one line into several. `outline` is re-applied so an
    outline-stated parent still anchors its oversize child.
    """
    _, stated = apply_outline_levels(seg_list, outline)
    return {
        violation.idx: 1
        for violation in _unnumbered_headings_at_parent_level(
            seg_list, keywords, stated
        )
        if len(violation.title) > _HEADING_MAX_LENGTH
    }


@dataclass(frozen=True)
class _WrappedParagraph:
    """A standalone paragraph wrapped in one emphasis run: a heading candidate.

    `idx` to `end_idx` are its physical lines, several when a hard line break
    split it; promotion rewrites `idx` and blanks the rest.
    """

    idx: int
    end_idx: int
    marker: str
    text: str
    number: tuple[int, ...] | None


def _has_heading(seg_list: list[Segment]) -> bool:
    """True when a plain zone carries a heading, ATX or setext."""
    previous = ""
    for line, protected in seg_list:
        if protected:
            previous = ""
            continue
        if ATX_HEADING_RE.match(line) or is_setext_underline(line.strip(), previous):
            return True
        previous = line
    return False


def _recovers_headings(method: ConversionMethod | None) -> bool:
    """True when the route the body came from allows heading recovery.

    A recognized body cannot say what bold means: marker both drops heading
    markers and wraps titles in bold, and the LLM-OCR route runs no marker.
    """
    return method in _HEADING_RECOVERY_METHODS


def _recover_unstyled_headings(seg_list: list[Segment]) -> list[Segment]:
    """Restore the headings a document marked with a bold paragraph, not a style.

    Recovery turns on only where the numbering proves the convention: a ladder
    of consecutive siblings under one wrap, each its own paragraph. Without a
    ladder the all-caps seed is the fallback; running both would promote the
    same lines twice. A title split into two paragraphs is rejoined last, once
    the promotions have decided which lines are headings.
    """
    candidates = _wrapped_paragraphs(seg_list)
    proven = _proven_ladder(candidates)
    if proven is None:
        return _recover_caps_headings(seg_list)
    marker, ladder = proven
    under_marker = [cand for cand in candidates if cand.marker == marker]
    result = list(seg_list)
    promoted = _promote_numbered(result, under_marker, ladder)
    wrapped = {i for cand in candidates for i in range(cand.idx, cand.end_idx + 1)}
    top = min(len(number) for number in promoted)
    _promote_unnumbered(result, under_marker, wrapped, max(1, top - 1))
    _merge_heading_tails(result, under_marker)
    return result


def _recover_caps_headings(seg_list: list[Segment]) -> list[Segment]:
    """Promote the all-caps section titles of a document that numbers nothing.

    Below `_CAPS_SEED_MIN` candidates nothing is promoted. A paragraph right
    below a promoted one is a split title's second half, left for
    `_merge_heading_tails`; only a promoted neighbour blocks, so a tail cannot
    suppress the section heading under it.
    """
    candidates = _caps_paragraphs(seg_list)
    if len(candidates) < _CAPS_SEED_MIN:
        return seg_list
    result = list(seg_list)
    promoted: set[int] = set()
    for cand in candidates:
        previous = prev_content_index(result, cand.idx)
        if previous is not None and previous in promoted:
            continue
        _promote_span(result, cand, _CAPS_HEADING_LEVEL)
        promoted.update(range(cand.idx, cand.end_idx + 1))
    _merge_heading_tails(result, candidates)
    return result


def _caps_paragraphs(seg_list: list[Segment]) -> list[_WrappedParagraph]:
    """The standalone paragraphs set entirely in capitals: heading candidates.

    Built like `_wrapped_paragraphs`, with the wrap optional. A list item, a
    paragraph past `_CAPS_MAX_LENGTH` or ending in a full stop, and a text the
    body repeats (a running head) are not candidates.
    """
    found: list[_WrappedParagraph] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected or not line.strip():
            idx += 1
            continue
        end = _hard_break_span_end(seg_list, idx)
        joined = _merge_adjacent_emphasis(_join_hard_break_span(seg_list, idx, end))
        match = _WRAPPED_PARAGRAPH_RE.match(joined)
        marker = "" if match is None else match.group(1)
        text = (joined if match is None else match.group(2)).strip()
        if marker and marker in text:
            idx = end + 1
            continue
        if not _is_caps_title(text) or not is_standalone_span(seg_list, idx, end):
            idx = end + 1
            continue
        found.append(
            _WrappedParagraph(
                idx=idx,
                end_idx=end,
                marker=marker,
                text=text,
                number=None,
            )
        )
        idx = end + 1
    repeated = {text for text, n in Counter(c.text for c in found).items() if n > 1}
    return [cand for cand in found if cand.text not in repeated]


def _is_upper_text(text: str) -> bool:
    """True when `text` has a letter and every letter in it is uppercase."""
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and all(ch.isupper() for ch in letters)


def _is_caps_title(text: str) -> bool:
    """True when `text` reads as a section title written in capitals."""
    if not _is_upper_text(text):
        return False
    if len(text) > _CAPS_MAX_LENGTH or text.endswith("."):
        return False
    return not LIST_ITEM_RE.match(text)


def _wrapped_paragraphs(seg_list: list[Segment]) -> list[_WrappedParagraph]:
    """The plain standalone paragraphs whose whole text is a single emphasis run.

    A hard-break span is joined and split runs are stitched before the check. A
    partial or doubled run is an emphasized phrase, and a text without letters
    (`**\\**`) is markup debris.
    """
    out: list[_WrappedParagraph] = []
    idx = 0
    count = len(seg_list)
    while idx < count:
        line, protected = seg_list[idx]
        if protected or not line.strip():
            idx += 1
            continue
        end = _hard_break_span_end(seg_list, idx)
        joined = _merge_adjacent_emphasis(_join_hard_break_span(seg_list, idx, end))
        match = _WRAPPED_PARAGRAPH_RE.match(joined)
        if match is None:
            idx = end + 1
            continue
        marker, text = match.group(1), match.group(2).strip()
        if marker in text or not any(ch.isalpha() for ch in text):
            idx = end + 1
            continue
        if not is_standalone_span(seg_list, idx, end):
            idx = end + 1
            continue
        out.append(
            _WrappedParagraph(
                idx=idx,
                end_idx=end,
                marker=marker,
                text=text,
                number=_wrapped_number(text),
            )
        )
        idx = end + 1
    return out


def _hard_break_span_end(seg_list: list[Segment], start: int) -> int:
    """Index of the last physical line of the paragraph opening at `start`."""
    idx = start
    count = len(seg_list)
    while (
        _HARD_BREAK_RE.search(seg_list[idx][0])
        and idx + 1 < count
        and not seg_list[idx + 1][1]
        and seg_list[idx + 1][0].strip()
    ):
        idx += 1
    return idx


def _join_hard_break_span(seg_list: list[Segment], start: int, end: int) -> str:
    """The lines `[start, end]` as one paragraph, hard breaks turned to spaces."""
    if start == end:
        return seg_list[start][0]
    lines = (_HARD_BREAK_RE.sub("", seg_list[i][0]) for i in range(start, end + 1))
    return " ".join(lines)


def _merge_adjacent_emphasis(text: str) -> str:
    """Stitch adjacent same-marker emphasis runs separated only by whitespace.

    Word can split one bold run at a revision mark or a kerning pair. Only the
    run boundary goes; the whitespace stays, so a word-boundary split keeps its
    space and a mid-word split keeps a stray one. Loops for chains of runs.
    """
    while True:
        merged = _ADJACENT_EMPHASIS_RE.sub(r"\1\2\3\4\1", text)
        if merged == text:
            return text
        text = merged


def _wrapped_number(text: str) -> tuple[int, ...] | None:
    """The section number a candidate opens with, or None when it carries none."""
    match = _LOST_HEADING_RE.match(text)
    if match is None or not any(ch.isalpha() for ch in match.group(2)):
        return None
    return _section_number(match.group(1))


def _proven_ladder(
    candidates: list[_WrappedParagraph],
) -> tuple[str, set[int]] | None:
    """The wrap that marks headings, and the candidate lines its ladders prove.

    One ladder whose parent is a candidate turns the mode on; then every ladder
    under that marker counts, since a block's own heading may be unwrapped.
    """
    for marker in ("**", "__"):
        ladders = _sibling_runs(candidates, marker)
        numbers = {
            cand.number
            for cand in candidates
            if cand.number is not None and cand.marker == marker
        }
        if not any(_has_parent(run[0][1], numbers) for run in ladders):
            continue
        return marker, {idx for run in ladders for idx, _ in run}
    return None


def _sibling_runs(
    candidates: list[_WrappedParagraph], marker: str
) -> list[list[tuple[int, tuple[int, ...]]]]:
    """Runs of `_LADDER_MIN` or more consecutive siblings, as (index, number).

    A gap ends a run: something in between is not a heading.
    """
    by_parent: dict[tuple[int, ...], list[tuple[int, tuple[int, ...]]]] = {}
    for cand in candidates:
        if cand.number is None or cand.marker != marker:
            continue
        by_parent.setdefault(cand.number[:-1], []).append((cand.idx, cand.number))

    runs: list[list[tuple[int, tuple[int, ...]]]] = []
    for group in by_parent.values():
        run = [group[0]]
        for previous, current in pairwise(group):
            if current[1][-1] == previous[1][-1] + 1:
                run.append(current)
                continue
            if len(run) >= _LADDER_MIN:
                runs.append(run)
            run = [current]
        if len(run) >= _LADDER_MIN:
            runs.append(run)
    return runs


def _has_parent(number: tuple[int, ...], numbers: set[tuple[int, ...]]) -> bool:
    """True when `number`'s parent section is itself among `numbers`.

    A two-component number passes: `_LOST_HEADING_RE` never admits its
    single-level parent.
    """
    parent = number[:-1]
    return len(parent) < 2 or parent in numbers


def _promote_numbered(
    result: list[Segment],
    candidates: list[_WrappedParagraph],
    ladder: set[int],
) -> list[tuple[int, ...]]:
    """Promote the numbered candidates in place; return the numbers promoted.

    A ladder member is promoted on the ladder's evidence. Any other candidate
    needs a promoted parent and a number in order among all candidates of its
    depth, promoted or not, so a figure label above the sections
    (`9.4 Fig. 9.5`) cannot bound the sequence one-sidedly.
    """
    siblings = _candidate_siblings(candidates)
    numbers: set[tuple[int, ...]] = set()
    promoted: list[tuple[int, ...]] = []
    for cand in candidates:
        if cand.number is None:
            continue
        depth = len(cand.number)
        if cand.idx not in ladder and not (
            _has_parent(cand.number, numbers)
            and _fits_sequence(siblings[depth], cand.idx, cand.number)
        ):
            continue
        level = min(_MAX_HEADING_LEVEL, depth)
        _promote_span(result, cand, level)
        numbers.add(cand.number)
        promoted.append(cand.number)
    return promoted


def _promote_span(result: list[Segment], cand: _WrappedParagraph, level: int) -> None:
    """Rewrite `cand`'s first line as a heading and blank the rest of its span."""
    result[cand.idx] = (f"{'#' * level} {cand.text}", False)
    for i in range(cand.idx + 1, cand.end_idx + 1):
        result[i] = ("", False)


def _candidate_siblings(
    candidates: list[_WrappedParagraph],
) -> dict[int, list[_NumberedHeading]]:
    """The numbered candidates grouped by depth, in document order, promoted or not."""
    by_depth: dict[int, list[_NumberedHeading]] = {}
    for cand in candidates:
        if cand.number is None:
            continue
        depth = len(cand.number)
        by_depth.setdefault(depth, []).append(
            _NumberedHeading(
                idx=cand.idx,
                indent="",
                level=min(_MAX_HEADING_LEVEL, depth),
                number=cand.number,
            )
        )
    return by_depth


def _promote_unnumbered(
    result: list[Segment],
    candidates: list[_WrappedParagraph],
    wrapped: set[int],
    level: int,
) -> None:
    """Promote the wrapped paragraphs without a number, after a proven ladder.

    They land on the level the numbering hangs from. A lead-in ending in a
    colon, a lowercase opening, and a paragraph right below another wrapped one
    (a split title's tail) are not headings.
    """
    for cand in candidates:
        if cand.number is not None:
            continue
        if cand.text.endswith(":") or _opens_lowercase(cand.text):
            continue
        previous = prev_content_index(result, cand.idx)
        if previous is not None and previous in wrapped:
            continue
        _promote_span(result, cand, level)


def _merge_heading_tails(
    result: list[Segment], candidates: list[_WrappedParagraph]
) -> None:
    """Glue a heading's tail paragraph back onto the heading above it.

    A tail agrees with its heading in one of two shapes. A lowercase opening
    continues a numbered heading; after an unnumbered one a bold remark is more
    plausible. A tail that reads as a capitals title joins an ATX heading whose
    text is in capitals too. Only a still-wrapped candidate is a target, and a
    heading takes at most one tail, so unrelated paragraphs do not chain onto
    one title.
    """
    extended: set[int] = set()
    for cand in candidates:
        if cand.number is not None:
            continue
        _, protected = result[cand.idx]
        joined = _merge_adjacent_emphasis(
            _join_hard_break_span(result, cand.idx, cand.end_idx)
        )
        if protected or not _WRAPPED_PARAGRAPH_RE.match(joined):
            continue
        if cand.text.endswith(":"):
            continue
        lowercase_tail = _opens_lowercase(cand.text)
        if not lowercase_tail and not _is_caps_title(cand.text):
            continue
        previous = prev_content_index(result, cand.idx)
        if previous is None or previous in extended:
            continue
        heading, heading_protected = result[previous]
        if heading_protected:
            continue
        if lowercase_tail:
            if not _HEADING_NUM_RE.match(heading):
                continue
        elif not ATX_HEADING_RE.match(heading) or not _is_upper_text(
            _heading_text(heading)
        ):
            continue
        result[previous] = (f"{heading} {cand.text}", False)
        for i in range(cand.idx, cand.end_idx + 1):
            result[i] = ("", False)
        extended.add(previous)


def _opens_lowercase(text: str) -> bool:
    """True when the first letter of `text` is lowercase."""
    letter = next((ch for ch in text if ch.isalpha()), None)
    return letter is not None and letter.islower()


def _heading_text(heading: str) -> str:
    """The heading's own title text, its leading `#` marker stripped."""
    return ATX_HEADING_RE.sub("", heading, count=1)
