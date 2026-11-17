"""M12 experimental economic-evidence accounting (no AI calls).

Source signals are hypotheses from a deterministic detector, not proof of
contract completeness. Each signal is closed by matching source-cited facts or
an evidence-checked non-economic classification. Open-issue narratives do not
close source signals. Unseen-contract independent testing is still required.
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from .storage import sha256, json_bytes, stable_id
from .m11_signal_qc import _numeric, _record_index, _rates as _m11_rates, _money as _m11_money

SCHEMA='m12-economic-flags.1'
REVISION='m12.0-source-occurrence-and-table-blocks'
_PERCENT=re.compile(r'(?<![\w.])(?:\d+(?:\.\d+)?|\.\d+)\s*(?:%|percent\b|per\s+cent\b)',re.I)
_WORDS=re.compile(r'\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty(?:[- ]\w+)?|thirty(?:[- ]\w+)?|forty(?:[- ]\w+)?|fifty(?:[- ]\w+)?|sixty(?:[- ]\w+)?|seventy(?:[- ]\w+)?|eighty(?:[- ]\w+)?|ninety(?:[- ]\w+)?|one[- ]half|two\s+and\s+one[- ]half)\s+(?:per\s+cent|percent)\b',re.I)
_MONEY=re.compile(r'(?<!\w)(?:US\s*)?\$\s*[\d,]+(?:\.\d+)?|\bUSD\s*[\d,]+(?:\.\d+)?\b',re.I)
_REDACT=re.compile(r'\[\s*(?:\*+|REDACTED|OMITTED)\s*\]|[■█]{2,}',re.I)
_ECON=re.compile(r'royalt(?:y|ies)|(?:net|gross)\s+sales|sublicen[sc](?:e|ing)\s+(?:fees?|income|receipt|revenue|consideration|share)|licen[sc](?:e|ing)\s+(?:fees?|payments?)|revenue\s+shar|(?:per|each)\s+(?:licensed\s+)?(?:unit|product|copy)|up[- ]?front|milestones?|minimum|payment',re.I)
_ROYALTY=re.compile(r'royalt(?:y|ies)|(?:net|gross)\s+sales|licen[sc]e\s+fee|sublicen[sc](?:e|ing)\s+(?:income|receipts|fees?|consideration|revenue|share)',re.I)
_AUDIT=re.compile(r'\baudit|examin(?:ation|e)|inspect|underpay(?:ment)?|discrepanc|\berror\s+in\s+royalties',re.I)
_INTEREST=re.compile(r'\blate[- ]?\s*payments?(?:\s+rate)?|\blate[- ]?\s*payment\s+rate|\binterest\s+(?:charges?|at|on|of|rate)|\bpenalt(?:y|ies)',re.I)
_OWNERSHIP=re.compile(r'\bequity\b|\bownership\b|\bsharehold|shares\s+of\s+(?:stock|capital)',re.I)
_INSURANCE=re.compile(r'\binsuran|insured|\bliability\s+coverage',re.I)
_STACK=re.compile(r'\bstacking\b|\banti[- ]?stack|third[- ]party\s+royalt|aggregate\s+royalt',re.I)
_FLOOR=re.compile(r'\bnot\s+(?:less|below)\b|\bfloor\b|\breduc(?:e|ed|tion)|\bdecreas(?:e|ed)|\boffset',re.I)
_STEP=re.compile(r'\b(?:step[- ]?up|step[- ]?down|increas(?:e|es|ed)|decreas(?:e|es|ed)|doubl(?:e|ed)|reduc(?:e|ed|tion))\b',re.I)
_SUB_RECEIPT=re.compile(r'\bsublicen[sc](?:e|ing)\s+(?:fees?|receipts?|income|revenues?|consideration|payments?|share)|non[- ]?royalty\s+sublicen[sc]e\s+income|\broyalt(?:y|ies)\s+on\s+sublicen[sc]',re.I)
_CAP=re.compile(r'royalt(?:y|ies)(?:\s+payments?)?.{0,180}(?:up\s+to\s+a\s+maximum\s+of|(?:shall|may|must|will)\s+not\s+exceed|shall\s+(?:be\s+)?limited\s+to|shall\s+not\s+exceed|(?:is|are)\s+capped\s+at|\bcap(?:ped)?\s+(?:at|of)|maximum\s+of|\bceiling\b)|(?:cap|ceiling|limit|maximum)\s+(?:on|of|for)?\s*(?:annual\s+|earned\s+|total\s+)?royalt',re.I)
_MIN=re.compile(r'guaranteed\s+minimum|minimum\s+(?:annual\s+|guaranteed\s+)?royalt|annual\s+minimum|\bminim(?:um|a)\s+(?:royalty|payment)',re.I)
_UPFRONT=re.compile(r'up[- ]?front|initial\s+(?:licen[sc]e\s+)?fee|licen[sc]e\s+issue\s+fee|\bissue\s+fee|\bsigning\s+fee|non[- ]?refundable\s+licen[sc]e\s+fee',re.I)
_MAINT=re.compile(r'\bmaintenance\s+fee|annual\s+licen[sc]e\s+fee|\blicen[sc]e\s+maintenance',re.I)
_MILE=re.compile(r'\bmilestones?|upon\s+(?:fda\s+)?approval|upon\s+\w+\s+approval|following\s+regulatory\s+approval|upon\s+(?:commercialization|commercialisation)|development\s+payment|\bon\s+(?:commerciali[sz]ation|regulatory\s+approval|product\s+launch)|\bupon\s+(?:launch|first\s+sale|first\s+commercial\s+sale)',re.I)
_PAYMENT=re.compile(r'\bpay(?:ment|able|ee|s)?\b|\bfee\b|\bshall\s+remit|\bwill\s+remit|becomes?\s+due|\bowes?\b',re.I)
_PER_UNIT=re.compile(r'(?:\bper|\bfor)\s+(?:each|every|one|a|the)?\s*(?:licensed\s+)?(?:product|unit|device|copy|item|dose|sale)\b|(?:licensed\s+)?(?:products?|units?)\s+sold',re.I)
_TABLE_HEAD=re.compile(r'royalt(?:y|ies)|\brate|percentage|\bnet\s+sales|sublicen[sc]|\bminimum|\bmilestone|\bpayment\s+amount|licen[sc]e\s+fee',re.I)
_STOP_ROW=re.compile(r'^\s*(?:ARTICLE|SECTION|SCHEDULE|APPENDIX)\s+[A-Z0-9]+',re.I)


def _d(v):
    return _numeric(v)


def _rate_hits(s):
    """Coalesce 'three percent (3%)'; do not coalesce distinct rate occurrences."""
    hits=[{'start':a,'end':b,'value':v,'literal':lit} for a,b,v,lit in _m11_rates(s)]
    hits.sort(key=lambda h:h['start'])
    result=[];i=0
    while i<len(hits):
        h=hits[i]
        if i+1<len(hits):
            n=hits[i+1]
            gap=s[h['end']:n['start']]
            # Only an exact adjacent parenthetical repetition, not two obligations.
            if (h['value']==n['value'] and re.fullmatch(r'\s*\(\s*',gap) and
                    re.match(r'\s*\)',s[n['end']:]) and not re.search(r'\d',h['literal'])):
                result.append({'start':h['start'],'end':n['end']+len(re.match(r'\s*\)',s[n['end']:]).group()),
                               'value':h['value'],'literal':s[h['start']:n['end']+1]})
                i+=2;continue
        result.append(h);i+=1
    return result


def _amount_hits(s):
    return [{'start':a,'end':b,'value':v,'literal':lit} for a,b,v,lit in _m11_money(s)]


def _fragment(s,start,end):
    """Bound semantic cue to its own clause, not arbitrary words in the passage."""
    left=max(s.rfind(';',0,start),s.rfind('\n',0,start),s.rfind(' . ',0,start))
    right=[p for p in (s.find(';',end),s.find('\n',end)) if p>=0]
    return s[max(left+1,start-180):min(min(right) if right else len(s),end+170)]


def _rate_role(s,h):
    frag=_fragment(s,h['start'],h['end']);before=s[max(0,h['start']-270):h['start']]
    tail=s[h['end']:h['end']+85]
    if re.search(r'(?:deductions?|allowable\s+discounts?).{0,180}(?:cap(?:ped)?|maximum|lesser|limit|shall\s+not\s+exceed)',before[-260:],re.I) or re.search(r'deductions?.{0,200}shall\s+not\s+exceed',before[-260:],re.I):
        return 'ADJUSTMENT_THRESHOLD'
    if re.match(r'\s+(?:on|of)\s+(?:the\s+)?(?:net|gross)\s+sales',tail,re.I):return 'ROYALTY'
    if _INTEREST.search(before) and not re.search(r'\bpay\s+royalt(?:y|ies)|royalt(?:y|ies)\s+(?:of|at|equal|rate)',before[-90:],re.I):return 'INTEREST'
    if re.search(r'\bgross\s+profit|\bmargin\b',before[-110:]):return 'GROSS_MARGIN'
    if re.search(r'milestone.{0,70}(?:creditable|reduction)|reduction\s+of\s+no\s+more\s+than',before[-140:],re.I):return 'ADJUSTMENT_THRESHOLD'
    if _INSURANCE.search(frag):return 'INSURANCE'
    if _AUDIT.search(before) and re.search(r'(?:threshold|discrepanc|underpay|err(?:or|ors?)|examin|\bover\b|reimburs|shortfall)',frag,re.I):return 'AUDIT'
    if re.search(r'\bnumber\s+of\s+shares|\bshares\s+of\s+(?:the\s+)?(?:licen[sc]ee|company)',s[h['end']:h['end']+140],re.I):return 'OWNERSHIP'
    if _OWNERSHIP.search(before) and not re.search(r'\b(?:in\s+lieu\s+of\s+equity|in\s+exchange\s+for\s+equity).*\b(?:pay|remit|royalt)',frag,re.I):return 'OWNERSHIP'
    if re.search(r'\b(?:net|gross)\s+sales\s+(?:are|were|is)\s*$',before[-30:],re.I) and re.search(r'\b(?:above|below|greater|less|more)(?:\s+than|\s+above|\s+below)?\s+(?:projections?|forecast|target)',tail,re.I):return 'ADJUSTMENT_THRESHOLD'
    if (_STACK.search(frag) or _FLOOR.search(frag)) and re.search(r'exceed|not\s+below|not\s+less|stack|third.party',frag,re.I):return 'ADJUSTMENT_THRESHOLD'
    if _ROYALTY.search(frag) or _SUB_RECEIPT.search(frag) or re.search(r'\b(?:fee|payment)\s+(?:of|at|equal\s+to|equals?)',before[-110:],re.I):return 'ROYALTY'
    return 'UNKNOWN_FINANCIAL'


def _amount_role(s,h,*,in_table=False):
    before=s[max(0,h['start']-130):h['start']]
    after=s[h['end']:min(len(s),h['end']+65)]
    frag=_fragment(s,h['start'],h['end'])
    if _CAP.search(before[-170:]+s[h['start']:h['end']]+after):return 'CAP'
    if _MIN.search(before[-125:]) or (in_table and _MIN.search(frag)):
        return 'MINIMUM_ROYALTY'
    # A single minimum-royalty sentence can specify successive annual periods,
    # e.g. $200,000 followed by $300,000. Do not require each figure to
    # repeat the word 'minimum'. The monthly installment needs a typed link.
    if _MIN.search(s[:160]) and not (_MILE.search(frag) or _UPFRONT.search(frag)):
        return 'MINIMUM_ROYALTY'
    if _MAINT.search(before[-110:]) or re.search(r'maintenance\s+fees?',after[:40],re.I):return 'MAINTENANCE_FEE'
    if _UPFRONT.search(before[-110:]) or (in_table and _UPFRONT.search(frag)):return 'UPFRONT_FEE'
    if _MILE.search(before[-125:]) or (in_table and _MILE.search(frag)) or re.search(r'\bupon\s+approval\b',before[-125:],re.I):return 'MILESTONE'
    if _PER_UNIT.search(frag) and (_ROYALTY.search(frag) or re.search(r'\bremit|\bpay|\bfee',frag,re.I)):
        return 'PER_UNIT_RATE'
    if _MIN.search(frag) and re.search(r'\bmonthly|per\s+month|\bannual|per\s+year',frag,re.I):return 'MINIMUM_ROYALTY'
    return None


def _table_rows(passages):
    """Join explicit pipe rows and bounded adjacent separate-cell rows.

    Never synthesize legal text: preserve original passage IDs and require source
    citations to the actual rate cell. A data row is contextualized by header.
    """
    rows=[];used=set();active=None;gap=0;ix=0
    n=len(passages)
    while ix<n:
        s=passages[ix]['text'].strip()
        if '|' in s:
            cells=[v.strip() for v in s.split('|')]
            if _TABLE_HEAD.search(s) and (re.search(r'\brate|percentage|amount|royalt|minimum|milestone',s,re.I) or '|' in s):
                active={'header':s,'lead':' '.join(p['text'][:180] for p in passages[max(0,ix-4):ix]), 'type':'pipe'};gap=0;ix+=1;continue
            if active and active['type']=='pipe' and len(cells)>=2 and (_rate_hits(s) or _REDACT.search(s) or _amount_hits(s)):
                rows.append({'rate_index':ix,'indices':[ix],'text':s,'header':active['header'],'lead':active['lead']});used.add(ix);gap=0;ix+=1;continue
            if active and active['type']=='pipe' and not s:ix+=1;continue
            if active is None and len(cells)>=2 and (_rate_hits(s) or _REDACT.search(s) or _amount_hits(s)):
                lead=' '.join(p['text'][:180] for p in passages[max(0,ix-6):ix])
                if _TABLE_HEAD.search(lead) and re.search(r'\b(?:following|minimum|guaranteed|royalt|tier|sublicen|milestone)',lead,re.I):
                    active={'header':'','lead':lead,'type':'pipe'}
                    rows.append({'rate_index':ix,'indices':[ix],'text':s,'header':'','lead':lead});used.add(ix);ix+=1;continue
        if active and active['type']=='pipe':
            if not s or re.fullmatch(r'(?:page\s*)?\d+(?:\s+of\s+\d+)?',s,re.I):
                gap+=1
                if gap<=2:ix+=1;continue
            active=None;gap=0
        # Separate-cell table: a semantic header line, or two adjacent header cells.
        if '|' not in s and len(s)<=80 and _TABLE_HEAD.search(s) and ix+1<n and '|' not in passages[ix+1]['text']:
            nxt=passages[ix+1]['text'].strip()
            adjacent_header=(('rate' in s.lower() or 'percentage' in s.lower()) and ('sales' in nxt.lower() or 'tier' in nxt.lower() or 'fees' in nxt.lower())) or \
                            (('sales' in s.lower() or 'fees' in s.lower()) and ('rate' in nxt.lower() or 'percentage' in nxt.lower()))
            if adjacent_header:
                lead=' '.join(p['text'][:150] for p in passages[max(0,ix-4):ix])
                j=ix+2;found=0
                while j+1<n and found<60:
                    a=passages[j]['text'].strip();b=passages[j+1]['text'].strip()
                    if _STOP_ROW.search(a) or _STOP_ROW.search(b):break
                    one=_rate_hits(a) or _REDACT.search(a);two=_rate_hits(b) or _REDACT.search(b)
                    if one and ( _amount_hits(b) or re.search(r'\b(?:under|above|less|greater|over|between|up\s+to)\b',b,re.I) or _REDACT.search(b)):
                        rate_ix=j
                    elif two and ( _amount_hits(a) or re.search(r'\b(?:under|above|less|greater|over|between|up\s+to)\b',a,re.I) or _REDACT.search(a)):
                        rate_ix=j+1
                    else:break
                    rows.append({'rate_index':rate_ix,'indices':[j,j+1], 'text':a+' | '+b, 'header':s+' | '+nxt,'lead':lead})
                    used.update((j,j+1));found+=1;j+=2
                if found:ix=j;continue
        ix+=1
    return rows,used


def issue_signals(mapping):
    ps=mapping['passages'];signals=[];rows,used=_table_rows(ps)
    def emit(kind,ix,*,value=None,role=None,detail=None,ordinal=0,related=None):
        p=ps[ix];pid=p['passage_id']
        core={'RATE','PER_UNIT_RATE','CAP','MINIMUM_ROYALTY','ADJUSTMENT'}
        if kind=='TABLE_ROW':
            severe='WARNING' if role in {'MILESTONE','UPFRONT_FEE','MAINTENANCE_FEE'} else 'HARD'
        elif kind=='REDACTED_ECONOMIC':
            severe='WARNING' if role=='SUPPORTING_PAYMENT' else 'HARD'
        else:
            severe='HARD' if kind in core else ('INFORMATION' if kind=='NON_ECONOMIC_PERCENT' else 'WARNING')
        detail=detail or {}
        raw={'signal_id':stable_id('SIG12',pid,kind,str(value),str(role),str(ordinal),str(detail.get('span_start'))),
           'passage_id':pid,'kind':kind,'role':role,'value':str(value) if value is not None else None,
           'severity':severe,'detail':detail,'source_text_sha256':mapping['text_sha256'],
           'related_passage_ids':related or [],'excerpt':p['text'][:2000]}
        signals.append(raw)
    for row in rows:
        ix=row['rate_index']; s=ps[ix]['text']
        context=row['lead']+' '+row['header']
        role='SUBLICENSING' if _SUB_RECEIPT.search(context) else ('MINIMUM_ROYALTY' if _MIN.search(context) or re.search(r'minimum\s+royalt',context,re.I) else ('MILESTONE' if _MILE.search(context) else 'ROYALTY'))
        # For separated cells recover both pieces, but rates always attach to original cell.
        vals=[str(x['value']) for x in _rate_hits(s)]
        reds=bool(_REDACT.search(s))
        amounts=[str(a['value']) for a in _amount_hits(row['text'])]
        emit('TABLE_ROW',ix,role=role,detail={'rates':vals,'amounts':amounts,'redacted':reds,
                  'table_header':row['header'][:220],'row_text':row['text'][:400],
                  'support_passage_ids':[ps[i]['passage_id'] for i in row['indices']]},related=[ps[i]['passage_id'] for i in row['indices'] if i!=ix])
    for ix,p in enumerate(ps):
        s=p['text'];hits=_rate_hits(s);amounts=_amount_hits(s)
        # Financial schedules commonly give a milestone heading once, then
        # '(a)', '(b)' rows with only amounts and trigger descriptions.
        preceding=' '.join(x['text'][:250] for x in ps[max(0,ix-5):ix])
        milestone_row=bool(re.match(r'^\s*\([a-z]\)',s,re.I) and _MILE.search(preceding) and
            not re.search(r'\b(?:creditable|offset|interest)\b',s[:100],re.I))
        if ix not in used:
            for j,h in enumerate(hits):
                # Distinguish non-royalty numbers by local role, never blanket exemptions.
                role=_rate_role(s,h)
                if role=='UNKNOWN_FINANCIAL' and not _ECON.search(_fragment(s,h['start'],h['end'])):continue
                kind='NON_ECONOMIC_PERCENT' if role in {'INTEREST','AUDIT','OWNERSHIP','INSURANCE','GROSS_MARGIN'} else 'RATE'
                if role=='ADJUSTMENT_THRESHOLD':kind='ADJUSTMENT'
                emit(kind,ix,value=h['value'],role=role,detail={'literal':h['literal'],'span_start':h['start'],'span_end':h['end']},ordinal=j)
            # Group actual redacted expressions; non-economic mere word 'redacted' is not one.
            redacts=list(_REDACT.finditer(s))
            if redacts and _ECON.search(s) and not hits:
                groups=[]
                for m in redacts:
                    local=_fragment(s,m.start(),m.end())
                    if not _ECON.search(local):continue
                    if groups and m.start()-groups[-1][-1].end()<=16:groups[-1].append(m)
                    else:groups.append([m])
                for j,cluster in enumerate(groups):
                    frag=_fragment(s,cluster[0].start(),cluster[-1].end())
                    support=bool((_UPFRONT.search(frag) or _MILE.search(frag) or _MAINT.search(frag)) and
                                 not _SUB_RECEIPT.search(frag) and not re.search(r'royalt(?:y|ies)\s+(?:rates?|shares?)',frag,re.I))
                    emit('REDACTED_ECONOMIC',ix,role='SUPPORTING_PAYMENT' if support else 'UNDISCLOSED',detail={'redacted':True,'offset_start':cluster[0].start(),
                          'offset_end':cluster[-1].end()},ordinal=j)
            for j,h in enumerate(amounts):
                role=_amount_role(s,h)
                if role is None and milestone_row:role='MILESTONE'
                if role is not None:
                    emit(role,ix,value=h['value'],detail={'literal':h['literal'],'span_start':h['start'],'span_end':h['end']},ordinal=j)
            # economic redaction in a per-unit payment without $ amount
            if not hits and not amounts and not redacts and _ECON.search(s) and re.search(r'\b(?:specified|set\s+forth|as\s+provided)\s+in\s+(?:schedule|exhibit|appendix)',s,re.I):
                emit('CROSS_REFERENCE',ix,role='ECONOMIC_CROSS_REFERENCE')
    payload={'schema':SCHEMA,'revision':REVISION,'document_id':mapping['document_id'],
             'source_text_sha256':mapping['text_sha256'],'signals':signals}
    # Signals are distinct source events; stable ID includes original occurrence position.
    payload['manifest_sha256']=sha256(json_bytes(payload))
    return payload


def _index(extraction):
    terms,payments,cites,associated=_record_index(extraction)
    return terms,payments,cites,associated


def _numeric_match(signal,record):
    val=_d(signal.get('value'))
    if val is None:return True
    return val==_d(record.get('rate_value')) or val==_d(record.get('amount_value'))


def _record_closes(signal,typ,rid,seq,extraction):
    terms,payments,cites,associated=_index(extraction)
    kind=signal['kind'];pid=signal['passage_id'];val=_d(signal.get('value'))
    red=bool(signal['detail'].get('redacted'))
    if typ=='TIER':
        t=terms.get(rid)
        z=next((x for x in (t or {}).get('tiers',[]) if x.get('sequence')==seq),None)
        if not z or not cites(z,pid):return False
        if kind not in {'TABLE_ROW','RATE','REDACTED_ECONOMIC'}:return False
        if signal.get('role')=='SUBLICENSING' and t.get('family')!='SUBLICENSING_RECEIPTS':return False
        if signal.get('role')=='ROYALTY' and t.get('family')=='SUBLICENSING_RECEIPTS':return False
        rates={_d(x) for x in signal['detail'].get('rates',[])}
        if rates and _d(z.get('rate_value')) not in rates:return False
        bounds={_d(z.get('lower')),_d(z.get('upper'))}
        thresholds={_d(x) for x in signal['detail'].get('amounts',[])}
        if thresholds and not thresholds.issubset(bounds):return False
        if val is not None and _d(z.get('rate_value'))!=val:return False
        if red and (z.get('rate_value') is not None or z.get('rate_unit')!='REDACTED'):return False
        return True
    if typ=='ROYALTY_TERM':
        t=terms.get(rid)
        if not t or not associated(t,pid):return False
        if kind not in {'RATE','TABLE_ROW','REDACTED_ECONOMIC','PER_UNIT_RATE'}:return False
        if kind=='TABLE_ROW' and t.get('structure')=='TIERED':return False
        if kind=='RATE' and t.get('structure') in {'TIERED','STEP_UP','STEP_DOWN'}:
            return False
        if kind=='TABLE_ROW' and signal['detail'].get('rates') and _d(t.get('rate_value')) not in {_d(v) for v in signal['detail']['rates']}:return False
        if signal.get('role')=='SUBLICENSING' and t.get('family')!='SUBLICENSING_RECEIPTS':return False
        if val is not None and _d(t.get('rate_value'))!=val:return False
        if red and (t.get('rate_value') is not None or t.get('disclosure_status')!='REDACTED'):return False
        if kind=='PER_UNIT_RATE' and t.get('rate_unit')!='CURRENCY_PER_UNIT':return False
        return True
    if typ=='PAYMENT':
        p=payments.get(rid)
        if not p or not cites(p,pid):return False
        allowed={'CAP':{'CAP'},'MINIMUM_ROYALTY':{'MINIMUM_ROYALTY','GUARANTEE'},
           'UPFRONT_FEE':{'UPFRONT'},'MAINTENANCE_FEE':{'OTHER','SERVICE'},'MILESTONE':{'MILESTONE'},
           'TABLE_ROW':{'MILESTONE','MINIMUM_ROYALTY','GUARANTEE','OTHER'},
           'REDACTED_ECONOMIC':{'MILESTONE','MINIMUM_ROYALTY','GUARANTEE','UPFRONT','OTHER'}}
        if kind not in allowed or p.get('kind') not in allowed[kind]:return False
        if kind=='TABLE_ROW' and signal.get('role') in {'ROYALTY','SUBLICENSING'}:return False
        if kind=='TABLE_ROW' and signal.get('role')=='MINIMUM_ROYALTY' and p.get('kind') not in {'MINIMUM_ROYALTY','GUARANTEE'}:return False
        if kind=='TABLE_ROW' and signal.get('role')=='MILESTONE' and p.get('kind')!='MILESTONE':return False
        if kind=='REDACTED_ECONOMIC' and signal.get('role')=='SUPPORTING_PAYMENT' and p.get('kind') not in {'UPFRONT','MILESTONE','OTHER','SERVICE'}:return False
        if kind=='TABLE_ROW':
            amounts={_d(v) for v in signal['detail'].get('amounts',[])}
            if amounts and _d(p.get('amount_value')) not in amounts:return False
        if val is not None and _d(p.get('amount_value'))!=val:return False
        if red and not(p.get('amount_value') is None and p.get('disclosure_status')=='REDACTED'):return False
        return True
    if typ=='ADJUSTMENT':
        t=terms.get(rid)
        if not t or kind not in {'ADJUSTMENT','RATE'}:return False
        if kind=='RATE' and signal.get('role')!='ADJUSTMENT_THRESHOLD':return False
        adj=[a for a in (t.get('adjustments') or [])+(t.get('conditions') or []) if isinstance(a,dict) and cites(a,pid)]
        if not adj:return False
        if val is None:return True
        return any(val==h['value'] for a in adj for h in _rate_hits(str(a.get('description') or a.get('text') or '')))
    return False


def _typed_closes(signal,reason,target_id,extraction):
    kind=signal['kind'];role=signal.get('role');s=signal['excerpt']
    if kind=='NON_ECONOMIC_PERCENT':
        return ({'AUDIT':'AUDIT_THRESHOLD','INTEREST':'NON_ROYALTY_INTEREST','OWNERSHIP':'OWNERSHIP_PERCENT',
                 'INSURANCE':'INSURANCE_LIMIT','GROSS_MARGIN':'NON_ROYALTY_MARGIN'}.get(role)==reason)
    if kind=='CROSS_REFERENCE' and reason=='CROSS_REFERENCE_ONLY':
        terms,payments,cites,associated=_index(extraction)
        if not target_id:return False
        return (target_id in terms and associated(terms[target_id],signal['passage_id'])) or \
               (target_id in payments and cites(payments[target_id],signal['passage_id']))
    if kind=='MINIMUM_ROYALTY' and reason=='INSTALLMENT_COMPONENT':
        _,payments,cites,_=_index(extraction)
        p=payments.get(target_id)
        amount=_d(signal['value']);annual=_d(p.get('amount_value')) if p else None
        return bool(p and cites(p,signal['passage_id']) and amount is not None and annual==amount*12
            and re.search(r'month(?:ly)?|per\s+month',s,re.I))
    if kind=='RATE' and reason in {'STACKING_THRESHOLD','REDUCTION_FLOOR'}:
        return _record_closes(signal,'ADJUSTMENT',target_id,None,extraction)
    return False


def propose_verified_closures(mapping,extraction):
    result=[]
    terms,payments,_,_=_index(extraction)
    for flag in issue_signals(mapping)['signals']:
        if flag['kind']=='NON_ECONOMIC_PERCENT':
            reason={'AUDIT':'AUDIT_THRESHOLD','INTEREST':'NON_ROYALTY_INTEREST','OWNERSHIP':'OWNERSHIP_PERCENT','INSURANCE':'INSURANCE_LIMIT','GROSS_MARGIN':'NON_ROYALTY_MARGIN'}.get(flag['role'])
            if reason:result.append({'signal_id':flag['signal_id'],'resolution':'TYPED_EXPLANATION','reason':reason})
            continue
        c=[]
        for t in terms.values():
            id=t['term_id']
            for typ in ('ROYALTY_TERM','ADJUSTMENT'):
                if _record_closes(flag,typ,id,None,extraction):c.append({'signal_id':flag['signal_id'],'resolution':'LINKED_RECORD','record_type':typ,'record_id':id})
            for z in t.get('tiers',[]):
                if _record_closes(flag,'TIER',id,z.get('sequence'),extraction):
                    c.append({'signal_id':flag['signal_id'],'resolution':'LINKED_RECORD','record_type':'TIER','record_id':id,'tier_sequence':z['sequence']})
        for p in payments.values():
            if _record_closes(flag,'PAYMENT',p['payment_id'],None,extraction):
                c.append({'signal_id':flag['signal_id'],'resolution':'LINKED_RECORD','record_type':'PAYMENT','record_id':p['payment_id']})
        # Prefer a precisely valued tier over its parent term in tiered/step-up
        # families. The parent and child can both cite the same paragraph.
        tiers=[x for x in c if x['record_type']=='TIER']
        if len(tiers)==1 and flag['kind'] in {'RATE','TABLE_ROW'}:c=tiers
        # More than one genuinely different candidate must remain open.
        if len(c)==1:result.append(c[0])
        elif not c and flag['kind']=='MINIMUM_ROYALTY':
            targets=[p['payment_id'] for p in payments.values()
                     if _typed_closes(flag,'INSTALLMENT_COMPONENT',p['payment_id'],extraction)]
            if len(targets)==1:result.append({'signal_id':flag['signal_id'],
                'resolution':'TYPED_EXPLANATION','reason':'INSTALLMENT_COMPONENT','target_id':targets[0]})
    return result


def reconcile_signals(mapping,extraction,resolutions=None):
    issued=issue_signals(mapping); lookup={x['signal_id']:x for x in issued['signals']}
    errors=[];warnings=[];closed=[];open_flags=[];answers={}
    if mapping['document_id']!=extraction.get('document_id') or mapping['text_sha256']!=extraction.get('source_text_sha256'):
        errors.append({'code':'M12_SOURCE_MISMATCH'})
    for item in resolutions or []:
        if not isinstance(item,dict) or item.get('signal_id') not in lookup:
            errors.append({'code':'M12_UNISSUED_SIGNAL','ref':item.get('signal_id') if isinstance(item,dict) else None});continue
        if item['signal_id'] in answers:
            errors.append({'code':'M12_DUPLICATE_RESOLUTION','ref':item['signal_id']});continue
        answers[item['signal_id']]=item
    for s in issued['signals']:
        r=answers.get(s['signal_id']);valid=False
        if r:
            valid=(_record_closes(s,r.get('record_type'),r.get('record_id'),r.get('tier_sequence'),extraction)
                   if r.get('resolution')=='LINKED_RECORD' else
                   _typed_closes(s,r.get('reason'),r.get('target_id'),extraction)
                   if r.get('resolution')=='TYPED_EXPLANATION' else False)
        if valid:closed.append({'signal_id':s['signal_id'],'resolution':r['resolution'],
                               'target':r.get('record_id') or r.get('target_id'),'reason':r.get('reason')})
        else:
            if r:errors.append({'code':'M12_INVALID_CLOSURE','ref':s['signal_id']})
            open_flags.append(s)
    # Repeated identical numerical rates in a single paragraph are distinct
    # occurrences unless coalesced as 'three percent (3%)' during issuance.
    # One term must not silently cover two separate commercial obligations.
    numeric_targets=defaultdict(list)
    for c in closed:
        flag=lookup[c['signal_id']]; r=answers[c['signal_id']]
        if flag['kind']!='RATE' or r.get('resolution')!='LINKED_RECORD':continue
        key=(flag['passage_id'],flag['value'],r.get('record_type'),r.get('record_id'),r.get('tier_sequence'))
        numeric_targets[key].append(flag['signal_id'])
    reused={sid for ids in numeric_targets.values() if len(ids)>1 for sid in ids}
    if reused:
        for sid in sorted(reused):
            errors.append({'code':'M12_DISTINCT_RATE_OCCURRENCES_REUSED','ref':sid})
            open_flags.append(lookup[sid])
        closed=[x for x in closed if x['signal_id'] not in reused]
    # Do not allow the same row to satisfy multiple genuinely independent
    # redacted obligations. Adjacent wording+numeric equivalents were merged at issuance.
    target_use=defaultdict(list)
    for x in closed:
        flag=lookup[x['signal_id']];r=answers[x['signal_id']]
        if flag['kind'] in {'TABLE_ROW','REDACTED_ECONOMIC'} and flag['detail'].get('redacted'):
            target_use[(r.get('record_type'),r.get('record_id'),r.get('tier_sequence'))].append(x['signal_id'])
    dup={sid for ids in target_use.values() if len(ids)>1 for sid in ids}
    if dup:
        for sid in sorted(dup):errors.append({'code':'M12_REDACTED_RECORD_REUSED','ref':sid});open_flags.append(lookup[sid])
        closed=[x for x in closed if x['signal_id'] not in dup]
    hard=[x for x in open_flags if x['severity']=='HARD']
    supporting=[x for x in open_flags if x['severity']=='WARNING']
    for x in hard:errors.append({'code':'M12_HARD_FLAG_OPEN','ref':x['signal_id'],'kind':x['kind']})
    for x in supporting:warnings.append({'code':'M12_SUPPORTING_FLAG_OPEN','ref':x['signal_id'],'kind':x['kind']})
    status=('FAIL_INTEGRITY' if any(x['code'] in {'M12_UNISSUED_SIGNAL','M12_DUPLICATE_RESOLUTION','M12_SOURCE_MISMATCH'} for x in errors) else
        'INCOMPLETE_CORE_ECONOMICS' if hard or any(x['code'] in {'M12_INVALID_CLOSURE','M12_REDACTED_RECORD_REUSED'} for x in errors) else
        'INCOMPLETE_SUPPORTING_ECONOMICS' if supporting else 'PASS_SOURCE_FLAGS_ONLY')
    # Quantify what the deterministic detector did not issue. This is a
    # screening risk indicator, not a measured false-negative count. It makes
    # it impossible to interpret a closed flag ledger as whole-document recall.
    flagged_passages={f['passage_id'] for f in issued['signals']}
    flagged_passages.update(pid for f in issued['signals'] for pid in f.get('related_passage_ids',[]))
    suspected=[]
    for p in mapping.get('passages',[]):
        reasons=set(p.get('candidate_reasons') or [])
        if ('FINANCE_VOCAB' in reasons and reasons.intersection(
                {'MONEY','PERCENT','REDACTION','SPELLED_RATE','SPELLED_FRACTION','INDIRECT_ECONOMICS','PER_UNIT'})
            and p['passage_id'] not in flagged_passages):
            suspected.append(p['passage_id'])
    return {'schema':'m12-qc.1','revision':REVISION,'document_id':mapping['document_id'],
            'screening_coverage':'UNVERIFIED_NOT_FULL_CONTRACT_RECALL',
            'unflagged_financial_candidate_count':len(suspected),
            'unflagged_financial_candidate_ids':suspected,
       'manifest_sha256':issued['manifest_sha256'],'status':status,'source_signal_count':len(issued['signals']),
       'closed_count':len(closed),'hard_open':len(hard),'warning_open':len(supporting),
       'closed':closed,'open_flags':open_flags,'errors':errors,'warnings':warnings,
       'notice':'PASS_SOURCE_FLAGS_ONLY means only detected source signals are accounted for, not full-document accuracy or recall.'}


def reconcile_with_proposals(mapping,extraction,resolutions=None):
    explicit=list(resolutions or []);known={x.get('signal_id') for x in explicit if isinstance(x,dict)}
    proposed=[x for x in propose_verified_closures(mapping,extraction) if x['signal_id'] not in known]
    q=reconcile_signals(mapping,extraction,explicit+proposed)
    q['auto_proposed']=len(proposed);q['explicit_resolutions']=len(explicit)
    return q


def build_correction_packet(mapping,extraction,*,resolutions=None,max_chars=1800,max_total_chars=36000):
    """Produce at most one targeted correction task; no model call.

    Every open economic source flag is included or the packet is marked unsafe
    to send. Missing flags remain visible and are never implicitly dismissed.
    """
    q=reconcile_with_proposals(mapping,extraction,resolutions)
    if q['status']=='FAIL_INTEGRITY':raise ValueError('Correct integrity failures before asking a model')
    pby={p['passage_id']:p['text'] for p in mapping['passages']}
    entries=[];contexts={};excluded=[]
    for flag in q['open_flags']:
        pid=flag['passage_id']
        start=(flag['detail'] or {}).get('span_start')
        source=pby[pid]
        offset=max(0,start-200) if isinstance(start,int) else 0
        context=source[offset:offset+max_chars]
        entries.append({k:flag.get(k) for k in ('signal_id','passage_id','kind','severity','value','role','detail')})
        trial=dict(contexts,**{pid:context})
        if len(json_bytes({'flags':entries,'passage_contexts':trial}))>max_total_chars:
            excluded.append(entries.pop()['signal_id'])
        else:contexts[pid]=context
    terms=[{'term_id':t.get('term_id'),'family':t.get('family'),'rate_value':t.get('rate_value'),
            'tiers':[{'sequence':z.get('sequence'),'rate_value':z.get('rate_value')} for z in (t.get('tiers') or [])]}
           for t in extraction.get('royalty_terms',[]) if isinstance(t,dict)]
    payments=[{'payment_id':p.get('payment_id'),'kind':p.get('kind'),'amount_value':p.get('amount_value')}
              for p in extraction.get('other_payments',[]) if isinstance(p,dict)]
    pkt={'schema':'m12-correction.1','document_id':mapping['document_id'],
      'source_text_sha256':mapping['text_sha256'],'extraction_sha256':sha256(json_bytes(extraction)),
      'manifest_sha256':q['manifest_sha256'],'previous_resolutions':list(resolutions or []),
      'open_flags':entries,'passage_contexts':contexts,'unpresented_open_signal_ids':excluded,
      'all_open_signal_count':len(q['open_flags']),'correction_ready':not excluded,
      'existing_terms':terms,'existing_payments':payments,'maximum_calls_per_document':1,
      'instruction':'Add missing evidence-linked economic records or provide source-checkable typed explanations. Never close with a generic issue. Preserve REDACTED null values; retain original attempt.'}
    pkt['task_sha256']=sha256(json_bytes(pkt))
    return pkt


def apply_correction_response(mapping,extraction,packet,response):
    """Append-only corrections; every item is validated against immutable task."""
    import copy
    from .m2_schema_check import validate_shape
    expected=build_correction_packet(mapping,extraction,resolutions=packet.get('previous_resolutions'))
    if not expected['correction_ready']:raise ValueError('Source flags exceed one-call correction budget')
    if any(packet.get(k)!=expected.get(k) for k in ('task_sha256','document_id','source_text_sha256','extraction_sha256','manifest_sha256')):
        raise ValueError('Correction packet changed or belongs to another extraction')
    if response.get('schema')!='m12-correction-response.1' or response.get('task_sha256')!=packet['task_sha256']:
        raise ValueError('Correction response is not bound to issued packet')
    available={s['signal_id'] for s in expected['open_flags']}
    res=response.get('resolutions') or []
    if not any(response.get(k) for k in ('resolutions','new_evidence','new_terms','new_tiers','new_payments','new_adjustments')):
        raise ValueError('Empty correction response cannot be accepted')
    if len({r.get('signal_id') for r in res if isinstance(r,dict)})!=len(res) or any(
            not isinstance(r,dict) or r.get('signal_id') not in available for r in res):
        raise ValueError('Duplicate, malformed or unissued correction resolution')
    out=copy.deepcopy(extraction)
    known_evidence={e.get('evidence_id') for e in out.get('evidence',[])}
    source={p['passage_id']:p['text'] for p in mapping['passages']}
    for ev in response.get('new_evidence') or []:
        if not isinstance(ev,dict) or ev.get('evidence_id') in known_evidence or ev.get('passage_id') not in source or \
           not isinstance(ev.get('quote'),str) or not ev['quote'] or ev['quote'] not in source[ev['passage_id']]:
            raise ValueError('Invalid, repeated or source-mismatched evidence')
        known_evidence.add(ev['evidence_id']);out['evidence'].append(ev)
    for dest,field,ident in [('royalty_terms','new_terms','term_id'),('other_payments','new_payments','payment_id')]:
        known={r.get(ident) for r in out.get(dest,[])}
        for rec in response.get(field) or []:
            if not isinstance(rec,dict) or not rec.get(ident) or rec[ident] in known:
                raise ValueError('Correction cannot overwrite or duplicate an existing economic record')
            known.add(rec[ident]);out[dest].append(rec)
    terms={t['term_id']:t for t in out.get('royalty_terms',[])}
    for row in response.get('new_tiers') or []:
        t=terms.get(row.get('term_id'));z=row.get('tier')
        if not t or not isinstance(z,dict) or any(x.get('sequence')==z.get('sequence') for x in t.get('tiers',[])):
            raise ValueError('Invalid or overlapping tier correction')
        t['tiers'].append(z)
    for row in response.get('new_adjustments') or []:
        t=terms.get(row.get('term_id'));a=row.get('adjustment')
        if not t or not isinstance(a,dict):raise ValueError('Unknown adjustment target')
        t['adjustments'].append(a)
    problems=validate_shape(out)
    if problems:raise ValueError('Correction produced invalid extraction: '+str(problems[:4]))
    combined=list(packet.get('previous_resolutions') or [])+res
    result=reconcile_with_proposals(mapping,out,combined)
    return {'schema':'m12-correction-applied.1','updated_extraction':out,'resolutions':combined,
        'qc':result,'prior_extraction_sha256':sha256(json_bytes(extraction)),
        'notice':'Create a new immutable attempt; do not overwrite the original.'}
