# Independent review — Royalty Research M5 v0.5.0

Reviewer: Claude (Fable 5.2) as lead, Sonnet subagents for bounded module reviews. Date: 2026-11-14.
Machine: this Mac, Python 3.12.13 (Homebrew), Claude Code 2.1.323 (Pro plan sign-in), codex-cli 0.167.2 (ChatGPT sign-in).

Workspace `~/royalty-research/`:

| Path | Content |
|---|---|
| `release_m5_original/` | Supplied ZIP extracted, read-only, untouched. ZIP SHA-256 `fa521bec47cc77433a9ab46f36220d59460d90b3c01646300310d32e532e0099` |
| `review_m5/` | Working copy under git. Baseline commit `edc3769` = as supplied. Branch `review-fixes` = v0.5.1-review |
| `review_log/` | This report, `original_checksums.sha256`, adversarial test outputs, agent scratch |
| `sec_samples/` | 80 real SEC exhibits (raw), their maps, discovery output for 2024-05-08 |
| `live/` | Every live model run: prompts, raw responses, receipts, merged results, QC reports, test workbook |
| `tools/` | Reviewer scripts (reproducible): `fetch_and_map.py`, `parser_preservation.py`, `adversarial_validator.py`, `adversarial_detector.py`, `show_map.py`, `show_extraction.py` |
| `packages/` | `Royalty_Research_M5_v0.5.1-review.zip` |

---

## A. Executive assessment

**v0.5.0 as supplied is not ready, and the reviewed build is ready for the development benchmark only.**

What works:
- Package integrity: 79 of 79 files match the release manifest.
- SEC discovery, pagination, date-splitting and source URL construction work against the live SEC full-text search.
- Download and HTML parsing ran on 80 real exhibits with no errors and no lost text.
- Source binding (hashes, exact-quote checks, immutable attempts, plan locks, interrupted-run states) behaves as designed.
- The subscription route works: Claude Code and Codex both returned usable structured extractions with no API key in play.
- Sonnet read two real agreements and GPT-6-sol read one. Both captured all four Market Finders tiers; Sonnet captured the NeurogesX 1% royalty and the separate 25% / 10% / 5% sublicensing schedule.

