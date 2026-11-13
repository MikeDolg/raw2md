from bisect import bisect_left, bisect_right
from typing import Annotated

from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block
from raw2md_engine.marker.schema.document import Document
from raw2md_engine.marker.schema.groups.page import PageGroup

Frame = tuple[float, float, float, float]


class ImageFurnitureProcessor(BaseProcessor):
    """
    Hides a picture that repeats at one place in the top or the bottom band of
    the pages: a logo or an ornament of the running header or footer.
    The block stays in the document; the renderer neither shows nor saves it.
    """

    block_types = (BlockTypes.Picture, BlockTypes.Figure)
    band: Annotated[
        float,
        "The height of the top and of the bottom band, as a share of the page height.",
        "A picture repeats as furniture only when its whole frame lies in one band.",
    ] = 0.15
    min_pages: Annotated[
        int,
        "The number of pages, the own page included, that hold a picture at the place of a picture that is furniture.",
    ] = 3
    frame_tolerance: Annotated[
        float,
        "The largest difference of each edge of two frames at one place, as a share of the page side.",
    ] = 0.015

    def __call__(self, document: Document):
        candidates: list[tuple[Frame, int, Block]] = []
        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                frame = self.relative_frame(page, block)
                if self.in_band(frame):
                    candidates.append((frame, page.page_id, block))

        # Sorted by the top edge, so each frame compares only with the frames
        # whose top edge lies within the tolerance.
        candidates.sort(key=lambda candidate: candidate[0][1])
        tops = [frame[1] for frame, _, _ in candidates]
        for frame, _, block in candidates:
            start = bisect_left(tops, frame[1] - self.frame_tolerance)
            end = bisect_right(tops, frame[1] + self.frame_tolerance)
            pages = {
                page_id
                for other, page_id, _ in candidates[start:end]
                if self.same_place(frame, other)
            }
            if len(pages) >= self.min_pages:
                block.ignore_for_output = True

    @staticmethod
    def relative_frame(page: PageGroup, block: Block) -> Frame:
        x0, y0, x1, y1 = block.polygon.bbox
        left, top = page.polygon.x_start, page.polygon.y_start
        width, height = page.polygon.width, page.polygon.height
        return (
            (x0 - left) / width,
            (y0 - top) / height,
            (x1 - left) / width,
            (y1 - top) / height,
        )

    def in_band(self, frame: Frame) -> bool:
        return frame[3] <= self.band or frame[1] >= 1 - self.band

    def same_place(self, frame: Frame, other: Frame) -> bool:
        return all(
            abs(edge - other_edge) <= self.frame_tolerance
            for edge, other_edge in zip(frame, other, strict=True)
        )
