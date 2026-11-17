"""M7 source-issued economic occurrence IDs and strict, source-bound reconciliation.

No LLM classification is trusted as evidence that an occurrence disappeared. Every
source location is issued by Python from the immutable M1 map. Full coverage of
these expressions does not imply full contract recall, especially for narrative
obligations without recognizable numeric language.
"""
from __future__ import annotations

from .m2_validation import _plain_number  # RF-08

import re
from decimal import Decimal
from .m6_source_risk import source_hits, number, _linked_amount, _linked_percent, POTENTIAL_RATE, NONRATE
from .mapping import FRACTION, PER_UNIT, SPELLED_RATE, INDIRECT_ECONOMICS
from .storage import json_bytes, sha256, stable_id

SCHEMA = 'm7-source-occurrences.1'
PAYMENT_CONTEXT = re.compile(r"\b(?:licen[sc](?:e|ing)|royalt(?:y|ies)|sublicen[sc](?:e|ing)|remit|pay(?:able|ment|s)?|consideration|sales)\b", re.I)
HIGH_RISKS = {'POTENTIAL_RUNNING_RATE','POTENTIAL_MINIMUM_OR_CAP',
              'POTENTIAL_REDACTED_ECONOMICS','POTENTIAL_SPELLED_RATE',
              'POTENTIAL_INDIRECT_PAYMENT'}
CHOICES = {'ROYALTY_RATE','ADJUSTMENT','OTHER_PAYMENT','THRESHOLD','CONDITION','NON_ROYALTY','REDACTION','UNRESOLVED'}

_NON_ECONOMIC_RATE = re.compile(
    r'\b(?:audit|examination|inspection|late[- ]payment|interest charges?|penalt(?:y|ies)|'
    r'does not represent a reasonable royalty)\b', re.I)

def _nonroyalty_context(text:str) -> bool:
    """Narrow context test: a threshold/interest clause is not a license rate.

    Never use this to excuse a rate in a sublicense/royalty table; the
    independent M9 source-context gate checks those rows regardless of labels.
    """
    if not _NON_ECONOMIC_RATE.search(text):return False
    if re.search(r'\b(?:earned royalty of|sublicense fee of|royalty rate of|'
                 r'pay\s+(?:\w+\s+){0,3}?\d+(?:\.\d+)?\s*%\s+of\s+net\s+sales|'
                 r'pay\s+(?:\w+\s+){0,3}?(?:one|two|three|four|five|six|seven|eight|nine|ten)\s+percent\s+of\s+net\s+sales)\b',text,re.I):
        return False
    return True


def issue_occurrences(mapping: dict) -> dict:
    from .mapping import validate_map
    errors = validate_map(mapping)
    if errors: raise ValueError('Invalid source map: '+', '.join(errors))
    hits = source_hits(mapping)
    for hit in hits:
        if hit.get("normalized") is not None:
            hit["normalized"] = str(hit["normalized"])
    for passage in mapping['passages']:
        for kind,rx in [('SPELLED_FRACTION',FRACTION),('PER_UNIT_SIGNAL',PER_UNIT),('SPELLED_RATE',SPELLED_RATE),('INDIRECT_ECONOMICS',INDIRECT_ECONOMICS)]:
            for m in rx.finditer(passage['text']):
                start=m.start();end=m.end();text=passage['text']
                window=text[max(0,start-160):min(len(text),end+160)]
                finance=bool(PAYMENT_CONTEXT.search(window) or POTENTIAL_RATE.search(window))
                nonrate=bool(NONRATE.search(window)) and not bool(POTENTIAL_RATE.search(window))
                risk='CONTEXT_REVIEW'
                if finance and not nonrate:
                    if kind in {'SPELLED_FRACTION','SPELLED_RATE'}:
                        risk='POTENTIAL_SPELLED_RATE'
                    elif kind=='INDIRECT_ECONOMICS':
                        risk='POTENTIAL_INDIRECT_PAYMENT'
                    elif kind=='PER_UNIT_SIGNAL' and POTENTIAL_RATE.search(window):
                        risk='POTENTIAL_INDIRECT_PAYMENT'
                hits.append({'id':stable_id('OCC',passage['passage_id'],kind,str(start),m.group(0)),
                    'passage_id':passage['passage_id'], 'kind':kind,'start':start,
                    'end':end,'literal':m.group(0),'risk':risk, 'normalized':None})
    order = {p['passage_id']:i for i,p in enumerate(mapping['passages'])}
    hits.sort(key=lambda x:(order[x['passage_id']],x['start'],x['end'],x['kind']))
    payload={'schema':SCHEMA,'document_id':mapping['document_id'],
             'source_text_sha256':mapping['text_sha256'],
             'source_passage_count':len(mapping['passages']), 'occurrences':hits}
    payload['manifest_sha256']=sha256(json_bytes(payload))
    return payload


