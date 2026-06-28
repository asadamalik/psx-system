#!/usr/bin/env bash
# One-time setup on ANY machine (or after moving the folder).
# A Python venv is NOT portable — it hardcodes its original path — so this rebuilds it
# fresh at the current location. The code and data in this folder ARE portable.
#
# Usage:  cd into this folder, then run:   ./setup.sh
set -e
cd "$(dirname "$0")"

echo "==> Rebuilding the virtual environment for: $(pwd)"
rm -rf .venv
python3 -m venv .venv
./.venv/bin/pip install -U pip -q
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m playwright install chromium

echo ""
echo "==> Done. This venv now points at the current folder."
echo "    Test it:   ./.venv/bin/python scripts/daily_run.py --no-scrape"
echo "    Live run:  ./.venv/bin/python scripts/daily_run.py"
