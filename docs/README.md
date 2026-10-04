# Documentation

These documents describe what raw2md does with a document and where you see
the result of each stage.

Start with the [reference](reference.md). It describes the commands, the
flags, the result files, the header, the service files, the exit codes, and
the environment.

A document goes through the stages in the order of this table:

| Stage | When it runs | Document |
|---|---|---|
| Conversion | always, except for an `md` input | [reference.md](reference.md#usage) |
| Cleaning | always, on every input | [cleaning.md](cleaning.md) |
| Inspection | with `--llm-inspection`, on `pdf` and `djvu` only | [inspection.md](inspection.md) |
| Post-processing | with `--llm-post`, on every input | [post.md](post.md) |
| Quality evaluation | after cleaning, and again after each LLM stage | [quality.md](quality.md) |

Each guide to a stage shows what the stage repairs or checks, with examples.
It also shows what the stage does not change, and where you see its result.
