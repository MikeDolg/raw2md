"""Rules for the tokens a recognition route got wrong.

`repair_attested_tokens` repairs what the body itself decides: a lower-cased
code and a one-letter misspelling, each against a frequent attested form.

`strip_ocr_fabrications` removes what the LLM-OCR route invents: it extracts
no media, so its image links, external links, and placeholder notes have no
source to salvage.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Iterator

from raw2md.cleaning.segments import WORD_RUN_RE, body_word_counts, prose_reading
from raw2md.keywords import Keywords, word_pattern
from raw2md.mdtext.links import IMAGE_RE
from raw2md.mdtext.pages import is_lost_page_marker
from raw2md.mdtext.zones import Segment, html_table_lines, segments

_logger = logging.getLogger("raw2md")

# A whole `<img>` tag, removed outright.
_HTML_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)

# A scanned page has no hyperlinks, so the markup goes. The visible text
# (group 1) stays: it can be the page's own printed text.
_EXTERNAL_LINK_RE = re.compile(
    r'(?<!!)\[([^\]]*)\]\([a-zA-Z][a-zA-Z0-9+.\-]*://[^)\s]*(?:\s+"[^"]*")?\)'
)

# `![alt][ref]`, or the collapsed `![alt][]` whose label is the alt text.
_REF_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\[([^\]]*)\]")

# `[text][ref]` or the collapsed `[text][]`, image usages excluded.
_REF_LINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\[([^\]]*)\]")

# A link reference definition; CommonMark allows three spaces of indent.
_REF_DEF_RE = re.compile(r'^ {0,3}\[([^\]]+)\]:\s*(\S+)(?:\s+"[^"]*")?\s*$')

# A reference definition's target, checked as `_EXTERNAL_LINK_RE` checks one.
_EXTERNAL_TARGET_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")

# A bracket-only line, a candidate placeholder note for a figure. The end
# anchor excludes `[text](url)` and `[text][ref]`.
_BRACKET_LINE_RE = re.compile(r"^\[([^\]]+)\]$")

# The OCR prompt's own uncertainty markers, never a placeholder. Mirrors
# `quality.evaluator._OCR_MARKERS` without brackets.
_OCR_PLACEHOLDER_EXEMPT = frozenset({"unreadable", "?"})


def strip_ocr_fabrications(text: str, keywords: Keywords) -> str:
    """Remove image links, external links, and image placeholders LLM-OCR invents.

    Image links go with their alt text; an external link keeps its visible
    text. Inline and reference-style forms are covered, and a definition that
    no usage spends any more goes too. A bracket-only line with a word of
    `keywords.yaml` section `image_placeholders` is a placeholder note: it is
    removed, or unwrapped when its text repeats a caption in the body. Other
    bracketed lines stay: a missed placeholder is cheaper than a wrong
    deletion. HTML table cells are read; other protected zones are not.
    """
    placeholders = word_pattern(keywords.image_placeholders)
    seg_list = segments(text)
    in_table = html_table_lines(text)
    reachable = [
        line
        for (line, protected), table_line in zip(seg_list, in_table, strict=True)
        if not protected or table_line
    ]
    ref_targets = _collect_reference_targets(reachable)
    captions = {line.strip() for line in reachable if line.strip()}

    processed: list[str] = []
    consumed_labels: set[str] = set()
    for (line, protected), table_line in zip(seg_list, in_table, strict=True):
        # The lost-page marker is bracketed too, but it is the OCR route's own
        # record of a page it could not read.
        if is_lost_page_marker(line) or (protected and not table_line):
            processed.append(line)
            continue
        fixed, used = _strip_reference_links(line, ref_targets)
        consumed_labels |= used
        fixed = _HTML_IMG_TAG_RE.sub("", IMAGE_RE.sub("", fixed))
        fixed = _EXTERNAL_LINK_RE.sub(r"\1", fixed)
        processed.append(_resolve_ocr_placeholder(fixed, captions, placeholders))

    still_used = _remaining_reference_labels(processed)
    out = [
        line
        for line in processed
        if not _is_orphaned_reference_definition(line, consumed_labels, still_used)
    ]
    body = "\n".join(out)
    return f"{body}\n" if text.endswith("\n") else body


def _normalize_ref_label(label: str) -> str:
    """CommonMark's reference-label equality: collapse whitespace, casefold."""
    return " ".join(label.split()).casefold()


