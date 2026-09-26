"""Fakes, builders, and bodies the inspection test modules share.

Plain functions rather than `conftest` fixtures, so they stay under the strict
type check.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import pytest

from raw2md.llm.base import (
    Availability,
    MediaPart,
    Part,
    Provider,
    Reply,
    TextPart,
)
from raw2md.llm.inspection.common import InspectOperation
from raw2md.settings import ModelConfig

_MODEL = ModelConfig(
    access="api",
    model="fake",
    key_env="FAKE_KEY",
    command=None,
    rpm=None,
    tpm=None,
    rpd=None,
)

SOURCE = MediaPart(b"%PDF-1.4 stub", "application/pdf")

# Spelled out: in the source it looks like a plain hyphen.
NON_BREAKING_HYPHEN = "\u2011"

# A sound math span is shown in the request as a numbered placeholder.
MASK_BRACKET = "\u27e6"


def mask(number: int = 1) -> str:
    return f"\u27e6valid formula {number}\u27e7"


class FakeProvider(Provider):
    """Provider returning queued replies in call order; an Exception is raised.

    A single reply, not a sequence, answers every call.
    """

    def __init__(self, reply: str | Exception | list[str | Exception]) -> None:
        super().__init__(_MODEL)
        self._replies: list[str | Exception] = (
            reply if isinstance(reply, list) else [reply]
        )
        self.calls: list[tuple[str, tuple[Part, ...]]] = []

    def available(self) -> Availability:
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        self.calls.append((prompt, tuple(parts)))
        reply = self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_op(
    reply: str | Exception | list[str | Exception], *, latex_fix: bool = False
) -> InspectOperation:
    return InspectOperation(
        provider=FakeProvider(reply),
        prompt="INSPECT",
        model_key="fake",
        latex_fix=latex_fix,
    )


class SchemaProvider(Provider):
    """A provider that takes a response schema and records the one it was given.

    Replies may carry an empty-reply reason, which `generate` cannot return.
    """

    def __init__(
        self, reply: str | Exception | Reply | list[str | Exception | Reply]
    ) -> None:
        super().__init__(_MODEL)
        self._replies: list[str | Exception | Reply] = (
            reply if isinstance(reply, list) else [reply]
        )
        self.calls: list[tuple[str, tuple[Part, ...], Mapping[str, object] | None]] = []

    def available(self) -> Availability:
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        return self.generate_reply(prompt, parts).text

    def generate_reply(
        self,
        prompt: str,
        parts: Sequence[Part] = (),
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> Reply:
        self.calls.append((prompt, tuple(parts), response_schema))
        reply = self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, Reply):
            return reply
        return Reply(reply)


def make_schema_op(
    reply: str | Exception | Reply | list[str | Exception | Reply],
) -> InspectOperation:
    return InspectOperation(
        provider=SchemaProvider(reply), prompt="INSPECT", model_key="fake"
    )


def sent_text(op: InspectOperation) -> str:
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    parts = provider.calls[0][1]
    return "\n".join(p.text for p in parts if isinstance(p, TextPart))


def sent_media(op: InspectOperation) -> list[MediaPart]:
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    return [p for p in provider.calls[0][1] if isinstance(p, MediaPart)]


def edits_reply(*entries: dict[str, object]) -> str:
    return json.dumps({"edits": list(entries)})


# A body whose third line carries an OCR-marker word for a semantic fix.
MARKER_BODY = "\n".join(
    [
        "# Heading",
        "",
        "Here the [unreadable] word is lost.",
        "",
        "Another paragraph.",
        "",
    ]
)

# A broken pipe table: the body row has one cell against a two-column header.
TABLE_BODY = "\n".join(["| A | B |", "| --- | --- |", "| x |", ""])

# A table row whose cells the layout crushed onto one line.
CRUSHED_ROW = (
    "Width 10 Height 20 Length 30 Diameter 40 Width 11 Height 21 "
    "Length 31 Diameter 41 Width 12 Height 22 Length 32 Diameter 42"
)

# Gemini echoes these backslashes unescaped in `old`/`new`.
LATEX_BODY = "\n".join(
    ["# Heading", "", r"Let \(\alpha\) and \left( x \right) be given.", "", "End.", ""]
)

# Every command starts with a JSON escape letter, so a strict decode corrupts it.
CONTROL_LATEX_BODY = "\n".join(
    ["# Heading", "", r"Sum: \beta \to \nu at \right.", "", "End.", ""]
)

# Tests with this body write `\uXXXX` in place of the command backslash.
CONTROL_CHAR_BODY = "\n".join(
    ["# Title", "", r"Given \beta, \forall x and \vec{v}.", "", "End.", ""]
)

# Sub-figure labels in straight quotes, echoed unescaped inside `old`.
QUOTED_LABEL_BODY = "\n".join(
    ["# Heading", "", '**Fig. 2** "a" first, "b" second.', "", "End.", ""]
)

# The comma after the closing quote belongs to the sentence, not to JSON.
QUOTED_PHRASE_BODY = "\n".join(
    [
        "# Heading",
        "",
        'See the chapter "general installation instructions", then proceed.',
        "",
        "End.",
        "",
    ]
)

# The quote after "A" is followed by a comma and another quote.
QUOTED_LIST_BODY = "\n".join(
    ["# Heading", "", 'Options: "A", "B", and "C".', "", "End.", ""]
)

# An unsupported `\mbox` and a dropped `\right`.
MATH_DAMAGE_BODY = "\n".join(
    ["# Heading", "", r"The value $\mbox{E} = \left( x$ is found.", "", "End.", ""]
)

# One display formula cut into a damaged span per line.
FORMULA_PIECES = [
    r"$$S = \frac{1}{2}\left[\left(\begin{aligned} p_{k}\right)^2$$",
    r"$$+ \left(q_{k}\right)^2\right]$$",
    r"$$+ \frac{1}{2}\left[\left(p_{m}\right)^2$$",
    r"$$+ \left(q_{m}\right)^2\right]$$",
]

# The pieces balance as one, though none balances alone.
REPAIRED_PIECES = [
    r"$$S = \frac{1}{2}\left[\left(p_{k}\right)^2$$",
    *FORMULA_PIECES[1:],
]

SPLIT_FORMULA_BODY = "\n".join(
    [
        "# Heading",
        "",
        *[line for piece in FORMULA_PIECES for line in (piece, "")],
        "End.",
        "",
    ]
)


SOUND_FORMULA_BODY = "\n".join(
    [
        "# Heading",
        "",
        "The moment $M_{yn1}$ is set.",
        "",
        "$$E = mc^2$$",
        "",
        "End.",
        "",
    ]
)

# The span parses and renders; only the source page shows the wrong index.
FLAGGED_FORMULA_BODY = "\n".join(
    ["# Heading", "", "The moment $M_{yn1}$ is set.", "", "End.", ""]
)


def skip_reason(caplog: pytest.LogCaptureFixture) -> str:
    """The one skip line the run logged."""
    messages = [r.message for r in caplog.records if "skip semantic edit" in r.message]
    assert len(messages) == 1
    return messages[0]
