# M13 v0.13.0 — test report

Built and tested by Claude (Fable 5.2) on 2026-11-15 and 2026-11-16, on the same Mac and workspace as the earlier reviews (`~/royalty-research/`). First reader in live tests: Sonnet (`claude-sonnet-5-5`, Claude Code 2.1.325, `authMethod claude.ai`). Second reader: Codex (`gpt-6-sol`, codex-cli 0.169.0, "Logged in using ChatGPT"). No API-key variable was set. No usage-limit or billing signal came back from any tool call.

This is the builder's own test report. It has not been reviewed by anyone else.

## Summary

| Question | Result |
|---|---|
| Offline tests | 316 pass (287 from M12 unchanged, 29 new) |
| Do correct readings pass the source check? | 9 of 9 saved Sonnet readings, 10 of 10 Codex readings, 2 of 2 fresh Sonnet readings: 0 errors. Under the rules as first written, 2 of these 21 failed (see "Changes made after seeing results") |
| Does the source check catch a wrong number or quote? | 288 of 288 deliberate changes |
| Do two models agree when both are right? | 10 pairs: 5 agree, 4 agree on numbers, 1 differs (a totals line; a mild false alarm). No other core difference |
| Would the other model expose an omission? | 124 deleted core records on 8 pairs: 110 core, 11 structure, 3 nothing (duplicates) |
| Does the second reader stay optional? | Yes. Single reading exports as `SINGLE_READER_NOT_CHECKED`; a check can be added later and writes `output_checked/` |
| Measured precision or recall | None. Not yet run |

## 1. Source check

