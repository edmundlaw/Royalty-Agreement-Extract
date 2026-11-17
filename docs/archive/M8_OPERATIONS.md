# M8 v0.8.0 — Integrated subscription-only operations

**Current authoritative instructions.** M8 is a development build, not a validated historical royalty dataset. Runs locally on Python, existing Codex/Claude Code subscriptions, JSON checkpoints, and Excel. It does not use paid model APIs or hosted infrastructure. There is **no human approval, review queue, reviewer identity, sign-off, or human-approved sheet**. All research output records including automated QC failures remain visible in Excel.

## Design decisions

- First-reader model tasks use the **full M1 source map**, split only by bounded packet size (`max_chars`). The M7 focused/remainder packets remain a complementary diagnostic and possible future optimization: they are not substituted for full source reading without proven recall.
- All full-source passages are accounted for in the M4 task ledger before M8 allows occurrence classification. An occurrence task uses **immutable Python-issued occurrence IDs** tied to original map and raw primary extraction.
- The first reader and secondary occurrence reader can use different subscription-model/CLI choices. **Recommended first live experiment:** first reader Claude Sonnet or Codex lightweight model, occurrence reader Claude Sonnet; do not assume lower real usage without measurements.
- Zero detected numeric or written economic occurrences does **not** establish the absence of licensing economics. A full-source first reader is still required; only the unnecessary occurrence ledger step is skipped.
- If one original source paragraph is fragmented **across model calls**, the final record receives an automatic HIGH open issue. Textual section references across tasks also receive HIGH open issues where discoverable. This does not resolve contractual meaning.
- The model is called **at most once per explicit `--execute` command**. There is no unattended queue and no automatic retry after ambiguous interruption or credit-limit message. Subscription login and extra-credit/auto-reload settings must be checked externally. CLI flags are operational billing acknowledgements, **not approval of extracted records**.
- CSV and Excel are both research outputs; a deterministic pass does not certify legal interpretation, clause recall, or professional reliability. Use QC/Open Issues sheets to inspect unresolved risks.

## Local setup

From project root (on Mac):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[xlsx,pdf]'
python -m unittest discover -s tests -q
python -m royalty_research --version
```

All commands below use a **locally saved M1 map** (made with the existing `map` command). No historical bulk run is included.

## Practical M8 procedure, one agreement at a time

**1. Prepare and check a complete reading plan.** This performs no model inference.

```bash
python -m royalty_research m8-prepare --map agreement_map.json \
  --root work/AGREEMENT_001 --engine codex --model YOUR_AVAILABLE_CODEX_MODEL \
  --ledger-engine claude --ledger-model sonnet \
  --max-chars 64000 --ledger-max-chars 14000
python -m royalty_research m8-status --root work/AGREEMENT_001
python -m royalty_research m8-crossrefs --map agreement_map.json --out work/AGREEMENT_001_crossrefs.json
```

Only use model labels actually available in your signed-in CLI. The first reader's `--max-chars` is a **source character** limit, not a token/usage guarantee. Compare prompt sizes and output quality before changing it.

**2. Controlled first-reader execution.** The default is a dry run.

```bash
python -m royalty_research m8-primary-next --root work/AGREEMENT_001
python -m royalty_research m8-primary-next --root work/AGREEMENT_001 \
  --execute --confirm-subscription --confirm-credit-controls
python -m royalty_research m8-status --root work/AGREEMENT_001
```

Each explicit `--execute` invokes **one** task. Repeat only when the current task was captured, not automatically. If failed/interrupted, use existing `m4-status`, `m4-recover-result`, `m4-authorize-retry`, and `m4-clear-limit` commands on `work/AGREEMENT_001/primary_plan` as appropriate. Never replay an ambiguous subscription call automatically.

**3. Issue bounded second-stage ledger tasks after all primary tasks are captured.** This may merge the raw extraction with a preliminary M7 FAIL (expected before the occurrence ledger is attached).

```bash
python -m royalty_research m8-ledger-prepare --root work/AGREEMENT_001
python -m royalty_research m8-ledger-next --root work/AGREEMENT_001
python -m royalty_research m8-ledger-next --root work/AGREEMENT_001 \
  --execute --confirm-subscription --confirm-credit-controls
```

The ledger runner executes at most one bounded task, with immutable response receipts. Again repeat only to advance captured tasks; a failed/limit task needs explicit operational recovery. Alternatively, an existing signed-in coding agent can produce a JSON response against the **exact** `ledger/tasks/ledger_NNNN.json`, and that response can be imported without another CLI model call:

```bash
python -m royalty_research m8-ledger-import --root work/AGREEMENT_001 \
  --response /path/to/exact_response.json
```

When saved JSON survives a crash but its receipt does not, use `m8-ledger-recover --root work/AGREEMENT_001 --chunk 1`. A failed model task can be explicitly released using `m8-ledger-retry ... --reason '...'`; a stopped limit requires `m8-ledger-clear-limit ... --reason '...'` after checking billing/account settings. These are retry safety controls, **not review approvals**.

**4. Finalize and export.** Every source-issued occurrence must have a valid disposition (or there must genuinely be zero occurrences) before export.

```bash
python -m royalty_research m8-status --root work/AGREEMENT_001
python -m royalty_research m8-finalize --root work/AGREEMENT_001
```

The local output contains `output/final_extraction.json`, `output/qc.json`, `output/output_manifest.json`, an audit-able `output/csv/` folder and `output/Royalty_Research_Historical_Staging.xlsx`. Export **includes QC failures**, with their error status in Excel. Existing output is immutable; a new attempt requires a separate versioned run directory. `--csv-only` is available if local XLSX dependency is missing.

## What M8 validates, and what it does not

It validates immutable plan hashes, complete source-passage assignment, saved model-task provenance, exact evidence references, model-output structure, occurrence ID coverage, contradictory/missing source economics detected by deterministic controls, cross-task paragraph risk warnings, final output file hashes and export reproducibility. It does **not** validate full-contract semantic recall, all amendments, scanned PDF completeness, real subscription throughput, actual token/credit use, or whether a model really read everything that was supplied. A second occurrence reader is **not** equivalent to an independent blind full-document extraction.

## Benchmarking

Use `benchmarks/DEVELOPMENT_25_PLAN.json` to select **25 distinct real agreements** and obtain independently checked reference observations based on complete original documents. This research benchmark is separate from user sign-off and does **not** add human approval to the extraction process. Create one file per reference based on `benchmarks/REFERENCE_TEMPLATE.json` and compare:

```bash
python -m royalty_research m8-benchmark \
  --reference gold_case.json \
  --extraction work/AGREEMENT_001/output/final_extraction.json \
  --out comparison_case.json
```

The comparator counts missing/extra distinct royalty terms and tiers using strict normalized field tuples; it **cannot adjudicate equivalent but differently worded contract bases**. Its ratios are field-agreement proxies against supplied reference labels, **not statistically estimated royalty recall or professional verification**. Do not create gold labels by copying model extractions. The 25-case development benchmark cannot substantiate population-wide 95% recall; later locked holdout testing is still necessary.
