# Fable independent review and Mac integration plan — M3 v0.3.0

## Objective

Independently challenge whether this local codebase correctly implements the M1–M3 research workflow. It is not production validated and there are no recorded live subscription-model completions.

## Do not accept the author's test count as an accuracy claim

- Re-run `PYTHONPATH=src python3 -m unittest discover -s tests -q` on Mac.
- Verify Python 3.10+ can run the no-extra-dependency JSON/CSV commands.
- Verify whether `artifact_tool` is available or installable on the user Mac before relying on direct XLSX export; do not assume this server environment reflects the Mac.
- Run an **unmodified** real SEC contract through M1 `map`, M2 `make-packets`, then subscription-authenticated Claude/Codex analysis, `validate-extraction`, M3 `ingest`, and CSV/XLSX staging export. Authenticate with subscription and check no API usage/extra credits.
- Independently compare all rates/bases/thresholds/sublicensing/definitions/cross-references against the original agreement, not merely M2 AI or Python's candidate list.
- Test a 25-case development benchmark and a separately locked acceptance set; quantify agreement-level omissions and false positives.
- Test true SEC filing inventory discovery with original exhibit links and SEC fair-use rate limits; do not extrapolate document count from one keyword/month without uncertainty.

## Adversarial tests to add

1. Documents with numerically unflagged economics and nonpercentage per-unit rates.
2. Long PDF tables, OCR-required or unreadable pages. Fail closed, never quietly exclude.
3. One source passage longer than M2's chunk bound. Explicit exception is the current behavior.
4. Tier boundary ambiguities (marginal vs retroactive), product-specific rates, sublicensing base changes.
5. An amendment that changes only one term; no automatic global replacement.
6. Filing duplicate by another reporting party; exact hashes or shared party names must not imply same agreement without evidence.
7. A packet with altered text and recomputed packet SHA; the merger must reject it.
8. An AI reader that lists passage IDs it never actually viewed; an ID ledger alone does not prevent the behavioral failure.
9. A first reader newly selected after second-read approval; the old AI comparison must NOT transfer.
10. Two interrupted processing sessions, a failure to write one chunk, and an agent restart; no lost record, silent overwrites or falsely completed batch.
11. Excel formula-injection payloads disguised as SEC contract titles, source URLs or excerpt text.
12. Check that workbook rates and thresholds are **numeric where safe**, percentages remain explicitly in percentage points, and workbook hyperlinks actually open legitimate SEC sources.

## Review deliverables requested from Fable

- A severity-ranked defect report with exact reproduction commands, offending source lines and expected vs actual behavior.
- Mac environment/bootstrap dependency report, including XLSX generation feasibility and CLI subscription billing safety checks.
- Independent 10–20 contract real SEC smoke test summary; enumerate *every* missed economics term, not just aggregate pass rate.
- Recommended minimal changes, regression tests, and a go/no-go decision for scaling historical extraction.

Do not modify the original M3 ZIP. Work in a clone. Compare release hashes and preserve issues found before fixes.
