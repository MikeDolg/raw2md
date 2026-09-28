#!/usr/bin/env bash
# Builds the environment of the MPDocBench scorer on Ubuntu 22.04 and checks
# that CDM answers real values.
#
# CDM renders every formula through xelatex and ImageMagick, and the harness
# shells out with `>/dev/null`, so it needs Linux. Every render, English
# formulas included, needs the font family "Source Han Sans SC". A missing
# piece is silent: CDM wraps its body in a bare `except` and returns zeros,
# which reads as a real score. That is why the script ends with a self-check.
#
# Usage, after `run.py fetch` put the harness under DATA/upstream:
#   bash scorer/setup.sh DATA [WORKDIR]
# The interpreter to pass as --scorer-python is WORKDIR/.venv-scorer/bin/python.
set -euo pipefail

DATA="${1:?usage: setup.sh DATA [WORKDIR]}"
CLONE="$DATA/upstream"                  # where run.py fetch clones the harness
FONT_RELEASE_TAG="2.005R"
FONT_ASSET="09_SourceHanSansSC.zip"
MAGICK_RELEASE_TAG="7.1.2-31"
MAGICK_ASSET="ImageMagick-${MAGICK_RELEASE_TAG}-gcc-x86_64.AppImage"  # archive/binaries/ 404s; a pinned release asset does not
WORKDIR="${2:-$HOME/mpdocbench-scorer}"  # holds the venv of the scorer

# A container runs as root and often carries no sudo, while a workstation is
# the other way round, so every privileged command goes through this prefix.
if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
elif command -v sudo >/dev/null; then
    SUDO="sudo"
else
    echo "this script installs system packages: run it as root or install sudo" >&2
    exit 1
fi

# The pins of requirements.txt are verified against this interpreter,
# and the apt package below exists for it on Ubuntu 22.04 alone. Say so here
# rather than through an apt error halfway through the install.
if ! command -v python3.10 >/dev/null; then
    echo "python3.10 is not on this image; the scorer pins are read for 3.10" >&2
    exit 1
fi

if [ ! -f "$CLONE/MPDocBench/pdf_validation.py" ]; then
    echo "no harness under $CLONE; run \`run.py fetch --data $DATA\` first" >&2
    exit 1
fi

$SUDO apt-get update
# Noninteractive: a texlive package that asks about its configuration would
# hang a session that has no terminal to answer from.
# texlive-lang-chinese carries xeCJK on Ubuntu 22.04; texlive-xecjk is not a
# package there. libfribidi0 is a library the ImageMagick AppImage needs but
# does not bundle. nodejs installs /usr/bin/node, which CDM's LaTeX
# normalizer shells out to. ghostscript is what ImageMagick delegates a PDF
# page to, and a minimal image does not have to carry it: without it every render
# fails and CDM answers zero for each formula.
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    texlive-xetex texlive-latex-recommended texlive-fonts-recommended \
    texlive-lang-chinese fontconfig curl unzip python3.10-venv \
    libfribidi0 nodejs ghostscript

# The portable AppImage, not the from-source build the CDM README asks for:
# apt's imagemagick ships IM6 (no `magick` binary), and building IM7 needs
# libpng-dev plus a compile step this script avoids.
$SUDO curl -L -o /usr/local/lib/magick.AppImage \
    "https://github.com/ImageMagick/ImageMagick/releases/download/${MAGICK_RELEASE_TAG}/${MAGICK_ASSET}"
$SUDO chmod +x /usr/local/lib/magick.AppImage

# Extracted once and kept, rather than run through --appimage-extract-and-run:
# that flag re-extracts to a fresh temp directory on every call, so a patch to
# the extracted tree would not survive past the invocation that made it.
# `magick` then execs the extracted AppRun directly, which also needs no FUSE
# mount, the reason the vendored harness's bare `magick` call needed a wrapper
# in the first place.
MAGICK_EXTRACT_PARENT="$(mktemp -d)"
(cd "$MAGICK_EXTRACT_PARENT" && /usr/local/lib/magick.AppImage --appimage-extract >/dev/null)

# ImageMagick 7 renders a PDF page through Ghostscript with
# -sDEVICE=png16malpha, which Ubuntu 22.04's Ghostscript 9.55 does not know;
# pngalpha is the name it does know. The AppImage reads its delegates config
# from inside itself with no override from outside, so the fix has to land in
# the extracted copy instead.
mapfile -t MAGICK_DELEGATE_FILES < <(grep -rl 'png16malpha' "$MAGICK_EXTRACT_PARENT/squashfs-root" || true)
if [ "${#MAGICK_DELEGATE_FILES[@]}" -eq 0 ]; then
    echo "no delegates config under the AppImage names the ghostscript device" \
         "png16malpha; the fix may no longer be needed, or the config moved" >&2
    exit 1
