# M1 test report — v0.1.0

## Test scope

- Unit and CLI regression test suite using **offline fixture documents only**.
- SEC quarterly master.idx parsing, individual filing inventory parsing, full-text response handling, saturation detection, deduplication and invalid data.
- HTML/TXT parsing, defined terms, broad numeric/royalty detection, cross-references, and preservation of otherwise untagged passages.
- Map integrity: offsets, counts, fingerprints, unique IDs, source links, idempotency, exception record.
- Security: domain allowlist, contact user agent requirement, HTTP 403 fail-closed.

## Provenance and limitations

- The 2025 SEC full-text URL and quarterly-index format were cross-checked against SEC documentation; executable SEC network access was **not available from this build container** (DNS failure).
- Therefore **no live SEC integration or PDF-layout coverage claim** is made.
- All royalty clauses in the bundled HTML test contract are **fictional synthetic test cases**; earlier conversation's eight research examples are not reproduced in these fixtures as audited benchmark labels.
- M1 tests **do not test LLM extraction or completeness against entire actual agreements**.
- Documentation: https://www.sec.gov/about/developer-resources and https://www.sec.gov/edgar/search/efts-faq.html

## Operational status

Run `PYTHONPATH=src python3 -m unittest discover -s tests -v` to obtain current assertion counts and results; refer to `docs/RUN_LOG.txt` for results from release packaging.

## Results recorded in this build

- **25 / 25 offline regression tests passed** (`docs/RUN_LOG.txt`), including intentional negative-path exceptions.
- CLI smoke test: synthetic HTML parsed into **12 passages**, of which **8** are heuristically flagged; all 12 remain in the map.
- Quarterly index fixture: **2 filings** parsed; filing inventory fixture: **2 documents** parsed.
- `validate-map` passed, including section-to-passage coverage; Python bytecode compilation passed.
- JSON Schema Draft 2020-12 structural validation using `jsonschema` passed in the build environment.
- SEC network requests from the build container failed at DNS resolution; there was **no validated live SEC end-to-end run**.

**No accuracy/recall percentage may be inferred from the 25 tests:** these are programming unit tests, not manually verified real-contract extraction benchmarks.
