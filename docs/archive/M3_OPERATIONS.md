# M3 operations, provenance and amendment linkage

## Workspaces

- `workspace.json`: only initializes local schema. No SaaS, database or LLM API.
- `documents/REC-<hash>/map.json`: immutable canonical M1 source map, including full normalized source passages. **This is a working text representation, NOT an archived original PDF/HTML file.**
- `documents/REC-<hash>/attempts/<sha256>/`: immutable extraction, deterministic QC, and attempt metadata. Reprocessing makes a NEW attempt, never overwrites an old attempt.
- `selected.json`: explicit mutable pointer to one reviewed attempt; a failed attempt can be selected for diagnosis, but still fails publication gates.
- `human_reviews/`: append-only, self-reported reviewer attestations linked to a specific immutable extraction digest.
- `ai_reviews/`: append-only second-reader results linked to the exact selected first-reader digest, invalidated for a subsequent different first read.

Mutating operations use filesystem locks on Unix/macOS and atomic writes. A workspace copied to another computer can be resumed without the previous CLI session, subject to file integrity checks.

## CLI syntax

```bash
# Create a canonical workspace
python3 -m royalty_research m3-init --workspace ~/royalty-research/work
python3 -m royalty_research m3-register-map --workspace ~/royalty-research/work --map map.json

# Append first-reader answer and select it for staged research output
python3 -m royalty_research m3-ingest --workspace ~/royalty-research/work \
  --document-id DOC-<id> --extraction first_answer.json --select

# Add independent second-reader answer without changing the first reader
python3 -m royalty_research m3-second-reader --workspace ~/royalty-research/work \
  --document-id DOC-<id> --extraction independent_answer.json

# Progress and source-linked Excel/CSV output
python3 -m royalty_research m3-status --workspace ~/royalty-research/work --out status.json
python3 -m royalty_research m3-validate-linkage --workspace ~/royalty-research/work --linkage linkage.json
python3 -m royalty_research m3-export --workspace ~/royalty-research/work --linkage linkage.json \
  --outdir export-2026-11-13 --format both
```

`--force` on M3 export replaces generated outputs; export to new directories to preserve prior snapshots and their SHA-256 manifest. A nonempty directory is refused otherwise.

## Explicit linkage file (`linkage.json`)

```json
{
  "schema": "m3-linkage.1",
  "groups": [
    {
      "agreement_id": "AGR-REVIEWED-0001",
      "document_ids": ["DOC-ORIGINAL", "DOC-AMENDMENT"],
      "status": "HUMAN_CONFIRMED",
      "reviewed_by": "Actual reviewer"
    }
  ],
  "relations": [
    {
      "from_document": "DOC-ORIGINAL",
      "to_document": "DOC-AMENDMENT",
      "relation": "AMENDS",
      "effective_date": "2025-01-01",
      "supersession_scope": "SOME_TERMS",
      "review_status": "HUMAN_CONFIRMED",
      "reviewed_by": "Actual reviewer",
      "basis": "Contractual section and link supporting the amendment relationship"
    }
  ]
}
```

This is an illustrative format only; both referenced document IDs must exist. No text duplicates, shared parties, or same license titles are automatically collapsed. A manually linked amendment **does not** automatically supersede any royalty rate in the workbook. The `Amendments` sheet records the relationship and retains the historical observations in both source documents.

## Human reviewer attestation (`review.json`)

```json
{
  "document_id": "DOC-ORIGINAL",
  "extraction_sha256": "THE_ACTUAL_64_HEX_SHA_OF_THE_SELECTED_EXTRACTION",
  "reviewer": "Actual reviewer name",
  "review_date": "2026-11-13",
  "review_scope": "FULL_DOCUMENT",
  "attested": true,
  "decision": "REVIEWED_ACCEPT",
  "amendments_checked": true
}
```

The operator is responsible for verifying the actual review. The software cannot authenticate a name or judge whether the source has been interpreted correctly. The curated `Human Reviewed` sheet also requires a human-confirmed agreement group, no unresolved high issue, a declared full-document M2 reading, a valid SEC URL, and no unresolved exact-source duplicates.

## Substantive exception policy

- `QC_FAILED`: extraction is rejected for all curated output.
- `QC_PASSED_OPEN_HIGH_ISSUE`: royalty-term/evidence rows can appear in staging, but **not** the human-reviewed view.
- `QC_PASSED_NOT_PROFESSIONALLY_VERIFIED`: extraction passed deterministic checks only; no professional sign-off.
- `HUMAN_REVIEW_RECORDED`: a self-declared full-source review was recorded; still not an audit opinion.
- `AWAITING_EXTRACTION`: source document stays in `Pending Jobs` and `Documents`; never silently excluded.

All raw observations are **historical**, not automatically currently operative. Valuers must inspect amendments, similar IP, bases, rights and conditions before relying on an observation.
