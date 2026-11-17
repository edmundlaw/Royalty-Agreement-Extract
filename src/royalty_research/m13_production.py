"""One-process controller for full-source M13 runs; no AI supervisor needed."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
from . import m13_two_reader as m13
from .m4_operator import import_manual_result, status as reader_status
from .mapping import map_contract
from .parsing import parse_document
from .sec_client import SECClient
from .storage import atomic_json, read_json, sha256, utc_now
from .m7_triage import triage_document


def prepare_one(mapping, run, *, mode, engine, model, check_engine=None, check_model=None,
                effort=None, check_effort=None, max_chars=64000):
    if mode=='manual':engine='manual';check_engine=None;check_model=None
    if mode=='single':check_engine=None;check_model=None
    if mode=='two' and (not check_engine or not check_model):
        raise ValueError('Two-reader mode requires second engine and model')
    if mode!='manual' and engine not in {'claude','codex'}:
        raise ValueError('Automated reader must be Claude or Codex')
    return m13.prepare(mapping,run,engine=engine,model=model,check_engine=check_engine,
                       check_model=check_model,max_chars=max_chars,reasoning_effort=effort,
                       check_reasoning_effort=check_effort)


def batch(candidates, root, *, user_agent, mode, engine, model, check_engine=None,check_model=None,
          effort=None,check_effort=None,max_agreements=10,max_chars=64000):
    """Fetch each unique SEC URL at most once; preserve every candidate in index."""
    if root.exists():raise FileExistsError('New batch directory required')
    if not 1<=max_agreements<=10000:raise ValueError('Invalid agreement limit')
    records=[json.loads(line) for line in Path(candidates).read_text().splitlines() if line.strip()]
    seen=set();unique=[]
    for r in records:
        url=r.get('source_url')
        if url not in seen:seen.add(url);unique.append(r)
    if not unique:raise ValueError('No candidate URLs')
    client=SECClient(user_agent)
    root.mkdir(parents=True)
    (root/'maps').mkdir();(root/'runs').mkdir()
    index=[];prepared=0;processed=0
    for n,r in enumerate(unique,1):
        url=r.get('source_url');item={'index':n,'source_url':url,'document_id':r.get('document_id')}
        parsed=urlparse(url or '')
        if parsed.scheme!='https' or parsed.hostname not in {'sec.gov','www.sec.gov'} or not parsed.path.startswith('/Archives/edgar/data/'):
            item['status']='INVALID_SOURCE_URL';index.append(item);continue
        if processed>=max_agreements:
            item['status']='NOT_PREPARED_AGREEMENT_LIMIT';index.append(item);continue
        try:
            processed+=1
            raw=client.fetch(url)
            paragraphs,parser=parse_document(raw,Path(parsed.path).name)
            did=r.get('document_id') or 'DOC-'+sha256(url.encode())[:16]
            mapping=map_contract(paragraphs,{'document_id':did,'source_url':url},raw_hash=sha256(raw),
                                 fetched_at=utc_now(),parser_type=parser)
            triage=triage_document(mapping);item['priority']=triage['priority']
            item['source_sha256']=sha256(raw)
            # The low-signal source is retained in the register and map. It is not
            # declared irrelevant or silently excluded from later full reading.
            atomic_json(root/'maps'/(did+'.json'),mapping)
            if triage['priority'].startswith('LOW_SIGNAL'):
                item['status']='LOW_SIGNAL_REVIEW_REQUIRED'
            else:
                prepare_one(mapping,root/'runs'/did,mode=mode,engine=engine,model=model,
                            check_engine=check_engine,check_model=check_model,effort=effort,
                            check_effort=check_effort,max_chars=max_chars)
                item['status']='FULL_SOURCE_PREPARED';prepared+=1
        except Exception as exc:
            item['status']='SOURCE_PROCESSING_FAILED';item['error']=str(exc)
        index.append(item)
        atomic_json(root/'candidate_register.json',index)
    atomic_json(root/'candidate_register.json',index)
    return {'candidates':len(unique),'prepared':prepared,'register':str(root/'candidate_register.json')}


def run_boundary(runs, *, max_calls, max_prompt_chars, max_reported_tokens=None, max_retries=0, execute=False,
                 confirm_subscription=False,confirm_credit_controls=False,timeout=900):
    """One bounded Python invocation. Never waits/polls or automatically retries."""
    if not 1<=max_calls<=1000 or max_prompt_chars<1000:raise ValueError('Invalid call/prompt budget')
    if not 0<=max_retries<=10:raise ValueError('Invalid retry budget')
    if max_reported_tokens is not None and max_reported_tokens<1:raise ValueError('Invalid token budget')
    outcomes=[]
    reported=0;unknown=False
    for receipt in Path(runs).glob('*/reader_*/results/*.receipt.json'):
        u=read_json(receipt).get('usage') or {}
        if not u:unknown=True
        reported+=sum(v for k,v in u.items() if k in {'input_tokens','output_tokens'} and isinstance(v,int))
    if max_reported_tokens is not None and unknown:
        return {'calls_attempted':0,'outcomes':[{'status':'STOPPED_USAGE_UNAVAILABLE'}]}
    if max_reported_tokens is not None and reported>=max_reported_tokens:
        return {'calls_attempted':0,'outcomes':[{'status':'STOPPED_TOKEN_BUDGET'}]}
    for root in sorted(p for p in Path(runs).iterdir() if p.is_dir() and (p/'m13_run.json').exists()):
        if len(outcomes)>=max_calls:break
        st=m13.status(root)
        if all(v['captured']==v['total'] for v in st['readers'].values()):continue
        next_reader=next((name for name,v in st['readers'].items() if v['captured']<v['total']),None)
        if not next_reader:continue
        folder=root/next_reader
        rs=reader_status(folder)
        task=next((t for t in rs['tasks'] if t['state']!='CAPTURED_NOT_QC_APPROVED'),None)
        if task is None:continue
        if task['state']!='PENDING':
            outcomes.append({'run':root.name,'status':'STOPPED_TASK_REQUIRES_MANUAL_ACTION','task':task['task_id']});break
        if task['attempts']>=max_retries+1:
            outcomes.append({'run':root.name,'status':'STOPPED_RETRY_BUDGET','task':task['task_id']});break
        prompt=folder/'prompts'/(task['task_id']+'.txt')
        if len(prompt.read_text())>max_prompt_chars:
            outcomes.append({'run':root.name,'status':'STOPPED_PROMPT_BUDGET','task':task['task_id']});break
        if read_json(folder/'plan.json')['engine']=='manual':
            outcomes.append({'run':root.name,'status':'MANUAL_RESULT_REQUIRED','task':task['task_id']});break
        result=m13.next_call(root,execute=execute,confirm_subscription=confirm_subscription,
                             confirm_credit_controls=confirm_credit_controls,timeout=timeout)
        outcomes.append({'run':root.name,'result':result})
        if not execute or result.get('status') not in {'CAPTURED_MORE_PENDING','ALL_READINGS_CAPTURED'}:break
        if max_reported_tokens is not None:
            receipt=folder/'results'/(task['task_id']+'.receipt.json')
            u=read_json(receipt).get('usage') if receipt.exists() else None
            if not u:
                outcomes.append({'run':root.name,'status':'STOPPED_USAGE_UNAVAILABLE'});break
            reported+=sum(v for k,v in u.items() if k in {'input_tokens','output_tokens'} and isinstance(v,int))
            if reported>=max_reported_tokens:
                outcomes.append({'run':root.name,'status':'STOPPED_TOKEN_BUDGET'});break
    return {'calls_attempted':sum('result' in o and execute for o in outcomes),'outcomes':outcomes}


def main(argv=None):
    ap=argparse.ArgumentParser(description='Full-source M13 production controller')
    sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--map',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    p=sub.add_parser('batch');p.add_argument('--candidates',type=Path,required=True);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--user-agent',required=True);p.add_argument('--max-agreements',type=int,default=10)
    for name in ('prepare','batch'):
        p=sub.choices[name];p.add_argument('--mode',choices=['manual','single','two'],default='manual')
        p.add_argument('--engine',choices=['claude','codex'],default='codex');p.add_argument('--model',required=True)
        p.add_argument('--effort',choices=['low','medium','high']);p.add_argument('--check-engine',choices=['claude','codex'])
        p.add_argument('--check-model');p.add_argument('--check-effort',choices=['low','medium','high'])
        p.add_argument('--max-chars',type=int,default=64000)
    p=sub.add_parser('run');p.add_argument('--runs',type=Path,required=True)
    p.add_argument('--max-calls',type=int,default=1);p.add_argument('--max-prompt-chars',type=int,default=300000)
    p.add_argument('--max-reported-tokens',type=int)
    p.add_argument('--max-retries',type=int,default=0,help='Cap prior explicitly authorized retries; never authorizes a retry')
    p.add_argument('--execute',action='store_true');p.add_argument('--confirm-subscription',action='store_true')
    p.add_argument('--confirm-credit-controls',action='store_true');p.add_argument('--timeout',type=int,default=900)
    p=sub.add_parser('import');p.add_argument('--run',type=Path,required=True);p.add_argument('--task',required=True)
    p.add_argument('--response',type=Path,required=True)
    p=sub.add_parser('finalize');p.add_argument('--run',type=Path,required=True);p.add_argument('--legacy-xlsx',action='store_true')
    p=sub.add_parser('combine');p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=ap.parse_args(argv)
    if a.command=='prepare':result=prepare_one(read_json(a.map),a.run,mode=a.mode,engine=a.engine,model=a.model,
        check_engine=a.check_engine,check_model=a.check_model,effort=a.effort,check_effort=a.check_effort,max_chars=a.max_chars)
    elif a.command=='batch':result=batch(a.candidates,a.root,user_agent=a.user_agent,mode=a.mode,
        engine=a.engine,model=a.model,check_engine=a.check_engine,check_model=a.check_model,
        effort=a.effort,check_effort=a.check_effort,max_agreements=a.max_agreements,max_chars=a.max_chars)
    elif a.command=='run':result=run_boundary(a.runs,max_calls=a.max_calls,max_prompt_chars=a.max_prompt_chars,
        max_reported_tokens=a.max_reported_tokens,max_retries=a.max_retries,
        execute=a.execute,confirm_subscription=a.confirm_subscription,
        confirm_credit_controls=a.confirm_credit_controls,timeout=a.timeout)
    elif a.command=='import':result=import_manual_result(a.run/'reader_a',a.task,a.response)
    elif a.command=='finalize':result=m13.finalize(a.run,legacy_xlsx=a.legacy_xlsx)
    else:result=m13.combine(a.runs,a.out)
    print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    return 0
if __name__=='__main__':raise SystemExit(main())
