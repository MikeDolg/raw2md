# Modified by the raw2md authors. See NOTICE.
from __future__ import annotations

from typing import Any, TypedDict


class Bbox:
    def __init__(self, bbox: list[float], ensure_nonzero_area=False):
        if ensure_nonzero_area:
            bbox = list(bbox)
            bbox[2] = max(bbox[0], bbox[2] + 1)
            bbox[3] = max(bbox[1], bbox[3] + 1)
        self.bbox = bbox
        self.ensure_nonzero_area = ensure_nonzero_area

    def __getitem__(self, item):
        return self.bbox[item]

    def __repr__(self):
        return f"Bbox({self.bbox})"

    @property
    def height(self):
        return self.bbox[3] - self.bbox[1]

    @property
    def width(self):
        return self.bbox[2] - self.bbox[0]

    @property
    def area(self):
        return self.width * self.height

    @property
    def center(self):
        return [(self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2]

    @property
    def size(self):
        return [self.width, self.height]

    @property
    def x_start(self):
        return self.bbox[0]

    @property
    def y_start(self):
        return self.bbox[1]

    @property
    def x_end(self):
        return self.bbox[2]

    @property
    def y_end(self):
        return self.bbox[3]

    def merge(self, other: Bbox) -> Bbox:
        self_bbox = self.bbox
        other_bbox = other.bbox
        return Bbox(
            [
                min(self_bbox[0], other_bbox[0]),
                min(self_bbox[1], other_bbox[1]),
                max(self_bbox[2], other_bbox[2]),
                max(self_bbox[3], other_bbox[3]),
            ]
        )

    def overlap_x(self, other: Bbox):
        return max(
            0, min(self.bbox[2], other.bbox[2]) - max(self.bbox[0], other.bbox[0])
        )

    def overlap_y(self, other: Bbox):
        return max(
            0, min(self.bbox[3], other.bbox[3]) - max(self.bbox[1], other.bbox[1])
        )

    def intersection_area(self, other: Bbox):
        return self.overlap_x(other) * self.overlap_y(other)

    def intersection_pct(self, other: Bbox):
        if self.area == 0:
            return 0

        intersection = self.intersection_area(other)
        return intersection / self.area

    def rotate(self, page_width: float, page_height: float, rotation: int) -> Bbox:
        if rotation not in [0, 90, 180, 270]:
            raise ValueError("Rotation must be one of [0, 90, 180, 270] degrees.")

        x_min, y_min, x_max, y_max = self.bbox

        if rotation == 0:
            return Bbox(self.bbox)
        if rotation == 90:
            new_x_min = page_height - y_max
            new_y_min = x_min
            new_x_max = page_height - y_min
            new_y_max = x_max
        elif rotation == 180:
            new_x_min = page_width - x_max
            new_y_min = page_height - y_max
            new_x_max = page_width - x_min
            new_y_max = page_height - y_min
        elif rotation == 270:
            new_x_min = y_min
            new_y_min = page_width - x_max
            new_x_max = y_max
            new_y_max = page_width - x_min

        # Ensure that x_min < x_max and y_min < y_max
        rotated_bbox = (
            min(new_x_min, new_x_max),
            min(new_y_min, new_y_max),
            max(new_x_min, new_x_max),
            max(new_y_min, new_y_max),
        )

        return Bbox(rotated_bbox)

    def rescale(self, img_size: list[int], page: Page) -> Bbox:
        w_scale = img_size[0] / page["width"]
        h_scale = img_size[1] / page["height"]
        new_bbox = [
            self.bbox[0] * w_scale,
            self.bbox[1] * h_scale,
            self.bbox[2] * w_scale,
            self.bbox[3] * h_scale,
        ]

        return Bbox(new_bbox)


class Char(TypedDict):
    bbox: Bbox
    char: str
    rotation: float
    font: dict[str, Any | str]
    char_idx: int


class Span(TypedDict):
    bbox: Bbox
    text: str
    font: dict[str, Any | str]
    chars: list[Char]
    char_start_idx: int
    char_end_idx: int
    rotation: int
    url: str
    superscript: bool
    subscript: bool


class Line(TypedDict):
    spans: list[Span]
    bbox: Bbox
    rotation: int


class Block(TypedDict):
    lines: list[Line]
    bbox: Bbox
    rotation: int


class Page(TypedDict):
    page: int
    bbox: Bbox
    width: int
    height: int
    blocks: list[Block]
    rotation: int


class TableCell(TypedDict):
    text: str
    bbox: Bbox


class TableInput(TypedDict):
    tables: list[list[int]]
    img_size: list[int]


class Link(TypedDict):
    page: int
    bbox: list[float]
    url: str | None


Chars = list[Char]
Spans = list[Span]
Lines = list[Line]
Blocks = list[Block]
Pages = list[Page]
Tables = list[list[TableCell]]
TableInputs = list[TableInput]
