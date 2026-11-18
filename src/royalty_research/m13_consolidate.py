"""Deterministic consolidation of one reading's royalty terms (v0.13.10, extended in v0.13.11; zero AI tokens).

The reader is told to record one term per distinct royalty, but a reading split over several chunks
(and a reader that lists each threshold variant or each reduction on its own) still produces extra
rows. This module repairs three patterns after the chunk merge and before the source check / export:

1. FOLD     A term with no rate quotation and no numeric rate (e.g. "Net Sales", rate UNKNOWN, seen in
            chunk 1 before the schedule) is folded into the one quoted term of the same family and the
            same royalty base. Evidence, conditions and adjustments are unioned; the quoted term's ID stays.
2. VARIANTS Terms of the same family, base, product scope, territory and period that differ ONLY by a
            threshold condition ("when annual Government Sales are less than X") become ONE term with one
            tier per variant (rate, threshold text, evidence kept). Different bases or scopes
            (Net Sales vs Government Sales vs Software Products) are never merged.
3. REDUCTIONS A term that only describes a reduction / offset / anti-stacking / floor of another royalty
            becomes an ADJUSTMENT on that royalty (all figures and evidence kept in the adjustment).

Rule of thumb: when a rule is not confident the terms stay separate (a duplicate is better than a lost
term). Every change is returned as a note and written into the reading as a RESOLVED / LOW open issue of
kind CONSOLIDATED, so it appears in the QC sheet. The input is never modified.

Two-reader comparison: finalize compares the two RAW readings (before consolidation), so the comparison
is symmetrical and exactly as before; only the exported first reading is consolidated.
"""
from __future__ import annotations

import copy
import re

from .storage import stable_id

_STOP = {'a', 'an', 'the', 'of', 'and', 'or', 'to', 'in', 'on', 'for', 'by', 'from', 'with', 'under', 'per', 'as', 'at',
         'any', 'all', 'each', 'every', 'such', 'that', 'is', 'are', 'be', 'its', 'their', 'other', 'than', 'this',
         'received', 'receivable', 'receive', 'payable', 'paid', 'made', 'sold'}
_GENERIC = {'licensed', 'licensee', 'licensor', 'affiliate', 'affiliates', 'product', 'products', 'process', 'processes',
            'patent', 'patents', 'right', 'rights', 'annual', 'aggregate', 'calendar', 'year', 'worldwide', 'total',
            'gross'}
_CANON = (('sublicens', 'sublicense'), ('revenue', 'revenue'), ('income', 'revenue'), ('receipt', 'revenue'),
          ('consideration', 'revenue'), ('sale', 'sales'))

# A condition that sets a threshold / volume / share level (not a mere description of scope).
_THRESHOLD = re.compile(r'\b(less than|fewer than|more than|greater than|exceed\w*|in excess of|at least|or more|or less|'
                        r'equal to|below|above|threshold|up to|over|under|not more than|not less than|between)\b|'
                        # v0.13.11: a phase split ("until the 5th anniversary" / "after the 5th anniversary") counts as a
                        # threshold only when the condition STARTS with the time word ("payable within 30 days after" does not).
                        r'^\s*(?:until|prior to|before|after|thereafter|beginning|commencing|following)\b', re.I)
# Reduction / offset / anti-stacking / floor wording.
_STRONG_REDUCTION = re.compile(r'stack|offset|set-?off|reduction|reduced|\bfloor\b|step-?down|cannot be reduced|'
                               r'not be reduced|credited against|creditable', re.I)
_ANY_REDUCTION = re.compile(r'stack|offset|set-?off|reduc(?:e|ed|es|ing|tion)\b|\bfloor\b|step-?down|not be reduced|'
                            r'no less than|credited against|creditable|in no event', re.I)
_ROYALTY_FAMILIES = {'PRODUCT_SALES', 'SUBLICENSING_RECEIPTS', 'PER_UNIT', 'USAGE', 'REVENUE_SHARE'}


def _words(text) -> frozenset:
    text = re.sub(r'\([^)]*\)', ' ', str(text or '').lower())
    out = set()
    for w in re.findall(r"[a-z]+", text):
        if w in _STOP or w in _GENERIC: continue
        for prefix, canon in _CANON:
            if w.startswith(prefix): w = canon; break
        else:
            if len(w) > 3 and w.endswith('s') and w != 'sales': w = w[:-1]
        out.add(w)
    return frozenset(out)


