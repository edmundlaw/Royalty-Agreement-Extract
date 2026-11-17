# Fable / Sonnet review handoff — M7 v0.7.0

Review **independently**, not as a rubber-stamp of prior GPT-6 unit tests.

- Start with `docs/M7_DESIGN_AND_OPERATIONS.md`, `docs/M7_TEST_REPORT.md` and source modules `m7_occurrences.py`, `m7_triage.py`, `m7_ledger_tasks.py`.
- Reproduce `PYTHONPATH=src python -m unittest discover -s tests -q` in a clean Python environment (Python >=3.10). Ignore M1–M6 historical log statements as evidence that M7 has been live-tested.
- Attack the occurrence ledger using **real SEC exhibits**, including rates that occur twice within one clause, written-out rates, indirect payment schedules, and unresolved items whose machine-generated QC issue must survive Excel export. A source-issued ID is a location, not automatic semantic proof.
- Test relevance screening *independently of its own lexical triggers* on the 80 saved maps and additional contracts. Estimate **missed relevant documents** via full-source random sampling; do not use the priority categories as automatic exclusions.
- Run the 25-agreement development benchmark using Sonnet for easy extraction/classification tasks. Reserve high reasoning for ambiguous tiers, exceptions, cross-reference chains, omission analysis and the final independent review. Prefer deterministic Python for file/hash/data checks.
- Measure actual context usage and performance of one-call 64k packets versus the previous 16k packet strategy. A larger packet may be cheaper but could reduce quality; test before enabling as a universal default.
- Verify that no human approval/sign-off is required anywhere. All records, including QC failures and unresolved issues, should remain in the final Excel; no `Human Reviewed` worksheet exists.
- Do not start the 2021–2025 bulk historical extraction until the independent acceptance benchmark and live subscription tests have demonstrated acceptable omission rates and bounded usage.
- Do not use paid inference APIs. Check all account-level extra-credit/auto-reload settings yourself before enabling any live CLI model call.

Deliver reproducible findings, evidence, small bounded fixes, and a separate versioned package. No human-review submission or approval recording is needed.
