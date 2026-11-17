#!/usr/bin/env python3
"""Read-only regression replay for Fable's M8 Mac review workspace.

Does not call any model/API, does not alter the workspace and is not a human
accuracy benchmark. Run with `python -m pip install -e .` or PYTHONPATH=src.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from royalty_research.storage import sha256
from royalty_research.m2_validation import validate_extraction
from royalty_research.m9_context_gate import check_context_economics


def replay(work_root:Path):
    results=[]
    for case in sorted(p for p in work_root.iterdir() if p.is_dir()):
        p=case/'source/m7_map.json';q=case/'output/final_extraction.json'
        if not (p.is_file() and q.is_file()):continue
        mapped=json.loads(p.read_text());extracted=json.loads(q.read_text())
        qc=validate_extraction(mapped,extracted)
        risks=check_context_economics(mapped,extracted)
        high_open=sum(z.get('severity') in ('HIGH','CRITICAL') and z.get('status')!='RESOLVED'
                      for z in extracted.get('open_issues',[]) if isinstance(z,dict))
        entry={'case':case.name,'document_id':mapped['document_id'],
               'source_map_sha256':sha256(p.read_bytes()),
               'extraction_file_sha256':sha256(q.read_bytes()),
               'deterministic_status':qc['deterministic_status'],
               'error_count':len(qc['errors']),
               'warning_count':len(qc['warnings']),
               'unresolved_high_issues':high_open,
               'source_context_tests':len(risks['tests']),
               'source_context_errors':[e['code'] for e in risks['errors']]}
        if case.name.casefold()=='neurogesx':
            effects={}
            for name,change in (
                ('drop_all_sublicensing',lambda x:x.__setitem__('royalty_terms',[
                    t for t in x['royalty_terms'] if t.get('family')!='SUBLICENSING_RECEIPTS'])),
                ('drop_25_percent_tier',lambda x:next(t for t in x['royalty_terms'] if
                    t.get('family')=='SUBLICENSING_RECEIPTS')['tiers'].pop(0)),
                ('swap_rates',lambda x:next(t for t in x['royalty_terms'] if
                    t.get('family')=='SUBLICENSING_RECEIPTS')['tiers'][0].update({'rate_value':'10'})),
                ('mislabel_sublicensing',lambda x:next(t for t in x['royalty_terms'] if
                    t.get('family')=='SUBLICENSING_RECEIPTS').update({'family':'PRODUCT_SALES'})),
                ('drop_royalty_caps',lambda x:(
                    x.__setitem__('other_payments',[p for p in x.get('other_payments',[])
                        if p.get('kind')!='CAP']),
                    next(t for t in x['royalty_terms'] if t.get('family')=='PRODUCT_SALES').__setitem__(
                        'conditions',[c for c in next(t for t in x['royalty_terms']
                           if t.get('family')=='PRODUCT_SALES').get('conditions',[])
                           if not any(k in str(c.get('text','')).lower() for k in ('cap','maximum','not to exceed'))])
                )),
            ):
                modified=copy.deepcopy(extracted);change(modified)
                res=check_context_economics(mapped,modified)
                effects[name]={'caught':bool(res['errors']),
                               'error_codes':sorted({e['code'] for e in res['errors']})}
            entry['adversarial_source_context_tests']=effects
        results.append(entry)
    return {'schema':'m9-saved-live-replay.1','disclaimer':
            'Deterministic source checks only; not independent contractual precision/recall.',
            'cases':results}


def main():
    p=argparse.ArgumentParser();p.add_argument('--work-root',type=Path,required=True)
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    result=replay(args.work_root)
    text=json.dumps(result,indent=2,ensure_ascii=False)
    if args.out:
        if args.out.exists():raise FileExistsError('Refusing to overwrite an existing replay')
        args.out.parent.mkdir(exist_ok=True,parents=True);args.out.write_text(text+'\n')
    else:print(text)

if __name__=='__main__':main()
