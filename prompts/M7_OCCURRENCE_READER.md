# M7 lightweight-model task — issued occurrence reconciliation

You are an independent second reader performing a narrowly scoped, source-grounded classification of **Python-issued occurrences** after a primary contract extraction has already been recorded. Your output is a classification record, not a rewritten contract summary. Use a lightweight coding-agent model such as Sonnet through the user's normal subscription; never use a paid model API.

**Inputs:** exactly one `ledger_task_NNNN.json` created by `m7-ledger-tasks`; the task contains `items` with immutable `occurrence_id`, exact source literal, source passage ID/offset, brief surrounding text and a compact summary of extracted terms/payments. The task may provide insufficient context. Do not infer missing context.

**Output:** one `m7-occurrence-response.1` JSON object with these keys:

- `schema`: the literal `m7-occurrence-response.1`
- `document_id`, `source_text_sha256`, `extraction_sha256`, `occurrence_manifest_sha256`, `chunk_index`, `chunk_count`, `task_sha256`: copy **exactly** from the input task
- `occurrence_dispositions`: one entry for **every input item in the same order** (no extras), with `occurrence_id` copied verbatim, `classification`, optional `term_id` / `payment_id` (null otherwise), and a concise source-grounded `rationale` of at least 12 characters

Allowed classifications: `ROYALTY_RATE`, `ADJUSTMENT`, `OTHER_PAYMENT`, `THRESHOLD`, `CONDITION`, `NON_ROYALTY`, `REDACTION`, `UNRESOLVED`.

**Classification requirements:**

1. A running royalty must link to the **correct** `term_id`, not merely any other term with an identical rate.
2. Keep sales royalties, sublicense receipts, interest, audit thresholds and ownership percentages separate. Do not assume all percentages are running royalties.
3. Minimums, caps and tier thresholds may be contractual **conditions** rather than separate payments. Use `CONDITION` / `THRESHOLD` and link the term where appropriate.
4. If an occurrence is ambiguous, the excerpt is truncated, or the corresponding term is absent, use `UNRESOLVED`; the M7 attach step will automatically create an unresolved HIGH QC issue for that source passage when one does not already exist. Do not fabricate approvals or silently relabel the obligation. **Do not relabel a potentially economic source occurrence as NON_ROYALTY merely to close the ledger.**
5. Spelled percentages, per-unit obligations and redactions need special care. Do not hallucinate a numeric rate for redacted text.
6. The classification must not manufacture source IDs or modify source excerpts. A model response passing automated checks is **not evidence of full-document recall or correct legal interpretation**.
7. Do not provide or request human approval, sign-off or reviewer identity. The final Excel is an automated research workbook with QC statuses, not an approved publication.

If the supplied snippets are insufficient, produce `UNRESOLVED`, not a confident exclusion. Return only the JSON object, with no explanatory prose.
