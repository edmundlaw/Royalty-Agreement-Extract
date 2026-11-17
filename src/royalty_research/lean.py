"""Model-neutral, deliberately incomplete royalty screening and summary validation.

No AI calls. The packet contains only selected source passages and records what was
excluded. It is a research aid, never a full-contract omission check.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .mapping import map_contract
from .m7_triage import triage_document
from .parsing import parse_document
from .sec_client import SECClient
from .storage import sha256

FIELDS = ('licensed_intangible_asset', 'licensor', 'licensee', 'territory',
          'exclusivity', 'exclusivity_scope', 'sublicensing_rights')
TERM_FIELDS = ('type', 'value_as_reported', 'basis', 'period_or_trigger', 'passage_id', 'exact_quote')
PROMPT = """Read packet.txt and fill summary_template.json only. Return valid JSON, no prose.
This is a screened excerpt, not the complete agreement. Do not assert that an
unmentioned term is absent. Use null where evidence is missing. Each royalty rate
and payment must have its source passage_id and a short exact_quote copied from
that passage. Keep advances, upfront fees, minimum royalties, caps, and shares
separate. Never sum overlapping or amendment amounts. Report ambiguity in notes.
Use payment type UPFRONT, ADVANCE, MINIMUM_ROYALTY, GUARANTEE, CAP, MILESTONE,
SERVICE, or OTHER. An advance due at signing remains ADVANCE. Do not use outside
knowledge. Do not infer exclusivity scope from a generic label. For each non-null
agreement field, add passage_id and exact_quote under agreement_evidence.
"""


def _template(source_url, document_id):
    return {'document_id': document_id, 'source_url': source_url,
            'coverage': 'SCREENED_EXCERPTS_ONLY',
            'agreement': {field: None for field in FIELDS}, 'agreement_evidence': {},
            'royalty_terms': [], 'other_payments': [], 'notes': []}


def screen(raw: bytes, filename: str, source_url: str, *, max_packet_chars=30000):
    if max_packet_chars < 2000:
        raise ValueError('max_packet_chars must be at least 2000')
    paragraphs, parser = parse_document(raw, filename)
    did='DOC-LEAN-'+sha256(raw)[:16]
    mapping=map_contract(paragraphs, {'document_id': did, 'source_url': source_url},
                         raw_hash=sha256(raw), parser_type=parser)
    triage=triage_document(mapping)
    passages=mapping['passages']
    scores={p['passage_id']:x['score'] for p,x in zip(passages,triage['passage_scores'])}
    selected=set()
    for i,p in enumerate(passages):
        if scores[p['passage_id']] >= 7:
            selected.update(range(max(0,i-1),min(len(passages),i+2)))
    # Use whole source passages. If the budget is exceeded, retain highest scoring
    # passages and explicitly report those omitted. No silent character truncation.
    ranked=sorted(selected,key=lambda i:(-scores[passages[i]['passage_id']],i))
    kept=[]; used=0
    for i in ranked:
        p=passages[i]; cost=len(p['text'])+len(p['passage_id'])+8
        if used+cost <= max_packet_chars:
            kept.append(i);used+=cost
    kept.sort()
    lines=[f"Source: {source_url or 'LOCAL_FILE'}",
           f"Document: {did}",
           'SCREENED EXCERPTS ONLY; source passages were omitted. No absence inference.', '']
    for i in kept:
        p=passages[i]
        lines += [f"[{p['passage_id']}]",p['text'],'']
    report={'document_id':did,'source_url':source_url,'source_sha256':sha256(raw),
            'parser_type':parser,'screening_priority':triage['priority'],
            'total_passages':len(passages),'candidate_passages':len(mapping['candidate_passages']),
            'selected_passages':len(selected),'included_passages':len(kept),
            'budget_omitted_passages':len(selected)-len(kept),
            'coverage':'SCREENED_EXCERPTS_ONLY',
            'status':'READY_FOR_AI' if kept else 'LOW_SIGNAL_OR_BUDGET_EMPTY_REVIEW_BEFORE_DISCARD',
            'warning':'Python screening can miss material royalty terms; unselected text was not read by AI.'}
    source={p['passage_id']:p['text'] for i,p in enumerate(passages) if i in kept}
    return '\n'.join(lines),report,source,_template(source_url,did)


def validate(summary: dict, source: dict):
    errors=[]
    if summary.get('coverage')!='SCREENED_EXCERPTS_ONLY':
        errors.append('coverage must remain SCREENED_EXCERPTS_ONLY')
    agreement=summary.get('agreement') or {}
    refs=summary.get('agreement_evidence') or {}
    for field in FIELDS:
        if agreement.get(field) not in (None,''):
            ref=refs.get(field) or {}
            passage=source.get(ref.get('passage_id'))
            quote=ref.get('exact_quote')
            if passage is None or not isinstance(quote,str) or not quote.strip() or quote not in passage:
                errors.append(f'agreement.{field} needs a verbatim quote from a selected passage')
    if not summary.get('royalty_terms') and not summary.get('other_payments') and any(
            re.search(r'\b(?:royalt(?:y|ies)|sublicen[sc]e|minimum\s+guarantee)\b',text,re.I)
            for text in source.values()):
        errors.append('Empty extraction despite royalty signals; source review required')
    for collection in ('royalty_terms','other_payments'):
        records=summary.get(collection)
        if not isinstance(records,list):errors.append(f'{collection} must be a list');continue
        for n,item in enumerate(records,1):
            if not isinstance(item,dict):errors.append(f'{collection}[{n}] must be an object');continue
            if collection=='other_payments' and item.get('type') not in {'UPFRONT','ADVANCE','MINIMUM_ROYALTY','GUARANTEE','CAP','MILESTONE','SERVICE','OTHER'}:
                errors.append(f'{collection}[{n}] unsupported payment type')
            pid=item.get('passage_id');quote=item.get('exact_quote');value=item.get('value_as_reported')
            passage=source.get(pid)
            if passage is None:errors.append(f'{collection}[{n}] unknown or unselected passage ID');continue
            if not isinstance(quote,str) or not quote.strip() or quote not in passage:
                errors.append(f'{collection}[{n}] quotation not verbatim in passage')
            if value not in (None,''):
                pattern=(r'(?<![\w.])'+re.escape(value)+r'(?![\w.])') if isinstance(value,str) else None
                if not pattern or not isinstance(quote,str) or not re.search(pattern,quote):
                    errors.append(f'{collection}[{n}] reported value not in quotation')
            basis=item.get('basis')
            if basis and (not isinstance(basis,str) or not isinstance(quote,str) or basis.lower() not in quote.lower()):
                errors.append(f'{collection}[{n}] basis not stated in quotation; semantic review required')
    return errors


def export_xlsx(summary: dict, source: dict, destination):
    """Map a validated lean summary into the familiar five-sheet research layout."""
    errors=validate(summary,source)
    if errors:raise ValueError('Source check failed: '+repr(errors))
    from .m3_export import HEADERS
    from .m13_research_export import write_research_xlsx
    rows={name:[cols[:]] for name,cols in HEADERS.items()}
    did=summary['document_id'];url=summary.get('source_url')
    agreement=summary.get('agreement') or {}
    def add(sheet,values):rows[sheet].append([values.get(h) for h in HEADERS[sheet]])
    add('Documents',{'Document_ID':did,'Agreement_ID':did,'Source_URL':url,
        'Licensed_IP':agreement.get('licensed_intangible_asset'),
        'Licensor':agreement.get('licensor'),'Licensee':agreement.get('licensee'),
        'Territory':agreement.get('territory'),'Exclusivity':agreement.get('exclusivity'),
        'Extraction_Status':'LEAN_SCREENED_EXCERPTS_ONLY',
        'Second_AI_Review_Status':'NOT_RUN'})
    refs=agreement.get('agreement_evidence') or summary.get('agreement_evidence') or {}
    first={'agreement':{'sublicensing_rights':agreement.get('sublicensing_rights'),
        'exclusivity_scope':agreement.get('exclusivity_scope'),
        'field_evidence':{}}}
    evidence=[]
    for collection,sheet in [('royalty_terms','Royalty Terms'),('other_payments','Other Payments')]:
        for n,item in enumerate(summary.get(collection) or [],1):
            eid=f'LE-{len(evidence)+1:03d}'
            evidence.append((eid,item['passage_id'],item['exact_quote'],collection))
            if sheet=='Royalty Terms':
                literal=item.get('value_as_reported') or ''
                numeric=float(literal[:-1]) if re.fullmatch(r'\d+(?:\.\d+)?%',literal) else None
                add(sheet,{'Observation_ID':f'{did}:R{n}','Document_ID':did,'Agreement_ID':did,
                    'Term_ID':f'R{n}','Family':item.get('type'),'Rate_Value_Text':item.get('value_as_reported'),
                    'Rate_Numeric':numeric,'Rate_Unit':'PERCENT' if numeric is not None else None,
                    'Royalty_Base':item.get('basis'),'Effective_Period':item.get('period_or_trigger'),
                    'Rate_Evidence_IDs':[eid],'Evidence_IDs':[eid],'Source_URL':url,
                    'Disclosure_Status':'AS_REPORTED','QC_State':'LEAN_SOURCE_CHECK_ONLY'})
            else:
                add(sheet,{'Payment_Record_ID':f'{did}:P{n}','Document_ID':did,'Agreement_ID':did,
                    'Payment_ID':f'P{n}','Kind':item.get('type'),'Amount_Text':item.get('value_as_reported'),
                    'Basis':item.get('basis'),'Condition':item.get('period_or_trigger'),
                    'Evidence_IDs':[eid],'Source_URL':url,'QC_State':'LEAN_SOURCE_CHECK_ONLY',
                    'Disclosure_Status':'AS_REPORTED'})
    for field,ref in refs.items():
        if field not in FIELDS or not isinstance(ref,dict):continue
        eid=f'LE-{len(evidence)+1:03d}'
        evidence.append((eid,ref['passage_id'],ref['exact_quote'],'agreement'))
        if field in ('sublicensing_rights','exclusivity_scope'):
            first['agreement']['field_evidence'][field]=[eid]
    for eid,pid,quote,role in evidence:
        add('Evidence',{'Evidence_Record_ID':f'{did}:{eid}','Document_ID':did,'Agreement_ID':did,
            'Evidence_ID':eid,'Passage_ID':pid,'Role':role.upper(),'Exact_Quotation':quote,
            'Source_URL':url})
    if not summary.get('royalty_terms'):
        add('Open Issues',{'Document_ID':did,'Agreement_ID':did,'Issue_ID':'LEAN-NO-RATE',
            'Severity':'HIGH','Kind':'SCREENED_NO_RATE','Description':'No rate recorded in screened excerpts; absence unverified',
            'Status':'OPEN','Source_URL':url})
    write_research_xlsx(rows,destination,{did:first})


def _save_screen(out,raw,filename,source_url,max_packet_chars):
    packet,report,source,template=screen(raw,filename,source_url,max_packet_chars=max_packet_chars)
    out.mkdir(parents=True)
    for name,obj in [('screening.json',report),('passages.json',source),('summary_template.json',template)]:
        (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    (out/'packet.txt').write_text(packet)
    (out/'PROMPT.md').write_text(PROMPT)
    return report


def main(argv=None):
    ap=argparse.ArgumentParser(description='Model-neutral, low-token SEC royalty screening; no AI call')
    sub=ap.add_subparsers(dest='command',required=True)
    p=sub.add_parser('screen'); g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--input',type=Path);g.add_argument('--url')
    p.add_argument('--source-url');p.add_argument('--user-agent');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--max-packet-chars',type=int,default=30000)
    p=sub.add_parser('batch');g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--input-dir',type=Path)
    g.add_argument('--candidates',type=Path,help='JSONL from the existing discover command')
    p.add_argument('--user-agent');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--max-packet-chars',type=int,default=30000)
    p=sub.add_parser('validate');p.add_argument('--packet-dir',type=Path,required=True)
    p.add_argument('--summary',type=Path,required=True)
    p=sub.add_parser('export');p.add_argument('--packet-dir',type=Path,required=True)
    p.add_argument('--summary',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(argv)
    if args.command=='screen':
        if args.out.exists():raise FileExistsError('Output directory already exists')
        if args.url:
            parsed=urlparse(args.url)
            if parsed.scheme!='https' or parsed.hostname not in {'sec.gov','www.sec.gov'} or not parsed.path.startswith('/Archives/edgar/data/'):
                raise ValueError('Only official SEC exhibit URLs are accepted')
            if not args.user_agent:raise ValueError('Live SEC access requires --user-agent')
            raw=SECClient(args.user_agent).fetch(args.url)
            filename=Path(parsed.path).name;source_url=args.url
        else:
            raw=args.input.read_bytes();filename=args.input.name;source_url=args.source_url
        report=_save_screen(args.out,raw,filename,source_url,args.max_packet_chars)
        print(json.dumps(report,indent=2))
    elif args.command=='batch':
        if args.out.exists():raise FileExistsError('Output directory already exists')
        if args.candidates and not args.user_agent:raise ValueError('Live SEC access requires --user-agent')
        if args.input_dir:
            if not args.input_dir.is_dir():raise ValueError('Input directory does not exist')
            inputs=[(p,None) for p in sorted(args.input_dir.iterdir()) if p.is_file()]
            if not inputs:raise ValueError('No files in input directory')
        else:
            records=[json.loads(line) for line in args.candidates.read_text().splitlines() if line.strip()]
            inputs=[(None,r.get('source_url')) for r in records]
            if not inputs:raise ValueError('No discovery candidates')
        client=SECClient(args.user_agent) if args.candidates else None
        args.out.mkdir(parents=True)
        index=[]
        for n,(file,url) in enumerate(inputs,1):
            try:
                if file:raw=file.read_bytes();filename=file.name
                else:
                    parsed=urlparse(url or '')
                    if parsed.scheme!='https' or parsed.hostname not in {'sec.gov','www.sec.gov'} or not parsed.path.startswith('/Archives/edgar/data/'):
                        raise ValueError('Not an official SEC exhibit URL')
                    raw=client.fetch(url);filename=Path(parsed.path).name
                folder=f'{n:04d}'
                report=_save_screen(args.out/folder,raw,filename,url,args.max_packet_chars)
                index.append({'item':folder,'input':str(file) if file else url,
                              'status':report['status'],'priority':report['screening_priority'],
                              'included_passages':report['included_passages']})
            except Exception as exc:
                index.append({'item':f'{n:04d}','input':str(file) if file else url,
                              'status':'ERROR_REQUIRES_REVIEW','error':str(exc)})
        (args.out/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'screened':len(index),'ready_for_ai':sum(x['status']=='READY_FOR_AI' for x in index),
                          'requires_review':sum(x['status']!='READY_FOR_AI' for x in index),'index':str(args.out/'index.json')},indent=2))
        return any(x['status']=='ERROR_REQUIRES_REVIEW' for x in index)
    else:
        source=json.loads((args.packet_dir/'passages.json').read_text())
        summary=json.loads(args.summary.read_text())
        errors=validate(summary,source)
        if args.command=='export' and not errors:
            if args.out.exists():raise FileExistsError('Output workbook already exists')
            export_xlsx(summary,source,args.out)
        print(json.dumps({'status':'PASS_SOURCE_CHECK' if not errors else 'FAIL','errors':errors},indent=2))
        return bool(errors)
    return 0

if __name__=='__main__':raise SystemExit(main())
