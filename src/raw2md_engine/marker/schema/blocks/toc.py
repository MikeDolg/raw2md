from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks.basetable import BaseTable


class TableOfContents(BaseTable):
    block_type: str = BlockTypes.TableOfContents
    block_description: str = "A table of contents."
