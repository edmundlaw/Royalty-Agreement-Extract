# Historical backfill (2001–2026) — run copies

Snapshot of the scripts that built the six Harvey batches (2001–2003 … 2024–2026).
They were run from their output folder (`outputs/royalty-history-keep-review.*/`),
which they treat as `ROOT`, with `cwd` = `m13` and `PYTHONPATH=src`.

- `backfill.py` — monthly SEC discovery + frozen screen into checkpoint ZIPs; `combine()`
  packages final KEEP/REVIEW only (oversized-only SKIPs stay SKIP), writes
  `00_SEC_SOURCE_MAP.csv` per month and `_admin/Unavailable_sources.json`.
- `deliver_batches.py` — waits for each date range's checkpoints, packages and sends it.
- `repackage.py` — rebuilds delivered batches from saved checkpoints with the current rule;
  no SEC requests, no email. `--apply` swaps the clean ZIP into the batch and hosted copies.

The email/hosting scripts (`send.py`, `send_batch.py`) are not included because they hold
personal addresses; they stay in the output folder.

Harvey prompt used on the batches: `docs/Harvey_Review_Table_prompt_v8_standard.md`.
Harvey export filenames drop `__`; match rows to the source map by removing all `_`
(SEC URL = `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession>/<file>`).
