"""Offline M10 replay on Fable M9 source-bound work folders (no model calls).

Run: PYTHONPATH=src python scripts/replay_m10_against_fable.py ~/royalty-research/m9test
This is a development regression, NOT a blind holdout or accuracy measurement.
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path
from royalty_research.m2_validation import validate_extraction
from royalty_research.m10_obligation_gate import check_source_obligations
from royalty_research.m7_ledger_tasks import prepare_ledger_tasks
from royalty_research.m7_occurrences import issue_occurrences


def main(root: Path):
    if not root.exists():raise FileNotFoundError(root)
    report={'schema':'m10-fable-replay.1','status':'DEVELOPMENT_REPLAY_NOT_INDEPENDENT_HOLDOUT',
            'no_model_calls':True,'cases':{},'adversarial':{}}
    for key in ('Qualigen','Kirklands'):
        folder=root/'work'/key
        source=json.loads((folder/'source'/'m7_map.json').read_text())
        extracted=json.loads((folder/'output'/'final_extraction.json').read_text())
        qc=validate_extraction(source,extracted)
        report['cases'][key]={'deterministic_status':qc['deterministic_status'],
             'qc_errors':[z['code'] for z in qc['errors']],
             'source_text_sha256':source['text_sha256']}
        def attempt(tag,mutation):
            altered=copy.deepcopy(extracted)
            mutation(altered)
            result=check_source_obligations(source,altered)
            report['adversarial'][tag]={'errors':[e['code'] for e in result['errors']],
                                      'detected':bool(result['errors'])}
        if key=='Qualigen':
            attempt('QUALIGEN_UPFRONT_REMOVED',lambda z:z.__setitem__('other_payments',
                [p for p in z['other_payments'] if p.get('kind')!='UPFRONT']))
            attempt('QUALIGEN_PASS_THROUGH_REMOVED',lambda z:(z.__setitem__('royalty_terms',[z['royalty_terms'][0]]),
                z.__setitem__('other_payments',[p for p in z['other_payments'] if p.get('kind') not in {'MINIMUM_ROYALTY','MILESTONE'}])))
        else:
            attempt('KIRKLANDS_STEPUP_TIER_REMOVED',lambda z:z['royalty_terms'][0].__setitem__('tiers',[z['royalty_terms'][0]['tiers'][0]]))
            attempt('KIRKLANDS_BOTH_MINIMUMS_REMOVED',lambda z:z.__setitem__('other_payments',
                [p for p in z['other_payments'] if p.get('kind')!='MINIMUM_ROYALTY']))
            attempt('KIRKLANDS_RATE_FAMILY_CHANGED',lambda z:z['royalty_terms'][0].__setitem__('family','SUBLICENSING_RECEIPTS'))
    for key in ('AUM','Kala'):
        source=json.loads((root/'maps'/(key+'.map.json')).read_text())
        no_terms={'evidence':[],'royalty_terms':[],'other_payments':[],
                  'open_issues':[{'severity':'HIGH','status':'OPEN','passage_ids':[p['passage_id'] for p in source['passages']]}]}
        gated=check_source_obligations(source,no_terms)
        report['cases'][key]={'source_text_sha256':source['text_sha256'],
            'source_signal_counts':{t:sum(x['type']==t for x in gated['tested'])
                for t in ('CONTEXTUAL_RATE_TABLE_ROW','EXPLICIT_RATE_OBLIGATION','EXPLICIT_SPECIAL_PAYMENT')},
            'missing_economic_records_flagged':len(gated['errors'])}
        if key=='Kala':
            raw=json.loads((root/'work'/key/'primary_plan'/'merged_extraction.json').read_text())
            occ=issue_occurrences(source)
            new_tasks=prepare_ledger_tasks(source,raw,max_chars=14000)
            report['cases'][key]['source_occurrences']=len(occ['occurrences'])
            report['cases'][key]['redaction_occurrences']=sum(h['kind']=='REDACTION' for h in occ['occurrences'])
            report['cases'][key]['remaining_AI_ledger_tasks']=len(new_tasks)
    return report


if __name__=='__main__':
    result=main(Path(sys.argv[1] if len(sys.argv)>1 else '~/royalty-research/m9test').expanduser())
    print(json.dumps(result,ensure_ascii=False,indent=2))
