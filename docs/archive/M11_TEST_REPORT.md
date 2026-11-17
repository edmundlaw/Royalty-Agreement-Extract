# M11 v0.11.0 — Engineering test report

## Source and independent findings

Basis: supplied `REVIEW_REPORT_M10_v0.10.0.md` and `Royalty_Research_Historical_Staging.xlsx`, plus the cumulative M10 project ZIP already available in this conversation. No M10 Fable proprietary local source maps for Equillium, KemPharm or Genprex were attached to this turn. The report provides their error counts and passage examples; it is **not** a substitute for source files for live replay.

Fable/Opus reviewed M10: 244 passing tests, but correct readings of Equillium, KemPharm and Genprex failed (8, 16, 9 errors); NeurogesX regressed; blanket issues excused missing redacted economics. These are confirmed **review findings**, not M11 results.

## M11 implementation changes

- New `m11_signal_qc.py`: source-issued flag manifest, table-block detection, typed source-evidenced closures, core-vs-supporting statuses, rejection of open issues as waivers, duplicate-source-obligation checks, one bounded correction packet, additive source-verified corrections.
- New opt-in `m11_pipeline.py`: full-source primary reading without M7 per-occurrence Sonnet ledger; immutable output and single correction attempt; no human approval.
- Existing CLI gains `--qc-profile m11`, `m11-finalize`, `m11-import-correction`, `m11-signals`, and `m11-check`. Legacy M10 path remains unchanged for comparative review.
- Excel export gains `Source Flags` and numeric/disclosure fields for Other Payments; QC shows typed source-flag outcomes. Existing staging rows remain present despite incomplete QC.
- Schema accepts optional payment disclosure status and source-bound M11 typed resolution fields.

## Test scope

Ran `PYTHONPATH=src python -m unittest discover -s tests -q` after changes. **269/269 offline tests passed** (244 inherited + 25 new tests). New cases cover: long tables without 7-passage windows; redacted rate/milestone rows; multiple sublicense shares; misleading sublicensee text; multiple source markers / one record reuse; direct and written rates; table-band amounts; audit and insurance thresholds; stacking/reduction floor; equity wording; minimum plus monthly instalments; independently reported payment warnings; correction output immutability; and a mock subscription CLI end-to-end workflow that excludes legacy occurrence-annotation calls.

The mock-CLI integration test is **not** live Sonnet/Codex inference or subscription-billing verification. No five-fresh-agreement blind holdout has been run. Original contract recall and false alarms are **unmeasured**. Accuracy/completeness claims must not be extrapolated from synthetic test pass counts.

## Outstanding risks / blockers

1. Source-signal detection remains heuristic; it cannot certify recall for clauses not flagged by Python, incomplete parsed tables, or payment obligations expressed unusually.
2. Semantic fields such as MARGINAL versus ALL_UNITS, tier calculation bases and cross-amendment current status need independent verification beyond occurrence matching.
3. Extra model use on huge documents is still unmeasured. Correction tasks larger than their configured context budget are marked `correction_ready=false`, not silently truncated or auto-approved.
4. Real Claude/Codex output, Mac Python dependencies, original SEC PDFs and scanned contracts, and source-file accessibility must be validated outside this environment.
5. M11 profile is opt-in; the legacy M8 profile still runs the previous M10 rules. The two profile outputs must not be confused.

## Release decision

**Development candidate for Fable independent review only.** Do not begin the SEC 2021–2025 bulk extraction. Freeze at least five new original agreements *before* examining their extraction outcomes; independently establish source obligations and test both correct-reading false rejections and corrupted-reading false passes.
