# Data dictionary and Excel design — proposed M2 extraction contract

**Status:** Detailed draft for independent review; not yet implemented as automatic extraction or Excel export. M1 generates only candidate document and passage maps.

## Design principles

1. One **agreement** may have multiple source **documents**, each containing multiple **evidence passages**.
2. One agreement may have multiple simultaneous or conditional **royalty regimes**. A regime may include several **tiers**. A recorded 5% of `Net Sales` must not be merged with 5% of `Sublicense Fees`.
3. **Filing date differs from agreement effective date.** An old contract filed in 2025 is a 2025 filing, not a new 2025 contract.
4. **Original contract facts and professional interpretation are distinct.** Do not infer related-party status, term, or validity without support.
5. **Facts are many-to-many with evidence.** Evidence must link to each material field through `Field_Evidence`, not only to the overall agreement.
6. Numeric fields retain original wording as well as normalized values. Percentages as decimal strings avoid floating-point issues. Threshold comparators and currency units are explicit.
7. Every missing/uncertain field has a **controlled disclosure status**: `DISCLOSED`, `REDACTED`, `NOT_FOUND_AFTER_REVIEW`, `NOT_APPLICABLE`, `AMBIGUOUS`, `NOT_VERIFIED`.
8. A status of `NOT_FOUND_AFTER_REVIEW` is only permissible after independent full-contract scope checks, not merely after Python screening.
9. One evidence record has one **source document ID**, original URL, page/section/paragraph, exact excerpt and text fingerprint; an extracted field is *not* source-verified just because a number appears in a quote.
10. Source links replace permanent raw HTML/PDF copies by user choice; normalized extracted text may remain in local intermediate maps for reprocessing. Deletion of raw files is not a claim that original sources can later be reproduced.

## Proposed Excel worksheets and row grain

| Sheet | One row per | Primary key | Notes |
|---|---|---|---|
| `Royalty_Summary` | individual publishable royalty observation / tier | `royalty_term_id + tier_sequence` | User-facing, agreement attributes repeated for filtering, not source-of-truth |
| `Agreements` | unique underlying negotiated/licensed arrangement | `agreement_id` | Do not count filing duplicates as new deals |
| `Documents` | unique SEC exhibit / filing version | `document_id` | Link to agreements through `Document_Agreements` for multi-party amendments |
| `Document_Agreements` | agreement-document linkage | `agreement_id + document_id + relation_type` | Original, amendment, restatement, narrative, legal dispute |
| `Royalty_Terms` | distinct economic rate rule | `royalty_term_id` | Headline rate plus basis, scope, conditions, evidence; may have many tiers |
| `Royalty_Tiers` | tier of a rate rule | `royalty_term_id + tier_sequence` | Boundaries, inclusivity, cumulative/marginal mechanics |
| `Other_Payments` | upfront/milestone/minimum/cap or other payment provision | `payment_id` | Keep apart from percentage-based running royalties |
| `Rights` | scope of rights / condition record | `rights_id` | Exclusivity can change over time |
| `Amendments` | amendment / supersession relationship | `amendment_id` | Preserve previous contractual facts |
| `Evidence` | source quotation/reference | `evidence_id` | Verbatim clause, original URL, retrieval and mapping metadata |
| `Field_Evidence` | support link between a field and evidence | `entity + entity_id + field + evidence_id` | One field may require definition and economic clause |
| `Field_Status` | disclosure status for an extracted field | `entity + entity_id + field` | Explicit missing / redacted / not applicable statuses |
| `Open_Issues` | unresolved discrepancy / extraction exception | `issue_id` | Document, severity, action, resolution |
| `QC` | test per document / agreement / run | `qc_id` | Separate algorithmic validation, AI review and human sign-off |
| `Definitions` | schema terms and value vocabularies | `field_path` | Human-readable data dictionary |

For 20,000+ agreements and potentially many royalty tiers, generate one or more user-facing Excel workbooks by year if Excel performance requires it. Preserve global, collision-resistant IDs across all files. The year shown must specify `filing_year` versus `effective_year`.

