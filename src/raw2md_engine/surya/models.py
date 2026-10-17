from typing import Dict

import torch

from raw2md_engine.surya.common.predictor import BasePredictor
from raw2md_engine.surya.detection import DetectionPredictor
from raw2md_engine.surya.layout import LayoutPredictor
from raw2md_engine.surya.logging import configure_logging
from raw2md_engine.surya.ocr_error import OCRErrorPredictor
from raw2md_engine.surya.foundation import FoundationPredictor
from raw2md_engine.surya.recognition import RecognitionPredictor
from raw2md_engine.surya.table_rec import TableRecPredictor
from raw2md_engine.surya.settings import settings

configure_logging()


def load_predictors(
    device: str | torch.device | None = None, dtype: torch.dtype | str | None = None
) -> Dict[str, BasePredictor]:
    return {
        "layout": LayoutPredictor(FoundationPredictor(checkpoint=settings.LAYOUT_MODEL_CHECKPOINT)),
        "ocr_error": OCRErrorPredictor(device=device, dtype=dtype),
        "recognition": RecognitionPredictor(FoundationPredictor(checkpoint=settings.RECOGNITION_MODEL_CHECKPOINT)),
        "detection": DetectionPredictor(device=device, dtype=dtype),
        "table_rec": TableRecPredictor(device=device, dtype=dtype),
    }
