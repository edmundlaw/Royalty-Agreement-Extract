"""M11 opt-in integration: one full-source primary reading, no M7 per-token AI ledger.

The typed source signal manifest is derived by Python. Evidence-linked source
flags close without another model call. One optional correction packet is issued
for the remaining signals; the corrected extraction is a new immutable attempt.
No human approval and no inference API or background execution.
"""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from .m8_pipeline import _read_state,_append_context_risk_issues
from .m4_operator import status as primary_status,merge_plan
from .m11_signal_qc import (issue_signals,propose_verified_closures,
                            build_correction_packet,apply_correction_response)
from .m2_validation import validate_extraction
from .m3_workspace import init,register_map,register_extraction
from .m3_export import build_rows,write_csvs
from .m3_workbook import write_xlsx
from .storage import read_json,atomic_json,atomic_bytes,sha256,json_bytes,utc_now


def _require_m11(root):
    root,meta,mapping,packet=_read_state(root)
    if meta.get('qc_profile')!='m11' or mapping.get('quality_control_profile')!='M11_TYPED_SIGNALS':
        raise ValueError('M11 pipeline requires --qc-profile m11 at m8-prepare')
    return root,meta,mapping,packet


def _export(run_root,meta,mapping,extraction,output_name,*,xlsx=True,correction_response=None,correction_task=None):
    root=Path(run_root)
    if '/' in output_name or output_name.startswith('.'):
        raise ValueError('Unsafe output folder name')
    target=root/output_name
    if target.exists():raise FileExistsError('Immutable output folder already exists: '+str(target))
    is_m12=mapping.get('quality_control_profile')=='M12_SOURCE_FLAGS'
    if is_m12:
        from . import m12_economic_qc as m12qc
    qc=validate_extraction(mapping,extraction)
    workspace=root/'workspace'
    init(workspace) if not workspace.exists() else None
    register_map(workspace,mapping)
    info=register_extraction(workspace,mapping['document_id'],extraction,select=True)
    rows=build_rows(workspace)
    with tempfile.TemporaryDirectory(prefix='.m11-out-',dir=root) as tmp:
        out=Path(tmp)/output_name;out.mkdir()
        atomic_json(out/'final_extraction.json',extraction)
        atomic_json(out/'qc.json',qc)
        atomic_json(out/'source_signals.json',m12qc.issue_signals(mapping) if is_m12 else issue_signals(mapping))
        if correction_response is not None:
            if correction_task is None:raise ValueError('Correction response requires original task')
            atomic_json(out/'correction_response.json',correction_response)
            atomic_json(out/'applied_correction_task.json',correction_task)
        write_csvs(rows,out/'csv')
        if xlsx:write_xlsx(rows,out/'Royalty_Research_Historical_Staging.xlsx')
        resolutions=extraction.get('m12_resolutions',[]) if is_m12 else extraction.get('m11_resolutions',[])
        packet=(m12qc.build_correction_packet(mapping,extraction,resolutions=resolutions) if is_m12
                else build_correction_packet(mapping,extraction,resolutions=resolutions))
        if packet['open_flags']:
            atomic_json(out/'correction_task.json',packet)
            prompt_file='M12_TARGETED_CORRECTION.md' if is_m12 else 'M11_TARGETED_CORRECTION.md'
            prompt=(Path(__file__).resolve().parents[2]/'prompts'/prompt_file).read_text(encoding='utf-8')
            if packet['correction_ready']:
                atomic_bytes(out/'correction_prompt.txt',(prompt+'\n\nISSUED SOURCE-BOUND TASK:\n'+json.dumps(packet,ensure_ascii=False,sort_keys=True)+'\n').encode())
        manifest={'schema':'m12-output-manifest.1' if is_m12 else 'm11-output-manifest.1','created_at_utc':utc_now(),
                  'source_map_sha256':meta['map_sha256'],'extraction_sha256':sha256(json_bytes(extraction)),
                  'qc_status':qc['deterministic_status'],'selected_attempt_sha256':info['extraction_sha256'],
                  'files':{str(p.relative_to(out)):sha256(p.read_bytes()) for p in sorted(out.rglob('*')) if p.is_file()}}
        atomic_json(out/'output_manifest.json',manifest)
        out.rename(target)
    return {'schema':'m12-export-result.1' if is_m12 else 'm11-export-result.1','output_dir':str(target),'qc_status':qc['deterministic_status'],
            'm11_status':qc.get('m11_source_flags',{}).get('status'),
            'm12_status':qc.get('m12_source_flags',{}).get('status'),
            'errors':len(qc['errors']),'warnings':len(qc['warnings']),
            'correction_task_prepared':(target/'correction_task.json').is_file(),
            'spreadsheet':str(target/'Royalty_Research_Historical_Staging.xlsx') if xlsx else None}


