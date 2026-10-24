from typing import Optional, Tuple

from pydantic import BaseModel

from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.document import Document
from raw2md_engine.marker.util import assign_config


class BaseProcessor:
    block_types: tuple[BlockTypes] | None = (
        None  # What block types this processor is responsible for
    )

    def __init__(self, config: BaseModel | dict | None = None):
        assign_config(self, config)

    def __call__(self, document: Document, *args, **kwargs):
        raise NotImplementedError
