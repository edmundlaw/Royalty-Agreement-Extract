"""Compact post-extraction Sonnet reconciliation tasks; no model API or network calls.

The original M2 extraction is immutable. This stage only annotates Python-issued
source occurrences, so the expensive contract extraction need not be repeated
when a bookkeeping-only correction is needed.
"""
from __future__ import annotations

from .m7_occurrences import issue_occurrences
from .storage import json_bytes,sha256,stable_id

PACKET='m7-occurrence-task.1'


def prepare_ledger_tasks(mapping,extraction,*,max_chars=14000):
    if not isinstance(max_chars,int) or max_chars<2000:raise ValueError('max_chars too small')
    if extraction.get('document_id')!=mapping['document_id'] or extraction.get('source_text_sha256')!=mapping['text_sha256']:
        raise ValueError('EXTRACTION_SOURCE_MISMATCH')
    manifest=issue_occurrences(mapping)
    pids={p['passage_id']:p for p in mapping['passages']}
    evidence={e['evidence_id']:e['passage_id'] for e in extraction.get('evidence',[]) if isinstance(e,dict) and 'evidence_id' in e and 'passage_id' in e}
    terms=[]
    for t in extraction.get('royalty_terms',[]):
        if not isinstance(t,dict):continue
        terms.append({'term_id':t.get('term_id'),'family':t.get('family'),'structure':t.get('structure'),
            'rate':t.get('rate_value'),'unit':t.get('rate_unit'),
            'tiers':[{'sequence':x.get('sequence'),'rate':x.get('rate_value'),
                      'lower':x.get('lower'),'upper':x.get('upper')} for x in t.get('tiers',[]) if isinstance(x,dict)],
            'cited_passage_ids':sorted({evidence[x] for x in (t.get('evidence_ids') or [])+(t.get('rate_evidence_ids') or []) if x in evidence})})
    payments=[{'payment_id':t.get('payment_id'),'kind':t.get('kind'),'amount':t.get('amount_value'),
          'cited_passage_ids':sorted({evidence[x] for x in t.get('evidence_ids',[]) if x in evidence})}
          for t in extraction.get('other_payments',[]) if isinstance(t,dict)]
    # Store summaries once per task; chunk by actual JSON bytes, not just source chars.
    chunks=[];current=[]
    summary={'terms':terms,'payments':payments}
    for h in manifest['occurrences']:
        # A redaction token conveys no numeric rate for a model to classify.
        # Preserve every source occurrence deterministically instead of issuing
        # hundreds of identical, expensive Sonnet requests. M10's independent
        # source gate separately requires each economic table row to be linked
        # to a redacted tier/payment record; this only closes the marker ledger.
        if h['kind']=='REDACTION':
            continue
        original=pids[h['passage_id']]['text']
        # Bounded exact substring around occurrence; rates may depend on neighboring
        # text, so model must request escalation if surrounding context insufficient.
        start=max(0,h['start']-220);end=min(len(original),h['end']+220)
        item={'occurrence_id':h['id'],'passage_id':h['passage_id'],'kind':h['kind'],
            'literal':h['literal'],'start':h['start'],'end':h['end'],'risk':h['risk'],
            'context':original[start:end], 'context_start':start,
            'is_context_truncated':start>0 or end<len(original)}
        trial=current+[item]
        if len(json_bytes({'summary':summary,'items':trial}))>max_chars and current:
            chunks.append(current);current=[item]
        elif len(json_bytes({'summary':summary,'items':trial}))>max_chars:
            raise ValueError('One ledger occurrence + term summary exceeds max_chars; use a larger budget')
        else:current=trial
    if current:chunks.append(current)
    tasks=[]
    for index,items in enumerate(chunks,1):
        task={'schema':PACKET,'document_id':mapping['document_id'],
            'source_text_sha256':mapping['text_sha256'],
            'extraction_sha256':sha256(json_bytes(extraction)),
            'occurrence_manifest_sha256':manifest['manifest_sha256'],
            'chunk_index':index,'chunk_count':len(chunks),
            'term_summary':terms,'payment_summary':payments,
            'items':items,
            'warning':'Local evidence snippets cannot prove contractual meaning; mark uncertainty for escalation'}
        task['task_sha256']=sha256(json_bytes(task))
        tasks.append(task)
    return tasks


