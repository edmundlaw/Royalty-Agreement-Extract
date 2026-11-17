# Independent Fable review — M5 v0.5.0

**Scope:** Review the complete M1–M5 source ZIP as an implementation candidate. Do not give it production approval on the basis of 138 synthetic/offline tests.

## First replay (offline; zero LLM calls)

1. Extract the ZIP into a standalone project folder outside confidential client repositories.
2. Install package in a local Python virtual environment: `python -m pip install -e .`.
3. Run `python -m unittest discover -s tests -q`. Require **138** passes.
4. Run `royalty-research m5-probe-manifest --fixtures tests/fixtures/m5 --manifest tests/fixtures/m5/anchor_manifest.json --out /tmp/m5-probe.json`. Expect 3 records, 14 anchors and explicit non-validation of contract recall.
5. Inspect `m2_validation.py` and attempt to bypass the UNKNOWN/UNCERTAIN source-passage issue gate. A resolved or LOW issue must not suffice.

## Second replay (real SEC source, controlled)

Use a declared contact User-Agent, respect SEC rate limits and do not attempt to bypass rate blocks. Download locally the complete exhibits below, including tables and schedules, and run the normal M1 `map` command on the **originals**. The mapping output must retain all key economics; do not substitute the paraphrased test fixtures.

- Market Finders: https://www.sec.gov/Archives/edgar/data/1520358/000149315213000675/ex10-2.htm
  - Check the 6/4/2/1 sales tier schedule and thresholds, annual minimum royalties, conditional $200k cap, .5% late interest, 5% audit shortfall and 40% gross-margin clause.
- UC / NeurogesX: https://www.sec.gov/Archives/edgar/data/1385830/000119312507022650/dex106.htm
  - Check 1% sales royalty, $1m annual cap, 25/10/5 sublicense tier table and thresholds, additional 25% cap, 11% third-party stacking and non-royalty equity percentage.

This is **not** the 25-case benchmark. It is an initial real-file ingestion smoke test. Dates of original exhibits predate the 2021–25 filing cohort; they are regression cases, not the historical population estimate.

## Third replay (model subscription)

1. Confirm local Claude Code and Codex CLI version, subscription login and purchased-credit controls. Do not infer billing eligibility from absent API-key variables alone.
2. Run at least one *fictional* and two independently annotated real extracts per engine; capture usage, model label, actual read scope and prompt hashes.
3. Specifically check if the 25/10/5 UC sublicense terms and 1% running rate are separately extracted. Check whether the nonroyalty percentages are excluded; never accept tier labels without matching calculation bases/thresholds.
4. Deliberately interrupt one CLI task and verify manual recovery without duplicate model calls or stale results. Check outcome when model returns invalid JSON or a limit message.
5. Independently read unflagged source sections and compare with detected candidates. Model agreement is not evidence of complete recall.

## Fourth replay (ground-truth readiness)

Use 25 genuinely human-verified development agreements, then a **separate, locked** holdout (candidate: 60 stratified agreements, but do not claim population-wide 95% recall without suitable sampling and interval logic). Establish manual annotation for every royalty, sublicensing, rate reduction, cap, minimum, milestone and cross-reference on entire contracts. Do not publish any accuracy figure from current M5 fixtures.

## Report back

For each failure: severity, exact command, filename, minimal original source quotation or clause reference, expected vs actual, whether it affects omission/incorrect classification, root cause, change required, and evidence of retest. Record actual SEC responses, CLI versions, model names, account mode without credentials, daily usage and any billing exposure.
