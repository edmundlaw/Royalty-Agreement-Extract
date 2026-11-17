"""Independent source-ledger risk signals (M6).

This is NOT a classifier of contractual meaning. Signals are generated from the
immutable M1 map, not from model-authored passage dispositions. A source hit is
only marked covered when a linked extraction record cites its original passage
and explicitly includes its numeric value. Ambiguity is a *blocker* pending
independent interpretation, not evidence that the rate is absent.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .mapping import PERCENT, MONEY, REDACTION
from .storage import stable_id

POTENTIAL_RATE = re.compile(r"\b(?:royalt(?:y|ies)|sublicen[sc](?:e|ing)|licen[sc](?:e|ing)\s+fee|net\s+sales|running\s+fee)\b",re.I)
NONRATE = re.compile(r"\b(?:late\s+payments?|interest|penalt(?:y|ies)|audit|discrepanc(?:y|ies)|gross\s+profit|shortfall|underpayment|examination|inspection|discrepancy|ownership|shareholder|equity)\b",re.I)
SPECIAL_AMOUNT = re.compile(r"\b(?:minimum\s+(?:annual\s+)?royalt(?:y|ies)|minimum\s+payment|guaranteed\s+minimum|annual\s+minimum|royalt(?:y|ies)\s+cap|royalt(?:y|ies)(?:\s+\w+){0,10}\s+(?:limited\s+to|shall\s+not\s+exceed)|maximum\s+(?:annual\s+)?royalt|capped\s+at)\b",re.I)
REDUCTION = re.compile(r"\b(?:shall\s+be\s+(?:halved|reduced)|royalt(?:y|ies)\s+shall\s+(?:decrease|increase)|anti[- ]stacking|stacking\s+reduction)\b",re.I)


def number(v):
    if v is None or isinstance(v,bool):return None
    try:
        s=str(v).strip().replace(',','')
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)",s):return None
        d=Decimal(s)
        return d if d.is_finite() else None
    except (InvalidOperation,ValueError):return None


def source_hits(mapping):
    """Produce deterministic IDs and offsets for all numeric %/money/redactions.

    Every original passage is examined, even when M1 did not nominate it as a
    candidate. Risk labels are heuristic; absence of a label means nothing.
    """
    passages=mapping['passages']; hits=[]
    # Preserve table-header semantics across physically separate table rows.
    section_headers={}
    for p in passages:
        section=p.get('section_guess')
        if section and section not in section_headers:
            section_headers[section]=p['text'][:350]
    for ix,p in enumerate(passages):
        value=p['text']; pid=p['passage_id']
        prior=' '.join(q['text'][:140] for q in passages[max(0,ix-2):ix])
        header=section_headers.get(p.get('section_guess'),'')
        for kind,rx in [('PERCENT',PERCENT),('MONEY',MONEY),('REDACTION',REDACTION)]:
            for m in rx.finditer(value):
                left=value[max(0,m.start()-70):m.start()]
                right=value[m.end():min(len(value),m.end()+70)]
                vicinity=left+' '+m.group(0)+' '+right
                strong=bool(POTENTIAL_RATE.search(vicinity))
                unrelated=bool(NONRATE.search(vicinity)) and not bool(re.search(r'net\s+sales|royalt(?:y|ies)\s+(?:rate|fee)',vicinity,re.I))
                risk='INVENTORY_ONLY'
                if kind=='PERCENT' and strong and not unrelated:
                    risk='POTENTIAL_RUNNING_RATE'
                if kind=='MONEY' and (SPECIAL_AMOUNT.search(vicinity) or
                     (SPECIAL_AMOUNT.search(header) and (m.start()==0 or '|' in value)) or
                     (m.start()==0 and SPECIAL_AMOUNT.search(prior[-160:]))):
                    risk='POTENTIAL_MINIMUM_OR_CAP'
                if kind=='REDACTION' and (strong or POTENTIAL_RATE.search(value)):
                    risk='POTENTIAL_REDACTED_ECONOMICS'
                # "+/-70" vicinity is designed as a conservative high-risk flag,
                # not a conclusion that a percentage is legally a royalty.
                hits.append({'id':stable_id('OCC',pid,kind,str(m.start()),m.group(0)),
                    'passage_id':pid,'kind':kind,'start':m.start(),'end':m.end(),
                    'literal':m.group(0),'risk':risk,
                    'normalized':number(re.sub(r'[^0-9.]','',m.group(0))) if kind!='REDACTION' else None})
    return hits


def _evidence_passages(extraction, ids):
    e={x.get('evidence_id'):x.get('passage_id') for x in extraction.get('evidence',[]) if isinstance(x,dict)}
    return {e[i] for i in ids if i in e}


def _linked_percent(extraction,pid,rate):
    """A candidate percent must be represented by a rate or a cited adjustment."""
    for t in extraction.get('royalty_terms',[]):
        if not isinstance(t,dict):continue
        if number(t.get('rate_value'))==rate and pid in _evidence_passages(extraction,t.get('rate_evidence_ids',[])):
            return True
        for tier in t.get('tiers') or []:
            if isinstance(tier,dict) and number(tier.get('rate_value'))==rate and pid in _evidence_passages(extraction,tier.get('evidence_ids',[])):
                return True
        for a in t.get('adjustments') or []:
            if isinstance(a,dict) and pid in _evidence_passages(extraction,a.get('evidence_ids',[])):
                if any(number(re.sub(r'[^0-9.]','',m.group()))==rate for m in PERCENT.finditer(a.get('description',''))):
                    return True
    return False


def _linked_amount(extraction,pid,amount):
    for p in extraction.get('other_payments',[]):
        if isinstance(p,dict) and number(p.get('amount_value'))==amount and pid in _evidence_passages(extraction,p.get('evidence_ids',[])):
            return True
    # Instalment components and derived payments may be recorded in a
    # source-linked payment's basis/condition even if amount_value captures
    # the annual headline obligation. Exact numeric presence still required.
    for p in extraction.get('other_payments',[]):
        if not isinstance(p,dict) or pid not in _evidence_passages(extraction,p.get('evidence_ids',[])):
            continue
        for val in (p.get('basis'),p.get('condition')):
            for match in re.finditer(r'(?<![\w.])(?:US\s*)?\$?\s*(\d[\d,]*(?:\.\d+)?)',str(val or '')):
                if number(match.group(1))==amount:return True
    # A cap or guarantee can be represented as a linked royalty condition or
    # adjustment, rather than a distinct payment, but it must mention the amount.
    for t in extraction.get('royalty_terms',[]):
        if not isinstance(t,dict):continue
        for item in (t.get('conditions') or [])+(t.get('adjustments') or []):
            if isinstance(item,dict) and pid in _evidence_passages(extraction,item.get('evidence_ids',[])):
                s=str(item.get('text') or item.get('description') or '')
                for m in re.finditer(r'(?<![\w.])\d[\d,]*(?:\.\d+)?',s):
                    if number(m.group())==amount:return True
    return False


def check_source_risk(mapping,extraction):
    """Return fail-closed high-risk discrepancies independent of model labels.

    This is **not proof of recall**; an extracted term may still have the wrong
    base/threshold/structure, which requires a blind re-key and human benchmark.
    """
    errors=[];h=source_hits(mapping)
    evidence={e.get('evidence_id'):e.get('passage_id') for e in extraction.get('evidence',[]) if isinstance(e,dict)}
    source_by_pid={p['passage_id']:p['text'] for p in mapping['passages']}
    for t in extraction.get('royalty_terms',[]):
        if not isinstance(t,dict):continue
        # Detect an unambiguous mismatch between a claimed gross/net sales base
        # and the wording supporting the RATE. Legal bases still require review.
        claim=str(t.get('base') or '').lower()
        rate_pids={evidence[eid] for eid in (t.get('rate_evidence_ids') or []) if eid in evidence}
        if not rate_pids and t.get('tiers'):
            rate_pids={evidence[eid] for tier in t['tiers'] for eid in tier.get('evidence_ids',[]) if eid in evidence}
        for pid in rate_pids:
            source=source_by_pid.get(pid,'').lower()
            if (t.get('family')=='SUBLICENSING_RECEIPTS' and
                    re.search(r'\bof\s+net\s+sales\b',source) and
                    not re.search(r'sublicen[sc](?:e|ing)',source)):
                errors.append({'code':'SOURCE_RATE_FAMILY_CONTRADICTION',
                   'message':'Sub-licensing receipt classification conflicts with sales-based rate evidence',
                   'ref':t.get('term_id'),'passage_id':pid})
            if (t.get('family')=='PRODUCT_SALES' and
                    re.search(r'\bof\s+sublicen[sc](?:e|ing)\s+(?:fees|receipts|revenues)\b',source) and
                    not re.search(r'\bnet\s+sales\b',source)):
                errors.append({'code':'SOURCE_RATE_FAMILY_CONTRADICTION',
                   'message':'Product-sales classification conflicts with sublicense receipt rate evidence',
                   'ref':t.get('term_id'),'passage_id':pid})
            if 'gross sales' in claim and re.search(r'\bof\s+net\s+sales\b',source) and 'gross sales' not in source:
                errors.append({'code':'SOURCE_RATE_BASE_CONTRADICTION',
                     'message':'Claimed gross-sales base contradicts explicit net-sales rate evidence',
                     'ref':t.get('term_id'),'passage_id':pid})
            if 'net sales' in claim and re.search(r'\bof\s+gross\s+sales\b',source) and 'net sales' not in source:
                errors.append({'code':'SOURCE_RATE_BASE_CONTRADICTION',
                     'message':'Claimed net-sales base contradicts explicit gross-sales rate evidence',
                     'ref':t.get('term_id'),'passage_id':pid})
        # When a single paragraph lists exactly one literal % for each tier,
        # it is unsafe to assign them to different tier sequence positions.
        # This is a narrow syntactic check, NOT a tier-interpretation proof.
        tiers=t.get('tiers') or []
        if len(tiers)<2 or len({tier.get('sequence') for tier in tiers if isinstance(tier,dict)})!=len(tiers):
            continue
        tier_pids=[{evidence[eid] for eid in tier.get('evidence_ids',[]) if eid in evidence}
                   for tier in tiers if isinstance(tier,dict)]
        shared=set.intersection(*tier_pids) if tier_pids else set()
        for pid in shared:
            source_rates=[number(re.sub(r'[^0-9.]','',m.group())) for m in PERCENT.finditer(source_by_pid.get(pid,''))]
            declared=[number(tier.get('rate_value')) for tier in sorted(tiers,key=lambda k:k['sequence'])]
            if (len(source_rates)==len(declared) and all(v is not None for v in source_rates+declared)
                    and sorted(source_rates)==sorted(declared) and source_rates!=declared):
                errors.append({'code':'SOURCE_TIER_RATE_ORDER_CONFLICT',
                   'message':'Tier rate order contradicts the source paragraph; require independent rate-to-band re-key',
                   'ref':t.get('term_id'),'passage_id':pid})
    for hit in h:
        risk=hit['risk'];pid=hit['passage_id'];v=hit['normalized']
        if risk=='POTENTIAL_RUNNING_RATE' and v is not None:
            if not _linked_percent(extraction,pid,v):
                errors.append({'code':'SOURCE_RATE_UNACCOUNTED',
                    'message':'Source-local potential royalty percentage has no matching evidence-linked rate or adjustment; independent review required',
                    'ref':hit['id'],'passage_id':pid,'literal':hit['literal']})
        elif risk=='POTENTIAL_MINIMUM_OR_CAP' and v is not None:
            if not _linked_amount(extraction,pid,v):
                errors.append({'code':'SOURCE_SPECIAL_PAYMENT_UNACCOUNTED',
                    'message':'Potential minimum/cap amount has no evidence-linked payment or condition',
                    'ref':hit['id'],'passage_id':pid,'literal':hit['literal']})
        elif risk=='POTENTIAL_REDACTED_ECONOMICS':
            # Only require that the redaction has an explicit open issue or a
            # redacted rate term with cited source. A rate must never be guessed.
            redacted=any(t.get('disclosure_status')=='REDACTED' and pid in _evidence_passages(extraction,t.get('evidence_ids',[]))
                         for t in extraction.get('royalty_terms',[]) if isinstance(t,dict))
            open_issue=any(pid in (i.get('passage_ids') or []) and i.get('severity') in ('HIGH','CRITICAL')
                           and i.get('status')!='RESOLVED' for i in extraction.get('open_issues',[]) if isinstance(i,dict))
            if not (redacted or open_issue):
                errors.append({'code':'SOURCE_REDACTION_UNACCOUNTED',
                   'message':'Potential redacted royalty must be represented or remain an open blocker',
                   'ref':hit['id'],'passage_id':pid,'literal':hit['literal']})
    return errors,h
