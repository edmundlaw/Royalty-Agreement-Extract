# M6 v0.6.0 — reproducible test report

## Test environment

Python 3.13.5, Linux sandbox. Baseline code was Fable's reviewed `v0.5.1-review` sourced from the user-provided `royalty-research.zip`; no network, local Claude/Codex login or paid AI inference was used.

Command:

```sh
PYTHONPATH=src python -m unittest discover -s tests -q
```

## Test suite result

- Original reviewer baseline: **146 passed** (confirmed from extracted project before changes).
- M6 cumulative tests: **164 passed**, including 18 new adversarial/source-integrity regressions.
- The v0.6.0 release is an engineering/test candidate, not independently assessed contract-recall performance.

## Real-source-informed checks

Tests include Fable's normalized full Market Finders source map and previously captured Sonnet extraction. The original result continues to pass *deterministic-only* checks. The following deliberate manipulations are detected:

- Dropping fourth rate (1%) and recategorizing the source as unrelated.
- Deleting the entire running royalty while keeping the source map.
- Deleting minimum royalties and the annual cap.
- Swapping 6% and 4% tier positions in a single passage.
- Changing the stated royalty basis from Net Sales to Gross Sales.
- Changing a product-sales royalty to sublicensing receipts.
- Independent-reader paraphrases of the same Net Sales definition do not generate a false economic-rate disagreement.
- Non-royalty audit thresholds such as Market Finders' 5% audit shortfall and the NeurogesX-style 5% examination discrepancy are not incorrectly treated as rates by the new source-risk layer.

Workspace tests additionally demonstrate: later human rejection removes prior approved status, registered document-folder deletion raises an exception, missing/swapped selected pointer raises an exception, missing review order journal fails closed, and missing expected-document register fails closed.

## Residual failures not solved

Fable's real UC/NeurogesX model output still reports **18 pre-existing deterministic bookkeeping/schema errors** when evaluated under M6 (not caused by the new source-ledger risk checker). It has **no new source-risk errors**. These legacy failures need a reworked model-facing occurrence contract and patch-based correction workflow, not manual relabeling.

The validation logic still cannot prove legal meanings such as marginal vs all-units, completeness of unflagged document sections, final current-contract amendments, or absence of other missed terms.

No 25-agreement human-verified benchmark or locked independent acceptance set has been run. No statistical precision/recall can be reported.

## Release boundary

A v0.5.1 workspace cannot be silently reused under v0.6.0. It lacks the new expected-document register and has QC reports issued under a different validator revision. The M6 runner intentionally refuses silent upgrades. Create a new workspace and import validated source/extraction objects with a recorded process.
