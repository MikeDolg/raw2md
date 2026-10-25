"""Heading levels follow the line heights, in any order of the headings."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ._helpers import Loader

# Clusters of different sizes: equal sizes would hide a height that loses its
# cluster label.
_HEIGHTS = [30.0] + [20.0] * 2 + [14.0] * 3 + [11.0] * 6
_LEVELS = {30.0: 1, 20.0: 2, 14.0: 3, 11.0: 4}


def _orders() -> list[list[float]]:
    rising = sorted(_HEIGHTS)
    falling = rising[::-1]
    return [
        rising,
        falling,
        rising[::2] + rising[1::2],
        falling[1::3] + falling[::3] + falling[2::3],
        rising[5:] + rising[:5],
    ]


def _header(engine: Loader, block_id: int, height: float) -> SimpleNamespace:
    block_types = engine("marker.schema").BlockTypes
    return SimpleNamespace(
        id=block_id,
        block_type=block_types.SectionHeader,
        structure=[],
        line_height=lambda document: height,
        heading_level=None,
        ignore_for_output=False,
    )


@pytest.mark.parametrize("heights", _orders())
def test_levels_follow_heights_in_any_order(
    engine: Loader, heights: list[float]
) -> None:
    blocks = [_header(engine, i, h) for i, h in enumerate(heights)]
    document = SimpleNamespace(pages=[SimpleNamespace(children=blocks)])
    processor = engine("marker.processors.sectionheader").SectionHeaderProcessor

    processor.__call__(object.__new__(processor), document)

    assert [b.heading_level for b in blocks] == [_LEVELS[h] for h in heights]


@pytest.mark.parametrize("heights", _orders())
def test_ranges_run_from_the_tallest_cluster(
    engine: Loader, heights: list[float]
) -> None:
    processor = engine("marker.processors.sectionheader").SectionHeaderProcessor

    ranges = processor.bucket_headings(object.__new__(processor), heights)

    assert ranges == [(30.0, 30.0), (20.0, 20.0), (14.0, 14.0), (11.0, 11.0)]


def test_headers_without_lines_take_no_cluster(engine: Loader) -> None:
    processor = engine("marker.processors.sectionheader").SectionHeaderProcessor
    heights = _HEIGHTS + [0.0] * 4

    ranges = processor.bucket_headings(object.__new__(processor), heights)

    assert ranges == [(30.0, 30.0), (20.0, 20.0), (14.0, 14.0), (11.0, 11.0)]


def test_empty_header_keeps_the_default_level(engine: Loader) -> None:
    blocks = [_header(engine, i, h) for i, h in enumerate(_HEIGHTS)]
    empty = _header(engine, 99, 0.0)
    blocks.append(empty)
    document = SimpleNamespace(pages=[SimpleNamespace(children=blocks)])
    processor = engine("marker.processors.sectionheader").SectionHeaderProcessor

    processor.__call__(object.__new__(processor), document)

    assert empty.heading_level == processor.default_level
    assert [b.heading_level for b in blocks[:-1]] == [_LEVELS[h] for h in _HEIGHTS]


@pytest.mark.parametrize(
    ("heights", "ranges"),
    [
        # 13 and 14 differ by under a tenth: one level of the two.
        (
            [30.0] + [20.0] * 2 + [14.0] * 3 + [13.0] * 6,
            [(30.0, 30.0), (20.0, 20.0), (13.0, 14.0)],
        ),
        # Every neighbor is close: the whole ladder is one level.
        ([12.0] * 2 + [12.5] * 3 + [13.0] * 3 + [13.5] * 3, [(12.0, 13.5)]),
    ],
)
def test_close_clusters_share_a_level(
    engine: Loader, heights: list[float], ranges: list[tuple[float, float]]
) -> None:
    processor = engine("marker.processors.sectionheader").SectionHeaderProcessor

    assert processor.bucket_headings(object.__new__(processor), heights) == ranges
