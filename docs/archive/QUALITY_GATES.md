# Quality gates / fail-closed policy

## M1 gates — implemented

| Gate | Objective and current behavior | Failed condition |
|---|---|---|
| Source identity | Exact SEC URL; CIK, accession, filename from search metadata | Invalid accession or dangerous filename → abort |
| Search window | Fetch all declared result pages or split saturated periods | Missing/duplicated page or saturated day → explicit failure |
| Index parsing | Parse every data row after index header | Malformed header/data row → explicit failure |
| Exhibit inventory | Document type/filename from filing table | No table or missing link → explicit failure |
| Document retrieval | User-agent, rate-limit, HTTPS/domain restriction, bounded size | 403, 429 exhausted, network error, too-large → explicit failure |
| Content decoding | Detect supported HTML/TXT/PDF, preserve table row boundaries | Bad encoding, encrypted/unreadable PDF → explicit failure |
| Passage coverage | Number every extracted text passage, keep untagged passages; map every passage into a section inventory | No readable text or missing section passage → explicit failure |
| Mapping integrity | Confirm unique IDs, offsets, counts and normalized text SHA-256 | Fail `validate-map` |
| Durable output | Atomic JSON writes and explicit exception records | No success marker for failed stage |

**Important:** M1 validates only *machine representation integrity*. It cannot certify that HTML/PDF extraction retained every source character or that the correct royalty economics were identified.

## M2 gate status — implemented controls and still-open requirements

**Implemented in v0.2.0:** strict structured output contract; exact source quote and hash checks; rate, threshold and tier numeric checks; per-passage and per-percentage disposition ledgers; selected/full reading packets; blind re-key packets; comparison of separate model results; conservative `PASS_DETERMINISTIC_ONLY` status. See `docs/M2_DESIGN.md`.

**Still not demonstrated or implemented as a complete production control:**

1. **Human-readable source completeness:** verify paragraph/table/appendix extraction against originals; flag text loss and pages not parsed. Long paragraphs, image-only schedules and OCR require separate control.
2. **Agreement classification:** signed / draft / offered / superseded / uncertain. Include negative controls.
3. **Candidate semantics:** The ledger is implemented; a classification can still be economically wrong or fail to detect a passage not flagged by Python.
4. **Actual economic extraction:** value, denominator, currency, tier boundaries, calculation mechanics, scope, time, conditions, rights, other consideration, related-party status.
5. **Cross-reference resolution:** definitions, tables, schedules and amendment chains. Never infer 'not found' from no candidate hits.
6. **Quote/source integrity:** Exact substring and mapped hash checks are implemented; display-layout and semantic source verification remain outstanding.
7. **Semantic verification:** blind independent re-keying of base, tier, trigger, term, conditions. Matching number alone is insufficient.
8. **Recall testing:** locked holdout sampled independent of tuning; full-document manual review, include noncandidate and negative samples; report uncertainty.
9. **Review status:** separate data extraction, source check, candidate coverage, independent AI recheck and human approval; no 'audit-verified' claims without professional review.
10. **Cross-document comparability:** licensor/licensee party relationship, amendments and parent/child licensing rights, valuation assessment separated from contract facts.

## Risk register

- **R1 Search recall:** Full-text keywords may miss implicit consideration or nonstandard terminology; quarterly-index sampling needed.
- **R2 Parser recall:** HTML is often fragmented; our line-numbered text inventory is not a certified facsimile. Tables and mathematical formulas may lose layout.
- **R3 Numeric false positives:** Equity ownership, interest, audit thresholds and profit margin may look like royalty rates.
- **R4 Numeric false negatives:** Rate expressed in words, bundled license fee, linked schedule or wholly redacted terms.
- **R5 Meaning:** Existence of a number in a quote does not verify the correct denominator, applicability, period or amendments.
- **R6 Cross-document history:** Different filing versions, changed agreements, redacted versions and restatements cannot be safely merged by a text hash alone.
- **R7 Commercial use:** Source-link-only records depend on SEC continued availability. An SHA-256 without archived bytes cannot reproduce the original.
- **R8 Subscription operation:** A local coding-agent CLI is not automatically an unlimited or permitted high-volume batch inference service. Verify official plan rules and actual billing before use.
