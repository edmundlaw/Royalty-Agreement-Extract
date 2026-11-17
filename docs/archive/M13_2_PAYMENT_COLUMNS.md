# M13 v0.13.2 — payment categories and exclusivity scope

## Scope
Only the source-bound extraction prompt, optional agreement metadata, and five-sheet research Excel output are changed. The M13 two-reader comparison algorithm, source reading engine, subscription/billing safeguards, 16-sheet optional technical output, rows.json and CSV records remain unchanged. This version is not a contract-level accuracy validation.

## Research Database columns
- **Minimum guarantee**: `MINIMUM_ROYALTY`, plus `GUARANTEE` entries only if their recorded basis begins explicitly with `minimum royalty`, `minimum guarantee`, `guaranteed minimum`, or `annual minimum`. Other guarantees remain visible in `03 Other Payments`, not silently treated as royalty minimums.
- **Royalty cap**: `CAP` records.
- **Advance / prepayment**: `ADVANCE` records. A creditable advance payable at signing is an advance, not automatically an upfront fee.
- **Upfront fee**: `UPFRONT` records. A one-time fee can be distinct from advances; payment timing alone is insufficient. Recoupability and non-refundable wording are not synonymous.
- **Exclusivity scope**: new OPTIONAL `agreement.exclusivity_scope` extracted with an existing source evidence ID. Legacy readings or unresolved scopes show `NOT_ASSESSED`; this is not a legal opinion or evidence that no limitation applies.
- **Payment source IDs**: `Kind:Payment_ID:Evidence_IDs` entries for all payment records, for tracing each summary to `03 Other Payments` and `04 Source Evidence`.

Agreement-level payment categories are repeated on every royalty observation row for filtering only; they are NOT independent obligations at each rate. No sums, no netting, no inference that unrecorded categories equal zero. One amount may be shown multiple times across related clauses or amendments: review `03 Other Payments` before economic aggregation.

`UPFRONT`, `ADVANCE`, `MINIMUM_ROYALTY`, `GUARANTEE`, `CAP` already existed in M13's payment schema; no migration or new payment type is required. A misclassified first-reader payment remains misclassified until source review. The two-reader QC does NOT independently verify these presentation columns, exclusivity scope, exclusivity interpretation, or payment recoupability. Source evidence binding checks only existence/quote integrity, not every economic interpretation.

## Example — FunctionalBrands
The output retains 6 royalty observations, 13 payments, 86 evidence records, 10 conditions, 4 adjustments, 7 reader differences and 23 open issues. There are multiple advances and guarantee/minimum records, but no separately extracted UPFRONT row, so the main Upfront Fee cell displays `NOT_ASSESSED`. The prior conflicting exclusivity wording is retained; scope is not invented.