def _norm(text) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9% ]', ' ', str(text or '').lower())).strip()


def _union(*lists) -> list:
    out = []
    for lst in lists:
        for x in lst or []:
            if x not in out: out.append(x)
    return out


def _all_evidence(t: dict) -> list:
    ids = _union(t.get('evidence_ids'), t.get('rate_evidence_ids'), t.get('base_evidence_ids'))
    for z in (t.get('conditions') or []) + (t.get('adjustments') or []):
        ids = _union(ids, z.get('evidence_ids'))
    for z in t.get('tiers') or []:
        ids = _union(ids, z.get('evidence_ids'), z.get('threshold_evidence_ids'))
    return ids


def _numeric(value) -> bool:
    return isinstance(value, str) and bool(re.search(r'\d', value))


def _has_numeric_rate(t: dict) -> bool:
    return _numeric(t.get('rate_value')) or any(_numeric(z.get('rate_value')) for z in t.get('tiers') or [])


def _unrated(t: dict) -> bool:
    return (not t.get('rate_value') and t.get('rate_unit') == 'UNKNOWN' and not t.get('tiers')
            and not t.get('rate_evidence_ids') and t.get('disclosure_status') != 'REDACTED')


def _quoted(t: dict) -> bool:
    return not _unrated(t) and (_has_numeric_rate(t) or bool(t.get('tiers')) or bool(t.get('rate_evidence_ids'))
                                or t.get('disclosure_status') == 'REDACTED')


def _scope_main(t: dict) -> str:
    return str(t.get('product_scope') or '').split(';')[0]


def _scope_qualifier(t: dict) -> str:
    parts = str(t.get('product_scope') or '').split(';')[1:]
    return '; '.join(p.strip() for p in parts if p.strip())


_RESIDUAL = re.compile(r'\b(?:other|remaining|rest)\b', re.I)


def _residual(t: dict) -> bool:
    """'All other Licensed Products' names the REST of the products, not a specific named product."""
    return bool(_RESIDUAL.search(_scope_main(t)))


def _scope_compatible(a: dict, b: dict) -> bool:
    # v0.13.11: "all other X" is NOT compatible with a specific named scope (its words are mostly filler, so the
    # word-subset test below used to accept it for every named scope).
    if _residual(a) != _residual(b) and _words(_scope_main(b if _residual(a) else a)): return False
    x, y = _words(a.get('product_scope')), _words(b.get('product_scope'))
    return not x or not y or x <= y or y <= x


def _territory_compatible(a: dict, b: dict) -> bool:
    x, y = _norm(a.get('territory_scope')), _norm(b.get('territory_scope'))
    return not x or not y or x == y


def _add_conditions(target: dict, source: dict):
    have = {_norm(c.get('text')) for c in target['conditions']}
    for c in source.get('conditions') or []:
        if _norm(c.get('text')) not in have: target['conditions'].append(copy.deepcopy(c))
        else:
            mine = next(x for x in target['conditions'] if _norm(x.get('text')) == _norm(c.get('text')))
            mine['evidence_ids'] = _union(mine.get('evidence_ids'), c.get('evidence_ids'))


def _add_adjustments(target: dict, source: dict):
    for a in source.get('adjustments') or []:
        mine = next((x for x in target['adjustments'] if _norm(x.get('description')) == _norm(a.get('description'))), None)
        if mine: mine['evidence_ids'] = _union(mine.get('evidence_ids'), a.get('evidence_ids'))
        else: target['adjustments'].append(copy.deepcopy(a))