def finalize_primary(root,*,xlsx=True):
    root,meta,mapping,packet=_require_m11(root)
    if (root/'output').exists():raise FileExistsError('M11 output already exists; never overwrite')
    state=primary_status(root/'primary_plan')
    if state['captured']!=state['total']:
        raise ValueError('Primary full-source reading incomplete')
    merged=root/'primary_plan'/'merged_extraction.json'
    if not merged.exists():merge_plan(root/'primary_plan')
    raw=read_json(merged)
    extraction=_append_context_risk_issues(mapping,packet,raw)
    extraction=dict(extraction)
    extraction['m11_manifest_sha256']=issue_signals(mapping)['manifest_sha256']
    extraction['m11_resolutions']=propose_verified_closures(mapping,extraction)
    return _export(root,meta,mapping,extraction,'output',xlsx=xlsx)


def import_correction(root,response,*,xlsx=True):
    root,meta,mapping,_=_require_m11(root)
    previous=root/'output'
    if not previous.is_dir():raise ValueError('M11 primary output not created')
    packet_path=previous/'correction_task.json'
    if not packet_path.exists():raise ValueError('No open source flags; correction task was unnecessary')
    if not read_json(packet_path).get('correction_ready'):
        raise ValueError('Source flags exceeded one-call budget; cannot import partial correction')
    if (root/'correction-01').exists():raise FileExistsError('Correction was already recorded; cannot overwrite')
    original=read_json(previous/'final_extraction.json');pkt=read_json(packet_path)
    changed=apply_correction_response(mapping,original,pkt,response)
    extraction=changed['updated_extraction']
    extraction['m11_manifest_sha256']=issue_signals(mapping)['manifest_sha256']
    extraction['m11_resolutions']=changed['resolutions']
    report=_export(root,meta,mapping,extraction,'correction-01',xlsx=xlsx,
                   correction_response=response,correction_task=pkt)
    report['previous_extraction_sha256']=changed['prior_extraction_sha256']
    report['correction_task_sha256']=pkt['task_sha256']
    return report


def _require_m12(root):
    root,meta,mapping,packet=_read_state(root)
    if meta.get('qc_profile')!='m12' or mapping.get('quality_control_profile')!='M12_SOURCE_FLAGS':
        raise ValueError('M12 requires --qc-profile m12 at m8-prepare')
    return root,meta,mapping,packet

def finalize_primary_m12(root,*,xlsx=True):
    from .m12_economic_qc import issue_signals,propose_verified_closures
    root,meta,mapping,packet=_require_m12(root)
    if (root/'output').exists():raise FileExistsError('M12 output exists; cannot overwrite')
    state=primary_status(root/'primary_plan')
    if state['captured']!=state['total']:raise ValueError('Full-source reading is incomplete')
    merged=root/'primary_plan'/'merged_extraction.json'
    if not merged.exists():merge_plan(root/'primary_plan')
    raw=read_json(merged)
    extraction=dict(_append_context_risk_issues(mapping,packet,raw))
    extraction['m12_manifest_sha256']=issue_signals(mapping)['manifest_sha256']
    extraction['m12_resolutions']=propose_verified_closures(mapping,extraction)
    return _export(root,meta,mapping,extraction,'output',xlsx=xlsx)

def import_correction_m12(root,response,*,xlsx=True):
    from .m12_economic_qc import apply_correction_response,issue_signals
    root,meta,mapping,_=_require_m12(root)
    prior=root/'output'
    if not prior.is_dir():raise ValueError('Primary M12 output not yet available')
    pkt_path=prior/'correction_task.json'
    if not pkt_path.exists():raise ValueError('No correction task required')
    if (root/'correction-01').exists():raise FileExistsError('Correction already exists; no overwrite')
    original=read_json(prior/'final_extraction.json')
    pkt=read_json(pkt_path)
    applied=apply_correction_response(mapping,original,pkt,response)
    ext=applied['updated_extraction']
    ext['m12_manifest_sha256']=issue_signals(mapping)['manifest_sha256']
    ext['m12_resolutions']=applied['resolutions']
    result=_export(root,meta,mapping,ext,'correction-01',xlsx=xlsx,
                   correction_response=response,correction_task=pkt)
    result['previous_extraction_sha256']=applied['prior_extraction_sha256']
    return result
