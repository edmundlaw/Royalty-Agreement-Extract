# Fable / Opus independent review — M11 typed-source QC candidate

## Scope

Review `Royalty_Research_M11_Typed_Source_Flags_v0.11.0.zip` independently. Preserve the original ZIP unchanged. M11 **is not** a final historical extractor and does not require human approval or sign-off. No paid inference API should be used. Delegate basic module review and tests to Sonnet if it saves subscription usage; Opus should judge contractual semantic risks.

## Baseline reproduction

1. Verify release checksums with `python scripts/verify_release.py`.
2. Run `PYTHONPATH=src python -m unittest discover -s tests -q`, record count/failures on your Mac.
3. Run the M11 opt-in mock end-to-end test and check `source_flags.csv`, other-payments disclosure columns, QC states, immutable correction-01 output, and absence of any human-approval gate.
4. Test the CLI dry-run. Explicit real `--execute` model calls require subscription verification and account-level credit/reload checks as in M9; no free-billing guarantee is claimed.

## Crucial independent tests

**First freeze at least five genuinely unseen complete agreements and their original SEC source files before looking at extraction outcomes.** Do not select from Market Finders, NeurogesX, Qualigen, Kirkland's, AUM, Kala, Equillium, KemPharm, Genprex, or any other development examples. Use several structures: sales tier, sublicense, redacted table, fee/minimum/cap, and adjustment/amendment. Check an independently prepared contractual obligation inventory against the complete original, not just the passages Python flagged.

For each fresh contract: (i) run Sonnet once on full-source primary task(s), (ii) run M11 flag accounting, (iii) allow **one** bounded Sonnet correction task if needed, (iv) measure correct-reading false failures and corruption false passes. Perturb by deleting one tier, redacted share, minimum, cap, labelled upfront fee and milestone, and by changing a family/base or MARGINAL calculation. Note that M11 still cannot certify the latter interpretation.

## Targets for observed M10 failure modes

- Equillium: the word 'sublicensees' inside a product-sales base must not change table family. Redacted sublicense-receipts obligations require distinct null-valued records, never blanket issues.
- KemPharm: redacted milestone rows must be traceable as PAYMENT records; ordinary redacted sales tiers must not be called fees. Entire long tables must be checked, not a seven-passage window.
- Genprex: flat rates in pipe-delimited enumerated rows may be FLAT terms. Insurance limits are not royalties. Sell-off cross-references are not necessarily new rates. Upfront/maintenance fees and milestones must remain visible if missing.
- NeurogesX: stacking threshold and reduction floor are not separate running royalty rates. Audit shortfall 5% is not a product-sales royalty.
- Same-source mixed percentages: `3% of Net Sales; audit shortfall 3%` must not let one term account for both.

## Defect report requirements

Report source passage IDs and evidence quotes for each finding. Separate **source detector miss**, **typed resolution failure**, **evidence/record wrong**, **semantic interpretation error**, **QC false alarm**, **execution/usage issue**. Include precise repro commands and save unmodified extraction + modified corruption JSONs.

**Do not approve 2021–2025 bulk processing** until unseen source coverage and precision/recall are measured and the subscription/Mac implementation passes. The reviewer may propose redesign if the new flags repeat M10's structural failure; do not patch by issuer name.
