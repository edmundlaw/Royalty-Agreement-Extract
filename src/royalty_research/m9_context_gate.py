"""M9 independent context-bearing economics gate.

This gate operates on *immutable M1 source passages*, not on the model's
occurrence labels. It intentionally does NOT change the M7 issued occurrence
manifest: old extraction attempts remain source-bound and can be revalidated.

Narrow high-confidence checks: percentage/threshold tables whose lead-in is an
explicit royalty/sublicense obligation; explicitly capped royalties. Ambiguous
contracts produce flags, never fabricated rates or an assurance of full recall.
"""
from __future__ import annotations

import re
from decimal import Decimal
from .m6_source_risk import number, _linked_amount

_TABLE_ROW = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*%\s*\|\s*(.+?)\s*$', re.I)
_CURRENCY = re.compile(r'(?:US\s*)?\$\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', re.I)
_TABLE_HEADER = re.compile(r'\b(?:percentage|percent|royalty\s+rate|aggregate\s+sublicense\s+fees|net\s+sales\s+tiers?)\b', re.I)
_ECONOMIC_LEAD = re.compile(r'\b(?:royalt(?:y|ies)|sublicen[sc](?:e|ing)\s+fees?|licen[sc](?:e|ing)\s+fees?)\b', re.I)
_SUBLICENSE_LEAD = re.compile(r'\b(?:sublicen[sc](?:e|ing)|sublicensee)\b', re.I)
_CAP = re.compile(r'\b(?:up\s+to\s+a\s+maximum|maximum\s+of|shall\s+not\s+exceed|capped\s+at|royalt(?:y|ies)\s+cap)\b', re.I)
_PERCENT_CAP = re.compile(r'\b(?:in\s+no\s+event|not\s+to\s+exceed|shall\s+not\s+exceed|capped\s+at)\b.{0,170}?\b(\d+(?:\.\d+)?)\s*%',re.I)


def _nearby_royalty_context(passages:list[dict], index:int):
    """Look backward, not forward, so later unrelated clauses cannot qualify a row."""
    row=passages[index]; section=row.get('section_guess')
    earlier=[]
    for p in passages[max(0,index-9):index]:
        if section and p.get('section_guess') and p['section_guess']!=section:
            # Include a prior subsection's parent heading, but never an unrelated article.
            if not (str(section).startswith(str(p['section_guess'])+'.')):
                continue
        earlier.append(p['text'])
    return '\n'.join(earlier[-8:])


def _value(v):
    if isinstance(v,bool):return None
    if isinstance(v,str):
        v=v.replace('$','').replace(',','').strip()
        if v.upper().startswith('US'):v=v[2:].strip()
    return number(v)


def _bounds_match(tier:dict, band:str):
    values=[number(z.group(1).replace(',','')) for z in _CURRENCY.finditer(band)]
    if not values:return True  # not a recognized monetary boundary; don't guess.
    lo=_value(tier.get('lower')); hi=_value(tier.get('upper'))
    if re.match(r'\s*<',band):return hi==values[0]
    if re.match(r'\s*>',band):return lo==values[0]
    if len(values)==2 and re.search(r'\s(?:--|\-|to|–|—)\s',band):
        return lo==values[0] and hi==values[1]
    return True


