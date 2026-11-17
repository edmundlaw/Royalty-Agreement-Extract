"""M13 research-facing five-sheet Excel from the *same* immutable M13 row sets.

No extra AI invocation and no new assessment of a contract. Legacy columns
and records remain in rows.json/CSV; the optional detailed XLSX is untouched.
A missing/legacy licensing-rights field is NOT_ASSESSED, never 'No'.
"""
from __future__ import annotations

import re
import json
from pathlib import Path
from collections import defaultdict

NAMES = ('01 Royalty Database', '02 Tiers & Mechanics', '03 Other Payments',
         '04 Source Evidence', '05 QC & Issues', '06 Other Terms')

HEADERS = {
    NAMES[0]: ['Observation ID','Nature of IA','Licensed intangible asset','Royalty rate (%)',
        'Usable for royalty benchmark','Benchmark note','Royalty rate as reported','Royalty family','Rate structure','Rate unit','Royalty base','Product / field of use',
        'Licensor','Licensee','Related party','Industry','Territory','Exclusivity','Exclusivity scope','Sublicensing rights',
        'Signing date','Effective date','SEC filing date','Agreement status','Royalty period','Minimum guarantee','Royalty cap',
        'Advance / prepayment','Upfront fee','Other material terms',
        'Payment source IDs','Rate evidence ID','Rate quotation','SEC source link','Disclosure','Reader comparison',
        'Document QC','Analyst action','Agreement ID','Document ID','IA evidence IDs',
        'Sublicensing evidence IDs','Exclusivity evidence IDs',
        'Exclusivity scope evidence IDs','Other terms evidence IDs','IA classification detail',
        'Agreement status (full text)','Exclusivity scope (full text)'],
    NAMES[1]: ['Record type','Observation ID','Term ID','Sequence','Rate (as reported)',
        'Rate numeric','Rate unit','Lower threshold','Upper threshold','Mechanics / condition',
        'Evidence IDs','SEC source link','Document ID','QC state','Notes'],
    NAMES[2]: ['Payment ID','Payment type','Amount (as reported)','Amount numeric','Currency / unit',
        'Economic basis','Trigger / period','Evidence IDs','First source quotation',
        'SEC source link','QC state','Licensor','Licensee','Disclosure','Document ID'],
    NAMES[3]: ['Evidence ID','Role','Passage ID','Section','Exact quotation',
        'Linked extracted records','SEC source link','Extraction SHA-256','Document ID'],
    NAMES[4]: ['Record type','Document ID','Priority / level','Value or issue ID','Description',
        'First reader / state','Second reader','Passage / issue ID','Section','Source quotation',
        'SEC source link','Analyst action'],
    NAMES[5]: ['Agreement ID','Document ID','Licensor','Licensee','Category','Text','Evidence IDs',
        'Quotation of first evidence','SEC source link'],
}

# --- Python-only helpers (no AI) -------------------------------------------
SHORT_LIMIT = 150      # cap for long agreement-level text in sheet 01
# Royalty families whose rate applies to money received from a sublicensee (a
# pass-through / recovery share), not to product sales. The schema has no
# separate 'recovery' family, so SUBLICENSING_RECEIPTS is the whole list.
PASS_THROUGH_FAMILIES = {'SUBLICENSING_RECEIPTS'}
# Term sheet / conditional agreements: simple wording match on contractual_status.
_CONDITIONAL = re.compile(r'term sheet|letter of intent|heads of terms|memorandum of understanding|non-?binding|'
                          r'conditional|conditions? precedent|subject to[^.;]{0,60}conditions?', re.I)
_IA_KEYWORDS = (('PATENT', re.compile(r'\bpatents?\b', re.I)),
                ('TRADEMARK_BRAND', re.compile(r'\btrade ?marks?\b|\bbrand marks?\b', re.I)),
                ('COPYRIGHT', re.compile(r'\bcopyrights?\b', re.I)),
                ('SOFTWARE', re.compile(r'\bsoftware\b|\bsource code\b', re.I)),
                ('KNOW_HOW', re.compile(r'\bknow-?how\b|\btrade secrets?\b', re.I)))
