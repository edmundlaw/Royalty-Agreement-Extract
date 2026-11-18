#!/usr/bin/env bash
# One-command royalty research run.
#   ./royalty.sh START END [MAX_AGREEMENTS]        dry run: discover, prepare, show what would be called
#   ./royalty.sh START END [MAX_AGREEMENTS] --go   also call the AI, finalize, combine, copy to ~/Downloads
#   ./royalty.sh --resume RUNS_FOLDER [--go]       skip discover/prepare; finish the remaining reader calls of an earlier
#                                                  run folder (dry run shows them; --go makes them), then finalize/combine/copy
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
# Single version source: src/royalty_research/__init__.py. Read as text, never imported: "python -I" ignores
# PYTHONPATH and picked up an old editable install (0.8.1) of another checkout for the workbook name.
VER="$(sed -n 's/^__version__ *= *"\(.*\)".*/\1/p' "$ROOT/src/royalty_research/__init__.py" | head -n1)"
[ -n "$VER" ] || { echo "Cannot read the package version" >&2; exit 2; }
[ "${1:-}" = "--version" ] && { echo "$VER"; exit 0; }
# SEC requires a contact in the User-Agent. Kept out of the repo: set ROYALTY_SEC_UA or put
# "Name contact@email" on the first line of ~/.config/royalty-research/sec_user_agent.
UA="${ROYALTY_SEC_UA:-}"
UA_FILE="$HOME/.config/royalty-research/sec_user_agent"
[ -n "$UA" ] || { [ -f "$UA_FILE" ] && UA="$(head -n1 "$UA_FILE")"; } || true
[ -n "$UA" ] || { echo "Missing SEC contact: put 'Name contact@email' in $UA_FILE (or set ROYALTY_SEC_UA)." >&2; exit 2; }

GO=0; BIG=0; CANDS=""; RESUME=""; ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --go) GO=1 ;;
    --big) BIG=1 ;;
    --candidates) shift; CANDS="${1:?--candidates needs a file}" ;;
    --resume) shift; RESUME="${1:?--resume needs a runs_... folder}" ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done
if [ -n "$RESUME" ]; then
  [ "${#ARGS[@]}" -eq 0 ] || { echo "--resume takes only the folder (and optional --go)" >&2; exit 2; }
  [ -d "$RESUME/batch/runs" ] || { echo "Not a runs folder (no batch/runs inside): $RESUME" >&2; exit 2; }
  BATCH="$(cd "$RESUME" && pwd)"
  # Dates for the output file name: run_info.json (new runs) or the name of an earlier workbook.
  if [ -f "$BATCH/run_info.json" ]; then
    read -r START END < <("$PY" -I -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["start"],d["end"])' "$BATCH/run_info.json")
  else
    prev="$(ls "$BATCH"/Royalty_Research_????-??-??_????-??-??*.xlsx 2>/dev/null | head -1 || true)"
    START="unknown"; END="unknown"
    if [[ "$(basename "${prev:-x}")" =~ ^Royalty_Research_([0-9-]{10})_([0-9-]{10}) ]]; then START="${BASH_REMATCH[1]}"; END="${BASH_REMATCH[2]}"; fi
  fi
  NRUNS=$(find "$BATCH/batch/runs" -maxdepth 2 -name m13_run.json | wc -l | tr -d ' ')
  MAX=$(( NRUNS > 0 ? NRUNS : 1 ))
else
[ "${#ARGS[@]}" -ge 2 ] && [ "${#ARGS[@]}" -le 3 ] || { echo "Usage: ./royalty.sh START END [MAX_AGREEMENTS] [--go]   or   ./royalty.sh --resume RUNS_FOLDER [--go]" >&2; exit 2; }
START="${ARGS[0]}"; END="${ARGS[1]}"; MAX="${ARGS[2]:-5}"
re='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
[[ "$START" =~ $re && "$END" =~ $re ]] || { echo "Dates must be YYYY-MM-DD" >&2; exit 2; }
[[ "$MAX" =~ ^[0-9]+$ ]] && [ "$MAX" -ge 1 ] || { echo "MAX_AGREEMENTS must be a positive number" >&2; exit 2; }
fi

