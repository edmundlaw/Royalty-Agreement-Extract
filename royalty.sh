#!/usr/bin/env bash
# One-command royalty research run.
#   ./royalty.sh START END [MAX_AGREEMENTS]        dry run: discover, prepare, show what would be called
#   ./royalty.sh START END [MAX_AGREEMENTS] --go   also call the AI, finalize, combine, copy to ~/Downloads
#   --big   also read licences over 120,000 characters (several calls each; off by default)
# Dates are YYYY-MM-DD. MAX_AGREEMENTS defaults to 5. Candidate choice is the fixed rule in
# `m13_prod.py batch`; nobody (human or AI) picks agreements.
# Hidden option: --candidates FILE  skips the SEC discover step and uses an existing discovery JSONL.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
PY="${ROYALTY_PYTHON:-$ROOT/../.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
export PYTHONPATH="$ROOT/src"
# SEC requires a contact in the User-Agent. Kept out of the repo: set ROYALTY_SEC_UA or put
# "Name contact@email" on the first line of ~/.config/royalty-research/sec_user_agent.
UA="${ROYALTY_SEC_UA:-}"
UA_FILE="$HOME/.config/royalty-research/sec_user_agent"
[ -n "$UA" ] || { [ -f "$UA_FILE" ] && UA="$(head -n1 "$UA_FILE")"; } || true
[ -n "$UA" ] || { echo "Missing SEC contact: put 'Name contact@email' in $UA_FILE (or set ROYALTY_SEC_UA)." >&2; exit 2; }

GO=0; BIG=0; CANDS=""; ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --go) GO=1 ;;
    --big) BIG=1 ;;
    --candidates) shift; CANDS="${1:?--candidates needs a file}" ;;
    -h|--help) sed -n 2,8p "$0"; exit 0 ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done
[ "${#ARGS[@]}" -ge 2 ] && [ "${#ARGS[@]}" -le 3 ] || { echo "Usage: ./royalty.sh START END [MAX_AGREEMENTS] [--go]" >&2; exit 2; }
START="${ARGS[0]}"; END="${ARGS[1]}"; MAX="${ARGS[2]:-5}"
re='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
[[ "$START" =~ $re && "$END" =~ $re ]] || { echo "Dates must be YYYY-MM-DD" >&2; exit 2; }
[[ "$MAX" =~ ^[0-9]+$ ]] && [ "$MAX" -ge 1 ] || { echo "MAX_AGREEMENTS must be a positive number" >&2; exit 2; }

step() { echo; echo "=== $* ==="; }
fail() { echo; echo "STOPPED: $* failed. Nothing further was run." >&2; exit 1; }

BATCH="$ROOT/runs_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BATCH"
echo "Batch folder: $BATCH"
[ "$GO" = 1 ] && echo "MODE: LIVE (AI calls will be made)" || echo "MODE: DRY RUN (no AI calls; add --go to run for real)"

if [ -n "$CANDS" ]; then
  step "1/4 Discover (skipped, using $CANDS)"
  cp "$CANDS" "$BATCH/discovery.jsonl" || fail "copy candidates"
else
  step "1/4 Discover SEC filings $START to $END"
  "$PY" -m royalty_research discover --start "$START" --end "$END" \
    --query 'royalty rate' --query 'license agreement' --query 'royalties' \
    --user-agent "$UA" --out "$BATCH/discovery.jsonl" || fail "discover"
fi

step "2/4 Prepare up to $MAX agreements (fixed rule, no manual picking)"
"$PY" scripts/m13_prod.py batch --candidates "$BATCH/discovery.jsonl" --root "$BATCH/batch" \
  --user-agent "$UA" --mode single --engine codex --model gpt-6-sol --effort low \
  --max-agreements "$MAX" $( [ "$BIG" = 1 ] && echo --max-source-chars 2000000 ) || fail "batch prepare"

echo; echo "Candidate summary (full list: $BATCH/batch/candidate_register.json):"
"$PY" -I -c '
import json,sys,collections
L=json.load(open(sys.argv[1]))
for k,v in collections.Counter(x["status"] for x in L).most_common(): print(f"  {v:5d}  {k}")
for x in L:
    if x["status"] in ("FULL_SOURCE_PREPARED","NOT_PREPARED_TOO_LARGE"):
        g=x.get("licence_gate") or {}
        print("  "+x["status"][:22].ljust(22), str(x.get("file_type") or "")[:9].ljust(9), str(x.get("company") or "")[:40].ljust(40), g.get("source_chars"), "chars")
' "$BATCH/batch/candidate_register.json" || true

step "3/4 Reader calls (max $((2*MAX)) calls)"
RUNARGS=(run --runs "$BATCH/batch/runs" --max-calls $((2*MAX)) --max-prompt-chars 300000 --max-reported-tokens 200000)
[ "$GO" = 1 ] && RUNARGS+=(--execute --confirm-subscription --confirm-credit-controls)
"$PY" scripts/m13_prod.py "${RUNARGS[@]}" || fail "run"

echo; echo "Prompt sizes (characters):"
find "$BATCH/batch/runs" -path '*prompts/*.txt' -exec wc -c {} + 2>/dev/null | sed 's|'"$BATCH"'/||' || true

if [ "$GO" != 1 ]; then
  echo; echo "Dry run finished. Nothing was sent to an AI. Re-run with --go to do it for real."
  exit 0
fi

step "4/4 Finalize, combine, copy"
for run in "$BATCH"/batch/runs/*/; do
  [ -f "$run/m13_run.json" ] || continue
  "$PY" scripts/m13_prod.py finalize --run "$run" || echo "NOTE: $(basename "$run") not finalized (reading incomplete); it is left out of the workbook"
done
OUT="$BATCH/Royalty_Research_${START}_${END}.xlsx"
"$PY" scripts/m13_prod.py combine --runs "$BATCH/batch/runs" --out "$OUT" || fail "combine"
mkdir -p "$HOME/Downloads"
cp "$OUT" "$HOME/Downloads/Royalty_Research_${START}_${END}.xlsx" || fail "copy to Downloads"
echo; echo "Done: $HOME/Downloads/Royalty_Research_${START}_${END}.xlsx"
