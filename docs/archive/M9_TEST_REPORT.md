# M9 v0.9.0 — QC semantics, source-context omissions and subscription CLI hardening

**Date:** 2026-11-14  
**Baseline:** User-supplied `Royalty_Research_M8_v0.8.1-review.zip` inside `royalty-research(1).zip`.  
**Scope:** Correct Fable's critical QC false failures, the missed UC/NeurogesX sublicense schedule, and CLI authentication/environment/limit handling. **No human approval or sign-off.**

## Evidence and results

- Cumulative regression suite: **233 tests passed** (subject to clean-ZIP rerun). M9 tests use mocked authentication/CLI binaries; no model inference was performed here.
- Revalidated Fable's three saved **real Sonnet extraction files** against their corresponding original saved M1 maps (not paraphrased fixtures):

| Saved extraction | Prior M8 QC errors | M9 deterministic QC errors | M9 warnings | Unresolved HIGH/CRITICAL issues |
|---|---:|---:|---:|---:|
| Market Finders | 38 | **0** | 13 | 0 |
| UC / NeurogesX | 38 | **0** | 18 | 12 |
| Immersion / Meta | 4 | **0** | 4 | 1 |

**Warning:** PASS_DETERMINISTIC_ONLY does not mean contract accuracy, precision or recall is established. The high-open-issue counts above remain visible in the workbook's QC/Open Issues records. Do not represent them as cleared. The existing `QC_PASSED_OPEN_HIGH_ISSUE` state remains material.

## M9 source-context tests

Previously missed UC/NeurogesX sublicense rates appear on three separately parsed table rows: `25% | < $250,000`, `10% | $250,000 -- $2,000,000`, and `5% | > $2,000,000`. The table heading and sublicense-fee obligation occur before those rows. The new **independent** M9 gate reads these source passages and tests each tier against the extracted, evidence-linked term. It does not trust the model-created classification or the M7 occurrence ledger as proof that a row is irrelevant.

The replay also tests an explicit annual-dollar royalty cap and percentage-based royalty/payment bounds. Deliberately corrupting the saved NeurogesX extraction triggers:

| Corruption | M9 source gate result |
|---|---|
| Entire sublicense term removed | Detected: `M9_TIER_TABLE_ROW_MISSING` |
| One sublicense tier removed | Detected: `M9_TIER_TABLE_ROW_MISSING` |
| Tier rate swapped relative to source row | Detected: `M9_TIER_RATE_ROW_MISMATCH` |
| Sublicense tiers relabeled as product sales | Detected: `M9_SUBLICENSE_TIER_MISCLASSIFIED` |
| Dollar and percentage royalty limits removed | Detected: `M9_ROYALTY_CAP_UNACCOUNTED` and `M9_PERCENT_ROYALTY_CAP_UNACCOUNTED` |

These are **source-grounded targeted regression tests, not measured full-contract recall**. Unseen contract table formats, unconventional royalty formulas, scattered schedules and amendments can still be missed.

## False-positive QC corrections

- Recognize quoted non-running interest/other payment descriptions such as `.5 %` and `40% of total sales price`, without treating them as numeric running-royalty rates.
- Accept thresholds that cite the original tier row and recorded bound, even when the model writes currency signs or commas.
- Permit source-anchored milestone-payment formulas and genuine contractual conditions rather than forcing all percentages into a running-royalty classification.
- Recognize non-royalty audit examination and late-payment-interest contexts. Accounted non-running economic payments remain in the data.
- Descriptive agreement title/industry/status without evidence are **explicitly warned as unverified**; licensor/licensee and quantified royalty claims still require source support.
- Preserve source passages labeled background/redacted, while independent source-risk checks continue to require economic redactions to be represented or flagged.

## Subscription CLI hardening

- Guard against provider-shaped API/billing override variables, not just the original 11-name denylist.
- Pass an explicit limited environment, retaining HOME for OAuth sign-in but dropping unrelated secrets and provider overrides.
- Before **real** model execution, require `claude auth status --json` to explicitly report `claude.ai` or `codex login status` to explicitly report ChatGPT sign-in. Mock-model testing uses a clearly designated test-only path.
- Disable Claude Code customizations with `--safe-mode`, `--strict-mcp-config` and no tools; use Codex read-only sandbox and `--ignore-user-config` where supported. CLI compatibility must be checked on the Mac.
- Treat usage-limit text in a successful **contract answer** as data. Stop on limit signals from a provider error envelope or a failed CLI invocation.
- Recover JSON from fenced or prose-wrapped saved responses locally, followed by normal strict schema/source validation. No repeat model call is required for this normalization.

**Not guaranteed:** account-level extra-usage/auto-reload settings, purchased-credit consumption, provider-managed settings, and future CLI authentication/flag behavior. User must verify account controls externally; no paid API calls occurred in this development session.

## Remaining material work

1. Test against at least five **previously unseen full real agreements**, including sublicense schedules with different table/paragraph structures. Do not tune against those holdouts and call it a recall estimate.
2. Measure precision and agreement-level recall on the separate 25-agreement development benchmark and independent acceptance set. These tests alone prove neither.
3. Reduce heavy subscription consumption (saved live trials used approximately 81k and 145k tokens) and add safe bounded batch scheduling. Current runner still uses explicit one-call execution.
4. Add a bounded AI correction task to resolve real remaining QC defects without rerunning entire contracts; avoid automatically accepting repaired content.
5. Test PDFs, redacted terms, multi-amendment reconciliation and actual usage-limit interruptions.
6. Mac-side verification of subscription-auth preflight and CLI flags; verify extra credits and auto-reload are off. A missing API key is not proof that purchased credits cannot be consumed.
7. More broadly evaluate semantic issues: marginal vs all-units tiers, cap applicability, royalty-base interpretation, and disclosure sufficiency.

**Release classification:** Development/independent-benchmark candidate only. Not approved for five-year bulk processing. No human approval workflow is present or required.