_RELATED = re.compile(r'related[- ]part(?:y|ies)|affiliated (?:entit(?:y|ies)|parties|companies)', re.I)


def _short(text, limit=SHORT_LIMIT):
    text='' if text is None else str(text)
    return text if len(text)<=limit else text[:limit-1].rstrip()+'\u2026'


def _ia_keyword_hint(texts):
    """Labelled fallback only: keyword scan of cited evidence text. Returns (nature, detail) or None."""
    found={}
    for label,rx in _IA_KEYWORDS:
        for t in texts:
            m=rx.search(t or '')
            if m:found.setdefault(label,m.group(0).lower());break
    if not found:return None
    nature=next(iter(found)) if len(found)==1 else 'MIXED'
    return nature,'Keyword hint (Python, not the reader): matched '+', '.join(f"'{w}' -> {k}" for k,w in found.items())+' in cited evidence'


def _related_hint(texts):
    for t in texts:
        for m in _RELATED.finditer(t or ''):
            if re.search(r'\b(?:not|no|nor|neither)\b[^.]{0,25}$',t[max(0,m.start()-30):m.start()],re.I):continue
            return m.group(0)
    return None


def benchmark_usable(term, related, status):
    """Python rule, zero AI. Returns ('YES'|'NO', note). Any one reason makes it NO."""
    reasons=[]
    family=term.get('Family')
    if family in PASS_THROUGH_FAMILIES:reasons.append('pass-through of sublicensee receipts, not a sales royalty')
    rate=term.get('Rate_Numeric')
    unit=str(term.get('Rate_Unit') or '').upper()
    if rate in (None,'') or term.get('Disclosure_Status') in ('REDACTED','AMBIGUOUS','NOT_VERIFIED') or unit in ('UNKNOWN','REDACTED'):
        reasons.append('rate not disclosed or unclear')
    else:
        try:
            if float(rate)>=50:reasons.append(f'rate {rate:g}% is 50% or more')
        except (TypeError,ValueError):reasons.append('rate not numeric')
        if unit not in ('PERCENT','PCT'):reasons.append('rate is not a percentage')
    if related.startswith('YES'):reasons.append('related-party agreement'+(' (keyword hint)' if 'hint' in related else ''))
    if _CONDITIONAL.search(status or ''):reasons.append('term sheet or conditional agreement')
    if reasons:return 'NO','; '.join(reasons)
    return 'YES','No exclusion rule triggered; still confirm at point of use'


def _records(rows, name):
    if name not in rows or not rows[name]: return []
    headers=rows[name][0]
    return [dict(zip(headers, r)) for r in rows[name][1:]]


def _join(value, delim='; '):
    if isinstance(value, list):return delim.join(str(v) for v in value if v is not None)
    return '' if value is None else str(value)


def _ids(value):
    """Read IDs from M3's JSON cells or from already separated row sets."""
    if isinstance(value, str) and value.startswith('['):
        try:
            decoded=json.loads(value)
            if isinstance(decoded, list):return [str(x) for x in decoded if x is not None]
        except ValueError:pass
    if isinstance(value, list):return [str(x) for x in value if x is not None]
    return [x.strip() for x in str(value or '').split(';') if x.strip()]


def _safe(value):
    if value is None:return None
    if isinstance(value, (float,int,bool)):return value
    text=str(value)
    if len(text)>32767:
        raise ValueError('Research cell exceeds Excel 32767-character limit; source must be split, not silently truncated')
    return text


def _observation_reference(term_id, document_id):
    return f'{document_id}:{term_id}'


