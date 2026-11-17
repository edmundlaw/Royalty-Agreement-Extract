# Fable / Sonnet — M8 independent handoff

You are reviewing GPT-6's **M8 v0.8.0** local subscription-based research workflow. Original M1–M7 source and tests are retained. **Do not treat the passing offline tests as evidence of contract-extraction accuracy.** No API calls, no hosted service and no human-approval/signoff steps are authorized.

## Priority review sequence

1. Fresh install; verify release SHA manifest, Python package version 0.8.0, all M1–M8 tests, and the M8 synthetic demonstration workbook. Use Python/shell, not a reasoning model, for mechanical tasks.
2. Inspect `m8_pipeline.py`, `m8_benchmark.py` and the M4/M7 interfaces. Confirm full-source passage coverage and that **every passage** in the M1 map is assigned to exactly one first-reader task. Check tamper/replay detection, immutable model-output receipts, crashes and output-resume safety.
3. Review the new M8 occurrence CLI runner. Confirm it uses the *actual* signed-in local subscription and does not switch to chargeable API inference. Inspect purchased credits / auto-reload separately; the CLI cannot prove account-level billing limits.
4. Verify the independent `--ledger-engine claude --ledger-model sonnet` path works when primary is Codex; test with one real agreement before spending on a large set. Delegate routine bounded module reviews, fixture checks and syntax issues to Sonnet. Use high reasoning for semantic royalty omission, amendments, and critical systemic defects.
5. Use actual SEC originals for Market Finders, UC/NeurogesX and **independent new agreements**. Specifically attack the four-tier and 25/10/5 sublicense schedule omissions; wrong bases/thresholds; conditional reductions; redactions; quoted rates with different economic roles; huge tables; cross-section definitions; and rates embedded outside Python-selected passages.
6. Validate the zero-occurrence negative-document case and a large multi-chunk source. A source map's full supplied text is not proof the model read every word. Verify preservation and report unresolved cross-task dependencies.
7. Compare *measured* subscription usage and error rates of 16k vs 64k reading packets with Sonnet/other available subscription models. M8 stores prompt-character estimates, not measured usage savings. Do not choose a setting solely on character count.
8. Prepare a **25-agreement development benchmark** using `benchmarks/DEVELOPMENT_25_PLAN.json`. Independently derive reference labels from full contracts. Model-provided reference data must be labeled as such; it is not truth. Log term-level and agreement-level omission patterns. Keep a later locked holdout test separate.
9. Check that the workbook has **no human approval fields** and that failed QC/open issues remain visible rather than disappearing. The user will not report any outside human review back to the software.

## Stop conditions

Do not authorize a five-year SEC bulk extraction until live CLI billing/usage and independent real-contract completeness measurements support it. Report genuine defects with source passage IDs, command/output hashes, reproduction steps and severity. Preserve M8 unchanged; deliver any corrections in a separately versioned release. Do not automatically rerun expensive model calls after ambiguous interruptions or limits.

**Open limitations to challenge:** cross-chunk semantics, indirect royalty obligations with no recognizable numerical expressions, false negatives in SEC discovery, amendment chains, scanned PDFs, relevance triage recall, the distinction between a bookkeeping second read and a truly independent full-source omission reader, and per-call subscription consumption.
