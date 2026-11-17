# M3 test report — offline release v0.3.0

**Recorded in the packaging environment on 13 November 2026.**

Command:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

Result: **92 tests executed; 92 passed; 0 failures and 0 errors.** Some tests deliberately invoke invalid commands; their expected `ERROR` lines are printed while the test assertions pass. The complete raw run summary is included as `docs/M3_OFFLINE_TEST_LOG.txt`.

## Scope covered

| Component | Offline evidence |
|---|---|
| M1 SEC parsing and source maps | Existing 60 M1/M2 tests: SEC response pagination rejection, quarterly master indexes, exhibit directories, source-text mapping, unreadable/unsafe input failure behavior |
| M2 structured extraction QC | Existing schema and source-bound quote/rate/candidate/percentage reconciliation tests; duplicate, stale QC and invalid evidence cases |
| M3 workspace | Atomic immutable map/attempt storage, resume across commands, explicit selected-attempt pointer, corrupted source/attempt rejection, pending/failed state visibility |
| M3 chunk merger | Multi-chunk success; absent/duplicate chunks, altered packet text, stale packet hash, missing read IDs, duplicate evidence IDs, conflicting headers rejected |
| M3 linkage | Same-text filings not silently merged, explicit grouping, relation validation, unknown documents, duplicate memberships and amendment cycles rejected |
| M3 independent reader | Second extraction bound to selected first reader's digest, old AI review not carried onto a newer first reader |
| M3 review gates | High unresolved issue blocks curated output even after self-declared review; unlinked/invalid-source extraction remains out of curated view |
| M3 export | 15 styled XLSX worksheets, source URLs and SEC identifier columns, exact quotes, separate tiers, durable CSV export, output manifest fingerprints, safe numeric helper columns and formula-injection guards |
| Excel round-trip | XLSX archive verified and reimported using artifact_tool; human-reviewed test rows and SEC-safe HYPERLINK formulas checked |
| Full offline CLI pipeline | Workspace map registration -> extraction ingestion -> status -> XLSX+CSV export -> SHA-256 manifest -> overwrite prevention |

## Deliberately excluded from claims

- **No live SEC retrieval or source discovery recall benchmark.** The sample cases inside code tests are fictional.
- **No live Claude Code or Codex subscription inference**, usage-limit or billing checks.
- **No professionally reviewed SEC benchmark**, hence no measured royalty-term recall, accuracy, precision or completeness percentage.
- **No proof that AI reads all passage IDs it claims to read.** Ledger checks verify documentation consistency only.
- **No Mac `artifact_tool` installation verification.** CLI CSV export runs without it.
- **No resilient oversized individual-passage segmentation**, so some unusually formatted contracts may require explicit pre-extraction exceptions.
- **No automatic semantic reconciliation across amendments and document chunks.** All historical observations remain attributed to their source document.

The passing tests demonstrate deterministic software behavior on controlled fixtures, **not audit-grade extraction quality**. Real agreements and independently human-verified answers are needed for the latter.
