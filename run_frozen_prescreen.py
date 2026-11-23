"""Compatibility entry point for the same pipeline as royalty-summary.sh."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from royalty_research.agreement_summary import batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--dates', nargs=2, type=date.fromisoformat, metavar=('START', 'END'))
    source.add_argument('--urls', nargs='+', metavar='SEC_URL')
    parser.add_argument('--limit', type=int, help='Maximum prepared exhibits for --dates')
    parser.add_argument('--output-root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    if args.dates and (args.limit is None or args.limit < 1):
        parser.error('--dates requires a positive --limit')
    if args.urls and args.limit is not None:
        parser.error('--limit applies only to --dates')
    try:
        start, end = args.dates or (None, None)
        return batch(start, end, args.limit, execute=True, urls=args.urls, output_root=args.output_root)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
