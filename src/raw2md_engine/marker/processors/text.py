import math
from typing import Annotated

import regex

from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block
from raw2md_engine.marker.schema.document import Document

# A sentence mark, optionally followed by closing quotes and brackets.
_SENTENCE_END = regex.compile(
    r"[.!?…:;。．｡！？：；]"
    r"[\p{Pe}\p{Pf}\"'＂＇]*$"
)
_WORD_HYPHEN = regex.compile(r"\p{L}[-¬]$")
_LINE_BREAK_MARK = regex.compile(r"[\p{Ll}\d][-—¬]$")
_LOWERCASE_START = regex.compile(r"^\p{Ll}")
# A lowercase letter that opens an item, as in `a)` or `b. `, starts no word.
_ITEM_LETTER = regex.compile(r"^\p{Ll}(\)|\.\s)")


class TextProcessor(BaseProcessor):
    """
    A processor for merging text across pages and columns.
    """

    block_types = (BlockTypes.Text, BlockTypes.TextInlineMath)
    ignored_block_types = (BlockTypes.PageHeader, BlockTypes.PageFooter)
    # Blocks that can stand between the halves of a cut paragraph; the joined
    # paragraph renders before them.
    stepped_block_types = (
        BlockTypes.Picture,
        BlockTypes.Figure,
        BlockTypes.PictureGroup,
        BlockTypes.FigureGroup,
        BlockTypes.Caption,
        BlockTypes.Footnote,
    )
    column_gap_ratio: Annotated[
        float,
        "The minimum ratio of the page width to the column gap to consider a column break.",
    ] = 0.02

    def __init__(self, config):
        super().__init__(config)

    def __call__(self, document: Document):
        # All joins are found on the reading order of the layout, before any
        # block moves.
        joins: list[tuple[Block, Block, list[Block]]] = []
        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                if block.structure is None:
                    continue
                found = self.find_second_half(document, block)
                if found is None:
                    continue
                next_block, between = found
                if self.continues(document, block, next_block, between):
                    block.has_continuation = True
                    joins.append((block, next_block, between))

        # A second half that does not follow its first half directly moves
        # behind it, so the halves render as one paragraph within one page.
        moved: set = set()
        for block, next_block, between in joins:
            if between or next_block.page_id != block.page_id or block.id in moved:
                self.move_after(document, next_block, block)
                moved.add(next_block.id)

    def find_second_half(
        self, document: Document, block: Block
    ) -> tuple[Block, list[Block]] | None:
        between: list[Block] = []
        candidate = document.get_next_block(block)
        while candidate is not None and (
            candidate.block_type in self.ignored_block_types
            or candidate.block_type in self.stepped_block_types
            or candidate.ignore_for_output
        ):
            between.append(candidate)
            candidate = document.get_next_block(candidate)
        if candidate is None or candidate.block_type not in self.block_types:
            return None
        if candidate.structure is None:
            return None
        return candidate, between

    def renders(self, block: Block) -> bool:
        return block.block_type in self.stepped_block_types and not (
            block.ignore_for_output
        )

    def continues(
        self,
        document: Document,
        block: Block,
        next_block: Block,
        between: list[Block],
    ) -> bool:
        first_text = block.raw_text(document).rstrip()
        second_text = next_block.raw_text(document).lstrip()
        text_evidence = bool(_WORD_HYPHEN.search(first_text)) or bool(
            first_text
            and not _SENTENCE_END.search(first_text)
            and _LOWERCASE_START.match(second_text)
            and not _ITEM_LETTER.match(second_text)
        )

        column_gap = block.polygon.width * self.column_gap_ratio
        column_break, page_break, figure_cut = False, False, False
        next_block_in_first_quadrant = False
        if next_block.page_id == block.page_id:
            column_break = math.floor(next_block.polygon.y_start) <= math.ceil(
                block.polygon.y_start
            ) and next_block.polygon.x_start > (block.polygon.x_end + column_gap)
            figure_cut = any(self.renders(b) for b in between)
        else:
            page_break = True
            next_page = document.get_page(next_block.page_id)
            next_block_in_first_quadrant = (
                next_block.polygon.x_start < next_page.polygon.width // 2
            ) and (next_block.polygon.y_start < next_page.polygon.height // 2)

        next_lines = next_block.line_polygons(document)
        next_block_starts_indented = True
        if next_lines:
            min_x = math.ceil(min(line.x_start for line in next_lines))
            next_block_starts_indented = next_lines[0].x_start > min_x
        if next_block_starts_indented:
            return False

        if text_evidence:
            return page_break or column_break or figure_cut

        all_lines = block.line_polygons(document)
        if len(all_lines) < 2:
            return False
        lines = [line for line in all_lines if line.width > 1]
        last_line_is_full_width = False
        if lines:
            max_x = math.floor(max(line.x_end for line in lines))
            last_line_is_full_width = lines[-1].x_end >= max_x
        last_line_is_broken = bool(_LINE_BREAK_MARK.search(first_text))
        return (last_line_is_full_width or last_line_is_broken) and (
            (next_block_in_first_quadrant and page_break) or column_break
        )

    @staticmethod
    def move_after(document: Document, block: Block, anchor: Block):
        # The block can move into the structure of an earlier page; it keeps
        # its own page id.
        for page in document.pages:
            if page.structure and block.id in page.structure:
                page.structure.remove(block.id)
        for page in document.pages:
            if page.structure and anchor.id in page.structure:
                page.structure.insert(page.structure.index(anchor.id) + 1, block.id)
                return
