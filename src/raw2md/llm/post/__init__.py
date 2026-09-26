"""Post-processing operation: LLM repair of the zones the markup shows damaged.

Runs under `--llm-post`. Every zone is read off the body itself, so the same
zones open whether an earlier step ran or not. `coordinator` runs the routes in
a fixed order; each route owns its detector, request, and verdict: `blocks`,
`tables`, `ladder`, and `spacing`. `common` holds what they share, and no route
imports the coordinator. A failed reply is retried once with the reason, then
reverted; an echo reverts at once.
"""
