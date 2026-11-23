# Royalty screen validation

This document records the earlier version-4 validation and its operating
commands at the time. See the [current launcher instructions](../README.md)
for the integrated frozen pre-screen workflow.

The one-sheet agreement summary route runs the deterministic screen after
saving the complete prepared input. In the default shadow mode, a
`WOULD_SKIP` audit still has an effective decision of `KEEP`. The original
validation below predates the version-pinned testable opt-in described in the
follow-up.

## Commands

From the repository, run the normal summary with
`./royalty-summary.sh 2026-10-26 2026-10-30 12 --go`.
Omit `--go` to run SEC discovery, preparation and screening without Codex or
Excel. Each prepared exhibit directory contains the original source, the
exact screened normalized text and its versioned audit.

## Regression evidence

The working tree passed 518 pre-existing tests before implementation. All 527
tests passed with the screen installed. The nine additional synthetic test
methods use subcases for the pattern families, overrides, ambiguous and
unsupported sources, the 2,000-character safeguard, late and appended rates,
audit failures and exhibit-level screening across multiple agreements. The
isolated batch test captures the actual reader command's standard input for
both an ordinary KEEP and a WOULD_SKIP, and verifies no invocation when
`--go` is absent. Pyflakes passed on the touched Python files. These checks
used mocked subscription execution.

Six exact historical SEC sources were retrieved through the existing SEC
client. The local
[fixture manifest](../runs_royalty_screen_historical/fixtures.json) and
[version 2 observations](../runs_royalty_screen_historical/observations_v2.json)
contain the URLs, hashes and exact evidence.

| Exhibit | Revision 2 result | Source finding |
| --- | --- | --- |
| Brazil Potash | KEEP, disclosed royalty | The appended terms create a perpetual 4% Gross Revenue royalty. The existing upstream licence screen rejects this exhibit, so the regression tested the complete mapped source directly. |
| Blue Water Biotech | KEEP, disclosed royalties and share | The operative term rows supply 5%, 3% and 20%. The example report's 10% is excluded from the safeguard evidence. |
| SEKISUI HOUSE | KEEP, disclosed rates and table uncertainty | Appendix B bases the royalty on the sales price of buildings. The tier table includes disclosed rates and an explicit 0% component. Its flattened header cannot support exclusion. |
| RiceBran | KEEP, no direct redaction and no disclosed safeguard | The licence is non-royalty-bearing and passes through unpriced future proceeds. The historical SKIP answered a different question. |
| Yield10 | KEEP, source uncertainty | The direct sales rate is redacted. Voting control, expense offsets and the reduction cap produced no rate safeguard. Merged economic tables prevent exclusion. |
| Arcadia | KEEP, unsupported marker and table uncertainty | The concentration percentages produced no rate safeguard. Forms such as `[…*…]` fall outside the supported marker dictionary. |

The original 22-filing sample manifest and its expected results were
unavailable. The historical prototype's holdouts describe its own rule
versions and are outside the measurements in this report.

## Decision and audit

The gate starts with the complete mapped source used to construct the saved
prompt. It records source uncertainty, searches every passage for direct
redactions, and searches the complete exhibit for disclosures that override
them. The 2,000-character minimum is only a short-source safeguard.
R1, R2, R4, R6, R7, R8 and R9 cover rate language, obligations, bases,
formulas and tiers. PER_UNIT and T1 cover unit pricing and recoverable table
layouts. Uncertain table alignment can keep a document in the reader path.

Evidence offsets are zero-based character offsets with an exclusive end.
`royalty_screen.json` records the screen version, timestamp, exhibit identity,
the raw and exact screened SHA-256 hashes, reasons, uncertainty, redaction
positions, disclosed safeguards, rejected numeric terms and source-review
status. The normalized text and audit are written atomically and read back.
An audit failure produces a terminal KEEP diagnostic. The sublicensing-only
taxonomy stays pending and is flagged when supported by the matched evidence.

