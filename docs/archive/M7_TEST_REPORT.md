# M7 offline test report — v0.7.0

**Status:** Engineering development release; **not** production-validated historical extraction.

Baseline: M6 v0.6.0 cumulative ZIP, which incorporated Fable's v0.5.1-review fixes. No M7 paid model API calls, real subscription inference or live SEC requests were made. Unit and integration tests are offline.

- M6 baseline: 164 tests in the earlier release.
- M7: the old human-approval tests were replaced with approval-free output/workflow tests; additional source-issued occurrence and CLI replay adversarial tests were added. Final M7 suite: 188 tests passing, including newly added adversarial tests for written-out rates, indirect payments, source passage mismatch and machine-generated unresolved issues. See the separately supplied test log for the command output.
- Source maps: 80 SEC exhibit maps previously fetched by Fable were read offline. See `M7_SAVED_SEC_MAP_TRIAGE.json` for all input file checksums, priorities and focus fractions. This analysis is **not** a relevance-accuracy or royalty-recall study.
- Relevance triage: 19 `HIGH_VALUE_FULL_EXTRACTION`, 20 `MEDIUM_VERIFY_IP_SCOPE`, 41 `LOW_SIGNAL_REQUIRES_TRIAGE_OR_SAMPLING` (80 total). No documents auto-excluded.
- Focused source-character fraction on those 80: mean 20.3%, median 16.6%, source-character-weighted 22.3%. The remainder pack includes all excluded text; no long-term omission is implied.
- Fable's real Market Finders M1 map: Python source inventory includes 6%, 4%, 2%, and 1% independently of AI-generated dispositions. M7 positive synthetic example retains distinct tier and sublicense rows, with no human approval sheet.
- M4 prompt-character illustration on Market Finders using the same source and full M2 schema: `make-packets --max-chars 16000 --mode full` generated four prompts totaling 113,619 characters; `--max-chars 64000 --mode full` generated one prompt totaling 60,138 characters, after compact source JSON formatting. These are **prompt characters**, not API tokens or observed subscription usage. A live test must check quality and capacity for larger single-call extraction.

**Known unresolved:** automated occurrence coverage can still miss semantically indirect obligations outside known source expressions; no measured full-document recall, no human truth benchmark, no verified subscription consumption or Mac integration for M7; scanned PDF and amendments untested; compact focused packets are not currently an automatic replacement for all-candidate M4 extraction.

- A ledger classified `UNRESOLVED` creates a source-bound machine-generated `HIGH` open issue during attachment; this prevents requiring any manual approval or a costly full re-extraction merely to record uncertainty. Automated QC reports still flag that issue.
- The tests exercise source-issued occurrence IDs, not full legal-semantic interpretation. A contract with two identical percentages attached to different obligations remains a known limitation.
