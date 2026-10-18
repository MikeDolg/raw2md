import os
from typing import Callable, Dict, Optional

import torch


class Settings:
    # Fixed values: the engine reads no environment variable and no settings
    # file. The caller passes the device and the batch size.

    # General
    IMAGE_DPI: int = 96  # Used for detection, layout, reading order
    IN_STREAMLIT: bool = False  # Whether we're running in streamlit
    DISABLE_TQDM: bool = False  # Disable tqdm progress bars
    MODEL_DIR: Optional[str] = None  # Set by marker.models.create_model_dict
    LOGLEVEL: str = "INFO"  # Logging level

    @property
    def TORCH_DEVICE_MODEL(self) -> str:
        if torch.cuda.is_available():
            return "cuda"

        if torch.backends.mps.is_available():
            return "mps"

        try:
            import torch_xla

            if len(torch_xla.devices()) > 0:
                return "xla"
        except Exception:
            pass

        return "cpu"

    # Text detection
    DETECTOR_BATCH_SIZE: Optional[int] = None  # Defaults to 2 for CPU/MPS, 32 otherwise
    DETECTOR_MODEL_CHECKPOINT: str = "s3://text_detection/2025_05_07"
    DETECTOR_IMAGE_CHUNK_HEIGHT: int = (
        1400  # Height at which to slice images vertically
    )
    DETECTOR_TEXT_THRESHOLD: float = (
        0.6  # Threshold for text detection (above this is considered text)
    )
    DETECTOR_BLANK_THRESHOLD: float = (
        0.35  # Threshold for blank space (below this is considered blank)
    )
    DETECTOR_POSTPROCESSING_CPU_WORKERS: int = min(
        8, os.cpu_count()
    )  # Number of workers for postprocessing
    DETECTOR_MIN_PARALLEL_THRESH: int = (
        3  # Minimum number of images before we parallelize
    )
    DETECTOR_BOX_Y_EXPAND_MARGIN: float = (
        0.05  # Margin by which to expand detected boxes vertically
    )
    COMPILE_DETECTOR: bool = False

    # Text recognition
    FOUNDATION_MODEL_CHECKPOINT: str = "s3://text_recognition/2025_09_23"
    FOUNDATION_MAX_TOKENS: Optional[int] = None
    FOUNDATION_CHUNK_SIZE: Optional[int] = None
    FOUNDATION_PAD_TO_NEAREST: int = 256
    COMPILE_FOUNDATION: bool = False
    FOUNDATION_MULTI_TOKEN_MIN_CONFIDENCE: float = 0.9

    RECOGNITION_MODEL_CHECKPOINT: str = "s3://text_recognition/2025_09_23"
    RECOGNITION_BATCH_SIZE: Optional[int] = (
        None  # Defaults to 8 for CPU/MPS, 256 otherwise
    )
    RECOGNITION_PAD_VALUE: int = 255  # Should be 0 or 255

    # Layout
    LAYOUT_MODEL_CHECKPOINT: str = "s3://layout/2025_09_23"
    LAYOUT_BATCH_SIZE: Optional[int] = None

    # Table Rec
    TABLE_REC_MODEL_CHECKPOINT: str = "s3://table_recognition/2025_02_18"
    TABLE_REC_IMAGE_SIZE: Dict = {"height": 768, "width": 768}
    TABLE_REC_MAX_BOXES: int = 150
    TABLE_REC_BATCH_SIZE: Optional[int] = None
    COMPILE_TABLE_REC: bool = False

    # OCR Error Detection
    OCR_ERROR_MODEL_CHECKPOINT: str = "s3://ocr_error_detection/2025_02_18"
    OCR_ERROR_BATCH_SIZE: Optional[int] = None
    COMPILE_OCR_ERROR: bool = False

    COMPILE_ALL: bool = False

    @property
    def DETECTOR_STATIC_CACHE(self) -> bool:
        return (
            self.COMPILE_ALL
            or self.COMPILE_DETECTOR
            or self.TORCH_DEVICE_MODEL == "xla"
        )  # We need to static cache and pad to batch size for XLA, since it will recompile otherwise

    @property
    def FOUNDATION_XLA(self) -> bool:
        return (
            self.TORCH_DEVICE_MODEL == "xla"
        )  # We need to static cache and pad to batch size for XLA, since it will recompile otherwise

    @property
    def FOUNDATION_STATIC_CACHE(self) -> bool:
        return (
            self.COMPILE_ALL
            or self.COMPILE_FOUNDATION
            or self.TORCH_DEVICE_MODEL == "xla"
        )  # We need to static cache and pad to batch size for XLA, since it will recompile otherwise

    @property
    def TABLE_REC_STATIC_CACHE(self) -> bool:
        return (
            self.COMPILE_ALL
            or self.COMPILE_TABLE_REC
            or self.TORCH_DEVICE_MODEL == "xla"
        )

    @property
    def OCR_ERROR_STATIC_CACHE(self) -> bool:
        return (
            self.COMPILE_ALL
            or self.COMPILE_OCR_ERROR
            or self.TORCH_DEVICE_MODEL == "xla"
        )

    @property
    def MODEL_DTYPE(self) -> torch.dtype:
        if self.TORCH_DEVICE_MODEL == "cpu":
            return torch.float32
        if self.TORCH_DEVICE_MODEL == "xla":
            return torch.bfloat16
        return torch.float16

    @property
    def MODEL_DTYPE_BFLOAT(self) -> torch.dtype:
        if self.TORCH_DEVICE_MODEL == "cpu":
            return torch.float32
        if self.TORCH_DEVICE_MODEL == "mps":
            return torch.bfloat16
        return torch.bfloat16

    @property
    def INFERENCE_MODE(self) -> Callable:
        if self.TORCH_DEVICE_MODEL == "xla":
            return torch.no_grad
        return torch.inference_mode


settings = Settings()
