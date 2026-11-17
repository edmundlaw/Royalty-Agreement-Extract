# v0.13.8 changes

- `Usable for royalty benchmark` now looks at the document QC state. `SOURCE_CHECK_FAILED`, `SECOND_READER_FAILED_SOURCE_CHECK` and `TWO_READERS_DIFFER` force NO with first reason `needs review: <state>`; any source-check error tied to the row (its term, tiers or evidence) also forces NO. `TWO_READERS_AGREE_ON_NUMBERS` stays allowed (same numbers in the same clauses) with a note to read the STRUCTURE differences in sheet 05. `SINGLE_READER_NOT_CHECKED` (normal mode) and `TWO_READERS_AGREE` stay allowed with the usual point-of-use note. Applies in `finalize` and `combine` (the combined workbook reads each run's `source_check.json`).
- New first sheet `00 Run Summary` in the default research workbook: one row per run folder (Document ID, company / licensor - licensee, SEC link, Status, QC state, royalty rows), a counts line ("3 agreements: 2 exported, 1 not finished") and counts of candidates the batch did not read, by register status (from `batch/candidate_register.json`). Unfinished agreements (v0.13.7 combined workbook never mentioned Trevena) show `NOT_FINISHED - n of m reading calls done`; a finalize failure shows `FAILED - reason` (saved as `finalize_error.txt` in the run folder, removed again on a later success). A single-run `finalize` workbook has the sheet with its one row. `scripts/verify_research_export_parity.py` checks the sheet (optional, must be first, royalty rows add up).
- Term-sheet / conditional wording match no longer fires on "unconditional" ("Unconditional and binding license agreement" is not a term sheet); "non-binding" still matches, a bare "binding" does not.
- `licence_gate`: a short licence with fewer than 3 "royalt" mentions now passes when it states a rate ("5% of Net Sales", "5 percent of gross revenue") and has at least one licence-grant phrase, unless its title is a services / purchase / loan / ... title. Calibration on 283 maps (149 distinct documents) under the earlier test folders and `runs_*/batch/maps`: no verdict changed, so no previously rejected non-licence now passes.
- `scripts/verify_release.py` and `RELEASE_SHA256.json` were not regenerated for 0.13.8.

# v0.13.7 changes

Fixes from the first live run (3 agreements, 12-14 Jan 2026).

- `run` now keeps calling the pending tasks of the same agreement until it is fully read (then the next agreement), still bounded by `--max-calls`, prompt cap, token budget, retry and manual stops. v0.13.6 made one call per agreement and left multi-chunk agreements (Trevena, 2 chunks) half read. A dry run lists the next call of every agreement.
- Chunk merge accepts every agreement field the schema allows: the field list is now derived from `m2_extraction.schema.json` (v0.13.6 had a hard-coded list without `related_party` and `licensed_ip_nature_basis`, so finalize failed with "Bad agreement evidence" for OSR/VXM01). Regression test finalizes from raw chunk results.
- Source check: `licensed_ip_nature_details` may cite the evidence given under `licensed_ip_nature` (the reader prompt tells the reader to do exactly that); the stricter v0.13.6 rule turned the OSR/VXM01 reading into SOURCE_CHECK_FAILED.
- SEC filing metadata (filing date, accession, CIK, form, company) now travels into the source map for new runs, so `SEC filing date` is filled. For runs prepared earlier (immutable map without it) finalize looks the document up in the batch's `discovery.jsonl` / `candidate_register.json`.
- `Royalty cap` shows only caps whose basis or condition text mentions royalties (N2OFF's US$1M cap on deferred service consideration was mislabelled); other caps remain in sheet 03.
- `Usable for royalty benchmark`: new first reason "no IP licence grant found (e.g. services / profit share)" when Nature of IA is UNDETERMINED and no licence-grant wording is found in the source.
- `licence_gate` strengthened (still zero AI tokens): document title detection plus licence-grant wording (`licence_grant.py`). Services, assignment, purchase, loan and similar titles are rejected unless 25+ grant phrases; documents without a licence title need at least one grant phrase. Calibrated on 35 known licences (all still pass) and the live-run negatives (N2OFF, Trevena assignment, Luminar, Pelthos, Liftoff, ... rejected). The register shows title, title kind, grant count and reason.
- New `./royalty.sh --resume RUNS_FOLDER [--go]`. Finalize prints one clean line per agreement (details in `batch/finalize_errors.log`) instead of a traceback; new workbooks never overwrite an earlier file (`_v<version>` suffix); `run_info.json` records the date range.
- `scripts/verify_release.py` and `RELEASE_SHA256.json` were not regenerated for 0.13.7.

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
