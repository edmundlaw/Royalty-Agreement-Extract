# M12 independent validation request

This is a **development candidate**. Do not approve it on the strength of the 287 passed module-level tests.

1. Keep v0.12.0 package and manifest immutable; create a separate review workspace.
2. Run `python scripts/verify_release.py` and `PYTHONPATH=src python -m unittest discover -s tests -q` (or isolated module tests if your environment stalls). Verify `--version` is 0.12.0.
3. Use `m8-prepare --qc-profile m12` for the revised pipeline. The old ledger and M10 keyword gates must not decide the M12 source-flag result.
4. Reproduce saved real cases; then choose **five new SEC agreements**, freeze the complete source and independently determined obligations before testing AI outputs. Do not recycle the four development cases.
5. Deliberately remove rates, tiers, all redacted sublicensing shares, caps, minimum guarantees, upfront fees and milestones. Require missing core economics to block and supporting economics to be visibly incomplete.
6. Specifically challenge band-first tables, separate-cell tables, schedules, definitions, compound spelled percentages, nonpercentage per-unit fees, unrelated audit/insurance/equity percentages, amendments, and cross-references.
7. Check source-issued flags can only close using correctly cited records or typed checkable explanations. Generic HIGH issues must never close a flag. Require each redacted economic obligation to have a null-valued record.
8. Test one targeted correction call, append-only history, restart, usage limits and subscription billing on your actual Mac. Do not enable purchased credits or API keys.
9. Independently examine the workbook's QC status, source flags, other payments and unresolved issues. There is no human approval or approval queue.

Report a direct PASS or FAIL with contract IDs, exact source passages, false-alarm counts, missed-omission examples, command transcripts, and real inference usage. **Only a fresh independent Claude review can issue a Claude PASS.**
