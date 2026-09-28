"""Print results as one Markdown table, the form the README carries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mpdocbench.pins import Pins
from mpdocbench.scoring import ENGINE, NOT_AVAILABLE, RESULT

_SET_NAMES = {"all": "Whole set", "english": "English"}


def _cell(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, int | float) else str(value)


def _caption(result: Mapping[str, Any]) -> str:
    documents = result["documents"]
    coverage = f"{documents['scored']} of {documents['annotated']} documents scored"
    extras = [
        f"{documents[key]} {key}" for key in ("missing", "failed") if documents[key]
    ]
    if extras:
        coverage += f" ({', '.join(extras)})"
    return (
        f"- raw2md {result['raw2md']}, `{result['command']}`,"
        f" language: {result['language']}, scored {result['scored_at']}:"
        f" {coverage}."
    )


def render(results: Sequence[Mapping[str, Any]], pins: Pins) -> str:
    """The scores with a pair of columns per result, and what each result ran."""
    if len(results) == 1:
        heads = ["Engine", "raw2md"]
    else:
        heads = [
            f"{_SET_NAMES.get(result['language'], result['language'])}, {column}"
            for result in results
            for column in ("engine", "raw2md")
        ]
    lines = [_caption(result) for result in results]
    lines += [
        "",
        "| Element, metric | " + " | ".join(heads) + " |",
        "|---" * (len(heads) + 1) + "|",
    ]
    for key in results[0]["scores"]:
        element, metric = key.rsplit(".", 1)
        arrow = "↓" if metric in pins.lower_is_better else "↑"
        cells = []
        for result in results:
            columns = result["scores"].get(key, {})
            cells += [
                _cell(columns.get(ENGINE, NOT_AVAILABLE)),
                _cell(columns.get(RESULT, NOT_AVAILABLE)),
            ]
        lines.append(f"| `{element}`, {metric} {arrow} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
