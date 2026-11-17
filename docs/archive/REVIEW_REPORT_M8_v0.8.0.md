# Independent re-test — Royalty Research M8 v0.8.0

Reviewer: Claude (Fable 5.2) as lead; one Sonnet subagent for the runner/export re-verification; Sonnet as the extraction model in every live call. Date: 2026-11-14. Same Mac and workspace as the M5 review (`~/royalty-research/`).

| Path | Content |
|---|---|
| `release_m8_original/` | Supplied ZIP extracted, read-only. ZIP SHA-256 `e546dca97fcbbb6bf18816c8b43e0d9765de665b3a49908940d433c5d2db4147`; 110 of 110 files match the manifest |
| `review_m8/` | Working copy under git; baseline = as supplied; branch `review-fixes` = v0.8.1-review |
| `m8test/` | Maps of the 80 saved exhibits made with M8, triage results, and the three live runs (`work/MarketFinders`, `work/NeurogesX`, `work/Immersion`) with prompts, raw responses, receipts, QC and workbooks |
| `tools/adversarial_validator_m8.py` | Corruption test against the M8 gates |

## Verdict

**M8 is a real improvement but is not ready to be finalised.** Sonnet's reading was correct on all three agreements tested. The controls around it are still not dependable: the automated QC marked all three correct results FAIL, and the omission gate missed a deliberately removed sublicensing schedule on an agreement it was not tuned on.

| Build | Classification |
|---|---|
| v0.8.0 as supplied | Not ready: an agreement that needs more than one reading task cannot be merged |
| v0.8.1-review | Ready for the development benchmark only |

## What was fixed since v0.5.0 (verified here)

| Earlier defect | M8 status | Evidence |
|---|---|---|
| D-01 parser fragments clauses and tables | Fixed | 80 of 80 exhibits: identical text, 58,728 → 33,960 passages |
| D-06 Excel needs an unavailable library | Fixed | 215 of 215 tests pass on this Mac; workbooks produced |
| D-07 prompt omits required key | Fixed | Three live first-reader calls captured first time |
| D-02 corrupted extractions pass | Much improved on Market Finders, not general | 10 of 11 corruptions caught there (3 of 11 before); 4 of 8 on NeurogesX |
| D-04 no relevance triage | Partly fixed | 80 exhibits: 21 high, 18 medium, 41 low (77 high before) |
| D-05 prompt overhead | Improved | Market Finders: 1 task of 60,000 characters (7 tasks of 244,000 before) |
| D-09 unusual phrasings undetected | Improved | 19 of 24 detected (9 of 24 before) |
| D-10 two-reader comparison | Fixed | Reworded conditions and null vs "0" no longer reported as a mismatch |
| D-13 silent loss of workspace records | Fixed | Deleting a pointer or record folder now raises an error |
| D-16 unquoted phrase queries | Fixed | Carried over from the review build |
| Human approval | Removed | No command, sheet or column; `record_human_review` raises `HUMAN_APPROVAL_DISABLED`. Remnants: `HUMAN_CONFIRMED` linkage status, `HUMAN_MANUAL` read scope, legacy `agreement.schema.json` fields |

## Live tests with Sonnet (subscription sign-in, no API key)

| Agreement | Calls | Tokens (in + out) | Time | Substance | Automated QC |
|---|---|---|---|---|---|
| Market Finders / Daugherty | 1 reader + 2 ledger | about 49,000 + 32,000 | 3.1 min | Correct: 4 tiers with thresholds, 5 minimums, $200,000 cap | FAIL, 38 errors |
| UC / NeurogesX | 2 reader + 3 ledger | about 94,000 + 51,000 | 4.8 min | Correct: 1% royalty; 25 / 10 / 5 sublicensing schedule separate; caps, milestones, minimum | FAIL, 38 errors (after the merge fix) |
| Immersion / Meta, patent licence and settlement, filed 2024 (not seen before) | 1 reader + 1 ledger | about 21,000 + 11,000 for the reader | 1.5 min | Correct: no running royalty invented; one lump-sum payment with the amount redacted; noted that the agreement says the payment is not a reasonable royalty | FAIL, 4 errors |

No usage limit was reached. Account-level credit settings remain unverified from this Mac.

## Defects found in M8

