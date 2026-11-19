"""M13 two-reader check.

Python no longer tries to judge what a number in a contract means. It does two
things it can do with certainty:

1. SOURCE CHECK (one reading): every quotation is an exact part of the cited
   passage, every recorded number appears in its quotation, every record has
   evidence, and every flagged passage has been accounted for.
2. READER COMPARISON (optional): a second, independent model reads the same
   document blind. The two readings are aligned on what they cite (passage and
   number), not on wording, and every difference is listed.

The second reading is optional. Without it the workbook says so plainly
(SINGLE_READER_NOT_CHECKED). It can be added later for selected agreements.

No model API is used. Model calls go through the M4 subscription CLI runner.
"""
from __future__ import annotations

import json
import re
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .mapping import validate_map
from .storage import atomic_bytes, atomic_json, json_bytes, read_json, sha256, utc_now

M13_PROFILE = 'M13_TWO_READER'
M13_VALIDATOR_REVISION = 'm13.0-source-check-and-two-reader-comparison'
RUN_SCHEMA = 'm13-run.1'

STATE_MEANING = {
    'TWO_READERS_AGREE': 'Two independent AI readings recorded the same rates, tiers, minimums and caps from the same clauses.',
    'TWO_READERS_AGREE_ON_NUMBERS': 'Both readings found the same numbers in the same clauses but arranged some of them differently (for example a rate versus an adjustment). See Reader Differences.',
    'TWO_READERS_DIFFER': 'The two readings differ on at least one rate, tier, threshold, minimum, cap or sublicensing share. Check the listed clauses before use.',
    'SINGLE_READER_NOT_CHECKED': 'One AI reading only. Quotes and numbers were checked against the source; completeness was not checked by a second reading.',
    'SOURCE_CHECK_FAILED': 'The reading failed the source check (a quote or number is not in the cited text, or a record has no evidence). Do not use without correction.',
    'SECOND_READER_FAILED_SOURCE_CHECK': 'The second reading failed its own source check, so the comparison is unreliable. Treat as a single reading.',
}

# ---------------------------------------------------------------------------
# Numbers in text
# ---------------------------------------------------------------------------
_UNITS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
          'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
          'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19}
_TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
_SCALES = {'hundred': 100, 'thousand': 1000, 'million': 10 ** 6, 'billion': 10 ** 9}
_FRACTIONS = {'half': Decimal('0.5'), 'quarter': Decimal('0.25'), 'quarters': Decimal('0.25')}
_WORDS = sorted(list(_UNITS) + list(_TENS) + list(_SCALES) + list(_FRACTIONS) + ['and'], key=len, reverse=True)
_WORD_RUN = re.compile(r'\b(?:' + '|'.join(_WORDS) + r')(?:(?:\s*-\s*|\s+)(?:' + '|'.join(_WORDS) + r'))*\b', re.I)
_DIGITS = re.compile(r'(?<![\w.,])(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?![\w])')
_PCT_AFTER = re.compile(r'\s*(?:%|per\s*cent\b|percent\b)', re.I)
_SCALE_AFTER = re.compile(r'\s*(thousand|million|billion)\b', re.I)
_DOLLARS_AFTER = re.compile(r'\s*(?:\(\s*)?(?:u\.?s\.?\s*)?dollars?\b', re.I)
_DOLLAR_BEFORE = re.compile(r'(?:\$|usd)\s*$', re.I)


def _norm(value: Decimal) -> str:
    text = format(value.normalize(), 'f')
    return text if text != '-0' else '0'


def _words_value(run: str):
    """Value of a run of English number words; None if it is not a number."""
    tokens = [t.lower() for t in re.split(r'[\s-]+', run.strip()) if t]
    while tokens and tokens[0] == 'and': tokens = tokens[1:]
    while tokens and tokens[-1] == 'and': tokens = tokens[:-1]
    if not tokens or all(t == 'and' for t in tokens): return None
    fraction = Decimal(0)
    if tokens[-1] in _FRACTIONS:
        unit = _FRACTIONS[tokens[-1]]
        count = 1
        tokens = tokens[:-1]
        if tokens and tokens[-1] in _UNITS:
            count = _UNITS[tokens[-1]]; tokens = tokens[:-1]
        if tokens and tokens[-1] == 'and': tokens = tokens[:-1]
        fraction = unit * count
    total = 0; current = 0; seen = False
    for t in tokens:
        if t == 'and': continue
        if t in _UNITS: current += _UNITS[t]; seen = True
        elif t in _TENS: current += _TENS[t]; seen = True
        elif t == 'hundred': current = (current or 1) * 100
        elif t in _SCALES: total += (current or 1) * _SCALES[t]; current = 0
        else: return None
    # "million" on its own (as in "$10 million" or "$[***] million") is not a number.
    if not seen and not fraction: return None
    return Decimal(total + current) + fraction


def numbers_in_text(text: str) -> list[dict]:
    """Every number in the text with its unit: PCT, USD or NUM. Digits and words."""
    found = []
    for m in _DIGITS.finditer(text):
        try: value = Decimal(m.group().replace(',', ''))
        except InvalidOperation: continue
        end = m.end()
        pct = _PCT_AFTER.match(text, end)
        if pct:
            found.append({'start': m.start(), 'end': pct.end(), 'unit': 'PCT', 'value': _norm(value)}); continue
        scale = _SCALE_AFTER.match(text, end)
        if scale:
            value *= _SCALES[scale.group(1).lower()]; end = scale.end()
        money = bool(_DOLLAR_BEFORE.search(text[max(0, m.start() - 6):m.start()])) or bool(_DOLLARS_AFTER.match(text, end))
        found.append({'start': m.start(), 'end': end, 'unit': 'USD' if money else 'NUM', 'value': _norm(value)})
    for m in _WORD_RUN.finditer(text):
        value = _words_value(m.group())
        if value is None: continue
        end = m.end()
        if _PCT_AFTER.match(text, end):
            unit = 'PCT'
        elif _DOLLARS_AFTER.match(text, end):
            unit = 'USD'
        else:
            unit = 'NUM'
        found.append({'start': m.start(), 'end': end, 'unit': unit, 'value': _norm(value)})
    found.sort(key=lambda x: (x['start'], x['end']))
    return found


def reader_value(value):
    """Numeric value of a field written by a reader, or None when it is not one number."""
    if value is None or isinstance(value, bool): return None
    if isinstance(value, (int, float, Decimal)):
        try: return _norm(Decimal(str(value)))
        except InvalidOperation: return None
    if not isinstance(value, str) or not value.strip(): return None
    plain = re.fullmatch(r'\s*(?:US\s*)?\$?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)\s*%?\s*', value, re.I)
    if plain:
        return _norm(Decimal(plain.group(1).replace(',', '')))
    # "Fifty Million Dollars ($[***])": the figure is redacted but the amount is stated in words. Drop the
    # redaction marker and read what is left; "$[***] million" leaves nothing and stays without a value.
    value = re.sub(r'\(?\s*(?:US\s*)?\$?\s*(?:\[\s*\*+\s*\]|\*{2,}|\[\s*redacted\s*\])\s*%?\s*\)?', ' ', value, flags=re.I)
    # Free text counts as a number only when it holds exactly one value and that value either leads the text
    # ("250000 exclusive", "less than $2,000,000", "1.5% per month") or is its only percentage or money amount.
    # A section reference inside a description ("2x (doubling of Section 4.1 rates)") does not count.
    text = value.strip()
    tokens = numbers_in_text(text)
    if not tokens or len({t['value'] for t in tokens}) != 1: return None
    first = tokens[0]
    leads = re.fullmatch(r'(?:[<>=~\u2264\u2265(\s]|up\s+to|at\s+least|at\s+most|less\s+than|greater\s+than|more\s+than|not\s+more\s+than|'
                         r'over|above|below|under|exceeding|approximately|about|or\s+equal\s+to|usd|us\$|\$)*', text[:first['start']], re.I)
    if leads or all(t['unit'] in ('PCT', 'USD') for t in tokens):
        return first['value']
    return None


def rate_number(record: dict, parent: dict | None = None):
    """A rate is a number only when its unit says so. '2 x the otherwise applicable rate' (unit FORMULA) is not 2%."""
    unit = record.get('rate_unit') or (parent or {}).get('rate_unit')
    if unit not in ('PERCENT', 'CURRENCY_PER_UNIT'): return None
    return reader_value(record.get('rate_value'))


# ---------------------------------------------------------------------------
# 1. Source check for one reading
# ---------------------------------------------------------------------------
def _loose(text: str) -> str:
    """Same words, ignoring letter case, spacing and typographic quote/dash variants."""
    import unicodedata
    text = unicodedata.normalize('NFKC', text)
    for a, b in (('\u201c', '"'), ('\u201d', '"'), ('\u2018', "'"), ('\u2019', "'"), ('\u2013', '-'), ('\u2014', '-')):
        text = text.replace(a, b)
    return ' '.join(text.split()).casefold()


def _evidence_index(mapping, extraction):
    passages = {p['passage_id']: p for p in mapping['passages']}
    index = {}
    for e in extraction.get('evidence') or []:
        if isinstance(e, dict) and isinstance(e.get('evidence_id'), str) and e['evidence_id'] not in index:
            index[e['evidence_id']] = e
    return passages, index


