"""Conversion engines behind a common interface.

The engines are marker, pandoc, and djvu. `pymupdf` is a shared analysis
helper, not an engine, so it is not re-exported here. `preflight` holds the
checks that run before an engine opens a source.
"""

from raw2md.engines.base import (
    ConversionError,
    ConversionResult,
    ConvertOptions,
    Engine,
    EngineError,
    EngineNotFoundError,
    EngineRegistry,
    EngineUnavailableError,
    normalize_extension,
)
from raw2md.engines.djvu import DjvuEngine
from raw2md.engines.marker import MarkerEngine
from raw2md.engines.pandoc import PandocEngine
from raw2md.engines.preflight import check_source
from raw2md.engines.signature import check_signature

__all__ = [
    "ConversionError",
    "ConversionResult",
    "ConvertOptions",
    "DjvuEngine",
    "Engine",
    "EngineError",
    "EngineNotFoundError",
    "EngineRegistry",
    "EngineUnavailableError",
    "MarkerEngine",
    "PandocEngine",
    "check_signature",
    "check_source",
    "normalize_extension",
]
