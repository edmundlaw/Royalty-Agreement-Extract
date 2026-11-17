# M13 — source check and optional second reader

M13 v0.13.1 preserves the two-reader process and adds a five-sheet research output. M13 replaces the keyword-rule QC of M6 to M12 for new work. Those modules are still in the package for comparison and are not used by the M13 commands.

## What it does

| Step | What is checked | Certain? |
|---|---|---|
| Source check (always) | Every quotation is part of the cited passage. Every recorded rate, threshold and amount appears in its quotation. Every record has evidence. Every flagged passage was cited or given a disposition. The whole document was read. | Yes. No judgement about meaning |
| Second reader (optional) | A second model reads the same document without seeing the first reading. Python lines the two readings up by passage and number and lists every difference. | Lowers the chance of an omission. Not proof |

The workbook rows always come from the first reader. The second reader only produces the comparison.

## Result shown in the workbook

| State | Meaning | What to do |
|---|---|---|
| `TWO_READERS_AGREE` | Both readings hold the same rates, tiers, thresholds, minimums and caps from the same clauses | Nothing beyond the normal check at the point of use |
| `TWO_READERS_AGREE_ON_NUMBERS` | Same numbers from the same clauses, arranged differently (for example a tier versus a condition, or a separate record for a pass-through clause) | Read the STRUCTURE rows in sheet Reader Differences |
| `TWO_READERS_DIFFER` | A rate, tier, threshold, minimum, cap or sublicensing share is held by one reader only, or the readers contradict each other | Open the clauses in the CORE rows and decide |
| `SINGLE_READER_NOT_CHECKED` | One reading. Quotes and numbers checked; completeness not checked | Add a second reader, or check the source yourself |
| `SOURCE_CHECK_FAILED` | A quote or number is not in the cited text, or a record has no evidence | Do not use. Re-run in a new folder |
| `SECOND_READER_FAILED_SOURCE_CHECK` | The second reading failed its own source check | Treat as a single reading |

Difference levels in sheet Reader Differences:

- **CORE**: a rate, tier, threshold, minimum or cap recorded by one reader only; a rate recorded as sales by one reader and sublicensing by the other; marginal versus all-units; licensor and licensee swapped; a redacted rate held by one reader only.
- **STRUCTURE**: both readers used the clause and the number, but filed it differently.
- **NOTE**: upfront fees, milestones, other payments and side conditions held by one reader only; the same value cited from two different clauses; party names worded differently.

Interest, late-payment and audit charges are left out of the comparison.

## Commands (one agreement per run folder)

```bash
# 1. Prepare. No model call. Leave out the two --check options for a single reading.
python -m royalty_research m13-prepare --map agreement_map.json --root runs/AGREEMENT_001 \
  --engine claude --model sonnet --check-engine codex --check-model gpt-6-sol

# 2. Read. Dry run first; then one model call per command, or --all for every call of this agreement.
python -m royalty_research m13-next --root runs/AGREEMENT_001
python -m royalty_research m13-next --root runs/AGREEMENT_001 --execute --confirm-subscription --confirm-credit-controls --all
python -m royalty_research m13-status --root runs/AGREEMENT_001

# 3. Check, compare and export. No model call.
python -m royalty_research m13-finalize --root runs/AGREEMENT_001

# Optional: add the second reader later, to an agreement already exported with one reading.
python -m royalty_research m13-add-check --root runs/AGREEMENT_001 --engine codex --model gpt-6-sol
python -m royalty_research m13-next --root runs/AGREEMENT_001 --execute --confirm-subscription --confirm-credit-controls --all
python -m royalty_research m13-finalize --root runs/AGREEMENT_001      # writes output_checked/, keeps output/

# One workbook for every finished run folder under runs/.
python -m royalty_research m13-combine --runs runs --out Royalty_Research_All.xlsx
```

`--all` runs the remaining calls of that one agreement and stops at the first task that is not captured. It never retries a failed task and never moves on to another agreement. A failed or limit-stopped task is released with the existing `m4-authorize-retry` or `m4-clear-limit` commands on `runs/AGREEMENT_001/reader_a` or `reader_b`.

