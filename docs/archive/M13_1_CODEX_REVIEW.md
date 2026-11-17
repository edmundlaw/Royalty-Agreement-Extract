# Independent Codex review assignment — M13 v0.13.1 research exporter

## Reviewer instruction

You are independent of the builder. Work in a *separate* review directory. Do not treat this changelog or the builder's 322 passed tests as a quality conclusion. Do not modify the sealed release before checking its hashes. You may copy it into an independent development workspace after verification. Do not use unstated prior extraction answers.

### 1. Reproduce the release

1. `python scripts/verify_release.py` must PASS with the correct v0.13.1 manifest.
2. `PYTHONPATH=src python -m royalty_research --version` must show 0.13.1 (if the CLI supports this flag). Run every `tests/test_*.py` module independently if discovery stalls; count exact tests, timeouts and errors. Never report a module not run as PASS.
3. Check `m13-finalize --help` and `m13-combine --help`: `--legacy-xlsx` must be present.
4. Confirm no paid API keys, network calls or additional reader calls are performed by the exporter. Leave M4 subscription/billing safeguards unchanged.

### 2. Verify workbook mapping and completeness

- Using included `examples/M13_Original_FunctionalBrands_16sheet.xlsx` and `examples/M13_Research_FunctionalBrands_5sheet.xlsx`, run `python scripts/verify_research_export_parity.py --original examples/M13_Original_FunctionalBrands_16sheet.xlsx --research examples/M13_Research_FunctionalBrands_5sheet.xlsx`.
- Independently inspect source row counts, observation IDs, six rates, 13 payments, 86 evidence, zero tiers, 10 conditions, 4 adjustments, seven reader differences (one CORE), 23 open issues. Verify no missing redactions, no numeric type conversion, no broken evidence IDs, no loss of quotes/SEC URLs. Check all five sheets and the optional detailed XLSX.
- Specifically confirm the original first-reader US$200,000 total-cash observation is not automatically netted, added to components, or modified to resolve the CORE disagreement.
- Check formula injection, hyperlink URL restrictions, Excel 32,767-character boundary, percent-points formatting (30 => displayed 30.0%, numeric 30), missing/null fields, no imputed IA type or rights, and duplicate source-document runs.
- Check generated sheet font names, orange rules `#FD5108`, black text, no full-sheet orange fills, frozen headers, filters, and row visibility in both Excel for Mac and programmatic inspection.

### 3. Verify schema, citations and existing M13 behavior

- Verify both schema copies are identical, new licensing fields are OPTIONAL and all legacy extraction examples still pass. Introduce falsified licensing fields, missing evidence IDs, unsupported schema enums, an unknown cited evidence ID, an unsupported sublicensing claim and a mixed-IP agreement.
- Compare single reader, added-check-later and two-reader statuses against v0.13.0; no change to original numerical reader comparison permitted. On multi-chunk M13, ensure optional fields survive merge, conflicting wording is not quietly overwritten and source evidence remains bound.
- Check that additional material terms do not suppress actual royalty/fee extraction and that classifications do not claim independent legal verification.
- Validate `m13-combine` on multiple distinct document IDs and large numeric/text sets. Verify `output_checked` is chosen when present, all original technical rows remain in JSON/CSV, and output hashes remain correct.

### 4. Independent judgment

Do **not** claim extraction accuracy based on exporter tests. The 25–50 unfamiliar SEC agreement pilot with independently established gold-standard obligations is still outstanding. If you run it, report separate recall/precision, material omissions, shared blind spots and costs; do not count this exporter patch as a benchmark.

### 5. Deliverable

Write `CODEX_INDEPENDENT_REVIEW.md` with a direct PASS/FAIL/CONDITIONAL verdict for *the exporter/schema patch only*, reproducible command transcript, file hashes, test counts, every material defect with exact file/function/line, and the resulting workbook sample(s). Keep a separate field for `Contract-level precision/recall: NOT MEASURED` unless independently measured. Never give a Claude/Codex pass based solely on the builder's own report.
