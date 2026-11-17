# M4 technical decisions, residual risks and implementation boundaries

## Completed

- **Oversized lines:** Source normalization remains M1 parsing. Long *normalized lines* are split in M1 mapping at an adjustable bound (default 12,000 chars), preserving parent-line hash, lengths and contiguous source spans. Every fragment has `SOURCE_SPLIT_ADJACENCY_REVIEW`. Reconstruct fragments by concatenation; inserted M1 passage separators are *mapping metadata*, not asserted to occur in the original line. Forced within-token boundaries are a deterministic QC failure. For semantic reconstruction always inspect neighboring fragments and linked definitions. This does not repair extraction errors arising before mapping.
- **Immutable task plan:** A plan contains full source map, packet, numbered passage IDs, output prompts, source/prompt digests, engine/model, and task ordering. Edits to source map, packet or prompt are rejected on resume. Plan creation is not model inference.
- **Manual one-call execution:** `m4-run-next` is DRY by default. Live calls require execute + subscription + credit-control acknowledgements. One model call per invocation; fresh `run_id`, serialized prompt, neutral temporary cwd, Claude tools disabled / Codex read-only sandbox, CLI stdout/stderr and status recorded. No API inference.
- **Fail-closed:** Wrong source hash, passage ID, engine/model/run ID, malformed JSON, nonzero CLI status, quota/billing signal or timeout results in a failed attempt. No model output is silently promoted to QC-PASS; explicit manual retry and reset handling are required.
- **Crash recovery:** An interrupted attempt remains visible. If result JSON was persisted before its receipt, it can be re-bound by explicit recovery to the original run. No automatic replay of potentially chargeable calls.
- **Downstream QC:** `m4-merge-plan` requires every chunk, runs M3 merge and M2 deterministic validation, and records a separate review report. This can still miss substantive errors or incomplete contract reading; M3's manually attested human view remains a separate gate.

## Explicit limitations — not solved by passing offline tests

1. **No live subscription calls were made** in this environment. Fake CLI scripts test only command wiring, file contracts, restart and error branches, not actual Claude/Codex answer quality, session caps or billing.
2. **No direct SEC integration run was performed.** Discovery yield, official SEC pagination / throttling, filing-inventory recall, PDF/HTML fidelity and historical throughput need live Mac validation.
3. **No guarantee of zero paid-credit use.** ChatGPT subscription sign-in can use credits if present after allowances; a script cannot enforce account billing settings or detect every config-based API credential. User must verify externally before clicking `--execute`.
4. **No automatic robust semantic cross-chunk inference.** Contracts whose conditions, tiers or definitions span assigned chunks need secondary review. Full packet coverage means text was supplied, *not* actually read by AI.
5. **No measured extraction precision/recall.** 116 offline tests are mostly fictional/deterministic engineering checks, including mock noninteractive model binaries. Model performance must be assessed against independently human-checked original contracts, with uncertainty by type.
6. **Source retention:** The local plan contains normalized document text (not a permanent original HTML/PDF). Keep it through verification, then decide retention/deletion based on evidence-reproducibility needs. SEC links and excerpts alone are not a permanent source archive.
7. **Review provenance:** Local JSON digests protect against accidental mismatch, not malicious users who could edit both content and hash/receipt. A local human attestation is not authenticated professional sign-off.
8. **Mac dependency:** `artifact_tool` availability for M3 Excel export must be independently checked. No hosted server or paid inference API is used.
9. **Model prompt errors remain:** A compliant-looking JSON result may still misinterpret net-sales definitions, marginal tiers, stepdowns or amendatory status. Quotation/number matching is necessary but not sufficient.
10. **Scope is not mass extraction:** A supervised M4 pilot should precede any scheduling and bulk 2021–2025 processing.
