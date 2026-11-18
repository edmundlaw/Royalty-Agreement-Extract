"""Compare original M13 16-sheet source rows with new five-sheet XLSX.

This verifies data mapping, not contract-level economic accuracy. No network/model.
Usage:
  python scripts/verify_research_export_parity.py \
    --original Royalty_Research_M13_example_FunctionalBrands.xlsx \
    --research Royalty_Research_M13.xlsx
"""
from __future__ import annotations
import argparse,json,sys
from collections import Counter
from pathlib import Path

def tab(workbook,name,header=1):
    ws=workbook[name]
    cols=[cell.value for cell in ws[header]]
    return [dict(zip(cols,r)) for r in ws.iter_rows(min_row=header+1,values_only=True) if any(x is not None for x in r)]

def expected_cell(value,unit):
    """Rows.json keeps percent-points; the workbook cell holds the fraction (5 -> 0.05) for percent units (v0.13.9).
    Since v0.13.12 the percent column holds ONLY percent units: any other unit gives an empty cell here and its number is
    in the 'Per-unit / currency rate' column (see expected_per_unit)."""
    if str(unit or '').upper() not in ('PERCENT','PCT'):return None
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        return round(float(value)/100.0,10)
    return value

def expected_per_unit(value,unit):
    """True when a numeric rate with a non-percent unit must show in the per-unit / currency column (text starting with the number)."""
    return isinstance(value,(int,float)) and not isinstance(value,bool) and str(unit or '').upper() not in ('PERCENT','PCT')

def per_unit_ok(cell,value):
    """The per-unit cell is text that starts with the same number as rows.json (e.g. '0.05 USD per unit')."""
    try:return isinstance(cell,str) and abs(float(cell.split()[0])-float(value))<1e-9
    except (ValueError,IndexError):return False

def same_number(a,b):
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return abs(float(a)-float(b))<1e-9
    return a==b

