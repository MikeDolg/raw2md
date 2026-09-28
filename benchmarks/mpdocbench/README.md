# Running MPDocBench-Parse

## Requirements

- Ubuntu 22.04.
- raw2md installed.
- An NVIDIA GPU with CUDA with 24 GB of VRAM or more.
- `uv`, `git`, `python3.10`, and root or `sudo`: the scorer setup installs
  TeX Live, ImageMagick, Ghostscript, and Node.js.
- About 4 GB of free disk space.
- For 11 documents from SlideVQA: accept its terms on the
  [Hub page](https://huggingface.co/datasets/NTT-hil-insight/SlideVQA) and log
  in with `hf auth login` or set `HF_TOKEN`. Without it, the run skips them.

## Run

```bash
git clone --depth 1 --branch v0.1.0 https://github.com/MikeDolg/raw2md
bash raw2md/benchmarks/mpdocbench/run.sh [options]
```

| Option | What it does |
|---|---|
| `--language english` | Only the English documents (193 of 420). Default: `all`. |
| `--llm MODEL` | Also run the LLM stages with this model key of `settings.json`. |
| `--documents NAME ...` | Only these documents, for a trial run. |
| `--skip-metric METRIC` | Do not compute this metric; the result shows it as `n/a`. |

The script downloads the scorer and the data, builds the scorer environment
once, converts the documents, and scores them. It creates these folders in the
current directory:

| Folder | What goes there |
|---|---|
| `mpdocbench-data/` | `upstream/` – the scorer clone; `images/` – the pages; the page archive |
| `mpdocbench-run/` | `pdfs/` – one PDF per document; `outputs/` – raw2md output; `scoring/` – scorer logs |
| `mpdocbench-scorer/` | the Python environment of the scorer |

The result is `mpdocbench-run/results.yaml`, and the script also prints it as
a table.

Single phases: `uv run --project raw2md python raw2md/benchmarks/mpdocbench/scripts/run.py --help`.
