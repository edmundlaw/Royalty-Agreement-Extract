"""Isolated launcher contract tests; no provider calls or live run folders."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def run_launcher(self, root, *args):
        fake = root / 'python'
        fake.write_text('''#!/bin/sh
if [ "$1" = scripts/m13_prod.py ]; then
  case "$2" in
    run) printf '%s\\n' "$@" > "$TEST_ARGS"; exit 0;;
    finalize) case "$4" in */one/) exit 0;; *) echo incomplete >&2; exit 1;; esac;;
    combine) while [ "$#" -gt 0 ]; do if [ "$1" = --out ]; then shift; touch "$1"; exit 0; fi; shift; done;;
  esac
fi
exec /usr/bin/python3 "$@"
''')
        fake.chmod(0o755)
        env = dict(os.environ, ROYALTY_PYTHON=str(fake), ROYALTY_SEC_UA='Test test@example.com',
                   TEST_ARGS=str(root / 'args'), HOME=str(root))
        return subprocess.run(['bash', str(ROOT / 'royalty.sh'), '--resume', str(root), *args],
                              cwd=ROOT, env=env, text=True, capture_output=True, timeout=30)

    def setup_runs(self, root):
        for name in ('one', 'two'):
            run = root / 'batch' / 'runs' / name
            run.mkdir(parents=True)
            (run / 'm13_run.json').write_text('{}')
        (root / 'run_info.json').write_text('{"start":"2026-01-01","end":"2026-01-31"}')

    def test_partial_export_returns_distinct_status_without_default_token_cap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.setup_runs(root)
            output = root / 'batch/runs/one/output'
            output.mkdir()
            (output / 'rows.json').write_text('{}')
            (output / 'reader_check.json').write_text('{"state":"SOURCE_CHECK_FAILED"}')
            result = self.run_launcher(root, '--go')
            self.assertEqual(result.returncode, 3, result.stderr + result.stdout)
            self.assertIn('Partial workbook (1 finished, 1 unfinished)', result.stdout)
            self.assertIn('Needs review: 1 (SOURCE_CHECK_FAILED: 1)', result.stdout)
            self.assertTrue(list((root / 'Downloads').glob('*.xlsx')))
            args = (root / 'args').read_text().splitlines()
            self.assertIn('--all-pending', args)
            self.assertNotIn('--max-calls', args)
            self.assertNotIn('--max-reported-tokens', args)

    def test_explicit_token_cap_adds_prior_reported_usage(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.setup_runs(root)
            results = root / 'batch/runs/one/reader_a/results'
            results.mkdir(parents=True)
            (results / 'chunk.receipt.json').write_text(json.dumps({'usage': {'input_tokens': 80, 'output_tokens': 20}}))
            result = self.run_launcher(root, '--max-reported-tokens', '200')
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            args = (root / 'args').read_text().splitlines()
            self.assertEqual(args[args.index('--max-reported-tokens') + 1], '300')
            for value in ('0', '-1', 'bad'):
                self.assertEqual(self.run_launcher(root, '--max-reported-tokens', value).returncode, 2)


if __name__ == '__main__':
    unittest.main()
