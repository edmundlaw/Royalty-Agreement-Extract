# M13 v0.13.9 — routine full-source run

## Routine use

1. In Terminal type `royalty` (shell alias; takes you to `~/royalty-research`), then `cd m13`.
2. Dry run (no AI calls, shows what would be called and prompt sizes): `./royalty.sh 2026-01-12 2026-01-14 5`
3. Real run: the same command with `--go` at the end. The workbook is copied to `~/Downloads/Royalty_Research_<START>_<END>.xlsx`.
4. An agreement left half read (call limit, a stop, or a failure)? Finish it without discovering or preparing again: `./royalty.sh --resume runs_YYYYMMDD_HHMMSS` (dry run: shows the remaining calls) then the same with `--go`. Resume makes only the calls still missing, finalizes agreements not yet finalized, and writes a new workbook beside the old one (`..._v<version>.xlsx`; an earlier workbook is never overwritten). The finalize step prints one line per agreement and lists any that are still unfinished; error details go to `batch/finalize_errors.log`.

Run the script yourself in Terminal. Running the tool through a Codex or Claude chat agent wastes most of the allowance on the agent's own reading and retries.

Which agreements are read (fixed Python rules, zero AI tokens; full list in `batch/candidate_register.json`):
- Order: EX-10 exhibits first, then other contract exhibits, then prospectuses/press releases; more matched search terms first.
- Licence check: "royalt" appears 3+ times, and the document's title (first lines, not the recitals) decides. A title naming a licence/royalty/collaboration/franchise agreement passes. A title naming services, purchase, loan, credit, security, guarantee, employment, consulting, separation, settlement, assignment, merger, underwriting, indenture, lease, supply or joint venture (without a licence word) is rejected unless the text has 25+ licence-grant phrases ("grants ... a licence", "hereby licenses", "exclusive licence", "Licensed Product" ...) and dense royalty wording. Other titles need dense royalty wording (1+ per 10,000 characters) or a licence named in the opening, plus at least one licence-grant phrase. Rejected documents become `NOT_PREPARED_NOT_LICENCE_LIKE`; the register shows the detected title and grant count (`licence_gate`).
- Size: licences over 120,000 characters become `NOT_PREPARED_TOO_LARGE` (each would need several reader calls). Add `--big` to read them.
- The agreement limit counts agreements actually prepared; at most 10 downloads per agreement requested (`NOT_PREPARED_DOWNLOAD_LIMIT`).
These rules trade completeness for allowance: a genuine licence with little royalty wording can be skipped. Nothing is deleted; skipped items stay listed.

**Production path:** `scripts/m13_prod.py` prepares a complete source packet for every selected agreement. The `lean_research.py` excerpt path is preliminary triage only. AI output is never certified as contract-complete by Python.

**v0.13.9 workbook notes:** rate cells are real percentages (cell value 0.05, shown 5.00%; use them directly in formulas). `Nature of IA` lists every component of a mixed licence (`MIXED: patent, know-how, trademark/brand`; `(inferred)` or `(keyword hint)` labels say where the list came from). Other terms carry a `Valuation relevance` tier set by Python rules: KEY terms are summarised in sheet 01, sheet 06 lists KEY, SUPPLEMENTARY, then greyed ADMIN rows; unsure terms are SUPPLEMENTARY.

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

Add `--legacy-xlsx` to `finalize` for the optional 16-sheet technical workbook. The default export is the established five-sheet workbook. `combine` lists unfinished runs in its result and workbook overview; they are not silently treated as complete. The default workbook also opens with sheet `00 Run Summary` (v0.13.8): one row per run folder with Status (EXPORTED / NOT_FINISHED - n of m reading calls done / FAILED - reason), QC state and royalty row count, a counts line, and counts of candidates the batch did not read. `Usable for royalty benchmark` is NO with first reason `needs review: <state>` for `SOURCE_CHECK_FAILED`, `SECOND_READER_FAILED_SOURCE_CHECK` and `TWO_READERS_DIFFER`, and for any row with its own source-check error; `TWO_READERS_AGREE_ON_NUMBERS` stays YES with a note to read the STRUCTURE differences.

## Status and interpretation

Use `PYTHONPATH=src python3 -m royalty_research m13-status --root /path/to/run` for a single status snapshot. `SINGLE_READER_NOT_CHECKED` means one full-source extraction with mechanical source checks only. `TWO_READERS_DIFFER` requires source review. `SOURCE_CHECK_FAILED` is unusable without correction. Even `TWO_READERS_AGREE` is not proof of semantic accuracy or completeness. Review source clauses at the point of valuation use. The candidate register distinguishes low-signal, processing failure and agreement-limit deferral; none means irrelevant.

Troubleshooting: use `--help` for exact flags. A missing result cannot be finalized; an interrupted/failed CLI task will not retry automatically. Keep prompts and answers under the batch directory, inspect the task's attempt receipt, and use the existing explicit retry/recovery workflow only after checking whether subscription usage was consumed.
