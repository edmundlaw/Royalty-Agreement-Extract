# M5 v0.5.0 — Reproducible engineering test report

## Status

- **138/138 local offline unit/integration tests passed** using `PYTHONPATH=src python -m unittest discover -s tests -q`.
- **22 M5-specific tests passed**, including adversarial paths. Earlier M1–M4 tests (116) passed unchanged.
- **3 pre-registered synthetic paraphrase fixtures, 14 source-informed anchors**: all were present and detected as candidates; `output/m5/anchor_probe_report.json` contains exact source and text hashes, match passage IDs, and explicit non-validations.
- No actual Codex or Claude Code subscription model was invoked. No SEC originals were fetched through the software from this environment. No historical royalty Excel dataset was generated.
- This report is **not an empirical finding of 95%+ accuracy, document discovery recall, royalty-term recall, or audit verification**.

## Source grounding for the factual scenario patterns

1. Market Finders Brokerage / Daugherty, SEC Exhibit 10.2: https://www.sec.gov/Archives/edgar/data/1520358/000149315213000675/ex10-2.htm
   - Royalty tiers 6%, 4%, 2%, 1%, tier thresholds 0.5m / 2.5m / 20m; minimum royalty schedule, support-related annual cap; interest and audit percentages are not running royalty rates.
2. University of California / NeurogesX, SEC Exhibit 10.6: https://www.sec.gov/Archives/edgar/data/1385830/000119312507022650/dex106.htm
   - Running 1% net-sales royalty; sublicense fee schedule 25% / 10% / 5% and thresholds; annual revenue-related cap; separate third-party stacking, non-royalty shareholding percentage.

The fixture language is paraphrased, simplified and selected. **These are not complete SEC files** and cannot validate whether M1 successfully parses the full original exhibits, whether the tier calculations are interpreted correctly, or whether M2 finds every rate.

## Test categories

| Control | Result | What it does *not* establish |
|---|---|---|
| Existing M1–M4 integration, retry and source integrity tests | 116 pass | Live browser/SEC and model CLI compatibility |
| SEC-informed rate/tier/interest/equity clause screening | Pass | Contractual semantic precision or recall |
| HTML table percent-to-threshold row preservation | Pass on synthetic table | General SEC HTML table preservation |
| Qualitative Annex / Attachment / Addendum references | Pass | Every nonstandard economic phrase can be found |
| Script/style unclosed-content parse failure | Pass | All malformed documents cause visible failures |
| UNKNOWN and UNCERTAIN without HIGH/CRITICAL issue | Deterministic QC FAIL | Model cannot misclassify a rate as UNRELATED |
| UNKNOWN linked to unresolved HIGH issue | Reported blocking warning | Human resolution or professional sign-off |
| Missing required anchors | Fails rather than skipping | Unregistered anchor completeness |
| Old workspace validator revision | Explicit rejection; original QC remains immutable | Automated migration to new QC rules |
| CLI existing report safety | Rejects unwarranted overwrite | No post-publication file tampering |

## Reproduction

```bash
python -m pip install -e .
python -m unittest discover -s tests -q
royalty-research m5-probe-manifest \
  --fixtures tests/fixtures/m5 \
  --manifest tests/fixtures/m5/anchor_manifest.json \
  --out /tmp/royalty-anchor-probe.json
```

The command must return `ALL_ANCHORS_PASS_NOT_RECALL_VALIDATED`. Inspect per-anchor `passage_ids`. The quality claim is **limited to these particular registered anchor patterns**.

## Independent acceptance requirements

Before bulk extraction: obtain complete original SEC exhibits locally; compare SEC discovery against a distinct filing/exhibit inventory; inspect HTML tables and appendices; use subscription-authenticated model runs and verify account billing settings; independently annotate at least 25 development cases and a locked additional holdout sample; report agreement-level complete-capture rate and precision with appropriate uncertainty; assess model throughput, limits and session recovery. Errors require correction and fresh acceptance samples where pipeline changes invalidate the previous estimate.
