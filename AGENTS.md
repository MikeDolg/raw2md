# AGENTS.md

This file tells a coding agent how the raw2md repository is laid out and how
to check a change. The user guide is [README.md](README.md). The reference for
every command, flag, result file, and exit code is
[docs/reference.md](docs/reference.md).

## Project

raw2md is a command-line tool. It accepts PDF, DjVu, DOCX, and Markdown
sources. It converts a PDF, DjVu, or DOCX source into Markdown and then cleans
the Markdown. A Markdown source goes to cleaning directly. The tool processes
one file at a time, in these stages:

| Stage | When it runs | What it does |
|---|---|---|
| Conversion | always, except for a Markdown source | converts the source with `raw2md-engine` (PDF), `pandoc` (DOCX), DjVuLibre and `raw2md-engine` (DjVu), or Gemini (`-e`) |
| Cleaning | always | repairs defects with deterministic rules |
| Inspection | with `-i`, for PDF and DjVu | compares the text with the source pages through a large language model (LLM) |
| Post-processing | with `-p` | repairs damaged markup through an LLM |
| Quality evaluation | after cleaning and after each LLM stage | gives the verdict, `ok` or `bad`, for the header of the result |

The guide to each stage is in `docs/`.

## Layout

| Path | Contents |
|---|---|
| `src/raw2md/cli.py` | the arguments and the subcommands |
| `src/raw2md/orchestrator.py`, `queue.py`, `lock.py` | the run: the lock, the queue, resume, and the exit code |
| `src/raw2md/pipeline.py` | the stages of one file |
| `src/raw2md/engines/` | the conversion engines; `base.py` holds their interface, `marker.py` is the adapter of `raw2md-engine`, and `weights.py` downloads its weights |
| `src/raw2md_engine/` | `raw2md-engine`: a reduced copy of `marker`, `surya`, and `pdftext`, with the upstream layout and names; `NOTICE` lists its changed files |
| `src/raw2md/cleaner.py` | the entry points of cleaning and the order of its passes |
| `src/raw2md/cleaning/` | the cleaning rules, grouped by the object that they repair: headings, lists, tables, formulas, and prose |
| `src/raw2md/mdtext/` | the Markdown readers that all stages share: protected zones, lines, tables, and formulas |
| `src/raw2md/llm/` | the LLM providers, the `inspection/` and `post/` stages, and the edit guard that limits what an inspection edit can change |
| `src/raw2md/quality/` | quality evaluation |
| `src/raw2md/header.py`, `output.py` | the header and the result files |
| `src/raw2md/keywords.yaml` | the words that the cleaning rules look for |
| `src/raw2md/prompts.py` | the default prompts of the LLM stages |
| `src/raw2md/katex.min.js` | KaTeX, which checks that a formula is valid |
| `tests/` | the tests; `tests/cleaning/` holds the tests of `src/raw2md/cleaning/` |
| `tests/corpus/`, `tests/synthesis/` | the reference Markdown and the round-trip harness |
| `benchmarks/` | the MPDocBench runner and its results |
| `examples/` | the conversion results of real documents |

## Setup

The project supports Python 3.11 to 3.14 on Linux and Windows.

The fast layer and the checks below do not need `torch`. For them, install a
light environment:

1. Run the `uv sync` command from `.github/workflows/ci.yml`. It skips `torch`
   and its CUDA packages.
2. Set the `UV_NO_SYNC` environment variable to `1`. Without it, the next
   `uv run` installs `torch` again.

Conversion with `raw2md-engine` and the round-trip layer need the full environment.
It includes the CUDA build of `torch`, which takes several gigabytes:

```bash
uv sync
```

## Checks

Run each command from the repository root. Before you finish a change, run all
of them, as CI does.

| Command | What it checks |
|---|---|
| `uv run pytest` | the fast layer, which needs no GPU, no network, and no external tool |
| `uv run pytest -m concurrency` | the lock between processes, in a few seconds |
| `uv run ruff format --check .` | the formatting |
| `uv run ruff check .` | all stable lint rules, minus the list in `pyproject.toml` |
| `uv run mypy` | the types of `src/`, `tests/`, and `benchmarks/`, in strict mode |
| `npm ci`, then `npm run lint:md` | the Markdown files |

Two more layers run only when you name their marker. Run a layer only when
the task needs it:

- `uv run pytest -m roundtrip` generates PDF, DOCX, and DjVu files from
  `tests/corpus/`. Then it converts them back and compares the result with
  the source. It uses `pandoc`, `xelatex`, DjVuLibre, and `raw2md-engine`,
  which downloads its weights into `~/.raw2md/models` on the first run.
  Without a GPU, the engine is very slow.
- `uv run pytest -m llm_live` sends real requests to Gemini and Claude Code.
  It spends the API quota. It needs `GOOGLE_API_KEY` and `claude` on `PATH`.

Both layers skip a test when its tool or its key is absent.

## Conventions

- Cleaning is deterministic: the same input always gives the same output. A
  rule repairs only an unambiguous defect. It leaves an ambiguous defect in
  place and reports it.
- No LLM stage rewrites the whole text. Inspection returns separate edits,
  and post-processing repairs one zone at a time. A guard checks each edit
  and each zone. When the guard rejects a change, the text stays as it was.
- If a change alters what a user sees, update its document in the same
  change: `docs/reference.md` for a command, a flag, a setting, a result file,
  or an exit code, and the stage guide in `docs/` for a repair or a check.
- Import `raw2md_engine`, `pymupdf`, and an LLM SDK only inside `engines/`
  and `llm/`. The rest of the code uses the interfaces in `engines/base.py` and
  `llm/base.py`.
- Give `encoding="utf-8"` to every file read and write. The code runs on
  Windows and Linux.
- A string or a regular expression in `src/` holds no Cyrillic letter. Give
  such a letter by its code point, for example `chr(0x0410)`.
- A comment states why, not what. `tests/test_comment_length.py` limits the
  length of comments and docstrings.
- Each `# noqa` and `# type: ignore` names its rule code and gives a reason.
- Test data is invented. Do not copy text from real documents into tests.
- `src/raw2md_engine/` is upstream code: `ruff`, `mypy`, and the comment
  length test skip it. When you change a file there, add its upstream path
  and the date to `NOTICE`.

## Issues and pull requests

An agent that files an issue or opens a pull request uses the templates in
`.github/`. `gh issue create` and `gh pr create` do not apply them, so follow
them by hand:

- For an issue, select the form in `.github/ISSUE_TEMPLATE/` that matches the
  problem. Write the `label` of each field of the form as a heading, and fill
  each field that the form requires. Add the label from the `labels` key of
  the form.
- Do not use the `Task` form. It is for the maintainer only.
- For a pull request, use the headings of
  `.github/pull_request_template.md`. End the body with `Closes #N`, where `N`
  is the number of the issue.

## Licenses

The code is under the GPL-3.0-or-later license. `src/raw2md_engine/` keeps
the licenses of its original packages, which `NOTICE` lists. The engine
weights are under the Datalab model license, which `THIRD_PARTY_NOTICES.md`
describes. The results in `examples/` have their own licenses, which
`examples/README.md` lists. Do not copy these results into code or tests.
