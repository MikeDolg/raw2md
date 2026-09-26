"""Ceilings on docstring and comment-block length in `src/` and `tests/`.

Each ceiling is the longest text of its kind at the time it was set, so the
gate stops regrowth without asking for a rewrite. A docstring is measured in
source lines; a comment block is a run of adjacent comment-only lines.
"""

import ast
import io
import tokenize
from collections.abc import Iterator
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

_CEILINGS = {
    "src": {"module": 18, "class": 11, "function": 14, "block": 9},
    "tests": {"module": 14, "class": 5, "function": 7, "block": 4},
}

_NON_CODE_TOKENS = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }
)


def _docstrings(tree: ast.Module) -> Iterator[tuple[str, int, int]]:
    """Yield the kind, first line, and line count of each docstring."""
    owners: list[
        tuple[str, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]
    ] = [("module", tree)]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            owners.append(("class", node))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            owners.append(("function", node))
    for kind, owner in owners:
        first = owner.body[0] if owner.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            end = first.end_lineno or first.lineno
            yield kind, first.lineno, end - first.lineno + 1


def _comment_blocks(text: str) -> Iterator[tuple[int, int]]:
    """Yield the first line and line count of each comment-only block."""
    comments: set[int] = set()
    code: set[int] = set()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            comments.add(token.start[0])
        elif token.type not in _NON_CODE_TOKENS:
            code.update(range(token.start[0], token.end[0] + 1))
    start = previous = None
    for line in sorted(comments - code):
        if previous is not None and line == previous + 1:
            previous = line
            continue
        if start is not None and previous is not None:
            yield start, previous - start + 1
        start = previous = line
    if start is not None and previous is not None:
        yield start, previous - start + 1


def _overlong(area: str) -> list[str]:
    ceilings = _CEILINGS[area]
    found: list[str] = []
    for path in sorted((_ROOT / area).rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        where = path.relative_to(_ROOT).as_posix()
        spans = list(_docstrings(ast.parse(text)))
        spans += [("block", line, count) for line, count in _comment_blocks(text)]
        found += [
            f"{where}:{line}: {kind} of {count} lines > {ceilings[kind]}"
            for kind, line, count in spans
            if count > ceilings[kind]
        ]
    return found


@pytest.mark.parametrize("area", sorted(_CEILINGS))
def test_docstrings_and_comment_blocks_stay_under_ceiling(area: str) -> None:
    assert _overlong(area) == []


def test_comment_block_splits_on_code_and_blank_lines() -> None:
    text = "# a\n# b\nx = 1  # trailing\n\n# c\ny = '# not a comment'\n"
    assert list(_comment_blocks(text)) == [(1, 2), (5, 1)]


def test_docstring_counts_source_lines_per_owner() -> None:
    text = (
        '"""M."""\n\n\nclass C:\n    """C\n\n    more.\n    """\n\n'
        '    def f(self):\n        """F."""\n'
    )
    assert sorted(_docstrings(ast.parse(text))) == [
        ("class", 5, 4),
        ("function", 11, 1),
        ("module", 1, 1),
    ]
