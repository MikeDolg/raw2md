import math
from typing import Annotated

from raw2md_engine.marker.processors import BaseProcessor
from raw2md_engine.marker.schema import BlockTypes
from raw2md_engine.marker.schema.blocks import Block, BlockId
from raw2md_engine.marker.schema.blocks.tablecell import TableCell
from raw2md_engine.marker.schema.document import Document
from raw2md_engine.marker.schema.groups.page import PageGroup
from raw2md_engine.marker.schema.polygon import PolygonBox

GROUP_TYPES = (
    BlockTypes.FigureGroup,
    BlockTypes.TableGroup,
    BlockTypes.ListGroup,
    BlockTypes.PictureGroup,
)
FURNITURE_TYPES = (BlockTypes.PageHeader, BlockTypes.PageFooter)

Span = tuple[float, float]
Row = list[TableCell]


class TableMergeProcessor(BaseProcessor):
    """
    Joins a table that a page break or a column break cuts in two. The table
    that closes a page takes the rows of the table that opens the next page,
    and the table that ends a column takes the rows of the table that opens
    the next column of the page, when only running headers, footers and
    hidden blocks stand between them and:
    - the column counts are equal, or differ by one and each column of the
      narrower part overlaps one column of the wider part along x;
    - the first rows of the second part repeat the first rows of the first
      part cell for cell, or the table model reads its first row as data.
    Only header rows repeat past the first row, and the join stops when a
    cell spans over the cut. The repeated rows go. A second part that opens with a header of its own
    stays a table of its own, and so does a table whose first row repeats a
    run of its own cells: records set side by side. The cells keep their page; a table that runs
    over three pages or columns or more joins as a chain.
    At a column break, each column of one part also overlaps the column of
    the other part that it joins, both measured as a share of the width of
    their own table: two tables side by side with other column widths stay
    apart.
    """

    block_types = (BlockTypes.Table,)
    column_gap_ratio: Annotated[
        float,
        "The share of the table width that the gap before the next column must pass.",
    ] = 0.02

    def __init__(self, config=None):
        super().__init__(config)
        self.frames: dict[BlockId, Span] = {}

    def __call__(self, document: Document):
        pages = document.pages
        # The edges come before any join: a part that joins still closes its page.
        edges = [self.content_blocks(document, page) for page in pages]
        # A joined cell keeps the x span of the table that it came from.
        self.frames = {
            cell.id: (block.polygon.x_start, block.polygon.x_end)
            for blocks in edges
            for block, _ in blocks
            if block.block_type in self.block_types
            for cell in block.contained_blocks(document, (BlockTypes.TableCell,))
        }
        heads: dict[BlockId, Block] = {}
        for index, page in enumerate(pages):
            for (last, _), (first, parent) in zip(
                edges[index], edges[index][1:], strict=False
            ):
                if self.opens_next_column(last, first):
                    self.merge(document, heads, last, first, parent, column_cut=True)
            if index + 1 == len(pages) or pages[index + 1].page_id != page.page_id + 1:
                continue
            if not edges[index] or not edges[index + 1]:
                continue
            last, _ = edges[index][-1]
            first, parent = edges[index + 1][0]
            self.merge(document, heads, last, first, parent, column_cut=False)

    def opens_next_column(self, block: Block, next_block: Block) -> bool:
        gap = block.polygon.width * self.column_gap_ratio
        return math.floor(next_block.polygon.y_start) <= math.ceil(
            block.polygon.y_start
        ) and next_block.polygon.x_start > (block.polygon.x_end + gap)

    def merge(
        self,
        document: Document,
        heads: dict[BlockId, Block],
        last: Block,
        first: Block,
        parent: Block,
        column_cut: bool,
    ) -> None:
        if last.block_type not in self.block_types:
            return
        if first.block_type not in self.block_types:
            return
        head = heads.get(last.id, last)
        if self.join(document, head, first, column_cut):
            parent.remove_structure_items([first.id])
            heads[first.id] = head

    @staticmethod
    def is_content(block: Block) -> bool:
        return not (
            block.removed
            or block.ignore_for_output
            or block.block_type in FURNITURE_TYPES
        )

    def content_blocks(
        self, document: Document, page: PageGroup
    ) -> list[tuple[Block, Block]]:
        """The content blocks of the page in order, each with its parent."""
        blocks: list[tuple[Block, Block]] = []
        for block in page.structure_blocks(page):
            if not self.is_content(block):
                continue
            if block.block_type in GROUP_TYPES:
                blocks += [
                    (child, block)
                    for child in block.structure_blocks(document)
                    if self.is_content(child)
                ]
            else:
                blocks.append((block, page))
        return blocks

    def join(
        self, document: Document, head: Block, part: Block, column_cut: bool
    ) -> bool:
        """Move the rows of `part` into `head`; False leaves both as they are.

        At a column break the columns compare as shares of their table width.
        """
        if head.html or part.html:
            return False
        head_cells = head.contained_blocks(document, (BlockTypes.TableCell,))
        part_cells = part.contained_blocks(document, (BlockTypes.TableCell,))
        if not head_cells or not part_cells:
            return False

        frames = self.frames if column_cut else None
        maps = self.column_maps(head_cells, part_cells, frames)
        if maps is None:
            return False
        head_map, part_map = maps
        head_width = self.column_count(head_cells)
        part_width = self.column_count(part_cells)

        head_rows = [row for row in self.rows(head_cells) if self.has_text(row)]
        part_rows = [row for row in self.rows(part_cells) if self.has_text(row)]
        if not part_rows:
            return False
        # A table that sets its records several columns up reads down each
        # column of a page; a join would put the next page between them.
        if self.repeats_columns(part_rows[0]) or (
            head_rows and self.repeats_columns(head_rows[0])
        ):
            return False
        repeated = 0
        for index, (head_row, part_row) in enumerate(
            zip(head_rows, part_rows, strict=False)
        ):
            if self.row_key(head_row, head_map) != self.row_key(part_row, part_map):
                break
            # Past the first row only a header row repeats; equal data rows
            # are records.
            if index and not any(cell.header_row for cell in (*head_row, *part_row)):
                break
            repeated += 1
        if repeated == len(part_rows):
            return False
        # A header row that did not repeat belongs to a table of its own.
        # A cell that spans over the cut cannot move with the rows after it.
        first_kept = part_rows[repeated][0].row_id
        if any(cell.header_row for cell in part_rows[repeated]) or any(
            cell.row_id < first_kept < cell.row_id + cell.rowspan for cell in part_cells
        ):
            return False
        kept = [cell for cell in part_cells if cell.row_id >= first_kept]
        offset = max(cell.row_id + cell.rowspan for cell in head_cells) - first_kept
        for cell in kept:
            cell.row_id += offset

        narrow = None
        if head_width < part_width:
            narrow, column_map, wide = head_cells, head_map, part_cells
        elif part_width < head_width:
            narrow, column_map, wide = kept, part_map, head_cells
        if narrow is not None:
            self.remap_columns(narrow, column_map)

        for cell in kept:
            head.add_structure(cell)
        part.structure = []

        if narrow is not None:
            width = max(head_width, part_width)
            spans = self.column_spans(wide, width, frames)
            missing = next(col for col in range(width) if col not in column_map)
            for filler, frame in self.fillers(narrow, missing, spans[missing], frames):
                document.get_page(filler.page_id).add_full_block(filler)
                head.add_structure(filler)
                self.frames[filler.id] = frame
        return True

    @staticmethod
    def column_count(cells: list[TableCell]) -> int:
        return max(cell.col_id + cell.colspan for cell in cells)

    def column_maps(
        self,
        head: list[TableCell],
        part: list[TableCell],
        frames: dict[BlockId, Span] | None,
    ) -> tuple[list[int], list[int]] | None:
        """The column of the joined table for each column of each part.

        None when the columns of the parts do not agree.
        """
        head_width = self.column_count(head)
        part_width = self.column_count(part)
        head_map = list(range(head_width))
        part_map = list(range(part_width))
        if head_width == part_width:
            if frames is not None and not self.columns_align(
                head, part, head_width, frames
            ):
                return None
            return head_map, part_map
        if abs(head_width - part_width) != 1:
            return None
        if head_width < part_width:
            found = self.column_map(head, part, head_width, part_width, frames)
            return None if found is None else (found, part_map)
        found = self.column_map(part, head, part_width, head_width, frames)
        return None if found is None else (head_map, found)

    @staticmethod
    def column_spans(
        cells: list[TableCell], width: int, frames: dict[BlockId, Span] | None = None
    ) -> dict[int, Span] | None:
        """The x span of each column, from the cells of one column only.

        With `frames`, each edge is a share of the width of the cell's table.
        """
        spans: dict[int, Span] = {}
        for cell in cells:
            if cell.colspan != 1:
                continue
            x0, _, x1, _ = cell.polygon.bbox
            if frames is not None:
                left, right = frames[cell.id]
                size = (right - left) or 1.0
                x0, x1 = (x0 - left) / size, (x1 - left) / size
            if cell.col_id in spans:
                left, right = spans[cell.col_id]
                x0, x1 = min(x0, left), max(x1, right)
            spans[cell.col_id] = (x0, x1)
        if len(spans) < width:
            return None
        return spans

    def column_map(
        self,
        narrow: list[TableCell],
        wide: list[TableCell],
        narrow_width: int,
        wide_width: int,
        frames: dict[BlockId, Span] | None,
    ) -> list[int] | None:
        """The column of the wider part that each narrower column overlaps most.

        None when a column overlaps none, or two columns land on one.
        """
        narrow_spans = self.column_spans(narrow, narrow_width, frames)
        wide_spans = self.column_spans(wide, wide_width, frames)
        if narrow_spans is None or wide_spans is None:
            return None
        found: list[int] = []
        for col in range(narrow_width):
            left, right = narrow_spans[col]
            overlaps = [
                min(right, wide_spans[other][1]) - max(left, wide_spans[other][0])
                for other in range(wide_width)
            ]
            best = max(range(wide_width), key=lambda other: overlaps[other])
            if overlaps[best] <= 0 or (found and best <= found[-1]):
                return None
            found.append(best)
        return found

    def columns_align(
        self,
        head: list[TableCell],
        part: list[TableCell],
        width: int,
        frames: dict[BlockId, Span],
    ) -> bool:
        """Each column of one part overlaps the same column of the other."""
        head_spans = self.column_spans(head, width, frames)
        part_spans = self.column_spans(part, width, frames)
        if head_spans is None or part_spans is None:
            return False
        return all(
            min(head_spans[col][1], part_spans[col][1])
            > max(head_spans[col][0], part_spans[col][0])
            for col in range(width)
        )

    @staticmethod
    def remap_columns(cells: list[TableCell], column_map: list[int]) -> None:
        for cell in cells:
            last = min(cell.col_id + cell.colspan, len(column_map)) - 1
            start = column_map[cell.col_id]
            cell.colspan = column_map[last] - start + 1
            cell.col_id = start

    def fillers(
        self,
        cells: list[TableCell],
        col: int,
        span: Span,
        frames: dict[BlockId, Span] | None,
    ) -> list[tuple[TableCell, Span]]:
        """An empty cell for each row of `cells` that no cell covers at `col`.

        Each filler comes with the x span of the table of its row. With
        `frames`, `span` is a share of that width.
        """
        first = min(cell.row_id for cell in cells)
        end = max(cell.row_id + cell.rowspan for cell in cells)
        fillers = []
        for row_id in range(first, end):
            covering = [
                cell
                for cell in cells
                if cell.row_id <= row_id < cell.row_id + cell.rowspan
            ]
            if not covering or any(
                cell.col_id <= col < cell.col_id + cell.colspan for cell in covering
            ):
                continue
            own = [cell for cell in covering if cell.row_id == row_id] or covering
            boxes = [cell.polygon.bbox for cell in own]
            top = min(box[1] for box in boxes)
            bottom = max(box[3] for box in boxes)
            frame = self.frames[own[0].id]
            left, right = span
            if frames is not None:
                size = frame[1] - frame[0]
                left, right = frame[0] + left * size, frame[0] + right * size
            filler = TableCell(
                polygon=PolygonBox.from_bbox([left, top, right, bottom]),
                text_lines=[],
                rowspan=1,
                colspan=1,
                row_id=row_id,
                col_id=col,
                is_header=any(cell.is_header for cell in own),
                header_row=any(cell.header_row for cell in own),
                page_id=own[0].page_id,
            )
            fillers.append((filler, frame))
        return fillers

    @staticmethod
    def rows(cells: list[TableCell]) -> list[Row]:
        by_row: dict[int, Row] = {}
        for cell in cells:
            by_row.setdefault(cell.row_id, []).append(cell)
        return [
            sorted(by_row[row_id], key=lambda cell: cell.col_id)
            for row_id in sorted(by_row)
        ]

    @staticmethod
    def cell_text(cell: TableCell) -> str:
        return " ".join(" ".join(cell.text_lines or []).split())

    def has_text(self, row: Row) -> bool:
        return any(self.cell_text(cell) for cell in row)

    def repeats_columns(self, row: Row) -> bool:
        """The row is two copies or more of one run of cells, two cells or wider."""
        names = [(cell.colspan, self.cell_text(cell)) for cell in row]
        width = len(names)
        for size in range(2, width // 2 + 1):
            if width % size or not any(text for _, text in names[:size]):
                continue
            if all(names[col] == names[col % size] for col in range(size, width)):
                return True
        return False

    def row_key(self, row: Row, column_map: list[int]) -> list[tuple[int, int, str]]:
        """The cells of the row as (column, span, text) on the wider layout."""
        key = []
        for cell in row:
            last = min(cell.col_id + cell.colspan, len(column_map)) - 1
            start = column_map[cell.col_id]
            key.append((start, column_map[last] - start + 1, self.cell_text(cell)))
        return key
