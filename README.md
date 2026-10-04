<h1 align="center">
  <img src="https://raw.githubusercontent.com/MikeDolg/raw2md/main/docs/assets/raw2md-logo.svg" alt="raw2md" width="420">
</h1>

<p align="center">
  <a href="https://github.com/MikeDolg/raw2md/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/MikeDolg/raw2md/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://codecov.io/gh/MikeDolg/raw2md"><img src="https://img.shields.io/codecov/c/github/MikeDolg/raw2md" alt="Coverage"></a>
  <a href="https://pypi.org/project/raw2md/"><img src="https://img.shields.io/pypi/v/raw2md" alt="PyPI"></a>
  <a href="https://pypi.org/project/raw2md/"><img src="https://img.shields.io/pypi/pyversions/raw2md" alt="Python"></a>
  <img src="https://img.shields.io/badge/platform-Linux%20%C2%B7%20Windows-blue" alt="Linux · Windows">
  <a href="https://github.com/MikeDolg/raw2md/blob/main/LICENSE"><img src="https://img.shields.io/github/license/MikeDolg/raw2md" alt="License"></a>
</p>

**raw2md** is an open-source Python command-line tool that converts PDF, DjVu, and DOCX documents into clean Markdown for retrieval-augmented generation (RAG) and other large language model (LLM) pipelines. It runs the conversion with `marker`, `pandoc`, or Gemini, then repairs the defects that these engines leave in headings, tables, formulas, lists, and text. Markdown from another converter goes through the same cleaning.

The cleaning uses deterministic rules and no LLM, so the same input always gives the same cleaned text. On the MPDocBench-Parse benchmark, the cleaning alone raises the aggregate score of the `marker` output by 3.1%.

Two optional LLM stages repair what the rules leave: inspection corrects recognition errors against the source pages, and post-processing repairs damaged markup.

## What does raw2md fix?

