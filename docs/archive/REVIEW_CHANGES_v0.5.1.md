# v0.5.1-review — changes made during the independent review of v0.5.0

This is a reviewer's build, not a GPT-6 release. It contains only fixes for defects that were reproduced
on real SEC exhibits or real subscription model calls on 2026-11-14. It is **not** accepted for
historical extraction. Full findings: `REVIEW_REPORT_M5_v0.5.0.md` (kept with the review log).

| Fix | File | Defect reproduced | Change | Evidence after the change |
|---|---|---|---|---|
| RF-01 | `src/royalty_research/m4_operator.py` | Live Sonnet call rejected: checker requires top-level `schema`, prompt never names it | Prompt lists the required top-level keys | Next live calls captured |
| RF-02 | `src/royalty_research/parsing.py` | Clauses cut at source line breaks; table cells emitted as separate passages; `$` and `%` in their own cells | Whitespace collapsed inside text nodes; a data row is one passage; symbol-only cells glued to their value; layout tables keep paragraph breaks | 80 of 80 real exhibits: identical non-whitespace text; 58,728 → 33,960 passages |
| RF-03 | `schemas/m2_extraction.schema.json` (both copies) | Runner requires `reader.engine == "claude"`, schema allowed only `claude-code` | `claude` added to the enum | Sonnet run passes deterministic QC |
| RF-04 | `src/royalty_research/m2_validation.py` | A source passage shorter than 8 characters could never be cited | A short quote is accepted only when it is the entire passage | No regression test yet |
| RF-05 | `src/royalty_research/m3_workbook.py`, `pyproject.toml`, `tests/test_m3_integration.py` | `artifact_tool` unavailable; no Excel output | Writer on openpyxl (optional dependency `xlsx`); strings never become formulas; HYPERLINK only for SEC URLs of 255 characters or fewer | 3 previously failing tests pass; workbook built from two real agreements |
| RF-06 | `src/royalty_research/discovery.py` | Unquoted multi-word query: 65 EX-10 hits, 55 without the phrase | Multi-word queries sent as exact phrases unless quoted or using operators | Same day, same query: 11 EX-10 hits |
| Tests | `tests/test_review_fixes.py` | | 8 regression tests from the real excerpts | 146 tests, all pass |

Compatibility: RF-02 changes passage numbering and text hashes. Maps made with v0.5.0 must be re-made.

Not changed, still open: see the defect register (D-02 to D-05, D-08 to D-15, D-17 to D-24).
