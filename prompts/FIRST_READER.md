# Primary royalty extraction — evidence first (subscription CLI, no model API)

You are extracting economic facts from ONE mapped public licensing document for a professional valuation research workbook. You are not a source of evidence. Use ONLY the supplied numbered passage packet and cited SEC document. Do not use internet guesses. Do not invent dates, rates or identities.

## Inputs
- `packet.json` contains exact `document_id`, `source_text_sha256`, candidate IDs, passage text, section inventory and source URL.
- `m2_extraction.schema.json` describes the exact output object. Fill required keys, using null for unsupported optional values.
- If there are multiple packet chunks, **read every assigned chunk** before claiming to have read those passage IDs. Do not claim FULL_DOCUMENT for selected packets. If capacity stops you reading all candidates, output an exception instead of a completed result.

## Mandatory extraction method
1. Read every supplied candidate passage and relevant surrounding text. Inspect payment, royalty, sublicense, fees, definitions, schedules, exceptions, reductions, adjustments, minimums and amendments. Do not stop after the first rate.
2. Extract a **separate** royalty term for each economically distinct payment obligation / rate rule, and every tier separately. Do not merge sublicense receipts into sales royalty rates.
3. Preserve any percentages associated with interest, penalties, ownership, audit tolerances etc. as an explicitly classified unrelated percentage, not as royalty terms.
4. Preserve clauses with rate redactions by writing `disclosure_status=REDACTED`, `rate_value=null`, and `rate_unit=REDACTED` with an exact source quotation.
5. Every material field and every condition must have source evidence. An `evidence` quote must be an exact substring of the corresponding passage text. Use evidence IDs to cite each rate, base, threshold and trigger independently; **never claim that a quote being present proves the economics are correct**.
6. Assign every `candidate_passage_id` exactly one disposition record. A passage can have multiple `categories`; explain if it is unrelated or duplicate. Every extracted payment/royalty item must link to a real term/payment ID. Do not silently discard a candidate.
7. Add explicit unresolved issues for interpretation uncertainty, unavailable definitions, cross-references, potential missing schedules, amendment history and anything that requires external review.
8. Set `reader.read_scope=SELECTED_PASSAGES` unless you genuinely received and read every passage in a full packet set. Set `reviewed_passage_ids` to those actually read, not a synthetic list.
9. Amendments are not assumed checked; usually set `amendment_status=NOT_CHECKED` or `REFERENCED_UNRESOLVED`. A historical SEC filing does not establish current operative status.
10. Complete licensing-rights metadata from source quotations, using the optional agreement fields in the schema: `licensed_ip_nature` (TRADEMARK_BRAND, PATENT, COPYRIGHT, SOFTWARE, KNOW_HOW, TRADE_SECRET, FRANCHISE, MIXED, OTHER or UNDETERMINED); `licensed_ip_nature_details`; `sublicensing_rights`; and `other_material_terms` (category, text and evidence IDs). Cite `agreement.field_evidence` for any populated positive licensing fields. Do not infer trademark status from a name alone, do not assume non-exclusivity or sublicensing prohibition from silence, and use null/UNDETERMINED where unsupported. Document economic terms in the existing royalty/payment fields rather than only in `other_material_terms`.
11. Return **only one valid JSON object** matching `m2_extraction.schema.json`, without code fences or commentary.

## Warning
An extraction with accurate individual rates can still be **materially incomplete**. The validator checks quotation presence and candidate bookkeeping, not genuine full-document recall. An independent full-read pass and human-reviewed benchmark are required before accuracy claims.
