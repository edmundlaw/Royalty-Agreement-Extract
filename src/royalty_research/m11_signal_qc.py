"""M11 typed, source-issued QC prototype.

Design principle: evidence flags are issued independently of the reader's answers.
A flag is closed only by a source-cited structured record or a *typed* explanation
whose reason and target can be checked. Open issues never close a flag.

This is an evidence accounting engine, not a guarantee of contractual recall.
Old M6/M7/M9/M10 heuristic gates are intentionally NOT imported here.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from .storage import stable_id, sha256, json_bytes

SCHEMA='m11-source-flags.1'
REVISION='m11.0-typed-evidence-closures'
_PERCENT=re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b)',re.I)
_MONEY=re.compile(r'(?<!\w)(?:US\s*)?\$\s*([\d,]+(?:\.\d+)?)|\bUSD\s*([\d,]+(?:\.\d+)?)\b',re.I)
_REDACT=re.compile(r'\[\s*(?:\*+|REDACTED|OMITTED)\s*\]|\b(?:\*{3,})\b|[█■]{2,}',re.I)
_RATE_WORD=re.compile(r'\b((?:(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|one[- ]half|two\s+and\s+one[- ]half))\s+percent\b',re.I)
_WORDS={**{n:Decimal(i) for i,n in enumerate(('zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen'))},**dict(zip(('twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety'),(20,30,40,50,60,70,80,90)))}
_ROYALTY=re.compile(r'royalt(?:y|ies)|(?:net|gross)\s+sales|earned\s+royalt|running\s+fee|non[- ]?royalt(?:y|ies)\s+sublicen',re.I)
_SUB_PAY=re.compile(r'sublicen[sc](?:e|ing)\s+(?:fees?|income|receipts|revenues?|consideration|share)|non[- ]?royalt(?:y|ies)\s+sublicen[sc]e\s+income',re.I)
_ECON=re.compile(r'royalt(?:y|ies)|sublicen[sc](?:e|ing)|licen[sc]e\s+fees?|net\s+sales|revenue\s+shar(?:e|ing)|milestone|guaranteed\s+minimum|upfront|up[- ]front|maintenance\s+fee|issue\s+fee|payment',re.I)
_RATE_PAY=re.compile(r'royalt(?:y|ies)|sublicen[sc](?:e|ing)\s+(?:fees?|income|share|receipts|consideration)|licen[sc]e\s+fees?|(?:on|of)\s+(?:net|gross)\s+sales|rate\s+of|shall\s+pay|payable|participation\s+fee',re.I)
_AUDIT=re.compile(r'audit|inspection|examination|shortfall|underpayment|discrepancy',re.I)
_INSURANCE=re.compile(r'insurance|insured|liability\s+coverage|policy\s+limit',re.I)
_INTEREST=re.compile(r'late[- ]?payment|interest\s+(?:on|at|of|rate)|penalt(?:y|ies)',re.I)
_OWNERSHIP=re.compile(r'equity|shareholding|ownership|shares?\s+of\s+(?:stock|capital)',re.I)
_STACK=re.compile(r'anti[- ]?stack|stacking|aggregate\s+royalt(?:y|ies)|third[- ]party\s+royalt',re.I)
_FLOOR=re.compile(r'reduc(?:e|ed|tion)|decreas(?:e|ed)|not\s+below|floor|step[- ]?down',re.I)
_STEP=re.compile(r'step[- ]?(?:up|down)|increas(?:e|es|ed)|decreas(?:e|es|ed)|reduc(?:e|es|ed)|doubl(?:e|es|ed)',re.I)
_REF=re.compile(r'\b(?:section|article|schedule|appendix|annex|exhibit)\s+[A-Za-z]?\d+(?:\.\d+)*\b',re.I)
_FEE=re.compile(r'(?P<kind>up[- ]?front|initial|issue|signing|maintenance|annual\s+licen[sc]e|licen[sc]e\s+maintenance)\s+(?:licen[sc]e\s+)?fees?|\b(?P<cap>royalt(?:y|ies)\s+(?:cap|ceiling|limit)|maximum\s+royalt(?:y|ies)|capped\s+at)|\b(?P<minimum>minimum\s+(?:(?:annual|guaranteed)\s+)?royalt(?:y|ies)|guaranteed\s+minimum\s+royalt(?:y|ies)|annual\s+minimum)|\b(?P<milestone>milestone\s+(?:payments?|fees?|consideration|amounts?)|development\s+milestones?|sales\s+milestones?|milestones?\b)',re.I)
_TABLE_HEADER=re.compile(r'\broyalt(?:y|ies)|royalty\s+rate|royalty\s+percentage|sublicen[sc](?:e|ing)|(?:net|gross)\s+sales|(?:minimum|milestones?)\s+(?:amount|payments?|royalt)|\bmilestones?\b|\bpayment\s+amount\b|guaranteed\s+minimum',re.I)
_SECTION_BREAK=re.compile(r'^\s*(?:article|section|schedule)\s+[A-Z0-9]+\s*[:.\-]',re.I)


def _numeric(s):
    if isinstance(s,bool) or s is None:return None
    try:
        v=Decimal(str(s).strip().replace(',','').replace('US$','').replace('$','').strip())
        return v if v.is_finite() else None
    except (InvalidOperation,ValueError):return None


def _word_rate(text):
    raw=re.sub(r'\s+',' ',text.lower().replace('-',' ')).strip()
    if raw=='two and one half':return Decimal('2.5')
    if raw=='one half':return Decimal('0.5')
    if raw in _WORDS:return _WORDS[raw]
    parts=raw.split(' ')
    if len(parts)==2 and parts[0] in _WORDS and parts[1] in _WORDS and _WORDS[parts[0]]>=20 and _WORDS[parts[1]]<10:
        return _WORDS[parts[0]]+_WORDS[parts[1]]
    return None


def _rates(s):
    hits=[]
    for m in _PERCENT.finditer(s): hits.append((m.start(),m.end(),_numeric(m.group(1)),m.group(0)))
    for m in _RATE_WORD.finditer(s):
        if not any(a<=m.start()<b for a,b,_,_ in hits):
            v=_word_rate(m.group(1))
            if v is not None:hits.append((m.start(),m.end(),v,m.group(0)))
    return sorted(hits)


def _money(s):
    return [(m.start(),m.end(),_numeric(m.group(1) or m.group(2)),m.group(0)) for m in _MONEY.finditer(s)]


def _money_role(s):
    m=_FEE.search(s)
    if not m:return None
    if m.group('cap'):return 'CAP'
    if m.group('minimum'):return 'MINIMUM_ROYALTY'
    if m.group('milestone'):return 'MILESTONE'
    word=(m.group('kind') or '').lower()
    if 'maintenance' in word:return 'MAINTENANCE_FEE'
    return 'UPFRONT_FEE'


def _table_blocks(passages):
    """Find bounded pipe-table blocks by header + lead, not seven-row lookbacks.

    A row is classified by the *table header/lead*, never by generic nearby
    'sublicensee' wording. Rows can carry numeric, redacted, or blank rate cells.
    Page numbers, page-footers and blank separators may interrupt a table.
    """
    blocks=[];active=None;gap=0;lead=[]
    for ix,p in enumerate(passages):
        s=p['text'].strip();pipe='|' in s
        if not pipe:
            if active is not None:
                if not s or re.fullmatch(r'(?:page\s*)?\d+(?:\s+of\s+\d+)?',s,re.I):
                    gap+=1
                    if gap<=3:continue
                blocks.append(active);active=None;gap=0
            lead.append(s[:400]);lead=lead[-12:]
            continue
        cells=[c.strip() for c in s.split('|')]
        is_header=bool(_TABLE_HEADER.search(s)) and (
            bool(re.search(r'\b(?:rate|percentage|amount|tier|royalt(?:y|ies)|minimum|milestones?)\b',s,re.I)) or
            bool(_TABLE_HEADER.search(' '.join(lead[-3:])))
        )
        if active is None:
            if is_header:
                active={'header':s,'lead':' '.join(lead[-5:]),'rows':[]}
            else:
                # An unheaded economic schedule can have a lead-in, e.g.,
                # a standalone line announcing 'the following royalty tiers'.
                context=' '.join(lead[-5:])
                if _ROYALTY.search(context) and (len(cells)>=2) and (_rates(s) or _REDACT.search(s)):
                    active={'header':'','lead':context,'rows':[]}
                else:
                    lead.append(s[:400]);lead=lead[-12:]
                    continue
        elif is_header and active['rows']:
            blocks.append(active)
            active={'header':s,'lead':' '.join(lead[-5:]),'rows':[]}
            continue
        gap=0
        if (not is_header and len(cells)>=2 and
            (_rates(s) or _money(s) or _REDACT.search(s))):
            active['rows'].append(ix)
    if active is not None:blocks.append(active)
    return [b for b in blocks if b['rows']]


def issue_signals(mapping:dict)->dict:
    passages=mapping['passages'];flagged=[];reserved=set()
    def add(kind,ix,*,value=None,role=None,detail=None,ordinal=0):
        p=passages[ix];pid=p['passage_id'];risk='HARD' if kind in {'RATE','TIER_ROW','REDACTED_ECONOMIC','MINIMUM_ROYALTY','CAP','STEP_RATE','ADJUSTMENT'} else 'WARNING'
        item={'signal_id':stable_id('SIG11',pid,kind,str(value),str(role),str(ordinal)),
              'passage_id':pid,'source_text_sha256':mapping['text_sha256'],
              'kind':kind,'severity':risk,'value':str(value) if value is not None else None,
              'role':role,'detail':detail,'excerpt':p['text'][:2000]}
        flagged.append(item)
    for block in _table_blocks(passages):
        context=(block['lead']+' '+block['header']).lower()
        role=('SUBLICENSING' if _SUB_PAY.search(context) else
              'MINIMUM_ROYALTY' if re.search(r'minimum|guarantee',context) else
              'MILESTONE' if 'milestone' in context else 'ROYALTY')
        for ix in block['rows']:
            reserved.add(ix)
            add('TIER_ROW' if role in {'ROYALTY','SUBLICENSING'} else 'PAYMENT_ROW',ix,
                role=role,detail={'rates':[str(x[2]) for x in _rates(passages[ix]['text'])],
                   'amounts':[str(x[2]) for x in _money(passages[ix]['text'])],
                   'redacted':bool(_REDACT.search(passages[ix]['text']))},ordinal=0)
    for ix,p in enumerate(passages):
        if ix in reserved:continue
        s=p['text'];rate_hits=_rates(s);money_hits=_money(s);redact=_REDACT.search(s)
        econ=bool(_ECON.search(s));money_role=_money_role(s)
        for j,(rate_start,rate_end,v,literal) in enumerate(rate_hits):
            if not (econ or _INTEREST.search(s) or _AUDIT.search(s) or _OWNERSHIP.search(s) or _INSURANCE.search(s)):continue
            role='STEP_RATE' if _STEP.search(s) and _RATE_PAY.search(s) else 'RATE'
            add(role,ix,value=v,detail={'literal':literal,'span_start':rate_start,'span_end':rate_end},ordinal=j)
        if money_role:
            for j,(amt_start,amt_end,v,literal) in enumerate(money_hits):
                add(money_role,ix,value=v,detail={'literal':literal,'span_start':amt_start,'span_end':amt_end},ordinal=j)
            if redact and not money_hits:
                add(money_role,ix,role='REDACTED',detail={'redacted':True},ordinal=0)
        elif redact and econ and not rate_hits:
            # Count separately signalled redacted obligations, not every raw
            # marker in a parenthetical `([***]%)`. Nearby duplicate markers
            # can represent one redacted rate; widely separated ones cannot.
            clusters=[]
            for marker in _REDACT.finditer(s):
                local=s[max(0,marker.start()-110):min(len(s),marker.end()+110)]
                if not _ECON.search(local):continue
                if not clusters or marker.start()-clusters[-1][-1].end()>20:
                    clusters.append([marker])
                else:clusters[-1].append(marker)
            for ordinal,group in enumerate(clusters):
                add('REDACTED_ECONOMIC',ix,role='UNCLASSIFIED',
                    detail={'redacted':True,'offset_start':group[0].start(),
                            'offset_end':group[-1].end(),'marker_count':len(group)},ordinal=ordinal)

        if _STEP.search(s) and _ROYALTY.search(s) and (rate_hits or redact):
            add('ADJUSTMENT',ix,role='ADJUSTMENT',detail={'rates':[str(x[2]) for x in rate_hits]},ordinal=0)
    payload={'schema':SCHEMA,'revision':REVISION,'document_id':mapping['document_id'],
        'source_text_sha256':mapping['text_sha256'],'signals':flagged}
    payload['manifest_sha256']=sha256(json_bytes(payload))
    return payload


def _record_index(extraction):
    evidence={x.get('evidence_id'):x.get('passage_id') for x in extraction.get('evidence',[]) if isinstance(x,dict)}
    terms={x.get('term_id'):x for x in extraction.get('royalty_terms',[]) if isinstance(x,dict)}
    payments={x.get('payment_id'):x for x in extraction.get('other_payments',[]) if isinstance(x,dict)}
    def cites(record,pid,fields=('evidence_ids',)):
        return any(evidence.get(eid)==pid for f in fields for eid in (record.get(f) or []))
    def associated(term,pid):
        return cites(term,pid,('evidence_ids','rate_evidence_ids','base_evidence_ids')) or any(cites(z,pid) for z in (term.get('tiers') or [])+(term.get('conditions') or [])+(term.get('adjustments') or []) if isinstance(z,dict))
    return terms,payments,cites,associated


def _match_signal(signal,record_type,record_id,sequence,extraction):
    terms,payments,cites,associated=_record_index(extraction)
    kind=signal['kind']; pid=signal['passage_id']; val=_numeric(signal['value']); red=bool((signal['detail'] or {}).get('redacted')) or signal.get('role')=='REDACTED'
    if record_type=='TIER':
        t=terms.get(record_id)
        if t is None:return False
        matches=[z for z in (t.get('tiers') or []) if isinstance(z,dict) and z.get('sequence')==sequence]
        if len(matches)!=1:return False
        z=matches[0]
        if not cites(z,pid):return False
        if kind not in {'TIER_ROW','RATE','STEP_RATE','REDACTED_ECONOMIC'}:return False
        if kind=='TIER_ROW':
            rates={_numeric(v) for v in (signal['detail'] or {}).get('rates',[])}
            if rates and _numeric(z.get('rate_value')) not in rates:return False
            # Numeric band limits cannot disappear from a claimed tier.
            amount_bands={_numeric(v) for v in (signal['detail'] or {}).get('amounts',[])}
            tier_bounds={_numeric(z.get('lower')),_numeric(z.get('upper'))}
            if amount_bands and not amount_bands.issubset(tier_bounds):return False
        elif val is not None and val!=_numeric(z.get('rate_value')):return False
        if red and (z.get('rate_value') is not None or z.get('rate_unit')!='REDACTED'):return False
        if signal.get('role')=='SUBLICENSING' and t.get('family')!='SUBLICENSING_RECEIPTS':return False
        if signal.get('role')=='ROYALTY' and t.get('family')=='SUBLICENSING_RECEIPTS':return False
        return True
    if record_type=='ROYALTY_TERM':
        t=terms.get(record_id)
        if t is None or not associated(t,pid):return False
        if kind=='TIER_ROW' and t.get('structure')=='TIERED':return False
        if kind in {'RATE','STEP_RATE','TIER_ROW'}:
            if kind=='TIER_ROW':
                rates={_numeric(v) for v in (signal['detail'] or {}).get('rates',[])}
                if rates and _numeric(t.get('rate_value')) not in rates:return False
            elif val is not None and _numeric(t.get('rate_value'))!=val:return False
        if red and (t.get('disclosure_status')!='REDACTED' or t.get('rate_value') is not None):return False
        if signal.get('role')=='SUBLICENSING' and t.get('family')!='SUBLICENSING_RECEIPTS':return False
        return kind in {'RATE','STEP_RATE','TIER_ROW','REDACTED_ECONOMIC'}
    if record_type=='PAYMENT':
        q=payments.get(record_id)
        if q is None or not cites(q,pid):return False
        kind_match={'CAP':{'CAP'},'MINIMUM_ROYALTY':{'MINIMUM_ROYALTY','GUARANTEE'},
                    'UPFRONT_FEE':{'UPFRONT'},'MAINTENANCE_FEE':{'OTHER','SERVICE'},'MILESTONE':{'MILESTONE'},
                    'PAYMENT_ROW':{'MILESTONE','MINIMUM_ROYALTY','GUARANTEE','OTHER'}}
        if kind not in kind_match or q.get('kind') not in kind_match[kind]:return False
        if val is not None and _numeric(q.get('amount_value'))!=val:
            # Every distinct milestone or licence payment is a separate
            # economic observation. A mention in a free-text condition does
            # not substitute for a second structured amount.
            return False
        if red and (q.get('amount_value') is not None or q.get('disclosure_status')!='REDACTED'):return False
        return True
    if record_type=='ADJUSTMENT':
        t=terms.get(record_id)
        if t is None:return False
        adjustments=[a for a in (t.get('adjustments') or [])+(t.get('conditions') or []) if isinstance(a,dict) and cites(a,pid)]
        if not adjustments:return False
        if kind not in {'ADJUSTMENT','STEP_RATE','RATE','CAP','MINIMUM_ROYALTY'}:return False
        if val is not None:
            content=' '.join(str(a.get('description') or a.get('text') or '') for a in adjustments)
            if not any(rate_val==val for _,_,rate_val,_ in _rates(content)) and not any(amt_val==val for _,_,amt_val,_ in _money(content)):
                return False
        return True
    return False


def _typed_explanation(signal,reason,target_id,extraction):
    s=signal['excerpt']; v=_numeric(signal['value']);kind=signal['kind']
    terms,payments,cites,associated=_record_index(extraction)
    span=signal.get('detail') or {}
    start=span.get('span_start')
    end=span.get('span_end')
    if type(start) is int and type(end) is int and 0<=start<end<=len(s):
        prefix=s[max(0,start-115):start];suffix=s[end:min(len(s),end+70)]
    else:
        prefix=s[:115];suffix=s[-70:]
    payable=bool(_RATE_PAY.search(s) and (_ROYALTY.search(s) or _SUB_PAY.search(s)))
    if reason=='AUDIT_THRESHOLD':
        return bool((_AUDIT.search(prefix) or (_AUDIT.search(suffix) and re.search(r'differ|discrepanc|underpay|variance|error',prefix,re.I)))
               and not re.search(r'(?:\d+(?:\.\d+)?\s*%|\w+\s+percent)\s+(?:on|of)\s+(?:net|gross)\s+sales',s[start:end]+suffix,re.I))
    if reason=='INSURANCE_LIMIT':return bool(_INSURANCE.search(prefix) and not payable)
    if reason=='NON_ROYALTY_INTEREST':return bool(_INTEREST.search(prefix) and not re.search(r'\bof\s+net\s+sales',prefix+s[start:end]+suffix,re.I))
    if reason=='OWNERSHIP_PERCENT':return bool(_OWNERSHIP.search(prefix) and not (payable and (v is not None)))
    if reason in {'STACKING_THRESHOLD','REDUCTION_FLOOR'}:
        t=terms.get(target_id)
        if t is None or not associated(t,signal['passage_id']):return False
        if reason=='STACKING_THRESHOLD' and not _STACK.search(prefix):return False
        if reason=='REDUCTION_FLOOR' and not _FLOOR.search(prefix):return False
        adjustments=[a for a in (t.get('adjustments') or [])+(t.get('conditions') or []) if isinstance(a,dict) and cites(a,signal['passage_id'])]
        return any(v==value for a in adjustments for _,_,value,_ in _rates(str(a.get('description') or a.get('text') or '')))
    if reason=='INSTALLMENT_COMPONENT':
        pay=payments.get(target_id)
        if not pay or not cites(pay,signal['passage_id']):return False
        annual=_numeric(pay.get('amount_value'))
        if not (kind=='MINIMUM_ROYALTY' and v is not None and annual is not None and annual==v*12):return False
        if not (re.search(r'\bmonth(?:ly)?\b|per\s+month',s,re.I) and
                re.search(r'\bannual(?:ly)?\b|per\s+year|\ba\s+year\b',s,re.I)):return False
        return any(v==amount for field in ('basis','condition')
                   for _,_,amount,_ in _money(str(pay.get(field) or '')))
    if reason=='REFERENCE_ONLY':
        t=terms.get(target_id)
        return bool(t and associated(t,signal['passage_id']) and _REF.search(s) and
             not (re.search(r'\bshall\s+pay|\bwill\s+pay|\bis\s+payable',s,re.I) and (v is not None or _REDACT.search(s))))
    return False


def reconcile_signals(mapping,extraction,resolutions=None,*,manifest=None):
    """Return transparent hard/warning/open status; no waivers through open issues."""
    issued=issue_signals(mapping)
    errors=[];warnings=[];closed=[];open_flags=[];seen={}
    if manifest is not None and manifest!=issued:
        return {'schema':'m11-qc.1','status':'FAIL_INTEGRITY','errors':[{'code':'M11_STALE_SIGNAL_MANIFEST'}],
            'warnings':[],'closed':[],'open_flags':[],'manifest_sha256':issued['manifest_sha256']}
    if extraction.get('document_id')!=mapping['document_id'] or extraction.get('source_text_sha256')!=mapping['text_sha256']:
        errors.append({'code':'M11_EXTRACTION_SOURCE_MISMATCH'})
    ids={x['signal_id']:x for x in issued['signals']}
    for item in resolutions or []:
        ident=item.get('signal_id') if isinstance(item,dict) else None
        if ident not in ids:
            errors.append({'code':'M11_UNISSUED_SIGNAL','ref':ident});continue
        if ident in seen:
            errors.append({'code':'M11_DUPLICATE_RESOLUTION','ref':ident});continue
        seen[ident]=item
    for signal in issued['signals']:
        ident=signal['signal_id']; res=seen.get(ident)
        if res is None:
            open_flags.append(signal);continue
        resolution=res.get('resolution')
        ok=False
        if resolution=='LINKED_RECORD':
            ok=_match_signal(signal,res.get('record_type'),res.get('record_id'),res.get('tier_sequence'),extraction)
        elif resolution=='TYPED_EXPLANATION':
            ok=_typed_explanation(signal,res.get('reason'),res.get('target_id'),extraction)
        if ok:closed.append({'signal_id':ident,'resolution':resolution,'target':res.get('record_id') or res.get('target_id'),
                             'reason':res.get('reason')})
        else:
            errors.append({'code':'M11_INVALID_CLOSURE','ref':ident,'kind':signal['kind'],
                           'message':'Source flag not closed by a verified structured record or typed explanation'})
            open_flags.append(signal)
    # Identical numeric percentages in one paragraph may have different roles
    # (e.g. 3% royalty and 3% audit threshold). One rate record cannot silently
    # close two source-issued occurrences simply because both cite that paragraph.
    numeric_use={}
    for signal in issued['signals']:
        if signal['kind'] not in {'RATE','STEP_RATE'} or signal.get('value') is None:continue
        answer=seen.get(signal['signal_id'])
        if not isinstance(answer,dict) or answer.get('resolution')!='LINKED_RECORD' or answer.get('record_type') not in {'TIER','ROYALTY_TERM'}:continue
        if signal['signal_id'] not in {x['signal_id'] for x in closed}:continue
        key=(signal['passage_id'],signal['value'],answer.get('record_type'),answer.get('record_id'),answer.get('tier_sequence'))
        numeric_use.setdefault(key,[]).append(signal['signal_id'])
    for key,signal_ids in numeric_use.items():
        if len(signal_ids)>1:
            for ident in signal_ids:
                errors.append({'code':'M11_SAME_NUMERIC_RECORD_REUSED','ref':ident,
                               'message':'One source-cited rate record cannot silently account for two identical percentage occurrences with potentially different roles'})
                if not any(x['signal_id']==ident for x in open_flags):open_flags.append(ids[ident])
                closed=[x for x in closed if x['signal_id']!=ident]
    # One redacted obligation row cannot be 'covered' by the same single
    # redacted record/tier as another independent source row. A model that
    # copies one rate record onto every table row must not get a clean pass.
    distinct_redacted={}
    for signal in issued['signals']:
        if signal['kind'] not in {'TIER_ROW','PAYMENT_ROW','REDACTED_ECONOMIC'}:
            continue
        if not (signal['kind']=='REDACTED_ECONOMIC' or (signal.get('detail') or {}).get('redacted')):
            continue
        ident=signal['signal_id'];answer=seen.get(ident)
        if not isinstance(answer,dict) or answer.get('resolution')!='LINKED_RECORD' or ident not in {x['signal_id'] for x in closed}:
            continue
        key=(answer.get('record_type'),answer.get('record_id'),answer.get('tier_sequence'))
        distinct_redacted.setdefault(key,[]).append(ident)
    for key,signal_ids in distinct_redacted.items():
        if len(signal_ids)>1:
            for ident in signal_ids:
                errors.append({'code':'M11_REDACTED_RECORD_REUSED','ref':ident,'target':str(key),
                    'message':'Multiple redacted source obligations cannot share one record/tier without independent proof of duplicate disclosure'})
                if not any(x['signal_id']==ident for x in open_flags):
                    open_flags.append(ids[ident])
                closed=[x for x in closed if x['signal_id']!=ident]
    hard=[x for x in open_flags if x['severity']=='HARD']
    soft=[x for x in open_flags if x['severity']=='WARNING']
    for x in hard:errors.append({'code':'M11_HARD_FLAG_OPEN','ref':x['signal_id'],'kind':x['kind']})
    for x in soft:warnings.append({'code':'M11_SUPPORTING_ECONOMICS_OPEN','ref':x['signal_id'],'kind':x['kind']})
    status='FAIL_INTEGRITY' if any(x['code'] in {'M11_UNISSUED_SIGNAL','M11_DUPLICATE_RESOLUTION','M11_EXTRACTION_SOURCE_MISMATCH','M11_STALE_SIGNAL_MANIFEST'} for x in errors) else (
        'INCOMPLETE_CORE_ECONOMICS' if any(x['code']=='M11_HARD_FLAG_OPEN' or x['code']=='M11_INVALID_CLOSURE' for x in errors) else
        'INCOMPLETE_SUPPORTING_ECONOMICS' if soft else 'PASS_SOURCE_FLAGS_ONLY')
    return {'schema':'m11-qc.1','revision':REVISION,'document_id':mapping['document_id'],
            'source_text_sha256':mapping['text_sha256'],'manifest_sha256':issued['manifest_sha256'],
            'status':status,'source_signal_count':len(issued['signals']), 'closed_count':len(closed),
            'hard_open':len(hard),'warning_open':len(soft),'closed':closed,'open_flags':open_flags,
            'errors':errors,'warnings':warnings,
            'notice':'Source flag reconciliation is not proof of full-contract recall or semantic correctness; open issues do not waive any flag.'}


def build_correction_packet(mapping, extraction, *,resolutions=None,max_chars=1500,max_total_chars=34000):
    """Prepare ONE compact source-bound correction task, without model calls.

    Passage text is sent once even when it holds many rate/fee flags. If the
    bounded task cannot contain every flag, no partial silent model call is
    authorized: the package lists all excluded flag IDs and is NOT_READY.
    """
    resolutions=list(resolutions) if resolutions is not None else propose_verified_closures(mapping,extraction)
    report=reconcile_signals(mapping,extraction,resolutions)
    if report['status']=='FAIL_INTEGRITY':raise ValueError('Correct source bindings before model correction')
    p_by_id={p['passage_id']:p for p in mapping['passages']}
    open_flags=[];contexts={};excluded=[]
    for flag in report['open_flags']:
        pid=flag['passage_id']
        item={'signal_id':flag['signal_id'],'passage_id':pid,'kind':flag['kind'],
              'severity':flag['severity'],'value':flag['value'],
              'role':flag['role'],'detail':flag['detail']}
        source=p_by_id[pid]['text']
        if pid not in contexts:
            literal=str((flag['detail'] or {}).get('literal') or '')
            offset=source.find(literal) if literal else -1
            anchor=max(0,offset-max_chars//3) if offset>=0 else 0
            contexts[pid]=source[anchor:anchor+max_chars]
        trial=open_flags+[item]
        if len(json_bytes({'flags':trial,'passage_contexts':contexts}))>max_total_chars:
            excluded.append(flag['signal_id'])
            # The flag remains OPEN in the QC report, not assumed irrelevant.
        else:
            open_flags.append(item)
    terms=[{'id':t.get('term_id'),'family':t.get('family'),'rate_value':t.get('rate_value'),
            'tiers':[{'sequence':z.get('sequence'),'rate_value':z.get('rate_value')} for z in t.get('tiers',[])]}
            for t in extraction.get('royalty_terms',[]) if isinstance(t,dict)]
    payments=[{'id':p.get('payment_id'),'kind':p.get('kind'),'value':p.get('amount_value')}
              for p in extraction.get('other_payments',[]) if isinstance(p,dict)]
    pkt={'schema':'m11-correction.1','document_id':mapping['document_id'],
       'source_text_sha256':mapping['text_sha256'], 'extraction_sha256':sha256(json_bytes(extraction)),
       'manifest_sha256':report['manifest_sha256'], 'previous_resolutions':resolutions,
       'open_flags':open_flags,'passage_contexts':{p:contexts[p] for p in {x['passage_id'] for x in open_flags}},
       'unpresented_open_signal_ids':excluded,
       'correction_ready':not excluded,
       'all_open_signal_count':len(report['open_flags']),
       'existing_terms':terms,'existing_payments':payments,
       'instruction':'One targeted response: use LINKED_RECORD or Python-checkable TYPED_EXPLANATION. Add cited records for missing economics; redacted numeric value must remain null with REDACTED status. An open issue cannot waive a flag.',
       'maximum_calls_per_document':1}
    pkt['task_sha256']=sha256(json_bytes(pkt))
    return pkt



def propose_verified_closures(mapping,extraction):
    """Generate exact evidence-record matches, never issue/ambiguity waivers.

    When more than one candidate record matches, leave the flag open for the
    targeted reviewer. This is bookkeeping, not independent interpretation.
    """
    terms=[x for x in extraction.get('royalty_terms',[]) if isinstance(x,dict)]
    payments=[x for x in extraction.get('other_payments',[]) if isinstance(x,dict)]
    proposals=[]
    for signal in issue_signals(mapping)['signals']:
        candidates=[]
        for t in terms:
            for typ,seq in [('ROYALTY_TERM',None),('ADJUSTMENT',None)]:
                if _match_signal(signal,typ,t.get('term_id'),seq,extraction):
                    candidates.append({'signal_id':signal['signal_id'],'resolution':'LINKED_RECORD','record_type':typ,'record_id':t['term_id']})
            for z in t.get('tiers',[]):
                if isinstance(z,dict) and _match_signal(signal,'TIER',t.get('term_id'),z.get('sequence'),extraction):
                    candidates.append({'signal_id':signal['signal_id'],'resolution':'LINKED_RECORD','record_type':'TIER',
                                       'record_id':t['term_id'],'tier_sequence':z['sequence']})
        for p in payments:
            if _match_signal(signal,'PAYMENT',p.get('payment_id'),None,extraction):
                candidates.append({'signal_id':signal['signal_id'],'resolution':'LINKED_RECORD','record_type':'PAYMENT','record_id':p['payment_id']})
        if len(candidates)==1:proposals.append(candidates[0])
        elif not candidates:
            # Narrow, source-verifiable non-economic explanations. An issue
            # cannot appear here and cannot be used as a waiver.
            matches=[reason for reason in ('AUDIT_THRESHOLD','INSURANCE_LIMIT','NON_ROYALTY_INTEREST','OWNERSHIP_PERCENT')
                     if _typed_explanation(signal,reason,None,extraction)]
            installment=[p.get('payment_id') for p in payments
                         if _typed_explanation(signal,'INSTALLMENT_COMPONENT',p.get('payment_id'),extraction)]
            if len(matches)==1 and not installment:
                proposals.append({'signal_id':signal['signal_id'],'resolution':'TYPED_EXPLANATION','reason':matches[0]})
            elif len(installment)==1 and not matches:
                proposals.append({'signal_id':signal['signal_id'],'resolution':'TYPED_EXPLANATION',
                                  'reason':'INSTALLMENT_COMPONENT','target_id':installment[0]})
    return proposals


def reconcile_with_proposals(mapping,extraction,resolutions=None):
    """Use explicit resolutions first, then safe unique proposals for the rest."""
    explicit={x.get('signal_id'):x for x in (resolutions or []) if isinstance(x,dict)}
    # Invalid/duplicate explicit resolutions are never masked by proposals.
    originals=list(resolutions or [])
    auto=[x for x in propose_verified_closures(mapping,extraction) if x['signal_id'] not in explicit]
    report=reconcile_signals(mapping,extraction,originals+auto)
    report['auto_proposed']=len(auto)
    report['explicit_resolutions']=len(originals)
    return report


def apply_correction_response(mapping, extraction, packet, response):
    """Apply a source-bound, additive, one-call correction; never mutate input.

    The model can *add* evidence, terms, payments, tiers and adjustments only.
    It may not overwrite existing facts, prior attempts or source passages.
    Every response resolution must refer to an issued open signal.
    """
    import copy
    from .m2_schema_check import validate_shape
    expected=build_correction_packet(mapping,extraction,
        resolutions=packet.get('previous_resolutions'))
    if not expected['correction_ready']:
        raise ValueError('Correction cannot safely fit every source flag in one call')
    if any(packet.get(k)!=expected[k] for k in ('task_sha256','document_id','source_text_sha256','extraction_sha256','manifest_sha256')):
        raise ValueError('M11 correction task does not match source/extraction or prior resolutions')
    if response.get('schema')!='m11-correction-response.1' or response.get('task_sha256')!=packet['task_sha256']:
        raise ValueError('M11 correction response is not bound to the exact issued task')
    active={x['signal_id'] for x in expected['open_flags']}
    resolutions=response.get('resolutions') or []
    if not any(response.get(x) for x in ('resolutions','new_terms','new_payments','new_evidence','new_tiers','new_adjustments')):
        raise ValueError('Empty correction is not a new review attempt')
    if any(not isinstance(x,dict) or x.get('signal_id') not in active for x in resolutions):
        raise ValueError('Correction may only address source-issued open flags')
    if len({x['signal_id'] for x in resolutions})!=len(resolutions):
        raise ValueError('Duplicate correction resolution')
    result=copy.deepcopy(extraction)
    by_id={x['evidence_id'] for x in result.get('evidence',[])}
    passages={p['passage_id']:p['text'] for p in mapping['passages']}
    for ev in response.get('new_evidence') or []:
        if not isinstance(ev,dict) or ev.get('evidence_id') in by_id or ev.get('passage_id') not in passages:
            raise ValueError('Invalid new evidence or duplicate evidence ID')
        if ev.get('quote') not in passages[ev['passage_id']]:
            raise ValueError('New evidence quotation does not exist in source')
        by_id.add(ev['evidence_id'])
        result['evidence'].append(ev)
    for collection,kind,key in [('royalty_terms','new_terms','term_id'),('other_payments','new_payments','payment_id')]:
        existing={x[key] for x in result.get(collection,[])}
        for rec in response.get(kind) or []:
            if not isinstance(rec,dict) or rec.get(key) in existing or not rec.get(key):
                raise ValueError('Correction record missing or duplicates existing ID')
            existing.add(rec[key]);result[collection].append(rec)
    terms={t['term_id']:t for t in result['royalty_terms']}
    for item in response.get('new_tiers') or []:
        t=terms.get(item.get('term_id'))
        z=item.get('tier')
        if not t or not isinstance(z,dict) or any(x.get('sequence')==z.get('sequence') for x in t['tiers']):
            raise ValueError('Correction tier target/sequence invalid')
        t['tiers'].append(z)
    for item in response.get('new_adjustments') or []:
        t=terms.get(item.get('term_id'));a=item.get('adjustment')
        if not t or not isinstance(a,dict):raise ValueError('Correction adjustment target invalid')
        t['adjustments'].append(a)
    problems=validate_shape(result)
    if problems:raise ValueError('Correction produced invalid extraction shape: '+str(problems[:5]))
    combined=list(packet.get('previous_resolutions') or [])+resolutions
    report=reconcile_with_proposals(mapping,result,combined)
    # Even a syntactically valid correction may leave flags open; never claim
    # a successful extraction merely because a model returned a JSON object.
    return {'schema':'m11-correction-applied.1','updated_extraction':result,
            'resolutions':combined,'qc':report,'source_text_sha256':mapping['text_sha256'],
            'prior_extraction_sha256':sha256(json_bytes(extraction)),
            'notice':'A new immutable extraction attempt must be saved; old attempts are never overwritten.'}