The billing safeguards are those of the M4 runner, unchanged: the subscription sign-in is checked before every real call, only a short allow-list of environment variables reaches the CLI, any provider API-key variable stops the run, and a usage-limit signal stops further calls. Account-level extra-usage and auto-reload settings cannot be checked from the tool.

## Run folder

```
runs/AGREEMENT_001/
  m13_run.json, m13_run.sha256    run record (tamper-evident)
  source/                         map and reading packet
  reader_a/                       first reader: prompts, raw responses, receipts, merged reading
  reader_b/                       second reader, when used
  output/                         final_extraction.json, source_check.json, reader_check.json, rows.json, csv/, Royalty_Research_M13.xlsx
  output_checked/                 the same, written when a second reader was added after a single-reader export
```

Nothing is overwritten. A new attempt needs a new run folder.

## Workbook

The **default XLSX** now has five PwC-style sheets: `01 Royalty Database`, `02 Tiers & Mechanics`, `03 Other Payments`, `04 Source Evidence`, `05 QC & Issues`. All original legacy records are also retained in `rows.json` and individual CSV files. Use `--legacy-xlsx` on `m13-finalize` or `m13-combine` to additionally export the original 16-sheet `*_Detailed.xlsx` for reviewers. M13's `QC_State` and original reader comparison are preserved; the output styling does not change the accuracy of the extraction.

## Measured on 2026-11-15/16 (this Mac, subscription sign-in, no API key)

Source check on nine saved Sonnet readings that earlier reviews judged correct (Market Finders, NeurogesX, Immersion, Qualigen, Kirkland's, Equillium, KemPharm, Genprex, Pieris): 0 errors on all nine. On the same readings, every one of 288 deliberately changed rates, thresholds, amounts and quotes was caught.

Codex (`gpt-6-sol`, ChatGPT sign-in) read eight of those agreements through `m13-next`; all eight Codex readings passed the source check. Sonnet versus Codex:

| Agreement | State | Numbers both recorded | Core | Structure | Note |
|---|---|---|---|---|---|
| Market Finders | TWO_READERS_AGREE | 16 | 0 | 0 | 1 |
| Kirkland's | TWO_READERS_AGREE | 7 | 0 | 0 | 0 |
| Pieris | TWO_READERS_AGREE | 11 | 0 | 0 | 0 |
| Equillium | TWO_READERS_AGREE | 10 | 0 | 0 | 1 |
| KemPharm | TWO_READERS_AGREE | 26 | 0 | 0 | 0 |
| NeurogesX | TWO_READERS_AGREE_ON_NUMBERS | 20 | 0 | 2 | 1 |
| Qualigen | TWO_READERS_AGREE_ON_NUMBERS | 6 | 0 | 1 | 0 |
| Genprex | TWO_READERS_AGREE_ON_NUMBERS | 19 | 0 | 1 | 3 |

Omission test on the eight pairs: each core record (royalty term, tier, minimum, cap) was deleted from one reader together with its evidence, and that reading was compared with the other model's untouched reading. 124 deletions: 110 raised a CORE difference, 11 a STRUCTURE difference (the clause was still held in another record of the same reader) and 3 nothing (the deleted record duplicated a number the same reader held elsewhere).

**How to read these figures.** Six comparison rules were adjusted after looking at these eight pairs (amounts written in words beside a redacted figure, quotes that differ only in letter case, bounds written as "250000 exclusive", formula rates such as "2 x the rate", when a record without a number counts as a filing difference, and the order in which such records are paired). The eight pairs are therefore development cases, not an independent test. See `M13_TEST_REPORT.md` for the fresh end-to-end runs.

## Limits

- Two readers can miss the same term. Agreement is evidence, not proof. The rate at which both miss the same term is not yet measured.
- The comparison works on numbers and cited passages. It does not compare the wording of the royalty base, the territory or the term.
- A reader that marks a clause as a royalty term but makes no record of it produces a STRUCTURE row, not a CORE row, when the other reader has a record without a number for that clause.
- Long agreements are read in several tasks; a term whose parts fall in different tasks can be recorded twice or split. Both readers use the same task boundaries.
- PDF and scanned exhibits, amendment chains and a live usage limit were not tested with M13.
- No precision or recall figure exists. The 25-agreement development benchmark is still to be run.