def _ids(*lists):
    out = []
    for value in lists:
        for eid in value or []:
            if isinstance(eid, str) and eid not in out: out.append(eid)
    return out


def _in_quotes(value, eids, index, percent=False):
    for eid in eids:
        quote = (index.get(eid) or {}).get('quote') or ''
        for token in numbers_in_text(quote):
            if token['value'] == value and (not percent or token['unit'] == 'PCT'):
                return True
    return False


def source_check(mapping: dict, extraction: dict) -> dict:
    """Certain checks only. No keyword judgement about what a clause means."""
    from .m2_schema_check import validate_shape
    errs, warns, checks = [], [], []
    def err(code, message, ref=None): errs.append({'code': code, 'message': message, 'ref': ref})
    def warn(code, message, ref=None): warns.append({'code': code, 'message': message, 'ref': ref})
    def done(name, codes): checks.append({'check': name, 'status': 'FAIL' if any(e['code'] in codes for e in errs) else 'PASS'})
    def report():
        return {'document_id': mapping.get('document_id') if isinstance(mapping, dict) else None,
                'schema': 'm13-source-check.1',
                'deterministic_status': 'FAIL' if errs else 'PASS_DETERMINISTIC_ONLY',
                'can_claim_complete': False, 'verification_scope': 'SOURCE_CHECK_ONLY',
                'errors': errs, 'warnings': warns, 'checks': checks,
                'notice': 'Checks that quotes and numbers are in the cited source and that records carry evidence. '
                          'It does not check that every term was found; that is the purpose of the second reader.'}
    if not isinstance(mapping, dict) or not isinstance(extraction, dict):
        err('M13_INVALID_INPUT', 'Map and extraction must both be objects'); return report()
    problems = validate_map(mapping)
    if problems:
        err('M13_INVALID_MAP', ', '.join(problems)); return report()
    for problem in validate_shape(extraction): err('M13_SCHEMA', problem)
    for key, expected in (('document_id', mapping['document_id']), ('source_text_sha256', mapping['text_sha256']),
                          ('source_url', mapping.get('source_url')), ('schema_version', 'm2.0')):
        if extraction.get(key) != expected: err('M13_BINDING', f'{key} does not match the mapped source', key)
    done('BOUND_TO_SOURCE', {'M13_BINDING', 'M13_SCHEMA'})
    passages, index = _evidence_index(mapping, extraction)
    seen = set()
    for e in extraction.get('evidence') or []:
        if not isinstance(e, dict) or not isinstance(e.get('evidence_id'), str) or not e.get('evidence_id'):
            err('M13_EVIDENCE_INVALID', 'Evidence entry has no ID'); continue
        eid = e['evidence_id']
        if eid in seen: err('M13_EVIDENCE_DUPLICATE', 'Evidence IDs must be unique', eid); continue
        seen.add(eid)
        pid, quote = e.get('passage_id'), e.get('quote')
        if pid not in passages:
            err('M13_EVIDENCE_PASSAGE_UNKNOWN', 'Evidence cites a passage that is not in the source', eid); continue
        text = passages[pid]['text']
        if not isinstance(quote, str) or not quote.strip():
            err('M13_QUOTE_NOT_IN_SOURCE', 'Quotation is not an exact part of the cited passage', eid)
        elif quote not in text:
            # Live case (KemPharm, Codex, 2026-11-15): "the table setting forth" quoted from "The table setting
            # forth". The words are in the source, so this is not a fabricated quote; it is recorded as a warning.
            if _loose(quote) in _loose(text):
                warn('M13_QUOTE_DIFFERS_IN_CASE_OR_SPACING', 'Quotation matches the passage except for letter case, spacing or quote marks', eid)
            else:
                err('M13_QUOTE_NOT_IN_SOURCE', 'Quotation is not an exact part of the cited passage', eid)
        if isinstance(quote, str) and quote.strip() and len(quote.strip()) < 8 and quote.strip() != text.strip() and quote in text:
            # v0.13.11: a short exact quote ("4%") is allowed (it is still checked as an exact part of the passage);
            # it is only weak evidence, so the record gets a warning instead of the whole document failing.
            warn('M13_QUOTE_VERY_SHORT', f'Quotation is only {len(quote.strip())} characters; prefer the shortest clause-level span '
                 'that shows the figure and its basis', eid)
    done('QUOTES_ARE_IN_SOURCE', {'M13_EVIDENCE_INVALID', 'M13_EVIDENCE_DUPLICATE', 'M13_EVIDENCE_PASSAGE_UNKNOWN',
                                 'M13_QUOTE_NOT_IN_SOURCE'})

    def known(eids, owner):
        ok = True
        for eid in eids:
            if eid not in index: err('M13_EVIDENCE_MISSING', 'Record cites an evidence ID that does not exist', f'{owner}:{eid}'); ok = False
        return ok

    def number(value, eids, owner, code, percent=False):
        val = reader_value(value)
        if val is None: return
        if not _in_quotes(val, eids, index, percent):
            err(code, f'Recorded number {value!r} is not in the quoted source text', owner)

    term_ids = set()
    for t in extraction.get('royalty_terms') or []:
        if not isinstance(t, dict): err('M13_RECORD_INVALID', 'Royalty term is not an object'); continue
        tid = t.get('term_id')
        if not isinstance(tid, str) or not tid or tid in term_ids:
            err('M13_RECORD_ID', 'Royalty term IDs must be present and unique', tid); continue
        term_ids.add(tid)
        tiers = [z for z in (t.get('tiers') or []) if isinstance(z, dict)]
        extras = [z for z in (t.get('conditions') or []) + (t.get('adjustments') or []) if isinstance(z, dict)]
        own = _ids(t.get('rate_evidence_ids'), t.get('evidence_ids'), t.get('base_evidence_ids'))
        everything = _ids(own, *[z.get('evidence_ids') for z in tiers], *[z.get('threshold_evidence_ids') for z in tiers],
                          *[z.get('evidence_ids') for z in extras])
        known(everything, tid)
        if not everything: err('M13_RECORD_WITHOUT_EVIDENCE', 'Royalty term has no source evidence', tid)
        number(rate_number(t), _ids(t.get('rate_evidence_ids'), t.get('evidence_ids')), tid,
               'M13_RATE_NOT_IN_QUOTE', percent=(t.get('rate_unit') == 'PERCENT'))
        for i, z in enumerate(tiers, 1):
            ref = f'{tid}:tier{i}'
            mine = _ids(z.get('evidence_ids'), z.get('threshold_evidence_ids'))
            if not mine: err('M13_RECORD_WITHOUT_EVIDENCE', 'Tier has no source evidence of its own', ref)
            number(rate_number(z, t), _ids(z.get('evidence_ids'), t.get('rate_evidence_ids'), t.get('evidence_ids')),
                   ref, 'M13_RATE_NOT_IN_QUOTE', percent=((z.get('rate_unit') or t.get('rate_unit')) == 'PERCENT'))
            for bound in ('lower', 'upper'):
                if bound == 'lower' and reader_value(z.get(bound)) == '0': continue   # "from zero" is implied, not quoted
                number(z.get(bound), _ids(z.get('threshold_evidence_ids'), z.get('evidence_ids'), t.get('evidence_ids')),
                       f'{ref}:{bound}', 'M13_THRESHOLD_NOT_IN_QUOTE')
    payment_ids = set()
    for p in extraction.get('other_payments') or []:
        if not isinstance(p, dict): err('M13_RECORD_INVALID', 'Payment is not an object'); continue
        pid = p.get('payment_id')
        if not isinstance(pid, str) or not pid or pid in payment_ids:
            err('M13_RECORD_ID', 'Payment IDs must be present and unique', pid); continue
        payment_ids.add(pid)
        eids = _ids(p.get('evidence_ids'))
        known(eids, pid)
        if not eids: err('M13_RECORD_WITHOUT_EVIDENCE', 'Payment has no source evidence', pid)
        val = reader_value(p.get('amount_value'))
        core_payment = _payment_group(p.get('kind')) == 'MINIMUM_OR_CAP'
        if val is not None and not core_payment and not _in_quotes(val, eids, index) and any(
                t['value'] == val for e in eids if (index.get(e) or {}).get('passage_id') in passages
                for t in numbers_in_text(passages[index[e]['passage_id']]['text'])):
            # Live case (FunctionalBrands, Sonnet, 2026-11-16): the quote stopped before "US$100,000.00" in the same
            # clause. For fees and other payments a number found in the cited passage is a short quote, not a
            # fabricated number. Rates, thresholds, minimums and caps must still be inside the quotation itself.
            warn('M13_AMOUNT_IN_PASSAGE_NOT_IN_QUOTE', f"Recorded number {p.get('amount_value')!r} is in the cited passage "
                 'but outside the quoted words', pid)
        else:
            number(p.get('amount_value'), eids, pid, 'M13_AMOUNT_NOT_IN_QUOTE')
    done('RECORDS_HAVE_EVIDENCE', {'M13_EVIDENCE_MISSING', 'M13_RECORD_WITHOUT_EVIDENCE', 'M13_RECORD_ID', 'M13_RECORD_INVALID'})
    done('NUMBERS_ARE_IN_QUOTES', {'M13_RATE_NOT_IN_QUOTE', 'M13_THRESHOLD_NOT_IN_QUOTE', 'M13_AMOUNT_NOT_IN_QUOTE'})

    reader = extraction.get('reader') if isinstance(extraction.get('reader'), dict) else {}
    reviewed = reader.get('reviewed_passage_ids') if isinstance(reader.get('reviewed_passage_ids'), list) else []
    if reader.get('read_scope') != 'FULL_DOCUMENT' or set(reviewed) != set(passages):
        err('M13_NOT_FULL_READ', 'The reading does not cover every passage of the document')
    cited = {e.get('passage_id') for e in index.values()}
    disposed = set()
    for d in extraction.get('dispositions') or []:
        if not isinstance(d, dict) or d.get('passage_id') not in passages:
            err('M13_DISPOSITION_UNKNOWN_PASSAGE', 'Disposition names a passage that is not in the source',
                d.get('passage_id') if isinstance(d, dict) else None); continue
        disposed.add(d['passage_id'])
    missing = [pid for pid in mapping.get('candidate_passages', []) if pid not in disposed and pid not in cited]
    if missing:
        err('M13_PASSAGE_NOT_ACCOUNTED', f'{len(missing)} flagged passages were neither cited nor given a disposition', missing[:15])
    done('EVERY_FLAGGED_PASSAGE_ACCOUNTED', {'M13_NOT_FULL_READ', 'M13_PASSAGE_NOT_ACCOUNTED', 'M13_DISPOSITION_UNKNOWN_PASSAGE'})
    agreement = extraction.get('agreement') if isinstance(extraction.get('agreement'), dict) else {}
    # Additional licensing fields are optional for legacy M13 recordings. When a
    # new extraction supplies a positive fact, require a real quoted source ID;
    # classification semantics are still an analyst/independent-reader judgement.
    header_refs = agreement.get('field_evidence') or {}
    inferred = agreement.get('licensed_ip_nature_basis') == 'INFERRED'
    for key in ('licensed_ip_nature', 'licensed_ip_components', 'licensed_ip_nature_details', 'sublicensing_rights', 'exclusivity_scope', 'related_party'):
        value = agreement.get(key)
        if value is None or (key == 'licensed_ip_components' and not value) or (key == 'licensed_ip_nature' and value == 'UNDETERMINED') or \
                (key == 'related_party' and value == 'NOT_STATED'):
            continue
        refs = _ids(header_refs.get(key))
        if key == 'licensed_ip_nature' and inferred and not refs:
            # An INFERRED nature may cite the context it was inferred from
            # (patent-term wording, the asset description) under a neighbouring field.
            refs = [r for k in ('licensed_ip_nature_details', 'licensed_ip', 'duration') for r in _ids(header_refs.get(k))]
        if key == 'licensed_ip_components' and not refs:
            # Same leniency as the nature: the components may be cited under licensed_ip_nature,
            # or (when INFERRED) under the context they were inferred from.
            refs = [r for k in (('licensed_ip_nature', 'licensed_ip_nature_details', 'licensed_ip', 'duration') if inferred
                                else ('licensed_ip_nature',)) for r in _ids(header_refs.get(k))]
        if key == 'licensed_ip_nature_details' and not refs:
            # The details only explain the nature; FIRST_READER rule 10 has the reader cite the evidence
            # under field_evidence.licensed_ip_nature (live OSR/VXM01 run, v0.13.7).
            refs = [r for k in ('licensed_ip_nature', 'licensed_ip_components', 'licensed_ip', 'duration') for r in _ids(header_refs.get(k))]
        known(refs, f'agreement.{key}')
        if not refs:
            err('M13_AGREEMENT_FIELD_WITHOUT_EVIDENCE',
                f'New licensing field {key} requires a quoted evidence ID', key)
    for i, item in enumerate(agreement.get('other_material_terms') or []):
        refs = _ids(item.get('evidence_ids'))
        known(refs, f'agreement.other_material_terms.{i}')
        if not refs:
            err('M13_AGREEMENT_FIELD_WITHOUT_EVIDENCE',
                'Other material terms require a quoted evidence ID', f'other_material_terms:{i}')
    done('ADDITIONAL_LICENSING_FIELDS_HAVE_EVIDENCE',
         {'M13_AGREEMENT_FIELD_WITHOUT_EVIDENCE', 'M13_EVIDENCE_MISSING'})
    for key in ('licensor', 'licensee'):
        if not agreement.get(key): warn('M13_PARTY_NOT_RECORDED', f'{key} was not recorded', key)
    if not term_ids and not payment_ids:
        warn('M13_NO_ECONOMIC_TERMS', 'No royalty term or payment recorded; this is not proof that none exists')
    return report()


