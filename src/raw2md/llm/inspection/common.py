"""What the inspection modules share: the operation, its result, an edit."""

from __future__ import annotations

from dataclasses import dataclass, field

from raw2md.llm.acceptance import TouchedLines
from raw2md.llm.base import DEFAULT_MAX_REQUEST_BYTES, Provider
from raw2md.llm.chunking import DEFAULT_CHUNK_TOKENS, DEFAULT_PAGES_PER_REQUEST

TRACE_OP = "inspection"


class InspectionReplyError(Exception):
    """The model's inspection reply could not be used as an edit list.

    An empty reply, one that will not decode even after repair, or one that
    is no edit list. `final` marks an empty reply a retry would reproduce.
    """

    def __init__(self, message: str, *, final: bool = False) -> None:
        super().__init__(message)
        self.final = final


@dataclass(frozen=True)
class InspectOperation:
    """A resolved inspection operation, built once per run.

    `token_budget`, `tpm`, `pages_per_request`, and `max_request_bytes` bound a
    request and pace the chunks. `latex_fix` opens every math span to a
    rewrite, and so also shows the sound spans the request otherwise masks.
    """

    provider: Provider
    prompt: str
    model_key: str
    token_budget: int = DEFAULT_CHUNK_TOKENS
    tpm: int | None = None
    pages_per_request: int = DEFAULT_PAGES_PER_REQUEST
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    latex_fix: bool = False


@dataclass(frozen=True)
class InspectResult:
    """Outcome of one inspection pass over a file.

    `skipped` counts edits whose `old` missed its address, a lost repair;
    `rejected` those the edit guard refused, a repair that would cost more than
    it fixed. `failure` is the refusal the run answers for, None when only
    coverage was lost. `chunks` is 0 for a single request; `skipped_chunks`
    counts chunks never answered in full. `touched` is recorded as the body is
    rebuilt, since a comparison cannot tell an edited line from a moved one.
    """

    body: str
    applied: int
    skipped: int
    rejected: int
    format_flags: int
    failure: Exception | None = None
    chunks: int = 0
    skipped_chunks: int = 0
    touched: TouchedLines = field(default_factory=TouchedLines)


@dataclass(frozen=True)
class SemanticEdit:
    page: int | None
    line: int
    old: str
    new: str