step() { echo; echo "=== $* ==="; }
fail() { echo; echo "STOPPED: $* failed. Nothing further was run." >&2; exit 1; }

if [ -z "$RESUME" ]; then
BATCH="$ROOT/runs_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BATCH"
printf '{"start":"%s","end":"%s","max_agreements":%s}\n' "$START" "$END" "$MAX" > "$BATCH/run_info.json"
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
  --user-agent "$UA" --mode single --engine codex --model gpt-6.2-sol --effort low \
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
else
  echo "Resuming $BATCH (discover and prepare skipped)"
  [ "$GO" = 1 ] && echo "MODE: LIVE (AI calls will be made)" || echo "MODE: DRY RUN (no AI calls; add --go to run for real)"
fi

step "3/4 Reader calls (max $((2*MAX)) calls)"
TOKENS=200000
if [ -n "$RESUME" ]; then   # the budget is for the NEW calls: add what earlier calls of this folder already used
  USED=$("$PY" -I -c '
import json,sys,glob
t=0
for f in glob.glob(sys.argv[1]+"/*/reader_*/results/*.receipt.json"):
    u=json.load(open(f)).get("usage") or {}
    t+=sum(v for k,v in u.items() if k in ("input_tokens","output_tokens") and isinstance(v,int))
print(t)' "$BATCH/batch/runs")
  TOKENS=$((TOKENS + USED))
fi
RUNARGS=(run --runs "$BATCH/batch/runs" --max-calls $((2*MAX)) --max-prompt-chars 300000 --max-reported-tokens "$TOKENS")
[ "$GO" = 1 ] && RUNARGS+=(--execute --confirm-subscription --confirm-credit-controls)
"$PY" scripts/m13_prod.py "${RUNARGS[@]}" || fail "run"

echo; echo "Prompt sizes (characters):"
find "$BATCH/batch/runs" -path '*prompts/*.txt' -exec wc -c {} + 2>/dev/null | sed 's|'"$BATCH"'/||' || true

if [ "$GO" != 1 ]; then
  echo; echo "Dry run finished. Nothing was sent to an AI. Re-run with --go to do it for real."
  exit 0
fi

step "4/4 Finalize, combine, copy"
[ "$START" != unknown ] || fail "date range unknown (no run_info.json or earlier workbook in $BATCH)"
FINLOG="$BATCH/batch/finalize_errors.log"
UNFINISHED=0
for run in "$BATCH"/batch/runs/*/; do
  [ -f "$run/m13_run.json" ] || continue
  name="$(basename "$run")"
  if [ -f "$run/output/rows.json" ] || [ -f "$run/output_checked/rows.json" ]; then
    echo "  $name: already finalized"; continue
  fi
  if "$PY" scripts/m13_prod.py finalize --run "$run" >/dev/null 2>>"$FINLOG"; then
    echo "  $name: finalized"
  else
    UNFINISHED=$((UNFINISHED+1))
    echo "  $name: NOT FINALIZED, left out of the workbook ($(tail -n 1 "$FINLOG" 2>/dev/null | cut -c1-200)). Details: $FINLOG"
  fi
done
[ "$UNFINISHED" -gt 0 ] && echo "  $UNFINISHED agreement(s) unfinished; finish them with: ./royalty.sh --resume $BATCH --go"
BASE="Royalty_Research_${START}_${END}"
SUFFIX=""
if [ -e "$BATCH/$BASE.xlsx" ] || [ -e "$HOME/Downloads/$BASE.xlsx" ]; then   # never overwrite an earlier workbook
  SUFFIX="_v${VER}"; n=2
  while [ -e "$BATCH/$BASE$SUFFIX.xlsx" ] || [ -e "$HOME/Downloads/$BASE$SUFFIX.xlsx" ]; do SUFFIX="_v${VER}_$n"; n=$((n+1)); done
fi
OUT="$BATCH/$BASE$SUFFIX.xlsx"
"$PY" scripts/m13_prod.py combine --runs "$BATCH/batch/runs" --out "$OUT" >/dev/null || fail "combine"
mkdir -p "$HOME/Downloads"
cp "$OUT" "$HOME/Downloads/$BASE$SUFFIX.xlsx" || fail "copy to Downloads"
echo; echo "Done: $HOME/Downloads/$BASE$SUFFIX.xlsx"
