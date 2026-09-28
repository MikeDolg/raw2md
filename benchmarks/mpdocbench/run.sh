#!/usr/bin/env bash
# Runs the whole benchmark on Ubuntu 22.04: downloads the harness and the
# pages, builds the scorer environment once, then converts and scores.
#
# Usage: bash run.sh [options of `run.py all`]
#   for example: bash run.sh --language english
# Every folder of the run is created in the current directory.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$HERE/../.."                  # the repository root, where raw2md is installed
DATA="$PWD/mpdocbench-data"
RUN="$PWD/mpdocbench-run"
# Absolute, because the scorer runs with the harness as its working directory.
SCORER="$PWD/mpdocbench-scorer"
SCORER_PYTHON="$SCORER/.venv-scorer/bin/python"

# pyarrow reads the SlideVQA pages. It is not a dependency of raw2md, so it
# comes in for this run only.
runner() {
    uv run --project "$PROJECT" --with pyarrow python "$HERE/scripts/run.py" "$@"
}

# The scorer setup reads the harness, so fetch goes first. `all` fetches again,
# and a download that is already there and matches its pin is reused.
runner fetch --data "$DATA"
if [ ! -x "$SCORER_PYTHON" ]; then
    bash "$HERE/scripts/scorer/setup.sh" "$DATA" "$SCORER"
fi
runner all --data "$DATA" --run "$RUN" --scorer-python "$SCORER_PYTHON" "$@"
