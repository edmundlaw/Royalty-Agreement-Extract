# M6 v0.6.0 — corrective integrity release

**Classification: Development benchmark candidate only. Do not run bulk SEC extraction.**

This builds on Fable's `v0.5.1-review` (RF-01 through RF-06) rather than replacing those improvements. Fable's complete `REVIEW_REPORT_M5_v0.5.0.md` and `REVIEW_CHANGES_v0.5.1.md` are retained for historical context. The M5 original release is not silently changed.

## What the new code changes

1. **Source-led independent risk inventory:** `m6_source_risk.py` scans EVERY original numbered source passage, not just Python candidates and not just AI classifications. It issues stable occurrence IDs, offsets and source-linked risk labels for literal percentage, currency and redaction occurrences. This is a *conservative error detector*, not an economic classifier.
2. **Rate omissions:** Potential royalty percentages adjacent to net-sales, royalty or sublicensing signals require a matching source-passage-linked royalty rate/tier/adjustment. A model can no longer quietly remove the Market Finders fourth tier and call its source percentage `UNRELATED` or `THRESHOLD` without a new deterministic source-risk failure.
3. **Payment omissions:** A minimum-royalty table's numeric rows inherit the mapped section heading. Minimum/guarantee and capped amounts require linked payment or condition evidence. In the Market Finders full-source map, deleting the five annual minimum payments and $200,000 cap now produces a source-risk error.
4. **Conservative economic contradictions:** Limited checks flag source rate order inconsistent with all tier rates in a single paragraph, explicit gross-vs-net sales-base contradictions, and an unmistakable product-sales-to-sublicensing-family misclassification. They **do not** prove true marginal-vs-all-units mechanics, thresholds' legal meaning, commercial status or broader comparability.
5. **Second-reader comparison:** Field-level numeric/family/base/tier/payment differences replace free-text equality; a different paraphrase of Net Sales does not automatically create a rate mismatch. Context differences still trigger review when they may hide an omission. No comparison result is treated as human verification.
6. **Human-review order:** Human reviews are journaled in insertion order. A later `REVIEWED_EXCEPTION` rejects a previously accepted extraction; earlier approval does not survive that decision. The curated workbook excludes it.
7. **No silent workspace loss:** An expected-document register records all registered source IDs, their map fingerprints, and selection events. Deleting a document folder, selected pointer, review order journal or register produces a hard error rather than an apparently smaller successful export.
8. **Version boundary:** The validator revision is now `m6.0-independent-source-obligation-gate`. Previously sealed M5 QC reports are not reused as M6 passes. Use a **new** workspace; there is no automatic in-place migration.

## Provenance of regression tests

- Includes the **full normalized Market Finders source map and Fable's Sonnet extraction** provided in the user's `royalty-research.zip`, under `tests/fixtures/m6/`. They are public SEC-source-derived review data, not human-validated truth labels and not a permanent SEC HTML/PDF archival system.
- Tests demonstrate that the original extraction passes the new independent source risk check while deliberate omissions (fourth tier, entire running royalty, minimums and cap), swapped rates, wrong basis/family, later human rejection and deleted records are flagged.
- Separate audit-shortfall regressions guard against treating 5% accounting inspection thresholds as royalty rates.
- **No paid AI API calls or subscription inference was performed here.** No new live SEC fetches were made in M6.

## Important remaining defects (NOT resolved by M6)

| Fable ID | Status | Why it remains important |
|---|---|---|
| D-02/D-03 | **Partial** | Source occurrence IDs exist but are not yet mandatory model-facing identifiers in the M2 schema. The model ledger is still self-authored, and correct full-document extractions can fail bookkeeping rules. Not all semantic corruptions can be caught deterministically. |
| D-04 | **Open — Critical** | No effective licensing/IP relevance triage. Most SEC hits are still routed as high-priority, including non-IP natural-resource royalty contracts. |
| D-05 | **Open — Critical** | Repeated schema/prompt envelopes, large outputs, no cost-capped automatic batch queue and suboptimal context usage. |
| D-08/D-09 | **Open — High** | Chunk boundaries and cross-references can split economics; unusual word-only payments, basis points and nonstandard redactions are underdetected. |
| D-14/D-15 | **Open — High** | CLI environment isolation, account-level credit safety and tolerant recovery from non-JSON wrappers need further work and live validation. |
| D-17–D-20 | **Open / partial** | Percent literal normalization, tier-level disclosure status, workbook ergonomics, and robust amendment/duplicate resolution. |

### Remaining *semantic* failure modes

- A model that interprets marginal tiers as all-units may produce correct source quotes and percentages. Python cannot prove the economic interpretation.
- A rate expressed as `twenty-five basis points` or a licence obligation located only in a side letter can still be missed by the M1 candidate detector.
- A correctly captured rate may be conditional, superseded, or require a defined base elsewhere.
- Source risk heuristics can produce false positives in complex clauses. Do **not** blindly relabel them as unrelated; review the actual source context and document the resolution.

## Validation scope and upgrade safety

Run `python -m unittest discover -s tests -q` in a clean environment and compare with the bundled test report. The previous 146 tests plus M6 adversarial cases must pass. Do not interpret a passing test count as a precision, recall or production assurance figure.

To use M6, create a new workspace; preserve previous M5 workspaces exactly as delivered. No in-place registry retrofit or silent QC upgrade is provided. Re-ingest source maps and corrected extraction objects under the new validator revision. Fable should specifically retest Market Finders, UC/NeurogesX, a redacted agreement, and previously unseen contracts before a larger pilot.

## Next engineering priority

**M7: subscription-efficient, omission-resistant document triage and model-facing occurrence IDs**, then section-aware reading, a minimal patch-based correction path, and isolated CLI subscription execution. These are prerequisites to a realistic 25-agreement benchmark at scale.