def _payment_summary(payments: list[dict], kinds: set[str], *, minimum=False):
    """Faithful non-additive list of classified agreement-level payment records.

    Never reinterpret a signing advance as a separate upfront fee, never sum
    payments, and never treat missing rows as proof of the absence of a clause.
    """
    matches=[]
    for p in payments:
        kind=p.get('Kind')
        if kind not in kinds:continue
        if minimum and kind=='GUARANTEE':
            # 'GUARANTEE' may be e.g. share-price or performance guarantees.
            # Only explicitly royalty/minimum-labelled guarantees go here.
            description=' '.join(str(p.get(k) or '') for k in ('Basis','Condition'))
            if not re.match(r'\s*(?:a\s+|an\s+|the\s+)?(?:minimum\s+(?:annual\s+)?royalt(?:y|ies)|royalt(?:y|ies)\s+minimum|guaranteed\s+minimum\s+royalt(?:y|ies))\b',description,re.I):
                continue
        raw=p.get('Amount_Text')
        if raw is None or str(raw).strip()=='':
            amount='AMOUNT_AMBIGUOUS' if p.get('Disclosure_Status')=='AMBIGUOUS' else 'AMOUNT_NOT_DISCLOSED'
        else:
            amount=str(raw).strip()
            if re.fullmatch(r'\d+',amount):amount=f'{int(amount):,}'
        currency=p.get('Currency')
        if currency and currency not in amount:amount=f'{currency} {amount}'
        elif not currency and re.search(r'\bshares?\b',str(p.get('Basis') or ''),re.I):amount+=' shares'
        matches.append(f"{amount} [{p.get('Payment_ID') or 'UNKNOWN_ID'}]")
    return '; '.join(matches) if matches else 'NOT_ASSESSED'


def _payment_references(payments: list[dict]):
    def evidence(value):
        if isinstance(value, str) and value.startswith('['):
            try:
                parsed=json.loads(value)
                if isinstance(parsed,list):return _join(parsed)
            except (ValueError,TypeError):pass
        return _join(value)
    return '; '.join(f"{p.get('Kind') or 'UNKNOWN'}:{p.get('Payment_ID') or 'UNKNOWN'}:{evidence(p.get('Evidence_IDs'))}"
                    for p in payments if p.get('Payment_ID'))


