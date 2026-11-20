#!/bin/sh
# Build the draft manuscript: figures, then HTML, then PDF. Offline.
#
#   sh paper/manuscript/build.sh
#
# Needs pandoc. The PDF step prints the HTML with a Chromium-based browser and is
# skipped if none is found; set CHROME to its executable to choose one. For arXiv,
# convert the same Markdown to LaTeX instead:
#   pandoc adaptive-rag-pilot.md --citeproc -s -o adaptive-rag-pilot.tex
set -eu

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out="$here/build"
name=adaptive-rag-pilot
mkdir -p "$out"

"$root/.venv/bin/python" "$here/make_figures.py"
"$root/.venv/bin/python" "$here/check_numbers.py"

cd "$here"
pandoc "$name.md" \
  --from markdown --to html5 --standalone --citeproc \
  --css style.css --embed-resources --mathml \
  --columns=10000 -M document-css=false \
  --output "$out/$name.html"
echo "wrote $out/$name.html"

chrome=${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}
if [ -x "$chrome" ]; then
  profile=$(mktemp -d)
  "$chrome" --headless=new --disable-gpu --no-pdf-header-footer \
    --user-data-dir="$profile" \
    --print-to-pdf="$out/$name.pdf" "file://$out/$name.html" >/dev/null 2>&1
  rm -rf "$profile"
  echo "wrote $out/$name.pdf"
else
  echo "no Chromium-based browser found; PDF step skipped"
fi
