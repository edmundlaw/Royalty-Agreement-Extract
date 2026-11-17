# Independent Fable review: M9 v0.9.0

Review the M9 changes independently against the user-supplied v0.8.1-review, without relying on GPT's interpretation of what passed.

## First: offline verification

```bash
cd ~/royalty-research/royalty_research_m9
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[xlsx,pdf]'
python -m unittest discover -s tests -q
```

If the archived directory has a different name, use that directory instead. No inference is invoked by this test suite. Verify the release manifest, if supplied, before running.

## Replay your three saved Sonnet cases, read-only

```bash
python scripts/replay_m9_review.py \
  --work-root ~/royalty-research/m8test/work \
  --out ~/royalty-research/review_log/M9_saved_replay.json
```

This replay reads the M8 source maps and saved Sonnet extraction JSON; it does **not** reread the originals from SEC, call Claude/Codex, consume tokens, or overwrite the saved attempt. It should show 0 new deterministic QC errors for each of the three cases, while preserving warnings/open issues.

Investigate whether any true material defects have been reclassified from errors to warnings. Pay particular attention to royalty-basis support, the independent source context logic, and any suspicious conditions passed without linked evidence.

## Adversarial checks

1. On NeurogesX, jointly remove the entire sublicense schedule and rewrite the ledger dispositions as non-royalty. Verify the M9 source gate still rejects 25/10/5.
2. Remove one row, swap two tiers, change the family and change the threshold. Verify all produce source-grounded failures.
3. Remove the annual dollar cap and the 25%-of-revenue limit, together with their payment/condition records. Both must fail.
4. Use **at least five unseen agreements** of differing contract formats to estimate false-positive and false-negative behavior. Full-document verification is needed; do not count old model outputs as gold answers.
5. Confirm the new guard only accepts actual subscription-mode CLI authentication and never silently falls back to API authentication. Check `--safe-mode` and `--ignore-user-config` against the CLI versions actually installed.
6. Test successful model JSON containing the text `rate limit reached`, failed CLI quota messages, and fenced JSON without spending real model calls.

## What is deliberately NOT changed

- No human approval, reviewer status, or approval requirement is added. All extracted records, including failed checks, remain available for research Excel export.
- The historical full-contract benchmark and SEC 2021–2025 bulk run are not conducted.
- This release does not claim an independent recall percentage, successful live M9 CLI inference, guaranteed zero credits, or token-efficiency gains.

## Report back

Provide a prioritized defect register with reproducible clause IDs, input fingerprints, expected vs actual results, and exact test/CLI version. Escalate semantic changes and security issues to a high-reasoning reviewer; delegate ordinary regression execution and documentation inspection to Sonnet where economical. Preserve the M9 ZIP unchanged.
