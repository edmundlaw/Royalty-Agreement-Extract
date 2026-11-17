## v0.13.2 — payment summaries and exclusivity scope (2026-11-16)

- Replaced combined `Min. / cap / advance` main-sheet hint with four independently source-classified columns: Minimum guarantee, Royalty cap, Advance / prepayment, Upfront fee. Added Payment source IDs.
- New optional evidence-bound `agreement.exclusivity_scope` field, displayed beside Exclusivity. Legacy means `NOT_ASSESSED`.
- No change to M13 numerical two-reader comparison or paid CLI runner. See M13_2_PAYMENT_COLUMNS.md and M13_2_TEST_REPORT.md.

## v0.13.1 — M13 research workbook presentation patch (2026-11-16)

- Default M13 XLSX changed to a five-sheet PwC-style research workbook; original 16-sheet format is optional with `--legacy-xlsx`.
- Extraction schema extended with OPTIONAL licensed IP nature, source-evidenced sublicensing rights, IA details and other material licensing terms; old saved results remain valid and render `NOT_ASSESSED` for missing data.
- Source-check enforces evidence IDs for populated new fields, not their economic interpretation. Independent-reader comparison remains numerically focused and does not independently validate new licensing fields.
- Preserved original `rows.json`, CSV, source checks, results and model billing safeguards. New sample and parity checks added.
- Offline: 19 test modules / 322 tests passed individually; mapping-parity check on original FunctionalBrands sample passed. No new live AI calls, blind SEC benchmark, or Codex independent PASS claimed.

## M13 v0.13.0 (2026-11-16) — built in review

- New module `m13_two_reader.py` and commands `m13-prepare`, `m13-add-check`, `m13-next`, `m13-status`, `m13-finalize`, `m13-combine`.
- Source check for one reading: exact quotes, numbers in quotes, evidence on every record, flagged passages accounted for, whole document read. No keyword judgement about what a clause means.
- Optional independent second reader; comparison aligned on cited passage and number; differences graded CORE, STRUCTURE or NOTE. The second reader can be added after a single-reader export.
- Workbook: sheets Reader Check and Reader Differences; Licensor and Licensee on term, tier and payment rows; one combined workbook for many runs.
- Validator profile `M13_TWO_READER` routes `validate_extraction` to the source check. M6 to M12 code paths unchanged.
- 28 new offline tests (315 in total). See `docs/M13_TEST_REPORT.md` for live results and limits.

## M9 v0.9.0 (2026-11-14)

- M9 independent source-context table and explicit royalty-cap gates; UC/NeurogesX 25/10/5 omissions detected even when the M7 ledger is corrupted together with the extraction.
- Corrected descriptive/non-running-payment false-positive QC failures; original live saved Market Finders, NeurogesX and Immersion results replay without deterministic errors (warnings/open issues retained).
- Subscription-only CLI preflight, allowlisted subprocess environment, model-output limit handling and fenced JSON recovery; no APIs invoked.
- 233 offline tests before final package verification. No human approval.
- See M9_TEST_REPORT.md for outstanding risks and evidence.

## v0.5.0 — M5 validation harness and fail-closed uncertainty

- Added pre-registered local source-anchor probe runner and CLI command, with source hashes and per-anchor passage IDs.
- Added 14 source-grounded but **paraphrased** anchor patterns from Market Finders / Daugherty, UC / NeurogesX, and qualitative indirect-payment terms; 3 small fixtures, **not originals**.
- Added 22 adversarial offline tests, including missing anchors, malformed HTML, tier-table row continuity, uncertainty-gate bypasses and CLI idempotency.
- Expanded screening vocabulary and references to Annex, Attachment, Addendum, remuneration and remittance language.
- Fixed potential silent HTML truncation: unclosed ignored HTML content now raises ParseError instead of losing subsequent clauses silently.
- Fixed a material QC bypass: UNKNOWN percentages and UNCERTAIN candidate passages now require an unresolved HIGH/CRITICAL issue tied to the passage; without it deterministic QC FAILS.
- Added explicit M3 validator-revision binding: old QC is preserved but must be revalidated in a new workspace instead of being grandfathered as a PASS.
- No API/hosted features or claims of SEC-live/LLM-live validation added.

# Change log

## v0.2.0 — M2 (2026-11-13)

- Preserves all M1 discovery, parsing, mapping and regression code.
- Adds bounded selected/full document reading packets, explicit unflagged sample, schema-bound AI extraction contract, evidence linking and exact-quote checks.
- Adds passage-level and individual percentage-occurrence disposition ledgers, rate/tier/threshold checks, conditional terms, redaction safety and amendment-check status.
- Adds source-only blind re-key packet and independent extraction discrepancy reporting.
- Adds synthetic multi-rate test output, prompt templates, and comprehensive offline failure tests.
- Does not invoke models or call paid LLM APIs; no accuracy claims or historical batch extraction.

## v0.1.0 — M1

See original M1 documentation and test log included in this package.

## v0.4.0 — M4 Mac operational readiness

- M1 exact source-preserving segmentation for oversized normalized lines, original-paragraph SHA and adjacency tracking. Forced mid-token splits block automated QC pass.
- New `m4-plan`, `m4-status`, `m4-run-next` (dry-run by default), `m4-authorize-retry`, `m4-clear-limit`, `m4-recover-result`, `m4-merge-plan` commands.
- Immutable packet/prompt/task/run records, subscription-account confirmation flags, one-call caps, no inference API, no automatic retry, quota stopping, crash-state recovery, deep read-time source binding.
- M4 operational instructions and Fable independent review matrix. No live model or SEC integration claims.

## v0.7.0 — M7 source-issued occurrence ledger, relevance triage and approval-free Excel (2026-11-14)

- Removed active human-approval command, sign-off gates and `Human Reviewed` worksheet; all selected records export with automated QC/exception flags.
- Added deterministic M7 source occurrence manifest and source-bound IDs, including numbers, money, selected rates written in words and indirect payment references; strict classification reconciliation without trusting a model-authored occurrence inventory.
- Added M7 high-risk challenges to detect omitted rates, ungrounded source-to-term links, and disallowed dismissals of risk-bearing written rates and indirect payment provisions.
- Added bounded Sonnet ledger follow-up tasks with exact task/source/extraction fingerprints and safe merge/attach; unresolved source occurrences automatically produce machine-only open QC issues, never a human approval request.
- Added transparent relevance priority scores with no automatic document exclusion, and full source coverage when focus and remainder packs are combined.
- Added 14-sheet Excel research demonstration, full cumulative regression suite and offline triage on previously saved SEC maps. No real model/token savings, production recall, live SEC integration or subscription costs claimed.


## M8 v0.8.0 (2026-11-14)
Integrated full-source first-reader/occurrence-ledger/Excel coordinator, separate low-cost ledger-model selection, immutable task responses, retry safeguards, cross-chunk issue detection, zero-occurrence case handling, 25-case benchmark scaffold, strict source-bound comparator, no human approval workflow. 215 cumulative offline tests passed. No live M8 subscription inference or accuracy certification.
