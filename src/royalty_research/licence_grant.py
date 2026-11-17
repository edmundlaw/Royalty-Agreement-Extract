"""Zero-AI text signals: does a document grant a licence, and what is its title (v0.13.7).

Used by the candidate gate (`m13_production.licence_gate`) and by the benchmark rule in the
research export, so both use the same wording rules.
"""
from __future__ import annotations
import re

# Each pattern is one kind of licence-grant wording. A document's score is the number of matches.
_SENT = r'[^.;\n]{0,200}?'      # stay inside one sentence / clause
GRANT_PATTERNS = (
    re.compile(r'\bgrant(?:s|ed|ing)?\b' + _SENT + r'\blicen[cs]es?\b', re.I),
    re.compile(r'\bhereby\s+(?:\w+\s+){0,3}?licen[cs]es?\b', re.I),
    re.compile(r'\b(?:non-?\s?exclusive|exclusive|sole|co-exclusive)\b[\w,\s\-]{0,60}?\blicen[cs]e\b', re.I),
    re.compile(r'\blicen[cs]ed\s+(?:patents?|products?|technolog(?:y|ies)|marks?|trademarks?|ip|intellectual|'
               r'software|know-?how|materials?|compounds?|rights|property|intangibles?)\b', re.I),
    re.compile(r'\broyalty-?\s?bearing\s+(?:\w+\s+){0,2}?licen[cs]e\b', re.I),
)

# Opening lines that are legends, not the title.
_LEGEND = re.compile(r'^[\s\u200b\ufeff]*(?:exhibit\b|execution\s+(?:version|copy)|final\s+(?:execution\s+)?(?:copy|form|version)|'
                     r'conformed\s+copy|confidential|certain\s+(?:\w+\s+){0,2}information|\[\s*(?:\*|redacted)|\(?redacted\)?\b|'
                     r'pursuant\s+to\s+item|portions?\s+of|\*\*\*|draft\b|_{3,}|-{3,}|\(?see\s+)', re.I)
_DOC_TYPE = re.compile(r'agreement|contract|term\s+sheet|amendment|lease|licen[cs]e|indenture|letter|assignment', re.I)
LICENCE_TYPE = re.compile(r'licen[cs]|royalt|franchis|collaborat', re.I)
NON_LICENCE_TYPE = re.compile(
    r'\b(?:services?|purchase|loan|credit|security|guarant(?:y|ee)|employment|consulting|separation|settlement|'
    r'assignment|merger|underwriting|indenture|lease|sublease|supply|joint\s+venture|subscription|pledge|'
    r'mortgage)\b', re.I)


def grant_hits(text: str) -> int:
    """Number of licence-grant phrases in the text (all five wording families, summed)."""
    return sum(len(p.findall(text or '')) for p in GRANT_PATTERNS)


def document_title(passages, window=1500) -> str:
    """Title from the opening ~1,500 characters: the first short non-legend passage that names a document type (plus one more if it does not).

    Falls back to the first 100 characters of the first non-legend passage (e.g. an opening
    'AMENDMENT No. 2, dated as of ...' sentence).
    """
    seen = 0; short = []; first_long = ''
    for p in passages:
        t = ' '.join(str(p.get('text', '')).split())
        if seen >= window: break
        seen += len(t) + 1
        if not t or _LEGEND.match(t): continue
        if len(t) <= 120:
            short.append(t)
            # one line naming the document type is the title; otherwise (e.g. "ABC Inc." / "LICENSE") take one more
            if len(short) == 2 or _DOC_TYPE.search(t): break
        elif not first_long and t[:1].isupper():   # a wrapped legend fragment starts in lower case
            first_long = t[:100]
            if not short: break
    return ' '.join(short) or first_long


def title_kind(title: str) -> str:
    """LICENCE, NON_LICENCE or UNKNOWN. A licence/royalty/collaboration/franchise word wins."""
    if LICENCE_TYPE.search(title or ''): return 'LICENCE'
    if NON_LICENCE_TYPE.search(title or ''): return 'NON_LICENCE'
    return 'UNKNOWN'