# ---------------------------------------------------------------------------
# 2. Comparison of two readings
# ---------------------------------------------------------------------------
_SALES = {'PRODUCT_SALES', 'PER_UNIT', 'USAGE', 'REVENUE_SHARE'}
_MINCAP = {'MINIMUM_ROYALTY', 'CAP', 'MINIMUM', 'GUARANTEED_MINIMUM', 'MAXIMUM', 'FLOOR'}
_IGNORED_PAYMENTS = {'INTEREST', 'LATE_INTEREST', 'LATE_PAYMENT_INTEREST', 'AUDIT_FEE', 'PENALTY', 'AUDIT_THRESHOLD'}
_UNIT_RANK = {'PCT': 0, 'USD': 1, 'NUM': 2}


def _family_group(family):
    if family in _SALES: return 'SALES'
    if family == 'SUBLICENSING_RECEIPTS': return 'SUBLICENSING'
    return 'OTHER'


def _payment_group(kind):
    return 'MINIMUM_OR_CAP' if str(kind or '').upper() in _MINCAP else 'FEE_OR_OTHER'


def _anchor(value, eids, index, passages, percent=False):
    """Where in the source a recorded number sits: (passage, unit, value) keys."""
    keys = set()
    for eid in eids:
        e = index.get(eid) or {}
        pid = e.get('passage_id')
        hits = [t for t in numbers_in_text(e.get('quote') or '') if t['value'] == value and (not percent or t['unit'] == 'PCT')]
        if pid in passages and hits:
            unit = min((t['unit'] for t in hits), key=_UNIT_RANK.get)
            keys.add((pid, unit, value))
    if not keys:
        for eid in eids:
            pid = (index.get(eid) or {}).get('passage_id')
            if pid in passages:
                keys.add((pid, 'PCT' if percent else 'NUM', value)); break
    return keys


