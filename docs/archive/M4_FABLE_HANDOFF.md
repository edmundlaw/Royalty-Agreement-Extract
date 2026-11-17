# Fable independent review & live pilot — M4 v0.4.0

## Exact scope to review

This is a standalone, local Python codebase plus fictional regression tests. It is **not** a finished 2021–2025 historical royalty dataset. Core release files: `mapping.py`, `m2_packets.py`, `m2_validation.py`, `m3_chunks.py`, `m3_workspace.py`, `m3_export.py`, `m4_operator.py`, `cli.py`, `tests/test_m4.py`.

A Fable review is valuable precisely because GPT-6 wrote and tested this implementation. **Do not accept its test claims without replaying tests, checking source text and challenging assumptions.** Prior fictional 8-case samples are not gold truth.

## Priority review tasks

1. **Source preservation:** Create SEC-like HTML, TXT and PDFs with huge text runs, cross-boundary rates, broken tables, redactions, multi-page sections and defined terms. Confirm exact reconstitution of each split original normalized line. Recheck document-level PDF/HTML extraction losses; no OCR fallback currently.
2. **SEC live discovery:** Verify actual full-text request format, pagination caps, SEC document metadata/exhibit type, retrieval error semantics and URL link fidelity. Compare a sample day of SEC full-text search against an independently retrieved filing/exhibit inventory. Report missed items and false positives; do not extrapolate a five-year number from January alone.
3. **Model CLI with subscription:** Verify authenticated account provenance, payment settings, Claude `-p` JSON envelope, Codex `exec -o`, tool sandbox/permission flags, model names and actual rate limits. Start with one **fictional**, then one public real contract. No claim of zero billing is possible from environment variables alone.
4. **Failure injection:** Kill a fake CLI mid-run; try corrupted map, prompt, receipt, chunk ID, source text, forged run ID, missing receipt, quota messages, duplicate attempts. Confirm no automatic re-runs or false approval.
5. **Economic semantics:** Human-verify at least Western Digital (interest vs royalty), Market Finders (four tiers), UC/NeurogesX (sublicensing 25/10/5), redacted RemeGen/Vor, and a conditional step-down. Inspect the full original exhibit and schedules, not just the detected passages.
6. **Independent omission checks:** Build a separate blind full-document review and manually examine *unflagged* sections. Reconcile all findings with M2 passage/percentage ledgers. Test recall from ground truth, not from model-model agreement.
7. **Excel and Mac runtime:** Install/test project with current Python and any required spreadsheet dependency. Generate CSV + XLSX from M3, inspect 15 worksheet schemas, verify reference links, sheet values, numeric helpers, no unapproved records in `Human Reviewed`. Record dependencies that prevent operation.
8. **User workload:** Measure agreements/day on actual available subscriptions, interruptions/retry costs, and accuracy by contract type. Implement daily/session caps **only after** measurement; the current runner processes one call at a time.

## Non-negotiable acceptance gates before large-scale research

- No unexplained source-text truncation, source-map mismatch or unreported parse failure.
- SEC search discovery independently cross-checked; retained recall uncertainty documented.
- Stage gates distinguish `CAPTURED_NOT_QC_APPROVED`, `PASS_DETERMINISTIC_ONLY`, independent model review, and true human review.
- 25-case development set thoroughly human-grounded, followed by **separate locked holdout** (e.g. 60 stratified cases); characterize stratum uncertainty and report agreement-level complete-capture proportion. No population-wide 95% confidence claims from unweighted, purposively stratified samples.
- At least 3 supervised CLI calls per engine with deliberate failure/restart/limit injection and observed no **unintended charges**; billing assumptions never inferred solely from absent env vars.
- Source evidence can be re-opened from exact SEC accession/exhibit URL, and revisions/amendments are not silently represented as current operative economics.
- External Fable verdict: pass/fail by gate, minimal reproducible bug reports, exact commands/model versions, no speculative conclusions.

## Report format to return to GPT-6

For each issue: severity, source/fixture path, command, expected vs actual, source evidence, whether it affects completeness/accuracy, minimal proposed fix. Include tested CLI versions, account mode (without credentials), usage consumed, benchmark annotations, and SEC search response counts with date boundaries.

**Important:** Do not use a lightweight AI model's agreement with the extraction as the sole acceptance measure. It does not constitute independent human-reviewed ground truth.
