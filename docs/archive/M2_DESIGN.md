# M2 Technical Design — Clause-level evidence and omission detection

## Objectives and implemented modules

| Component | Module/command | Deterministic control | Residual risk |
|---|---|---|---|
| Source-bound reading packet | `m2_packets.make_packets` / `make-packets` | Complete candidate inclusion; full packet exact passage list, stable SHA and chunk manifest | An LLM can fail to read a supplied chunk; text parser may have omitted visual content |
| Unflagged review sample | `deterministic_unflagged_sample` | Noncandidate snippets selected deterministically, with section spread | Not a statistical random sample of contracts; limited recall inference |
| Extraction output contract | `schemas/m2_extraction.schema.json`, `m2_schema_check` | Required fields, types, identifiers, controlled categories | Structural correctness does not imply true clauses |
| Source evidence | `m2_validation.validate_extraction` | Exact substrings in same passage, passage/doc hashes, linked field evidence | Quoted text can support a different economic meaning |
| Numeric royalty checks | `m2_validation` | Decimals match quoted percentages/per-unit amounts; numeric thresholds quoted; tiers ordered and sequence 1..N | Unit/basis/context and conditional interpretation require semantic verification |
| Candidate disposition ledger | `m2_validation` | Every M1 candidate passage assigned one reasoned disposition, linked to records | An irrelevant classification may itself be wrong; missed candidates remain unreviewed |
| Numeric percentage reconciliation | `m2_validation` | Every literal numeric percentage occurrence in each candidate paragraph is given separate outcome, linked royalty rates checked | Percentages spelled fully in words, per-unit text, cash minimums may require other detection passes |
| Blind semantic re-key | `m2_packets.make_blind_rekey_packet` | No first-reader rate/tier interpretations included | Reviews only already located clauses; not an omission search |
| Independent full read | `make-packets --mode full` + independent prompt | Every parsed passage supplied across numbered chunks | Requires separate model/human execution and read accountability |
| Cross-reader discrepancy report | `compare_independent_extractions` | Structural and term/tier/condition differences flagged | Identical results may share the same error; reviewer is still necessary |

## Exact M2 result unit

**One source document** with a verified `document_id`, `source_url` and normalized-text SHA-256. The output includes a non-inferred agreement header, royalty terms with explicit tiers, other payments, source quotations and passage dispositions. It is deliberately *not* yet a unique economic agreement across amendments and duplicated SEC filings.

The separate agreement-level master and amendment consolidation are later tasks. Conflicting filed amendments must NOT be silently merged; store them as different source documents and require a reconciled disposition.

## Evidence semantics

- `evidence.quote` must occur character-for-character inside `mapping.passages[].text`. The normalization performed by M1 may differ from original HTML display or PDF page rendering. Checking presence is a narrow deterministic fact.
- `rate_value` represents the displayed percent **as a percent number** (e.g. `5` means `5%`, not `0.05`). No floating-point transformation is performed.
- `royalty_terms[].rate_evidence_ids`, `base_evidence_ids`, `tiers[].evidence_ids`, `tiers[].threshold_evidence_ids`, each condition's `evidence_ids` and agreement's `field_evidence` are separate traceability links.
- `dispositions` cover all M1 candidate passage IDs; a passage may have several categories. `percentage_dispositions` must account for **each literal numeric percentage occurrence** in that passage. It can classify a percentage as unrelated interest instead of royalty. A classifier can still lie/misread: independent review catches some errors.
- `disclosure_status=REDACTED` requires `rate_value=null`, `rate_unit=REDACTED`, with source evidence. Do not replace redacted amounts with industry expectations.
- `reader.read_scope=FULL_DOCUMENT` is a **self-reported provenance claim** that is checked against passage IDs; it is not proof the model processed their contents.
- `open_issues` remain visible even when deterministic checks pass. High unresolved issues are warned, and `can_claim_complete` is **always false** at M2.

## Quality gates

M2 produces only `PASS_DETERMINISTIC_ONLY` or `FAIL`. This is distinct from completeness or human approval. A passing result can still have high-risk warnings and fail future publication gates.

Future acceptance requires: a human-verified gold-standard set with full-document review, an independent holdout sample, quantified document-level completeness/precision, verified paper trail, and a review of amendment effects. No 95% accuracy claim is supported by the 60 programming tests.

## Model-billing safety

The project does not call any model, API or executable agent binary. The prompts are text files for local use with a legitimately authenticated coding-agent subscription. Safe billing/usage cannot be established from inspecting local environment variables alone. The user/Fable must test those features before automation.

## Known engineering risks (M3 backlog)

1. A single M1 passage may exceed `max_chars` and currently raises an explicit error rather than splitting. Implement offset-safe fragmenting and reconciliation if observed on SEC contracts.
2. Model responses from separate chunks are not yet safely merged or provenance-bound through a journal.
3. The percent occurrence ledger does not by itself exhaustively cover spelled-out percentages, dollar amounts, per-unit formulas, indirect obligations, or tables with lost formatting.
4. Comparison uses normalized economic signatures and is a discrepancy screen, not a contract-law determination.
5. Original-file hash is only a fingerprint; without keeping the original file it cannot recreate removed or changed source bytes.
6. SEC discovery recall and true contract-qualification rate are unmeasured; Fable should perform the initial live-day audit.
