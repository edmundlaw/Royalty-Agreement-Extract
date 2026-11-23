"""Load the frozen pre-screen and check evidence against extractor text."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
import sys
from types import ModuleType
import unicodedata
from urllib.parse import parse_qs, urldefrag, urlsplit

from .parsing import parse_document


PROTOTYPE = Path(__file__).resolve().parents[3] / 'royalty_prescreen_prototype' / 'validation_v3'
FREEZE = {
    'pdf_source': 'a4c6620e022e8d41014d520ee6ee315eac07aaac5f912c5526ac9531edb73bdf',
    'prescreen': '45f4976b3799b74c8de93cda01a026254093d5cdec3c8e279b9be7aa794c8369',
}
DRAFT = 'All outputs, including the workbook, are drafts. Manually confirm rates against the original SEC filings before use.'
NPI = re.compile(r'\b(?:net[ -]+profits?[ -]+interests?|overriding[ -]+royalt(?:y|ies))\b')


def verified_sources():
    sources = {}
    for name, expected in FREEZE.items():
        path = PROTOTYPE / f'{name}.py'
        body = path.read_bytes()
        observed = sha256(body).hexdigest()
        if observed != expected:
            raise ValueError(f'Frozen code mismatch at {path}: {observed}; expected {expected}')
        sources[name] = (path, body)
    return sources


def load_screen():
    if all(getattr(sys.modules.get(name), '__freeze_sha256__', None) == FREEZE[name] for name in FREEZE):
        verified_sources()
        return sys.modules['prescreen']
    # Execute the verified source bytes directly, so stale bytecode or the
    # similarly named parent implementation cannot supply screening rules.
    for name, (path, body) in verified_sources().items():
        if name in sys.modules:
            raise RuntimeError(f'Module name already in use: {name}')
        module = ModuleType(name)
        module.__file__ = str(path)
        sys.modules[name] = module
        exec(compile(body, str(path), 'exec'), module.__dict__)
        module.__freeze_sha256__ = FREEZE[name]
    return sys.modules['prescreen']


def normalize(value):
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def screen_document(screen, document, number):
    url = document.url
    decision = screen.decide(str(number), url, (document,))
    parsed, issue = screen.parse(document)
    screen_text = ' '.join(block.text for block in parsed.blocks)
    own_text = ''
    source_error = ''
    if issue and issue.reason != screen.OTHER_UNCERTAINTY:
        source_error = issue.detail
    elif parsed.hidden or '\ufffd' in screen_text:
        source_error = 'Unclosed hidden section or replacement characters in source text'
    try:
        paragraphs, _ = parse_document(document.body, Path(urlsplit(url).path).name)
        own_text = normalize(' '.join(paragraphs))
        if not own_text or '\ufffd' in own_text:
            source_error = source_error or 'Extractor text is empty or contains replacement characters'
    except (ValueError, RuntimeError, AssertionError) as exc:
        source_error = source_error or str(exc)

    flags = []
    outcome = decision.decision
    if source_error:
        flags.append('unreadable_source')
        outcome = 'REVIEW'
    if decision.decision == 'KEEP':
        evidence_url, separator, _ = decision.evidence_location.partition(' # ')
        excerpt = normalize(decision.rate_excerpt)
        if source_error or issue or not separator or evidence_url != url or not excerpt:
            flags.append('pointer_uncheckable')
            outcome = 'REVIEW'
        elif excerpt in own_text:
            flags.append('pointer_ok')
        else:
            flags.append('pointer_mismatch')
            outcome = 'REVIEW'
    if outcome == 'SKIP' and NPI.search(normalize(screen_text) + ' ' + own_text):
        flags.append('npi_notice')

    return {
        'source_url': url,
        'prescreen_decision': decision.decision,
        'decision': outcome,
        'captured_rate_text': decision.rate_text,
        'captured_excerpt': decision.rate_excerpt,
        'evidence_pointer': decision.evidence_location,
        'flags': flags,
        'skip_reason': decision.primary_reason if decision.decision == 'SKIP' else '',
        'prescreen_reason': decision.primary_reason,
        'prescreen_flags': decision.secondary_flags,
        'prescreen_caveat': decision.caveat,
        'source_issue': source_error or (issue.detail if issue else ''),
        'extractor_status': 'not_sent',
    }


def direct_url(url):
    parts = urlsplit(url)
    if parts.path in {'/ix', '/ixviewer/doc/action'} and parts.hostname in {'www.sec.gov', 'sec.gov'}:
        document, = parse_qs(parts.query).get('doc', [''])
        if document.startswith('/Archives/'):
            return f'https://{parts.hostname}{document}'
    return urldefrag(url)[0]


def filing_documents(screen, fetcher, url):
    url = direct_url(url)
    if not screen.sec_url(url):
        raise ValueError(f'Expected an SEC Archives document or filing index URL: {url}')
    parts = urlsplit(url)
    filing = screen.SEC_PATH.match(parts.path)
    accession = filing[2]
    dashed = f'{accession[:10]}-{accession[10:12]}-{accession[12:]}'
    is_index = parts.path.endswith(('-index.htm', '-index.html'))
    index_url = url if is_index else f'https://{parts.netloc}{filing[0]}{dashed}-index.htm'
    index, issue = screen.parse(fetcher.get(index_url))
    if issue:
        if is_index:
            raise ValueError(f'{index_url}: {issue.detail}')
        return [url], [f'Filing index unavailable for {url}. Screened only the supplied document. {issue.detail}']
    primary, attachments = screen.filing_links(index, index_url)
    if is_index or parts.path in {urlsplit(item).path for item in primary}:
        if not primary and not attachments:
            raise ValueError(f'No candidate document links in {index_url}')
        return primary + attachments, []
    return [url], []


class DownloadedSource:
    """Hand the unchanged bytes from the screened response to extractor.prepare."""

    def __init__(self, document):
        self.document = document

    def fetch(self, url):
        if url != self.document.url:
            raise ValueError(f'Extractor requested a different document: {url}')
        return self.document.body
