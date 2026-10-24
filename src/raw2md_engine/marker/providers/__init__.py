from copy import deepcopy
from typing import Dict, List, Optional

from PIL import Image
from pydantic import BaseModel

from raw2md_engine.marker.logger import configure_logging
from raw2md_engine.marker.schema.polygon import PolygonBox
from raw2md_engine.marker.schema.text import Span
from raw2md_engine.marker.schema.text.char import Char
from raw2md_engine.marker.schema.text.line import Line
from raw2md_engine.marker.util import assign_config

configure_logging()


class ProviderOutput(BaseModel):
    line: Line
    spans: list[Span]
    chars: list[list[Char]] | None = None

    @property
    def raw_text(self):
        return "".join(span.text for span in self.spans)

    def __hash__(self):
        return hash(tuple(self.line.polygon.bbox))

    def merge(self, other: "ProviderOutput"):
        new_output = deepcopy(self)
        other_copy = deepcopy(other)

        new_output.spans.extend(other_copy.spans)
        if new_output.chars is not None and other_copy.chars is not None:
            new_output.chars.extend(other_copy.chars)
        elif other_copy.chars is not None:
            new_output.chars = other_copy.chars

        new_output.line.polygon = new_output.line.polygon.merge(
            [other_copy.line.polygon]
        )
        return new_output


ProviderPageLines = dict[int, list[ProviderOutput]]


class BaseProvider:
    def __init__(self, filepath: str, config: BaseModel | dict | None = None):
        assign_config(self, config)
        self.filepath = filepath

    def __len__(self):
        pass

    def get_images(self, idxs: list[int], dpi: int) -> list[Image.Image]:
        pass

    def get_page_bbox(self, idx: int) -> PolygonBox | None:
        pass

    def get_page_lines(self, idx: int) -> list[Line]:
        pass

    def __enter__(self):
        return self