## Mandatory attributes per entity

### `Agreements`

| Field | Type | Interpretation |
|---|---|---|
| `agreement_id` | string / PK | Stable independent licence arrangement ID |
| `agreement_title` | text | Original document title, if known |
| `licensor_name`, `licensee_name` | text | Legal names as stated in source |
| `licensor_parent`, `licensee_parent` | nullable text | Parent identity only if supported |
| `related_party_status` | enum | THIRD_PARTY / RELATED_PARTY / UNKNOWN |
| `agreement_type` | multi-label enum | Patent, trademark, copyright, franchise, technology, software, cross-licence, hybrid |
| `industry`, `subindustry` | controlled string | Industry classification and product market |
| `licensed_ip_description`, `licensed_products` | text | Asset/product identity, not marketing inference |
| `execution_date`, `effective_date`, `expiry_date` | ISO date or null | Must not be assumed from SEC filing date |
| `duration_text` | text | Original contract wording on term |
| `contractual_status` | enum | EXECUTED / PROPOSED / CONDITIONAL / TERMINATED / EXPIRED / SUPERSEDED / UNKNOWN |
| `territory`, `field_of_use` | text | Source-backed territory / application constraints |
| `exclusivity` | enum | EXCLUSIVE / SOLE / NONEXCLUSIVE / MIXED / UNKNOWN |
| `sublicensing_permitted` | enum | YES / NO / CONDITIONAL / UNKNOWN |
| `renewal_rights`, `termination_rights` | text | Separate from duration and operative status |
| `in_scope_status` | enum | QUALIFIED / PENDING / OUT_OF_SCOPE / REDACTED_ONLY |
| `filing_year_first_seen` | integer | First discovery in SEC filing window, not agreement year |
| `review_status` | enum | Detailed status ladder below |

### `Documents`

`document_id`, `filing_id`, `agreement_id` (via relationship table), `cik`, `accession`, `form`, `exhibit_number`, `filename`, `filing_date`, `source_url`, `document_relation` (original, amendment, restatement, narrative, court, secondary), `original_sha256`, `normalized_text_sha256`, `retrieved_at_utc`, `text_parser`, `text_coverage_status`, `download_status`, `link_last_checked_at_utc`, `filing_metadata_notes`.

### `Royalty_Terms`

`royalty_term_id`, `agreement_id`, `term_family` (PRODUCT_SALES / SUBLICENSING_RECEIPTS / PER_UNIT / USAGE / REVENUE_SHARE / OTHER), `original_rate_wording`, `normalized_rate_value` (decimal string or null), `rate_unit` (PERCENT / CURRENCY_PER_UNIT / FORMULA / REDACTED), `rate_formula_text`, `royalty_base`, `royalty_base_defined_term`, `royalty_base_deductions`, `licensed_product_scope`, `territory_scope`, `field_of_use_scope`, `rate_structure` (FLAT / TIERED / STEP_UP / STEP_DOWN / HYBRID / FORMULA), `tier_group_id`, `royalty_trigger`, `rate_reduction`, `credits_offsets`, `anti_stacking`, `cap_floor_reference`, `payment_frequency`, `effective_from`, `effective_to`, `condition_text`, `operative_status`, `disclosure_status`, `uncertainty_note`.

**One royalty-term record does not automatically equal one percentage.** A single rule may have many tier rows. `rate_value` should not be populated with only the maximum tier if the structure is tiered.

### `Royalty_Tiers`

`royalty_term_id`, `tier_sequence`, `threshold_basis`, `threshold_lower`, `threshold_upper`, `lower_inclusive`, `upper_inclusive`, `rate_value`, `rate_unit`, `tier_calculation` (MARGINAL / ALL_UNITS / CUMULATIVE / UNKNOWN), `measurement_period`, `measurement_currency`, `tier_condition`, `tier_evidence_id`.

Never assume tiers are contiguous or marginal merely because the source lists increasing sales bands. Python may flag apparent gaps, but the AI/reviewer must adjudicate economic interpretation.

