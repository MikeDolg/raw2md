"""Inspection operation: compare the source against the md and emit fixes.

Runs under ``--llm-inspection`` for ``pdf`` and ``djvu``. The model gets the
source and the body and returns an edit list, never a rewritten document: each
``old`` -> ``new`` pair is confirmed at its page-scoped address, passes the edit
guard, and is substituted by the tool. `coordinator` sends the requests, whole
or in chunks of pages; `reply` decodes an answer, `numbering` recounts a chunk
answered in its own numbering, `addressing` places a quote in the body,
`masking` hides sound math spans from the request and puts them back, and
`apply` rebuilds the body. `common` holds the types they share.
"""
