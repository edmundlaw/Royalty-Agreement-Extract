"""Run the existing local batch in monthly windows and package retained originals."""
from calendar import monthrange
from collections import Counter
import csv
from datetime import date, timedelta
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import unquote, urlsplit
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from royalty_research import agreement_summary as app
from royalty_research.discovery import SearchCoverageError, hit_to_record, search_range
from royalty_research.sec_client import SECRequestError

ROOT = Path(__file__).resolve().parent
CHECKPOINTS = ROOT / 'months'
FIELDS = ['Uploaded_filename', 'Original_SEC_URL', 'Filing_date', 'Exhibit_type',
          'Title', 'Screening_status', 'Title_status', 'SHA256',
          'Initial_decision', 'Screen_reason', 'Flags']
START = date(2001, 1, 1)
END = date(2026, 11, 26)
JANUARY = Path('../outputs/royalty-january-2026-keep-review.4eIidc/January_2026_SEC_EX10_and_Contract_EX4_KEEP_REVIEW.zip')
JANUARY_SCREENING = ROOT.parent / 'royalty-january-2026-harvey.aOjLdu'
KEEP_REVIEW = {'KEEP', 'REVIEW'}
QUERIES = ['royalty rate', 'license agreement', 'royalties']


def month_windows():
    end = END
    while end >= START:
        start = end.replace(day=1)
        yield start, end
        end = start - timedelta(days=1)
        end = end.replace(day=monthrange(end.year, end.month)[1])


def discover_window(client, start, end):
    try:
        candidates = {}
        unavailable = {}
        for query in QUERIES:
            for hit in search_range(client, query, start, end):
                metadata = hit.get('_source') or {}
                kind = (metadata.get('file_type') or '').strip().upper()
                if not app.matches_exhibit(kind, ('EX-10', 'EX-4')):
                    continue
                try:
                    record = hit_to_record(hit, query)
                except (ValueError, SearchCoverageError) as exc:
                    document_id = hit.get('_id', '')
                    unavailable[document_id] = {
                        'sec_document_id': document_id, 'exhibit_type': kind,
                        'filing_date': metadata.get('file_date'),
                        'reason': f'SEC record could not be resolved safely: {exc}',
                    }
                    continue
                if record['source_url'] not in candidates:
                    record['matched_queries'] = [query]
                    candidates[record['source_url']] = record
                elif query not in candidates[record['source_url']]['matched_queries']:
                    candidates[record['source_url']]['matched_queries'].append(query)
        return list(candidates.values()), list(unavailable.values())
    except (SearchCoverageError, SECRequestError) as exc:
        if isinstance(exc, SECRequestError) and exc.status not in {'HTTP_500', 'HTTP_502', 'HTTP_503', 'HTTP_504'}:
            raise
        if start == end:
            raise
        middle = start + (end - start) // 2
        print(f'{start} to {end}: splitting SEC discovery after {exc}', flush=True)
        early, early_missing = discover_window(client, start, middle)
        late, late_missing = discover_window(client, middle + timedelta(days=1), end)
        return early + late, early_missing + late_missing


