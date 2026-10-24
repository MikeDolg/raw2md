from typing import Any

from pydantic import BaseModel

from raw2md_engine.surya.common.polygon import PolygonBox


class TextDetectionResult(BaseModel):
    bboxes: list[PolygonBox]
    heatmap: Any | None
    affinity_map: Any | None
    image_bbox: list[float]