Converters leave typical defects in Markdown. In a RAG pipeline, these defects can split chunks in the wrong places and hide words from search. The `cleaning` stage repairs more than 70 types of defects ([full list](https://github.com/MikeDolg/raw2md/blob/main/docs/cleaning.md)), but only where the defect is unambiguous. For example:

- running heads and page numbers → removed
- wrong heading levels → corrected from the PDF bookmarks, the table of contents, or the numbering
- tables cut by a page break → merged
- words broken across lines → joined
- paragraphs broken into short lines → joined
- formulas cut into parts → joined
- recognition loops → cut to one copy
- `marker` navigation links → replaced with their text

## Why raw2md?

raw2md is built for large, mixed collections of long documents:

- One command converts a whole folder. The tool picks the engine for each format: `marker` for PDF, `pandoc` for DOCX, and DjVuLibre with `marker` for DjVu.
- A rule does not guess: it leaves an ambiguous defect in place and reports it.
- Each result starts with a header that holds the verdict, `ok` or `bad`, and the checks that fired. The verdict shows which files need a review.
- Without the LLM stages, the documents do not leave your machine.
- An interrupted run continues with `raw2md resume` and skips the finished files.

## What's the impact?

On the full [MPDocBench-Parse](https://arxiv.org/abs/2605.22100) set, the deterministic cleaning alone, with no LLM stage involved, lifts the seven-metric aggregate score of the underlying `marker` output from 67.14 to 69.22. That is a gain of 2.08 points, or 3.1% relative. The score follows the leaderboard formula, a normalized mean of the task scores, but without Figure F1: raw2md cannot be scored on that task. Therefore, the score is not comparable with the Overall column of the leaderboard.

Most of the improvement lands in the document structure:

- table TEDS: 0.652 → 0.698 (+7%)
- merged-table TEDS: 0.488 → 0.553 (+13%)
- heading TEDS: 0.371 → 0.408 (+10%)

Plain text, on the other hand, loses a little: the text edit distance grows from 0.122 to 0.130. You can find every metric in the [benchmark results](https://github.com/MikeDolg/raw2md/blob/main/benchmarks/README.md).

The benchmark, however, tells only part of the story: raw2md is designed primarily for long, complex documents. The [examples](https://github.com/MikeDolg/raw2md/tree/main/examples) show how it copes with entire books:

| Result      | Source type      | Pages | Engine   | Source   |
|-------------|------------------|-------|----------|----------|
| [`book.md`](https://github.com/MikeDolg/raw2md/blob/main/examples/book.md) | scanned PDF | 344 | `marker` | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Elementary_mechanism-_a_textbook_for_students_of_mechanical_engineering_(IA_cu31924031203742).pdf) |
| [`thesis.md`](https://github.com/MikeDolg/raw2md/blob/main/examples/thesis.md) | born-digital PDF | 230 | `marker` | [University of Cambridge](https://www.repository.cam.ac.uk/items/04ec45a9-4b8b-4ece-b848-7806d4636412) |
| [`report.md`](https://github.com/MikeDolg/raw2md/blob/main/examples/report.md) | DOCX | – | `pandoc` | [University of Derby](https://derby-repository.worktribe.com/output/804857/an-evaluation-of-the-derbyshire-and-nottinghamshire-collaborative-outreach-programme) |

## How does it work?

The first step, the conversion itself, runs on one of these engines:

- `marker` for PDF
- `pandoc` for DOCX
- Gemini for OCR of PDF and DjVu files (the `-e` flag)
- DjVuLibre to turn a DjVu file into a PDF before recognition

The cleaning of a file then goes through three stages, and two of them are optional:

| Stage        | Formats   | Turned on by  | What the stage does                     | Guide    |
|--------------|-----------|---------------|-----------------------------------------|----------|
| `cleaning`   | all       | always        | removes typical artifacts with deterministic rules | [cleaning.md](https://github.com/MikeDolg/raw2md/blob/main/docs/cleaning.md) |
| `inspection` | PDF, DjVu | the `-i` flag | checks the text against the source      | [inspection.md](https://github.com/MikeDolg/raw2md/blob/main/docs/inspection.md) |
| `post`       | all       | the `-p` flag | repairs the structure without the source | [post.md](https://github.com/MikeDolg/raw2md/blob/main/docs/post.md) |

After cleaning, and again after each LLM stage, a deterministic [quality evaluation](https://github.com/MikeDolg/raw2md/blob/main/docs/quality.md) grades the text. Its verdict, `ok` or `bad`, goes into the header of the result together with the checks that fired.

For now, inspection runs on Gemini only, while post-processing can use either Gemini or Claude Code through `claude -p`.

## What languages are supported?

Most of the testing used English and Russian sources, with a few German, French, and Italian ones on top. Chinese was never part of the testing, but the full-set results suggest that the structural repairs carry over to it. More than half of the MPDocBench set is Chinese, and yet the gains on the full set match those on its English part. The seven-metric aggregate grows by 3.10% relative on the full set and by 3.14% on the English part. The table and heading scores also grow by about the same amount on both.

## Installation

For `marker`, you need an NVIDIA GPU of the Turing generation or newer (GTX 16xx, RTX 20xx, and later cards) with driver 580 or newer. Without such a card, `marker` runs on the CPU. This mode is very slow, and raw2md does not support it.

Install the tool with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
uv tool install raw2md --torch-backend cu130
```

Or with `pip`:

```bash
pip install raw2md --extra-index-url https://download.pytorch.org/whl/cu130
```

Or straight from GitHub:

```bash
uv tool install git+https://github.com/MikeDolg/raw2md.git
```

On Windows, do not skip `--torch-backend cu130` or `--extra-index-url`: without them, you get a `torch` build with no CUDA support, and `marker` can then run on the CPU only.

To work with DOCX files, you need to install `pandoc` 3.1.9 or later separately:

```powershell
# Windows
winget install --source winget --exact --id JohnMacFarlane.Pandoc
```

```bash
# Ubuntu 25.10 and later
sudo apt install pandoc

# Ubuntu 22.04 and 24.04: the apt package is older than 3.1.9, so get pandoc from the releases page
curl -fsSLO https://github.com/jgm/pandoc/releases/download/3.10.1/pandoc-3.10.1-1-amd64.deb
sudo dpkg -i pandoc-3.10.1-1-amd64.deb
```

To work with DjVu files, you also need to install DjVuLibre separately. On Windows, use the [installer](https://sourceforge.net/projects/djvu/files/DjVuLibre_Windows/).

```powershell
# Windows: the installer does not add its folder to PATH, so this command does it
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";${env:ProgramFiles(x86)}\DjVuLibre", "User")
```

```bash
# Ubuntu
sudo apt install djvulibre-bin
```

When everything is in place, check the installation. If CUDA is not available, `raw2md doctor` tells you why:

```bash
raw2md doctor
```

## Folders

All service files live in the `.raw2md` folder in your home directory:

```text
~/.raw2md/
  settings.json     # models and settings; created by raw2md init
  prompts.yaml      # prompts of the LLM stages; created by raw2md init
  keywords.yaml     # words that the cleaning rules look for; created by raw2md init
  state/            # queue, lock, daily request counter
  logs/raw2md.log   # log of the last run
  tmp/              # temporary conversion files
```

The first `marker` conversion also downloads the model weights, which take about 3.3 GB:

| System | Weights folder |
|---|---|
| Windows | `%LOCALAPPDATA%\datalab\datalab\Cache\models` |
| Linux | `~/.cache/datalab/models` |

To keep the weights somewhere else, set the `MODEL_CACHE_DIR` environment variable.

## Quick start

Give raw2md a file, a folder, or nothing at all:

```bash
raw2md book.pdf   # a single file
raw2md scans      # every pdf, djvu, docx, and md file in the folder, without subfolders
raw2md            # the current folder
```

Each result lands next to its source:

```text
book.pdf   # source
book.md    # result
book/      # images, if the document has any

notes.md            # Markdown source
notes_cleaned.md    # result; the source stays untouched
```

Every result starts with a header. The `status` field holds the verdict of the quality evaluation, and `issues` lists the checks that fired:

```yaml
---
raw2md_version: 0.1.0
source: book.pdf
engine: marker
inspection: none
post: none
converted_at: 2026-10-03
source_hash: 9rZ2...
status: ok
issues:
- headings
---
```

## Options

These are the flags you will reach for most often:

| Flag | What it does |
|---|---|
| `-o DIR` | puts the results into `DIR` instead of next to the source |
| `-e <model>` | recognizes PDF and DjVu with a model instead of `marker` |
| `-i <model>` | turns on inspection, which checks the text against the source |
| `-p <model>` | turns on post-processing |
| `-s` | keeps a finished result and does not convert the file again |
| `-d` | saves the text after each stage into the `<name>.debug` folder |
| `-h` | prints the list of all flags |
| `--disable-image-extraction` | skips the images but keeps their captions |

The model in `-e`, `-i`, and `-p` is a key from `settings.json`, such as `gemini_api`. The [reference](https://github.com/MikeDolg/raw2md/blob/main/docs/reference.md) covers every flag, along with the `resume`, `init`, `settings`, `prompts`, and `keywords` commands.

## Settings

Without a settings file, raw2md falls back on its built-in settings, which know two models:

| Key | Model | Stages | What you need |
|---|---|---|---|
| `gemini_api` | Gemini through the API | `-e`, `-i`, `-p` | an API key in the `GOOGLE_API_KEY` variable |
| `claude_cli` | Claude Code through `claude -p` | `-p` | `claude` installed, signed in, and on `PATH` |

To turn on the LLM stages, put your key into `GOOGLE_API_KEY` and name the model in the flag:

```bash
raw2md book.pdf -i gemini_api -p gemini_api
```

The built-in `gemini_api` model and its limits, 15 requests per minute and 500 per day, target the free tier of Google AI Studio, so a free API key is enough to start. Google sets the actual quotas for each project and can change them. With a paid key, you can pick a larger model and raise the limits.

To change a model or its limits, create the settings file and open it:

```bash
raw2md init
raw2md settings edit
```

These are the fields you are most likely to change:

| Field | What it sets |
|---|---|
| `models.<key>.model` | the model name at the provider |
| `models.<key>.rpm`, `rpd` | the request limits per minute and per day |
| `models.<key>.pages_per_request` | how many source pages go into one request |
| `marker.recognition_batch_size` | the batch size of `marker` recognition; a smaller number uses less video memory |

The [reference](https://github.com/MikeDolg/raw2md/blob/main/docs/reference.md#service-files) describes every field, as well as `prompts.yaml` and `keywords.yaml`.

## Update

```bash
uv tool upgrade raw2md
```

If you have not edited `prompts.yaml` and `keywords.yaml`, delete them from `~/.raw2md` after the upgrade and run `raw2md init` to get the new versions: the old files replace the built-in ones, and `init` does not overwrite them.

## Uninstall

```bash
uv tool uninstall raw2md
```

The uninstall leaves `~/.raw2md` and the `marker` weights where they are.

## License notes

- The raw2md code is released under the [MIT](https://github.com/MikeDolg/raw2md/blob/main/LICENSE) license. The license covers the code only: the raw2md name and logo fall outside it, and you can use them to identify other products only with the author's permission.
- The installed tool uses `PyMuPDF` (AGPL-3.0) and `marker` (GPL-3.0). [THIRD_PARTY_NOTICES.md](https://github.com/MikeDolg/raw2md/blob/main/THIRD_PARTY_NOTICES.md) lists the licenses of all third-party components.
- The `marker` model weights come under a separate [Datalab license](https://github.com/datalab-to/marker/blob/v1.10.2/MODEL_LICENSE), a modified AI Pubs OpenRAIL-M. It allows commercial use only to organizations whose revenue and funding stay below the threshold set in the license, and it forbids such use to competitors of Datalab. The license also extends to the result of a PDF or DjVu conversion: if you publish one, credit Datalab and include the license text. DOCX conversion through `pandoc` does not use the weights.
- The LLM stages send the content of the document to the provider: inspection sends the source pages and the recognized text, `-e` sends the page images, and post-processing sends fragments of the text. How the provider stores and uses this data depends on your terms with that provider, so check them with the provider directly.
