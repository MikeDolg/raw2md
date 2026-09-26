"""KaTeX itself, as the judge of whether a math span renders at all.

The cleaner, the LLM edit guard, and the evaluator ask this question of the
same spans, so they share one judge, and it is the renderer, not a stand-in.

The renderer runs in a wasm sandbox over the bundled `katex.min.js` (KaTeX
0.18.4, the npm file byte for byte). The bundle keeps the verdict the same on
every machine and keeps Node out of the runtime.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quickjs_rs import Context, Runtime

_BUNDLE = Path(__file__).with_name("katex.min.js")

# `renderToString`, not the parser alone: a command KaTeX parses but cannot
# build does not render either.
# `displayMode` is on because only display mode has the `align` family; the
# verdict is about the formula, not its delimiters.
# `strict: 'ignore'` keeps warnings from becoming errors: a Unicode letter in
# math mode warns on nearly every span of a Cyrillic body.
_INSTALL_JUDGE = """
globalThis.raw2mdRenderError = function (payload) {
  try {
    katex.renderToString(JSON.parse(payload), {
      throwOnError: true,
      displayMode: true,
      strict: 'ignore',
    });
    return '';
  } catch (error) {
    return String(error.message);
  }
};
'installed';
"""

_runtime: Runtime | None = None
_context: Context | None = None


def _judge() -> Context:
    """The sandbox with KaTeX loaded, built on first use and kept for the process.

    The runtime is held beside the context because the context does not
    outlive it.
    """
    from quickjs_rs import Runtime

    global _runtime, _context  # noqa: PLW0603 -- process-wide sandbox singleton
    if _context is None:
        _runtime = Runtime()
        context = _runtime.new_context()
        # The UMD bundle, with no `module` or `define` in the sandbox, assigns
        # `katex` on the global object.
        context.eval(_BUNDLE.read_text(encoding="utf-8"))
        context.eval(_INSTALL_JUDGE)
        _context = context
    return _context


@cache
def renders(content: str) -> bool:
    """True when KaTeX renders `content` as a formula.

    Cached by content: cleaning asks about the same span several times as it
    repairs it, and a document repeats its formulas. The cache lives as long
    as the run.
    """
    # Lazy: `wasmtime` costs more than the rest of the start-up together.
    from quickjs_rs import TimeoutError as SandboxTimeout
    from wasmtime import Trap

    payload = json.dumps(json.dumps(content))
    try:
        message = _judge().eval(f"raw2mdRenderError({payload})")
    except SandboxTimeout:
        # A span the renderer cannot finish is a region that lost its closing
        # delimiter and swallowed the prose behind it. The sandbox survives.
        return False
    except Trap:
        # A recognition loop over a scope-opening command (`\textstyle`
        # hundreds of times) recurses past the host stack and aborts the call.
        # The sandbox stays sound for the next span.
        return False
    return bool(message == "")