def reading_facts(mapping: dict, extraction: dict) -> dict:
    """What one reading recorded, expressed as source positions rather than wording."""
    passages, index = _evidence_index(mapping, extraction)
    valued = {}      # key -> list of role dicts
    valueless = []   # records that carry no single number (redacted, formula, pass-through)
    marker = re.compile(r'\[\s*\*+\s*\]|\*{2,}|redact', re.I)
    def redacted(*values): return any(v == 'REDACTED' or (isinstance(v, str) and marker.search(v)) for v in values)

    def use(keys, role):
        for key in keys: valued.setdefault(key, []).append(role)

    def cited(eids):
        return {(index.get(e) or {}).get('passage_id') for e in eids if (index.get(e) or {}).get('passage_id') in passages}

    for t in extraction.get('royalty_terms') or []:
        if not isinstance(t, dict): continue
        tid = t.get('term_id'); group = _family_group(t.get('family'))
        tiers = [z for z in (t.get('tiers') or []) if isinstance(z, dict)]
        term_eids = _ids(t.get('rate_evidence_ids'), t.get('evidence_ids'))
        rate = rate_number(t)
        if rate is not None:
            use(_anchor(rate, term_eids, index, passages, t.get('rate_unit') == 'PERCENT'),
                {'role': 'RATE', 'family': group, 'record': tid})
        elif not tiers:
            valueless.append({'role': 'RATE', 'family': group, 'record': tid, 'passages': cited(term_eids),
                              'redacted': redacted(t.get('disclosure_status'), t.get('rate_unit'), t.get('rate_value')),
                              'label': f"royalty term with no stated rate ({t.get('disclosure_status') or t.get('rate_unit') or 'no value'})"})
        for i, z in enumerate(tiers, 1):
            ref = f'{tid} tier {i}'
            tier_eids = _ids(z.get('evidence_ids'), z.get('threshold_evidence_ids'))
            rate = rate_number(z, t)
            if rate is not None:
                use(_anchor(rate, _ids(z.get('evidence_ids'), term_eids), index, passages,
                            (z.get('rate_unit') or t.get('rate_unit')) == 'PERCENT'),
                    {'role': 'RATE', 'family': group, 'record': ref, 'calculation': z.get('calculation')})
            else:
                valueless.append({'role': 'RATE', 'family': group, 'record': ref, 'passages': cited(tier_eids) or cited(term_eids),
                                  'redacted': redacted(z.get('rate_unit'), z.get('rate_value'), t.get('disclosure_status'), t.get('rate_unit')),
                                  'label': 'tier with no stated rate'})
            for bound in ('lower', 'upper'):
                val = reader_value(z.get(bound))
                if val is not None and not (bound == 'lower' and val == '0'):
                    use(_anchor(val, _ids(z.get('threshold_evidence_ids'), z.get('evidence_ids'), term_eids), index, passages),
                        {'role': 'THRESHOLD', 'record': ref})
        for kind, items, field in (('condition', t.get('conditions'), 'text'), ('adjustment', t.get('adjustments'), 'description')):
            for item in items or []:
                if not isinstance(item, dict): continue
                eids = _ids(item.get('evidence_ids'))
                for token in numbers_in_text(str(item.get(field) or '')):
                    if token['unit'] == 'NUM': continue
                    keys = {k for k in _anchor(token['value'], eids, index, passages, token['unit'] == 'PCT')
                            if any(q['value'] == token['value'] for e in eids
                                   for q in numbers_in_text((index.get(e) or {}).get('quote') or ''))}
                    use(keys, {'role': 'MODIFIER', 'record': f'{tid} {kind}'})
    for p in extraction.get('other_payments') or []:
        if not isinstance(p, dict) or str(p.get('kind') or '').upper() in _IGNORED_PAYMENTS: continue
        eids = _ids(p.get('evidence_ids')); group = _payment_group(p.get('kind'))
        val = reader_value(p.get('amount_value'))
        if val is not None:
            use(_anchor(val, eids, index, passages), {'role': 'PAYMENT', 'group': group, 'record': p.get('payment_id'), 'kind': p.get('kind')})
        else:
            valueless.append({'role': 'PAYMENT', 'group': group, 'record': p.get('payment_id'), 'passages': cited(eids),
                              'redacted': redacted(p.get('disclosure_status'), p.get('amount_value')),
                              'label': f"{str(p.get('kind') or 'payment').lower()} payment with no stated amount"})
    # Clauses this reader treated as economic: cited by any record, or given a royalty/payment disposition.
    used = set()
    for t in extraction.get('royalty_terms') or []:
        if not isinstance(t, dict): continue
        parts = [t] + [z for z in (t.get('tiers') or []) + (t.get('conditions') or []) + (t.get('adjustments') or []) if isinstance(z, dict)]
        for part in parts:
            used |= cited(_ids(part.get('evidence_ids'), part.get('rate_evidence_ids'), part.get('base_evidence_ids'),
                               part.get('threshold_evidence_ids')))
    for p in extraction.get('other_payments') or []:
        if isinstance(p, dict): used |= cited(_ids(p.get('evidence_ids')))
    for d in extraction.get('dispositions') or []:
        # ...or flagged as uncertain, redacted or a cross-reference: the reader noticed the clause. Only a clause
        # dismissed as background, unrelated or a definition counts as not seen as economic.
        if isinstance(d, dict) and set(d.get('categories') or []) & {'ROYALTY_TERM', 'OTHER_PAYMENT', 'UNCERTAIN',
                                                                      'CROSS_REFERENCE', 'REDACTED'}:
            used.add(d.get('passage_id'))
    return {'valued': valued, 'valueless': valueless, 'economic_passages': used}


def _party_tokens(name):
    drop = {'inc', 'incorporated', 'llc', 'ltd', 'limited', 'corp', 'corporation', 'company', 'co', 'the', 'a', 'an', 'of',
            'and', 'plc', 'lp', 'gmbh', 'ag', 'sa', 'delaware', 'its', 'affiliates', 'formerly', 'known', 'as'}
    return {w for w in re.findall(r'[a-z0-9]+', str(name or '').lower()) if w not in drop and len(w) > 1}


def _same_party(a, b):
    x, y = _party_tokens(a), _party_tokens(b)
    return bool(x and y and x & y)


def _describe(roles):
    parts = []
    for r in roles:
        if r['role'] == 'RATE':
            parts.append(f"royalty rate ({r['family'].lower()}) in {r['record']}")
        elif r['role'] == 'THRESHOLD':
            parts.append(f"tier threshold in {r['record']}")
        elif r['role'] == 'PAYMENT':
            parts.append(f"{str(r.get('kind') or 'payment').lower()} payment {r['record']}")
        else:
            parts.append(f"{r['record']}")
    return '; '.join(dict.fromkeys(parts)) or 'not recorded'


