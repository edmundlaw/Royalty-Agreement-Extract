"""Rebuild delivered batch ZIPs from saved monthly checkpoints with the current packaging rule.

Drops exhibits the frozen screen marked SKIP whose only preparation failure was the
300,000-character prompt limit. No SEC requests and no email. Monthly checkpoints are
read only. Each clean ZIP is verified in staging, then replaces the batch copy and the
hosted download copy under the same name, so previously sent links serve the clean ZIP.

    python repackage.py 2024-2026 [2019-2023 ...]      # build and verify in staging only
    python repackage.py --apply 2024-2026 [...]        # also swap into delivery locations
"""
from collections import Counter
from hashlib import file_digest
import io
import csv
import json
import os
from pathlib import Path
import sys
from zipfile import ZipFile

import backfill
import deliver_batches

ROOT = Path(__file__).resolve().parent
STAGING = ROOT / 'batches_clean'
ALL_WINDOWS = list(backfill.month_windows())  # before combine() narrows backfill.START/END
HOSTED = Path('/Users/edmund/valuation-dashboard/library/Impairment_Assistant_Tools/deliverables')


def digest(path):
    with path.open('rb') as handle:
        return file_digest(handle, 'sha256').hexdigest()


def statuses(archive):
    with ZipFile(archive) as bundle:
        counts = Counter()
        for name in bundle.namelist():
            if name.endswith('/00_SEC_SOURCE_MAP.csv'):
                counts.update(row['Screening_status'] for row in
                              csv.DictReader(io.StringIO(bundle.read(name).decode())))
        return counts


def rebuild(label, apply):
    first_year, last_year = map(int, label.split('-'))
    selected = sorted(pair for pair in ALL_WINDOWS if first_year <= pair[0].year <= last_year)
    missing = [f'{start:%Y-%m}' for start, _ in selected if not (backfill.CHECKPOINTS / f'{start:%Y-%m}.zip').is_file()]
    if missing:
        raise RuntimeError(f'{label}: monthly checkpoints not finished: {missing[:3]}...')
    delivered = ROOT / 'batches' / label
    receipt = json.loads((delivered / 'delivery.json').read_text())
    if 'gmail_message_id' not in receipt:
        raise RuntimeError(f'{label}: original delivery not finished; rerun after it is sent')
    old_zip = Path(receipt['archive'])
    stage = STAGING / label
    stage.mkdir(parents=True, exist_ok=True)
    backfill.ROOT, backfill.START, backfill.END = stage, selected[0][0], selected[-1][1]
    new_zip = stage / old_zip.name
    if not new_zip.is_file():
        backfill.combine(selected)
    result = json.loads((stage / 'packaging_result.json').read_text())

    before, after = statuses(old_zip), statuses(new_zip)
    with ZipFile(new_zip) as bundle:
        assert bundle.testzip() is None
        html = sum(n.endswith(('.htm', '.html')) for n in bundle.namelist())
        assert 'Unavailable_sources.json' not in bundle.namelist()
    assert html == sum(result['counts'].values()) == sum(after.values())
    assert after['KEEP'] == before['KEEP'], f'{label}: KEEP count changed {before} -> {after}'
    assert after['REVIEW'] <= before['REVIEW']
    print(f'{label}: {sum(before.values())} -> {sum(after.values())} exhibits '
          f'(KEEP {before["KEEP"]}, REVIEW {before["REVIEW"]} -> {after["REVIEW"]}); '
          f'{old_zip.stat().st_size / 1e9:.2f} GB -> {new_zip.stat().st_size / 1e9:.2f} GB', flush=True)
    if not apply:
        return

    hosted = HOSTED / f'public-sec-royalty-history-harvey-{label}' / old_zip.name
    old_sha, new_sha = digest(old_zip), digest(new_zip)
    if old_sha == new_sha:
        print(f'{label}: already clean', flush=True)
        return
    assert hosted.is_file() and digest(hosted) == old_sha, f'{label}: hosted copy is not the delivered ZIP'
    os.replace(new_zip, old_zip)
    temporary = hosted.with_suffix('.relink')
    temporary.unlink(missing_ok=True)
    os.link(old_zip, temporary)
    os.replace(temporary, hosted)
    assert digest(old_zip) == digest(hosted) == new_sha
    os.replace(stage / 'packaging_result.json', delivered / 'packaging_result.json')
    receipt.update(previous_sha256=old_sha, previous_html_count=receipt.get('html_count'),
                   sha256=new_sha, bytes=old_zip.stat().st_size, html_count=html,
                   repackaged='Oversized initial SKIPs removed; no new SEC downloads; not re-emailed')
    (delivered / 'delivery.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'{label}: replaced batch and hosted ZIP; old {old_sha[:12]} -> new {new_sha[:12]}', flush=True)


def main(argv):
    apply = '--apply' in argv
    labels = [a for a in argv if a != '--apply'] or [f'{a}-{b}' for a, b in deliver_batches.BATCH_RANGES]
    for label in labels:
        rebuild(label, apply)


if __name__ == '__main__':
    main(sys.argv[1:])