The existing SEC selection, preparation and prompt size bound still apply.
Existing prepared runs can still be read directly through the CLI. The prompt,
subscription invocation, output validation, raw response, one-sheet mapping
and treatment of multiple agreements use their previous code paths.

## SEC dry-run selection

All batches used the stock date-range launcher without `--go`. The existing
SEC search queries were “royalty rate”, “license agreement” and “royalties”.
The launcher ranked and deduplicated URLs, applied its existing upstream
screen and stopped at the exhibit limit or candidate cap. None of the six
historical examples was used for these runs. The original external corpus
manifests were unavailable for a full overlap check.

The Nov 2–6 discovery attempt stopped before preparation with the existing
`Unsafe SEC exhibit filename` error. Discovery and filename handling were
left in the existing path.

| Filing dates | Screen version | Distinct screened | KEEP status | WOULD_SKIP | Uncertainty KEEPs | Exhibits with a disclosure safeguard |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [Nov 16–20](../runs_summary_2026-11-16_2026-11-20_110658_1m0fftnv/batch.log) | 1, pilot | 12 | 11 | 1 | 5 | 2 |
| [Nov 9–13](../runs_summary_2026-11-09_2026-11-13_110951_7jxg404x/batch.log) | 1, pilot | 12 | 11 | 1 | 7 | 3 |
| [Oct 26–30](../runs_summary_2026-10-26_2026-10-30_111326_ebuxxmq1/batch.log) | 2, final | 12 | 12 | 0 | 5 | 3 |
| [Oct 12–16](../runs_summary_2026-10-12_2026-10-16_111405_kt9wrrsm/batch.log) | 2, final | 7 | 7 | 0 | 3 | 0 |

All 43 raw hashes were distinct. The audit hashes and stored excerpt offsets
were checked against the saved sources. No batch called the downstream reader.
The version 2 sample hit the prompt bound twice, rejected two unreadable
PDFs and rejected one SEC response above the existing size limit. The version
1 pilots had five prompt-bound failures. These documents did not reach the
screen. Other rejections were made by the existing upstream licence and
triage checks.

## Codex source-review register

The reviewers reopened each listed exhibit, checked its identity against the
SEC filing index and refetched the filed bytes. The saved raw hashes matched,
and reparsing reproduced the exact screened text. The register is the record
of completed Codex source review. The original prediction audits preserve
their status at screening time.

| Run and exact prediction | Coverage | Codex conclusion |
| --- | --- | --- |
| [Nov 16–20 pilot, Kazia EX-4.22](../runs_summary_2026-11-16_2026-11-20_110658_1m0fftnv/exhibit-008/royalty_screen.json) | All 261 passages, pages 1–30, §§1–11, signatures, financial tables and Appendix A | **SKIP supported.** §4.4(a), chars 34,599–34,647, places `[***]` in the royalty on annual worldwide Net Sales. All four §7.4(d) sublicense-revenue tiers are redacted. The affiliate-control percentages, one-time fee and noncommercial royalty-free grant supply no qualifying benchmark. No integral rate schedule was missing. Version 2 still proposes SKIP on replay. |
| [Nov 9–13 pilot, ArriVent EX-10.1](../runs_summary_2026-11-09_2026-11-13_110951_7jxg404x/exhibit-001/royalty_screen.json) | All 616 passages, §§1–14, signatures, both royalty tables and Exhibits A–E | **Overturned to KEEP.** §§6.3 and 12.6 redact every Net Sales tier. §14.10 incorporates Exhibits D and E, which govern collaboration cost allocations and supply. Both are withheld in full, leaving potentially relevant commercial terms unavailable. Version 2 replays as `KEEP / MISSING_SCHEDULE_OR_APPENDIX`. |

