"""Prepare, read, and export SEC exhibits as commercial terms summaries."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from .discovery import discover
from .m13_production import DOWNLOADS_PER_AGREEMENT, candidate_rank, licence_gate
from .m13_research_export import estimate_row_height
from .m4_operator import _command, _preflight_subscription, _safe_environment
from .m7_triage import triage_document
from .mapping import map_contract
from .parsing import parse_document
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


def prepare(url, run, user_agent, source_file=None, gics_reference=None, *, client=None, reference=None):
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
    atomic_json(run / 'prepared.json', {
        'document_id': document_id, 'source_url': url, 'source_sha256': sha256(raw),
        'parser': parser, 'screening': gate, 'priority': priority,
        'passages': len(mapping['passages']), 'prompt_chars': len(prompt), 'limitation': limitation,
        'gics_reference_url': reference_url, 'gics_reference_sheet': GICS_SHEET,
    })
    print(f'Prepared one prompt with {len(mapping["passages"])} passages and {len(prompt):,} characters.')
    if limitation:
        print(limitation)


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


def agreement_rows(runs):
    for run in runs:
        prepared = read_json(run / 'prepared.json')
        names = gics_names((run / 'gics_reference.xlsx').read_bytes())
        for agreement in read_json(run / 'raw_response.txt')['agreements']:
            yield agreement, prepared, names


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
    wrapped = Alignment(vertical='top', wrap_text=True)
    for number, (_, _, width) in enumerate(COLUMNS, 1):
        sheet.column_dimensions[get_column_letter(number)].width = width
        cell = sheet.cell(1, number)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = header_border
        cell.alignment = Alignment(vertical='center', wrap_text=True)
    sheet['E1'].comment = Comment('Analytical mapping of the licensed activity using the March 2023 GICS hierarchy. '
                                  'This does not classify the contracting companies.', 'Source preparation')

    widths = [width * 0.9 for _, _, width in COLUMNS]
    for number, (agreement, prepared, names) in enumerate(agreement_rows(runs), 2):
        fields = dict(agreement, industry=gics_path(agreement['gics_code'], names), source_url='Original document')
        row = [fields[key] for _, key, _ in COLUMNS]
        sheet.row_dimensions[number].height = estimate_row_height(row, widths, minimum=45, maximum=409)
        for column, (_, key, _) in enumerate(COLUMNS, 1):
            cell = sheet.cell(number, column)
            value = fields[key]
            if key == 'agreement_date':
                cell.value = date.fromisoformat(value) if value else None
                cell.number_format = 'yyyy-mm-dd'
            else:
                cell.value = value
                cell.data_type = 's'
            cell.alignment = wrapped
            cell.font = link_font if key == 'source_url' else body_font
            if number % 2 == 1:
                cell.fill = band_fill
        source_cell = sheet.cell(number, len(COLUMNS))
        source_cell.hyperlink = prepared['source_url']
        if prepared['limitation']:
            source_cell.comment = Comment(prepared['limitation'], 'Source preparation')

    sheet.auto_filter.ref = sheet.dimensions
    output = BytesIO()
    workbook.save(output)
    atomic_bytes(destination, output.getvalue())
    print(f'Wrote {sheet.max_row - 1} agreement summaries to {destination}')


def sec_user_agent():
    return (os.environ.get('ROYALTY_SEC_UA')
            or (Path.home() / '.config/royalty-research/sec_user_agent').read_text().strip())


def batch(start, end, limit, *, execute=False, gics_reference=None):
    if end < start or (end - start).days >= 31:
        raise ValueError('Provide an inclusive date range of 1 to 31 days.')
    if limit < 1:
        raise ValueError('The exhibit limit must be positive.')

    agent = sec_user_agent()
    client = SECClient(agent)
    candidates = discover(client, ['royalty rate', 'license agreement', 'royalties'], start, end)
    ranked = sorted(candidates, key=candidate_rank)
    urls = list(dict.fromkeys(item['source_url'] for item in ranked if item.get('source_url')))
    if not urls:
        raise ValueError('SEC discovery returned no exhibit URLs for those dates.')

    reference_file = gics_reference or (SAVED_GICS if SAVED_GICS.is_file() else None)
    reference = ((reference_file.read_bytes(), GICS_URLS[1]) if reference_file else download_gics())
    prefix = f'runs_summary_{start}_{end}_{datetime.now():%H%M%S}_'
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=Path.cwd()))
    print(f'Batch folder: {root}', flush=True)
    prepared = []
    for url in urls[:limit * DOWNLOADS_PER_AGREEMENT]:
        run = root / f'exhibit-{len(prepared) + 1:03}'
        try:
            prepare(url, run, agent, client=client, reference=reference)
        except (ValueError, SECRequestError) as exc:
            print(f'Skipped {url}: {exc}', file=sys.stderr)
            continue
        prepared.append(run)
        print(f'Prepared {len(prepared)}/{limit}: {url}', flush=True)
        if len(prepared) == limit:
            break
    if not prepared:
        raise ValueError('No exhibit passed preparation in the candidate sample.')
    if not execute:
        print(f'Prepared {len(prepared)} exhibit(s). Add --go to run Codex and write Excel.')
        return

    completed = []
    try:
        for run in prepared:
            read(run)
            completed.append(run)
    finally:
        if completed:
            name = 'Royalty_Agreement_Summary.xlsx' if len(completed) == len(prepared) else 'Royalty_Agreement_Summary_partial.xlsx'
            write_workbook(completed, root / name)


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
            batch(args.start, args.end, args.max_exhibits, execute=args.go, gics_reference=args.gics_reference)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f'{args.step}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