### `Other_Payments`

`payment_id`, `agreement_id`, `payment_type` (UPFRONT / MILESTONE / MINIMUM_ROYALTY / GUARANTEE / ADVANCE / CAP / SERVICE / OTHER), `original_wording`, `amount_value`, `currency`, `percentage_value`, `calculation_base`, `trigger`, `timing`, `creditable_against_running_royalty`, `payment_scope`, `disclosure_status`, `evidence_id`.

### `Rights` / `Amendments`

Rights: `rights_id`, `agreement_id`, `type`, `scope`, `effective_from`, `effective_to`, `exceptions`, `evidence_id`.

Amendments: `amendment_id`, `agreement_id`, `document_id`, `amendment_date`, `affected_clause`, `affected_term_ids`, `change_description`, `supersedes_prior`, `effective_date`, `review_status`, `evidence_id`.

### `Evidence`

`evidence_id`, `document_id`, `source_url`, `filing_accession`, `exhibit_number`, `original_sha256`, `normalized_text_sha256`, `passage_id`, `section_number`, `page_number`, `quote_exact_normalized`, `evidence_role` (RATE / BASE / TIER / CONDITION / DEFINITIONS / RIGHTS / NEGATIVE / OTHER), `verified_quote_exists`, `semantic_review_status`, `retrieved_at_utc`, `verified_at_utc`.

### `Field_Evidence` / `Field_Status`

`entity_type`, `entity_id`, `field_name`, `evidence_id`, `role`, `support_status`; and `entity_type`, `entity_id`, `field_name`, `disclosure_status`, `reason` respectively.

A rate and its denominator should have separate evidence links even if they occur in the same sentence; a rate and its exceptions may need several pieces of evidence.

### `Open_Issues` / `QC`

`issue_id`, `entity_id`, `issue_type`, `severity`, `observed_issue`, `source_document_id`, `owner`, `status`, `resolution`, `timestamp`; and `qc_id`, `scope_id`, `gate_name`, `status`, `check_version`, `details`, `ai_reader_model`, `independent_reader_model`, `human_reviewer`, `reviewed_at_utc`, `evidence_ids`.

## Publication and review statuses

`DISCOVERED → SOURCE_RETRIEVED → TEXT_PARSED → MAPPED → AI_EXTRACTED → QUOTE_CHECKED → COVERAGE_CHECKED → SECOND_AI_REVIEWED → HUMAN_REVIEWED`.

`EXCEPTION` is a separate branch at every stage. `REDACTED` is a disclosure status, not an extraction failure. `QUOTE_CHECKED` is *not* equivalent to `SEMANTICALLY_VERIFIED`, and `COVERAGE_CHECKED` refers to an identified candidate universe unless independently assessed against unflagged text.

The user-facing summary must label `automated_extract`, `evidence_verified`, `independent_ai_review`, and `human_reviewer` separately. A record is never automatically marked `audit-approved`.

## Illustrative hypothetical agreement (not a real observation)

- Agreement `AGR-EXAMPLE`: patent and know-how licence, worldwide, initially exclusive.
- Rule `RT-01`: 3% of net sales through the first US$10m of annual sales, then 5% marginally above US$10m; separate rows in `Royalty_Tiers`.
- Rule `RT-02`: 20% of sublicense fees, excluding actual product-sale royalties; different `term_family` and evidence.
- Payment `OP-01`: US$100,000 minimum annual royalty; report whether creditable to running royalties.
- Conditional adjustment: 50% step-down in specified countries after valid patent claims end. Must link to `RT-01` and its supporting clause, not create an unrelated ordinary royalty of 50%.
- The model must not infer that this is a 3–5% industry benchmark without reviewing exclusivity, term, territory, bundling, payments and age.

## Schema file

`schemas/agreement.schema.json` provides a machine-readable future agreement output contract. Additional field-level validation is needed before it can be a production AI output contract. Data dictionary and field choices should be reviewed by Fable against real SEC agreements before M2 implementation.