def _usage_label(match: re.Match[str]) -> str:
    """The normalized label a usage spends; the collapsed form uses its text."""
    return _normalize_ref_label(match.group(2) or match.group(1))


def _collect_reference_targets(lines: list[str]) -> dict[str, str]:
    """Normalized label -> target for every link reference definition."""
    targets: dict[str, str] = {}
    for line in lines:
        match = _REF_DEF_RE.match(line.strip())
        if match is not None:
            targets[_normalize_ref_label(match.group(1))] = match.group(2)
    return targets


def _strip_reference_links(
    line: str, ref_targets: dict[str, str]
) -> tuple[str, set[str]]:
    """Remove a reference-style image usage; unwrap one to an external link.

    Returns the fixed line and the labels it spent.
    """
    consumed: set[str] = set()

    def image_repl(match: re.Match[str]) -> str:
        consumed.add(_usage_label(match))
        return ""

    fixed = _REF_IMAGE_RE.sub(image_repl, line)

    def link_repl(match: re.Match[str]) -> str:
        label = _usage_label(match)
        target = ref_targets.get(label)
        if target is None or not _EXTERNAL_TARGET_RE.match(target):
            return match.group(0)
        consumed.add(label)
        return match.group(1)

    fixed = _REF_LINK_RE.sub(link_repl, fixed)
    return fixed, consumed


def _remaining_reference_labels(lines: list[str]) -> set[str]:
    """Normalized reference labels an image or link usage still spends."""
    used: set[str] = set()
    for line in lines:
        used.update(_usage_label(m) for m in _REF_IMAGE_RE.finditer(line))
        used.update(_usage_label(m) for m in _REF_LINK_RE.finditer(line))
    return used


def _is_orphaned_reference_definition(
    line: str, consumed: set[str], still_used: set[str]
) -> bool:
    """True when `line` defines a label this pass spent and nothing still uses."""
    match = _REF_DEF_RE.match(line.strip())
    if match is None:
        return False
    label = _normalize_ref_label(match.group(1))
    return label in consumed and label not in still_used


def _resolve_ocr_placeholder(
    line: str, captions: set[str], placeholders: re.Pattern[str]
) -> str:
    """Drop a bracketed image placeholder, or unwrap one that echoes a caption."""
    stripped = line.strip()
    match = _BRACKET_LINE_RE.match(stripped)
    if match is None:
        return line
    inner = match.group(1).strip()
    if inner in _OCR_PLACEHOLDER_EXEMPT:
        return line
    if not placeholders.search(inner):
        return line
    return inner if inner in captions else ""


# ---- the token the body attests ----------------------------------------------

# Measured band: 5 occurrences separate a repair from noise, 20 make it
# unarguable. The strict end is the default: a token left alone still reaches
# inspection, a wrong repair reaches nothing. settings.json can lower it.
DEFAULT_WITNESS_MIN = 20

# A short word has many one-letter neighbours, so a frequent one proves
# nothing.
_MIN_REPAIRABLE_WORD = 6

# One letter and a digit is as often a variable (`x1`) as a code, and case
# can be the whole difference between two labels.
_MIN_CODE_LETTERS = 2

# Two words one letter apart share exactly one blurred key. U+FFFE is a
# Unicode noncharacter, so no body carries it.
_BLUR = "\ufffe"


def repair_attested_tokens(
    seg_list: list[Segment], witness_min: int = DEFAULT_WITNESS_MIN
) -> list[Segment]:
    """Repair a corrupt token that the body's own frequency profile identifies.

    A code (a digit and at least `_MIN_CODE_LETTERS` letters) becomes the
    capitalised form the body spells `witness_min` times and more often. A word
    of at least `_MIN_REPAIRABLE_WORD` letters standing once becomes its only
    neighbour one substitution away that the body spells `witness_min` times.
    An inflection has two frequent neighbours, so it stays. Price: a real word
    used once next to a frequent one is rewritten. Reads `prose_reading` only.
    """
    prose = prose_reading(seg_list)
    literal = _literal_counts(prose)
    folded = body_word_counts(prose)
    case_repairs = _case_repairs(literal, witness_min)
    spelling_repairs = _spelling_repairs(folded, literal, witness_min)
    if not case_repairs and not spelling_repairs:
        return seg_list
    out: list[Segment] = []
    cases = spellings = 0
    for (line, protected), text in zip(seg_list, prose, strict=True):
        if text is None:
            out.append((line, protected))
            continue
        fixed, line_cases, line_spellings = _repair_line(
            line, text, case_repairs, spelling_repairs
        )
        cases += line_cases
        spellings += line_spellings
        out.append((fixed, protected))
    if cases or spellings:
        # A repaired token carries no mark, so the log is the only record.
        _logger.info(
            "tokens repaired by the body's own witness: %d code, %d spelling",
            cases,
            spellings,
        )
    return out


