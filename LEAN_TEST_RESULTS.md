# Lean mode test record

Environment: macOS 2026-11-17, Python 3.12 in `.venv`, openpyxl 3.1.5. No model/API calls or paid credits.

```sh
for f in tests/test_*.py; do PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p "${f:t}" -q; done
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_lean.py' -q
.venv/bin/python -m pyflakes src/royalty_research/lean.py scripts/lean_research.py tests/test_lean.py
PYTHONPATH=src .venv/bin/python scripts/lean_research.py screen --input tests/fixtures/synthetic_licence.html --out /tmp/lean-demo-20261117
```

Twenty isolated modules: **332 passed, 0 failed, 0 skipped, 0 timeouts**. Focused lean module re-run after batch addition: **5 passed**. Pyflakes: zero findings. Synthetic licence screen: 12 passages, 8 heuristic candidates, 4 passages sent to AI packet, 0 budget omissions; no AI call. The old v0.13.3 ZIP was not edited.

Batch local-directory test: two files, one `READY_FOR_AI` and one low-signal item retained in `index.json`.

The CLI source validation checks exact quotation presence and reported value presence. It does not prove that an AI interpreted the contract correctly, that screening captured every term, or that SEC URLs remain live. Contract-level precision/recall: **NOT MEASURED**. Token savings are expected from the smaller packet and output format, but **not measured** with a live model run.
