# Independent review instructions for Fable / local Codex or Claude Code

**Release:** v0.1.0 / M1, foundational Python only. This is an independent review target, not a claim of completeness or release approval. No paid AI inference will run during M1 tests.

## Review order

1. Read `README.md`, `docs/DATA_DICTIONARY.md`, `docs/SEC_DISCOVERY.md`, `docs/QUALITY_GATES.md` and schema.
2. Reproduce `PYTHONPATH=src python3 -m unittest discover -s tests -v` with no network access. Review the assertion quality; challenge synthetic examples and edge cases.
3. Run all offline CLI examples. Check idempotency, `--force`, `--skip-existing`, malformed files, untagged passages, duplicate and saturated searches.
4. On user's Mac, use a legitimate user agent and run **one day only** SEC full-text search with several independent terms, plus one quarterly index and at least three real filing inventories. Record exact commands, result counts, response content types and failures.
5. On two real SEC HTML exhibits, run `map --url`, compare source HTML with extracted passage inventory and inspect tables, appendices, long paragraphs, section references, defined terms and omitted formatting. Do not attempt AI extraction yet.
6. Attempt a scanned/unsupported document and verify that it becomes an explicit exception, not a false negative.
7. Audit security and SEC fair-access controls. Check Python compatibility and dependencies on the Mac.
8. Deliver a numbered defect report with reproducible commands and source URLs, severity, root cause and recommended fix. Keep all review/test outputs external to sensitive client repositories.

## Independent questions

- Does the full-text search include enough distinct queries to avoid systemic false negatives?
- Can the filing inventory parser cope with SEC's actual document tables?
- Do section/schedule boundaries, defined terms, mathematical formulas and table semantics survive HTML/PDF normalization?
- Does a complete paragraph list materially reduce omission risk, or does it give false confidence?
- Is a separate per-document JSON file with retained normalized text compatible with the user's no-original-archive preference?
- Are the data fields sufficient for economic and valuation comparability, including multiple royalty regimes and payment bases?
- Are output status labels sufficiently conservative?

## Do NOT do yet

- Do not run a five-year sweep, bulk downloading or permanent archive.
- Do not enable paid model APIs or assume CLI inference can be automated without checking subscription terms.
- Do not label synthetic test records as real royalties.
- Do not create a new hosted database or production website.
