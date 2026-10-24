from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block


class Figure(Block):
    block_type: BlockTypes = BlockTypes.Figure
    description: str | None = None
    html: str | None = None
    block_description: str = "A chart or other image that contains data."

    def assemble_html(
        self, document, child_blocks, parent_structure, block_config=None
    ):
        if self.html:
            return super().handle_html_output(
                document, child_blocks, parent_structure, block_config
            )

        html = super().assemble_html(document, [], parent_structure, block_config)
        if self.description:
            html += f"<p role='img' data-original-image-id='{self.id}'>Image {self.id} description: {self.description}</p>"
        return html