def compare_readers(mapping: dict, first: dict, second: dict) -> dict:
    """List every difference between two readings of the same mapped source.

    Levels: CORE (a rate, tier, threshold, minimum, cap or sublicensing share is
    recorded by one reader only, or the readers contradict each other on it),
    STRUCTURE (same number from the same clause, arranged differently) and NOTE
    (fees, milestones and side conditions recorded by one reader only).
    """
    passages = {p['passage_id']: p for p in mapping['passages']}
    fa, fb = reading_facts(mapping, first), reading_facts(mapping, second)
    differences = []; agreed = 0

    def excerpt(pid):
        return (passages.get(pid, {}).get('text') or '')[:300]

    def add(level, kind, pid, value, a, b, text):
        differences.append({'level': level, 'kind': kind, 'passage_id': pid, 'section': passages.get(pid, {}).get('section_guess'),
                            'value': value, 'first_reader': a, 'second_reader': b, 'description': text, 'source_excerpt': excerpt(pid)})

    def show(unit, value):
        if unit == 'PCT': return f'{value}%'
        whole, _, frac = value.partition('.')
        text = f'{int(whole):,}' + (f'.{frac}' if frac else '') if whole.lstrip('-').isdigit() else value
        return f'${text}' if unit == 'USD' else text

    def classes(roles): return {r['role'] for r in roles}

    def one_sided_level(roles):
        kinds = classes(roles)
        if 'RATE' in kinds or 'THRESHOLD' in kinds: return 'CORE'
        if any(r['role'] == 'PAYMENT' and r['group'] == 'MINIMUM_OR_CAP' for r in roles): return 'CORE'
        return 'NOTE'

    only_a = {}; only_b = {}
    for key in sorted(set(fa['valued']) | set(fb['valued'])):
        ra, rb = fa['valued'].get(key, []), fb['valued'].get(key, [])
        pid, unit, value = key
        if ra and not rb: only_a[key] = ra; continue
        if rb and not ra: only_b[key] = rb; continue
        ca, cb = classes(ra), classes(rb)
        if ('RATE' in ca) != ('RATE' in cb):
            other = cb if 'RATE' in ca else ca
            level = 'STRUCTURE' if 'MODIFIER' in other else 'CORE'
            add(level, 'ROLE_DIFFERS', pid, show(unit, value), _describe(ra), _describe(rb),
                f'{show(unit, value)} is a royalty rate for one reader and something else for the other.')
            continue
        if 'RATE' in ca:
            ga = {r['family'] for r in ra if r['role'] == 'RATE'}; gb = {r['family'] for r in rb if r['role'] == 'RATE'}
            if not ga & gb:
                level = 'CORE' if 'OTHER' not in ga | gb else 'STRUCTURE'
                add(level, 'FAMILY_DIFFERS', pid, show(unit, value), _describe(ra), _describe(rb),
                    f'{show(unit, value)}: the readers disagree on what the rate is charged on (sales versus sublicensing receipts).')
                continue
            known = {'MARGINAL', 'ALL_UNITS'}
            xa = {r.get('calculation') for r in ra} & known; xb = {r.get('calculation') for r in rb} & known
            if xa and xb and not xa & xb:
                add('CORE', 'CALCULATION_DIFFERS', pid, show(unit, value), '/'.join(sorted(xa)), '/'.join(sorted(xb)),
                    f'{show(unit, value)}: one reader applies the tier to the band only (marginal), the other to all sales.')
                continue
        elif ca != cb:
            add('STRUCTURE', 'ROLE_DIFFERS', pid, show(unit, value), _describe(ra), _describe(rb),
                f'{show(unit, value)} is recorded by both readers but in different kinds of record.')
            continue
        elif 'PAYMENT' in ca and not {r['group'] for r in ra if r['role'] == 'PAYMENT'} & {r['group'] for r in rb if r['role'] == 'PAYMENT'}:
            add('STRUCTURE', 'PAYMENT_KIND_DIFFERS', pid, show(unit, value), _describe(ra), _describe(rb),
                f'{show(unit, value)}: one reader records a minimum or cap, the other a fee or other payment.')
            continue
        agreed += 1
    # The same number quoted from two different places is agreement on the number.
    for ka in sorted(only_a):
        match = next((kb for kb in sorted(only_b) if kb[1:] == ka[1:] and classes(only_b[kb]) & classes(only_a[ka])), None)
        if match:
            add('NOTE', 'SAME_VALUE_DIFFERENT_CLAUSE', ka[0], show(ka[1], ka[2]), _describe(only_a[ka]),
                _describe(only_b[match]) + f' (cited from {match[0]})',
                f'Both readers recorded {show(ka[1], ka[2])} but cited different clauses.')
            del only_b[match]; only_a[ka] = None
    for side, table in (('first', only_a), ('second', only_b)):
        for key in sorted(table):
            roles = table[key]
            if not roles: continue
            pid, unit, value = key
            add(one_sided_level(roles), 'RECORDED_BY_ONE_READER', pid, show(unit, value),
                _describe(roles) if side == 'first' else 'not recorded', _describe(roles) if side == 'second' else 'not recorded',
                f'{show(unit, value)} was recorded by the {side} reader only.')
    # Records without a single number (redacted rates, formulas, pass-through obligations).
    free_b = list(fb['valueless'])
    def valued_overlap(facts, own, item):
        # The other reader gives a number in the same clause that this reader does not have: that
        # difference is already listed above, so the record without a value is not listed twice.
        return any(k[0] in item['passages'] and k not in own['valued'] and any(r['role'] == item['role'] for r in roles)
                   for k, roles in facts['valued'].items())
    def unmatched(side, item, other_facts, own_facts):
        if valued_overlap(other_facts, own_facts, item): return
        core = (item['role'] == 'RATE' and item['family'] != 'OTHER') or (item['role'] == 'PAYMENT' and item['group'] == 'MINIMUM_OR_CAP')
        pid = sorted(item['passages'])[0] if item['passages'] else None
        level = 'CORE' if core else 'NOTE'; kind = 'RECORDED_BY_ONE_READER'
        text = f"{item['label'][0].upper()}{item['label'][1:]}: recorded by the {side} reader only."
        # A record with no number that is not a redaction (a pass-through, a formula, a "no payment due" clause):
        # if the other reader also treated that clause as economic, they read it the same way and filed it differently.
        if core and not item['redacted'] and item['passages'] & other_facts['economic_passages']:
            level = 'STRUCTURE'; kind = 'SEPARATE_RECORD_BY_ONE_READER'
            text = (f"The {side} reader made a separate record ({item['label']}) from a clause that the other reader "
                    "also treated as economic but did not record separately.")
        add(level, kind, pid, 'no stated value',
            f"{item['label']} ({item['record']})" if side == 'first' else 'no separate record',
            f"{item['label']} ({item['record']})" if side == 'second' else 'no separate record', text)
    def same_kind(x, y): return x.get('family') == y.get('family') and x.get('group') == y.get('group')
    pairs = []; left = list(fa['valueless'])
    for strict in (True, False):          # like with like first, so the pairing does not depend on record order
        for item in list(left):
            options = [x for x in free_b if x['role'] == item['role'] and x['passages'] & item['passages']
                       and (same_kind(x, item) or not strict)]
            if not options: continue
            partner = max(options, key=lambda x: len(x['passages'] & item['passages']))
            free_b.remove(partner); left.remove(item); pairs.append((item, partner))
    for item in left: unmatched('first', item, fb, fa)
    for item, partner in pairs:
        pid = sorted(item['passages'] & partner['passages'])[0]
        if item['role'] == 'RATE' and item['family'] != partner['family'] and 'OTHER' not in {item['family'], partner['family']}:
            add('CORE', 'FAMILY_DIFFERS', pid, 'no stated value', f"{item['family'].lower()} ({item['record']})",
                f"{partner['family'].lower()} ({partner['record']})",
                'The readers disagree on what this rate is charged on (sales versus sublicensing receipts).')
        elif item['role'] == 'PAYMENT' and item['group'] != partner['group']:
            add('STRUCTURE', 'PAYMENT_KIND_DIFFERS', pid, 'no stated value', f"{item['label']} ({item['record']})",
                f"{partner['label']} ({partner['record']})", 'One reader records a minimum or cap, the other a fee or other payment.')
        else:
            agreed += 1
    for item in free_b: unmatched('second', item, fa, fb)
    # Compare the licensed rights themselves, not component order or a redundant singleton list.
    def ia_classification(agreement):
        nature = agreement.get('licensed_ip_nature')
        raw = agreement.get('licensed_ip_components')
        components = frozenset(raw) if isinstance(raw, list) else frozenset()
        if nature and nature not in {'MIXED', 'OTHER', 'UNDETERMINED'} and not components:
            components = frozenset((nature,))
        return nature, components

    ha = first.get('agreement') if isinstance(first.get('agreement'), dict) else {}
    hb = second.get('agreement') if isinstance(second.get('agreement'), dict) else {}
    ia_a, ia_b = ia_classification(ha), ia_classification(hb)
    if ia_a != ia_b:
        def ia_display(value):
            nature, components = value
            return (nature or 'not recorded') + (': ' + ', '.join(sorted(components)) if components else '')
        add('CORE', 'LICENSED_IP_DIFFERS', None, None, ia_display(ia_a), ia_display(ia_b),
            'The readers disagree on the nature or components of the licensed intellectual assets; review the original grant and definitions.')
    # Parties.
    if (ha.get('licensor') and hb.get('licensor') and ha.get('licensee') and hb.get('licensee')
            and not _same_party(ha['licensor'], hb['licensor']) and _same_party(ha['licensor'], hb['licensee'])
            and _same_party(ha['licensee'], hb['licensor'])):
        add('CORE', 'PARTIES_SWAPPED', None, None, f"licensor {ha['licensor']}", f"licensor {hb['licensor']}",
            'The readers name licensor and licensee the other way round.')
    else:
        for key in ('licensor', 'licensee'):
            if ha.get(key) and hb.get(key) and not _same_party(ha[key], hb[key]):
                add('NOTE', 'PARTY_DIFFERS', None, None, str(ha[key]), str(hb[key]), f'The readers name the {key} differently.')
    count = {level: sum(1 for d in differences if d['level'] == level) for level in ('CORE', 'STRUCTURE', 'NOTE')}
    order = {'CORE': 0, 'STRUCTURE': 1, 'NOTE': 2}
    differences.sort(key=lambda d: (order[d['level']], str(d['passage_id']), str(d['value'])))
    ra, rb = first.get('reader') or {}, second.get('reader') or {}
    return {'schema': 'm13-reader-comparison.1', 'document_id': mapping['document_id'],
            'first_reader': {'engine': ra.get('engine'), 'model': ra.get('model')},
            'second_reader': {'engine': rb.get('engine'), 'model': rb.get('model')},
            'independence': ('DIFFERENT_MODELS' if (ra.get('engine'), ra.get('model')) != (rb.get('engine'), rb.get('model'))
                             else 'SAME_MODEL_REPEATED'),
            'facts_both_recorded': agreed, 'core': count['CORE'], 'structure': count['STRUCTURE'], 'note': count['NOTE'],
            'differences': differences,
            'notice': 'Agreement of two AI readings lowers the chance of an omission; it is not proof of correctness.'}


def decide_state(first_check: dict, second_check: dict | None, comparison: dict | None) -> str:
    if first_check['deterministic_status'] != 'PASS_DETERMINISTIC_ONLY': return 'SOURCE_CHECK_FAILED'
    if comparison is None or second_check is None: return 'SINGLE_READER_NOT_CHECKED'
    if second_check['deterministic_status'] != 'PASS_DETERMINISTIC_ONLY': return 'SECOND_READER_FAILED_SOURCE_CHECK'
    if comparison['core']: return 'TWO_READERS_DIFFER'
    if comparison['structure']: return 'TWO_READERS_AGREE_ON_NUMBERS'
    return 'TWO_READERS_AGREE'


# ---------------------------------------------------------------------------
# 3. Run folder: prepare, call, finalise
# ---------------------------------------------------------------------------
def _root(path):
    p = Path(path).expanduser()
    if p.is_symlink(): raise ValueError('Run folder cannot be a symlink')
    return p


def _project(): return Path(__file__).resolve().parents[2]


def _plan_inputs():
    instructions = (_project() / 'prompts' / 'FIRST_READER.md').read_text(encoding='utf-8')
    schema = read_json(_project() / 'schemas' / 'm2_extraction.schema.json')
    return instructions, schema


def _load(root):
    root = _root(root)
    if not (root / 'm13_run.json').is_file(): raise ValueError('Not an M13 run folder')
    meta = read_json(root / 'm13_run.json')
    if sha256(json_bytes(meta)) != (root / 'm13_run.sha256').read_text().strip():
        raise ValueError('M13 run record was changed after it was created')
    mapping = read_json(root / 'source' / 'map.json')
    packet = read_json(root / 'source' / 'full_packet.json')
    if sha256(json_bytes(mapping)) != meta['map_sha256'] or sha256(json_bytes(packet)) != meta['packet_sha256']:
        raise ValueError('Source map or packet was changed after the run was prepared')
    return root, meta, mapping, packet


