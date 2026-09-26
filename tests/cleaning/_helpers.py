"""Builders the cleaning test modules share.

Plain functions rather than `conftest` fixtures, so they stay under the strict
type check.
"""

from __future__ import annotations

from raw2md.cleaner import CleanOptions, clean, clean_in_place, clean_with_report
from raw2md.header import ConversionMethod
from raw2md.source_outline import SourceOutline


def outlined(*entries: tuple[int, str]) -> CleanOptions:
    """Cleaning options carrying a source outline that states `entries`."""
    return CleanOptions(outline=SourceOutline(list(entries)))


def body(*lines: str) -> str:
    """A body from `lines`, each entry its own paragraph."""
    return "\n\n".join(lines) + "\n"


# Heading recovery runs only on a text route.
TEXT_ROUTE = CleanOptions(method=ConversionMethod.PANDOC)


def clean_text(text: str) -> str:
    """`clean_in_place` on a text route."""
    return clean_in_place(text, TEXT_ROUTE)


def clean_full_text(text: str) -> str:
    """`clean` on a text route."""
    return clean(text, TEXT_ROUTE)


def laid_out_table(*rows: str) -> str:
    """`rows` written out as cleaning delivers a table: cells padded to columns.

    Each row is a GFM row, the header first. Cleaning leaves a table built here as
    it stands, so a test of another rule can assert on the whole block.
    """
    grid = [
        [cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows
    ]
    widths = [max(len(row[col]) for row in grid) for col in range(len(grid[0]))]
    written = [
        "| "
        + " | ".join(cell.ljust(widths[col]) for col, cell in enumerate(row))
        + " |"
        for row in grid
    ]
    delimiter = "|" + "|".join("-" * (width + 2) for width in widths) + "|"
    return "".join(f"{line}\n" for line in [written[0], delimiter, *written[1:]])


def reported(text: str, options: CleanOptions | None = None) -> str:
    """The findings of one clean, one `kind detail` per line."""
    result = clean_with_report(text, options)
    return "\n".join(f"{f.kind} {f.detail}".rstrip() for f in result.findings)
