# M10 development test report — 2026-11-14

## Source and scope

Baseline: user-uploaded `royalty-research(2).zip`, containing Fable's unchanged
M9 review code and saved SEC agreement test runs. M9 baseline: 233 offline tests.
Changes made only in a separate working copy. No Claude/Codex model inference,
no SEC network requests, no Excel historical database generation in this run.

## Engineering changes

- New source-first `m10_obligation_gate.py` wired into M2 QC. It checks table
  rows regardless of column order, spelled percentages, redacted tiers, and
  explicit payable royalties independently of AI labels.
- Special payments: upfront/guaranteed minimums and their amounts, pass-through
  royalty/minimum/milestone obligations, and rate-change adjustments must have
  actual source-cited economic records.
- Narrowed over-broad M7 nonroyalty exceptions (no equity/ownership blanket
  waiver). A general open issue no longer excuses a NON_ROYALTY dismissal.
- Corrected bookkeeping for undetermined pass-through royalty rates,
  references to existing royalty obligations, and documented installment amounts.
- Redaction markers retained automatically, but source-level redacted tiers
  still require individual cited tier records. Existing results are immutable.

## Offline evidence

`tests/test_m10.py` contains general synthetic adversarial tests for band-first
rates, redaction tiers, fee-first sublicensing, minimums, step-ups, upfront
fees, equity wording, audit/interest exclusions, pass-through obligations and
source-bound deterministic marker preservation.

Saved Fable M9 data replay (no new AI calls):

| Case | Result under revised validator |
|---|---|
| Qualigen/Pan-RAS original | 0 QC errors on its actual M8 source map |
| Beyond/Kirkland's original | 0 QC errors on its actual M8 source map |
| Qualigen upfront removed | Detected |
| Qualigen pass-through royalty/minimum removed | Detected |
| Kirkland's 5% step-up tier removed | Detected |
| Kirkland's two minimums removed | Detected |
| Kirkland's rate family changed | Detected |
| AUM 6%/8%/10% band-first table, empty extraction | 3 rate rows detected, absent records flagged |
| Stanford/Combangio Kala, empty extraction | Six redacted earned-royalty rows plus three sublicensing rows detected, absent records flagged |
| Kala source occurrence workload | 248 occurrences, 241 redaction markers; estimated occurrence classification tasks reduced to 2 |

These are known, developer-visible files, so no independent statistical recall
or generalization claim is justified. Other familiar/available evidence maps
were also inspected for plausible table rows and false positives.

## Unresolved limits

- No five-agreement blinded holdout has been run.
- Full-document recall and contractual semantic accuracy remain unmeasured.
- No real subscription usage savings, live PDF/OCR, amendment chain, credit
  settings or real usage-limit interruption tested here.
- No automated batch mode or targeted model correction call.
- Source-heuristic coverage is inherently incomplete, and some financial tables
  may be misclassified. QC PASS means source-led deterministic checks passed,
  not that the contract is commercially verified or fit for audit use.
