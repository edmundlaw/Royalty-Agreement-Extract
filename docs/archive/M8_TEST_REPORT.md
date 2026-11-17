# M8 v0.8.0 — Engineering / Integration Test Report

**Result:** **215/215 offline tests passed** from the M8 development workspace. Includes 188 retained M1–M7 regressions and **27 new M8 tests**. These tests are engineering verification and adversarial fixtures, **not measured extraction recall or legal/valuation accuracy**.

## What was actually executed

- Complete cumulative suite: `PYTHONPATH=src python -m unittest discover -s tests -q` → `Ran 215 tests ... OK`.
- Source syntax compilation: `python -m compileall -q src scripts tests` → success.
- Project package version: `python -m royalty_research --version` → `0.8.0`.
- Synthetic end-to-end demonstration: fake Codex CLI emits the prewritten artificial agreement extraction → M4 source-bound chunk capture → M8 full passage coverage → M7 occurrence task issuance → exact saved classification receipts → strict M7 validation → M3 workspace → Excel with **14 sheets**, including terms, tiers, QC and open issues. No genuine subscription inference occurs in the synthetic test.
- Synthetic open issue: the example is marked `PASS_DETERMINISTIC_ONLY` **with a HIGH unresolved issue**; Excel state is `QC_PASSED_OPEN_HIGH_ISSUE`, not a professional approval. The demonstration includes four royalty tier rows (2 sales, 2 sublicensing).
- Mocked negative agreement with **zero numeric economic occurrences**: the full first-reader task is still mandatory; the secondary ledger step is skipped; export succeeds without fabricating royalties.
- Deliberately wrong occurrence classifications: outputs are exported for research with `FAIL` QC; no silent exclusion.
- Ledger dry runs and source/response fingerprint integrity: tampering, wrong IDs, duplicate responses, stale receipts and missing tasks are rejected.
- Mocked CLI failures: one-task-only capture, explicit retry release and fail-closed limit stop, without contacting real subscription models.
- Long documents: all source passages assigned once; interrupted/incomplete first-reader tasks block subsequent stages; a normalized original source paragraph split across AI tasks generates an automatic HIGH open issue.
- Benchmark comparator: strict signed document/text identity, duplicate multi-set rates not collapsed, missing tiers/wrong bases flagged, numeric normalization; **only a field-agreement proxy against independently provided reference labels**, not statistical truth.
- Workbook inspected with `artifact_tool`: 14 named worksheets, distinct royalty/sublicensing terms and tier rows, source/QC/open-issue columns; no formula-error cell matches in the synthetic example. The final release workbook is a **fictional demonstration**, not an SEC historical result.

## Operational limitations left open

1. **Live inference:** M8 did not invoke a real Claude Code or Codex subscription; local executables in the tests are mocks. Fable's earlier limited real-agreement tests do not prove the new M8 integration is working on a Mac or with actual subscription usage limits.
2. **Recall:** no full-source human-independent historical gold-standard precision/recall measurement exists. Source-issued numeric occurrences can miss indirect narrative economics or semantic conditions.
3. **Cross-chunk meaning:** the raw chunk merger preserves disjoint source and evidence, but a rate/condition split across model calls can still be misinterpreted; M8 raises risk issues for known segmented paragraphs/cross-task references, not a full semantic resolution.
4. **Amendments and PDFs:** connected multi-document amendment chains, scanned exhibits and large source PDFs still need real-world testing.
5. **Efficiency:** the 16k-vs-64k prompt-size comparison remains based on **characters**, not measured subscription usage, latency or quality. The all-source first-reader plan is intentionally conservative; it is not yet demonstrated to be the lowest-usage approach.
6. **SEC discovery recall:** filing discovery/screening from M1–M7 is not yet independently validated for all historical contract vocabulary or all applicable filings.
7. **Billing:** local environment checks reject obvious API-key routes but **cannot guarantee** purchased credits are disabled. Account credit/auto-reload settings require separate owner verification before any real CLI `--execute`.
8. **Benchmark labels:** the supplied `benchmarks/DEVELOPMENT_25_PLAN.json` contains **25 unfilled slots**, not completed source-independent gold labels. The aggregate code intentionally does not certify measured accuracy.

**Recommended release classification:** ready for Fable's controlled live-Mac integration tests and the 25-agreement **development** benchmark. **Not ready for full SEC 2021–2025 extraction.**