def research_rows(rows: dict, first_readings: dict | None = None, source_texts: dict | None = None) -> dict:
    """Derive a presentational database. All primary evidence remains in rows.

    first_readings maps Document_ID to its *first reader* extraction. This does
    not resolve reader disagreements or infer novel rights on old recordings.
    """
    first_readings=first_readings or {}
    source_texts=source_texts or {}
    docs={d['Document_ID']:d for d in _records(rows,'Documents')}
    terms=_records(rows,'Royalty Terms')
    payments=_records(rows,'Other Payments')
    evid=_records(rows,'Evidence')
    evid_by_doc={(e['Document_ID'],e['Evidence_ID']):e for e in evid}
    links=defaultdict(list)
    for table, key, id_field in (('Royalty Terms','Rate_Evidence_IDs','Term_ID'),
                                 ('Royalty Terms','Evidence_IDs','Term_ID'),
                                 ('Tiers','Evidence_IDs','Term_ID'),
                                 ('Other Payments','Evidence_IDs','Payment_ID')):
        for item in _records(rows,table):
            for evidence_id in _ids(item.get(key)):
                if evidence_id:
                    ref=f'{table}:{item[id_field]}'
                    if ref not in links[(item['Document_ID'],evidence_id)]:links[(item['Document_ID'],evidence_id)].append(ref)
    result={n:[HEADERS[n][:]] for n in NAMES}
    payments_by_doc=defaultdict(list)
    for p in payments:payments_by_doc[p['Document_ID']].append(p)
    conditions=defaultdict(list)
    for c in _records(rows,'Conditions'):conditions[(c['Document_ID'],c['Term_ID'])].append(c)
    adjustments=defaultdict(list)
    for a in _records(rows,'Adjustments'):adjustments[(a['Document_ID'],a['Term_ID'])].append(a)

    for t in terms:
        did=t['Document_ID']; doc=docs.get(did,{})
        ex=first_readings.get(did) or {}; agreement=ex.get('agreement') or {}
        field_refs=agreement.get('field_evidence') or {}
        field_ev=lambda *keys:[(evid_by_doc.get((did,i)) or {}).get('Exact_Quotation') or ''
                               for k in keys for i in _ids(field_refs.get(k))]
        nature=agreement.get('licensed_ip_nature')
        nature='NOT_ASSESSED' if nature is None else nature
        ia_detail=agreement.get('licensed_ip_nature_details')
        if nature=='UNDETERMINED' or (nature=='NOT_ASSESSED' and agreement):
            hint=_ia_keyword_hint(field_ev('licensed_ip','licensed_ip_nature','licensed_ip_nature_details','duration'))
            if hint:  # never overrides a reader's own non-UNDETERMINED value
                nature=f'{hint[0]} (keyword hint)'
                ia_detail=(str(ia_detail)+' | ' if ia_detail else '')+hint[1]
        elif nature not in ('NOT_ASSESSED','UNDETERMINED') and agreement.get('licensed_ip_nature_basis')=='INFERRED':
            nature=f'{nature} (inferred)'
        related=agreement.get('related_party')
        if related is None:
            related='NOT_ASSESSED'
            if agreement:
                word=_related_hint(field_ev('licensed_ip','contractual_status') + [e.get('Exact_Quotation') or '' for (d_,_i),e in evid_by_doc.items() if d_==did]
                                   + list(source_texts.get(did) or []))
                if word:related=f'YES (keyword hint: "{word}")'
        usable,usable_note=benchmark_usable(t,related,doc.get('Contract_Status'))
        license_text=doc.get('Licensed_IP') or agreement.get('licensed_ip')
        rights=agreement.get('sublicensing_rights') or 'NOT_ASSESSED'
        material=agreement.get('other_material_terms') or []
        cats=sorted({str(m.get('category','OTHER')) for m in material})
        n_cond=len(conditions.get((did,t['Term_ID']),[])); n_adj=len(adjustments.get((did,t['Term_ID']),[]))
        summary=(', '.join(cats)+f' ({len(material)} term{"" if len(material)==1 else "s"}) \u2013 see sheet 06') if material else 'none recorded'
        if n_cond or n_adj:summary+=f'; {n_cond} condition(s), {n_adj} adjustment(s) \u2013 see sheet 02'
        summary=_short(summary,120)
        payments_present=payments_by_doc.get(did,[])
        min_hint=_payment_summary(payments_present,{'MINIMUM_ROYALTY','GUARANTEE'},minimum=True)
        cap_hint=_payment_summary(payments_present,{'CAP'})
        advance_hint=_payment_summary(payments_present,{'ADVANCE'})
        upfront_hint=_payment_summary(payments_present,{'UPFRONT'})
        payment_ids=_payment_references(payments_present)
        exclusivity_scope=agreement.get('exclusivity_scope') or 'NOT_ASSESSED'
        rate_ids=_join(t.get('Rate_Evidence_IDs'))
        evid_id=next(iter(_ids(t.get('Rate_Evidence_IDs'))),'')
        quote=(evid_by_doc.get((did,evid_id)) or {}).get('Exact_Quotation') or ''
        action='Review CORE differences' if doc.get('Extraction_Status')=='TWO_READERS_DIFFER' else 'Point-of-use source review'
        result[NAMES[0]].append([
            t.get('Observation_ID'),nature,license_text,t.get('Rate_Numeric'),usable,usable_note,t.get('Rate_Value_Text'),t.get('Family'),t.get('Structure'),
            t.get('Rate_Unit'),t.get('Royalty_Base'),t.get('Product_Scope'),t.get('Licensor') or doc.get('Licensor'),
            t.get('Licensee') or doc.get('Licensee'),related,doc.get('Industry'),t.get('Territory') or doc.get('Territory'),
            doc.get('Exclusivity') if doc.get('Exclusivity') is not None else 'NOT_ASSESSED',
            _short(exclusivity_scope),rights,doc.get('Executed') or agreement.get('execution_date'),doc.get('Effective'),
            doc.get('Filing_Date'),_short(doc.get('Contract_Status')),t.get('Effective_Period'),min_hint,cap_hint,advance_hint,
            upfront_hint,summary,payment_ids,rate_ids,quote,
            t.get('Source_URL'),t.get('Disclosure_Status'),doc.get('Second_AI_Review_Status'),
            t.get('QC_State'),action,t.get('Agreement_ID'),did,
            _join(field_refs.get('licensed_ip_nature')),_join(field_refs.get('sublicensing_rights')),
            _join(field_refs.get('exclusivity')),
            _join(field_refs.get('exclusivity_scope')),
            _join([x for m in material for x in (m.get('evidence_ids') or [])]),
            ia_detail,doc.get('Contract_Status'),exclusivity_scope])

    for did,ex in first_readings.items():
        agreement=(ex or {}).get('agreement') or {}
        doc=docs.get(did,{})
        if not any(t['Document_ID']==did for t in terms):continue   # same agreements as sheet 01
        first_term=next(t for t in terms if t['Document_ID']==did)
        for m in agreement.get('other_material_terms') or []:
            ids=[str(x) for x in (m.get('evidence_ids') or [])]
            quote=(evid_by_doc.get((did,ids[0])) or {}).get('Exact_Quotation') if ids else ''
            result[NAMES[5]].append([first_term.get('Agreement_ID'),did,agreement.get('licensor') or doc.get('Licensor'),
                agreement.get('licensee') or doc.get('Licensee'),m.get('category','OTHER'),m.get('text'),
                _join(ids),quote,doc.get('Source_URL') or first_term.get('Source_URL')])

    for row in _records(rows,'Tiers'):
        result[NAMES[1]].append(['TIER',row.get('Observation_ID'),row.get('Term_ID'),row.get('Sequence'),
             row.get('Rate_Value_Text'),row.get('Rate_Numeric'),row.get('Rate_Unit'),
             row.get('Lower_Threshold_Text'),row.get('Upper_Threshold_Text'),
             'Calculation: '+_join(row.get('Calculation'))+'; Period: '+_join(row.get('Measurement_Period'))+
             '; Threshold basis: '+_join(row.get('Threshold_Basis')),
             row.get('Evidence_IDs'),row.get('Source_URL'),row.get('Document_ID'),row.get('QC_State'),
             'Tier bounds are quoted, not inferred'])
    for table,record_type,body in (('Conditions','CONDITION','Condition_Text'),('Adjustments','ADJUSTMENT','Adjustment_Description')):
        for row in _records(rows,table):
            result[NAMES[1]].append([record_type,_observation_reference(row['Term_ID'],row['Document_ID']),
                row.get('Term_ID'),None,None,None,None,None,None,row.get(body),row.get('Evidence_IDs'),
                row.get('Source_URL'),row.get('Document_ID'),(docs.get(row['Document_ID']) or {}).get('Extraction_Status'),
                'As extracted; no inferred economics'])

    for p in payments:
        doc=docs.get(p['Document_ID'],{})
        evidence_id=next(iter(_ids(p.get('Evidence_IDs'))),'')
        q=(evid_by_doc.get((p['Document_ID'],evidence_id)) or {}).get('Exact_Quotation')
        result[NAMES[2]].append([p.get('Payment_ID'),p.get('Kind'),p.get('Amount_Text'),
            p.get('Amount_Numeric'),p.get('Currency'),p.get('Basis'),p.get('Condition'),
            p.get('Evidence_IDs'),q,p.get('Source_URL'),p.get('QC_State'),p.get('Licensor') or doc.get('Licensor'),
            p.get('Licensee') or doc.get('Licensee'),p.get('Disclosure_Status'),p.get('Document_ID')])

    for e in evid:
        result[NAMES[3]].append([e.get('Evidence_ID'),e.get('Role'),e.get('Passage_ID'),e.get('Passage_Section'),
            e.get('Exact_Quotation'),_join(links.get((e['Document_ID'],e['Evidence_ID']),[])),
            e.get('Source_URL'),e.get('Extraction_SHA256'),e.get('Document_ID')])

    for r in _records(rows,'Reader Check'):
        result[NAMES[4]].append(['READER_CHECK',r.get('Document_ID'),r.get('State'),
            r.get('Facts_Both_Readers_Recorded'),r.get('Meaning'),r.get('First_Reader'),r.get('Second_Reader'),
            None,None,None,r.get('Source_URL'),r.get('What_To_Do')])
    for r in _records(rows,'Reader Differences'):
        result[NAMES[4]].append(['READER_DIFFERENCE',r.get('Document_ID'),r.get('Level'),r.get('Value'),
            r.get('What_Differs'),r.get('First_Reader'),r.get('Second_Reader'),r.get('Passage_ID'),
            r.get('Section'),r.get('Source_Excerpt'),r.get('Source_URL'), 'Source review required' if r.get('Level')=='CORE' else 'Review if material'])
    for r in _records(rows,'Open Issues'):
        result[NAMES[4]].append(['OPEN_ISSUE',r.get('Document_ID'),r.get('Severity'),r.get('Issue_ID'),
            r.get('Description'),r.get('Kind'),r.get('Status'),r.get('Source_Passage_IDs'),
            None,None,r.get('Source_URL'),'Review open issue'])
    for r in _records(rows,'QC'):
        result[NAMES[4]].append(['DETERMINISTIC_QC',r.get('Document_ID'),r.get('State'),r.get('Errors'),
            'Warnings: '+_join(r.get('Warnings'))+'; read scope: '+_join(r.get('Read_Scope')),
            r.get('Deterministic_Result'),r.get('Second_AI_Review_Status'),None,None,None,
            r.get('Source_URL'),'Machine checks are not full-contract recall'])
    for r in _records(rows,'Amendments'):
        result[NAMES[4]].append(['AMENDMENT',r.get('From_Document_ID'),r.get('Evidence_Status'),r.get('To_Document_ID'),
            r.get('Relation'),r.get('Supersession_Scope'),r.get('Basis'),None,None,None,None,
            'No automatic effective-rate inference'])
    for r in _records(rows,'Pending Jobs'):
        result[NAMES[4]].append(['PROCESSING',r.get('Document_ID'),r.get('State'),r.get('Attempt_Count'),
            r.get('What_Next'),None,None,None,None,None,r.get('Source_URL'), 'Follow M13 run status'])

    return {name:[[_safe(x) for x in row] for row in result[name]] for name in NAMES}