**Saved correct readings.** `tools/replay_m13.py` on the nine Sonnet readings that the M8 to M12 reviews judged correct against the source (Market Finders, NeurogesX, Immersion, Qualigen, Kirkland's, Equillium, KemPharm, Genprex, Pieris): 0 errors each. Under M12 QC the same readings carried 0, 0, 2, 0, 0, 10, 31, 5 and 5 hard flags.

**Deliberate corruption.** `tools/sweep_m13.py` on the same nine readings: 6 term rates, 9 tier rates, 14 thresholds, 34 payment amounts and 225 quotations were each changed in turn. All 288 raised a source-check error.

## 2. Sonnet versus Codex on the same agreement

Eight agreements: the saved Sonnet reading compared with a new Codex reading made through `m13-next` (`tools/compare_all_m13.py`). Two agreements: read fresh by both models through the full M13 flow.

| Agreement | How run | State | Numbers both recorded | Core | Structure | Note |
|---|---|---|---|---|---|---|
| Market Finders | saved Sonnet + new Codex | TWO_READERS_AGREE | 16 | 0 | 0 | 1 |
| Kirkland's | saved Sonnet + new Codex | TWO_READERS_AGREE | 7 | 0 | 0 | 0 |
| Pieris | saved Sonnet + new Codex | TWO_READERS_AGREE | 11 | 0 | 0 | 0 |
| Equillium | saved Sonnet + new Codex | TWO_READERS_AGREE | 10 | 0 | 0 | 1 |
| KemPharm | saved Sonnet + new Codex | TWO_READERS_AGREE | 26 | 0 | 0 | 0 |
| NeurogesX | saved Sonnet + new Codex | TWO_READERS_AGREE_ON_NUMBERS | 20 | 0 | 2 | 1 |
| Qualigen | saved Sonnet + new Codex | TWO_READERS_AGREE_ON_NUMBERS | 6 | 0 | 1 | 0 |
| Genprex | saved Sonnet + new Codex | TWO_READERS_AGREE_ON_NUMBERS | 19 | 0 | 1 | 3 |
| FunctionalBrands / Trailer Park Boys | fresh, both models, full flow | TWO_READERS_DIFFER | 27 | 1 | 0 | 6 |
| Himalaya / InsureTEK | fresh, both models, full flow, rules frozen | TWO_READERS_AGREE_ON_NUMBERS | 2 | 0 | 1 | 4 |

The two fresh agreements had not been read by any model before. Both were cases on which M12 raised false hard flags (FunctionalBrands: "0.3% THC", "100% of the gross amount", 12% interest; Himalaya: an equity grant, 4 flags).

**FunctionalBrands (38,636 characters).** Both readers recorded the same six royalty rates (30%, 30%, 20%, 30%, 30%, 20%) and the same advances. Checked against the source: section 5 gives a Standard Royalty Rate of thirty percent (30%) of Net Sales and a DTC rate of thirty percent (30%); section 4 lists guarantees of $50,000, 600,000 shares and $150,000, with a line "Total cash | $200,000.00". The one CORE difference is that total line: Sonnet recorded it as a minimum royalty of 200,000; Codex recorded the components and gave the total line the disposition DUPLICATE. Both readings are right; the difference is a mild false alarm. It was left as CORE so that the result of this run was not tuned.

**Himalaya (36,825 characters).** Both readers recorded one royalty of 10% of Gross Revenue and neither treated the share percentages (5%, 2.5%) as royalty rates. STRUCTURE: Sonnet made a record for a "Minimum Royalty" that the agreement mentions without an amount; Codex noticed the clause and made no record. NOTE: Sonnet recorded the share grants as three payments and the options as one; Codex as one text record each.

## 3. Would the other model expose an omission?

`tools/omission_pairs_m13.py` on the eight saved-plus-Codex pairs. For each royalty term with a rate, tiers or a redacted rate, each tier, and each minimum or cap held by one reader, the record was deleted from that reader together with its evidence, its clauses were marked BACKGROUND, and the result was compared with the other model's untouched reading.

| Outcome | Count | What it means |
|---|---|---|
| New CORE difference | 110 | The omission is flagged |
| New STRUCTURE difference | 11 | The clause is still held in another record of the same reader (for example a cap also written as a condition, a pass-through minimum in the same clause as the pass-through royalty) |
| Nothing new | 3 | The deleted record duplicated a number the same reader held elsewhere (a tier equal to the term's own rate; a cap recorded twice) |

This test shows that the comparison notices a missing record when the other model has it. It does not show how often both models miss the same term; that needs the benchmark.

## 4. Pipeline and workbook

- `tests/test_m13.py` runs the full flow offline with a fake CLI: single reading, check added later, a second reader that omits a tier, export without a finished check, tamper detection on the run record, refusal to overwrite, and the combined workbook.
- Live: 20 reading calls went through `m13-next` (4 Sonnet, 16 Codex). All 20 were captured at the first attempt. The M4 sign-in preflight ran before each.
- Workbook of the FunctionalBrands run opened with openpyxl: 16 sheets, Overview / Reader Check / Reader Differences first; `QC_State` on term rows holds the state; Licensor and Licensee are filled on term rows.

## 5. Changes made after seeing results

These are listed so the figures above are read correctly. Each is covered by a test in `tests/test_m13.py`.

| # | Seen on | Change |
|---|---|---|
| 1 | Sweep on saved readings | Records without a number are paired like with like before anything else, so the result does not depend on record order |
| 2 | Qualigen pair | A record without a number that is not a redaction is a STRUCTURE difference when the other reader also treated the clause as economic |
| 3 | Pieris pair | "Fifty Million Dollars ($[***])" is read as 50,000,000 |
| 4 | KemPharm pair (Codex) | A quotation that differs from the passage only in letter case, spacing or quote marks is a warning. Under the first rule this Codex reading failed the source check |
| 5 | Genprex pair | "The other reader noticed the clause" includes the dispositions UNCERTAIN, CROSS_REFERENCE and REDACTED |
| 6 | NeurogesX pair (Codex) | A bound written "250000 exclusive" is read as 250,000 |
| 7 | Genprex pair (Codex) | A rate with unit FORMULA ("2 x the otherwise applicable rate") is not read as 2% |
| 8 | FunctionalBrands fresh run (Sonnet) | For fees and other payments, a number that is in the cited passage but outside the quoted words is a warning. Rates, thresholds, minimums and caps must still be inside the quotation. Under the first rule this Sonnet reading failed the source check |

Changes 1 to 7 were made while the eight saved-plus-Codex pairs were being run, so those eight are development cases. Change 8 was made after the first fresh run. The second fresh run (Himalaya) was made and assessed with no change afterwards. One clean run is not a holdout.

## 6. Tokens and calls

| Agreement | Characters | Sonnet calls | Sonnet tokens | Codex calls | Codex tokens |
|---|---|---|---|---|---|
| FunctionalBrands | 38,636 | 2 | 94,409 | 2 | 61,261 |
| Himalaya | 36,825 | 2 | 85,120 | 2 | 52,722 |
| Eight Codex-only readings | 7,916 to 51,204 | 0 | 0 | 12 | 327,074 |

Sonnet used about 2.4 tokens per source character and Codex about 1.4 (Codex figures are the "tokens used" line of the CLI). A two-reader agreement of about 38,000 characters therefore costs about 90,000 tokens on the Claude plan and about 57,000 on the ChatGPT plan, in four commands or one with `--all`. There is no ledger step and no correction call.

## 7. Known weaknesses

1. **A totals or summary line recorded by one reader only is flagged CORE** (FunctionalBrands). A reader's DUPLICATE disposition could be used to downgrade it. Not changed; decide with benchmark data.
2. **Shared blind spots are not measured.** Both readers get the same prompt and the same task boundaries.
3. **Base, territory, term and exclusivity are not compared.** A changed royalty base passes both the source check and the comparison unless the family changes.
4. **STRUCTURE can hide a weak reading.** A reader that notices a clause but records nothing produces STRUCTURE, not CORE, when the other reader's record has no number.
5. **Term inflation is unchanged.** Sonnet still records ancillary clauses as extra terms (Genprex 7 terms for 3 royalties). The comparison tolerates it; the workbook rows still show it.
6. **The workbook layout is GPT's**, with three sheets added. It has not been restyled.
7. **One reader's rows only.** When the readers differ, the workbook shows the first reader's rows and lists the difference; nothing is corrected automatically.

## 8. Not tested

A long agreement (over 64,000 characters, several tasks per reader) through M13; PDF or scanned exhibits; an amendment chain; a live usage limit; Codex as first reader with Sonnet as check; `m13-add-check` on a live run (offline test only); `m13-combine` on live runs (offline test only); the 25-agreement benchmark; any precision or recall figure. Account-level extra-usage and auto-reload settings cannot be seen from this Mac.

## 9. Recommended next steps

1. Run the 25-agreement development benchmark with both readers and count: source-check failures, states, CORE rows that are false alarms, and (against a hand-checked reference for a subset) terms both readers missed.
2. Decide the totals-line rule (weakness 1) and whether base wording should be compared (weakness 3) from that data.
3. Have the build reviewed independently before any larger run.