| ID | Sev | Defect and evidence | Status |
|---|---|---|---|
| M8-01 | Critical | **Merge refuses multi-task agreements.** NeurogesX: both reader tasks captured, then `m8-ledger-prepare` failed with "Conflicting agreement header across chunks: licensor" because one task wrote "NeuroGesX, Inc." and the other "NeurogesX, Inc." (`m3_chunks.py:99`). The captured work is stranded | Confirmed live. **Fixed RF-07**: first value kept, difference recorded as an open issue |
| M8-02 | Critical | **QC fails correct extractions (3 of 3).** With human approval removed, QC status is the only quality signal in the workbook, and it does not separate good from bad. Causes: (a) number formats `50,000.00` and `$500,000` rejected (Market Finders: 16 of 38 errors); (b) the occurrence check demands a royalty-term link for a CONDITION while the ledger prompt allows a payment link (7 errors); (c) risk heuristics flag the audit clause "five percent" and the clause "does not represent a reasonable royalty"; (d) agreement title and similar fields need evidence links; (e) interest listed as a payment with a non-numeric amount. There is still no correction call | Confirmed live. Part fixed **RF-08** (Market Finders 38 → 22). Rest open |
| M8-03 | Critical | **Omission gate is tuned to Market Finders.** On NeurogesX, removing the whole 25 / 10 / 5 sublicensing schedule from the extraction and the ledger added no error. Also not caught there: both caps removed, sublicensing rates swapped, sublicensing share relabelled as a sales royalty. The table rows (`25% | < $250,000`) carry no royalty vocabulary themselves, so they are classed `INVENTORY_ONLY` | Confirmed (`m8test`, script in the review log). Open |
| M8-04 | High | Billing guard unchanged: deny-list of 11 variables (four others reached a fake CLI), no sign-in status check, no isolation from user settings, hooks, MCP servers or CLAUDE.md, for either runner | Confirmed (agent). Open |
| M8-05 | High | Usage-limit pattern still matched against the model's answer: a valid result containing "rate limit reached" was discarded and the plan blocked. Fenced or prose-wrapped JSON still cannot be recovered without a new model call | Confirmed (agent). Open |
| M8-06 | High | Throughput: 45,000 to 145,000 tokens and 2 to 5 manual commands per agreement; no batch mode, queue or daily cap. Triage still rates credit agreements of 490,000 to 630,000 characters and several employment agreements as high value | Measured. Open |
| M8-07 | Medium | Blocking status still comes from the model's own open-issue list; deterministic checks only set QC FAIL | Suspected (agent, code reading). Open |
| M8-08 | Medium | Workbook: `Lower_Numeric` / `Upper_Numeric` blank when the model wrote `$500,000` (fixed by RF-08); Other Payments has no numeric amount column; term and tier rows carry no licensor or licensee; a redacted payment amount shows as a blank cell with no redaction status; `Rate_Numeric` blank for tiered terms | Confirmed. Part fixed RF-08 |
| M8-09 | Medium | Noise: NeurogesX received 24 open issues, 7 of them automatic HIGH "cross-reference across AI tasks" | Confirmed live. Open |
| M8-10 | Medium | Triage rated two short redacted amendments to licence or collaboration agreements as low priority; amendments can change royalty terms | Observed on 2 of 41 low-priority exhibits. Open |
| M8-11 | Low | Definitions are still sent as term names without their text | Confirmed (agent). Open |
| M8-12 | Low | Still undetected: "one-twentieth", in-kind royalty, an amount in words only, an obligation in a schedule heading, most-favoured terms | Confirmed. Open |

## Corruption tests (deterministic)

Market Finders, extraction and ledger corrupted together: fourth tier dropped (two ways), whole royalty removed, minimums and cap removed, rates swapped, base changed, threshold scale, family relabelled, invented rate, wrong band: **all caught**. Marginal changed to all-units: not caught (not decidable by rule).

NeurogesX: 1% royalty removed, milestones removed, minimum removed, conditions and adjustments removed: caught. Sublicensing schedule removed, caps removed, sublicensing rates swapped, sublicensing relabelled: **not caught**.

## Changes in v0.8.1-review

| Fix | File | Change |
|---|---|---|
| RF-07 | `m3_chunks.py`, `tests/test_m3.py` | A differently worded agreement header in a later task is kept visible as a MEDIUM open issue instead of stopping the merge |
| RF-08 | `m2_validation.py`, `m3_export.py`, `m7_occurrences.py` | `$500,000` and `50,000.00` are accepted as numbers in validation, export and the occurrence threshold check |

215 tests pass after the changes (one test rewritten to the new merge behaviour).

## Required before finalising

1. Make QC meaningful: align the occurrence rules with the ledger prompt, stop the audit-clause and "not a reasonable royalty" false alarms, relax evidence links for descriptive header fields, and add a correction call that sends only the errors (M8-02).
2. Generalise the omission gate: a table row inherits the vocabulary of its lead-in sentence and heading, and the gate is tested on at least five agreements it was not developed on (M8-03).
3. Isolate and guard the runner; read limit messages only from error output; recover fenced JSON from the saved response (M8-04, M8-05).
4. Add a batch runner with a daily cap, and tighten triage for long non-licence contracts and for amendments (M8-06, M8-10).
5. Record a redaction status on payments and add numeric amount and party columns (M8-08).
6. Then the 25-agreement development benchmark.

## Not tested

RemeGen through a model, PDF or scanned exhibits, amendment chains, a live usage limit, Codex as first reader, 16,000 versus 64,000 character packets, and any measured precision or recall.
