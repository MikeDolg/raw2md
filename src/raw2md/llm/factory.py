"""Provider construction from a settings model.

Kept apart from `base`, which holds the contracts the concrete providers
implement; only this module knows the concrete classes.
"""

from __future__ import annotations

from raw2md.llm.base import Provider
from raw2md.llm.claude import ClaudeCliProvider
from raw2md.llm.gemini import GeminiApiProvider
from raw2md.settings import ModelConfig


def build_provider(model: ModelConfig) -> Provider:
    """Return the provider for a settings model, dispatched by access type.

    Never by model name, so a new model is added through settings, not code.
    """
    if model.access == "api":
        return GeminiApiProvider(model)
    if model.access == "cli":
        return ClaudeCliProvider(model)
    # Guards an access type added to settings without a provider.
    raise ValueError(f"unknown access type '{model.access}'")