def _literal_counts(prose: list[str | None]) -> Counter[str]:
    """How often the body spells each word run verbatim, case kept."""
    counts: Counter[str] = Counter()
    for text in prose:
        if text is not None:
            counts.update(WORD_RUN_RE.findall(text))
    return counts


def _case_repairs(literal: Counter[str], witness_min: int) -> dict[str, str]:
    """Literal spelling -> the capitalised one the body attests for it."""
    repairs: dict[str, str] = {}
    for form, count in literal.items():
        capitalised = form.upper()
        if capitalised == form or not _is_code(form):
            continue
        witness = literal[capitalised]
        if witness >= witness_min and witness > count:
            repairs[form] = capitalised
    return repairs


def _is_code(form: str) -> bool:
    """True when `form` reads as an alphanumeric code rather than a word."""
    letters = sum(1 for char in form if char.isalpha())
    return letters >= _MIN_CODE_LETTERS and any(char.isdigit() for char in form)


def _spelling_repairs(
    folded: Counter[str], literal: Counter[str], witness_min: int
) -> dict[str, str]:
    """Case-blind spelling -> the literal form of its one attested neighbour.

    A lookup costs the word length, not the vocabulary size. A word cannot find
    itself: it occurs once, and the index holds words seen at least twice.
    """
    index: dict[str, set[str]] = {}
    for word, count in folded.items():
        if count >= witness_min and _is_repairable(word):
            for key in _blurred(word):
                index.setdefault(key, set()).add(word)
    if not index:
        return {}
    repairs: dict[str, str] = {}
    for word, count in folded.items():
        if count != 1 or not _is_repairable(word):
            continue
        neighbours: set[str] = set()
        for key in _blurred(word):
            neighbours |= index.get(key, set())
        if len(neighbours) != 1:
            continue
        repairs[word] = _literal_form(next(iter(neighbours)), literal)
    return repairs


def _is_repairable(word: str) -> bool:
    """True when `word` is long enough and plain enough to be repaired at all."""
    return len(word) >= _MIN_REPAIRABLE_WORD and word.isalpha()


def _blurred(word: str) -> Iterator[str]:
    """`word` with each position in turn replaced by the substitution marker."""
    for index in range(len(word)):
        yield f"{word[:index]}{_BLUR}{word[index + 1 :]}"


def _literal_form(word: str, literal: Counter[str]) -> str:
    """The spelling the body most often gives `word`; a tie goes by spelling."""
    forms = [form for form in literal if form.casefold() == word]
    return max(forms, key=lambda form: (literal[form], form))


def _repair_line(
    line: str,
    prose: str,
    case_repairs: dict[str, str],
    spelling_repairs: dict[str, str],
) -> tuple[str, int, int]:
    """`line` with its attested repairs applied, and the count of each kind.

    The two maps never claim one token: a code has a digit, a word has none.
    """
    edits: list[tuple[int, int, str]] = []
    cases = spellings = 0
    for match in WORD_RUN_RE.finditer(prose):
        token = match.group()
        capitalised = case_repairs.get(token)
        if capitalised is not None:
            edits.append((match.start(), match.end(), capitalised))
            cases += 1
            continue
        attested = spelling_repairs.get(token.casefold())
        if attested is None:
            continue
        edits.append((match.start(), match.end(), _matching_case(token, attested)))
        spellings += 1
    for start, end, text in reversed(edits):
        line = f"{line[:start]}{text}{line[end:]}"
    return line, cases, spellings


def _matching_case(token: str, attested: str) -> str:
    """`attested` with the case of `token`'s first letter, or all caps."""
    if token.isupper() and len(token) > 1:
        return attested.upper()
    if token[:1].isupper():
        return f"{attested[:1].upper()}{attested[1:]}"
    return f"{attested[:1].lower()}{attested[1:]}"
