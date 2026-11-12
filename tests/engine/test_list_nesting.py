"""List nesting reads the start of the first text line of an item."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ._helpers import Loader

_PAGE = (600.0, 800.0)


def _box(engine: Loader, box: tuple[float, float, float, float]) -> Any:
    return engine("marker.schema.polygon").PolygonBox.from_bbox(list(box))


def _list(
    engine: Loader, items: list[tuple[tuple[float, float, float, float], float]]
) -> tuple[Any, Any, list[Any]]:
    """A list group on a page; each item is a frame and the start of its line."""
    types = engine("marker.schema").BlockTypes
    blocks = engine("marker.schema.blocks")
    page = engine("marker.schema.groups.page").PageGroup(
        polygon=_box(engine, (0.0, 0.0, *_PAGE)), page_id=0
    )
    group = page.add_full_block(
        engine("marker.schema.groups.list").ListGroup(
            polygon=_box(engine, (20.0, 100.0, 580.0, 100.0 + 40.0 * len(items))),
            page_id=0,
            block_type=types.ListGroup,
        )
    )
    page.add_structure(group)
    line_class = engine("marker.schema.text.line").Line
    made = []
    for frame, line_x in items:
        item = page.add_full_block(
            blocks.ListItem(
                polygon=_box(engine, frame), page_id=0, block_type=types.ListItem
            )
        )
        line = page.add_full_block(
            line_class(
                polygon=_box(engine, (line_x, frame[1], frame[2], frame[1] + 18.0)),
                page_id=0,
            )
        )
        item.add_structure(line)
        group.add_structure(item)
        made.append(item)
    return page, group, made


def _indent(engine: Loader, page: Any) -> None:
    processor = engine("marker.processors.list").ListProcessor({})
    processor.list_group_indentation(
        SimpleNamespace(pages=[page], get_block=page.get_block)
    )


def test_a_frame_wider_than_the_text_does_not_nest(engine: Loader) -> None:
    page, group, items = _list(
        engine,
        [
            ((50.0, 100.0, 550.0, 130.0), 50.0),
            ((90.0, 140.0, 550.0, 170.0), 50.0),
            ((50.0, 180.0, 550.0, 210.0), 50.0),
        ],
    )

    _indent(engine, page)

    assert [item.list_indent_level for item in items] == [0, 0, 0]
    assert len(group.structure) == 3


def test_an_indented_first_line_nests(engine: Loader) -> None:
    page, group, items = _list(
        engine,
        [
            ((50.0, 100.0, 550.0, 130.0), 50.0),
            ((90.0, 140.0, 550.0, 170.0), 90.0),
        ],
    )

    _indent(engine, page)

    assert [item.list_indent_level for item in items] == [0, 1]
    assert group.structure == [items[0].id]


def test_a_paragraph_indent_on_the_first_line_does_not_nest(engine: Loader) -> None:
    page, _group, items = _list(
        engine,
        [
            ((50.0, 100.0, 550.0, 130.0), 50.0),
            ((50.0, 140.0, 550.0, 170.0), 58.0),
        ],
    )

    _indent(engine, page)

    assert [item.list_indent_level for item in items] == [0, 0]


def test_the_merge_keeps_the_start_of_the_parent_line(engine: Loader) -> None:
    page, _group, items = _list(
        engine,
        [
            ((50.0, 100.0, 550.0, 130.0), 50.0),
            ((90.0, 140.0, 550.0, 170.0), 90.0),
        ],
    )
    start = items[0].line_polygons(page)[0].x_start

    _indent(engine, page)

    assert items[0].line_polygons(page)[0].x_start == start == 50.0
