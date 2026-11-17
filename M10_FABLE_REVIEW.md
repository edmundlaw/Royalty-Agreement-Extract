# Fable independent QA handoff — Royalty Research M10 v0.10.0

M10 builds on your *unchanged* M9 review package. It is a **new development
release**, not a production-ready extractor. The source code includes no paid
inference API and no human-approval gate.

## What to run first

1. Preserve the original M9 files and extract M10 in a separate working directory.
2. Run `PYTHONPATH=src python -m unittest discover -s tests -q` and verify the
   report on your own Mac. Verify `python -m royalty_research --version`.
3. On your unchanged previous M9 source maps/extractions, run:
   `PYTHONPATH=src python scripts/replay_m10_against_fable.py ~/royalty-research/m9test`.
   This uses **no AI calls** and is a **known development regression**, not blind.
4. Re-check the source evidence for all reported errors; don't blindly downgrade
   an error just because Sonnet's narrative looks plausible.

## Four generalization questions

- Does the table checker identify tier rows when the sales band appears first,
  the rate appears as spelled words, or the rate is redacted? Test completely
  unfamiliar formats, not NeurogesX/AUM/Kala/Regulus/Viking/Scynexis.
- Can omitted step-ups, minimums, upfront payments, pass-through obligations,
  and redacted economic rows still pass despite an unrelated HIGH open issue?
- Are valid extractions now rejected for benign cross-references, unknown
  pass-through rates, installment components or non-royalty audit thresholds?
- Does automatic redaction bookkeeping truly reduce task count in a fresh
  **dry-run**, without suppressing rate-table completeness errors? The known
  Kala 248-occurrence case reduces to two AI ledger tasks; actual paid/subscription
  usage has **not** been measured.

## Strict independent test recommendation

Choose **at least five complete agreements not used in M1–M10 development**.
Do not provide their source text, expected royalties, or AI answers back to the
developer until test outputs are frozen. Include different table structures,
written rates, redacted economics, percentage-free obligations, and a negative
contract. Assess both (a) correct extractions that fail QC and (b) deliberate
omissions that pass QC. Do not reuse the 12 M9 exhibits as a blind holdout.

If possible use the existing saved extraction results for mutations first; do
not waste subscription usage on repeated full-contract calls. Delegate purely
mechanical tests to local Python, bounded simple checks to Sonnet, and reserve
higher reasoning for genuine conflicts.

## Stop conditions / remaining open design problems

- No published recall/precision figure exists and neither model's agreement is
  proof of contract completeness.
- The M7 occurrence reader can still label ambiguous items UNRESOLVED; all
  such high-risk issues must remain visible. M10 catches strong source facts
  independent of such issue labels but cannot detect every unusual obligation.
- The daily-capped batch runner and targeted model correction task are **not
  implemented** in this release. The remaining initial reading/long contracts
  can still consume heavy subscription usage. Test with dry-run first.
- PDF, amended agreements, external pass-through terms and account credit/auto-
  reload settings remain independently unverified. No API credits should be
  used; verify account controls separately.

Return a **reproducible defect register** identifying source passage IDs,
expected term structure, actual extracted record, QC result and minimal
reproduction. Do not authorize 2021–2025 bulk extraction.
