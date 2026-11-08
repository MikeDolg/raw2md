# Running MPDocBench-Parse

## Requirements

- Ubuntu 22.04.
- raw2md installed.
- An NVIDIA GPU with CUDA with 24 GB of VRAM or more.
- `uv`, `git`, and root or `sudo`: the scorer setup installs TeX Live,
  ImageMagick, Ghostscript, Node.js, and, through `uv`, Python 3.14.
- About 4 GB of free disk space.
- For 11 documents from SlideVQA: accept its terms on the
  [Hub page](https://huggingface.co/datasets/NTT-hil-insight/SlideVQA) and log
  in with `hf auth login` or set `HF_TOKEN`. Without it, the run skips them.

## Run

```bash
git clone --depth 1 --branch v0.3.0 https://github.com/MikeDolg/raw2md
bash raw2md/benchmarks/mpdocbench/run.sh [options]
```

| Option | What it does |
|---|---|
| `--language english` | Only the English documents (193 of 420). Default: `all`. |
| `--llm MODEL` | Also run the LLM stages with this model key of `settings.json`. |
| `--documents NAME ...` | Only these documents, for a trial run. |
| `--skip-metric METRIC` | Do not compute this metric; the result shows it as `n/a`. If Overall uses the metric, Overall is `n/a` too. |

The script downloads the scorer and the data, builds the scorer environment
once, converts the documents, and scores them. It creates these folders in the
current directory:

| Folder | What goes there |
|---|---|
| `mpdocbench-data/` | `upstream/` – the scorer clone; `images/` – the pages; the page archive |
| `mpdocbench-run/` | `pdfs/` – one PDF per document; `outputs/` – raw2md output; `scoring/` – the copies of the Markdown files that the scorer reads, the scorer logs, `metric_result.json`, and the per-sample score files of the scorer (`*_per_page_edit.json`, `*_per_table_TEDS.json`, `*_per_sample_CDM.json`, `*_per_sample_HeadTEDS.json`, `*_per_doc_FigureF1.json`) |
| `mpdocbench-scorer/` | the Python environment of the scorer |

The result is `mpdocbench-run/results.yaml`: the score of each metric and
Overall. The script also prints the result as a table.

Single phases: `uv run --project raw2md python raw2md/benchmarks/mpdocbench/scripts/run.py --help`.
