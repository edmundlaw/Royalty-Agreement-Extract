# M11 — ONE targeted source-flag correction (Sonnet preferred)

This task is not a full reread. You receive source-issued open flags only, the
exact cited passages, and a compact existing terms/payments list. Output one
valid JSON object with `schema="m11-correction-response.1"`, `task_sha256`
unchanged, and arrays: `new_evidence`, `new_terms`, `new_payments`, `new_tiers`,
`new_adjustments`, `resolutions`.

For each flag, choose one of:
1. `LINKED_RECORD`: cite `record_type` (ROYALTY_TERM/TIER/PAYMENT/ADJUSTMENT),
   `record_id` and `tier_sequence` where applicable. If no supporting record
   exists, create a complete schema-valid economic record with exact source
   quotation and evidence ID; for a redaction, use null value plus REDACTED.
2. `TYPED_EXPLANATION`: only with a checkable reason (AUDIT_THRESHOLD,
   INSURANCE_LIMIT, NON_ROYALTY_INTEREST, OWNERSHIP_PERCENT,
   STACKING_THRESHOLD, REDUCTION_FLOOR, INSTALLMENT_COMPONENT, REFERENCE_ONLY) and `target_id` for
   term-dependent reasons.
3. If uncertain, leave the flag *unresolved* and state uncertainty in the
   reasoning outside the JSON only if the invoking operator explicitly permits;
   never invent a rate, and never claim a source issue exempts a missing record.

Do not use online tools, do not invoke another agent, do not infer a redacted
number, and do not modify existing extracted facts or attempt history. Exactly
one correction attempt per agreement is budgeted; if many flags remain, the QC
report must show incomplete status rather than fabricate closure.