def prepare(mapping: dict, root, *, engine: str, model: str, check_engine: str | None = None,
            check_model: str | None = None, max_chars: int = 64000,
            reasoning_effort: str | None = None, check_reasoning_effort: str | None = None) -> dict:
    """Create the reading plan(s). No model call. The second reader is optional."""
    from .m2_packets import make_packets
    from .m4_operator import create_plan
    problems = validate_map(mapping)
    if problems: raise ValueError('Invalid source map: ' + repr(problems))
    if bool(check_engine) != bool(check_model): raise ValueError('Give both the second reader engine and model, or neither')
    if not 4000 <= max_chars <= 200000: raise ValueError('max_chars must be 4000-200000')
    root = _root(root)
    if root.exists(): raise FileExistsError('Run folder already exists; never overwrite a prior run')
    root.parent.mkdir(parents=True, exist_ok=True)
    m13 = dict(mapping); m13['quality_control_profile'] = M13_PROFILE
    packet = make_packets(m13, mode='full', max_chars=max_chars)
    if packet['included_passage_ids'] != [p['passage_id'] for p in m13['passages']]:
        raise AssertionError('The reading plan does not cover the whole document')
    instructions, schema = _plan_inputs()
    with tempfile.TemporaryDirectory(prefix='.m13-preparing-', dir=root.parent) as td:
        work = Path(td) / 'run'; (work / 'source').mkdir(parents=True)
        atomic_json(work / 'source' / 'map.json', m13)
        atomic_json(work / 'source' / 'full_packet.json', packet)
        create_plan(m13, packet, work / 'reader_a', engine=engine, model=model, instructions=instructions, schema=schema,
                    reasoning_effort=reasoning_effort)
        if check_engine:
            create_plan(m13, packet, work / 'reader_b', engine=check_engine, model=check_model,
                        instructions=instructions, schema=schema, reasoning_effort=check_reasoning_effort)
        meta = {'schema': RUN_SCHEMA, 'created_at_utc': utc_now(), 'document_id': m13['document_id'],
                'source_text_sha256': m13['text_sha256'], 'map_sha256': sha256(json_bytes(m13)),
                'packet_sha256': sha256(json_bytes(packet)), 'max_chars': max_chars,
                'reading_tasks_per_reader': len(packet['chunks']),
                'source_characters': sum(len(p['text']) for p in m13['passages']),
                'first_reader': {'engine': engine, 'model': model, 'reasoning_effort':reasoning_effort}, 'human_approval': 'NOT_USED'}
        atomic_json(work / 'm13_run.json', meta)
        atomic_bytes(work / 'm13_run.sha256', (sha256(json_bytes(meta)) + '\n').encode())
        if root.exists(): raise FileExistsError('Run folder appeared during preparation')
        work.rename(root)
    return {'status': 'M13_PREPARED_NO_MODEL_CALLED', 'root': str(root), 'document_id': meta['document_id'],
            'tasks_per_reader': len(packet['chunks']),
            'second_reader': {'engine': check_engine, 'model': check_model} if check_engine else 'NONE (single reading)'}


def add_check(root, *, engine: str, model: str) -> dict:
    """Add the second reader to an existing run (before or after a single-reader export)."""
    from .m4_operator import create_plan
    root, meta, mapping, packet = _load(root)
    if (root / 'reader_b').exists(): raise FileExistsError('This run already has a second reader')
    instructions, schema = _plan_inputs()
    create_plan(mapping, packet, root / 'reader_b', engine=engine, model=model, instructions=instructions, schema=schema)
    return {'status': 'SECOND_READER_PREPARED_NO_MODEL_CALLED', 'root': str(root),
            'tasks': len(packet['chunks']), 'second_reader': {'engine': engine, 'model': model}}


def _readers(root):
    return [(name, root / name) for name in ('reader_a', 'reader_b') if (root / name).is_dir()]


def status(root) -> dict:
    from .m4_operator import status as plan_status, load_plan
    root, meta, mapping, packet = _load(root)
    out = {'schema': 'm13-status.1', 'document_id': meta['document_id'], 'readers': {}, 'outputs': {}}
    for name, folder in _readers(root):
        plan, _, _ = load_plan(folder); st = plan_status(folder)
        out['readers'][name] = {'engine': plan['engine'], 'model': plan['model'], 'captured': st['captured'],
                                'total': st['total'], 'limit_stopped': (folder / 'limit_stop.json').exists(),
                                'tasks': [{'task_id': t['task_id'], 'state': t['state']} for t in st['tasks']]}
    for name in ('output', 'output_checked'):
        if (root / name / 'reader_check.json').is_file():
            out['outputs'][name] = read_json(root / name / 'reader_check.json')['state']
    out['second_reader'] = 'PREPARED' if 'reader_b' in out['readers'] else 'NONE (single reading)'
    return out


def next_call(root, *, execute=False, confirm_subscription=False, confirm_credit_controls=False, run_all=False,
              timeout=900, allow_cli_path=None) -> dict:
    """Run the next reading task (first reader, then second reader). One model call,
    or with run_all every remaining call of THIS agreement, stopping at the first
    task that is not captured. Never retries a failed task."""
    from .m4_operator import run_next, status as plan_status
    root, meta, mapping, packet = _load(root)
    results = []
    while True:
        pending = next(((name, folder) for name, folder in _readers(root)
                        if plan_status(folder)['captured'] != plan_status(folder)['total']), None)
        if pending is None:
            return {'status': 'ALL_READINGS_CAPTURED', 'calls': results}
        name, folder = pending
        result = run_next(folder, execute=execute, confirm_subscription=confirm_subscription,
                          confirm_credit_controls=confirm_credit_controls, timeout=timeout,
                          allow_cli_path=(allow_cli_path or {}).get(name) if isinstance(allow_cli_path, dict) else allow_cli_path)
        result['reader'] = name; results.append(result)
        if not execute:
            return {'status': 'DRY_RUN_NO_AI_CALLED', 'next': result}
        if result.get('status') != 'CAPTURED_NOT_QC_APPROVED':
            return {'status': 'STOPPED_TASK_NOT_CAPTURED', 'calls': results}
        if not run_all:
            done = all(plan_status(f)['captured'] == plan_status(f)['total'] for _, f in _readers(root))
            return {'status': 'ALL_READINGS_CAPTURED' if done else 'CAPTURED_MORE_PENDING', 'calls': results}


def _merged(folder):
    from .m4_operator import merge_plan
    if not (folder / 'merged_extraction.json').is_file(): merge_plan(folder)
    return read_json(folder / 'merged_extraction.json')


_NEXT_STEP = {
    'TWO_READERS_AGREE': 'None required. Check the source at the point of use as usual.',
    'TWO_READERS_AGREE_ON_NUMBERS': 'Read the Reader Differences rows marked STRUCTURE before relying on how a rate is classified.',
    'TWO_READERS_DIFFER': 'Open the clauses listed in Reader Differences (CORE rows) and decide which reading is right.',
    'SINGLE_READER_NOT_CHECKED': 'Add a second reader (m13-add-check) before relying on completeness, or check the source yourself.',
    'SOURCE_CHECK_FAILED': 'Do not use. Re-run the reading in a new run folder.',
    'SECOND_READER_FAILED_SOURCE_CHECK': 'Treat as a single reading, or re-run the second reader in a new run folder.',
}


def decorate_rows(rows: dict, *, document_id: str, state: str, first_check: dict, second_check: dict | None,
                  comparison: dict | None, first: dict, second: dict | None, url: str) -> dict:
    """Put the M13 result into the workbook rows produced by the standard export."""
    def col(sheet, name): return rows[sheet][0].index(name)
    for sheet, name in (('Documents', 'Extraction_Status'), ('Royalty Terms', 'QC_State'), ('Tiers', 'QC_State'),
                        ('Other Payments', 'QC_State'), ('QC', 'State'), ('Pending Jobs', 'State')):
        c = col(sheet, name); d = col(sheet, 'Document_ID')
        for r in rows[sheet][1:]:
            if r[d] == document_id: r[c] = state
    label = ('NOT_PERFORMED' if comparison is None else
             f"{comparison['core']} core, {comparison['structure']} structure, {comparison['note']} note differences")
    for sheet in ('Documents', 'QC'):
        c = col(sheet, 'Second_AI_Review_Status'); d = col(sheet, 'Document_ID')
        for r in rows[sheet][1:]:
            if r[d] == document_id: r[c] = label
    c = col('Pending Jobs', 'What_Next'); d = col('Pending Jobs', 'Document_ID')
    for r in rows['Pending Jobs'][1:]:
        if r[d] == document_id: r[c] = _NEXT_STEP[state]
    agreement = first.get('agreement') if isinstance(first.get('agreement'), dict) else {}
    for sheet in ('Royalty Terms', 'Tiers', 'Other Payments'):
        d = col(sheet, 'Document_ID')
        rows[sheet][0].extend(['Licensor', 'Licensee'])
        for r in rows[sheet][1:]:
            r.extend([agreement.get('licensor'), agreement.get('licensee')] if r[d] == document_id else [None, None])
    def who(x): return f"{(x.get('reader') or {}).get('engine')} / {(x.get('reader') or {}).get('model')}" if x else 'none'
    check = [['Document_ID', 'State', 'Meaning', 'What_To_Do', 'First_Reader', 'Second_Reader', 'First_Reader_Source_Check',
              'First_Reader_Errors', 'Second_Reader_Source_Check', 'Core_Differences', 'Structure_Differences',
              'Note_Differences', 'Facts_Both_Readers_Recorded', 'Reader_Independence', 'Source_URL'],
             [document_id, state, STATE_MEANING[state], _NEXT_STEP[state], who(first), who(second),
              'PASS' if first_check['deterministic_status'] == 'PASS_DETERMINISTIC_ONLY' else 'FAIL',
              '; '.join(sorted({e['code'] for e in first_check['errors']})),
              'NOT_PERFORMED' if second_check is None else
              ('PASS' if second_check['deterministic_status'] == 'PASS_DETERMINISTIC_ONLY' else 'FAIL'),
              comparison['core'] if comparison else None, comparison['structure'] if comparison else None,
              comparison['note'] if comparison else None, comparison['facts_both_recorded'] if comparison else None,
              comparison['independence'] if comparison else None, url]]
    diffs = [['Document_ID', 'Level', 'What_Differs', 'Value', 'First_Reader', 'Second_Reader', 'Passage_ID', 'Section',
              'Source_Excerpt', 'Source_URL']]
    for x in (comparison or {}).get('differences', []):
        diffs.append([document_id, x['level'], x['description'], x['value'], x['first_reader'], x['second_reader'],
                      x['passage_id'], x['section'], x['source_excerpt'], url])
    ordered = {'Overview': rows['Overview'], 'Reader Check': check, 'Reader Differences': diffs}
    for name, table in rows.items():
        if name in ordered or (name == 'Source Flags' and len(table) == 1): continue
        ordered[name] = table
    ordered['Overview'] = [rows['Overview'][0],
                           ['Reader check result', state, STATE_MEANING[state]],
                           ['Readers', f'{who(first)}; second: {who(second)}', 'A second reading is optional; see sheet Reader Check']
                           ] + [r for r in rows['Overview'][1:] if r[0] not in {
                               'Documents with QC-passed extraction', 'Failed/pending extraction', 'High unresolved issue records'}]
    dd = ordered['Data Dictionary']
    dd.append(['Reader Check', 'Result of the source check and, when a second reader was used, of the comparison of the two readings',
               'Agreement of two AI readings lowers the chance of an omission; it is not proof of correctness'])
    dd.append(['Reader Differences', 'One row per difference between the two readings: CORE, STRUCTURE or NOTE',
               'The workbook rows come from the first reader; a CORE row means the second reader saw it differently'])
    return ordered


