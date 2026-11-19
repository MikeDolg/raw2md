import math
import statistics
from typing import Annotated

import regex

from raw2md.mdtext.seams import (
    continues_without_case,
    first_half_runs_on,
    second_half_runs_on,
)
from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block
from raw2md_engine.marker.schema.document import Document

_WORD_HYPHEN = regex.compile(r"\p{L}[-¬]$")
_LINE_BREAK_MARK = regex.compile(r"[\p{Ll}\d][-—¬]$")
# A label and a number that open a caption, as in `Fig. 14` or `Probl. 2.43`.
_LABEL_NUMBER = regex.compile(r"^\p{Lu}\p{L}{0,11}\.?\s*\d+(?:\.\d+)*")
# A TeX command such as `\theta` is no word.
_WORD = regex.compile(r"(?<![\\\p{L}])\p{L}{3,}")
# A text block on this many pages is a running line or a watermark, not prose.
_REPEATED_PAGES = 3
# A text repeats when it holds 3 words split by spaces or 11 letters, so a
# running line counts in a script without spaces as well. A short connective
# or label between formulas holds up to 10 letters and stays content.
_REPEATED_MIN_WORDS = 3
_REPEATED_MIN_LETTERS = 11
_LETTER = regex.compile(r"\p{L}")
# With text evidence, the indent tolerance covers the scatter of scanned line
# frames at the left edge (up to 1.5 units and 0.0124 of the block width); a
# paragraph indent starts at 9 units and 0.027 of the width.
_INDENT_FLOOR = 1.5
_INDENT_SHARE = 0.02
# Without text evidence any offset is an indent, beyond float noise.
_INDENT_NOISE = 0.01
# Two blocks of one paragraph stand closer than half a line height and share
# most of their width; a caption, a pull quote, or a new paragraph stands
# farther off. A gap below minus half a line is an overlay, not a stack.
_STACK_GAP_MIN = -0.5
_STACK_GAP_MAX = 0.5
_STACK_OVERLAP = 0.5


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
        self.repeated_texts: set[str] = set()

    def __call__(self, document: Document):
        self.repeated_texts = self.find_repeated_texts(document)
        # All joins are found on the reading order of the layout, before any
        # block moves.
        joins: list[tuple[Block, Block, list[Block]]] = []
        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                if block.structure is None or block.ignore_for_output:
                    continue
                if self.is_repeated(document, block) or self.is_label(document, block):
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
            or self.is_repeated(document, candidate)
        ):
            between.append(candidate)
            candidate = document.get_next_block(candidate)
        if candidate is None or candidate.block_type not in self.block_types:
            return None
        if candidate.structure is None or self.is_label(document, candidate):
            return None
        return candidate, between

    def find_repeated_texts(self, document: Document) -> set[str]:
        pages_of: dict[str, set] = {}
        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                text = self.normalized_text(document, block)
                if (
                    len(text.split()) >= _REPEATED_MIN_WORDS
                    or len(_LETTER.findall(text)) >= _REPEATED_MIN_LETTERS
                ):
                    pages_of.setdefault(text, set()).add(page.page_id)
        return {
            text for text, pages in pages_of.items() if len(pages) >= _REPEATED_PAGES
        }

    @staticmethod
    def normalized_text(document: Document, block: Block) -> str:
        return " ".join(block.raw_text(document).split())

    def is_repeated(self, document: Document, block: Block) -> bool:
        if block.block_type not in self.block_types:
            return False
        return self.normalized_text(document, block) in self.repeated_texts

    @staticmethod
    def is_label(document: Document, block: Block) -> bool:
        # A label with a number and no word after it is a caption that the
        # layout read as text; a sentence that opens with a label has words.
        text = block.raw_text(document).strip()
        found = _LABEL_NUMBER.match(text)
        return found is not None and not _WORD.search(text[found.end() :])

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
        text_evidence = bool(_WORD_HYPHEN.search(first_text)) or (
            first_half_runs_on(first_text) and second_half_runs_on(second_text)
        )

        column_gap = block.polygon.width * self.column_gap_ratio
        column_break, page_break, figure_cut, stacked = False, False, False, False
        next_block_in_first_quadrant = False
        if next_block.page_id == block.page_id:
            column_break = math.floor(next_block.polygon.y_start) <= math.ceil(
                block.polygon.y_start
            ) and next_block.polygon.x_start > (block.polygon.x_end + column_gap)
            figure_cut = any(self.renders(b) for b in between)
            stacked = not between and self.stacked(document, block, next_block)
        else:
            page_break = True
            next_page = document.get_page(next_block.page_id)
            next_block_in_first_quadrant = (
                next_block.polygon.x_start < next_page.polygon.width // 2
            ) and (next_block.polygon.y_start < next_page.polygon.height // 2)

        # On a stack or a cut by a figure, the text alone does not separate a
        # cut paragraph in a script without case from two paragraphs.
        if not text_evidence and (page_break or column_break):
            text_evidence = continues_without_case(first_text, second_text)

        if self.starts_indented(document, next_block, text_evidence):
            return False

        if text_evidence:
            return page_break or column_break or figure_cut or stacked

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
    def starts_indented(document: Document, block: Block, text_evidence: bool) -> bool:
        lines = block.line_polygons(document)
        if not lines:
            return True
        offset = lines[0].x_start - min(line.x_start for line in lines)
        tolerance = _INDENT_NOISE
        if text_evidence:
            tolerance = max(_INDENT_FLOOR, _INDENT_SHARE * block.polygon.width)
        return offset > tolerance

    @staticmethod
    def stacked(document: Document, block: Block, next_block: Block) -> bool:
        heights = [line.height for line in block.line_polygons(document)]
        heights = [height for height in heights if height > 0]
        if not heights:
            return False
        line_height = statistics.median(heights)
        gap = next_block.polygon.y_start - block.polygon.y_end
        if not _STACK_GAP_MIN * line_height <= gap < _STACK_GAP_MAX * line_height:
            return False
        first, second = block.polygon, next_block.polygon
        overlap = min(first.x_end, second.x_end) - max(first.x_start, second.x_start)
        narrow = min(first.width, second.width)
        return narrow > 0 and overlap >= _STACK_OVERLAP * narrow

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