def check_context_economics(mapping:dict, extraction:dict):
    """Return source-triggered discrepancies. No reliance on AI labels/dispositions."""
    errors=[];warnings=[];tested=[]
    passages=mapping['passages']
    evidence={x.get('evidence_id'):x.get('passage_id') for x in extraction.get('evidence',[]) if isinstance(x,dict)}
    terms=[t for t in extraction.get('royalty_terms',[]) if isinstance(t,dict)]
    for index,p in enumerate(passages):
        pid=p['passage_id'];txt=p['text']
        row=_TABLE_ROW.match(txt)
        if row:
            context=_nearby_royalty_context(passages,index)
            # Both a recognizable table heading AND an economic lead-in are
            # required; mere references to royalties in an audit clause do not qualify.
            if _TABLE_HEADER.search(context) and _ECONOMIC_LEAD.search(context):
                declared=number(row.group(1)); band=row.group(2)
                matches=[]
                for t in terms:
                    for z in t.get('tiers') or []:
                        if not isinstance(z,dict):continue
                        if pid in {evidence.get(eid) for eid in z.get('evidence_ids',[])}:
                            matches.append((t,z))
                tested.append({'kind':'CONTEXTUAL_TIER_ROW','passage_id':pid,'source_rate':str(declared),'band':band})
                if not matches:
                    errors.append({'code':'M9_TIER_TABLE_ROW_MISSING', 'ref':pid,
                        'message':'Royalty/sublicense schedule table row has no source-cited tier record'})
                    continue
                correct=[(t,z) for t,z in matches if _value(z.get('rate_value'))==declared]
                if not correct:
                    errors.append({'code':'M9_TIER_RATE_ROW_MISMATCH','ref':pid,
                        'message':'Tier rate differs from the rate on its cited original table row'})
                    continue
                if not any(_bounds_match(z,band) for _,z in correct):
                    errors.append({'code':'M9_TIER_BAND_MISMATCH','ref':pid,
                        'message':'Tier threshold disagrees with the band printed on its cited source row'})
                if _SUBLICENSE_LEAD.search(context) and not any(t.get('family')=='SUBLICENSING_RECEIPTS' for t,_ in correct):
                    errors.append({'code':'M9_SUBLICENSE_TIER_MISCLASSIFIED','ref':pid,
                        'message':'Sublicense-fee table is linked to the wrong economic rate family'})
        cap_pct=_PERCENT_CAP.search(txt)
        if cap_pct and re.search(r'\b(?:revenue|royalt(?:y|ies)|sales|pay(?:ment|able)?)\b',txt,re.I):
            cap_rate=number(cap_pct.group(1))
            tested.append({'kind':'EXPLICIT_PERCENTAGE_CAP','passage_id':pid,'source_rate':str(cap_rate)})
            represented=False
            for t in terms:
                for item in (t.get('conditions') or []) + (t.get('adjustments') or []):
                    if not isinstance(item,dict):continue
                    if pid not in {evidence.get(eid) for eid in item.get('evidence_ids',[])}:continue
                    detail=str(item.get('text') or item.get('description') or '')
                    if any(number(match.group(1))==cap_rate for match in
                           re.finditer(r'(\d+(?:\.\d+)?)\s*%',detail)):
                        represented=True
            if not represented:
                errors.append({'code':'M9_PERCENT_ROYALTY_CAP_UNACCOUNTED','ref':pid,
                    'message':'Explicit percentage cap on royalty-related payments is absent from cited conditions/adjustments'})
        if _CAP.search(txt) and _ECONOMIC_LEAD.search(txt):
            # A clear number near an explicit royalty cap (rather than maximum
            # permitted late-payment interest) must be reflected in source-linked
            # economic records.
            if re.search(r'\blate\s+payments?|interest\s+charges?\b',txt,re.I) and not re.search(r'\bearned\s+royalt',txt,re.I):
                continue
            cap_clause=_CAP.search(txt)
            if not cap_clause:continue
            after=txt[cap_clause.start():cap_clause.start()+160]
            money=_CURRENCY.search(after)
            if money:
                amt=number(money.group(1).replace(',',''))
                tested.append({'kind':'EXPLICIT_ROYALTY_CAP','passage_id':pid,'source_amount':str(amt)})
                if not _linked_amount(extraction,pid,amt):
                    errors.append({'code':'M9_ROYALTY_CAP_UNACCOUNTED','ref':pid,
                        'message':'Source explicitly caps royalty at a monetary amount not supported by any cited condition/payment'})
    return {'schema':'m9-source-context.1','document_id':mapping['document_id'],
            'tests':tested,'errors':errors,'warnings':warnings,
            'deterministic_status':'FAIL' if errors else 'PASS_CONTEXT_RULES_ONLY'}
