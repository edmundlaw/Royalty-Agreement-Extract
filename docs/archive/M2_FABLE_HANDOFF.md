# Fable independent review — M2 v0.2.0

## First review

Review the **source code and assertions**, not just the passing test count. Re-run the full suite offline:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m royalty_research validate-extraction \
  --map output/synthetic_clause_map.json \
  --extraction examples/synthetic_m2_extraction.json \
  --out output/reproduced_qc.json --force
```

Trace the input through `mapping.py` -> `m2_packets.py` -> `m2_schema_check.py` -> `m2_validation.py`. Review the M1 parsing and SEC discovery dependencies too.

## Critical red-team tests

1. Remove one of several royalty tiers from an otherwise correctly classified passage. Must flag omitted percentage or inconsistent tier count.
2. Replace net-sales royalty basis with gross-sales; see whether the text-based warning works and recognize that it does not prove the semantics.
3. Introduce interest, patent expiry, sublicensing fees, unrelated 50% ownership and a tier with a rate in words rather than digits. Check false positive and false negative paths.
4. Produce a valid quote from the wrong subsection that contains the right percentage but a different product/territory. Observe whether blind re-keying discovers the incorrect applicability.
5. Change source hashes and quoted substrings, duplicate a disposition, omit a candidate, and change evidence IDs. Confirm failures are not suppressed.
6. Long SEC contract, SEC PDF table, a scanned PDF, an exhibit containing redactions and a standalone definition schedule. Check parser failures are recorded, not considered no royalties.
7. Blind full-document review: deliberately include a material payment clause that M1 candidate detection does **not** flag. Confirm a full-document reader can find it, and that candidate-ledger success alone is not promoted to complete.
8. Verify normalized output schema against the machine-readable Draft 2020-12 schema and audit whether the stdlib subset validator omits any used keywords.
9. Test a three-chunk contract and interruption halfway through. M2 does not currently resume partial model outputs; this must be addressed before bulk use.
10. Ensure all CLI modes have **zero API billing**; actual AI model execution is not included in this package. Verify any `claude -p`/`codex exec` use follows official account/billing terms, not simply environment assumptions.

## Live Mac checks (separately approved; do not run bulk extraction)

- Read one or two SEC agreements from the actual URLs, compare normalized passages to rendered documents and reconcile numerical/sublicense schedules.
- Run both subscription agents only if the user authorizes and expected billing is verified.
- Report *measured* average usage, extraction recall against a manually reviewed contract, and the observed failures. Do not infer historical completion rates from code tests.

## Requested defect report

For each issue give: `ID`, `severity`, `affected module`, `reproduction command/fixture`, `expected vs actual`, `impact on omitted royalties`, and `proposed correction`. Submit changes for another regression pass. Do not call M2 audit-verified or commercially publishable.
