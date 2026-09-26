"""The context object the cleaning passes read beyond the markdown itself."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from raw2md.cleaning.ocr import DEFAULT_WITNESS_MIN
from raw2md.header import ConversionMethod
from raw2md.keywords import Keywords, default_keywords
from raw2md.source_outline import SourceOutline
from raw2md.source_text import SourceText


@dataclass(frozen=True)
class CleanOptions:
    """Context the cleaning passes read beyond the markdown text.

    `base_dir` resolves image links; without it links are not checked. With
    `disable_image_extraction` a link to a missing image is removed, not
    reported. `method` is the route the body came from; only heading recovery
    reads it, and ``None`` disables that recovery. `llm_ocr` marks a body that
    LLM-OCR recognized: the route extracts no media, so any image link is
    fabricated. `source_text` and `outline` are the source's own text layer and
    outline; their empty defaults confirm nothing, so a rule stays conservative.
    `witness_min` is the attestation threshold of `repair_attested_tokens`.
    """

    base_dir: Path | None = None
    disable_image_extraction: bool = False
    method: ConversionMethod | None = None
    llm_ocr: bool = False
    source_text: SourceText = field(default_factory=SourceText.empty)
    outline: SourceOutline = field(default_factory=SourceOutline.empty)
    witness_min: int = DEFAULT_WITNESS_MIN
    keywords: Keywords = field(default_factory=default_keywords)
