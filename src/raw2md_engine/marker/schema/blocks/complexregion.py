from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block


class ComplexRegion(Block):
    block_type: BlockTypes = BlockTypes.ComplexRegion
    html: str | None = None
    block_description: str = "A complex region that can consist of multiple different types of blocks mixed with images. This block is chosen when it is difficult to categorize the region as a single block type."

    def assemble_html(self, document, child_blocks, parent_structure, block_config):
        if self.html:
            html = super().assemble_html(document, [], parent_structure, block_config)
            return html + self.html
        template = super().assemble_html(
            document, child_blocks, parent_structure, block_config
        )
        return f"<p>{template}</p>"
