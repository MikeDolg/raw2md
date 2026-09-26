"""Shared path constants for synthesis scripts."""

from pathlib import Path

SYNTHESIS_DIR: Path = Path(__file__).parent
CORPUS_DIR: Path = SYNTHESIS_DIR.parent / "corpus"
ASSETS_DIR: Path = CORPUS_DIR / "assets"

# Committed Cyrillic handwriting font for synthesised pages.
FONTS_DIR: Path = ASSETS_DIR / "fonts"
HANDWRITING_FONT_NAME: str = "HansHand-cyr"
HANDWRITING_FONT_EXT: str = ".ttf"

# Fixed epoch makes xelatex embed a stable creation date in the PDF.
SOURCE_DATE_EPOCH: str = "1000000000"

RASTER_DPI: int = 150
