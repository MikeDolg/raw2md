from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block


class Equation(Block):
    block_type: BlockTypes = BlockTypes.Equation
    html: str | None = None
    block_description: str = "A block math equation."

    def assemble_html(
        self, document, child_blocks, parent_structure=None, block_config=None
    ):
        if self.html:
            html_out = super().assemble_html(
                document, [], parent_structure, block_config
            )
            html_out += f"""<p block-type='{self.block_type}'>{self.html}</p>"""
            return html_out
        else:
            template = super().assemble_html(
                document, child_blocks, parent_structure, block_config
            )
            return f"<p block-type='{self.block_type}'>{template}</p>"