_SEC_META_KEYS = ('cik', 'accession', 'filing_date', 'file_type', 'company', 'form', 'filename')


def _batch_metadata(root, document_id) -> dict:
    """SEC filing metadata for a run made before v0.13.7 (its immutable map carries only id + URL).

    Looks the document up in the batch's discovery.jsonl, then its candidate_register.json. Read-only;
    returns {} when the run was not produced by ./royalty.sh or the document is not listed.
    """
    root = Path(root)
    batch_root = root.parent.parent                      # <batch>/runs/<DOC>
    found = {}
    for path in (batch_root.parent / 'discovery.jsonl', batch_root / 'candidate_register.json'):
        try:
            if not path.is_file(): continue
            text = path.read_text(encoding='utf-8')
            rows = json.loads(text) if path.suffix == '.json' else [json.loads(x) for x in text.splitlines() if x.strip()]
        except (OSError, ValueError):
            continue
        for r in rows:
            if isinstance(r, dict) and r.get('document_id') == document_id:
                for k in _SEC_META_KEYS:
                    if r.get(k) and not found.get(k): found[k] = r[k]
    return found


def finalize(root, *, export_xlsx=True, without_check=False, legacy_xlsx=False) -> dict:
    """Merge, check, compare (when a second reader exists) and export. No model call.

    When it fails, a one-line reason is saved as finalize_error.txt in the run folder (next to, not inside,
    the immutable inputs) so the combined workbook's sheet 00 can say why the agreement is missing.
    """
    try:
        result = _finalize(root, export_xlsx=export_xlsx, without_check=without_check, legacy_xlsx=legacy_xlsx)
    except FileExistsError:
        raise
    except Exception as exc:
        try: (Path(root).expanduser() / 'finalize_error.txt').write_text(f'{type(exc).__name__}: {exc}'[:400] + '\n', encoding='utf-8')
        except OSError: pass
        raise
    try: (Path(root).expanduser() / 'finalize_error.txt').unlink()
    except OSError: pass
    return result


def _finalize(root, *, export_xlsx=True, without_check=False, legacy_xlsx=False) -> dict:
    from .m3_workspace import init, register_map, register_extraction
    from .m3_export import build_rows, write_csvs
    from .m3_workbook import write_xlsx
    from .m4_operator import status as plan_status
    root, meta, mapping, packet = _load(root)
    readers = dict(_readers(root))
    def complete(folder): st = plan_status(folder); return st['captured'] == st['total']
    if not complete(readers['reader_a']): raise ValueError('The first reading is not complete; run m13-next')
    use_b = 'reader_b' in readers and complete(readers['reader_b'])
    if 'reader_b' in readers and not use_b and not without_check:
        raise ValueError('A second reader is prepared but not finished; run m13-next, or pass --without-check')
    target = root / 'output'
    if target.exists():
        prior = read_json(target / 'reader_check.json')
        if not use_b or prior.get('second_reader_used'): raise FileExistsError('Output already exists; never overwrite a prior result')
        target = root / 'output_checked'
        if target.exists(): raise FileExistsError('Checked output already exists; never overwrite a prior result')
    from .m13_consolidate import consolidate
    raw_first = _merged(readers['reader_a'])
    second = _merged(readers['reader_b']) if use_b else None
    # v0.13.10: the exported first reading is consolidated (duplicate / threshold-variant / reduction terms);
    # the two-reader comparison uses the RAW readings of both, so it stays symmetrical and unchanged.
    first, consolidation = consolidate(raw_first)
    first_check = source_check(mapping, first)
    second_check = source_check(mapping, second) if use_b else None
    comparison = compare_readers(mapping, raw_first, second) if use_b else None
    state = decide_state(first_check, second_check, comparison)
    workspace = root / ('workspace' if target.name == 'output' else 'workspace_checked')
    export_map = mapping
    meta_have = mapping.get('document_metadata') or {}
    extra = _batch_metadata(root, mapping['document_id'])
    if extra:
        merged_meta = dict(meta_have)
        for key, value in extra.items():
            if merged_meta.get(key) is None or str(merged_meta[key]).strip() == '':
                merged_meta[key] = value
        export_map = dict(mapping); export_map['document_metadata'] = merged_meta
    init(workspace); register_map(workspace, export_map)
    register_extraction(workspace, mapping['document_id'], first, select=True)
    rows = decorate_rows(build_rows(workspace), document_id=mapping['document_id'], state=state, first_check=first_check,
                         second_check=second_check, comparison=comparison, first=first, second=second,
                         url=mapping.get('source_url') or '')
    summary = {'schema': 'm13-reader-check.1', 'document_id': mapping['document_id'], 'state': state,
               'meaning': STATE_MEANING[state], 'second_reader_used': bool(use_b),
               'first_reader_source_check': first_check['deterministic_status'],
               'second_reader_source_check': second_check['deterministic_status'] if second_check else None,
               'comparison': comparison}
    with tempfile.TemporaryDirectory(prefix='.m13-export-', dir=root) as td:
        out = Path(td) / target.name; out.mkdir()
        atomic_json(out / 'final_extraction.json', first)
        atomic_json(out / 'source_check.json', first_check)
        if consolidation:
            atomic_json(out / 'first_reader_extraction_before_consolidation.json', raw_first)
        atomic_json(out / 'consolidation.json', {'schema': 'm13-consolidation.1', 'document_id': mapping['document_id'],
                                                 'terms_before': len(raw_first.get('royalty_terms') or []),
                                                 'terms_after': len(first.get('royalty_terms') or []), 'notes': consolidation})
        if use_b:
            atomic_json(out / 'second_reader_extraction.json', second)
            atomic_json(out / 'second_reader_source_check.json', second_check)
        atomic_json(out / 'reader_check.json', summary)
        atomic_json(out / 'rows.json', rows)      # typed workbook rows, used by m13-combine
        write_csvs(rows, out / 'csv')
        if export_xlsx:
            from .m13_research_export import write_research_xlsx
            summary_row = _summary_row(mapping, 'EXPORTED', state, rows, first)
            write_research_xlsx(rows, out / 'Royalty_Research_M13.xlsx', {mapping['document_id']: first},
                                {mapping['document_id']: [x.get('text') or '' for x in mapping.get('passages', [])]},
                                source_errors={mapping['document_id']: first_check['errors']},
                                run_summary=_summary_block([summary_row]))
            if legacy_xlsx:
                write_xlsx(rows, out / 'Royalty_Research_M13_Detailed.xlsx')
        manifest = {'schema': 'm13-output-manifest.1', 'source_map_sha256': meta['map_sha256'], 'state': state,
                    'final_extraction_sha256': sha256(json_bytes(first)),
                    'output_files_sha256': {str(p.relative_to(out)): sha256(p.read_bytes())
                                            for p in sorted(out.rglob('*')) if p.is_file()}}
        atomic_json(out / 'output_manifest.json', manifest)
        if target.exists(): raise FileExistsError('Output appeared during export')
        out.rename(target)
    return {'status': 'EXPORTED', 'state': state, 'meaning': STATE_MEANING[state],
            'source_check_errors': len(first_check['errors']),
            'consolidation_notes': len(consolidation),
            'core_differences': comparison['core'] if comparison else None,
            'structure_differences': comparison['structure'] if comparison else None,
            'note_differences': comparison['note'] if comparison else None,
            'output_dir': str(target),
            'spreadsheet': str(target / 'Royalty_Research_M13.xlsx') if export_xlsx else None}


