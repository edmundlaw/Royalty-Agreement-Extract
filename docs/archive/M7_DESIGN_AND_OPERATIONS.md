# M7 v0.7.0 — Source-issued occurrences, triage, subscription efficiency, no human approval

## Authoritative workflow (supersedes M1–M6 human-approval instructions)

M7 is **not** a SaaS/database service. It is an offline Python package for locally held SEC source maps, subscription-based Codex/Claude Code reading, stringent automatic QC and Excel output. Original source files are not required to be permanently archived, but direct SEC URLs, exact quotations, source hashes and candidate histories remain in the research files.

**Human approval is removed.** No reviewer sign-off, acceptance form, human approval queue or 'Human Reviewed' Excel sheet exists in the M7 active workflow. Every selected extraction appears in the Excel **including QC failures**; each has its own state. Automated QC PASS does not mean completeness or professional verification. Professional point-of-use reading, if someone later chooses it, is entirely outside this tool and not reported back to AI.

## Major M7 changes

1. **Python-issued occurrence IDs:** `m7_occurrences.py` enumerates every source-observed numeric percent, currency amount, redaction, written-fraction signal, per-unit phrase and indirect payment signal across **all mapped passages**, including passages Python did not initially flag. Each occurrence has an immutable ID derived from source passage, type, offset and literal. Every source ID must be classified exactly once. An invalid, missing, duplicated or invented ID blocks M7 QC. These are expressions, not proof of economic obligations.
2. **Source-risk check:** high-risk source percentages/minimums/redactions and contextual written-rate/indirect-payment signals cannot be dismissed merely by the model saying `UNRELATED`; they need linked economics or an explicit unresolved issue. Rate classifications must link to the right term and quoted evidence. M6's separate source-risk gate remains active.
3. **Relevance triage:** `m7_triage.py` ranks evidence-rich IP licensing, ambiguous contract and incidental/mineral interest candidates before expensive agent calls. **No document is automatically discarded** by this heuristic. A document scored low remains in the immutable source inventory until separately screened. No relevance recall estimate exists yet.
4. **Complementary reading packs:** focused source passages prioritize royalty obligations, neighboring text, definitions and deterministic unflagged samples. A separately issued remainder pack contains **every excluded passage**. Both share the same source manifest and their union exactly equals the original mapped source. Focus reading alone cannot claim completeness.
5. **Compact correction calls:** an already completed first AI extraction is followed by small occurrence-classification tasks (`m7_ledger_tasks.py`). This lets Sonnet correct occurrence bookkeeping **without repeating full-document extraction**. Unresolved occurrences automatically create source-bound machine-only `HIGH` QC issues when the ledger is attached; they are not human approvals and remain visible in Excel. Every task and model result is bound to the exact original extraction hash, original source hash, task hash and occurrence manifest.
6. **No human sign-off gate:** the former active `m3-human-review` command has been removed and old reviewer recording is disabled. The exporter emits **14 research/QC sheets**, no human-status fields and no `Human Reviewed` sheet.
7. **Prompt compacting:** the existing M4 subscription CLI now serializes unchanged source JSON compactly instead of repeating 2-space indented JSON. To reduce repeated schema/context overhead, benchmarking a larger `make-packets --max-chars 64000` against 16000 is recommended for agreements that fit; this is not yet validated by live Sonnet/Codex extraction.

## Reproducible commands (Python 3.10+; project directory)

