# M4 v0.4.0 — offline test and release report

**Scope:** M1–M4 combined code. **Result: 116 / 116 Python `unittest` tests passed** on the packaging environment. These are deterministic engineering/CLI-mock tests, **not** empirical royalty extraction accuracy or human-reviewed SEC completeness results.

## Automated regression coverage

- Existing M1 SEC search/inventory parsers, HTTP and source-map error handling; M2 quote/number/percentage disposition and structural checks; M3 chunk merging, immutable attempts, second-reader provenance, staging workbook and human-review separation.
- M4 source line segmentation: exact reconstruction and hashes, forced within-token split warnings, fragment coverage/tamper detection and full packet inclusion.
- M4 immutable task plan: exact map/packet/prompt/source hashes, model identity, section inventory, full vs selected scope and no silent plan overwrite.
- M4 simulated Claude and Codex CLI execution: response JSON envelope/last-message parsing, strict source/run IDs, document/packet hash checks, environment API-key block, explicit flags and no model calls on dry run.
- M4 interruptions: no automatic retry after failed, malformed or interrupted runs; manual retry receipts; quota stop; manual reset; surviving on-disk outputs and controlled recovery of orphan result JSON.
- M4 cross-stage integration: fictional contract with omitted economic rates gets a deterministic QC **FAIL**; an independently prewritten **fictional** complete M2 fixture merges through the same fake CLI bridge and receives `PASS_DETERMINISTIC_ONLY` (not human assurance).
- M3 workbook integration checks remain in the full suite, using the installed `artifact_tool` on this environment. No Mac test or UI-level professional accuracy review was performed.

## Tests not performed here

- Real SEC queries, downloads and agreement document parsing at scale (container network restrictions / not in test scope).
- Actual subscription-authenticated Claude Code `-p` or Codex `exec` calls. Only locally scripted mock CLI binaries were used; no live inference, billed usage, speed or plan enforcement measured.
- Real human-verified 25-case development benchmark or 60-case locked holdout.
- SEC sampling-based discovery recall, contract economics semantic accuracy, repeatable amendment reconciliation, source link longevity or professional audit acceptance.
- Mac CLI behavior, credential mode or Excel exporter dependency availability.

## Fail-closed conditions and warnings

- Generated model outputs are labeled `CAPTURED_NOT_QC_APPROVED` until M3 deterministic and independent/actual human checks.
- Forced within-token paragraph segmentation blocks deterministic QC PASS.
- M4 `m4-merge-plan` exits nonzero on deterministic `FAIL` and retains diagnostics for inspection.
- A successful CLI subprocess or completed packet list cannot establish that the model actually read all passages or interpreted them correctly.
- The CLI cannot guarantee no purchased subscription credits or API charges; account-level billing verification is mandatory before live work.

## Reproduction

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONPATH=src python3 -m royalty_research --version
PYTHONPATH=src python3 -m royalty_research m4-run-next --help
```

Test log: `docs/M4_OFFLINE_TEST_LOG.txt`. The archive also contains a SHA-256 file inventory for unintentional alteration checks.
