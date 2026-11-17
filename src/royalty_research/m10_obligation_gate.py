"""M10 source-led contractual economics checks.

This is an independent, deterministic *signal* checker over the complete passage
map. It cannot certify legal interpretation or recall. It does not consult the
model's passage/occurrence classifications or use model open issues as waivers.

Three source signals are deliberately different:
  - table-band rates/redacted rates, whatever column contains the rate;
  - expressly payable rates and changes in prose (including spelled percentages);
  - clearly labelled upfront/guaranteed-minimum monetary obligations.

No issuer-specific text, company names, amounts, or exact known heading strings
are hard-coded into these rules.
"""
from __future__ import annotations

import re
from decimal import Decimal
from .m6_source_risk import number, _linked_amount, _linked_percent

# Ordinary '%' has a non-word boundary, so use a separate pattern.
_RATE = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(?:%|percent\b|per\s+cent\b)', re.I)
_WORD_RATE = re.compile(r'\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|twenty[- ]five|thirty|forty|fifty|sixty|seventy|eighty|ninety)\s*(?:percent|per\s+cent)\b',re.I)
_WORD_NUMBER={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'twenty-five':25,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
_REDACT = re.compile(r'\[(?:\*{2,}|REDACTED)\]|\*{3,}',re.I)
_MONEY = re.compile(r'(?:US\s*)?\$\s*([0-9][0-9,]*(?:\.\d+)?)',re.I)
_ECON = re.compile(r'royalt(?:y|ies)|sublicen[sc](?:e|ing|ee)|licen[sc](?:e|ing)\s+(?:fees?|payments?)|net\s+sales|revenue\s+share|percentage\s+of\s+(?:receipts|sales)',re.I)
_TABLE_HEADER = re.compile(r'royalt(?:y|ies)|royalty\s+rate|(?:sublicen[sc](?:e|ing))\s+(?:fees?|share|income)|(?:net\s+sales|sales\s+band).{0,75}(?:rate|percentage)|(?:rate|percentage).{0,75}net\s+sales',re.I)
_PAYABLE = re.compile(r'\b(?:shall|will|must|agrees?\s+to|is\s+required\s+to)\s+(?:\w+\s+){0,8}?(?:pay|remit|share)|\broyalt(?:y|ies)\s+(?:of|at)|\b(?:rate|royalt(?:y|ies))\s+(?:increas|decreas|reduc|step)', re.I)
_NON_RATE = re.compile(r'\b(?:late\s+payment\s+interest|audit\s+shortfall|inspection\s+cost|underpayment\s+threshold|interest\s+rate)\b',re.I)
_RATE_ADJUST = re.compile(r'\b(?:royalt(?:y|ies)|royalty rate|licen[sc]e fee).{0,160}?(?:reduc(?:e|es|ed|tion)|decreas(?:e|es|ed)|increas(?:e|es|ed)|step[- ]?(?:up|down)|adjust(?:ed|ment))\b|\b(?:reduc(?:e|es|ed)|decreas(?:e|es|ed)|increas(?:e|es|ed))\b.{0,160}?\broyalt(?:y|ies)\b',re.I)
_INDIRECT = re.compile(r'\b(?:all\s+)?(?:running[- ]?)?royalt(?:y|ies)|\bannual\s+minimum\b|\bmilestone\s+payments?\b|\blump[- ]sum\s+(?:settlement\s+)?payment\b',re.I)
_SPECIAL = re.compile(r'\b(?:upfront\s+(?:licen[sc]e\s+)?fee|up[- ]front\s+payment|initial\s+licen[sc]e\s+fee|guaranteed\s+minimum\s+royalt(?:y|ies)|minimum\s+(?:annual\s+)?royalt(?:y|ies)|annual\s+minimum|minimum\s+guarantee)\b',re.I)


def _percentage_values(s):
    values={Decimal(m.group(1)) for m in _RATE.finditer(s)}
    for m in _WORD_RATE.finditer(s):
        v=_WORD_NUMBER.get(m.group(1).lower().replace(' ','-'))
        if v is not None: values.add(Decimal(v))
    return values


def _cited_objects(extraction):
    evidence={e.get('evidence_id'):e.get('passage_id') for e in extraction.get('evidence',[]) if isinstance(e,dict)}
    def cites(record,pid,keys=('evidence_ids',)):
        return any(evidence.get(eid)==pid for k in keys for eid in (record.get(k) or []))
    return evidence,cites


def _term_record_values(t,pid,cites):
    """One passage is not evidence of another; inspect only source-linked attributes."""
    values=set()
    if cites(t,pid,('rate_evidence_ids',)):
        v=number(t.get('rate_value'))
        if v is not None:values.add(v)
    for z in t.get('tiers') or []:
        if isinstance(z,dict) and cites(z,pid):
            v=number(z.get('rate_value'))
            if v is not None:values.add(v)
    for a in (t.get('conditions') or [])+(t.get('adjustments') or []):
        if isinstance(a,dict) and cites(a,pid):
            values |= _percentage_values(str(a.get('text') or a.get('description') or ''))
    return values


def _table_rows(passages):
    """Rate-bearing columns or enumerated tier items with a nearby economic lead.

    Work at row level, not at paragraph-block level. HTML extractors may insert
    blank rows, page headers, or unrelated enumerated subsections between table
    rows. Do not assume a percentage is in the first column.
    """
    for i,p in enumerate(passages):
        s=p['text']
        if '|' not in s or re.match(r'^\s*\d+(?:\.\d+)+\s*\|',s):
            continue  # ordinary numbered contract clause, not a table row
        cols=s.split('|',1)
        if (re.match(r'^\s*\(?[a-z]\)\s*$',cols[0],re.I) and
                _RATE_ADJUST.search(cols[1])):
            continue  # conditional rate change, not a numeric band/tier row
        if not (_RATE.search(s) or _WORD_RATE.search(s) or
                (_REDACT.search(s) and re.search(r'percent|%|royalt(?:y|ies)|rate',s,re.I))):
            continue
        previous=passages[max(0,i-7):i]
        section=p.get('section_guess')
        # Prefer local context. If a parser only emits a broad heading (e.g.
        # 'Exhibit 10.18'), retain the short window rather than matching all
        # earlier financial clauses under that broad header.
        def related(q):
            other=q.get('section_guess')
            if not section or not other:return True
            a,b=str(section),str(other)
            return a==b or a.startswith(b+'.') or b.startswith(a+'.')
        context='\n'.join(q['text'][:700] for q in previous if related(q))
        if not _TABLE_HEADER.search(context) or not _ECON.search(context):
            continue
        subtype='SUBLICENSING_RECEIPTS' if re.search(r'sublicen[sc]',context[-800:],re.I) else None
        yield i,subtype


def check_source_obligations(mapping:dict, extraction:dict) -> dict:
    passages=mapping['passages']
    evidence,cites=_cited_objects(extraction)
    terms=[t for t in extraction.get('royalty_terms',[]) if isinstance(t,dict)]
    payments=[q for q in extraction.get('other_payments',[]) if isinstance(q,dict)]
    errors=[];tested=[];seen=set()
    def flag(code,pid,message,detail=None):
        key=(code,pid,str(detail))
        if key in seen:return
        seen.add(key)
        errors.append({'code':code,'ref':pid,'message':message,'detail':detail})
    def record_rate(pid,value):
        return any(value in _term_record_values(t,pid,cites) for t in terms)
    def cited_tiers(pid):
        return [(t,z) for t in terms for z in (t.get('tiers') or []) if isinstance(z,dict) and cites(z,pid)]
    table_idx={i:sub for i,sub in _table_rows(passages)}
    for i,p in enumerate(passages):
        pid=p['passage_id']; s=p['text']; rates=_percentage_values(s)
        if i in table_idx:
            linked=cited_tiers(pid)
            redacted=bool(_REDACT.search(s)) and bool(re.search('percent|%|rate',s,re.I))
            tested.append({'type':'CONTEXTUAL_RATE_TABLE_ROW','passage_id':pid,'rates':[str(x) for x in sorted(rates)],'redacted':redacted})
            if not linked:
                flag('M10_TIER_ROW_MISSING',pid,'Source rate-table row lacks a source-cited tier record')
            elif rates and not any(rates <= {number(z.get('rate_value')) for t,z in linked} for _ in (0,)):
                flag('M10_TIER_RATE_MISMATCH',pid,'Source tier row rate differs from linked extracted tier',sorted(map(str,rates)))
            elif redacted and not any((z.get('rate_unit')=='REDACTED' or t.get('disclosure_status')=='REDACTED') and z.get('rate_value') is None for t,z in linked):
                flag('M10_REDACTED_TIER_UNACCOUNTED',pid,'Redacted source tier requires a cited null-valued redacted tier')
            if table_idx[i]=='SUBLICENSING_RECEIPTS' and linked and not any(t.get('family')=='SUBLICENSING_RECEIPTS' for t,z in linked):
                flag('M10_TIER_FAMILY_MISMATCH',pid,'Source appears to be sublicensing rate table but linked family differs')
            continue
        # Direct obligations only: do not treat interest or audit thresholds as
        # royalties merely because the same paragraph mentions the license.
        if rates and _ECON.search(s) and _PAYABLE.search(s) and not (
                re.search(r'\b(?:audit|auditor|inspection|underpayment|interest|shortfall)\b',s,re.I)
                and not re.search(r'royalt(?:y|ies)\s+(?:of|at)|of\s+net\s+sales|percentage\s+of\s+net\s+sales',s,re.I)):
            tested.append({'type':'EXPLICIT_RATE_OBLIGATION','passage_id':pid,'rates':list(map(str,sorted(rates)))})
            for rate in rates:
                if not record_rate(pid,rate):
                    flag('M10_EXPLICIT_RATE_MISSING',pid,'Expressly payable rate is absent from source-cited term, tier or adjustment',str(rate))
            # Listing a changed percentage in narrative conditions does not
            # populate a sortable second rate. A step-up/down must carry every
            # explicitly stated rate as a structured rate value or tier, not
            # merely mention it somewhere in the description text.
            if len(rates)>1 and re.search(r'\b(?:increas(?:e|es|ed)|decreas(?:e|es|ed)|step[- ]?(?:up|down)|reduc(?:e|es|ed))\b',s,re.I):
                structured=set()
                for t in terms:
                    if not (cites(t,pid,('rate_evidence_ids',)) or any(cites(z,pid) for z in t.get('tiers') or [] if isinstance(z,dict))):
                        continue
                    v=number(t.get('rate_value'))
                    if v is not None and cites(t,pid,('rate_evidence_ids',)):structured.add(v)
                    structured.update(number(z.get('rate_value')) for z in t.get('tiers') or [] if isinstance(z,dict) and cites(z,pid))
                for missing in rates-structured:
                    flag('M10_CHANGED_RATE_NOT_STRUCTURED',pid,
                         'Source step-up/down rate is mentioned but missing as a structured rate/tier',str(missing))
            # Apply a family contradiction only when this clause makes the base
            # explicit and does not also state an alternative sublicense base.
            unmistakable_sales=bool(re.search(r'\b(?:on|of)\s+(?:all\s+)?net\s+sales\b',s,re.I))
            unmistakable_sublicense=bool(re.search(r'\b(?:of|on)\s+(?:all\s+)?sublicen[sc](?:e|ing)\s+(?:fees|receipts|income|revenue)\b',s,re.I))
            if unmistakable_sales != unmistakable_sublicense:
                required='PRODUCT_SALES' if unmistakable_sales else 'SUBLICENSING_RECEIPTS'
                relevant=[t for t in terms if _term_record_values(t,pid,cites)&rates]
                if relevant and not any(t.get('family')==required for t in relevant):
                    flag('M10_RATE_FAMILY_CONTRADICTION',pid,'Rate family contradicts source-stated calculation base',required)
        # A source adjustment is not itself a tier. Require a source-cited
        # condition/adjustment for a stated rate change, including a redacted
        # percentage. Does not claim that the adjustment is correctly calculated.
        if (_RATE_ADJUST.search(s) and _ECON.search(s) and
                (rates or (_REDACT.search(s) and re.search(r'percent|%',s,re.I)))):
            tested.append({'type':'SOURCE_RATE_ADJUSTMENT','passage_id':pid})
            if not any(any(isinstance(a,dict) and cites(a,pid)
                           for a in (t.get('adjustments') or [])+(t.get('conditions') or []))
                       for t in terms):
                flag('M10_ADJUSTMENT_MISSING',pid,
                     'Source rate adjustment lacks a specifically cited extracted condition/adjustment')
        # Rate-unspecified pass-through obligations are still real licensing
        # economics. A source clause can require paying another party's annual
        # minimum, royalty or milestones without exposing their numerical rate.
        # The evidence-linked record may be NOT_VERIFIED, never fabricated.
        if (_PAYABLE.search(s) and _INDIRECT.search(s) and
                re.search(r'\b(?:required\s+(?:by|under)|pursuant\s+to|per\s+the|as\s+and\s+when|lump[- ]sum)\b',s,re.I)):
            tested.append({'type':'INDIRECT_ECONOMIC_OBLIGATION','passage_id':pid})
            if not any(cites(t,pid) or any(cites(a,pid) for a in t.get('conditions') or [] if isinstance(a,dict)) for t in terms) and not any(cites(q,pid) for q in payments):
                flag('M10_INDIRECT_OBLIGATION_MISSING',pid,
                     'Source states a pass-through or lump-sum payment but no evidence-linked economic record exists')
        # Minimums and upfront fees are obligations, not necessarily royalties.
        # This deliberately does not require every amount in a nearby unrelated
        # clause or table to have a payment record.
        if _SPECIAL.search(s) and _PAYABLE.search(s):
            amounts={number(m.group(1).replace(',','')) for m in _MONEY.finditer(s)}
            amounts.discard(None)
            tested.append({'type':'EXPLICIT_SPECIAL_PAYMENT','passage_id':pid,'amounts':list(map(str,sorted(amounts)))})
            has_source_record=any(cites(q,pid) and (q.get('kind') in {'UPFRONT','MINIMUM_ROYALTY','GUARANTEE','OTHER'}) for q in payments)
            has_term_record=any(cites(t,pid) or any(cites(x,pid) for x in t.get('conditions',[]) if isinstance(x,dict)) for t in terms)
            if not (has_source_record or has_term_record):
                flag('M10_SPECIAL_PAYMENT_MISSING',pid,'Explicit upfront/minimum payment obligation has no linked economic record')
            for amt in amounts:
                if not _linked_amount(extraction,pid,amt):
                    # An instalment component may be documented in the same
                    # payment's basis/condition rather than amount_value.
                    represented=any(cites(q,pid) and
                        any(number(m.group(1).replace(',',''))==amt for val in (q.get('basis'),q.get('condition'))
                            for m in _MONEY.finditer(str(val or ''))) for q in payments)
                    if not represented:
                        flag('M10_SPECIAL_PAYMENT_AMOUNT_MISSING',pid,'Source minimum/upfront amount has no source-linked payment or condition',str(amt))
    return {'schema':'m10-source-obligations.1','document_id':mapping['document_id'],
            'tested':tested,'errors':errors,'status':'FAIL' if errors else 'PASS_RULES_ONLY',
            'notice':'Source-led deterministic heuristics; not a certified completeness or semantic accuracy test.'}