[SEC Kazia exhibit](https://www.sec.gov/Archives/edgar/data/1075880/000119312526465487/d503086dex422.htm) · [SEC ArriVent exhibit](https://www.sec.gov/Archives/edgar/data/1868279/000110465926124513/avbp-ex10d1.htm)

Both pilot proposals received completed Codex source review. One was supported,
one was overturned and none remained unresolved. The final revision had no
proposals in the two fresh October windows. Its replay of the supported Kazia
proposal and the overturned ArriVent proposal is recorded separately from
the fresh October results.

## Original operational status

The screen remained in shadow mode. The fresh version 2 run supplied no proposed
exclusions for source review. The next step toward activation is to repeat
the normal dry run on fresh filing dates and review every proposed exclusion
from version 2. Activation would then require a separate owner decision and a
small change in the reader dispatch to act only on a verified, eligible audit.

## Bounded follow-up

**GO for normal shadow use. NO-GO for an automatic-exclusion pilot.**
Production exclusions are OFF. The final implementation is
`royalty-screen.4` on local `main`, HEAD
`5eda2fc0dd4b9b262ce42aa82bcdb14c0241f5bb`. There is no persistent switch.
Omitting the version-pinned opt-in restores shadow on the next command.

The follow-up changes are in `src/royalty_research/royalty_screen.py`,
`src/royalty_research/agreement_summary.py`, `tests/test_royalty_screen.py`,
`ARCHITECTURE.json`, `README.md` and this report. The original pre-edit
session shows that the architecture, README, prompt and summary Python file
were already modified. Their unrelated changes and the untracked
`.DS_Store` were preserved. No commit was created. The prompt, discovery,
parser, mapper and launcher hashes match their follow-up entry hashes.
The reader's input, subscription invocation, saved response and workbook
mapping were preserved.

- [Checkout provenance and starting fingerprints](../runs_royalty_screen_final_validation/baseline.md)
- [Frozen v3 fingerprints](../runs_royalty_screen_final_validation/frozen-sha256.txt)
- [Final v4 fingerprints](../runs_royalty_screen_final_validation/final-v4-sha256.txt)
- [Final full test log](../runs_royalty_screen_final_validation/tests-final-v4.log)

The archived totals reconcile as 518 base test methods plus nine screening
methods, or 527. ArriVent was added as a subcase. The exercise froze v3
after 529 collected and passed. The final v4 suite collected and passed
531, with zero failed, skipped or errored. Pyflakes and `git diff --check`
passed.

### Local dispatch and source safety

Only a batch with `--go` and an explicit matching screen version can act on
a proposal made in that batch. The reader dispatch checks the retained
advisory audit against the in-memory proposal, then verifies exhibit
identity, raw/screened/prompt hashes and exact redaction offsets. Before
suppressing the reader it writes and reads back `royalty_exclusion.json`,
which records the actual SKIP. The original `royalty_screen.json` retains
the earlier advisory decision. Tests used a mocked reader. They exercised
KEEP, test SKIP, shadow rollback, exceptions, missing economic attachments,
corrupt or stale evidence, and audit and receipt failures. They checked that
an exclusion produces neither a raw response nor a workbook agreement and
that reader failures preserve partial-workbook behavior. An unreadable
source continues through existing preparation error handling.

The screen and reader use the same complete mapped passages. Re-parsing
the saved original source for every prepared exercise exhibit reproduced
both the exact screened text and the numbered exhibit section of the
reader prompt. Input hashes, identities, evidence offsets and versions also
matched. These checks establish the content the two paths shared.
Completeness still depends on the source filed with EDGAR and the parser's
treatment of its formatting. Missing documents, suspect layouts and
malformed wrappers warrant KEEP.

The quantified-sublicensing-only test still triggers
`SUBLICENSE_SHARE_ONLY_TAXONOMY_PENDING` and KEEP. Brazil Potash remains a
separate upstream coverage limitation. All eight historical decisions and
core evidence checks were re-run. Kazia's supported v1 proposal remains a
v4 WOULD_SKIP on replay. ArriVent's overturned v1 proposal remains KEEP
for missing attachments. The other six outcomes remain as documented
above. These are replays of known sources.
[Historical recheck](../runs_royalty_screen_final_validation/historical_recheck.json) ·
[Post-repair replays](../runs_royalty_screen_final_validation/post-repair-v4-replays.json)

### Predeclared no-model exercise

The [protocol](../runs_royalty_screen_final_validation/protocol.md) fixed
four five-business-day windows, ten preparation slots per window and the
default rank, upstream filters and attempt cap before discovery. Ranking
uses exhibit type, matched-query count, filing date and URL. The local
deduplication baseline contained 5,312 accession/filename identities, 331
raw hashes and 11 examined windows. All 37 prepared exhibits were distinct
against that baseline and across the exercise. Overlap with unavailable
external holdout manifests is unverified. No window was replaced or blocked.

| Filing window | Discovered unique candidates | Attempted | Upstream rejected | Preparation failures | Prepared | WOULD_SKIP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sep 9–13, 2024 | 796 | 14 | 4 | 0 | 10 | 1 |
| Nov 4–8, 2024 | 1,817 | 94 | 81 | 3 | 10 | 0 |
| Jun 9–13, 2025 | 587 | 100 | 89 | 4 | 7 | 0 |
| Aug 4–8, 2025 | 1,994 | 21 | 7 | 4 | 10 | 0 |
| Total | 5,194 | 229 | 181 | 11 | 37 | 1 |

No duplicate URLs remained after the discovery merge. No prepared identity
or source hash matched the prior records. June stopped at the existing
100-attempt cap. Eight preparation failures hit the existing prompt length
bound and three PDFs had unreadable pages. Of 36 KEEP decisions, 28 had
uncertainty. Two carried a recorded safeguard, including the page number
error found during the targeted KEEP review. All 37 effective decisions
were KEEP. No model calls were made.
[Identities, reasons, counts and audit paths](../runs_royalty_screen_final_validation/fresh-results.json)

Codex reviewed the only v3 proposal against the full SEC exhibit and its
native table. Sling's matched marker was a hypothetical third-party
royalty example. The filing also omitted the Sanofi licence listed as
attached Exhibit A, which affects payment terms. The proposal was
**overturned to KEEP**, with zero supported and zero unresolved proposals.
The observed proposal share was **1/37 (2.7%)**. It produced no supported
exclusion or demonstrated saving.
[Completed source review](../runs_royalty_screen_final_validation/skip-2024-09-09-009.md)

The eight systematically selected KEEP reviews found no defensible missed
exclusion. Several sources had masked rate tables accompanied by missing
economic terms or uncertain layouts. One contained an appended qualitative
rate the gate missed. The Vir/Sanofi source supplied the false safeguard
when a footer page number was associated with a royalty heading.
[September 001–002](../runs_royalty_screen_final_validation/keep-sep-001-002.md) ·
[September 003 and 005](../runs_royalty_screen_final_validation/keep-sep-003-005.md) ·
[September 004 and 007](../runs_royalty_screen_final_validation/keep-sep-004-007.md) ·
[September 006](../runs_royalty_screen_final_validation/keep-sep-006.md) ·
[November 002](../runs_royalty_screen_final_validation/keep-nov-002.md)

Version 4 now rejects hypothetical rate text as affirmative evidence, flags
missing explicitly attached material and requires a resolved table position
for a bare number. It kept Sling and removed the page-number safeguard
on replay. All 37 seen sources replayed as KEEP. The bounded fresh
exercise ended at the fourth window. Version 4 has no independent fresh
positive exclusion evidence, so an automatic pilot is not recommended.

### Operating command

From the checkout, the ordinary command also restores shadow for later
batches because the opt-in is per invocation:

```sh
./royalty-summary.sh 2025-08-04 2025-08-08 10 --go
```

Change dates as needed. Omit `--go` for preparation and screening only.
The same launcher without `--go` ran all four SEC windows, and the reader
path with `--go` was exercised in isolated tests. Syntax was checked
without invoking a model. To reprocess a retained exhibit, use the existing
standalone `read --run` command with its exhibit directory. It always sends
the saved prompt to the reader.
