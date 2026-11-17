# v0.13.6 changes

- New `royalty.sh START END [MAX] [--go]`: one-command discover, prepare, read, finalize, combine and copy to Downloads. Dry run by default; fixed queries, model and budgets.
- Optional `agreement.related_party` (YES / NO_STATED_ARMS_LENGTH / NOT_STATED) with evidence; new `Related party` column. Old readings show NOT_ASSESSED, or `YES (keyword hint: ...)` when a Python scan of cited evidence or source text finds related-party / affiliated-entity wording.
- New Python-only columns `Usable for royalty benchmark` and `Benchmark note`. NO when: SUBLICENSING_RECEIPTS family (the only pass-through family in the schema), rate 50% or more, rate undisclosed/redacted/ambiguous/non-numeric, rate not a percentage, related party YES, or contract status reads as a term sheet / conditional (simple wording match). No AI tokens.
- IA nature: FIRST_READER rule 10 now requires the best-supported category plus optional `licensed_ip_nature_basis` (STATED / INFERRED). Source check accepts INFERRED when it cites evidence. Export shows `PATENT (inferred)`. Labelled Python fallback `(keyword hint)` for old/UNDETERMINED readings; never overrides a reader's own value.
- Sheet 01 `Other material terms` is a short summary; new sheet `06 Other Terms` has one row per term. `Agreement status` and `Exclusivity scope` capped at 150 characters with full text in end columns. Parity script updated for six sheets.
- New columns `Signing date` (execution date) and `SEC filing date` (filing metadata). `Effective date` kept.
- Candidate selection (found in a live dry run: the old rule read candidates in hash order, let a low-signal Citigroup pricing supplement use up the limit, and would have sent a 287k-character asset purchase agreement to the reader): candidates are ordered EX-10 first; a zero-token licence check (`licence_gate`) rejects documents that mention royalties only in boilerplate; licences over 120,000 characters are deferred unless `--big`; the limit counts prepared agreements, with a cap of 10 downloads per agreement. Dry run on 12-14 Jan 2026 (3 agreements) found the VXM01 term sheet automatically and rejected 12 purchase/loan/security agreements.
- `scripts/verify_release.py` and `RELEASE_SHA256.json` were not regenerated for 0.13.6.

# v0.13.5 changes

- Restored the v0.13.3 **complete source** M13 reading path as the routine production workflow; v0.13.4 lean excerpts remain labelled preliminary screening only.
- Added `m13_prod.py`: one-process batch preparation, one-time SEC fetch/map per unique candidate, bounded CLI execution, manual model-neutral answer import, resumability through existing immutable M13 plans, finalization and combination.
- Added explicit reader effort settings, task-boundary call/prompt/available-usage budgets, and per-call usage fields when emitted by the CLI. No paid API or nested AI controller.
- Manual imported reader answers use a new backward-compatible `manual` schema engine value in both schema copies; existing Claude/Codex outputs remain valid.
- Strengthened lean excerpt validation against numeric substrings, unsupported basis and suspiciously empty output. This does not make lean mode complete.
- Preserved the five-sheet exporter and added main-sheet `Royalty rate as reported` and `Agreement status` columns; renamed QC title to avoid implying a second reader was used.
- Added a two-document historical-fixture workbook and full-source coverage/controller regressions.
