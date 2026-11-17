# Lean royalty research (v0.13.4)

This is a separate, model-neutral path. It makes **no AI calls** and does not require Claude or Codex. Python selects likely royalty passages with neighboring text; an AI you choose fills a short JSON template. Python then checks quoted values against selected source text and produces the familiar five-sheet research workbook. The original M13 full-reading/QC path remains available.

## Run

From this directory, with Python 3.10+ (and `openpyxl` for Excel):

```sh
PYTHONPATH=src python3 scripts/lean_research.py screen --input /path/to/agreement.html --source-url https://www.sec.gov/Archives/edgar/data/... --out /path/to/lean-run
```

For an official SEC URL, use `--url https://www.sec.gov/Archives/edgar/data/... --user-agent 'Name email@example.com'` instead of `--input`. Live SEC access is the only network action; no AI service is invoked. Local inputs can be text, HTML, or PDF with the existing parser (PDF requires `pypdf`). An output directory must be new.

To screen a directory of downloaded candidate exhibits without any AI calls:

```sh
PYTHONPATH=src python3 scripts/lean_research.py batch --input-dir /path/to/exhibits --out /path/to/lean-batch
```

Or pass `--candidates /path/to/discover.jsonl --user-agent "Name email@example.com"` to fetch the SEC hits from the existing `discover` command. `index.json` lists every candidate, including low-signal and fetch-error items. Only `READY_FOR_AI` folders need to be sent to your AI by default; retain the rest for review or sampling. A low-signal label is not an irrelevant-contract finding.

Give your chosen AI **only** `lean-run/packet.txt`, `lean-run/PROMPT.md`, and `lean-run/summary_template.json`. Ask it to return the filled JSON. It need not receive the code or full contract. It may run this script itself if it has local Python/file access; otherwise run the screener locally and upload the three small files. Save its response as `summary.json`, then:

```sh
PYTHONPATH=src python3 scripts/lean_research.py validate --packet-dir /path/to/lean-run --summary /path/to/summary.json
PYTHONPATH=src python3 scripts/lean_research.py export --packet-dir /path/to/lean-run --summary /path/to/summary.json --out /path/to/Lean_Royalty_Research.xlsx
```

The output workbook uses the five M13 research-sheet names and style. Empty categories display `NOT_ASSESSED`, not zero. It records rates, payments and quotes without summing them. Some technical columns remain blank because lean mode does not perform full extraction or two-reader QC.

## Cost and coverage

The default packet budget is 30,000 characters, adjustable with `--max-packet-chars`. Python scores IP, royalty, obligation and numerical language and includes a neighboring passage around strong signals. `screening.json` records total, selected, included and budget-omitted passages. Low-signal documents are marked `LOW_SIGNAL_OR_BUDGET_EMPTY_REVIEW_BEFORE_DISCARD`; this is **not** proof of irrelevance. A full contract may contain royalty terms outside the packet. `passages.json` is retained locally for validation; do not upload it unless needed.

The source check verifies that each reported rate/payment value is in its short quote and that the quote is verbatim in the cited selected passage. Agreement fields also need a cited verbatim quote in `agreement_evidence`. This is a mechanical check, not verification of legal interpretation or completeness. Contract-level precision/recall are **NOT MEASURED**. Review source agreements before using any resulting rate for valuation.