def write_research_xlsx(legacy_rows: dict, destination, first_readings: dict | None = None, source_texts: dict | None = None):
    """Optional dependency matches existing M13 writer; no network or model calls."""
    from .m3_export import official_sec_url
    from .m3_workbook import _clean
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError('M13 research XLSX needs the existing optional openpyxl dependency') from exc
    sheets=research_rows(legacy_rows,first_readings,source_texts)
    wb=Workbook();wb.remove(wb.active)
    orange='FD5108'; gray='DFE3E6'; light='F5F7F8'; black='000000'
    for idx,(name,matrix) in enumerate(sheets.items()):
        ws=wb.create_sheet(name)
        ws.sheet_view.showGridLines=False
        ws.sheet_properties.tabColor=(orange if idx==0 else 'FFE8D4' if idx<3 else 'FFCDA8')
        n=len(matrix[0]); last_col=get_column_letter(n)
        title=['ROYALTY DATABASE  |  Valuation research','TIERS & ECONOMIC MECHANICS',
               'OTHER PAYMENTS & GUARANTEES','SOURCE EVIDENCE REGISTER',
               'READER & SOURCE QC  |  ACTION REGISTER','OTHER MATERIAL TERMS  |  One row per term'][idx]
        ws.cell(1,1,title).font=Font(name='Georgia',size=15,bold=True,color=black)
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=min(n,7))
        ws.row_dimensions[1].height=29
        for c in range(1,n+1):
            ws.cell(2,c).border=Border(bottom=Side(style='medium',color=orange))
        ws.row_dimensions[2].height=8
        intro=['One row per source-document royalty term; NOT a unique transaction benchmark',
               'Separate tiers, conditions and rate adjustments linked to original observations',
               'One record per extracted fee or guarantee; totals may duplicate component amounts',
               'Original quotations and passage identifiers; do not replace with paraphrases',
               'Machine source checks and reader differences when a second reading was used',
               'Full text of each other material term recorded by the reader; sheet 01 shows only a short summary'][idx]
        ws.cell(3,1,intro).font=Font(name='Arial',size=10,color=black)
        ws.merge_cells(start_row=3,start_column=1,end_row=3,end_column=min(n,9))
        ws.cell(4,1,f'{len(matrix)-1} records | source-document-specific | no unverified assumptions auto-filled').font=Font(name='Arial',size=10,bold=True,color=black)
        ws.merge_cells(start_row=4,start_column=1,end_row=4,end_column=min(n,9))
        ws.cell(5,1,('Missing fee categories = NOT_ASSESSED (not zero); agreement-level fees repeat on rate rows, NEVER SUM. Rates: 30 = 30%. '
                     'Reader agreement is not proof of recall.' if idx==0 else
                     'Full unmodified M13 technical evidence remains in rows.json and optional Detailed XLSX.')).font=Font(name='Arial',size=10,color=black)
        ws.merge_cells(start_row=5,start_column=1,end_row=5,end_column=min(n,9))
        ws.row_dimensions[5].height=20
        for c,title in enumerate(matrix[0],1):
            cell=ws.cell(7,c,_clean(title)); cell.font=Font(name='Arial',size=10,bold=True,color=black)
            cell.fill=PatternFill('solid',fgColor='FFFFFF')
            cell.alignment=Alignment(vertical='center',wrap_text=True)
            cell.border=Border(top=Side(style='medium',color=orange),bottom=Side(style='medium',color=orange))
            width=24
            if any(tok in title.lower() for tok in ['quotation','quote','description','mechanics','material terms','text','note','rights','base','source','licensed intangible','product','payment','guarantee','cap','fee']):width=38
            elif any(tok in title.lower() for tok in ['id','document','licensee','licensor','territory','evidence']):width=26
            if title in ('Royalty rate (%)','Rate numeric','Amount numeric'):width=16
            ws.column_dimensions[get_column_letter(c)].width=min(width,45)
        ws.row_dimensions[7].height=37
        for ridx,row in enumerate(matrix[1:],8):
            ws.row_dimensions[ridx].height=33 if idx in (0,4) else 30
            for c,val in enumerate(row,1):
                cell=ws.cell(ridx,c,_clean(val))
                if isinstance(cell.value,str):cell.data_type='s'
                cell.font=Font(name='Arial',size=10,color=black)
                cell.alignment=Alignment(vertical='center',wrap_text=True)
                if idx==0 and c==4 and isinstance(cell.value,(int,float)):
                    # Rates are stored as percent-points (30 means 30%).
                    cell.number_format='0.0"%"'
                if ridx%2==1:cell.fill=PatternFill('solid',fgColor=light)
                # A subtle separator every fifth row rather than an orange grid.
                if (ridx-7)%5==0:
                    cell.border=Border(bottom=Side(style='hair',color=gray))
                if isinstance(cell.value,str) and title and ('sec.gov/' in cell.value):
                    if official_sec_url(cell.value):cell.hyperlink=cell.value
        if len(matrix)>1:
            ws.auto_filter.ref=f'A7:{last_col}{len(matrix)+6}'
        ws.freeze_panes='D8' if idx==0 else 'C8'
        ws.sheet_view.zoomScale=85
        ws.print_options.horizontalCentered=False
        ws.page_setup.orientation='landscape'
    out=Path(destination);out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_name('.'+out.name+'.tmp.xlsx')
    try:
        wb.save(tmp)
        if tmp.stat().st_size<1000:raise RuntimeError('Empty research workbook')
        tmp.replace(out)
    finally:
        if tmp.exists():tmp.unlink()
    return str(out)
