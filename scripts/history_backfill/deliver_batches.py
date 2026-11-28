"""Package and send each date range when all its monthly checkpoints are present."""
from pathlib import Path
import os
import subprocess
import sys
import time

import backfill

BATCH_RANGES = [(2024, 2026), (2019, 2023), (2014, 2018),
                (2009, 2013), (2004, 2008), (2001, 2003)]
ROOT = Path(__file__).resolve().parent


def main():
    windows = list(backfill.month_windows())
    for first_year, last_year in BATCH_RANGES:
        selected = sorted(pair for pair in windows if first_year <= pair[0].year <= last_year)
        first, last = selected[0][0], selected[-1][1]
        destination = ROOT / 'batches' / f'{first_year}-{last_year}'
        destination.mkdir(exist_ok=True)
        receipt = destination / 'delivery.json'
        if receipt.is_file() and 'gmail_message_id' in receipt.read_text():
            continue
        print(f'Waiting for {first} through {last}', flush=True)
        while not all((backfill.CHECKPOINTS / f'{start:%Y-%m}.zip').is_file()
                      for start, _ in selected):
            try:
                os.kill(int((ROOT / 'worker.pid').read_text()), 0)
            except ProcessLookupError:
                raise RuntimeError(f'Backfill stopped before {first_year}–{last_year} was ready') from None
            time.sleep(45)
        if not (destination / 'packaging_result.json').is_file():
            backfill.ROOT, backfill.START, backfill.END = destination, first, last
            backfill.combine(selected)
        for attempt in range(3):
            result = subprocess.run([sys.executable, str(ROOT / 'send_batch.py'),
                                     str(destination), first.isoformat(), last.isoformat()], check=False)
            if result.returncode == 0:
                break
            marker = destination / 'gmail_send_attempt'
            if attempt == 2 or (marker.is_file() and not marker.read_text().strip()):
                result.check_returncode()
            time.sleep(45)


if __name__ == '__main__':
    main()
