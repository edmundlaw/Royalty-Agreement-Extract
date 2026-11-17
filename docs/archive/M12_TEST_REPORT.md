# M12 engineering validation — v0.12.0

## Status

**Development candidate, NOT an independent Claude PASS and NOT approved for historical bulk extraction.** M12's deterministic checks are tested offline; actual contract-level recall is not established.

## Results

- **287 module-scoped unittest executions passed**, covering every `tests/test_*.py` module independently. Running the entire suite in one process did not complete within the execution time limit; the tests were therefore run by module, with every module reporting exit code 0. The independently run M12-specific modules account for 18 tests.
- Four saved real Sonnet extraction/source-map pairs (Market Finders, NeurogesX, Kirkland's, Qualigen) pass M12 deterministic validation without changing their extracted economic facts. **These are development examples and not unseen acceptance cases.**
- Ten saved-case mutation scenarios require missing records (tier, running rate, minimum, cap, sublicense and upfront fee); altered extractions no longer reconcile as clean.
- Constructed probes cover redacted economic signals, linked source records, caps stated as limits, per-unit currency rates, upfront and approval-triggered fees, written + numeric percentage deduplication, mixed payment/audit passages, twelve-row redacted tables and separate-cell tables.
- A fake local CLI completes full-source reading, source-flag issuance, QC report and Excel export, without cloud model calls. The exported workbook includes Source Flags and QC sheets and no human-approval gate.
- An open-source-flag correction task can be created after the original reading. Correction responses are source-bound, append-only, and cannot overwrite the original extraction attempt.

## Residual limitations — release blockers for production

1. Source detection can miss unforeseen language, unusual tables, and poorly parsed or referenced financial arrangements. `PASS_SOURCE_FLAGS_ONLY` is **not** full-contract recall.
2. No genuinely unseen, independently reviewed group of five real agreements has passed an acceptance test with Claude. No measured extraction precision, recall, or model usage savings.
3. No completed live test of PDF/scans, amendment chains, usage-limit interruption or Codex primary reading for M12.
4. Some unflagged financial-looking passages remain on saved SEC maps; the exported QC includes their count, not a fictional verified-complete assertion.
5. The CLI retains legacy mode for backwards compatibility. **Specify `--qc-profile m12`** to use the redesigned source-flag engine.
6. No account-level credit and auto-reload guarantees are possible from this container.

## Minimum acceptance gate on user's Mac

Select and freeze at least five previously unseen complete SEC agreements *before* their terms/answers are revealed to the developer. Use subscription-authenticated Sonnet to read all source sections. Independently verify the full set of source obligations. Require zero false QC failures on complete readings and detected omissions for all injected running royalties, tiers, sublicensing, redacted rates, minimums and caps, with warnings for missing supporting payments. Any failure warrants a reproducible defect report and revision, not a claimed Claude PASS.
