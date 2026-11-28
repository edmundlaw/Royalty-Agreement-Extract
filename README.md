# Royalty Agreement Extract

Run the one-sheet agreement summary from the repository:

```sh
./royalty-summary.sh 2026-01-12 2026-01-14 5 --go
```

Replace the inclusive SEC filing dates and the maximum number of exhibits
that pass preparation. The batch attempts up to ten EX-10 candidates per slot.
By default only EX-10 exhibits go through the frozen Nov 22 pre-screen and
evidence pointer check. Use `--exhibits EX-10,EX-4` to select other SEC
document-type prefixes. Add `--contract-title-only` to exclude known titles
without a contract keyword. Unknown titles continue and are flagged. The
screening log records document type, title and exclusions. Preparation errors,
including unreadable and oversized sources,
are logged as REVIEW. With `--go`, the launcher sends eligible KEEPs and readable
REVIEWs to Codex. REVIEW rows carry a pending-human-review notice in Other
material conditions, and one exhibit can produce several rows. Omit `--go`
to prepare and screen without making model calls or writing a workbook.

The batch prints its output folder and writes a separate `screening_log.json`.
For a prepared HTML exhibit missing its closing root tag, a separate recovery
check may allow a REVIEW to proceed if the extractor recovered a substantive
agreement body with evidence of an ending. The log preserves the original
decision and evidence, and the workbook flags that completeness is unverified.
For a `--go` batch, `--exclude-royalty-screen royalty-screen.4` explicitly adds
the version-4 exclusions to the frozen KEEPs. See the
[version-4 validation notes](docs/ROYALTY_SCREEN_VALIDATION.md).

The frozen files must be available at
`../royalty_prescreen_prototype/validation_v3/` relative to this checkout.
The launcher verifies both hashes before using them. Install the existing
`pdf` and `xlsx` extras in the launcher's Python environment for PDF parsing
and workbook export.

The launcher uses the existing SEC contact configuration (`ROYALTY_SEC_UA` or
`~/.config/royalty-research/sec_user_agent`) and Codex CLI signed in through
ChatGPT. The workbook keeps 16 columns. Other material conditions identifies
sources such as press releases, amendments and term sheets, and describes
non-licence roles. Cells too long for Excel retain their full text in a cell
note and the saved raw response. Verify consequential terms against the
original SEC link. The reader cannot see redactions or embedded images.

## Earlier research workflow

Start with [RUN_M13.md](RUN_M13.md). Production uses complete source packets by default. The separate `lean_research.py` excerpt path is preliminary triage only.

See [CHANGELOG.md](CHANGELOG.md), [TEST_RESULTS.md](TEST_RESULTS.md), and [ARCHITECTURE_TOKEN_EFFICIENCY.md](ARCHITECTURE_TOKEN_EFFICIENCY.md). Historical development reports are in `docs/archive/`. Schemas are in `schemas/` and `src/royalty_research/schemas/`; implementation is in `src/royalty_research/`.

No live extraction benchmark or contract-level precision/recall claim is included.