def _summary_row(mapping, status, state, rows, first=None, note='', extra_meta=None):
    """One row of sheet 00 (columns: see m13_research_export.SUMMARY_HEADERS)."""
    did = mapping['document_id']
    meta = {**(extra_meta or {}), **(mapping.get('document_metadata') or {})}
    agreement = (first or {}).get('agreement') if isinstance((first or {}).get('agreement'), dict) else {}
    parties = ' \u2013 '.join(x for x in (agreement.get('licensor'), agreement.get('licensee')) if x)
    who = ' | '.join(x for x in (meta.get('company'), parties) if x)
    n = 0
    if rows is not None and 'Royalty Terms' in rows:
        d = rows['Royalty Terms'][0].index('Document_ID')
        n = sum(1 for r in rows['Royalty Terms'][1:] if r[d] == did)
    return [did, who, mapping.get('source_url') or meta.get('source_url') or '', status, state or '', n, note]


def _summary_block(rows, candidates=None, total_candidates=None):
    """The run_summary argument of write_research_xlsx: counts line, run rows, skipped-candidate counts."""
    exported = sum(1 for r in rows if str(r[3]).startswith('EXPORTED'))
    failed = sum(1 for r in rows if str(r[3]).startswith('FAILED'))
    notdone = len(rows) - exported - failed
    parts = [f'{exported} exported'] + ([f'{notdone} not finished'] if notdone else []) + ([f'{failed} failed'] if failed else [])
    block = {'rows': rows, 'counts': f"{len(rows)} agreement{'' if len(rows) == 1 else 's'}: " + ', '.join(parts)}
    if notdone or failed:
        block['counts'] += ' (not-finished and failed agreements are NOT in sheets 01-06)'
    if candidates:
        skipped = sum(c for _, c, _ in candidates)
        block['candidates'] = candidates
        block['candidate_line'] = (f'Batch candidate register: {total_candidates} candidates, {len(rows)} read, {skipped} not read: '
                                   + '; '.join(f'{c} {k}' for k, c, _ in candidates))
    return block


_REGISTER_MEANING = {
    'NOT_PREPARED_AGREEMENT_LIMIT': 'Not read: the batch reached its agreement limit first (not judged either way unless its licence gate result says so)',
    'NOT_PREPARED_NOT_LICENCE_LIKE': 'Failed the zero-AI licence gate (not a licence, or no royalty wording)',
    'NOT_PREPARED_TOO_LARGE': 'Licence-like but over the source-size limit; read it with --big',
    'LOW_SIGNAL_REVIEW_REQUIRED': 'Few royalty signals; a person should decide whether to read it',
}


def _register_counts(runs_dir):
    """(candidates, total) from <batch>/candidate_register.json when it exists; read-only, never fails."""
    path = Path(runs_dir).parent / 'candidate_register.json'
    try:
        rows = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    except (OSError, ValueError):
        rows = None
    if not isinstance(rows, list): return None, None
    from collections import Counter
    counts = Counter(str(r.get('status') or 'UNKNOWN') for r in rows if isinstance(r, dict))
    counts.pop('FULL_SOURCE_PREPARED', None)
    return [(k, v, _REGISTER_MEANING.get(k, 'See candidate_register.json')) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])], len(rows)


def _unfinished_row(run, run_map):
    """Status row for a run folder without an exported result: NOT_FINISHED (n of m calls) or FAILED (reason)."""
    from .m4_operator import status as plan_status
    meta = _batch_metadata(run, run_map['document_id'])
    done = total = 0
    for _, folder in _readers(run):
        st = plan_status(folder); done += st['captured']; total += st['total']
    err = run / 'finalize_error.txt'
    if total and done == total and err.is_file():
        reason = ' '.join(err.read_text(encoding='utf-8', errors='replace').split())[:160]
        return _summary_row(run_map, f'FAILED \u2013 {reason}', '', None, extra_meta=meta,
                            note='All reading calls are done but finalize failed; see finalize_error.txt in the run folder')
    if total and done == total:
        return _summary_row(run_map, 'NOT_FINISHED \u2013 readings done, not finalized yet', '', None, extra_meta=meta,
                            note='Run finalize (./royalty.sh --resume ... --go)')
    return _summary_row(run_map, f'NOT_FINISHED \u2013 {done} of {total} reading calls done', '', None, extra_meta=meta,
                        note='Finish it with ./royalty.sh --resume <folder> --go, then combine again')


# ---------------------------------------------------------------------------
# 4. One workbook for many agreements
# ---------------------------------------------------------------------------
def combine(runs_dir, destination, *, legacy_xlsx=False) -> dict:
    """Put the exported result of every finished M13 run under runs_dir into one workbook.

    Uses the checked result of a run when it has one, otherwise the single-reader result.
    Runs that are not finished are counted and named, never silently left out. No model call.
    """
    from collections import Counter
    from .m3_workbook import write_xlsx
    runs_dir = Path(runs_dir).expanduser(); destination = Path(destination).expanduser()
    if destination.exists(): raise FileExistsError('Combined workbook already exists; choose a new file name')
    if destination.suffix.lower() != '.xlsx': raise ValueError('The combined workbook must be an .xlsx file')
    combined = None; states = Counter(); used = []; unfinished = []; first_readings = {}; source_texts = {}
    source_errors = {}; summary_rows = []
    for run in sorted(p for p in runs_dir.iterdir() if p.is_dir() and (p / 'm13_run.json').is_file()):
        out = next((run / n for n in ('output_checked', 'output') if (run / n).is_dir()), None)
        if out is None:
            unfinished.append(run.name)
            try:
                _, _, run_map, _ = _load(run)
                summary_rows.append(_unfinished_row(run, run_map))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                reason = ' '.join(str(exc).split())[:160]
                summary_rows.append(_summary_row({'document_id':run.name},
                    f'FAILED – {type(exc).__name__}: {reason}', '', None,
                    note='Invalid unfinished run; inspect its saved files before resuming'))
            continue
        _, _, run_map, _ = _load(run)  # Finalized runs remain subject to strict integrity checks.
        manifest = read_json(out / 'output_manifest.json')
        if manifest['output_files_sha256'].get('rows.json') != sha256((out / 'rows.json').read_bytes()):
            raise ValueError(f'{run.name}: exported rows were changed after export')
        rows = read_json(out / 'rows.json'); states[read_json(out / 'reader_check.json')['state']] += 1
        extraction = read_json(out / 'final_extraction.json')
        if sha256(json_bytes(extraction)) != manifest['final_extraction_sha256']:
            raise ValueError(f'{run.name}: final extraction changed since export')
        did = extraction['document_id']
        # Legacy combine allows multiple runs of the same SEC document; preserve
        # the first metadata record. Each detailed source row still remains.
        first_readings.setdefault(did, extraction)
        try: source_errors.setdefault(did, read_json(out / 'source_check.json').get('errors') or [])
        except (OSError, ValueError): pass
        summary_rows.append(_summary_row(run_map, 'EXPORTED', read_json(out / 'reader_check.json')['state'], rows, extraction, extra_meta=_batch_metadata(run, did)))
        source_texts.setdefault(did, [x.get('text') or '' for x in run_map.get('passages', [])])
        used.append(run.name)
        if combined is None:
            combined = {name: [list(table[0])] for name, table in rows.items()}
            combined['Data Dictionary'] = [list(r) for r in rows['Data Dictionary']]
        for name, table in rows.items():
            if name in ('Overview', 'Data Dictionary'): continue
            if name not in combined: combined[name] = [list(table[0])]
            if combined[name][0] != table[0]: raise ValueError(f'{run.name}: sheet {name} has different columns')
            combined[name].extend(table[1:])
    if combined is None: raise ValueError('No finished M13 run found in this folder')
    overview = [combined['Overview'][0], ['Agreements in this workbook', len(used), 'One row per SEC document in sheet Reader Check']]
    for state in STATE_MEANING:
        if states[state]: overview.append([state, states[state], STATE_MEANING[state]])
    overview.append(['Runs not finished (left out)', len(unfinished), ', '.join(unfinished) or 'none'])
    overview.append(['Workbook scope', 'HISTORICAL NOT CURRENT', 'Amendment/effective economics require separate interpretation'])
    overview.append(['Inference billing', 'NONE', 'Local scripts do not invoke AI model APIs'])
    combined['Overview'] = overview
    from .m13_research_export import write_research_xlsx
    detailed = destination.with_name(destination.stem + '_Detailed.xlsx')
    if legacy_xlsx and detailed.exists(): raise FileExistsError('Detailed combined XLSX already exists')
    candidates, total = _register_counts(runs_dir)
    write_research_xlsx(combined, destination, first_readings, source_texts, source_errors=source_errors,
                        run_summary=_summary_block(summary_rows, candidates, total))
    if legacy_xlsx:
        write_xlsx(combined, detailed)
    return {'status': 'COMBINED', 'agreements': len(used), 'states': dict(states), 'not_finished': unfinished,
            'spreadsheet': str(destination)}

