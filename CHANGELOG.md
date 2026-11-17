# v0.13.5 changes

- Restored the v0.13.3 **complete source** M13 reading path as the routine production workflow; v0.13.4 lean excerpts remain labelled preliminary screening only.
- Added `m13_prod.py`: one-process batch preparation, one-time SEC fetch/map per unique candidate, bounded CLI execution, manual model-neutral answer import, resumability through existing immutable M13 plans, finalization and combination.
- Added explicit reader effort settings, task-boundary call/prompt/available-usage budgets, and per-call usage fields when emitted by the CLI. No paid API or nested AI controller.
- Manual imported reader answers use a new backward-compatible `manual` schema engine value in both schema copies; existing Claude/Codex outputs remain valid.
- Strengthened lean excerpt validation against numeric substrings, unsupported basis and suspiciously empty output. This does not make lean mode complete.
- Preserved the five-sheet exporter and added main-sheet `Royalty rate as reported` and `Agreement status` columns; renamed QC title to avoid implying a second reader was used.
- Added a two-document historical-fixture workbook and full-source coverage/controller regressions.
