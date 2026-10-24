from pydantic import BaseModel

from raw2md_engine.surya.common.polygon import PolygonBox


class LayoutBox(PolygonBox):
    label: str
    position: int
    top_k: dict[str, float] | None = None


class LayoutResult(BaseModel):
    bboxes: list[LayoutBox]
    image_bbox: list[float]
    sliced: bool = False  # Whether the image was sliced and reconstructed
