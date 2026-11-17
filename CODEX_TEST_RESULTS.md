# Codex test results — M13 v0.13.3

Environment: macOS, 2026-11-16; Python `.venv/bin/python`, openpyxl 3.1.5. No paid/API/SEC live calls. Sealed ZIP SHA-256: `5a67f0600720fc9934244c3f7d25da03785b5d6eb275914af41e59cc219cc326`; sealed manifest verified 158/158 files before edits. Plain `python` was unavailable; all dependent checks used the stated venv.

Commands run from `royalty_research_m13`:

```sh
python3 scripts/verify_release.py
.venv/bin/python scripts/verify_research_export_parity.py --original examples/M13_Original_FunctionalBrands_16sheet.xlsx --research examples/M13_Research_FunctionalBrands_5sheet_v0.13.2.xlsx
for f in tests/test_*.py; do PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p "${f:t}" -q; done
PYTHONPATH=src .venv/bin/python scripts/reexport_functionalbrands_review.py
.venv/bin/python scripts/verify_research_export_parity.py --original examples/M13_Original_FunctionalBrands_16sheet.xlsx --research examples/M13_Research_FunctionalBrands_5sheet_v0.13.3.xlsx
.venv/bin/python -m pyflakes src/royalty_research/m13_research_export.py tests/test_m13_research_export.py scripts/reexport_functionalbrands_review.py scripts/verify_research_export_parity.py
```

Original 19 modules: 325 passed, 0 failed, 0 skipped, 0 timeout. Corrected 19 modules: 327 passed, 0 failed, 0 skipped, 0 timeout (test counts by module: 19,11,23,2,15,3,29,11,36,26,5,24,22,17,26,27,17,6,8 in filename order). Focused exporter module: 11 passed. Pyflakes: 0 findings after removing two unused variables. Initial focused run failed once because the first guarantee rule accepted negated text; the anchored correction passes.

Both supplied and corrected parity: PASS_MAPPING_ONLY — 6 royalty observations, 13 payments, 86 evidence rows, 10 conditions, 4 adjustments, 33 QC rows. Enhanced parity checks exact rate/payment URLs and payment basis, condition and disclosure. Supplemental row comparison of 7 reader differences and 23 open issues found no losses. Five-sheet sample: 6/6 rate quotes and 13/13 payment quotes populated; 52/86 evidence records have linked extracted record labels. All five sheets have filters and frozen panes, zero formulas. The optional sixteen-sheet source sample remains `examples/M13_Original_FunctionalBrands_16sheet.xlsx`.

No contract-level precision/recall measured. Source URLs were compared as strings, not requested over the network. No test timeout occurred.

v0.13.1 package: unavailable locally; no direct version-to-version comparison. ZIP CRC check with `unzip -t` passed. The sealed v0.13.2 ZIP SHA-256 was rechecked after packaging and remained unchanged.
