# M13 v0.13.6 — routine full-source run

## Routine use

1. In Terminal type `royalty` (shell alias; takes you to `~/royalty-research`), then `cd m13`.
2. Dry run (no AI calls, shows what would be called and prompt sizes): `./royalty.sh 2026-01-12 2026-01-14 5`
3. Real run: the same command with `--go` at the end. The workbook is copied to `~/Downloads/Royalty_Research_<START>_<END>.xlsx`.

Run the script yourself in Terminal. Running the tool through a Codex or Claude chat agent wastes most of the allowance on the agent's own reading and retries.

**Production path:** `scripts/m13_prod.py` prepares a complete source packet for every selected agreement. The `lean_research.py` excerpt path is preliminary triage only. AI output is never certified as contract-complete by Python.

## Install and prerequisites

Python 3.10+; `pip install -e '.[xlsx,pdf]'` in a local virtual environment. No API keys. For live SEC downloads, supply a descriptive SEC user agent with contact email. Automated modes require a working `claude` or `codex` CLI authenticated to the user's existing subscription. The code checks subscription login, refuses provider API-key/billing overrides, and requires explicit execution flags. Confirm account credit settings yourself; the CLI cannot prove them. Manual mode needs no CLI or AI call.

## Prepare once

For an existing M1 map:

```sh
PYTHONPATH=src python3 scripts/m13_prod.py prepare --map /path/to/map.json --run /path/to/batch/runs/agreement-1 --mode manual --model chosen-ai
```

For SEC discovery results (`discover` JSONL with `source_url`), prepare a bounded batch. This downloads/maps each unique candidate once and writes `candidate_register.json`; low-signal and failed candidates remain visible:

```sh
PYTHONPATH=src python3 scripts/m13_prod.py batch --candidates /path/to/discover.jsonl --root /path/to/batch --user-agent 'Name contact@example.com' --mode single --engine codex --model MODEL --effort low --max-agreements 5
```

Use `--mode two --check-engine claude --check-model MODEL --check-effort medium` for independent full-source readers. `--mode manual` prepares prompts with no automatic AI call. `--max-chars` changes chunk size, not coverage; all source passages remain in the immutable packet.

## Read and finish

**Manual:** give each `runs/<id>/reader_a/prompts/CHUNK-*.txt` to the chosen AI in a fresh context. Save the returned JSON and import each chunk:

```sh
PYTHONPATH=src python3 scripts/m13_prod.py import --run /path/to/run --task CHUNK-0001 --response /path/to/answer.json
```

**Automated single or two reader:** one bounded Python invocation executes at most the stated number of calls. No AI controller, continuous polling or automatic retry:

```sh
PYTHONPATH=src python3 scripts/m13_prod.py run --runs /path/to/batch/runs --max-calls 2 --max-prompt-chars 300000 --max-reported-tokens 200000 --execute --confirm-subscription --confirm-credit-controls
```

Omit `--execute` for a dry run. `--max-calls`, `--max-agreements`, `--max-retries` (default zero), prompt-character cap and per-call `--timeout` are hard task-boundary stops. `--max-reported-tokens` stops subsequent calls when the CLI reports that threshold; if prior usage is unavailable, it stops instead of assuming zero. A single call may exceed the remaining reported-token budget because the CLI does not expose a pre-call token guarantee. Reader receipts record available input, cached-input, output and reasoning token counts; unavailable fields stay unknown. Failed or interrupted tasks require explicit manual retry through the original M13/M4 recovery commands. Restart `run` to resume captured work; it does not repeat completed calls.

When all chunks have been captured:

```sh
PYTHONPATH=src python3 scripts/m13_prod.py finalize --run /path/to/run
PYTHONPATH=src python3 scripts/m13_prod.py combine --runs /path/to/batch/runs --out /path/to/Combined_Royalty_Research.xlsx
```

Add `--legacy-xlsx` to `finalize` for the optional 16-sheet technical workbook. The default export is the established five-sheet workbook. `combine` lists unfinished runs in its result and workbook overview; they are not silently treated as complete.

## Status and interpretation

Use `PYTHONPATH=src python3 -m royalty_research m13-status --root /path/to/run` for a single status snapshot. `SINGLE_READER_NOT_CHECKED` means one full-source extraction with mechanical source checks only. `TWO_READERS_DIFFER` requires source review. `SOURCE_CHECK_FAILED` is unusable without correction. Even `TWO_READERS_AGREE` is not proof of semantic accuracy or completeness. Review source clauses at the point of valuation use. The candidate register distinguishes low-signal, processing failure and agreement-limit deferral; none means irrelevant.

Troubleshooting: use `--help` for exact flags. A missing result cannot be finalized; an interrupted/failed CLI task will not retry automatically. Keep prompts and answers under the batch directory, inspect the task's attempt receipt, and use the existing explicit retry/recovery workflow only after checking whether subscription usage was consumed.