```bash
export PYTHONPATH=src

# Existing authoritative normalized M1 source map is input. No inference/SEC calls.
python -m royalty_research m7-prepare --map source_map.json --outdir work/doc1_m7

# Inspect triage, M7 source manifest and focus/remainder packs. Neither pack is a complete extraction.
# For an unchanged M4 first-reader path, make the M2 source packet from the enriched M7 map:
python -m royalty_research make-packets --map work/doc1_m7/m7_map.json --mode selected --max-chars 64000 --out work/doc1_packet.json

# Create M4 CLI plan using subscription sign-in (the first output will not yet pass final M7 strict QC).
python -m royalty_research m4-plan --map work/doc1_m7/m7_map.json --packet work/doc1_packet.json --outdir work/doc1_plan --engine claude --model sonnet
# m4-run-next is a DRY RUN unless the user explicitly opts in and confirms billing controls.
# After capturing and merging all chunks, save the raw original M2 extraction as work/doc1_raw.json.

# Rather than re-running the full model, issue bounded occurrence-review tasks for Sonnet:
python -m royalty_research m7-ledger-tasks --map work/doc1_m7/m7_map.json --extraction work/doc1_raw.json --outdir work/doc1_occ_tasks
# Read prompts/M7_OCCURRENCE_READER.md and send each task to a subscription-signed-in coding agent.
# Save each answer as an immutable JSON response, e.g. response_0001.json.

# In a real case repeat --task and --response for every chunk (one response per issued task).
python -m royalty_research m7-merge-ledger --map work/doc1_m7/m7_map.json --extraction work/doc1_raw.json --task work/doc1_occ_tasks/ledger_task_0001.json --response response_0001.json --out work/doc1_ledger.json
python -m royalty_research m7-attach-ledger --map work/doc1_m7/m7_map.json --extraction work/doc1_raw.json --ledger work/doc1_ledger.json --out work/doc1_final.json
python -m royalty_research m7-validate --map work/doc1_m7/m7_map.json --extraction work/doc1_final.json --out work/doc1_qc.json

# The M3 workspace and Excel export are automatic (NO human review required).
python -m royalty_research m3-init --workspace workspace
python -m royalty_research m3-register-map --workspace workspace --map work/doc1_m7/m7_map.json
python -m royalty_research m3-ingest --workspace workspace --document-id DOC_ID --extraction work/doc1_final.json --select
python -m royalty_research m3-export --workspace workspace --outdir output --format both
```

**Important:** The existing M4 `m4-merge-plan` is expected to produce `FAIL` under a strict M7 map before occurrence classifications are attached. It still preserves the raw merged extraction and validation report; this is the intended two-stage workflow. Do not interpret intermediate FAIL as an erased result or force old M6 QC to PASS.

## Critical limits still requiring independent validation

- A source occurrence inventory does **not** prove full-document recall, legal interpretation or that a numerical expression was assigned to the correct economic clause. Written rates and non-numeric schedules can still be missed.
- Full contract / amendment chains, PDFs, zero-rate licence fees and unusual nested tables are not yet benchmarked end-to-end with M7.
- Relevance triage's observed distribution is **not** an accuracy/recall estimate and must not be used to automatically discard any candidate without a separately tested screening rule.
- Subscription-model usage savings are **not measured**; only source-character and prompt-character differences are observed offline.
- No new real Claude/Codex model calls or live SEC requests were made during M7; Fable's 80 saved SEC maps were reused for triage analysis.
- Older M6 workspaces must be revalidated/ingested into a **new versioned workspace**; an older QC certificate cannot be silently carried forward.
- Any legacy M3/M4/M5 documents mentioning human approval are historical design records. This M7 document is authoritative for the current operational workflow.

## Fable's recommended independent checks

1. Confirm the new M7 `m7-prepare` output inventories and focus/remainder union against real SEC contracts and the 80-map sample.
2. Run 25 diverse contracts with independently prepared complete-source answers; measure term-level omissions, term-basis interpretation, wrong rate tiers, minimums, caps, redactions and excluded clauses. No user-entered approvals need to be recorded.
3. Compare real subscription usage and extraction accuracy for one-call 64k packets, old 16k packets and the focused + remainder strategy. Do not confuse fewer source characters with fewer *actual paid-plan usage units*.
4. Attack the source-issued ledger with identical percentages in different roles, excluded high-risk obligations, unknown rates, stale response hashes and duplicated occurrence IDs.
5. Recheck live SEC / PDF parsing and amendments. Do not bulk process 2021–2025 before these tests.
