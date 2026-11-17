"""M8 local single-document coordinator, full-source-first, approval-free.

Zero model calls by default. Every paid-plan CLI call is an explicit separate
command governed by existing M4 limits. The secondary occurrence reader is
prepared as bounded immutable tasks; raw responses can be imported without
AI reruns. Publication includes failures and never asserts human approval.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .mapping import validate_map
from .m2_packets import make_packets
from .m7_triage import compact_packet,triage_document
from .m7_occurrences import issue_occurrences, verify_issued_manifest
from .m7_ledger_tasks import prepare_ledger_tasks, merge_ledger_chunks, attach_ledger
from .m4_operator import create_plan,load_plan,status as primary_status,merge_plan
from .m2_validation import validate_extraction
from .m3_workspace import init,register_map,register_extraction
from .m3_export import build_rows,export_manifest,write_csvs
from .m3_workbook import write_xlsx
from .storage import atomic_json, atomic_bytes, json_bytes, read_json,sha256,utc_now,stable_id

SCHEMA='m8-document-run.1'


def _root(path):
    root=Path(path).expanduser()
    if root.is_symlink():raise ValueError('Run root is a symlink')
    return root


def _project():return Path(__file__).resolve().parents[2]


def _read_state(root):
    root=_root(root)
    manifest=read_json(root/'m8_run.json')
    if (root/'m8_run.sha256').read_text(encoding='utf-8').strip()!=sha256(json_bytes(manifest)):
        raise ValueError('M8 immutable run settings were changed')
    if manifest.get('schema')!=SCHEMA:raise ValueError('Unsupported M8 run')
    mapping=read_json(root/'source'/'m7_map.json')
    occurrences=read_json(root/'source'/'source_occurrences.json')
    verify_issued_manifest(mapping,occurrences)
    if mapping.get('occurrence_manifest_sha256')!=occurrences['manifest_sha256']:
        raise ValueError('M8 map/issued-occurrence manifest mismatch')
    if sha256(json_bytes(mapping))!=manifest['map_sha256']:
        raise ValueError('M8 original source map was modified')
    full_packet=read_json(root/'source'/'full_packet.json')
    if sha256(json_bytes(full_packet))!=manifest['packet_sha256']:
        raise ValueError('M8 full packet was modified')
    plan,loaded_packet,loaded_map=load_plan(root/'primary_plan')
    if (plan['packet_sha256']!=manifest['packet_sha256'] or
        plan['engine']!=manifest['engine'] or plan['model']!=manifest['model'] or
        plan['prompt_count']!=manifest['primary_chunks'] or
        loaded_map!=mapping or loaded_packet!=full_packet):
        raise ValueError('M8 primary plan does not match authoritative source')
    all_ids=[x['passage_id'] for x in mapping['passages']]
    if full_packet.get('mode')!='full' or full_packet.get('included_passage_ids')!=all_ids:
        raise ValueError('M8 first-reader plan is not FULL DOCUMENT')
    focus=read_json(root/'source'/'focus_packet.json')
    remainder=read_json(root/'source'/'remainder_packet.json')
    if focus!=compact_packet(mapping,stage='focus',max_chars=manifest['max_chars']) or \
       remainder!=compact_packet(mapping,stage='remainder',max_chars=manifest['max_chars']):
        raise ValueError('M8 compact packet content was altered')
    if (set(focus['included_passage_ids'])&set(remainder['included_passage_ids']) or
        set(focus['included_passage_ids'])|set(remainder['included_passage_ids'])!=set(all_ids)):
        raise ValueError('M8 focus/remainder union lost source passages')
    return root,manifest,mapping,full_packet


def _prepare_run_impl(mapping,root, *, engine,model,ledger_engine=None,ledger_model=None,max_chars=64000,ledger_max_chars=14000,qc_profile="legacy"):
    """Prepare all full-source primary tasks; never calls AI or excludes source.

    Do not use priority as a filter. Retain compact focus/remainder manifests
    for later omission diagnosis and optional experimental comparison.
    """
    errs=validate_map(mapping)
    if errs:raise ValueError('Invalid source map: '+repr(errs))
    ledger_engine=ledger_engine or engine
    ledger_model=ledger_model or model
    if ledger_engine not in {'claude','codex'}:
        raise ValueError('Invalid ledger engine')
    if not isinstance(ledger_model,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',ledger_model):
        raise ValueError('Invalid ledger model label')
    if not 4000<=max_chars<=200000:raise ValueError('Packet max_chars must be 4000-200000')
    if not 2000<=ledger_max_chars<=100000:raise ValueError('Ledger max chars must be 2000-100000')
    root=_root(root)
    if root.exists():raise FileExistsError('M8 run already exists; never overwrite a prior run')
    if qc_profile not in {'legacy','m11','m12'}:raise ValueError('Unknown quality control profile')
    manifest=issue_occurrences(mapping)
    m7=dict(mapping)
    m7['quality_control_profile']='M12_SOURCE_FLAGS' if qc_profile=='m12' else ('M11_TYPED_SIGNALS' if qc_profile=='m11' else 'M7_ISSUED_OCCURRENCES')
    m7['occurrence_manifest_sha256']=manifest['manifest_sha256']
    focus=compact_packet(m7,stage='focus',max_chars=max_chars)
    remainder=compact_packet(m7,stage='remainder',max_chars=max_chars)
    full=make_packets(m7,mode='full',max_chars=max_chars)
    ids=[p['passage_id'] for p in m7['passages']]
    if (set(focus['included_passage_ids'])&set(remainder['included_passage_ids']) or
        set(focus['included_passage_ids'])|set(remainder['included_passage_ids'])!=set(ids) or
        full['included_passage_ids']!=ids):
        raise AssertionError('M8 cannot issue an incomplete document reading plan')
    root.mkdir(parents=True)
    source=root/'source';source.mkdir()
    for name,obj in [('m7_map',m7),('source_occurrences',manifest),('triage',triage_document(m7)),
                     ('focus_packet',focus),('remainder_packet',remainder),('full_packet',full)]:
        atomic_json(source/(name+'.json'),obj)
    instructions=(_project()/'prompts'/'FIRST_READER.md').read_text(encoding='utf-8')
    schema=read_json(_project()/'schemas'/'m2_extraction.schema.json')
    create_plan(m7,full,root/'primary_plan',engine=engine,model=model,
                instructions=instructions,schema=schema)
    prompt_sizes=[len((root/'primary_plan'/'prompts'/f"CHUNK-{i:04d}.txt").read_text(encoding='utf-8'))
                  for i in range(1,len(full['chunks'])+1)]
    meta={'schema':SCHEMA,'created_at_utc':utc_now(),
          'document_id':m7['document_id'],'source_text_sha256':m7['text_sha256'],
          'map_sha256':sha256(json_bytes(m7)),'packet_sha256':sha256(json_bytes(full)),
          'occurrence_manifest_sha256':manifest['manifest_sha256'],
          'engine':engine,'model':model,'ledger_engine':ledger_engine,'ledger_model':ledger_model,
          'ledger_max_chars':ledger_max_chars,'max_chars':max_chars,'qc_profile':qc_profile,
          'source_passage_count':len(ids),'primary_chunks':len(full['chunks']),
          'priority':triage_document(m7)['priority'],
          'full_source_characters':sum(len(p['text']) for p in m7['passages']),
          'prompt_character_total':sum(prompt_sizes),
          'prompt_character_max':max(prompt_sizes),
          'focus_character_fraction':focus['character_budget_proxy']['fraction_of_source_text'],
          'guarantee':'FULL_SOURCE_WAS_SUPPLIED_TO_TASKS_NOT_PROOF_MODEL_READ_OR_UNDERSTOOD',
          'human_approval':'NOT_USED'}
    atomic_json(root/'m8_run.json',meta)
    atomic_bytes(root/'m8_run.sha256',(sha256(json_bytes(meta))+'\n').encode())
    return {'status':'M8_PREPARED_NO_MODEL_CALLED','root':str(root),'document_id':meta['document_id'],
            'tasks':len(full['chunks']),'prompt_characters':sum(prompt_sizes),
            'focus_fraction':meta['focus_character_fraction']}


def prepare_run(mapping,root, *, engine,model,ledger_engine=None,ledger_model=None,max_chars=64000,ledger_max_chars=14000,qc_profile="legacy"):
    """Atomic first-run creation; interrupted preparation never leaves a fake run."""
    import tempfile
    root=_root(root)
    if root.exists():raise FileExistsError('M8 target run already exists')
    root.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.m8-preparing-',dir=root.parent) as td:
        work=Path(td)/'run'
        result=_prepare_run_impl(mapping,work,engine=engine,model=model,
                                 ledger_engine=ledger_engine,ledger_model=ledger_model,
                                 max_chars=max_chars,ledger_max_chars=ledger_max_chars,qc_profile=qc_profile)
        if root.exists():raise FileExistsError('M8 target appeared during preparation')
        work.rename(root)
        result['root']=str(root)
        return result

def status(root):
    root,manifest,mapping,packet=_read_state(root)
    primary=primary_status(root/'primary_plan')
    ledger_dir=root/'ledger'
    result={'schema':'m8-status.1','document_id':manifest['document_id'],
            'full_document_passages_assigned':len(packet['included_passage_ids']),
            'source_passages':len(mapping['passages']),
            'primary':{'captured':primary['captured'],'total':primary['total'],
                       'tasks':primary['tasks'],'limit_stopped':primary['limit_stopped']},
            'ledger':{'prepared':ledger_dir.is_dir(),'captured':0,'total':0},
            'final':{'ready':(root/'output'/'final_extraction.json').is_file(),
                     'excel':(root/'output'/'Royalty_Research_Historical_Staging.xlsx').is_file()},
            'notice':'No human approval; QC failures are retained in research export.'}
    if ledger_dir.exists():
        tasks=_load_ledger_tasks(root)
        states=[]
        for t in tasks:
            ix=t['chunk_index'];p=ledger_dir/'responses'/f'ledger_{ix:04d}.json'
            receipt=ledger_dir/'responses'/f'ledger_{ix:04d}.receipt.json'
            if p.exists() != receipt.exists():raise ValueError('Incomplete ledger response receipt: '+str(ix))
            if p.exists():
                response=read_json(p);r=read_json(receipt)
                _check_one_response(t,response)
                if r.get('sha256')!=sha256(json_bytes(response)) or r.get('task_sha256')!=t['task_sha256']:
                    raise ValueError('Stale or changed ledger response/receipt')
                states.append({'chunk_index':ix,'state':'CAPTURED'})
            else:states.append({'chunk_index':ix,'state':'PENDING'})
        result['ledger']={'prepared':True,'captured':sum(x['state']=='CAPTURED' for x in states),
            'total':len(tasks),'tasks':states}
    if result['final']['ready']:
        output=root/'output'
        hashes=read_json(output/'output_manifest.json')['output_files_sha256']
        for name,digest in hashes.items():
            p=output/name
            if not p.is_file() or p.is_symlink() or sha256(p.read_bytes())!=digest:
                raise ValueError('M8 finalized output was modified or deleted: '+name)
        report=read_json(output/'qc.json')
        result['final']['qc_status']=report['deterministic_status']
    return result


def _load_ledger_tasks(root):
    ledger=_root(root)/'ledger'
    meta=read_json(ledger/'manifest.json')
    tasks=[read_json(ledger/'tasks'/f'ledger_{i:04d}.json') for i in range(1,meta['task_count']+1)]
    if [t['task_sha256'] for t in tasks]!=meta['task_sha256']:
        raise ValueError('M8 ledger task manifest changed')
    for t in tasks:
        ix=t['chunk_index'];prompt=ledger/'tasks'/f'ledger_{ix:04d}.prompt.txt'
        if (not prompt.is_file() or prompt.is_symlink() or
            sha256(prompt.read_bytes())!=meta['prompt_sha256'][ix-1]):
            raise ValueError('M8 ledger prompt modified; refusing model call')
    return tasks


def _prepare_ledger_impl(root, *, ledger_dir):
    root,meta,mapping,_=_read_state(root)
    if meta.get('qc_profile') in {'m11','m12'}:raise ValueError('Typed-source profile does not require the legacy M7 ledger; run m11-finalize or m12-finalize')
    if (root/'ledger').exists():raise FileExistsError('Ledger tasks already prepared; preserve them')
    primary=primary_status(root/'primary_plan')
    if primary['captured']!=primary['total']:
        raise ValueError('Primary model reading incomplete; cannot issue occurrence classifications')
    output=root/'primary_plan'/'merged_extraction.json'
    if output.exists():
        # Previously merged output must still match a fresh deterministic merge.
        from .m3_chunks import merge_chunks
        plan,packet,_=load_plan(root/'primary_plan')
        chunks=[read_json(root/'primary_plan'/'results'/(t['task_id']+'.json')) for t in plan['tasks']]
        reconstructed,report=merge_chunks(mapping,packet,chunks)
        if reconstructed!=read_json(output):raise ValueError('Saved primary merge differs from current model chunks')
    else:
        merge_plan(root/'primary_plan')
    raw=read_json(output)
    tasks=prepare_ledger_tasks(mapping,raw,max_chars=meta['ledger_max_chars'])
    if not tasks and any(h['kind']!='REDACTION' for h in issue_occurrences(mapping)['occurrences']):
        raise ValueError('Ledger generator lost non-redacted source occurrence records')
    ledger=ledger_dir;(ledger/'tasks').mkdir(parents=True)
    (ledger/'responses').mkdir()
    prompt=(_project()/'prompts'/'M7_OCCURRENCE_READER.md').read_text(encoding='utf-8')
    prompt_hashes=[]
    for task in tasks:
        ix=task['chunk_index']
        atomic_json(ledger/'tasks'/f'ledger_{ix:04d}.json',task)
        exact=(prompt+'\n\nOUTPUT: JSON ONLY. DO NOT CALL TOOLS.\n\nISSUED TASK:\n'+
               json.dumps(task,ensure_ascii=False,separators=(',',':'))+'\n')
        atomic_bytes(ledger/'tasks'/f'ledger_{ix:04d}.prompt.txt',exact.encode())
        prompt_hashes.append(sha256(exact.encode()))
    meta2={'schema':'m8-ledger-manifest.1','document_id':mapping['document_id'],
           'source_text_sha256':mapping['text_sha256'],
           'raw_extraction_sha256':sha256(json_bytes(raw)),
           'occurrence_manifest_sha256':issue_occurrences(mapping)['manifest_sha256'],
           'task_count':len(tasks),'task_sha256':[t['task_sha256'] for t in tasks],
           'prompt_sha256':prompt_hashes,
           'no_auto_model_calls':True,'created_at_utc':utc_now()}
    atomic_json(ledger/'manifest.json',meta2)
    return {'status':('LEDGER_NOT_NEEDED_ZERO_SOURCE_OCCURRENCES' if not tasks else 'LEDGER_PREPARED_NO_MODEL_CALLED'),'tasks':len(tasks),
            'raw_extraction':str(output),'response_folder':str(ledger/'responses')}



def prepare_ledger(root):
    """Stage source-bound ledger tasks atomically, without any model calls."""
    import tempfile
    root=_root(root)
    _read_state(root)
    if (root/'ledger').exists():
        raise FileExistsError('Ledger has already been prepared')
    with tempfile.TemporaryDirectory(prefix='.m8-ledger-preparing-',dir=root) as td:
        staged=Path(td)/'ledger'
        result=_prepare_ledger_impl(root,ledger_dir=staged)
        staged.rename(root/'ledger')
        result['response_folder']=str(root/'ledger'/'responses')
        return result


def _check_one_response(task,response):
    if not isinstance(response,dict) or response.get('schema')!='m7-occurrence-response.1':
        raise ValueError('Wrong occurrence response schema')
    for k in ('document_id','source_text_sha256','extraction_sha256',
              'occurrence_manifest_sha256','chunk_index','chunk_count','task_sha256'):
        if response.get(k)!=task.get(k):raise ValueError('Occurrence response binding mismatch: '+k)
    if [x.get('occurrence_id') for x in response.get('occurrence_dispositions',[]) if isinstance(x,dict)]!=[
            x['occurrence_id'] for x in task['items']]:
        raise ValueError('Missing, extra, or reordered occurrence ID')
    if not isinstance(response.get('occurrence_dispositions'),list):raise ValueError('Occurrence dispositions missing')
    return True


def import_ledger_response(root, response):
    root,_,_,_=_read_state(root)
    tasks=_load_ledger_tasks(root)
    ix=response.get('chunk_index') if isinstance(response,dict) else None
    if type(ix)!=int or not 1<=ix<=len(tasks):raise ValueError('Unknown ledger task index')
    task=tasks[ix-1];_check_one_response(task,response)
    resp=root/'ledger'/'responses'/f'ledger_{ix:04d}.json'
    receipt=root/'ledger'/'responses'/f'ledger_{ix:04d}.receipt.json'
    raw=json_bytes(response)
    if resp.exists() or receipt.exists():
        if resp.exists() and receipt.exists() and resp.read_bytes()==raw:
            chk=read_json(receipt)
            if chk['sha256']==sha256(raw) and chk['task_sha256']==task['task_sha256']:
                return {'status':'EXISTING_IDENTICAL_RESPONSE','chunk_index':ix}
        raise ValueError('Ledger response exists with different bytes/receipt; no overwrite')
    # O_EXCL prevents a competing process from overwriting an already saved
    # source-bound model response. A crash between response and receipt can be
    # recovered deterministically with m8-ledger-recover.
    import os
    fd=os.open(resp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())
    atomic_json(receipt,{'schema':'m8-response-receipt.1','chunk_index':ix,
                        'task_sha256':task['task_sha256'],'sha256':sha256(raw),
                        'saved_at_utc':utc_now(),
                        'status':'CAPTURED_UNVERIFIED_NOT_HUMAN_APPROVED'})
    return {'status':'IMPORTED_IMMUTABLE_LEDGER_RESPONSE','chunk_index':ix}



def _append_context_risk_issues(mapping,packet,extraction):
    """Flag exact source paragraphs broken across AI calls and external refs.

    Never auto-resolves legal cross references or invents terms. Output is a
    warning requiring subsequent AI analysis, not a human sign-off.
    """
    chunks={p['passage_id']:i for i,c in enumerate(packet['chunks'],1)
            for p in c['passages']}
    ordered=[p['passage_id'] for p in mapping['passages']]
    issues=list(extraction.get('open_issues',[]))
    known={x.get('issue_id') for x in issues if isinstance(x,dict)}
    def add(kind,refs,description,severity='HIGH'):
        ident=stable_id('ISSUE-M8',kind,*refs)
        if ident not in known:
            issues.append({'issue_id':ident,'severity':severity,'status':'OPEN',
                'kind':kind,'description':description,'passage_ids':sorted(set(refs))})
            known.add(ident)
    for seg in mapping.get('source_segmentation',{}).get('split_original_paragraphs',[]):
        refs=[ordered[i-1] for i in seg['fragment_indices']]
        if len({chunks[x] for x in refs})>1:
            add('M8_ORIGINAL_PARAGRAPH_SPLIT_ACROSS_AI_TASKS',refs,
                'One original source paragraph was split across multiple model tasks. '
                'Its rate conditions/thresholds may not have been interpreted together.')
    sections={str(s['section']).strip().casefold():s['passage_ids'] for s in mapping.get('sections',[])}
    for entry in mapping.get('cross_references',[]):
        src=entry['passage_id']
        for ref in entry.get('references',[]):
            normalized=re.sub(r'^\s*(?:section|clause|paragraph|article)\s+', '',ref,flags=re.I).strip().casefold()
            targets=sections.get(normalized)
            if targets and any(chunks[x]!=chunks[src] for x in targets):
                add('M8_ECONOMIC_REFERENCE_ACROSS_AI_TASKS',[src]+targets[:3],
                    'A contractual cross-reference points to a section supplied in a different '
                    'model task; source completeness does not prove joint interpretation.')
    result=dict(extraction)
    result['open_issues']=issues
    return result


def finalize(root, *, export_xlsx=True):
    import tempfile
    root,meta,mapping,packet=_read_state(root)
    if meta.get('qc_profile') in {'m11','m12'}:raise ValueError('Use m11-finalize or m12-finalize for the typed-source QC profile')
    if (root/'output').exists():raise FileExistsError('Output already exists; never overwrite a prior result')
    ledger_status=status(root)['ledger']
    if not ledger_status['prepared'] or ledger_status['captured']!=ledger_status['total']:
        raise ValueError('Not all occurrence tasks have captured model responses')
    tasks=_load_ledger_tasks(root)
    outputs=[read_json(root/'ledger'/'responses'/f'ledger_{i:04d}.json') for i in range(1,len(tasks)+1)]
    raw=read_json(root/'primary_plan'/'merged_extraction.json')
    merged=merge_ledger_chunks(mapping,raw,outputs,tasks=tasks)
    extraction=attach_ledger(mapping,raw,merged)
    extraction=_append_context_risk_issues(mapping,packet,extraction)
    qc=validate_extraction(mapping,extraction)
    workspace=root/'workspace'
    init(workspace);register_map(workspace,mapping)
    register_extraction(workspace,mapping['document_id'],extraction,select=True)
    rows=build_rows(workspace)
    final_output=root/'output'
    with tempfile.TemporaryDirectory(prefix='.m8-export-preparing-',dir=root) as td:
        output=Path(td)/'output'
        output.mkdir()
        atomic_json(output/'merged_ledger.json',merged)
        atomic_json(output/'final_extraction.json',extraction)
        atomic_json(output/'qc.json',qc)
        write_csvs(rows,output/'csv')
        if export_xlsx:
            write_xlsx(rows,output/'Royalty_Research_Historical_Staging.xlsx')
        manifest={'schema':'m8-output-manifest.1','source_map_sha256':meta['map_sha256'],
                  'raw_extraction_sha256':sha256(json_bytes(raw)),
                  'final_extraction_sha256':sha256(json_bytes(extraction)),
                  'qc_status':qc['deterministic_status'],
                  'output_files_sha256':{str(p.relative_to(output)):sha256(p.read_bytes())
                      for p in sorted(output.rglob('*')) if p.is_file()}}
        atomic_json(output/'output_manifest.json',manifest)
        if final_output.exists():raise FileExistsError('Output appeared during export')
        output.rename(final_output)
    return {'status':'EXPORTED_WITH_AUTOMATED_QC_STATUS','qc_status':qc['deterministic_status'],
            'errors':len(qc['errors']),'open_issues':len(extraction.get('open_issues',[])),
            'output_dir':str(final_output),'spreadsheet':str(final_output/'Royalty_Research_Historical_Staging.xlsx') if export_xlsx else None}


def inspect_cross_references(mapping):
    """Conservative diagnostic only: unknown reference resolution is NOT no issue."""
    sections={str(s['section']).strip().casefold():s for s in mapping.get('sections',[])}
    headings=[str(s['section']).strip().casefold() for s in mapping.get('sections',[])]
    records=[]
    for entry in mapping.get('cross_references',[]):
        for ref in entry.get('references',[]):
            tail=re.sub(r'^\s*(?:section|clause|paragraph|article)\s+', '',ref, flags=re.I).strip().casefold()
            exact=tail in sections or any(x.startswith(tail+'.') for x in headings)
            records.append({'from_passage':entry['passage_id'],'reference':ref,
                            'status':'SECTION_LABEL_PRESENT' if exact else 'UNRESOLVED_TEXTUAL_REFERENCE',
                            'notice':'A label match does not prove semantic cross-reference resolution'})
    return {'schema':'m8-crossref-audit.1','document_id':mapping['document_id'],
            'total_refs':len(records),'unresolved_refs':sum(x['status']=='UNRESOLVED_TEXTUAL_REFERENCE' for x in records),
            'references':records}


def ledger_run_next(root,*,execute=False,confirm_subscription=False,confirm_credit_controls=False,
                    timeout=900,allow_cli_path=None):
    """Execute at most ONE bounded occurrence-classification task.

    No automatic retries, no network/tools from source text, no paid API. Billing
    settings cannot be inferred: user must confirm subscription and purchased-
    credit settings OUTSIDE the tool. This is not human approval of any record.
    """
    import os,shutil,subprocess,tempfile,uuid
    from .m4_operator import (_check_billing_environment,_parse_provider_output,_command,
                              LIMIT_WORDS,OUTPUT_LIMIT,_lock)
    root,meta,mapping,_=_read_state(root)
    ledger=root/'ledger'
    tasks=_load_ledger_tasks(root)
    state=status(root)
    remain=[x for x in state['ledger']['tasks'] if x['state']!='CAPTURED']
    if not remain:return {'status':'ALL_LEDGER_RESPONSES_CAPTURED','total':len(tasks)}
    ix=remain[0]['chunk_index']
    if not execute:
        return {'status':'DRY_RUN_NO_MODEL_CALLED','next_chunk':ix,
                'remaining':len(remain),'engine':meta['ledger_engine'],'model':meta['ledger_model']}
    if not confirm_subscription or not confirm_credit_controls:
        raise ValueError('Explicit --execute --confirm-subscription --confirm-credit-controls required')
    if not 30<=timeout<=3600:raise ValueError('Invalid model task timeout')
    _check_billing_environment()
    with _lock(ledger):
        if (ledger/'limit_stop.json').exists():
            raise RuntimeError('Subscription limit/billing stop active; cannot call model')
        if status(root)['ledger']['tasks'][ix-1]['state']=='CAPTURED':
            raise RuntimeError('Task has been completed by another process')
        attempts=ledger/'attempts'/f'ledger_{ix:04d}'
        attempts.mkdir(parents=True,exist_ok=True)
        previous=sorted(x for x in attempts.iterdir() if x.is_dir())
        if previous and not (previous[-1]/'retry_authorized.json').is_file():
            raise RuntimeError('Previous attempt exists; explicitly authorize retry before another model call')
        exec_path=allow_cli_path or shutil.which(meta['ledger_engine'])
        if not exec_path or not Path(exec_path).is_file():
            raise RuntimeError('CLI executable not found; no model call made')
        run_id=str(uuid.uuid4())
        attempt=attempts/run_id
        attempt.mkdir()
        prompt_file=ledger/'tasks'/f'ledger_{ix:04d}.prompt.txt'
        prompt=prompt_file.read_text(encoding='utf-8')
        atomic_json(attempt/'started.json',{'schema':'m8-attempt.1','chunk_index':ix,
            'task_sha256':tasks[ix-1]['task_sha256'],'run_id':run_id,
            'prompt_sha256':sha256(prompt.encode()),'started_at_utc':utc_now()})
        result=None
        with tempfile.TemporaryDirectory(prefix='royalty-m8-ledger-') as sandbox:
            output_file=Path(sandbox)/'last_message.json'
            command=_command(meta['ledger_engine'],meta['ledger_model'],output_file)
            command[0]=str(exec_path)
            from .m4_operator import _safe_environment,_preflight_subscription,_structured_limit_error
            safe_env=_safe_environment()
            test_mock=(allow_cli_path is not None and meta['ledger_model'].startswith('mock-'))
            try:
                if not test_mock:
                    _preflight_subscription(exec_path,meta['ledger_engine'],safe_env,sandbox)
                proc=subprocess.run(command,input=prompt,text=True,capture_output=True,
                    timeout=timeout,cwd=sandbox,env=safe_env,check=False)
                stdout=proc.stdout or '';stderr=proc.stderr or ''
                if len(stdout)>OUTPUT_LIMIT or len(stderr)>OUTPUT_LIMIT:
                    raise ValueError('CLI output exceeded safety limit')
                atomic_bytes(attempt/'stdout.txt',stdout.encode('utf-8'))
                atomic_bytes(attempt/'stderr.txt',stderr.encode('utf-8'))
                if _structured_limit_error(meta['ledger_engine'],stdout,stderr,proc.returncode):
                    atomic_json(ledger/'limit_stop.json',{'schema':'m8-limit-stop.1',
                        'chunk_index':ix,'at_utc':utc_now()})
                    raise RuntimeError('Limit/billing signal detected; stop further model calls')
                if proc.returncode:
                    raise RuntimeError('CLI returned nonzero exit: '+str(proc.returncode))
                obj=_parse_provider_output(meta['ledger_engine'],stdout,output_file)
                _check_one_response(tasks[ix-1],obj)
                result=import_ledger_response(root,obj)
                result['run_id']=run_id
                result['status']='CAPTURED_UNVERIFIED_NOT_HUMAN_APPROVED'
            except subprocess.TimeoutExpired:
                result={'status':'FAILED_TIMEOUT_NO_AUTORETRY','chunk_index':ix,
                    'warning':'Subscription use may have been consumed'}
            except (ValueError,RuntimeError,UnicodeError,json.JSONDecodeError) as exc:
                result={'status':'FAILED_NO_AUTORETRY','chunk_index':ix,
                    'error_type':type(exc).__name__,'message':str(exc)}
            atomic_json(attempt/'finished.json',{**result,'finished_at_utc':utc_now()})
            return result


def ledger_authorize_retry(root,chunk_index,reason):
    """Account/retry safety acknowledgement, never contract review/approval."""
    root,_,_,_=_read_state(root)
    if not isinstance(reason,str) or len(reason.strip())<12:
        raise ValueError('Provide meaningful retry reason of at least 12 characters')
    tasks=_load_ledger_tasks(root)
    if type(chunk_index)!=int or not 1<=chunk_index<=len(tasks):
        raise ValueError('Unknown chunk index')
    attempts=root/'ledger'/'attempts'/f'ledger_{chunk_index:04d}'
    if not attempts.is_dir():raise ValueError('No previous attempt to release')
    prior=sorted(x for x in attempts.iterdir() if x.is_dir())
    if not prior or not (prior[-1]/'started.json').is_file():
        raise ValueError('No valid previous attempt')
    if (root/'ledger'/'responses'/f'ledger_{chunk_index:04d}.json').exists():
        raise ValueError('Chunk already captured; never retry')
    flag=prior[-1]/'retry_authorized.json'
    if flag.exists():raise ValueError('Retry already released')
    atomic_json(flag,{'schema':'m8-retry.1','reason':reason.strip(),
                      'at_utc':utc_now(),
                      'notice':'Retry may consume further subscription usage; not human approval'})
    return {'status':'RETRY_RELEASED_NO_MODEL_CALLED','chunk_index':chunk_index}


def ledger_clear_limit(root,reason):
    root,_,_,_=_read_state(root)
    if not isinstance(reason,str) or len(reason.strip())<12:
        raise ValueError('A meaningful account-settings check reason is required')
    flag=root/'ledger'/'limit_stop.json'
    if not flag.exists():raise ValueError('No active limit stop')
    import uuid
    atomic_json(root/'ledger'/('limit_cleared_'+str(uuid.uuid4())+'.json'),
                {'old_stop':read_json(flag),'reason':reason,'at_utc':utc_now()})
    flag.unlink()
    return {'status':'LIMIT_CLEARED_NO_MODEL_CALLED'}


def recover_ledger_receipt(root,chunk_index):
    """Crash recovery: one saved exact response, no billing/model call."""
    root,_,_,_=_read_state(root)
    tasks=_load_ledger_tasks(root)
    if type(chunk_index)!=int or not 1<=chunk_index<=len(tasks):
        raise ValueError('Invalid ledger chunk index')
    base=root/'ledger'/'responses'
    p=base/f'ledger_{chunk_index:04d}.json'
    r=base/f'ledger_{chunk_index:04d}.receipt.json'
    if not p.is_file() or p.is_symlink() or r.exists():
        raise ValueError('Receipt recovery requires exactly one unreceipted regular response')
    obj=read_json(p)
    task=tasks[chunk_index-1]
    _check_one_response(task,obj)
    atomic_json(r,{'schema':'m8-response-receipt.1','chunk_index':chunk_index,
                    'task_sha256':task['task_sha256'],'sha256':sha256(json_bytes(obj)),
                    'saved_at_utc':utc_now(),
                    'status':'RECOVERED_CAPTURE_UNVERIFIED_NOT_HUMAN_APPROVED'})
    return {'status':'RECEIPT_RECOVERED_NO_MODEL_CALLED','chunk_index':chunk_index}