def verify_issued_manifest(mapping:dict, manifest:dict):
    expected=issue_occurrences(mapping)
    if manifest != expected:
        raise ValueError('SOURCE_OCCURRENCE_MANIFEST_MISMATCH: regenerate from immutable source map')
    return True


def check_m7_occurrences(mapping:dict, extraction:dict):
    """Fail-closed source-ID reconciliation. Returns a non-professional QC report.

    Distinct occurrence IDs avoid model-invented literal counts, but cannot prove
    that the model interpreted legal meaning correctly. A rate shared by two
    different economic obligations in one passage remains a semantic risk.
    """
    manifest=issue_occurrences(mapping)
    ids={o['id']:o for o in manifest['occurrences']}
    dispositions=extraction.get('occurrence_dispositions')
    errors=[];warnings=[];seen={}
    def fail(code,ref,message):errors.append({'code':code,'ref':ref,'message':message})
    if not isinstance(dispositions,list):
        fail('M7_OCCURRENCE_LEDGER_MISSING',None,'A source-issued occurrence ledger is required')
        dispositions=[]
    if extraction.get('occurrence_manifest_sha256')!=manifest['manifest_sha256']:
        fail('M7_MANIFEST_BINDING_MISMATCH',None,'Extraction must cite the exact source-issued occurrence manifest')
    eids={x.get('evidence_id'):x.get('passage_id') for x in extraction.get('evidence',[]) if isinstance(x,dict)}
    def cites(pid, evidence_ids):
        return any(eids.get(eid)==pid for eid in (evidence_ids or []))
    def term_cites(term,pid):
        return (cites(pid,term.get('evidence_ids')) or cites(pid,term.get('rate_evidence_ids')) or
            any(cites(pid,z.get('evidence_ids')) or cites(pid,z.get('threshold_evidence_ids'))
                for z in term.get('tiers',[]) if isinstance(z,dict)) or
            any(cites(pid,z.get('evidence_ids')) for z in (term.get('conditions') or [])+
                (term.get('adjustments') or []) if isinstance(z,dict)))
    terms={x.get('term_id'):x for x in extraction.get('royalty_terms',[]) if isinstance(x,dict)}
    payments={x.get('payment_id'):x for x in extraction.get('other_payments',[]) if isinstance(x,dict)}
    issues={p for x in extraction.get('open_issues',[]) if isinstance(x,dict) and x.get('status')!='RESOLVED'
                and x.get('severity') in {'HIGH','CRITICAL'} for p in x.get('passage_ids',[])}
    sources={p['passage_id']:p['text'] for p in mapping['passages']}
    for item in dispositions:
        if not isinstance(item,dict):fail('M7_BAD_DISPOSITION',None,'Not an object');continue
        ident=item.get('occurrence_id')
        if ident not in ids:
            fail('M7_UNISSUED_OCCURRENCE_ID',ident,'Unknown or model-invented occurrence ID');continue
        if ident in seen:fail('M7_DUPLICATE_OCCURRENCE',ident,'Occurrence classified more than once');continue
        seen[ident]=item
        hit=ids[ident];cls=item.get('classification');term=item.get('term_id');payment=item.get('payment_id')
        if cls not in CHOICES:fail('M7_BAD_CLASSIFICATION',ident,'Unsupported occurrence classification')
        rationale=item.get('rationale')
        if not isinstance(rationale,str) or len(rationale.strip())<12:
            fail('M7_RATIONALE_REQUIRED',ident,'Explain disposition with at least 12 characters')
        if cls=='UNRESOLVED' and hit['passage_id'] not in issues:
            fail('M7_UNRESOLVED_WITHOUT_ISSUE',ident,'Unresolved requires HIGH/CRITICAL open issue linked to passage')
        if cls=='ROYALTY_RATE':
            if term not in terms:
                fail('M7_RATE_TERM_MISSING',ident,'Rate must link to a valid extracted term')
            elif hit['kind'] not in {'PERCENT','SPELLED_RATE','SPELLED_FRACTION','PER_UNIT_SIGNAL'}:
                fail('M7_RATE_WRONG_SOURCE_KIND',ident,'Royalty rate classification needs a rate-related occurrence')
            elif hit['kind'] == 'PERCENT' and (hit['normalized'] is None or not _linked_percent(extraction,hit['passage_id'],number(hit['normalized']))):
                fail('M7_RATE_NOT_EVIDENCED',ident,'Rate must be represented with linked source evidence')
            else:
                t=terms[term];rate_values=[t.get('rate_value')]+[z.get('rate_value') for z in t.get('tiers',[]) if isinstance(z,dict)]
                if not term_cites(t,hit['passage_id']):
                    fail('M7_RATE_TERM_SOURCE_MISMATCH',ident,'Rate term must cite the original occurrence passage')
                if hit['kind']=='PERCENT' and number(hit['normalized']) not in [number(x) for x in rate_values]:
                    fail('M7_WRONG_TERM_RATE',ident,'Rate must appear in the specifically linked term')
        if cls in {'CONDITION','THRESHOLD'}:
            nonrate=_nonroyalty_context(sources.get(hit['passage_id'],''))
            linked_term=term in terms and term_cites(terms[term],hit['passage_id'])
            linked_payment=payment in payments and cites(hit['passage_id'],payments[payment].get('evidence_ids'))
            contractual_condition=(hit['risk']=='INVENTORY_ONLY' and
                re.search(r'\b(?:termination for breach|material breach|failure to cure|undisputed (?:portion|amount))\b',
                          sources.get(hit['passage_id'],''),re.I) and
                not re.search(r'\broyalt(?:y|ies)\s+(?:of|at)\b|\bof\s+net\s+sales\b',sources.get(hit['passage_id'],''),re.I))
            if not (linked_term or linked_payment or nonrate or contractual_condition):
                fail('M7_ECONOMIC_CONDITION_UNLINKED',ident,
                     'Condition/threshold must cite a term, payment, or explicit non-royalty source context')
            if hit['kind']=='MONEY' and not nonrate:
                amt=number(hit['normalized'])
                represented=_linked_amount(extraction,hit['passage_id'],amt)
                if linked_term and not represented:
                    represented=any((cites(hit['passage_id'],tier.get('threshold_evidence_ids')) or
                        cites(hit['passage_id'],tier.get('evidence_ids'))) and
                        amt in [number(_plain_number(tier.get('lower'))),
                                number(_plain_number(tier.get('upper')))]
                        for tier in terms[term].get('tiers',[]) if isinstance(tier,dict))
                if not represented:
                    fail('M7_CONDITION_SOURCE_UNLINKED',ident,
                         'Money threshold/condition lacks a source-linked record with the same amount')
        if cls=='OTHER_PAYMENT':
            if payment not in payments:
                fail('M7_PAYMENT_ID_MISSING',ident,'Payment classification requires a linked payment record')
            elif hit['kind']=='MONEY' and not _linked_amount(extraction,hit['passage_id'],number(hit['normalized'])):
                fail('M7_PAYMENT_NOT_EVIDENCED',ident,'Amount not linked to source payment evidence')
        if cls=='ADJUSTMENT':
            nonrate=_nonroyalty_context(sources.get(hit['passage_id'],''))
            payment_formula=(payment in payments and
                cites(hit['passage_id'],payments[payment].get('evidence_ids')) and
                (nonrate or (payments[payment].get('kind') in {'MILESTONE','UPFRONT','OTHER'} and
                 re.search(r'\b(?:milestone|IPO|shares?|stockholders?|merger|acquisition)\b',
                           sources.get(hit['passage_id'],''),re.I))))
            if term not in terms and not payment_formula:
                fail('M7_ADJUSTMENT_TERM_MISSING',ident,'Economic rate adjustment requires a term; non-royalty interest may cite its payment')
            elif term in terms and hit['kind']=='PERCENT' and not nonrate:
                if not (_linked_percent(extraction,hit['passage_id'],number(hit['normalized'])) or
                        term_cites(terms[term],hit['passage_id'])):
                    fail('M7_ADJUSTMENT_NOT_EVIDENCED',ident,'Rate change not source-linked to the term')
        if hit['risk'] in HIGH_RISKS:
            text=sources.get(hit['passage_id'],'')
            nonrate=_nonroyalty_context(text)
            conditional=cls in {'CONDITION','THRESHOLD'} and term in terms and term_cites(terms[term],hit['passage_id'])
            payment_cited=payment in payments and cites(hit['passage_id'],payments[payment].get('evidence_ids'))
            if cls in {'NON_ROYALTY','UNRESOLVED'}:
                # A real payment deliberately categorized as non-running-royalty
                # remains source-accounted. An unlinked dismissal never does.
                if cls=='NON_ROYALTY' and not (nonrate or payment_cited):
                    fail('M7_HIGH_RISK_DISMISSAL',ident,
                        'Potential economic obligation dismissed without a supported payment or source exception')
            if hit['risk'] in {'POTENTIAL_RUNNING_RATE','POTENTIAL_SPELLED_RATE'}:
                if cls not in {'ROYALTY_RATE','ADJUSTMENT','UNRESOLVED'} and not (
                        conditional or nonrate or (cls=='UNRESOLVED' and hit['passage_id'] in issues)):
                    fail('M7_RATE_RISK_CLASSIFICATION',ident,
                        'Source suggests a rate but no source-supported royalty, condition or exception')
            if hit['risk']=='POTENTIAL_MINIMUM_OR_CAP' and cls not in {
                    'OTHER_PAYMENT','CONDITION','ADJUSTMENT','THRESHOLD','UNRESOLVED'}:
                if not (payment_cited or (cls=='UNRESOLVED' and hit['passage_id'] in issues)):
                    fail('M7_AMOUNT_RISK_CLASSIFICATION',ident,
                         'Potential minimum/cap lacks supported payment or adjustment')
            if hit['risk']=='POTENTIAL_INDIRECT_PAYMENT' and cls not in {
                    'ROYALTY_RATE','ADJUSTMENT','OTHER_PAYMENT','THRESHOLD','CONDITION','UNRESOLVED'}:
                if not (payment_cited or nonrate or (cls=='UNRESOLVED' and hit['passage_id'] in issues)):
                    fail('M7_INDIRECT_PAYMENT_UNACCOUNTED',ident,
                         'Indirect payment has no supported record or source exception')
            if hit['risk']=='POTENTIAL_REDACTED_ECONOMICS' and cls not in {'REDACTION','UNRESOLVED'}:
                if hit['passage_id'] not in issues and not payment_cited:
                    fail('M7_REDACTION_RISK_CLASSIFICATION',ident,
                         'Redacted economics must be preserved in a record or unresolved issue')
    missing=set(ids)-set(seen)
    if missing:fail('M7_OCCURRENCE_COVERAGE_INCOMPLETE',sorted(missing)[:12],f'{len(missing)} source-issued occurrences unclassified')
    # High-risk classification can still be a semantic false positive; accuracy awaits live benchmark.
    if any(x['kind']=='SPELLED_FRACTION' for x in manifest['occurrences']):
        warnings.append({'code':'SPELLED_RATE_SEMANTIC_CHECK','message':'Written fractions require interpretation, not numerical matching'})
    return {'schema':'m7-occurrence-qc.1', 'document_id':mapping['document_id'],
        'manifest_sha256':manifest['manifest_sha256'], 'source_occurrences':len(ids),
        'classified':len(seen), 'unclassified':len(missing),'errors':errors,'warnings':warnings,
        'deterministic_status':'PASS_DETERMINISTIC_ONLY' if not errors else 'FAIL'}