def source_csv(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def screen_metadata(row):
    return {
        'Initial_decision': row.get('prescreen_decision') or '',
        'Screen_reason': row.get('prescreen_reason') or row.get('skip_reason') or '',
        'Flags': ', '.join(row.get('flags', [])),
    }


def checkpoint_decision(row):
    # Older checkpoints moved a SKIP to REVIEW on a size-only failure.
    flags = row.get('flags', [])
    if (row.get('prescreen_decision') == 'SKIP' and 'source_too_large' in flags
            and 'unreadable_source' not in flags):
        return 'SKIP'
    return row['decision']


def checkpoint_screening(month, key):
    if 'month_report.json' in month.namelist():
        report = json.loads(month.read('month_report.json'))
        return report['screening_log'], report['unavailable']
    if key == '2026-01':
        # January was packaged before the monthly checkpoint format was introduced.
        logs = sorted(JANUARY_SCREENING.glob('*/*/screening_log.json'))
        if len(logs) == 2:
            return [row for log in logs for row in json.loads(log.read_text())['documents']
                    if row['decision'] != 'EXCLUDED'], []
    raise ValueError(f'{key}: screening logs missing from checkpoint')


def run_month(start, end):
    key = start.strftime('%Y-%m')
    completed = CHECKPOINTS / f'{key}.zip'
    if completed.is_file():
        return
    if shutil.disk_usage(ROOT).free < 3_000_000_000:
        raise RuntimeError('Local free disk space fell below 3 GB; backfill paused with checkpoints intact')
    app.frozen.verified_sources()
    if key == '2026-01':
        with ZipFile(JANUARY) as bundle:
            assert bundle.testzip() is None
        shutil.copyfile(JANUARY, completed.with_suffix('.partial'))
        completed.with_suffix('.partial').replace(completed)
        print(f'Completed {key}: reused the verified January package', flush=True)
        return

    agent = app.sec_user_agent()
    print(f'{key}: searching SEC filing dates {start} through {end}', flush=True)
    candidates, missing = discover_window(app.SECClient(agent), start, end)
    print(f'{key}: found {len(candidates)} EX-10/EX-4 candidates, {len(missing)} unresolved URLs', flush=True)
    dates = {item['source_url']: item.get('filing_date') for item in candidates if item.get('source_url')}
    log_rows, manifest = [], []
    screen = app.frozen.load_screen()
    with tempfile.TemporaryDirectory(prefix='processing-', dir=ROOT) as temporary:
        work = Path(temporary)
        original_fetch = screen.Fetcher.get
        bundle_path = work / 'month.zip'
        with ZipFile(bundle_path, 'x', ZIP_DEFLATED, compresslevel=6) as bundle:
            for exhibit, titles_only in [('EX-10', False), ('EX-4', True)]:
                selected = [item for item in candidates if item.get('source_url')
                            and app.matches_exhibit((item.get('file_type') or '').strip().upper(), (exhibit,))]
                expected = {item['source_url'] for item in selected}
                if not expected:
                    continue
                originals = work / f'{exhibit}-sources'
                originals.mkdir()
                destination = work / exhibit
                destination.mkdir()

                def record_source(fetcher, url):
                    document = original_fetch(fetcher, url)
                    if document.body and not document.issue:
                        (originals / sha256(url.encode()).hexdigest()).write_bytes(document.body)
                    # Each candidate URL occurs once in the batch. Release the source object after processing.
                    fetcher.responses.pop(url, None)
                    return document

                with (patch.object(app, 'discover', return_value=selected),
                      patch.object(screen.Fetcher, 'get', record_source),
                      patch.object(app, 'read', side_effect=AssertionError('AI is disabled for this export'))):
                    app.batch(start, end, len(expected), exhibits=(exhibit,),
                              contract_title_only=titles_only, output_root=destination)
                log_path, = destination.glob('*/screening_log.json')
                log = json.loads(log_path.read_text())
                rows = log['documents']
                if ({row['source_url'] for row in rows} != expected
                        or log.get('sha256_after') != app.frozen.FREEZE or log['execute']):
                    raise RuntimeError(f'{key} {exhibit}: incomplete screening log: {log["errors"]}')
                log_rows.extend(rows)
                for row in rows:
                    if row['decision'] not in KEEP_REVIEW:
                        continue
                    url = row['source_url']
                    local = originals / sha256(url.encode()).hexdigest()
                    parts = re.fullmatch(r'/Archives/edgar/data/(\d+)/(\d{18})/([^/]+\.html?)',
                                         unquote(urlsplit(url).path), re.I)
                    if not local.is_file() or not parts:
                        missing.append({'url': url, 'reason': row.get('error') or
                                        ('Original unavailable' if not local.is_file() else 'Non-HTML original')})
                        continue
                    body = local.read_bytes()
                    if body.lstrip().startswith(b'%PDF-'):
                        missing.append({'url': url, 'reason': 'Non-HTML original'})
                        continue
                    kind = re.sub(r'[^A-Z0-9.-]', '_', row['document_type'])
                    name = f'{kind}__{parts[1]}_{parts[2]}__{parts[3]}'
                    bundle.writestr(f'{key}/{name}', body)
                    manifest.append({
                        'Uploaded_filename': name,
                        'Original_SEC_URL': url,
                        'Filing_date': dates.get(url) or '',
                        'Exhibit_type': row['document_type'],
                        'Title': row.get('title') or '',
                        'Screening_status': row['decision'],
                        'Title_status': row.get('title_status') or '',
                        'SHA256': sha256(body).hexdigest(),
                        **screen_metadata(row),
                    })
            assert len(manifest) == len({row['Uploaded_filename'].casefold() for row in manifest})
            bundle.writestr(f'{key}/00_SEC_SOURCE_MAP.csv', source_csv(manifest))
            bundle.writestr('month_report.json', json.dumps({
                'discovered': len(dates), 'screening': Counter(row['decision'] for row in log_rows),
                'unavailable': missing, 'screening_log': log_rows,
            }))
        app.frozen.verified_sources()
        bundle_path.replace(completed)
    print(f'Completed {key}: {len(manifest)} originals; {len(missing)} unavailable', flush=True)


def combine(windows):
    archive = ROOT / f'SEC_EX10_and_Contract_EX4_KEEP_REVIEW_{START}_{END}.zip'
    partial = archive.with_suffix('.partial')
    counts, statuses, unavailable, large, seen = Counter(), Counter(), [], [], set()
    with ZipFile(partial, 'w', ZIP_DEFLATED, compresslevel=6) as output:
        for start, _ in sorted(windows):
            key = start.strftime('%Y-%m')
            index = f'{key}/00_SEC_SOURCE_MAP.csv'
            with ZipFile(CHECKPOINTS / f'{key}.zip') as month:
                screening_rows, month_unavailable = checkpoint_screening(month, key)
                screened = {row['source_url']: row for row in screening_rows}
                unavailable.extend(item for item in month_unavailable
                                   if item.get('url') not in screened
                                   or checkpoint_decision(screened[item['url']]) in KEEP_REVIEW)
                month_rows = []
                for row in csv.DictReader(io.StringIO(month.read(index).decode())):
                    url = row['Original_SEC_URL']
                    if url in seen or checkpoint_decision(screened[url]) not in KEEP_REVIEW:
                        continue
                    row.update(screen_metadata(screened[url]))
                    seen.add(url)
                    name = f'{key}/{row["Uploaded_filename"]}'
                    body = month.read(name)
                    assert sha256(body).hexdigest() == row['SHA256']
                    output.writestr(name, body)
                    month_rows.append(row)
                    assert row['Screening_status'] in KEEP_REVIEW
                    counts[row['Exhibit_type'].split('.')[0]] += 1
                    statuses[row['Screening_status']] += 1
                    if len(body) > 8_000_000:
                        large.append(name)
                if month_rows:
                    output.writestr(index, source_csv(month_rows))
        if unavailable:
            output.writestr('_admin/Unavailable_sources.json', json.dumps(unavailable, indent=2))
    with ZipFile(partial) as bundle:
        assert bundle.testzip() is None
        assert sum(name.endswith(('.htm', '.html')) for name in bundle.namelist()) == len(seen)
    app.frozen.verified_sources()
    partial.replace(archive)
    (ROOT / 'packaging_result.json').write_text(json.dumps({
        'archive': str(archive), 'counts': counts, 'statuses': statuses,
        'omitted': unavailable, 'large_html': large,
    }, indent=2))
    print(f'Backfill packaged: {len(seen)} originals, {len(unavailable)} unavailable', flush=True)


def main():
    CHECKPOINTS.mkdir(exist_ok=True)
    windows = list(month_windows())
    errors = {}
    for start, end in windows:
        for attempt in range(3):
            try:
                run_month(start, end)
                break
            except (SECRequestError, SearchCoverageError) as exc:
                print(f'{start:%Y-%m}: SEC discovery attempt {attempt + 1} failed: {exc}', flush=True)
                if attempt < 2:
                    time.sleep(10 * (attempt + 1))
                else:
                    errors[start.strftime('%Y-%m')] = str(exc)
    (ROOT / 'discovery_failures.json').write_text(json.dumps(errors, indent=2))
    if errors:
        raise RuntimeError(f'{len(errors)} discovery windows failed; checkpoints remain available for resume')
    combine(windows)


if __name__ == '__main__':
    main()
