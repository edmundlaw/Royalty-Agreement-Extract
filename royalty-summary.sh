#!/usr/bin/env bash
# ./royalty-summary.sh START END MAX_EXHIBITS [--go]
set -euo pipefail
cd "$(dirname "$0")"
python_path="${ROYALTY_PYTHON:-../.venv/bin/python}"
if [[ ! -x "$python_path" ]]; then
    python_path="$(command -v python3)"
fi
export PYTHONPATH="$PWD/src"
exec "$python_path" -m royalty_research.agreement_summary batch "$@"
