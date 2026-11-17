# M4 Mac operations — subscription CLI, no model API

**Release:** v0.4.0 (development, offline tested). **No automatic bulk extraction.** The runner executes at most **one** user-authorized model task per invocation. No subscription model was actually called during these tests.

## 0. Account controls BEFORE live work

1. Use a personal/local project containing **public SEC materials only**. Do not mix confidential client files. Keep `~/royalty-research` outside client work repositories.
2. Update the official Claude Code and Codex CLIs. Log in interactively via the subscription accounts. Check `claude auth status` and `codex login status` or the current CLI's equivalent; CLI flags may change. **Do not use API-key authentication.**
3. Check account-level purchases, available credits, auto-reload, and subscription usage. A CLI runner cannot prove that available purchased credits will not be consumed. **Even with ChatGPT sign-in, credit-funded usage may occur when plan allowances are exhausted.** If zero additional spend is required, verify settings/credit balances externally and do not run if unsure.
4. Remove API keys, custom API endpoints, Bedrock/Vertex proxy flags from the CLI environment. The runner fails closed on common relevant environment variables, but cannot inspect stored credentials or guarantee billing.
5. The SEC requires a descriptive User-Agent for network commands. Stay within SEC access policies, monitor 403/429, and do not treat blocking as evidence of a missing exhibit.

Official references (verify on the day of use):
- `https://code.claude.com/docs/en/cli-reference`
- `https://learn.chatgpt.com/docs/cli/reference`
- `https://help.openai.com/en/articles/12642688-using-credits-for-flexible-usage-in-chatgpt-personal-plans`
- `https://www.sec.gov/os/accessing-edgar-data`

## 1. Installation / preflight (no models)

From the extracted top-level `royalty_research_m4` directory:

```bash
python3 --version
PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONPATH=src python3 -m royalty_research --version
```

Python >=3.10. M1/M2/M3 operate without LLM APIs. PDF parsing needs optional `pypdf`. The existing M3 Excel exporter depends on `artifact_tool`; availability on the Mac is **unverified**. CSV export is a fallback, not the required final Excel deliverable. Resolve Excel dependency during the pilot.

## 2. Map a document and prepare FULL reading packets

For an *offline* source file obtained from an official SEC exhibit:

```bash
mkdir -p work/demo
PYTHONPATH=src python3 -m royalty_research map \
  --input tests/fixtures/synthetic_licence.html \
  --document-id DOC-DEMONSTRATION \
  --out work/demo/map.json
PYTHONPATH=src python3 -m royalty_research validate-map --input work/demo/map.json
PYTHONPATH=src python3 -m royalty_research make-packets \
  --map work/demo/map.json --mode full --max-chars 16000 \
  --out work/demo/full_packet.json
```

This demonstration uses fictional fixture text. For a real SEC document, `map --url ... --user-agent 'Project Name research@example.com' --out ...` retrieves an allowlisted SEC exhibit temporarily and retains a mapped text/evidence inventory. Never insert fabricated contact details into a real SEC call.

**Long source lines:** M4 splits original normalized text into <=12,000-character fragments by default (`map --segment-chars 12000`), preserving an exact reconstruction manifest. Adjacent fragments must be interpreted together. Forced cuts inside an unbroken token block automatic deterministic approval. If a packet still exceeds the bound, remap with `--segment-chars` smaller than your packet budget; no text may be truncated.

## 3. Immutable plan: NO inference on creation

Use ONE plan for the primary reader, with the model currently accessible to your subscription:

```bash
PYTHONPATH=src python3 -m royalty_research m4-plan \
  --map work/demo/map.json \
  --packet work/demo/full_packet.json \
  --engine claude --model sonnet \
  --outdir work/demo/claude_plan

PYTHONPATH=src python3 -m royalty_research m4-status --plan work/demo/claude_plan
PYTHONPATH=src python3 -m royalty_research m4-run-next --plan work/demo/claude_plan
```

The final command is a **dry run**. It shows the next pending task but makes no model call.

For Codex: prepare a **separate** plan using `--engine codex --model <your-available-model>`. Do not assume model names or subscription availability; verify locally. Blind independent review must use a separate prompt/plan and must not see the primary extraction answer.

## 4. Execute exactly ONE subscription CLI chunk, by explicit opt-in

Only after external subscription/billing verification:

```bash
PYTHONPATH=src python3 -m royalty_research m4-run-next \
  --plan work/demo/claude_plan \
  --execute --confirm-subscription --confirm-credit-controls \
  --timeout 900
```

**One call, then stop.** Review `m4-status` and inspect the raw result. Invoke again manually for the next chunk. No automatic retry and no forced continuation after a usage-limit signal. `--tools '' --strict-mcp-config` disables Claude tools and loaded MCP integrations. Codex runs in a read-only sandbox from a neutral temporary directory; contract text is passed through standard input.

`CAPTURED_NOT_QC_APPROVED` is **not** validated extraction, not proof the model read everything, not a completed agreement, and not permission to publish. A model-generated claim of full reading is not independently verifiable.

## 5. Failure, interrupted call, quota/credits

- Failed or malformed output remains an immutable attempted run. Subsequent automatic invocations will **refuse** to retry.
- After diagnosing the problem, manually allow a retry:

```bash
PYTHONPATH=src python3 -m royalty_research m4-authorize-retry \
  --plan work/demo/claude_plan --task-id CHUNK-0001 \
  --reason 'Reviewed failed response and corrected environment'
```

- If a recorded result exists but its receipt is missing after a crash, use `m4-recover-result --plan ... --task-id ... --confirm-recovery`. Source, task, and original run IDs must match; recovery does not certify extraction quality.
- If the runner recorded `limit_stop.json`, **verify** subscription reset and billing controls externally before `m4-clear-limit --reason '...'`. An exit error may have consumed subscription usage already. Do not run into limits repeatedly.
- The same source/plan can be resumed after process restarts. The code refuses stale or altered maps, prompts, receipts, and unaccounted chunks.

## 6. Merge and validate — all chunks required

After all tasks have captured JSON:

```bash
PYTHONPATH=src python3 -m royalty_research m4-merge-plan --plan work/demo/claude_plan
```

Creates `merged_extraction.json` and `merged_validation.json`. A failed deterministic QC yields nonzero exit and **cannot enter the reviewed Excel sheet**. Cross-chunk royalties, amendments, semantic meaning, and unflagged missed clauses still need independent checks.

For M3 registration/export, follow `docs/M3_OPERATIONS.md`. Never record a human review or approved agreement linkage without actually doing the underlying review.

## 7. Resource budgeting

Track per agreement: number of packet chunks, input prompt bytes, attempted calls, failures/retries, output validity, M3 deterministic errors, independent QC, and actual agent subscription usage from the local usage dashboard. No measured agreements/day or token throughput exists yet. Stop after a small, supervised Mac pilot; don't launch a 2021–2025 bulk search before the acceptance gates.
