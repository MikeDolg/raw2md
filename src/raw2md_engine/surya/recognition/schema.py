import math

import numpy as np
from pydantic import BaseModel, field_validator

from raw2md_engine.surya.common.polygon import PolygonBox


class BaseChar(PolygonBox):
    text: str
    confidence: float | None = 0

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if v is None or math.isnan(v) or np.isnan(v):
            return 0
        return v


class TextChar(BaseChar):
    bbox_valid: bool = True  # This is false when the given bbox is not valid


class TextWord(BaseChar):
    bbox_valid: bool = True


class TextLine(BaseChar):
    chars: list[TextChar]  # Individual characters in the line
    original_text_good: bool = False
    words: list[TextWord] | None = None


class OCRResult(BaseModel):
    text_lines: list[TextLine]
    image_bbox: list[float]
