#!/usr/bin/env bash
# sync.sh — incremental update for aeon-movie-maker.
set -euo pipefail
[[ -f .env ]] && { set -a; source .env; set +a; }

c_blu(){ printf '\033[36m%s\033[0m\n' "$*"; }
c_grn(){ printf '\033[32m%s\033[0m\n' "$*"; }
c_yel(){ printf '\033[33m%s\033[0m\n' "$*"; }

NO_MODELS=0
for arg in "$@"; do [[ "$arg" == "--no-models" ]] && NO_MODELS=1; done

c_blu "==> aeon-movie-maker sync"

c_blu "[1/3] git pull"
git pull --ff-only

c_blu "[2/3] pip install -r requirements.txt"
python -m pip install --quiet -r requirements.txt
c_grn "      ✓ deps up to date"

if [[ $NO_MODELS -eq 1 ]]; then
    c_yel "[3/3] --no-models: skipping model check"
else
    c_blu "[3/3] model delta-check"
    ./setup.sh | tail -n 40 || true
fi

echo ""
c_grn "==> sync complete"
