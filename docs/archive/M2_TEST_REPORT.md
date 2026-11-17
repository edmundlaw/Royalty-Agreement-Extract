# M2 v0.2.0 — offline verification

- Baseline: M1 v0.1.0 retained; no production SEC source documents in the bundled example.
- New test suite: `tests/test_m2.py` plus M1 existing tests.
- **60 offline unittest tests passed**, including deliberate mutations of evidence, document hash, tier rate and thresholds, candidate passage coverage, percentage-by-percentage coverage, redaction handling, and independent-reader mismatch.
- New M2 synthetic fixture: one fictional agreement with running sales royalty tiers (6%, 4%), sublicense receipt tiers (25%, 10%), $2/unit, interest 1.5% unrelated to royalties and redacted rate adjustment. It is a deterministic test oracle, not a genuine SEC deal or model output.
- Independent standard Draft 2020-12 `jsonschema` library additionally validates the bundled schema and synthetic output. Runtime schema checking uses a dependency-free subset of the schema vocabulary.
- CLI test returns nonzero on malformed extraction while preserving QC JSON; output file writes are atomic.
- No Claude Code, Codex, API, live SEC, external network, scanned PDF, real 8-case accuracy, historical deduplication or Excel export tests are claimed in M2.

Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` to reproduce. Look at `docs/M2_RUN_LOG.txt` for exact recorded output. Tests are programming checks, **not observations of model accuracy or completeness**.
