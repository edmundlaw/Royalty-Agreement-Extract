# Fable independent handoff — M6 v0.6.0 (development build)

**Goal:** challenge the new independent source-risk QC and fail-closed workspace gate. Do not rubber-stamp results or start a 2021–2025 bulk run.

## Suggested process

1. Extract M6 into a NEW folder; preserve your existing M5 reviewer workspace unchanged.
2. Verify `RELEASE_SHA256.json` using `python scripts/verify_release.py`.
3. Use Homebrew Python 3.12 in a virtual environment; run `python -m pip install -e '.[xlsx,pdf]'` and `python -m unittest discover -s tests -q`. Expected: **164 tests**.
4. Read `docs/M6_CORRECTIVE_RELEASE.md` and `docs/M6_TEST_REPORT.md`.
5. Independently recreate Fable's real Market Finders and UC/NeurogesX tests. Focus on whether the new source-ledger fails correctly on genuine omissions without falsely flagging interest, audit thresholds, or repeated mentions.
6. Attempt to defeat the new rules with a valid but materially incomplete extraction. In particular try: missing rows of table-based minimums, a reference to a side letter, a spelled-out rate, a marginal-vs-all-units reversal, and a royalty hidden in an unflagged section.
7. Test the human-review acceptance/rejection sequence and accidental deletion of selected pointers/registered source folders. Do not edit an existing workspace in place to make the tests pass.
8. Compare the same economic extraction by Sonnet and Codex and distinguish numeric/field differences from differences in writing style. Identify any material mismatch that the normalized comparator misses.
9. Issue a **new** severity-ranked defect register with exact reproduction and fixes. Report source-risk false positives separately from false negatives.

## Model usage

Deterministic offline tests need no LLM. Delegate bounded inspection to Sonnet where helpful; reserve higher reasoning for source-contract interpretation, adversarial review, and decisions about material omissions. Keep subscription costs low; do not use paid model APIs or auto-credit replenishment.

## Critical unsolved areas

Do NOT conclude that M6 is ready for bulk extraction. Fable's D-03/D-04/D-05/D-08/D-09/D-14/D-15 remain substantially open. The next build should prioritize a source-issued, model-facing occurrence schema and efficient relevance/reading pipeline before live benchmark expansion.

The embedded Market Finders sample is a public SEC-source-derived regression fixture supplied in the uploaded Fable review package; it is **not** a gold label and cannot support claims about real-world recall.
