"""Prepare, read, and export SEC exhibits as commercial terms summaries."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from textwrap import TextWrapper
from urllib.error import URLError
from urllib.parse import urlparse, urlsplit
from urllib.request import urlopen

from .discovery import discover
from . import frozen_prescreen as frozen
from .m13_production import DOWNLOADS_PER_AGREEMENT, candidate_rank, licence_gate
from .m4_operator import _command, _preflight_subscription, _safe_environment
from .m7_triage import triage_document
from .mapping import map_contract
from .parsing import ParseError, parse_document
from .royalty_screen import SCREEN_VERSION, audit_screen, record_exclusion
from .sec_client import SECClient, SECRequestError
from .storage import atomic_bytes, atomic_json, read_json, sha256

PROMPT = Path(__file__).resolve().parents[2] / 'prompts' / 'AGREEMENT_SUMMARY.md'
MAX_PROMPT_CHARS = 300_000  # Same prompt bound as the existing Codex launcher.
IMAGE_LIMITATION = 'Embedded images in the SEC exhibit were not read. The supplied source covers the exhibit text.'
GICS_URLS = (
    'https://www.spglobal.com/spdji/en/documents/index-policies/2023-gics-structure-english.xlsx',
    'https://www.msci.com/documents/1296102/23c8ec04-fd1c-3518-e04c-4aa37027889d',
)
GICS_SHEET = 'Effective close of Mar 17 2023'
SAVED_GICS = PROMPT.parents[1] / 'runs_agreement_summary_ex103_gics' / 'gics_reference.xlsx'
SOURCE_TYPES = {'Agreement', 'Amendment', 'Term sheet', 'Press release', 'Other disclosure', 'Unclear'}
TRANSACTION_TYPES = {'Licence', 'Rights transfer', 'Royalty interest acquisition', 'Other', 'Unclear'}
NON_LICENCES = TRANSACTION_TYPES - {'Licence', 'Unclear'}
CONTROLLED = {
    'source_type': SOURCE_TYPES,
    'transaction_type': TRANSACTION_TYPES,
    'royalty_basis': {'Gross Sales', 'Net Sales', 'Other', 'Not stated'},
    'royalty_structure': {'Flat', 'Tiered', 'Not stated'},
    'exclusivity': {'Exclusive', 'Non-exclusive', 'Sole', 'Co-exclusive', 'Mixed', 'Conditional',
                    'Ambiguous', 'Not stated', 'Not applicable'},
}
MAX_VISIBLE_LINES = 27
LINE_HEIGHT = 14


class OutputError(ValueError):
    """A saved reader response could not be mapped safely to the sheet."""


def download_gics():
    for url in GICS_URLS:
        try:
            with urlopen(url, timeout=25) as response:
                return response.read(), url
        except URLError as exc:
            print(f'GICS download failed from {url}: {exc}', file=sys.stderr)
    raise RuntimeError('The official GICS reference could not be downloaded from S&P DJI or MSCI.')


def gics_names(source):
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(source), read_only=True, data_only=True)
    names = {}
    try:
        sheet = workbook[GICS_SHEET]
        for row in sheet.iter_rows(min_row=5, max_col=8, values_only=True):
            for code, label in zip(row[::2], row[1::2]):
                if not isinstance(code, int) or not isinstance(label, str) or '(Discontinued)' in label:
                    continue
                # Drop change annotations and footnote markers while preserving official names such as REITs.
                name = re.sub(r'\s*\((?:New|Definition Update|Sector Change)[^()]*\)\s*$', '', label, flags=re.I)
                names[str(code)] = ' '.join(name.strip().rstrip('*').split())
    finally:
        workbook.close()
    return names


def prepare(url, run, user_agent, source_file=None, gics_reference=None, *, client=None, reference=None, audit_royalty_screen=True):
    parsed = urlparse(url)
    if parsed.hostname not in {'sec.gov', 'www.sec.gov'} or not parsed.path.startswith('/Archives/edgar/data/'):
        raise ValueError('Provide an SEC Archives exhibit URL.')
    raw = source_file.read_bytes() if source_file is not None else (client or SECClient(user_agent)).fetch(url)
    filename = Path(parsed.path).name
    paragraphs, parser = parse_document(raw, filename)
    document_id = 'DOC-' + sha256(url.encode())[:16]
    mapping = map_contract(paragraphs, {'document_id': document_id, 'source_url': url},
                           raw_hash=sha256(raw), parser_type=parser)
    gate = licence_gate(mapping)
    priority = triage_document(mapping)['priority']
    if priority.startswith('LOW_SIGNAL') or not gate['passed']:
        raise ValueError(f'Exhibit did not pass existing screening ({priority}): {gate["reason"]}')

    limitation = IMAGE_LIMITATION if re.search(rb'<img\b', raw, re.I) else ''
    source_note = f'\n\nPREPARATION LIMITATION\n\n{limitation}' if limitation else ''
    passages = '\n\n'.join(f'[{p["passage_id"].split(":")[-1]}] {p["text"]}' for p in mapping['passages'])
    if reference is not None:
        reference, reference_url = reference
    elif gics_reference is None:
        reference, reference_url = download_gics()
    else:
        reference, reference_url = gics_reference.read_bytes(), GICS_URLS[1]
    names = gics_names(reference)
    hierarchy = '\n'.join(f'{"  " * (len(code) // 2 - 1)}{code} {names[code]}' for code in sorted(names))
    prompt = (f'{PROMPT.read_text(encoding="utf-8")}{source_note}'
              f'\n\nOFFICIAL GICS HIERARCHY ({GICS_SHEET})\n\n{hierarchy}'
              f'\n\nSEC EXHIBIT TEXT\n\n{passages}\n')
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f'Full prompt is {len(prompt):,} characters, above the current CLI bound '
                         f'of {MAX_PROMPT_CHARS:,}. No split or partial reading was prepared.')

    run.mkdir(parents=True)
    (run / 'source.htm').write_bytes(raw)
    (run / 'gics_reference.xlsx').write_bytes(reference)
    (run / 'prompt.txt').write_text(prompt, encoding='utf-8')
    prepared = {
        'document_id': document_id, 'source_url': url, 'source_sha256': sha256(raw),
        'parser': parser, 'screening': gate, 'priority': priority,
        'passages': len(mapping['passages']), 'prompt_chars': len(prompt), 'limitation': limitation,
        'gics_reference_url': reference_url, 'gics_reference_sheet': GICS_SHEET,
        'reader_format': 2,
    }
    atomic_json(run / 'prepared.json', prepared)
    audit = None
    if audit_royalty_screen:
        audit = audit_screen(run, '\n'.join(p['text'] for p in mapping['passages']),
                         raw, prepared, verified_identity=source_file is None,
                         prompt_sha256=sha256(prompt.encode('utf-8')))
        print(f"Royalty screen: {audit['status'] if audit else 'KEEP'} (preparation).")
    print(f'Prepared one prompt with {len(mapping["passages"])} passages and {len(prompt):,} characters.')
    if limitation:
        print(limitation)
    return audit


def read(run):
    prompt = (run / 'prompt.txt').read_text(encoding='utf-8')
    response = (run / 'raw_response.txt').resolve()
    if response.exists():
        raise FileExistsError('Raw response already exists. Use the write step to import it.')
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Codex CLI is not installed.')
    env = _safe_environment()
    with tempfile.TemporaryDirectory(prefix='royalty-agreement-cli-') as work:
        _preflight_subscription(executable, 'codex', env, work)
        command = _command('codex', 'gpt-6.2-sol', response, 'low')
        command[0] = executable
        result = subprocess.run(command, input=prompt, text=True, capture_output=True,
                                timeout=900, cwd=work, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f'Codex exited with {result.returncode}: {result.stderr.strip()}')
    if not response.is_file():
        raise RuntimeError('Codex did not save a final response.')
    load_agreements(run, read_json(run / 'prepared.json'), gics_names((run / 'gics_reference.xlsx').read_bytes()))
    print(f'Saved raw Codex response to {response}')


COLUMNS = (
    ('Agreement title', 'title', 36),
    ('Agreement date', 'agreement_date', 16),
    ('Licensor', 'licensor', 25),
    ('Licensee', 'licensee', 23),
    ('Industry (GICS)', 'industry', 40),
    ('Nature IA', 'ip_nature', 23),
    ('Detailed licensed IA', 'licensed_asset', 57),
    ('Royalty rate (%)', 'royalty_rate_percent', 16),
    ('Royalty basis', 'royalty_basis', 16),
    ('Royalty per unit', 'royalty_per_unit', 18),
    ('Royalty structure', 'royalty_structure', 19),
    ('Upfront payment', 'upfront_payment', 24),
    ('Exclusivity', 'exclusivity', 16),
    ('Licence term/duration', 'licence_term', 37),
    ('Other material conditions', 'other_material_conditions', 89),
    ('Source URL', 'source_url', 22),
)


def gics_path(code, names):
    if code == 'Not stated':
        return code
    ancestors = [names[code[:level]] for level in range(2, len(code), 2)]
    return ' > '.join([*ancestors, names[code]])


def write(run):
    write_workbook([run], run / 'Royalty_Agreement_Summary.xlsx')


def load_agreements(run, prepared, names):
    try:
        payload = read_json(run / 'raw_response.txt')
    except json.JSONDecodeError as exc:
        raise OutputError(f'{run.name}: saved Codex response is not JSON ({exc})') from exc
    agreements = payload.get('agreements') if isinstance(payload, dict) else None
    if not isinstance(agreements, list):
        raise OutputError(f'{run.name}: expected an agreements list in the saved response')
    keys = {key for _, key, _ in COLUMNS} - {'industry', 'source_url'} | {'gics_code'}
    if prepared.get('reader_format') == 2:
        keys |= {'source_type', 'transaction_type'}
    for number, agreement in enumerate(agreements, 1):
        label = f'{run.name}, agreement {number}'
        if not isinstance(agreement, dict):
            raise OutputError(f'{label}: expected an agreement object')
        missing = sorted(key for key in keys if not isinstance(agreement.get(key), str))
        if missing:
            raise OutputError(f'{label}: missing or non-text fields: {", ".join(missing)}')
        for key, allowed in CONTROLLED.items():
            if key in keys and agreement[key] not in allowed:
                raise OutputError(f'{label}: unrecognized {key}: {agreement[key]!r}')
        try:
            gics_path(agreement['gics_code'], names)
            stated_date = agreement['agreement_date']
            if stated_date and date.fromisoformat(stated_date).isoformat() != stated_date:
                raise ValueError('Expected YYYY-MM-DD')
        except (KeyError, ValueError) as exc:
            raise OutputError(f'{label}: invalid GICS code or agreement date') from exc
    return agreements


def agreement_rows(runs):
    for run in runs:
        prepared = read_json(run / 'prepared.json')
        names = gics_names((run / 'gics_reference.xlsx').read_bytes())
        for agreement in load_agreements(run, prepared, names):
            yield agreement, prepared, names


def display_fields(agreement, names):
    fields = dict(agreement, industry=gics_path(agreement['gics_code'], names), source_url='Original document')
    source = agreement.get('source_type')
    transaction = agreement.get('transaction_type')
    context = []
    if source and source != 'Agreement':
        context.append(f'Source: {source}.')
    if transaction and transaction != 'Licence':
        context.append(f'Transaction: {transaction}.')
    if transaction in NON_LICENCES:
        fields.update(licensor='Not applicable', licensee='Not applicable', exclusivity='Not applicable')
    notes = agreement['other_material_conditions']
    fields['other_material_conditions'] = '\n'.join(filter(None, [' '.join(context), notes]))
    return fields


def fit_cell(value, width):
    """Return display text, wrapped line count, and full text if the Excel row cannot fit it."""
    wrapper = TextWrapper(width=max(1, int(width * 0.9)))
    lines = [line for paragraph in value.split('\n') for line in (wrapper.wrap(paragraph) or [''])]
    if len(lines) <= MAX_VISIBLE_LINES:
        return value, len(lines), None
    preview = '\n'.join(lines[:MAX_VISIBLE_LINES - 2] + ['… See note.'])
    return preview, MAX_VISIBLE_LINES, value


def write_workbook(runs, destination):
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if destination.exists():
        raise FileExistsError(f'Workbook already exists: {destination}')

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Agreement Summary'
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 85
    sheet.sheet_properties.tabColor = 'FD5108'
    sheet.freeze_panes = 'C2'
    sheet.append([name for name, _, _ in COLUMNS])
    sheet.row_dimensions[1].height = 37
    header_font = Font(name='Arial', size=10, color='000000', bold=True)
    header_fill = PatternFill('solid', fgColor='FFFFFF')
    orange_rule = Side(style='medium', color='FD5108')
    header_border = Border(top=orange_rule, bottom=orange_rule)
    body_font = Font(name='Arial', size=10, color='000000')
    link_font = Font(name='Arial', size=10, color='000000', underline='single')
    band_fill = PatternFill('solid', fgColor='F5F7F8')
    wrapped = Alignment(horizontal='left', vertical='top', wrap_text=True)
    for number, (_, _, width) in enumerate(COLUMNS, 1):
        sheet.column_dimensions[get_column_letter(number)].width = width
        cell = sheet.cell(1, number)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = header_border
        cell.alignment = Alignment(vertical='center', wrap_text=True)
    sheet['E1'].comment = Comment('Analytical mapping of the licensed activity using the March 2023 GICS hierarchy. '
                                  'This does not classify the contracting companies.', 'Source preparation')

    for number, (agreement, prepared, names) in enumerate(agreement_rows(runs), 2):
        fields = display_fields(agreement, names)
        row_lines = 1
        for column, (_, key, width) in enumerate(COLUMNS, 1):
            cell = sheet.cell(number, column)
            value = fields[key]
            if key == 'agreement_date':
                cell.value = date.fromisoformat(value) if value else None
                cell.number_format = 'yyyy-mm-dd'
            else:
                cell.value, lines, full = fit_cell(value, width)
                row_lines = max(row_lines, lines)
                cell.data_type = 's'
                if full is not None:
                    note_lines = sum(max(1, len(TextWrapper(width=95).wrap(line))) for line in full.split('\n'))
                    cell.comment = Comment(full, 'Full reader text', width=760, height=max(180, note_lines * 17 + 30))
            cell.alignment = wrapped
            cell.font = link_font if key == 'source_url' else body_font
            if number % 2 == 1:
                cell.fill = band_fill
        sheet.row_dimensions[number].height = max(45, row_lines * LINE_HEIGHT + 8)
        source_cell = sheet.cell(number, len(COLUMNS))
        source_cell.hyperlink = prepared['source_url']
        if prepared['limitation']:
            source_cell.comment = Comment(prepared['limitation'], 'Source preparation')

    if sheet.max_row == 1:
        print('No reportable agreements or transactions in the completed exhibits. No workbook written.')
        return
    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    atomic_bytes(destination, output.getvalue())
    print(f'Wrote {sheet.max_row - 1} agreement summaries to {destination}')


def sec_user_agent():
    return (os.environ.get('ROYALTY_SEC_UA')
            or (Path.home() / '.config/royalty-research/sec_user_agent').read_text().strip())


def legacy_exclusion(run, document):
    """Run the explicitly selected version-4 gate on a frozen KEEP."""
    prepared = read_json(run / 'prepared.json')
    paragraphs, parser = parse_document(document.body, Path(urlsplit(document.url).path).name)
    mapping = map_contract(paragraphs, {'document_id': prepared['document_id'], 'source_url': document.url},
                           raw_hash=prepared['source_sha256'], parser_type=parser)
    audit = audit_screen(run, '\n'.join(p['text'] for p in mapping['passages']), document.body, prepared,
                         verified_identity=True, prompt_sha256=sha256((run / 'prompt.txt').read_bytes()))
    return record_exclusion(run, audit)


def batch(start, end, limit, *, execute=False, gics_reference=None, exclude_royalty_screen=None,
          urls=None, output_root=None):
    if urls is None and (not 0 <= (end - start).days < 31 or limit < 1):
        raise ValueError('Provide an inclusive date range of 1 to 31 days and a positive exhibit limit.')
    if exclude_royalty_screen is not None and (not execute or exclude_royalty_screen != SCREEN_VERSION):
        raise ValueError(f'Exclusions require --go and the screen version {SCREEN_VERSION}.')

    screen = frozen.load_screen()
    agent = sec_user_agent()
    client = SECClient(agent)
    fetcher = screen.Fetcher(agent)
    if urls is None:
        prefix = f'runs_summary_{start}_{end}_{datetime.now():%H%M%S}_'
    else:
        prefix = 'runs_frozen_prescreen_'
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=output_root or Path.cwd()))
    print(f'Batch folder: {root}', flush=True)
    log = {'notice': frozen.DRAFT, 'prototype_root': str(frozen.PROTOTYPE), 'sha256_before': frozen.FREEZE,
           'documents': [], 'preparation_failures': [], 'errors': [], 'workbook': None,
           'legacy_exclusion': exclude_royalty_screen, 'execute': execute}
    prepared = []
    completed = []
    try:
        if urls is None:
            ranked = sorted(discover(client, ['royalty rate', 'license agreement', 'royalties'], start, end),
                            key=candidate_rank)
            candidates = list(dict.fromkeys(item['source_url'] for item in ranked if item.get('source_url')))
            candidate_cap = limit * DOWNLOADS_PER_AGREEMENT
            print(f'SEC candidates: {len(ranked)} ranked, {len(candidates)} unique URLs, '
                  f'at most {candidate_cap} attempted.', flush=True)
            candidates = candidates[:candidate_cap]
        else:
            candidates = []
            for url in urls:
                try:
                    documents, warnings = frozen.filing_documents(screen, fetcher, url)
                    candidates.extend(documents)
                    log['errors'].extend(warnings)
                except (OSError, ValueError) as exc:
                    log['errors'].append(str(exc))
            candidates = list(dict.fromkeys(candidates))
        if not candidates:
            raise ValueError('No candidate documents to prepare.')

        reference_file = gics_reference or (SAVED_GICS if SAVED_GICS.is_file() else None)
        reference = ((reference_file.read_bytes(), GICS_URLS[1]) if reference_file else download_gics())
        print(f'Royalty screening mode: frozen{f" and opt-in {SCREEN_VERSION}" if exclude_royalty_screen else ""}.',
              flush=True)
        for url in candidates:
            document = None
            run = root / f'exhibit-{len(prepared) + 1:03}'
            try:
                document = fetcher.get(url)
                if document.issue:
                    raise ParseError(document.issue.detail)
                prepare(url, run, agent, client=frozen.DownloadedSource(document), reference=reference,
                        audit_royalty_screen=False)
            except (ValueError, OSError, SECRequestError) as exc:
                unreadable = document is None or isinstance(exc, (ParseError, UnicodeError, OSError, SECRequestError))
                if document is not None and not unreadable:
                    _, issue = screen.parse(document)
                    unreadable = bool(issue and issue.reason != screen.OTHER_UNCERTAINTY)
                failure = {'source_url': url, 'error': str(exc), 'extractor_status': 'not_sent',
                           'flags': ['unreadable_source'] if unreadable else []}
                if unreadable:
                    log['documents'].append(dict(failure, decision='REVIEW', prescreen_decision=None,
                                                 captured_rate_text='', captured_excerpt='',
                                                 evidence_pointer='', skip_reason=''))
                else:
                    log['preparation_failures'].append(failure)
                print(f'Preparation rejected {url}: {exc}', file=sys.stderr)
                continue
            prepared.append((run, document))
            print(f'Prepared {len(prepared)}/{limit if limit is not None else len(candidates)}: {url}', flush=True)
            if len(prepared) == limit:
                break

        ready = []
        for number, (run, document) in enumerate(prepared, 1):
            try:
                row = frozen.screen_document(screen, document, number)
            except Exception as exc:
                row = {'source_url': document.url, 'prescreen_decision': None, 'decision': 'REVIEW',
                       'captured_rate_text': '', 'captured_excerpt': '', 'evidence_pointer': '',
                       'flags': ['pointer_uncheckable'], 'skip_reason': '', 'extractor_status': 'not_sent',
                       'error': f'{type(exc).__name__}: {exc}'}
                log['errors'].append(row['error'])
            log['documents'].append(row)
            print(f'{row["decision"]} {document.url} {", ".join(row["flags"])}', flush=True)
            if row['decision'] == 'KEEP':
                ready.append((run, document, row))
        if not prepared:
            raise ValueError('No exhibit passed preparation in the candidate sample.')
        if not execute:
            print(f'Prepared {len(prepared)} exhibit(s). Add --go to run Codex and write Excel.')
        else:
            excluded = 0
            for run, document, row in ready:
                try:
                    if exclude_royalty_screen and legacy_exclusion(run, document):
                        excluded += 1
                        row['extractor_status'] = 'excluded_by_royalty_screen.4'
                        print(f'Excluded {run.name} before reading. Evidence: {run / "royalty_exclusion.json"}')
                        continue
                    row['extractor_status'] = 'started'
                    read(run)
                except Exception as exc:
                    row['extractor_status'] = 'error'
                    row['extractor_error'] = f'{type(exc).__name__}: {exc}'
                    log['errors'].append(f'{run.name}: {row["extractor_error"]}')
                    if not isinstance(exc, OutputError):
                        break
                else:
                    row['extractor_status'] = 'completed'
                    completed.append(run)
            if completed:
                name = ('Royalty_Agreement_Summary.xlsx' if len(completed) + excluded == len(ready)
                        else 'Royalty_Agreement_Summary_partial.xlsx')
                workbook = root / name
                write_workbook(completed, workbook)
                if workbook.is_file():
                    log['workbook'] = str(workbook)
    except Exception as exc:
        log['errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        log['prepared_count'] = len(prepared)
        try:
            frozen.verified_sources()
            log['sha256_after'] = frozen.FREEZE
        except (OSError, ValueError) as exc:
            log['errors'].append(f'Final freeze check failed: {exc}')
        path = root / 'screening_log.json'
        with path.open('x', encoding='utf-8') as handle:
            json.dump(log, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        print(f'Screening log: {path}', flush=True)
    for error in log['errors']:
        print(error, file=sys.stderr)
    return int(bool(log['errors']))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='step', required=True)
    prep = commands.add_parser('prepare', help='Download, screen and prepare the full SEC exhibit')
    prep.add_argument('url')
    prep.add_argument('--user-agent', default=os.environ.get('ROYALTY_SEC_UA'))
    prep.add_argument('--source-file', type=Path, help='Use a saved copy of the exhibit at this URL')
    prep.add_argument('--gics-reference', type=Path, help='Use a saved copy of the official MSCI workbook')
    reader = commands.add_parser('read', help='Read with ChatGPT-signed-in Codex and save the raw answer')
    writer = commands.add_parser('write', help='Map the saved answer into one Excel row per agreement')
    sampler = commands.add_parser('batch', prog='./royalty-summary.sh',
                                  help='Run the 16-column workflow for a dated SEC sample')
    sampler.add_argument('start', type=date.fromisoformat)
    sampler.add_argument('end', type=date.fromisoformat)
    sampler.add_argument('max_exhibits', type=int)
    sampler.add_argument('--go', action='store_true', help='Run Codex and write the workbook')
    sampler.add_argument('--exclude-royalty-screen', choices=(SCREEN_VERSION,),
                         help='Explicitly opt in to this screen version for one --go batch')
    sampler.add_argument('--gics-reference', type=Path, help='Use a saved copy of the official MSCI workbook')
    for command in (prep, reader, writer):
        command.add_argument('--run', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.step == 'prepare':
            user_agent = args.user_agent
            if args.source_file is None and not user_agent:
                user_agent = sec_user_agent()
            prepare(args.url, args.run, user_agent, args.source_file, args.gics_reference)
        elif args.step == 'read':
            read(args.run)
        elif args.step == 'write':
            write(args.run)
        else:
            return batch(args.start, args.end, args.max_exhibits, execute=args.go, gics_reference=args.gics_reference,
                  exclude_royalty_screen=args.exclude_royalty_screen)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'{args.step}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