def merge_ledger_chunks(mapping,extraction,outputs, *, tasks):
    expected=issue_occurrences(mapping)
    issued={h['id']:h for h in expected['occurrences']}
    digest=sha256(json_bytes(extraction))
    if extraction.get('document_id')!=mapping['document_id'] or extraction.get('source_text_sha256')!=mapping['text_sha256']:
        raise ValueError('Original extraction mismatches source map')
    if not isinstance(outputs,list) or not isinstance(tasks,list) or bool(outputs)!=bool(tasks):
        raise ValueError('Ledger response/task lists must correspond')
    if not tasks and any(h['kind']!='REDACTION' for h in expected['occurrences']):
        raise ValueError('Non-redaction source occurrences cannot bypass model classification')
    task_by_index={t.get('chunk_index'):t for t in tasks}
    if len(task_by_index)!=len(tasks) or set(task_by_index)!=set(range(1,len(tasks)+1)):
        raise ValueError('Missing/duplicate issued tasks')
    if any(t.get('task_sha256')!=sha256(json_bytes({k:v for k,v in t.items() if k!='task_sha256'})) for t in tasks):
        raise ValueError('Issuer task hash mismatch')
    if any(t.get('extraction_sha256')!=digest or t.get('occurrence_manifest_sha256')!=expected['manifest_sha256'] for t in tasks):
        raise ValueError('Issuer task/source/extraction mismatch')
    chosen={};seen_chunks=set();expected_n=None
    for hit in expected['occurrences']:
        if hit['kind']=='REDACTION':
            chosen[hit['id']]={'occurrence_id':hit['id'],
                'classification':'REDACTION','term_id':None,'payment_id':None,
                'rationale':'Python preserved source redaction marker without inferring economic meaning; independent source-row QC remains mandatory.'}

    for output in outputs:
        if not isinstance(output,dict):raise ValueError('Invalid response chunk')
        if output.get('schema')!='m7-occurrence-response.1':raise ValueError('Wrong response schema')
        idx=output.get('chunk_index');n=output.get('chunk_count')
        if type(idx) is not int or type(n) is not int or idx<1 or n<1 or idx>n or idx in seen_chunks:
            raise ValueError('Missing/duplicate/bad ledger chunk index')
        seen_chunks.add(idx)
        task=task_by_index.get(idx)
        if task is None or output.get('task_sha256')!=task['task_sha256']:
            raise ValueError('Ledger response task fingerprint mismatch')
        expected_ids=[x['occurrence_id'] for x in task['items']]
        received_ids=[x.get('occurrence_id') if isinstance(x,dict) else None for x in output.get('occurrence_dispositions',[])]
        if received_ids != expected_ids:
            raise ValueError('Ledger chunk must classify exact source-issued occurrence IDs in source order')
        if expected_n is not None and n!=expected_n:raise ValueError('Conflicting chunk_count')
        expected_n=n
        for field,val in [('document_id',mapping['document_id']),('source_text_sha256',mapping['text_sha256']),
                          ('extraction_sha256',digest),('occurrence_manifest_sha256',expected['manifest_sha256'])]:
            if output.get(field)!=val:raise ValueError('Stale or mismatched ledger binding: '+field)
        classified=output.get('occurrence_dispositions')
        if not isinstance(classified,list):raise ValueError('Missing occurrence_dispositions array')
        for item in classified:
            if not isinstance(item,dict):raise ValueError('Invalid occurrence disposition')
            ident=item.get('occurrence_id')
            if ident not in issued:raise ValueError('Unissued occurrence ID in model response')
            if ident in chosen:raise ValueError('Duplicate occurrence across ledger chunks')
            chosen[ident]=item
    if seen_chunks!=set(range(1,(expected_n or 0)+1)):
        raise ValueError('Missing one or more numbered ledger response chunks')
    if set(issued)!=set(chosen):
        missing=sorted(set(issued)-set(chosen))[:20]
        raise ValueError('Ledger source occurrence coverage incomplete: '+str(missing))
    return {'schema':'m7-merged-ledger.1', 'document_id':mapping['document_id'],
            'source_text_sha256':mapping['text_sha256'], 'extraction_sha256':digest,
            'occurrence_manifest_sha256':expected['manifest_sha256'],
            'automatically_preserved_redactions':sum(h['kind']=='REDACTION' for h in expected['occurrences']),
            'occurrence_dispositions':[chosen[h['id']] for h in expected['occurrences']]}


def attach_ledger(mapping,extraction,ledger):
    manifest=issue_occurrences(mapping)
    if ledger.get('schema')!='m7-merged-ledger.1':raise ValueError('Unrecognized ledger schema')
    if ledger.get('document_id')!=mapping['document_id'] or ledger.get('source_text_sha256')!=mapping['text_sha256']:
        raise ValueError('LEDGER_SOURCE_MISMATCH')
    if ledger.get('extraction_sha256')!=sha256(json_bytes(extraction)):
        raise ValueError('LEDGER_EXTRACTION_CHANGED: cannot attach ledger to another attempt')
    if ledger.get('occurrence_manifest_sha256')!=manifest['manifest_sha256']:
        raise ValueError('LEDGER_MANIFEST_MISMATCH')
    result=dict(extraction)
    if 'occurrence_dispositions' in result or 'occurrence_manifest_sha256' in result:
        raise ValueError('Refusing to replace previously attached occurrence ledger')
    result['occurrence_manifest_sha256']=manifest['manifest_sha256']
    result['occurrence_dispositions']=ledger['occurrence_dispositions']
    # A narrowly scoped Sonnet classification task must not force a full re-read
    # merely to record its uncertainty. Generate explicit MACHINE open issues for
    # unresolved source-issued occurrences, never a human sign-off or inferred rate.
    existing=list(extraction.get('open_issues',[]))
    by_passage={pid for issue in existing if isinstance(issue,dict) and
                issue.get('status')!='RESOLVED' and issue.get('severity') in {'HIGH','CRITICAL'}
                for pid in (issue.get('passage_ids') or [])}
    issued={h['id']:h for h in manifest['occurrences']}
    for item in ledger['occurrence_dispositions']:
        if item.get('classification')!='UNRESOLVED': continue
        hit=issued[item['occurrence_id']]
        pid=hit['passage_id']
        if pid in by_passage:continue
        existing.append({'issue_id':stable_id('ISSUE-M7',item['occurrence_id']),
                         'severity':'HIGH', 'status':'OPEN',
                         'kind':'M7_AUTOMATED_OCCURRENCE_UNRESOLVED',
                         'description':('Automatic evidence issue: source occurrence '+
                             hit['literal']+' was unresolved by the occurrence reader. '+
                             'Requires subsequent source-based AI correction; no human sign-off.'),
                         'passage_ids':[pid]})
        by_passage.add(pid)
    result['open_issues']=existing
    return result