What fails:
- The Excel deliverable cannot be produced as supplied (it needs a library that exists only in the developer's sandbox).
- The first live model call was rejected because the prompt never names a key the checker requires.
- The parser cuts clauses and table rows into fragments on real filings, which separates a rate from its threshold.
- The deterministic check accepts materially incomplete or wrong extractions (8 of 11 deliberate corruptions passed) and rejects correct ones (3 of the 4 captured live results failed on bookkeeping, and a fifth response was rejected outright).
- Nothing between discovery and the model decides whether a document is a royalty-bearing licence, so the model would read everything.
- A 26,000-character agreement cost about 97,000 tokens and, at the documented defaults, seven manual commands.

What remains unverified: agreement-level precision and recall (two agreements only, checked by an AI reviewer, not a human), PDF and scanned exhibits, amendment chains on real filings, behaviour at a real usage limit, a lighter model than Sonnet, and account-level credit settings.

---

## B. Test report

### B1. Offline suite

| Check | Result |
|---|---|
| Release manifest | 79/79 SHA-256 match |
| Tests present | 138 (test_m1 19, test_m2 35, test_m3 27, test_m3_integration 5, test_m4 24, test_m5 22, test_quality_edgecases 6) |
| v0.5.0 on this Mac | **135 pass, 1 failure, 2 errors** (stable over 4 runs). All three are the Excel path: `ModuleNotFoundError: No module named 'artifact_tool'` |
| System Python 3.9.6 | Below the declared minimum 3.10; Homebrew 3.12 used |
| Line coverage | 85% overall; `m3_workbook.py` 17%, `sec_client.py` 67%, `parsing.py` 73% |
| v0.5.1-review | **146 tests, all pass** (138 original + 8 regression tests) |

Test-suite weaknesses (Sonnet audit, file:line evidence in `review_log`):
- The happy-path fixture is built with the validator's own regex and quotes whole passages, so the percentage ledger and quote check cannot fail on it (`tests/make_m2_fixture.py:11,35,43`).
- No test chains map → packets → model output → validation → workspace → export.
- No Excel content check ran in this environment.
- Not tested: an omitted whole term, a real royalty labelled unrelated, a rate in words, real PDF parsing, 429 retry, SEC-sourced duplicates and amendments.
- Two functions replaced by constant stubs still passed their tests (`deterministic_unflagged_sample`, `make_blind_rekey_packet`).

### B2. Live SEC tests (declared contact, 1 request per second, about 110 requests in total)

| Test | Result |
|---|---|
| Full-text discovery, 2024-05-08, queries `royalty`, `royalties`, `license agreement`, `sublicense` | 719 documents, 77 typed EX-10, 20 seconds, complete pagination |
| Source URL construction | 80 of 80 URLs fetched (HTTP 200) |
| Parse and map | 80 of 80 succeeded; median 65,800 characters, largest 872,150 |
| Search cross-check | For the 77 exhibits, no query word present in the text was missing from SEC's match list |
| Phrase handling | Unquoted `license agreement` matched 65 EX-10 exhibits; 55 do not contain the phrase. As an exact phrase: 11 |
| Python screening priority | 77 of 80 rated HIGH, 3 MEDIUM: it does not discriminate |
| Relevance of the day's 77 EX-10 hits | 33 mention "royalt"; 8 have a percentage within 200 characters of it; the top scorers are a revenue-share "Royalty Agreement" with individuals, oil-and-gas and mining royalties |
| PDF exhibits, amendments, duplicate filings | None in the sample: **not tested live** |

Named agreements (original HTML compared with the tool's map):

| Agreement | v0.5.0 parse | Finding |
|---|---|---|
| Market Finders / Daugherty | 363 passages, 58 candidates | Section 4.2 is cut into three passages at source line breaks: the 4% rate and its $500,000–$2,500,000 band are in different passages. The minimum-royalty table is one passage per cell |
| UC / NeurogesX | 476 passages, 122 candidates | The sublicensing table is six separate passages (`25%`, `< $250,000`, …). Cells of 3–6 characters cannot be cited: the checker requires quotes of 8+ characters |
| RemeGen / Vor | 882 passages, 405 candidates | All 162 `[***]` markers flagged. Four redacted royalty tiers present, each cell a separate passage |

Confirmed economics of the two agreements used for extraction testing (from the originals):
- **Market Finders**: 6% to $500,000, 4% to $2,500,000, 2% to $20,000,000, 1% above, per Agreement Year, on Net Sales. Minimum royalty $0 / $50,000 / $75,000 / $100,000 / $125,000 by year band, as a condition of exclusivity. $200,000 annual cap if the licensor stops support. Late interest 0.5% per month, audit threshold 5% and a 40% gross-profit clause are not royalties.
- **NeurogesX**: 1% of Net Sales, capped at $1,000,000 a year. Sublicense fees 25% below $250,000, 10% to $2,000,000, 5% above. Total payments capped at 25% of annual product revenue. Stacking reduction above 11% with a 50% floor. $5,000 maintenance fee, $10,000 minimum annual royalty, milestones of $50,000 / $100,000 / $1,000,000 and a share-based liquidity payment. 10% late interest is not a royalty.

### B3. Live model runs (subscription sign-in, no API key variables set)

| # | Engine / model | Agreement, map | Input tokens | Output tokens | Time | Tool outcome | Substance |
|---|---|---|---|---|---|---|---|
| 1 | Claude / Sonnet | Market Finders, chunk 1 of 7, v0.5.0 | 19,565 | 7,439 | 0:45 | **Rejected**: "mismatched required schema" | Clean JSON; key named `schema_version` |
| 2 | Claude / Sonnet | Market Finders, one call, v0.5.0 map | 55,772 | 41,294 | 3:38 | QC FAIL, 11 errors | All tiers, minimums and cap correct |
| 3 | Claude / Sonnet | NeurogesX, one call, corrected map | 55,360 | 45,247 | 3:59 | QC FAIL, 18 errors | 1% royalty and 25/10/5 schedule separate and correct |
| 4 | Codex / gpt-6-terra | Market Finders | 0 | 0 | 0:03 | Refused: model not available on a ChatGPT account | No inference |
| 5 | Codex / gpt-6-sol | Market Finders, corrected map | 35,584 total | | 3:01 | QC FAIL, 15 errors | All tiers, minimums and cap correct |
| 6 | Claude / Sonnet | Market Finders, one call, corrected map | 32,043 | 26,272 | 2:29 | **QC PASS** | Correct |

Claude Code reported a list-price equivalent of $0.15, $0.64, $0.67 and $0.39 for runs 1, 2, 3 and 6. Subscriptions are not billed this way; the figures only indicate scale.

### B4. Adversarial tests (deterministic, no model usage)

Validator, starting from the real QC-passing extraction of run 6 (`review_log/adversarial/validator_mutations.json`):

| Corruption | Validator |
|---|---|
| 1. Fourth tier (1%) dropped, percentage labelled UNRELATED | **PASS** |
| 2. Fourth tier dropped, percentage labelled THRESHOLD | **PASS** |
| 3. Fourth tier dropped, ledger still says it is a royalty rate | FAIL (caught) |
| 4. Entire running royalty removed, passages relabelled BACKGROUND | **PASS** |
| 5. Minimum-royalty schedule and $200,000 cap removed | **PASS** |
| 6. Tier rates swapped (4% on the first band, 6% on the second) | **PASS** |
| 7. Marginal changed to all-units | **PASS** |
| 8. Base changed to gross sales of all products | **PASS** |
| 9. Threshold 500,000 changed to 500 | FAIL (caught) |
| 10. Running royalty relabelled as a sublicensing share | **PASS** |
| 11. Invented 7% rate (control) | FAIL (caught) |
| 12. All open issues deleted | FAIL (caught, only because UNCERTAIN labels remained) |

Candidate detector, 24 unusual phrasings (`review_log/adversarial/detector_cases.json`): **15 not flagged**. Missed: a rate in words in a table row, basis points, "one-twentieth", "share equally", in-kind royalty, cost plus fifteen percent, an amount in words, the euro sign, an obligation by reference to a side letter, three of four redaction styles (`*****`, `[…]`, `■■■■`), most-favoured terms, "shall be halved", and a technical service charge in words. In a full read the model still sees these passages, but nothing forces it to account for them.

### B5. Runner and recovery (Sonnet agent, fake executables only)

- Kill mid-run: task left `INTERRUPTED_REQUIRES_MANUAL_RELEASE`; nothing skipped or duplicated.
- Two concurrent runs: second refused by the plan lock.
- Captured task is never re-run; a missing receipt is recoverable with `m4-recover-result`.
- Fenced, noisy or empty output: raw text saved, but the only way forward is a retry that repeats the model call.
- A valid result whose text contained "rate limit reached" was discarded and the plan blocked.
- Unlisted variables (`ANTHROPIC_FOUNDRY_API_KEY`, `AZURE_OPENAI_API_KEY`, `ANTHROPIC_CUSTOM_HEADERS`, `CLAUDE_CODE_USE_MANTLE`) reached the child process. No sign-in status check is made.
- One manual command per task; no batch mode, daily cap or scheduler.

### B6. Excel (after the writer was replaced)

Workbook built from runs 6 and 3: `live/excel_test/out/Royalty_Research_Historical_Staging.xlsx`, 15 sheets.
- Market Finders: one term, four tier rows (6 / 4 / 2 / 1) with numeric thresholds, five minimum-royalty rows and the cap on Other Payments.
- NeurogesX: the 1% term and the 25 / 10 / 5 schedule are separate records (family `SUBLICENSING_RECEIPTS`); every row shows `QC_FAILED`.
- Documents sheet links are `=HYPERLINK(...)` formulas to sec.gov; evidence rows carry quotation, passage and URL.
- `Human Reviewed` sheet is empty, as it should be.
- Not opened in Excel itself; checked with openpyxl only.

---

## C. Defect register

Status: C = confirmed by reproduction, S = suspected from code reading. "Fixed" refers to branch `review-fixes`.

| ID | Sev | Module | Defect and evidence | Impact | Recommended correction | Status |
|---|---|---|---|---|---|---|
| D-01 | Critical | `parsing.py` | Source line breaks inside an HTML element become passage boundaries; table cells holding `<p>`/`<div>` become separate passages. Reproduce: `map` on Market Finders ex10-2.htm, passages 90–92 and 96–114 | Rate separated from threshold; short cells uncitable; candidate counts doubled | Collapse whitespace in text nodes; emit a data row as one passage | C, **fixed RF-02** (80/80 exhibits: no text lost, 58,728 → 33,960 passages) |
| D-02 | Critical | `m2_validation.py` | Incomplete or wrong extractions pass (B4: 8 of 11). Money amounts, words-only rates and tier meaning are not reconciled; a rate labelled UNRELATED or THRESHOLD needs no term | Silent omission and wrong economics reach `PASS` | Python-issued occurrence IDs for every percentage, amount, spelled number and redaction; rule that a percentage in a royalty-vocabulary passage cannot be excluded without second-reader agreement; field-level second read | C, open |
| D-03 | Critical | `m2_validation.py`, prompts | Correct extractions fail (3 of 4 captured runs: 2, 3 and 5): ledger literals must equal the validator's regex output, which the prompt never states; `STEP_DOWN` with tiers needs a flat rate; percentage caps cannot be expressed; trivial uncertainty needs a HIGH issue. A failure can only be retried with the identical prompt | Most model usage is wasted; no convergence | Occurrence IDs as in D-02; schema fields for percentage-type payments; correction call that sends only the errors and the prior JSON | C, part fixed (RF-03, RF-04) |
| D-04 | Critical | pipeline | No relevance decision between discovery and the model: 77 of 80 rated HIGH; roughly one in ten EX-10 hits has a percentage near a royalty word, and several of those are oil, gas or mining | The model reads about ten times more than needed | Python score plus a short yes/no triage call on a digest; scope rule for non-IP royalties | C, open |
| D-05 | Critical | `m2_packets.py`, `m4_operator.py` | 26,403-character agreement → 7 tasks, 243,790 characters of prompt at the documented `--max-chars 16000`; one call 55,772 in / 41,294 out. Budget counts a 200-character JSON envelope per passage; the schema is resent every call; each call needs a manual command | Not operable at scale on Pro and Plus | Compact passage format; one call per agreement within a token budget; split on section boundaries; batch runner with a daily cap | C, open (RF-02 alone cut run 2 → run 6 by 40%) |
| D-06 | High | `m3_workbook.py` | Needs `artifact_tool`, absent from PyPI and this Mac; `m3-export --format both` exits 2 | No Excel deliverable | openpyxl | C, **fixed RF-05** |
| D-07 | High | `m4_operator.py` | Prompt never names the required key `schema`; embedded schema says `schema_version` (run 1) | Every live call rejected | State the top-level keys in the prompt | C, **fixed RF-01** |
| D-08 | High | `m2_packets.py`, `m3_chunks.py` | Chunks cut by size: at defaults the Market Finders minimum-royalty heading is in chunk 2 and its amounts in chunk 3. The definitions list carries term names without text. Merge has no cross-chunk reconciliation | Values read without their heading or definitions | Section-aware splitting, definitions text in every chunk, a reconciliation pass | C (split) / S (effect on a model) |
| D-09 | High | `mapping.py` | 15 of 24 adversarial phrasings unflagged (B4); spelled-out percentages are outside the ledger; bare-number table rows unflagged | Forced accounting has gaps | Number-word, fraction, basis-point, currency-code and redaction patterns; flag every row of a table whose header carries payment vocabulary | C, open |
| D-10 | High | `m2_validation.py` | Two readers with identical economics reported `ECONOMIC_TERM_MISMATCH` and `PAYMENT_COUNT_MISMATCH` (runs 5 and 6): the signature includes free text, and `'0'` ≠ null | Every agreement is `REVIEW_REQUIRED`; the control cannot discriminate | Compare normalised sets of (family, rate, lower, upper) and report field-level differences | C, open |
| D-11 | High | `m3_workspace.py`, `m3_export.py` | An earlier accept outranks a later rejection: rows stayed in the `Human Reviewed` sheet | Rejected records in the approved view | Latest review decides; any rejection blocks | C (agent), open |
| D-12 | High | `m3_workspace.py` | Blocking status comes from the model's own `open_issues`; re-ingesting with an empty list passed | The gate is self-certified | Derive blocking flags from deterministic checks and second-reader differences | C (agent), open |
| D-13 | High | `m3_workspace.py` | Deleting `selected.json` or a record folder silently removes a document from status and export | Silent loss of records | Register of expected documents, reconciled at export | C (agent), open |
| D-14 | High | `m4_operator.py` | Billing guard lists 11 variables; four others passed through. No sign-in check. User settings, hooks, MCP servers and CLAUDE.md load into each call (run 1: 19,565 input tokens for a 35,000-character prompt) | Possible unintended billing route; token overhead; user instructions leak into extraction | Allow-list environment; check `claude auth status` / `codex login status`; isolate settings (`--setting-sources`, `--no-session-persistence`, `--ephemeral`) | C (agent), open |
| D-15 | High | `m4_operator.py` | The usage-limit pattern is matched against the model's answer; fenced or noisy JSON cannot be recovered without a new call | Valid results discarded; repeated calls | Match limit messages on stderr and error envelopes only; tolerant JSON extraction from the saved response | C (agent), open |
| D-16 | Medium | `discovery.py` | Multi-word queries sent unquoted (B2) | 71% noise in EX-10 hits for that query | Send as an exact phrase | C, **fixed RF-06** |
| D-17 | Medium | `m2_validation.py` | `_numeric_in_quotes` cannot match a rate written `.5%`, and accepts any number within 16 characters before a percent sign | False failures; a wrong number can pass | Parse percentage tokens, not number-near-symbol | S |
| D-18 | Medium | schema | One disclosure status per term (cannot mix disclosed and redacted tiers); no scale or unit for thresholds; interest is a payment kind, so both models listed late interest and audit fees as Other Payments; no royalty-type field for non-IP royalties | Misleading rows; unusual structures forced into wrong labels | Tier-level disclosure status; percentage-type payments; separate non-economic items; arrangement-type field | C (observed in runs 2, 3, 5) |
| D-19 | Medium | `m3_export.py` | No licensor, licensee or industry on term rows; `Rate_Numeric` empty for tiered terms; amounts stored as text; no per-row review status; a leading `'` is added to quotes starting with `=`, `+`, `-`, `@`, altering the exact quotation | Workbook is traceable but awkward to filter; quotes altered | Flattened summary sheet; numeric amounts; per-row status; write strings as strings without a prefix | C (agent) |
| D-20 | Medium | `m3_linkage.py` | Duplicates only by identical text hash; amendments only by manual link; illogical links accepted | Re-filed and redacted versions counted twice; amendments unlinked | Party/title/date key plus similarity; amendment title detection | C (agent), not tested on real filings |
| D-21 | Medium | tests | See B1 | Passing tests overstate assurance | End-to-end test on a real excerpt; mutation tests from B4 | C |
| D-22 | Low | `m4_operator.py` | A plan is bound to a model label that is not checked against the account (run 4) | Wasted step | Preflight model check | C |
| D-23 | Low | `m3_workspace.py` | `--select` overwrites the selection pointer with no log; one tampered file blocks the whole workspace | Audit trail gap | Append-only selection log; per-document isolation | C (agent) |
| D-24 | Low | docs | macOS system Python is 3.9; README does not say which interpreter to use | Setup friction | State Homebrew Python 3.12 and a virtual environment | C |

---

## D. Extraction accuracy assessment

Measured:
- Two agreements, read by one or two models, compared with the reviewer's reading of the originals.
- Market Finders (Sonnet ×2, GPT-6-sol ×1): 4 of 4 tiers with thresholds, 5 of 5 minimum-royalty rows, the cap and the Net Sales exclusion captured in all three; no royalty term missed; interest, audit and margin percentages not treated as royalties.
- NeurogesX (Sonnet ×1): running royalty, annual cap, three sublicensing tiers with thresholds, stacking reduction, revenue cap, maintenance fee, minimum annual royalty and four milestone items captured. Articles 3 to 7 were compared in full; other articles only where flagged.
- Interpretive weaknesses seen: the sublicensing schedule labelled `STEP_DOWN` with calculation `UNKNOWN` (raised as an open issue); late interest and audit items listed as Other Payments.

Not measured:
- Precision or recall. Two agreements, both old regression cases named in the brief, cannot support a rate.
- Human-verified truth. The comparison was made by an AI reviewer.
- Redacted agreements through a model (RemeGen was not sent: 380 to 405 candidates and over 200,000 characters).
- Any agreement from 2021 to 2025 through a model.

Expectation, not evidence: full-read extraction by Sonnet-class models looks capable on short agreements. The measured weakness is in the controls around the model, not in the reading.

---

## E. Subscription feasibility

- Sign-in: `claude auth status` reports `claude.ai`, plan `pro`, first-party; `codex login status` reports ChatGPT. No API-key variables, no `apiKeyHelper`.
- Not verifiable from this Mac: purchased credits, extra usage and auto-reload settings on both accounts. I relied on the sign-in status and on the Pro limit pausing this session on 13 November instead of charging. Please confirm both settings in the account pages.
- Structured output: both engines returned a single clean JSON object without fences in every run.
- Cost per agreement: 58,000 to 100,000 tokens and 2.5 to 4 minutes for agreements of 26,000 to 51,000 characters. The median 2024 exhibit in the sample is 65,800 characters.
- Codex model names on a ChatGPT account are restricted (`gpt-6-terra` refused; `gpt-6-sol` worked).
- No usage limit was reached during testing, so limit handling was tested only with fake executables.
- Throughput today: one manual command per call. At the measured cost, thousands of agreements are out of reach on Pro and Plus until D-04 and D-05 are fixed.

---

## F. Corrections required before historical extraction

1. Keep RF-01 to RF-06 (parser, prompt, engine name, short quotes, Excel writer, phrase queries).
2. Replace the literal-matching ledger with Python-issued occurrence IDs covering percentages, amounts, spelled numbers and redactions (D-02, D-03, D-09).
3. Add the exclusion rule and a field-level second read; repair the comparison (D-02, D-10).
4. Add document triage and a scope rule for non-IP royalties (D-04).
5. Compact prompts, one call per agreement, section-aware splitting, a correction call instead of a full retry (D-03, D-05, D-08).
6. Batch runner with daily cap, stop-on-limit, isolated settings and a sign-in check (D-05, D-14, D-15).
7. Fix the approved-view logic and workspace integrity (D-11, D-12, D-13).
8. Then run the 25-agreement development benchmark with human-verified answers, followed by a locked acceptance sample.

## G. Updated package

`~/royalty-research/packages/Royalty_Research_M5_v0.5.1-review.zip` (branch `review-fixes`). Changes are listed in `docs/REVIEW_CHANGES_v0.5.1.md` inside the package. The original release is preserved unchanged.

## H. Readiness recommendation

| Build | Classification |
|---|---|
| v0.5.0 as supplied | **Not ready — critical defects** (D-01, D-06, D-07 stop the workflow; D-02 to D-05 undermine it) |
| v0.5.1-review | **Ready for development benchmark only** |

Evidence: with the review fixes the workflow ran end to end on a real agreement and produced a workbook, but the completeness control still passes corrupted extractions, the comparison control cannot discriminate, and the cost per agreement rules out a pilot of any size on the current subscriptions.
