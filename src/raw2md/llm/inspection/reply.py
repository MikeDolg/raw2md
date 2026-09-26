"""Decode a model reply into the edit list, tolerating the model's usual slips.

A format flag is counted and written nowhere, so it is kept as its type alone.
"""

from __future__ import annotations

import json
import re

from raw2md.llm.base import FINAL_EMPTY_REASONS, Reply, empty_reason_label
from raw2md.llm.inspection.common import InspectionReplyError, SemanticEdit

# The semantic edit only: a flag is written nowhere, so allowing one would only
# spend output tokens. The `edits` wrapper matches the prompt, so a constrained
# reply and a free-text one decode the same way.
RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "line": {"type": "integer"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                },
                "required": ["page", "line", "old", "new"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["edits"],
}


# A code fence the model sometimes wraps around the JSON.
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*)\n```\s*$", re.DOTALL)


_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


_ERROR_FRAGMENT_RADIUS = 100


def parse_edits(reply: Reply) -> tuple[list[SemanticEdit], list[str]]:
    """Parse the model reply into semantic edits and flag types, tolerantly.

    An edit that names no page keeps ``page`` unset and counts as a miss. A
    flag yields its type for the count only. Control characters are restored
    here, once, so every later reader sees the same text.
    """
    entries = _reply_entries(reply)
    semantic: list[SemanticEdit] = []
    flags: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if "old" in entry and "new" in entry:
            line = _as_number(entry.get("line"))
            old, new = entry.get("old"), entry.get("new")
            if line is not None and isinstance(old, str) and isinstance(new, str):
                semantic.append(
                    SemanticEdit(
                        page=_as_number(entry.get("page")),
                        line=line,
                        old=_restore_control_chars(old),
                        new=_restore_control_chars(new),
                    )
                )
            continue
        flag = entry.get("flag")
        if isinstance(flag, str):
            flags.append(flag)
    return semantic, flags


# A JSON escape that swallowed a LaTeX command's backslash. Only the three a
# body never holds are restored; a real newline is legal in the quote of a
# formula cut across lines, and `_repair_reply_text` already reads that case.
_CONTROL_CHAR_LETTERS = {
    "\x08": "b",
    "\x0c": "f",
    "\x0b": "v",
}


def _restore_control_chars(text: str) -> str:
    """Undo a JSON escape that ate a LaTeX command's own backslash."""
    for control, letter in _CONTROL_CHAR_LETTERS.items():
        if control in text:
            text = text.replace(control, f"\\{letter}")
    return text


def _reply_entries(reply: Reply) -> list[object]:
    """Decode the reply into a list of raw edit entries.

    An empty reply raises rather than reading as "nothing to fix", which only
    an explicit empty list says; it is `final` when its reason would repeat.
    """
    stripped = reply.text.strip()
    fenced = _FENCE_RE.match(stripped)
    if fenced is not None:
        stripped = fenced.group(1).strip()
    if not stripped:
        reason = reply.empty_reason
        final = reason in FINAL_EMPTY_REASONS
        raise InspectionReplyError(
            f"empty reply ({empty_reason_label(reason)})", final=final
        )
    data = _decode(stripped)
    if isinstance(data, dict):
        data = data.get("edits", [])
    if not isinstance(data, list):
        raise InspectionReplyError("model reply is not a list of edits")
    return data


def _decode(text: str) -> object:
    """Decode a non-empty reply as JSON, tolerating the model's usual slips.

    The repair runs before any strict decode: ``\\times`` or ``\\nu`` would
    decode strictly into control characters and never reach it. The error
    quotes a fragment, since the reply can hold the whole document.
    """
    repaired = _repair_reply_text(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as exc:
        raise InspectionReplyError(
            f"could not parse model reply as JSON: {exc} "
            f"(reply length {len(text)}, near position {exc.pos}: "
            f"{_error_fragment(repaired, exc.pos)!r})"
        ) from exc


def _error_fragment(text: str, pos: int) -> str:
    lo = max(0, pos - _ERROR_FRAGMENT_RADIUS)
    hi = min(len(text), pos + _ERROR_FRAGMENT_RADIUS)
    return text[lo:hi]


# Only free text copied from the scan can carry an unescaped quote.
_FREE_TEXT_FIELDS = frozenset({"old", "new"})


_CONTROL_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


# `\n` before a letter is `\nu` or `\nabla`; before anything else it is a break.
_WHITESPACE_ESCAPES = frozenset("nrt")


_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")


def _repair_reply_text(text: str) -> str:  # noqa: C901, PLR0912, PLR0915 -- one-pass character scanner; every branch reads and sets the same scan state
    """Repair a model reply so a strict JSON decoder accepts it.

    One scan fixes three slips: a stray LaTeX backslash is doubled, while
    ``\\n``, ``\\r``, ``\\t`` before a non-letter stay escapes; a raw control
    character is escaped; a quote inside ``old`` or ``new`` is escaped unless
    a real JSON continuation follows. A well-formed reply passes unchanged.
    """
    out: list[str] = []
    in_string = False
    is_key = False
    current_field: str | None = None
    key_chars: list[str] = []
    last_significant = ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
                is_key = last_significant in ("{", ",", "[")
                key_chars = []
            elif not ch.isspace():
                last_significant = ch
            i += 1
            continue
        if ch == '"':
            if is_key:
                out.append(ch)
                in_string = False
                current_field = "".join(key_chars)
                last_significant = '"'
                i += 1
                continue
            if current_field in _FREE_TEXT_FIELDS and not _looks_like_string_end(
                text, i + 1
            ):
                out.append('\\"')
                i += 1
                continue
            out.append(ch)
            in_string = False
            last_significant = '"'
            i += 1
            continue
        if ch == "\\":
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt in ('"', "\\", "/"):
                out.append(text[i : i + 2])
                if is_key:
                    key_chars.extend(text[i : i + 2])
                i += 2
                continue
            if nxt in _WHITESPACE_ESCAPES and not _LATIN_LETTER_RE.match(text, i + 2):
                # A whitespace escape, told from `\nu` or `\times` by the
                # letters that follow a command.
                out.append(text[i : i + 2])
                if is_key:
                    key_chars.extend(text[i : i + 2])
                i += 2
                continue
            if nxt == "u" and _is_hex4(text, i + 2):
                out.append(text[i : i + 6])
                if is_key:
                    key_chars.extend(text[i : i + 6])
                i += 6
                continue
            out.append("\\\\")
            if is_key:
                key_chars.append(ch)
            i += 1
            continue
        if ch in _CONTROL_ESCAPES:
            out.append(_CONTROL_ESCAPES[ch])
            if is_key:
                key_chars.append(ch)
            i += 1
            continue
        if ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
            if is_key:
                key_chars.append(ch)
            i += 1
            continue
        out.append(ch)
        if is_key:
            key_chars.append(ch)
        i += 1
    return "".join(out)


def _looks_like_string_end(text: str, pos: int) -> bool:
    """True when a JSON string could legitimately end right before `pos`.

    A ``}``, or a comma opening the next key: a quoted phrase's own comma is
    followed by a quote that opens no key.
    """
    j = pos
    n = len(text)
    while j < n and text[j] in " \t\r\n":
        j += 1
    if j >= n:
        return False
    if text[j] == "}":
        return True
    if text[j] == ",":
        j += 1
        while j < n and text[j] in " \t\r\n":
            j += 1
        return _starts_json_key(text, j)
    return False


def _starts_json_key(text: str, pos: int) -> bool:
    """True when a quoted JSON key, any key, begins at `pos`: a colon follows."""
    n = len(text)
    if pos >= n or text[pos] != '"':
        return False
    end = text.find('"', pos + 1)
    if end == -1:
        return False
    j = end + 1
    while j < n and text[j] in " \t\r\n":
        j += 1
    return j < n and text[j] == ":"


def _is_hex4(text: str, start: int) -> bool:
    quartet = text[start : start + 4]
    return len(quartet) == 4 and all(c in _HEX_DIGITS for c in quartet)


def _as_number(value: object) -> int | None:
    if isinstance(value, bool):  # bool is an int subclass; reject it explicitly
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