def _remap_terms(extraction: dict, mapping: dict):
    """Dispositions and percentage ledgers that named a removed term now name the kept one."""
    def fix(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k == 'term_id' and isinstance(v, str) and v in mapping: node[k] = mapping[v]
                elif k == 'term_ids' and isinstance(v, list):
                    node[k] = _union([mapping.get(x, x) for x in v])
                else: fix(v)
        elif isinstance(node, list):
            for v in node: fix(v)
    fix(extraction.get('dispositions') or [])


# --- rule 2: threshold variants -------------------------------------------------------------------------------
def _variant_key(t: dict):
    return (t.get('family'), _words(t.get('base')), _words(_scope_main(t)), _norm(t.get('territory_scope')),
            _norm(t.get('effective_period')), _residual(t))


def _split_conditions(t: dict):
    thr = [c for c in t.get('conditions') or [] if _THRESHOLD.search(c.get('text') or '')]
    rest = [c for c in t.get('conditions') or [] if c not in thr]
    return thr, rest


_LOWER_WORDS = re.compile(r'(?:more than|greater than|exceed\w*|in excess of|above|over|at least|not less than|no less than|'
                          r'greater than or equal to|minimum of)(?![a-z])', re.I)
_UPPER_WORDS = re.compile(r'(?:less than|fewer than|below|under|not more than|no more than|up to|at most|not exceed\w*|'
                          r'less than or equal to|maximum of)(?![a-z])', re.I)
_LOWER_AFTER = re.compile(r'\s*(?:or more|or greater|or higher|and above|or over)\b', re.I)
_UPPER_AFTER = re.compile(r'\s*(?:or less|or fewer|or lower|and below|or under)\b', re.I)
_REFERENCE_BEFORE = re.compile(r'(?:section|article|paragraph|exhibit|schedule|clause|appendix)\s*$', re.I)
_PERIOD = re.compile(r'\b(calendar (?:year|quarter|month)|contract (?:year|quarter)|fiscal (?:year|quarter)|annual(?:ly)?|'
                     r'quarterly|monthly|per year|each year|per annum)\b', re.I)
_MARGINAL = re.compile(r'\b(?:that portion|such portion|portion of|incremental|marginal|only to the excess|the excess)\b', re.I)
_ALL_UNITS = re.compile(r'\b(?:retroactive\w*|applies? to all (?:net sales|units|sales)|all units)\b', re.I)


def _bound_tokens(text: str) -> list:
    from .m13_two_reader import numbers_in_text
    out = []
    for tok in numbers_in_text(text):
        if tok['unit'] == 'PCT': continue
        if _REFERENCE_BEFORE.search(text[max(0, tok['start'] - 14):tok['start']]): continue
        out.append(tok)
    return out


def _parse_bounds(text: str):
    """(lower, upper) as plain number strings, read from threshold wording; None when the text does not state one.

    Understands "less than / fewer than / below / under / up to / not more than X" (upper), "more than / greater than /
    exceed(s) / in excess of / above / over / at least X" and "X or more" (lower), and "between X and Y". Amounts with
    $/USD/million/thousand are handled by the same number reader the source check uses. A conflict (two different
    lower bounds, say) returns (None, None): when unsure, no bound."""
    toks = _bound_tokens(text)
    if not toks: return None, None
    m = re.search(r'\bbetween\b', text, re.I)
    if m:
        after = [t for t in toks if t['start'] > m.end()]
        if len(after) == 2: return after[0]['value'], after[1]['value']
    lower, upper = set(), set()
    for tok in toks:
        before = text[max(0, tok['start'] - 40):tok['start']]
        found = None
        for kind, rx in (('lower', _LOWER_WORDS), ('upper', _UPPER_WORDS)):
            for hit in rx.finditer(before):
                gap = before[hit.end():]
                if len(gap) <= 30 and not re.search(r'[.;]', gap) and (found is None or hit.end() > found[1]): found = (kind, hit.end())
        if found: (lower if found[0] == 'lower' else upper).add(tok['value']); continue
        if _LOWER_AFTER.match(text, tok['end']): lower.add(tok['value'])
        elif _UPPER_AFTER.match(text, tok['end']): upper.add(tok['value'])
    if len(lower) > 1 or len(upper) > 1: return None, None
    return (next(iter(lower), None), next(iter(upper), None))


def _quoted_values(ids, quotes: dict) -> set:
    from .m13_two_reader import numbers_in_text
    return {t['value'] for e in ids or [] for t in numbers_in_text(quotes.get(e) or '')}


def _tier_from_variant(n: int, m: dict, quotes: dict) -> dict:
    thr, _ = _split_conditions(m)
    basis = '; '.join(c['text'] for c in thr) or _scope_qualifier(m) or 'no threshold condition stated (default rate)'
    thr_ids = _union(*[c.get('evidence_ids') for c in thr])
    own_ids = _union(m.get('evidence_ids'), m.get('rate_evidence_ids'))
    lower = upper = None
    period = calc = None
    if thr:
        text = ' '.join(c['text'] for c in thr)
        lo, up = _parse_bounds(text)
        # v0.13.11 (B6): a bound is only written when the cited quotation holds that very number, so the source
        # check (THRESHOLD_NOT_IN_QUOTE) can never fail because of Python's reading.
        have = _quoted_values(_union(thr_ids, own_ids), quotes)
        lower = lo if lo is not None and lo in have else None
        upper = up if up is not None and up in have else None
        pm = _PERIOD.search(text)
        period = pm.group(1).lower() if pm else None
        whole = ' '.join([text] + [c['text'] for c in _split_conditions(m)[1]])
        calc = 'MARGINAL' if _MARGINAL.search(whole) else 'ALL_UNITS' if _ALL_UNITS.search(whole) else None
    return {'sequence': n, 'rate_value': m.get('rate_value'), 'rate_unit': m.get('rate_unit'),
            'lower': lower, 'upper': upper, 'calculation': calc or 'UNKNOWN', 'measurement_period': period,
            'threshold_basis': basis, 'threshold_evidence_ids': thr_ids, 'evidence_ids': own_ids}


def _merge_variants(terms: list, notes: list, quotes: dict | None = None) -> list:
    quotes = quotes or {}
    groups: dict = {}
    for t in terms:
        if _quoted(t) and not t.get('tiers') and _variant_key(t)[1]:
            groups.setdefault(_variant_key(t), []).append(t)
    drop, replace = set(), {}
    for members in groups.values():
        if len(members) < 2: continue
        split = [(m, *_split_conditions(m)) for m in members]
        defaults = [m for (m, thr, _) in split if not thr]
        if len(defaults) > 1:
            # v0.13.11 (B1): two or more terms without a threshold cannot both be "the" default rate, so none of
            # them is merged - but the terms that DO carry a threshold may still be tiers of one another.
            split = [x for x in split if x[1]]
            defaults = []
            if len(split) < 2: continue
        members = [m for (m, _, _) in split]
        thr_texts = [tuple(sorted(_norm(c['text']) for c in thr)) for _, thr, _ in split]
        rest_texts = {tuple(sorted(_norm(c['text']) for c in rest)) for _, _, rest in split}
        if len(set(thr_texts)) != len(thr_texts) or len(rest_texts) != 1: continue
        if len(members) - len(defaults) < 1: continue
        # v0.13.11 (B5): one rate unit only. A percentage and a per-unit amount are different economics.
        if len({m.get('rate_unit') for m in members}) > 1: continue
        ordered = defaults + [m for (m, thr, _) in split if thr]
        keep = copy.deepcopy(ordered[0])
        rates = {(m.get('rate_value'), m.get('rate_unit')) for m in ordered}
        statuses = {m.get('disclosure_status') for m in ordered}
        keep['tiers'] = [_tier_from_variant(n, m, quotes) for n, m in enumerate(ordered, 1)]
        keep['structure'] = 'TIERED'
        if len(rates) != 1:
            keep['rate_value'] = None
            keep['rate_unit'] = ordered[0].get('rate_unit')
        if len(statuses) > 1: keep['disclosure_status'] = 'DISCLOSED' if 'DISCLOSED' in statuses else keep['disclosure_status']
        keep['product_scope'] = _scope_main(ordered[0]).strip() or None
        keep['conditions'] = [copy.deepcopy(c) for c in _split_conditions(ordered[0])[1]]
        for m in ordered[1:]:
            keep['evidence_ids'] = _union(keep['evidence_ids'], m.get('evidence_ids'))
            keep['rate_evidence_ids'] = _union(keep['rate_evidence_ids'], m.get('rate_evidence_ids'))
            keep['base_evidence_ids'] = _union(keep['base_evidence_ids'], m.get('base_evidence_ids'))
            _add_adjustments(keep, m)
        kept_id = keep['term_id']
        replace[kept_id] = keep
        gone = [m['term_id'] for m in ordered[1:]]
        drop.update(gone)
        unparsed = [z['sequence'] for z, m in zip(keep['tiers'], ordered)
                    if _split_conditions(m)[0] and z['lower'] is None and z['upper'] is None]
        message = (f"CONSOLIDATED: {', '.join(gone)} merged into {kept_id} as tiers (same family, base and product scope; "
                   f"they differ only by a threshold condition)")
        if unparsed:
            message += (f". Numeric bounds could not be read for tier(s) {', '.join(str(n) for n in unparsed)} "
                        f"(redacted, not a plain number, or not in the cited quotation); the threshold text is kept in threshold_basis")
        notes.append({'rule': 'VARIANTS', 'kept': kept_id, 'removed': gone, 'message': message, 'unparsed_tiers': unparsed,
                      'evidence': _union(*[_all_evidence(m) for m in ordered])})
    return [replace.get(t['term_id'], t) for t in terms if t['term_id'] not in drop]


# --- rule 1: fold unrated duplicates ----------------------------------------------------------------------------
def _fold_rank(target: dict, u: dict) -> tuple:
    """Exact product scope first, then exact territory (v0.13.11). (False, False) means nothing tells candidates apart."""
    scope = bool(_norm(_scope_main(u))) and _norm(_scope_main(target)) == _norm(_scope_main(u))
    terr = bool(_norm(u.get('territory_scope'))) and _norm(target.get('territory_scope')) == _norm(u.get('territory_scope'))
    return (scope, terr)


def _fold_unrated(terms: list, notes: list) -> list:
    out = list(terms)
    for u in [t for t in terms if _unrated(t)]:
        if u not in out: continue
        base = _words(u.get('base'))
        if not base: continue
        cands = [t for t in out if t is not u and _quoted(t) and t.get('family') == u.get('family')
                 and _words(t.get('base')) == base and _scope_compatible(t, u) and _territory_compatible(t, u)]
        if not cands: continue
        if len(cands) > 1:
            best_rank = max(_fold_rank(c, u) for c in cands)
            best = [c for c in cands if _fold_rank(c, u) == best_rank]
            if len(best) != 1 or best_rank == (False, False):
                # Several equally good targets: attaching the unrated term's adjustments to any of them (or to all)
                # could invent economics the source does not state. Keep the row, say so loudly.
                names = ', '.join(c['term_id'] for c in cands)
                notes.append({'rule': 'UNRESOLVED', 'kept': u['term_id'], 'removed': [], 'candidates': [c['term_id'] for c in cands],
                              'message': f"UNRESOLVED CROSS-CHUNK DUPLICATE: term {u['term_id']} has no rate quoted and could be the same "
                                         f"royalty as {names}. It was NOT merged and its adjustments were NOT attached to any of them; "
                                         f"it stays benchmark NO. Read the source and decide by hand.",
                              'evidence': _all_evidence(u)})
                continue
            cands = best
        target = cands[0]
        merged = copy.deepcopy(target)
        merged['evidence_ids'] = _union(merged['evidence_ids'], u.get('evidence_ids'))
        merged['base_evidence_ids'] = _union(merged['base_evidence_ids'], u.get('base_evidence_ids'))
        if not merged.get('product_scope') and u.get('product_scope'): merged['product_scope'] = u['product_scope']
        if not merged.get('base_definition') and u.get('base_definition'): merged['base_definition'] = u['base_definition']
        _add_conditions(merged, u); _add_adjustments(merged, u)
        out[out.index(target)] = merged
        out.remove(u)
        notes.append({'rule': 'FOLD', 'kept': target['term_id'], 'removed': [u['term_id']], 'message':
                      f"CONSOLIDATED: {u['term_id']} folded into {target['term_id']} (same family and base, no rate quoted)",
                      'evidence': _all_evidence(u)})
    return out


# --- rule 3: reductions become adjustments --------------------------------------------------------------------
def _text(*parts) -> str:
    return ' '.join(str(p) for p in parts if p)


def _is_reduction(t: dict) -> bool:
    if _strong_in_base(t): return True
    own = _text(*[c.get('text') for c in t.get('conditions') or []], *[a.get('description') for a in t.get('adjustments') or []])
    return (t.get('family') == 'OTHER' or t.get('structure') == 'FORMULA') and not _has_numeric_rate(t) \
        and bool(_ANY_REDUCTION.search(own))


def _strong_in_base(t: dict) -> bool:
    return bool(_STRONG_REDUCTION.search(_text(t.get('base'), t.get('product_scope')))) and not _unrated(t)


def _mentions(t: dict, tid: str) -> bool:
    body = _text(*[c.get('text') for c in t.get('conditions') or []], *[a.get('description') for a in t.get('adjustments') or []])
    return bool(re.search(r'(?<![\w-])' + re.escape(tid) + r'(?![\w-])', body, re.I))


def _adjustment_text(r: dict) -> str:
    parts = [f"Reduction/offset recorded by the reader as separate term {r['term_id']}: {r.get('base') or 'n/a'}"]
    if r.get('product_scope'): parts.append(f"Scope: {r['product_scope']}")
    if r.get('rate_value'): parts.append(f"Figure: {r['rate_value']} {r.get('rate_unit') or ''}".strip())
    if r.get('conditions'): parts.append('Conditions: ' + '; '.join(c['text'] for c in r['conditions']))
    if r.get('adjustments'): parts.append('Adjustments: ' + '; '.join(a['description'] for a in r['adjustments']))
    for z in r.get('tiers') or []:
        parts.append(f"Step {z.get('sequence')}: {z.get('rate_value') or 'no figure'} {z.get('rate_unit') or ''} "
                     f"{z.get('threshold_basis') or ''}".strip())
    return ' | '.join(parts)


def _reductions_to_adjustments(terms: list, notes: list) -> list:
    reductions = [t for t in terms if _is_reduction(t)]
    others = [t for t in terms if t not in reductions and t.get('family') in _ROYALTY_FAMILIES]
    out = list(terms)
    for r in reductions:
        target = None
        explicit = [t for t in others if _mentions(t, r['term_id'])]
        if len(explicit) == 1: target = explicit[0]
        elif not explicit and r.get('family') in _ROYALTY_FAMILIES:
            same = [t for t in others if t.get('family') == r.get('family')]
            if len(same) == 1: target = same[0]
        elif not explicit and len(others) == 1:
            # v0.13.11 (B3): an OTHER / FORMULA reduction in a reading with exactly ONE royalty term can only reduce that term.
            target = others[0]
        if target is None: continue
        merged = copy.deepcopy(target)
        merged['adjustments'].append({'description': _adjustment_text(r), 'evidence_ids': _all_evidence(r)})
        out[out.index(target)] = merged
        others[others.index(target)] = merged
        out.remove(r)
        notes.append({'rule': 'REDUCTION', 'kept': target['term_id'], 'removed': [r['term_id']], 'message':
                      f"CONSOLIDATED: {r['term_id']} converted to an adjustment on {target['term_id']} "
                      f"(reduction / offset / anti-stacking wording; figures and evidence kept)",
                      'evidence': _all_evidence(r)})
    return out


def consolidate(extraction: dict):
    """Return (new extraction, notes). The input is not modified; with no change the copy equals the input."""
    result = copy.deepcopy(extraction)
    notes: list = []
    terms = result.get('royalty_terms') or []
    for t in terms:
        for k in ('conditions', 'adjustments', 'tiers', 'evidence_ids', 'rate_evidence_ids', 'base_evidence_ids'):
            if not isinstance(t.get(k), list): return result, []        # malformed: leave to the source check
    quotes = {e.get('evidence_id'): e.get('quote') for e in result.get('evidence') or [] if isinstance(e, dict)}
    terms = _merge_variants(terms, notes, quotes)
    terms = _fold_unrated(terms, notes)
    terms = _reductions_to_adjustments(terms, notes)
    if not notes: return result, []
    original = {t['term_id'] for t in extraction.get('royalty_terms') or []}
    kept = {t['term_id'] for t in terms}
    mapping = {}
    for n in notes:
        for gone in n['removed']: mapping[gone] = n['kept']
    assert original - kept == set(mapping)
    result['royalty_terms'] = terms
    _remap_terms(result, mapping)
    index = {e.get('evidence_id'): e.get('passage_id') for e in result.get('evidence') or []}
    issues = list(result.get('open_issues') or [])
    for n in notes:
        passages = _union([index[e] for e in n['evidence'] if index.get(e)])
        if n['rule'] == 'UNRESOLVED':
            issues.append({'issue_id': stable_id('ISSUE-UNRESOLVED', n['kept'], *n['candidates']), 'severity': 'HIGH',
                           'status': 'OPEN', 'kind': 'UNRESOLVED_DUPLICATE', 'description': n['message'], 'passage_ids': passages})
            continue
        issues.append({'issue_id': stable_id('ISSUE-CONSOL', n['kept'], *n['removed']), 'severity': 'LOW',
                       'status': 'RESOLVED', 'kind': 'CONSOLIDATED', 'description': n['message'], 'passage_ids': passages})
        if n.get('unparsed_tiers'):
            issues.append({'issue_id': stable_id('ISSUE-TIERBOUNDS', n['kept']), 'severity': 'LOW', 'status': 'OPEN',
                           'kind': 'TIER_BOUNDS_NOT_PARSED',
                           'description': f"Tier(s) {', '.join(str(x) for x in n['unparsed_tiers'])} of {n['kept']} have no numeric lower/upper "
                                          f"bound (redacted, not a plain number, or not in the cited quotation); read threshold_basis (sheet 02).",
                           'passage_ids': passages})
    result['open_issues'] = issues
    for n in notes: n.pop('evidence', None)
    return result, notes
