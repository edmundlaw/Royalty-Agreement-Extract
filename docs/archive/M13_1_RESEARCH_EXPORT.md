# M13 v0.13.1 — research workbook integration

## Purpose and scope

This is a **presentation and metadata** patch on M13 v0.13.0, not a new extraction-QC architecture. The five-sheet workbook is built deterministically from the first-reader extraction and the exact same M13 `rows.json` used in the original 16-sheet output. No independent reader corrections are merged into the first reader's rows. The separate optional 16-sheet workbook exists for full technical audit.

### Five-sheet default output

1. `01 Royalty Database`: observation-level rates, rate base, licensed IP, **source-referenced IA nature**, exclusivity, sublicensing rights, agreement metadata, source evidence and QC state. The rate column stores **percent-points**: numeric `30` is displayed as `30.0%`, and is NOT a decimal fraction of `0.30`.
2. `02 Tiers & Mechanics`: rate tiers, conditions and adjustments as explicitly typed rows. A missing tier row means none extracted, not none in the actual contract.
3. `03 Other Payments`: amounts remain separate, including potentially duplicated totals. No additions or effective-rate inference.
4. `04 Source Evidence`: every original source quotation, evidence ID, passage ID, source URL, extraction hash. Original quotation text is not paraphrased.
5. `05 QC & Issues`: reader check, CORE/STRUCTURE/NOTE differences, open issues, QC summaries, amendment links and pending jobs; no automatic resolution.

The original 16-sheet layout and every underlying record are still in `rows.json` and `/csv`. For an additional full technical Excel use `--legacy-xlsx` on `m13-finalize` (creates `Royalty_Research_M13_Detailed.xlsx`) or `m13-combine` (creates `<output-stem>_Detailed.xlsx`). CSV-only export is unchanged.

## Schema additions (optional, backward compatible)

`agreement.licensed_ip_nature`: TRADEMARK_BRAND, PATENT, COPYRIGHT, SOFTWARE, KNOW_HOW, TRADE_SECRET, FRANCHISE, MIXED, OTHER, UNDETERMINED or null. Both the type and its supporting source quotation must be recorded. Type is a **source-supported candidate classification**, not independent legal verification.

`agreement.licensed_ip_nature_details` and `agreement.sublicensing_rights`: string or null; any populated value needs an existing `agreement.field_evidence` entry with an actual evidence ID and an exact source quotation. Silence is **unknown**, not a prohibition.

`agreement.other_material_terms`: optional array of `{category, text, evidence_ids}` for document-level licence rights or limitations not otherwise captured. Source ID is mandatory for each entry. Economic royalty/fee terms MUST remain in `royalty_terms` or `other_payments`; this is not a dumping ground or a substitute for extraction.

Legacy M13 runs have no optional fields and use `NOT_ASSESSED` on output. The existing `exclusivity` field is retained, not reinterpreted.

## Style source

User's Excel rule workbook `.Rule_v0.2.xlsx`, sent in the email “Formatting” on 2026-08-31. Georgia 15pt sheet titles; Arial 10pt data; white background; core orange `#FD5108` header and section rules; black text; grey `#F5F7F8` alternate rows and occasional `#DFE3E6` separators; no orange slabs, blue/red heading text, italics or underlining. The user asked for visible borderlines; the implementation uses orange header rules and sparse light-grey row dividers.

## Usage (no model call in export)

```sh
# Existing prepared/finished run; model execution happens separately as before
python -m royalty_research m13-finalize --root runs/AGREEMENT_001
# Export BOTH the default five-sheet workbook and old 16-sheet technical workbook
python -m royalty_research m13-finalize --root runs/AGREEMENT_002 --legacy-xlsx
# Combine completed runs, prefer checked version when available
python -m royalty_research m13-combine --runs runs --out Royalty_Research_All.xlsx --legacy-xlsx
```

M13 exports are append-only to new run/output folders. `m13-finalize` never overwrites existing output; use a different run directory for a fresh attempt. `m13-combine` refuses an already-existing target.

## Quality boundaries

- The M13 two-reader QC still compares rates, tiers, thresholds, minimums and caps, **not IA nature, sublicensing-rights wording, exclusivity, royalty base, territory, or license term**. These new columns have citation checks but no semantic assurance and are first-reader values.
- Exact quoted source evidence is not a guarantee of correct interpretation. IA classification may need professional legal/economic review.
- Duplicate rate observations may be distinct clauses or term inflation; rates are NOT deduplicated automatically.
- The combined output may contain multiple historical runs for the same document if the supplied runs directory includes them; do not treat output rows as unique transactions.
- `NOT_ASSESSED` is used for unavailable new fields; it does not mean the clause is absent.
- Text beyond Excel's 32,767-character per-cell limit raises an error rather than being silently truncated.
- Not benchmarked for extraction precision/recall; no independent Codex PASS yet, not for historical bulk SEC processing.
