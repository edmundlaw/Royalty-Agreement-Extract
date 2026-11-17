# M13 v0.13.2 — builder offline test report

Status: **development candidate for independent Codex review. NOT a Codex PASS.**

- 19 test modules executed separately, **325 / 325 tests passed**, including 9 research-export tests. One omnibus attempt was interrupted and must not be counted; a 9-second attempt at test_m8 timed out, and the complete `test_m8` module was rerun, passing 27 tests in 12.271 seconds.
- New tests require upfront and advance to remain distinct even when an advance is payable at signing, preserve all raw payment rows, protect against double-counting, prevent an unrelated guarantee from becoming a minimum royalty, test NULL/legacy fallback, and require an evidence ID for new exclusivity scope.
- The original 16-sheet FunctionalBrands and the v0.13.2 5-sheet derived example pass `scripts/verify_research_export_parity.py`, status `PASS_MAPPING_ONLY`: 6 royalty records, 13 payments, 86 source evidence, 10 conditions, 4 adjustments, 7 reader differences and 23 open issues.
- No live model calls and no SEC 25–50 unseen-agreement accuracy benchmark were run for this update. No contract-level recall/precision claims.
- Known limitation: source-classified payment kind can be wrong; a guarantee marked OTHER is not upgraded by heuristics, and some GUARANTEE rows with less explicit wording do not appear in the summary but remain in detail. Different agreements/amendments may mention overlapping amounts and are not consolidated.
