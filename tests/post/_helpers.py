"""Fakes and builders the post test modules share.

Plain functions rather than `conftest` fixtures, so they stay under the strict
type check.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace

from raw2md.llm.base import (
    Availability,
    Part,
    Provider,
    Reply,
    TextPart,
)
from raw2md.llm.post.common import MAX_REPLY_CHARS, PostOperation
from raw2md.settings import ModelConfig

_MODEL = ModelConfig(
    access="cli",
    model="fake",
    key_env=None,
    command="fake",
    rpm=None,
    tpm=None,
    rpd=None,
)


class FakeProvider(Provider):
    """Provider returning queued replies in order; an Exception reply is raised."""

    def __init__(
        self, replies: Sequence[str | Exception], model: ModelConfig = _MODEL
    ) -> None:
        super().__init__(model)
        self._replies = list(replies)
        self.calls: list[tuple[str, tuple[Part, ...]]] = []

    def available(self) -> Availability:
        return Availability(True)

    def generate(self, prompt: str, parts: Sequence[Part] = ()) -> str:
        self.calls.append((prompt, tuple(parts)))
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class SchemaProvider(FakeProvider):
    """A provider that takes a response schema; records each one it is given."""

    def __init__(self, replies: Sequence[str | Exception]) -> None:
        super().__init__(replies)
        self.schemas: list[Mapping[str, object] | None] = []

    def generate_reply(
        self,
        prompt: str,
        parts: Sequence[Part] = (),
        *,
        response_schema: Mapping[str, object] | None = None,
    ) -> Reply:
        self.schemas.append(response_schema)
        return Reply(self.generate(prompt, parts))


def make_op(
    replies: Sequence[str | Exception], *, max_request_bytes: int | None = None
) -> PostOperation:
    model = (
        _MODEL
        if max_request_bytes is None
        else replace(_MODEL, max_request_bytes=max_request_bytes)
    )
    return PostOperation(
        provider=FakeProvider(replies, model), prompt="FIX", model_key="fake"
    )


def sent_text(op: PostOperation, call: int = 0) -> str:
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    parts = provider.calls[call][1]
    return "\n".join(p.text for p in parts if isinstance(p, TextPart))


def call_count(op: PostOperation) -> int:
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    return len(provider.calls)


def call_parts(op: PostOperation, call: int) -> tuple[Part, ...]:
    provider = op.provider
    assert isinstance(provider, FakeProvider)
    return provider.calls[call][1]


def reason_text(op: PostOperation, call: int = 1) -> str:
    """The retry-note part of a call, isolated from the repeated zone text."""
    text_parts = [p.text for p in call_parts(op, call) if isinstance(p, TextPart)]
    return text_parts[-1]


# A formula the renderer refuses; the tests take it for any block zone.
ZONE = [r"Hence $$E = \frac{mv^2}{2$$ for any $v$."]
ZONE_FIXED = r"Hence $$E = \frac{mv^2}{2}$$ for any $v$."


def join_blocks(*blocks: list[str]) -> str:
    """Join line blocks with a blank separator, ending in a trailing newline."""
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"


BROKEN_TABLE_ZONE = [
    "| A | B |",
    "| --- | --- |",
    "| x |",
]


# Row 3 gains the cell its separator declares.
ROW_FIX = '{"rows": [{"row": 3, "text": "| x |  |"}]}'


def rows_reply(*rows: tuple[int, str]) -> str:
    """A row-indexed reply naming each `(index, text)` pair."""
    return json.dumps({"rows": [{"row": row, "text": text} for row, text in rows]})


def wide_zone() -> tuple[list[str], str]:
    """A table whose six repairable rows need three requests, and their fix."""
    wide = ("value " * (MAX_REPLY_CHARS // 14)).strip()
    body_rows = [f"| {wide} |" for _ in range(6)]  # width 1, every one repairable
    zone = ["| A | B |", "| --- | --- |", *body_rows]
    return zone, f"| {wide} |  |"


def runs_reply(*closed: tuple[int, str]) -> str:
    """The JSON run list a spacing zone is answered with."""
    return json.dumps({"runs": [{"run": n, "text": text} for n, text in closed]})
