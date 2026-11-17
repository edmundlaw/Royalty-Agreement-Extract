# Codex findings — M13 v0.13.3

Verdict: **CONDITIONAL** for exporter/schema functional QA. The three reproducible exporter defects below are corrected and offline tests pass. This is review plus self-validation of repairs, not independent sign-off on the new code. Contract-level precision/recall: **NOT MEASURED**.

| ID | Severity / impact | Reproduction and root cause | Correction / test | Outcome |
|---|---|---|---|---|
| C-01 | Major: source evidence hidden | `m13_research_export.py:research_rows` treated `Rate_Evidence_IDs='["1-E01"]'` and payment IDs as literal IDs. In the sealed FunctionalBrands example this left 6 rate quotes, 13 payment quotes and 86 reverse-link cells blank. | `_ids()` decodes M3 JSON arrays; `test_json_evidence_ids_link_quotes_and_records`. | Six rate and 13 payment quotes now populated; 52 evidence rows have reverse links (remaining evidence is not linked to a displayed record). |
| C-02 | Moderate: misleading amount status | `m13_research_export.py:_payment_summary` displayed `2-PAY02` as `USD AMOUNT_NOT_DISCLOSED` despite `Disclosure_Status=AMBIGUOUS`; the source schedule is not converted into an assumed total. | Display `AMOUNT_AMBIGUOUS`; `test_ambiguous_amount_is_not_called_undisclosed`. | Correct status, no invented value. |
| C-03 | Moderate: unrelated guarantee in main column | `_payment_summary` matched generic `annual minimum` and `minimum guarantee`; synthetic records with Basis `Annual minimum marketing expenditure` and `Minimum guarantee of share price` appeared as minimum royalties. | Restrict GUARANTEE display to explicitly royalty-labelled leading basis; expanded payment regression. | Both unrelated guarantees remain on payment detail, absent from Minimum guarantee. |

The original FunctionalBrands example contains overlapping/duplicated reported items: USD 150,000 advance in `1-PAY03` and `2-PAY03`; 400,000 shares in `1-PAY06` and `2-PAY04`; USD 200,000 minimum in `1-PAY04` overlaps USD 50,000 and USD 150,000 advance components. These source records are preserved separately and never summed in the exporter. `2-PAY02` remains ambiguous. `OTHER` records stay in detailed payments without being forced into a fee category.

Both schema copies are identical and include optional `agreement.exclusivity_scope`; source validation requires a known evidence ID. M3 chunk merge keeps the first value and records a conflict issue. The FunctionalBrands ZIP lacks the first-reader extraction JSON, so its first-reader `Exclusive` statement and semantic support for scope cannot be reverified from packaged source. The workbook explicitly reports conflicting exclusive deal terms and non-exclusive grant; scope remains `NOT_ASSESSED`. A synthetic exact `Exclusive` value survives export. No legal term was altered.

Remaining limits: no fresh unseen SEC gold standard, no live SEC link reachability check, no live single/combined subscription-runner execution. Default five-sheet and optional detailed sixteen-sheet routing were inspected and covered by offline M13 tests. M13 two-reader numeric comparison code was not changed.

The v0.13.1 package was not supplied or found locally, so a file-by-file v0.13.1 regression comparison was not completed; this remains an explicit acceptance limitation.
