# M11 — Typed source-flag QC redesign (development candidate)

**Status:** opt-in development and independent-testing candidate. **Not** certified for large-scale historical extraction. No human-approval workflow.

## Why M10 was retired as a pass/fail authority

The uploaded `REVIEW_REPORT_M10_v0.10.0.md` found 33 false QC failures across Equillium, KemPharm and Genprex (8/16/9), plus 3 on NeurogesX; an open HIGH issue could excuse missing redacted royalty economics. Worse, existing heuristic exemptions alternated between missed obligations and false alarms. The 244 passing M10 software tests did not validate real-contract recall.

**M11 is a redesign, not a patch of those keyword exceptions.** The historical M10 gates remain available only for comparison when using the legacy QC profile. A new opt-in `M11_TYPED_SIGNALS` profile excludes the M6/M7/M9/M10 heuristic source gates from the pass/fail decision, but retains M2 source binding, evidence integrity, basic schema/number/candidate controls, and independent source-flag reconciliation.

## Source-flag issuance

`m11_signal_qc.issue_signals(map)` deterministically emits a hash-bound signal inventory from the complete numbered source map, not from the AI's extracted terms, explanations, or open-issue list. Flags comprise:

- Source numeric / written percentages in likely financial contexts; includes local offsets for role disambiguation.
- Whole pipe-table blocks, classified from header and lead-in, not a fixed seven-passage window. Each economic data row gets its own signal; numeric and redacted rate bands can be in either column. A generic 'sublicensee' in a net-sales definition does not imply a sublicensing-receipts table.
- Redacted prose obligations, with adjacent markers of one redacted expression grouped, and distinct clauses kept separate.
- Labelled minimums, caps, upfront / maintenance / issue fees and milestones, including amounts in tables and clauses without 'shall pay'.
- Rate-change adjustments and thresholds, with a separate signal from the base running royalty.

These detections are **not exhaustive**: the regex/table heuristics cannot prove discovery recall. HTML/PDF parsing, clause boundaries, definitions, and unknown phrase forms remain separate risks.

## Evidence resolution contract

Each source signal can close **only** through:

1. `LINKED_RECORD` — a real `ROYALTY_TERM`, `TIER`, `PAYMENT` or `ADJUSTMENT` with a matching source passage and, where applicable, the same amount/rate, calculation family, redaction status, and tier bounds. Redacted terms have null numeric values and explicit `REDACTED` status. A single tier/payment cannot cover two independently issued redacted rows.
2. `TYPED_EXPLANATION` — a narrowly allowed reason that Python checks locally: `AUDIT_THRESHOLD`, `INSURANCE_LIMIT`, `NON_ROYALTY_INTEREST`, `OWNERSHIP_PERCENT`, `STACKING_THRESHOLD`, `REDUCTION_FLOOR`, `INSTALLMENT_COMPONENT`, or `REFERENCE_ONLY`. Reasons requiring a term/payment must link to it. Generic text and HIGH/CRITICAL `open_issues` are **not waivers**.

A source signal still open after a model responds remains open. Any invalid source binding is an integrity failure. An unissued or duplicated signal ID cannot be accepted. If two identical percentages occur in one passage, a single rate record does not silently close both.

## Policy on supporting fees

- **Hard incomplete:** running/sublicensing rates, redacted economic shares, rates and tiers (including their threshold values), minimum/guaranteed royalties, caps, and adjustments.
- **Supporting incomplete:** upfront/issue/maintenance fees, milestones, cost-like payments. They produce warnings and an explicit `INCOMPLETE_SUPPORTING_ECONOMICS` status, **not** a clean PASS.
- Actual source quotes and unresolved errors always remain in the exported research workbook. No approval or human-review columns are required.

This policy prioritizes royalty comparability while still making omission of supporting consideration visible. If you later choose to treat supporting fees as hard fail, change only the source-signal severity policy and rerun tests; do not add an untestable source exemption.

## One targeted correction call

The initial primary full-document model reading remains source-bound. M11 skips M7's separate per-percentage model ledger. Python automatically proposes only unambiguous evidence-to-record matches. If flags remain, `build_correction_packet` produces a single compact task containing only unresolved IDs, their source passages **once per paragraph**, and a compact record summary. It never invokes a model. The correction may add exact-quotation evidence, complete new terms/payments, tiers or adjustments; it cannot change existing facts. A response binds to the exact source/extraction/task hash and produces a new immutable attempt. An empty response is rejected.

If too many flags exist to fit safely in the single-call budget, the packet is explicitly `correction_ready=false` and lists unpresented IDs; the process must **not** silently clear or send a partial subset. Live model and token usage are not measured here.

## Local command sequence (opt-in)

```bash
PYTHONPATH=src python -m royalty_research m8-prepare --map mapped.json --root runs/AGREEMENT-001 \
  --engine claude --model sonnet --qc-profile m11
PYTHONPATH=src python -m royalty_research m8-primary-next --root runs/AGREEMENT-001
# Dry-run is the default; only explicitly execute after account credit controls are checked.
# Repeat authorized one-task calls until all primary tasks have captured responses.
PYTHONPATH=src python -m royalty_research m11-finalize --root runs/AGREEMENT-001
```

`runs/AGREEMENT-001/output/` then contains `final_extraction.json`, `qc.json`, source-flag manifest, CSV files, Excel file (if local spreadsheet dependency installed), and—if needed—`correction_task.json` plus a Sonnet-ready prompt. To import a separately obtained JSON correction response:

```bash
PYTHONPATH=src python -m royalty_research m11-import-correction \
  --root runs/AGREEMENT-001 --response model_response.json
```

The new result is under `correction-01/`; the original `output/` is never overwritten. Existing M8 runs remain on their legacy profile; do not retroactively relabel or edit them.

## What this does NOT establish

- No real Sonnet or Codex inference was performed for M11 in this environment.
- No new five-agreement blind holdout was tested. **All synthetics are development regressions**, and all agreements discussed in the supplied M10 report are now known.
- A correct source-flag ledger is not proof that every contractual payment was detected in the first place.
- Legal meanings such as MARGINAL versus ALL_UNITS, field-of-use, amendments and linked defined terms still require independent full-document re-keying and measured benchmark evidence.
- A future Fable test must evaluate both false-negative omissions and false-positive refusals in newly frozen contracts, not merely whether known regressions pass.