def go(original,research):
    from openpyxl import load_workbook
    w=load_workbook(original,read_only=True,data_only=True)
    v=load_workbook(research,read_only=True,data_only=True)
    names=['01 Royalty Database','02 Tiers & Mechanics','03 Other Payments','04 Source Evidence','05 QC & Issues','06 Other Terms']
    errs=[];checks={}
    summary_name='00 Run Summary'   # new in 0.13.8: one row per run folder; optional for workbooks written by other callers
    sheets=[x for x in v.sheetnames if x!=summary_name]
    if sheets!=names:errs.append('Research workbook does not have exactly the approved six sheets (01-05 map to the original rows; 06 Other Terms is new; 00 Run Summary is optional)')
    if summary_name in v.sheetnames:
        if v.sheetnames[0]!=summary_name:errs.append('00 Run Summary must be the first sheet')
        summ=[r for r in v[summary_name].iter_rows(min_row=8,values_only=True) if r[0] and str(r[0]).startswith('DOC-')]
        hdr=[c.value for c in v[summary_name][7]]
        if hdr[:1]!=['Document ID'] or 'Status' not in hdr:errs.append('00 Run Summary: header row 7 missing')
        else:
            si=hdr.index('Status');ri=hdr.index('Royalty rows')
            exported=[r for r in summ if str(r[si]).startswith('EXPORTED')]
            if sum((r[ri] or 0) for r in exported)!=len(tab(w,'Royalty Terms')):errs.append('00 Run Summary: royalty row counts do not add up to the original rows')
            if any(not str(r[si]).startswith(('EXPORTED','NOT_FINISHED','FAILED')) for r in summ):errs.append('00 Run Summary: unknown status')
        checks['run_summary_rows']=len(summ)
    a=tab(w,'Royalty Terms');b=tab(v,names[0],7)
    key='Observation_ID'; old={r[key]:r for r in a};new={r['Observation ID']:r for r in b}
    if len(a)!=len(b) or set(old)!=set(new):errs.append('Missing, extra, or duplicate royalty observations')
    for id in old.keys() & new.keys():
        for akey,bkey in [('Rate_Numeric','Royalty rate (%)'),('Royalty_Base','Royalty base'),('Family','Royalty family'),
                          ('Product_Scope','Product / field of use'),('Rate_Evidence_IDs','Rate evidence ID'),
                          ('Source_URL','SEC source link'),('QC_State','Document QC')]:
            if akey=='Rate_Numeric':
                if not same_number(expected_cell(old[id][akey],old[id].get('Rate_Unit')),new[id][bkey]):errs.append(f'{id}: {akey} differs')
                if expected_per_unit(old[id][akey],old[id].get('Rate_Unit')):
                    if not per_unit_ok(new[id].get('Per-unit / currency rate'),old[id][akey]):errs.append(f'{id}: per-unit / currency rate missing or differs')
                elif new[id].get('Per-unit / currency rate') not in (None,''):errs.append(f'{id}: per-unit / currency rate on a percent row')
            elif old[id][akey]!=new[id][bkey]:errs.append(f'{id}: {akey} differs')
    checks['royalty_observations']=len(b)
    a=tab(w,'Other Payments');b=tab(v,names[2],7)
    old={r['Payment_ID']:r for r in a};new={r['Payment ID']:r for r in b}
    if len(a)!=len(b) or set(old)!=set(new):errs.append('Missing, extra or duplicate other payments')
    for id in old.keys() & new.keys():
        for akey,bkey in [('Kind','Payment type'),('Amount_Text','Amount (as reported)'),('Amount_Numeric','Amount numeric'),
                          ('Currency','Currency / unit'),('Evidence_IDs','Evidence IDs'),
                          ('Basis','Economic basis'),('Condition','Trigger / period'),
                          ('Source_URL','SEC source link'),('Disclosure_Status','Disclosure')]:
            if old[id][akey]!=new[id][bkey]:errs.append(f'Payment {id}: {akey} differs')
    checks['other_payments']=len(b)
    a=tab(w,'Evidence');b=tab(v,names[3],7)
    old={(r['Document_ID'],r['Evidence_ID']):r for r in a};new={(r['Document ID'],r['Evidence ID']):r for r in b}
    if len(a)!=len(b) or set(old)!=set(new):errs.append('Missing, extra or duplicated evidence')
    for id in old.keys() & new.keys():
        for akey,bkey in [('Passage_ID','Passage ID'),('Exact_Quotation','Exact quotation'),('Source_URL','SEC source link'),
                          ('Extraction_SHA256','Extraction SHA-256')]:
            if old[id][akey]!=new[id][bkey]:errs.append(f'Evidence {id}: {akey} differs')
    checks['source_evidence']=len(b)
    mechanics=tab(v,names[1],7)
    old_types={'TIER':len(tab(w,'Tiers')),'CONDITION':len(tab(w,'Conditions')),'ADJUSTMENT':len(tab(w,'Adjustments'))}
    new_types=Counter(r['Record type'] for r in mechanics)
    for kind,old_n in old_types.items():
        if old_n !=new_types[kind]:errs.append(f'{kind} rows lost or duplicated: {old_n} vs {new_types[kind]}')
    old_tiers={(t['Observation_ID'],t['Term_ID'],t['Sequence']):t for t in tab(w,'Tiers')}
    for r in mechanics:
        if r['Record type']=='TIER':
            k=(r['Observation ID'],r['Term ID'],r['Sequence']);src=old_tiers.get(k)
            if src is None or not same_number(expected_cell(src.get('Rate_Numeric'),src.get('Rate_Unit')),r['Rate numeric']):
                errs.append(f'Tier {k}: rate numeric differs')
            elif expected_per_unit(src.get('Rate_Numeric'),src.get('Rate_Unit')) and not per_unit_ok(r.get('Per-unit / currency rate'),src.get('Rate_Numeric')):
                errs.append(f'Tier {k}: per-unit / currency rate missing or differs')
    checks['mechanics']=dict(new_types)
    q=tab(v,names[4],7)
    for typ,src in [('READER_CHECK','Reader Check'),('READER_DIFFERENCE','Reader Differences'),
                    ('OPEN_ISSUE','Open Issues'),('DETERMINISTIC_QC','QC'),('AMENDMENT','Amendments'),('PROCESSING','Pending Jobs')]:
        # v0.13.12: OPEN_ISSUE rows of kind PERIOD_LIMITED_LINK_UNRESOLVED are raised by the export rules, not read from rows.json
        n_new=sum(r['Record type']==typ and not (typ=='OPEN_ISSUE' and r.get('First reader / state')=='PERIOD_LIMITED_LINK_UNRESOLVED') for r in q)
        if n_new!=len(tab(w,src)):
            errs.append(f'QC {typ}: count mismatch')
    checks['qc_records']=len(q)
    other=tab(v,names[5],7)   # new in 0.13.6: one row per other material term; no original-row equivalent
    if any(not (r.get('Document ID') and r.get('Category') and r.get('Text')) for r in other):errs.append('06 Other Terms: row without document, category or text')
    checks['other_terms']=len(other)
    return {'status':'PASS_MAPPING_ONLY' if not errs else 'FAIL','source':str(original),
            'research':str(research),'checks':checks,'errors':errs}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--original',type=Path,required=True);p.add_argument('--research',type=Path,required=True)
    a=p.parse_args()
    result=go(a.original,a.research);print(json.dumps(result,indent=2));sys.exit(bool(result['errors']))