fi
sed -i 's/png16malpha/pngalpha/g' "${MAGICK_DELEGATE_FILES[@]}"

$SUDO rm -rf /usr/local/lib/magick.AppDir
$SUDO mv "$MAGICK_EXTRACT_PARENT/squashfs-root" /usr/local/lib/magick.AppDir
rm -rf "$MAGICK_EXTRACT_PARENT"
$SUDO rm -f /usr/local/lib/magick.AppImage

printf '#!/usr/bin/env bash\nexec /usr/local/lib/magick.AppDir/AppRun "$@"\n' \
    | $SUDO tee /usr/local/bin/magick >/dev/null
$SUDO chmod +x /usr/local/bin/magick
magick --version

curl -L -o /tmp/source-han-sans-sc.zip \
    "https://github.com/adobe-fonts/source-han-sans/releases/download/${FONT_RELEASE_TAG}/${FONT_ASSET}"
mkdir -p ~/.fonts
unzip -j /tmp/source-han-sans-sc.zip '*.otf' -d ~/.fonts
fc-cache -f ~/.fonts
fc-list | grep -i "Source Han Sans SC" || echo "WARNING: font family not registered under the expected name"

mkdir -p "$WORKDIR"
python3.10 -m venv "$WORKDIR/.venv-scorer"
"$WORKDIR/.venv-scorer/bin/pip" install --upgrade pip
"$WORKDIR/.venv-scorer/bin/pip" install -r "$(dirname "$0")/requirements.txt"

# Named rather than left to the self-check below: `node` changes the score of
# a changed pair without breaking it, so its absence hides inside a plausible
# number, and `gs` is reached by ImageMagick through a shell.
for tool in node gs; do
    if ! command -v "$tool" >/dev/null; then
        echo "$tool is not on PATH after the install above; CDM needs both" \
             "node (its LaTeX normalizer) and gs (the PDF delegate of" \
             "ImageMagick), and a missing one is not reported as an error" >&2
        exit 1
    fi
done

# Self-check: CDM.evaluate() wraps its body in a bare `except` and returns a
# zero score on a broken toolchain, which reads as a real result rather than
# a setup failure. The harness's own demo pair
# (metrics/cdm/assets/example/input_example.json, case_2) is one changed token
# out of seven, so it separates a working environment from both failures that
# score without erroring.
HARNESS="$CLONE/MPDocBench"
CHECK_DIR="$(mktemp -d)"
CHECK_OUTPUT="$(cd "$HARNESS" && "$WORKDIR/.venv-scorer/bin/python" - "$CHECK_DIR" <<'PY'
import json
import sys

from metrics.cdm_metric import CDM

with open(
    "metrics/cdm/assets/example/input_example.json", encoding="utf-8"
) as handle:
    demo = json.load(handle)
pair = next(item for item in demo if item["img_id"] == "case_2")

cdm = CDM(output_root=sys.argv[1])
identical = cdm.evaluate(pair["gt"], pair["gt"], "selfcheck_identical")["F1_score"]
changed = cdm.evaluate(pair["gt"], pair["pred"], "selfcheck_changed")["F1_score"]
print(identical, changed)
PY
)"
rm -rf "$CHECK_DIR"

# The last line, not the first: CDM shells out to xelatex and magick with the
# stdout of this process, and only the xelatex call redirects, so a line from a
# render would otherwise be read in place of the numbers.
read -r CHECK_IDENTICAL CHECK_CHANGED <<< "$(printf '%s\n' "$CHECK_OUTPUT" | tail -n 1)"
# A range, not a constant: the score of the changed pair is the share of boxes
# that matched, and how a renderer splits one formula into boxes moves with the
# versions of xelatex, ImageMagick and the font. A broken toolchain scores the
# pair 0, and a matcher that sees one box scores it 1, so the environment is
# trustworthy exactly between them.
if ! awk -v identical="${CHECK_IDENTICAL:-none}" -v changed="${CHECK_CHANGED:-none}" \
    'BEGIN { exit !(identical == 1 && changed > 0 && changed < 1) }'; then
    echo "CDM self-check failed: identical pair scored '${CHECK_IDENTICAL:-<none>}'" \
         "(want 1.0), changed pair scored '${CHECK_CHANGED:-<none>}' (want a value" \
         "above 0 and below 1). A silent toolchain failure in CDM.evaluate() reads" \
         "as a real zero score, so this environment cannot be trusted to score" \
         "formulas yet." >&2
    exit 1
fi
echo "CDM self-check passed: identical pair $CHECK_IDENTICAL, changed pair $CHECK_CHANGED"

echo "Scorer environment ready at $WORKDIR"
echo "  harness: $HARNESS"
echo "  venv:    $WORKDIR/.venv-scorer"
