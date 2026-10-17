from typing import List, Optional, Any

from pydantic import BaseModel

from raw2md_engine.surya.common.polygon import PolygonBox


class TextDetectionResult(BaseModel):
    bboxes: List[PolygonBox]
    heatmap: Optional[Any]
    affinity_map: Optional[Any]
    image_bbox: List[float]
