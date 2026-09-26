"""LLM provider layer and operations.

`base` defines the provider interface, the request parts, and the typed
runtime errors; concrete providers live in `gemini` and `claude`, and `factory`
builds one. Operations resolve a provider through settings, never by name.
`post`, `inspection`, and `ocr` are the operations built on this layer;
`edit_guard` bounds what an applied inspection edit may change.
"""

from raw2md.llm.base import (
    AuthError,
    Availability,
    ConnectionDroppedError,
    DailyQuotaExceededError,
    DocumentTooLargeError,
    MediaPart,
    Part,
    Provider,
    ProviderError,
    RateLimitError,
    TextPart,
    TransientError,
)
from raw2md.llm.claude import ClaudeCliProvider
from raw2md.llm.factory import build_provider
from raw2md.llm.gemini import GeminiApiProvider
from raw2md.llm.inspection.common import InspectOperation, InspectResult
from raw2md.llm.inspection.coordinator import inspect
from raw2md.llm.ocr import OcrOperation, OcrResult, recognize
from raw2md.llm.post.common import PostOperation
from raw2md.llm.post.coordinator import PostResult, post_process

__all__ = [
    "AuthError",
    "Availability",
    "ClaudeCliProvider",
    "ConnectionDroppedError",
    "DailyQuotaExceededError",
    "DocumentTooLargeError",
    "GeminiApiProvider",
    "InspectOperation",
    "InspectResult",
    "MediaPart",
    "OcrOperation",
    "OcrResult",
    "Part",
    "PostOperation",
    "PostResult",
    "Provider",
    "ProviderError",
    "RateLimitError",
    "TextPart",
    "TransientError",
    "build_provider",
    "inspect",
    "post_process",
    "recognize",
]
