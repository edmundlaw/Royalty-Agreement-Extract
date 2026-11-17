# M13 v0.13.1 — builder's offline regression report (NOT independent Codex acceptance)

Date: 2026-11-16. Scope: adding the five-sheet export, optional licensing-fields schema and source evidence ID checks. The M13 numerical two-reader comparison and account safeguards are unchanged.

## Execution

- The all-in-one `unittest discover` run stalled and did not finish within the execution budget. This is **not counted as a PASS**.
- Every test module was then invoked in an isolated Python subprocess. **19/19 modules passed; 322/322 tests passed**, of which **6 were new research-export/source-evidence tests**. The previous M13 report listed 316 tests.
- The two original `test_m13.py` pipeline assertions were updated for the new five-sheet default, and now independently check that the old 16-sheet layout is still produced with `legacy_xlsx=True`.
- Both `m13-finalize --help` and `m13-combine --help` display `--legacy-xlsx`; `python -m royalty_research --version` prints `0.13.1`.

## Real saved-case mapping check

Ran `scripts/verify_research_export_parity.py` against the original M13 FunctionalBrands 16-sheet workbook and the new five-sheet workbook. Status `PASS_MAPPING_ONLY`, 0 reported errors.

| Source record | Original M13 16-sheet | New five-sheet |
|---|---:|---:|
| Royalty term observations | 6 | 6 |
| Other payment records | 13 | 13 |
| Exact source evidence records | 86 | 86 |
| Rate tiers | 0 | 0 |
| Conditions | 10 | 10 |
| Adjustments | 4 | 4 |
| Reader differences | 7 (1 CORE) | 7 (1 CORE) |
| Open issues | 23 | 23 |

Original observation ID, rate numeric, rate base, family, product scope, evidence ID and document QC columns were compared, plus payment amounts, source quotations, SHA-256 fields, source URLs and typed-issue counts. The US$200,000 total-cash disagreement remains unresolved, as it should.

## Critical negative tests

A synthetic licensing header with a declared IA nature but no source evidence ID produces `M13_AGREEMENT_FIELD_WITHOUT_EVIDENCE`. A nonexistent source evidence ID produces `M13_EVIDENCE_MISSING`. Old M13 extractions lacking the new optional fields continue to pass the same M13 source checks. Rates and payments remain numeric; new Excel presentation retains numeric percentage-point values.

## Limits

This is the developer's test, not an independent Codex review. It does not measure SEC agreement precision/recall, prove semantic accuracy of licensed IP classification, test 25–50 blind agreements, or demonstrate account-level credit/billing behavior on the user's Mac. New licensing metadata is still not compared by the independent reader for semantic agreement. Acceptance for historical-scale use is **NOT GRANTED**.
