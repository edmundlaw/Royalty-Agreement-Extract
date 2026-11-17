"""Optional, independent benchmark comparison for M8.

This is an offline measurement against a supplied reference set, NOT an
assertion that AI-generated reference labels are true.  No human sign-off is
required for Excel publication. Benchmark provenance remains explicit.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from .storage import json_bytes, sha256

SCHEMA='m8-gold.1'


def _decimal(value):
    if value is None: return None
    if isinstance(value, bool): raise ValueError('Boolean rate is invalid')
    try: return str(Decimal(str(value)).normalize())
    except (InvalidOperation,TypeError): raise ValueError('Invalid benchmark rate: '+str(value))


def extraction_observations(extraction):
    """Flatten percentage tiers without collapsing multiple independent terms.

    IDs remain for diagnosis, never for cross-provider matching.
    Conditions/bases are deliberately compared strictly; this is a regression
    comparator, not a legal-semantic matcher.
    """
    result=[]
    for t in extraction.get('royalty_terms',[]):
        if not isinstance(t,dict): continue
        shared={
            'family':str(t.get('family') or '').strip().upper(),
            'base':str(t.get('base') or '').strip().casefold(),
            'product_scope':str(t.get('product_scope') or '').strip().casefold(),
            'effective_period':str(t.get('effective_period') or '').strip().casefold(),
            'disclosure_status':str(t.get('disclosure_status') or '').strip().upper(),
        }
        tiers=t.get('tiers') or []
        if tiers:
            for tier in tiers:
                result.append({**shared,'kind':'ROYALTY_TIER','rate_value':_decimal(tier.get('rate_value')),
                    'rate_unit':str(tier.get('rate_unit') or t.get('rate_unit') or '').upper(),
                    'lower':_decimal(tier.get('lower')),'upper':_decimal(tier.get('upper')),
                    'calculation':str(tier.get('calculation') or '').upper(),
                    'term_id':t.get('term_id'),'sequence':tier.get('sequence')})
        else:
            result.append({**shared,'kind':'ROYALTY_TERM','rate_value':_decimal(t.get('rate_value')),
                'rate_unit':str(t.get('rate_unit') or '').upper(),
                'lower':None,'upper':None,'calculation':'',
                'term_id':t.get('term_id'),'sequence':None})
    return result


_FIELDS=('kind','family','base','product_scope','effective_period','disclosure_status',
         'rate_value','rate_unit','lower','upper','calculation')

def _signature(item,fields=_FIELDS):
    numeric={'rate_value','lower','upper'}
    categorical={'kind','family','disclosure_status','rate_unit','calculation'}
    result=[]
    for k in fields:
        value=item.get(k)
        if k in numeric:value=_decimal(value)
        elif k in categorical:value=str(value or '').strip().upper()
        else:value=str(value or '').strip().casefold()
        result.append(value)
    return tuple(result)


def compare_to_reference(reference,extraction):
    """Exact semantic-field signature: intentionally conservative and explainable.

    A difference in free-text basis/scope is a *potential* error requiring
    independent analysis; report it rather than declaring contract meaning.
    """
    if reference.get('schema')!=SCHEMA:raise ValueError('Unknown benchmark reference schema')
    if reference.get('document_id')!=extraction.get('document_id'):
        raise ValueError('Reference/extraction document mismatch')
    if reference.get('source_text_sha256')!=extraction.get('source_text_sha256'):
        raise ValueError('Reference/extraction source mismatch')
    if not reference.get('reference_provenance') or not reference.get('complete_source_checked') in (True, False):
        raise ValueError('Reference provenance and complete-source-check declaration required')
    expected=reference.get('observations')
    if not isinstance(expected,list):raise ValueError('Reference observations must be an array')
    for item in expected:
        if not isinstance(item,dict) or set(_FIELDS)-set(item):raise ValueError('Reference fields incomplete')
    actual=extraction_observations(extraction)
    # Multiset arithmetic prevents an extraction with one rate from fulfilling
    # two distinct contractual occurrences with identical economics.
    want=Counter(_signature(x) for x in expected)
    got=Counter(_signature(x) for x in actual)
    matched=want & got
    missed=want-matched; extra=got-matched
    def describe(counter):
        return [{**dict(zip(_FIELDS,key)),'count':count} for key,count in sorted(counter.items(),key=lambda kv:str(kv[0]))]
    return {'schema':'m8-benchmark-result.1','document_id':extraction['document_id'],
        'source_text_sha256':extraction['source_text_sha256'],
        'reference_sha256':sha256(json_bytes(reference)),
        'reference_provenance':reference['reference_provenance'],
        'reference_complete_source_checked':reference['complete_source_checked'],
        'reference_is_independently_verified':bool(reference.get('independently_verified',False)),
        'reference_count':sum(want.values()),'extraction_count':sum(got.values()),
        'matched_count':sum(matched.values()),'missed_count':sum(missed.values()),
        'extra_count':sum(extra.values()),
        'complete_record':not missed and not extra,
        'missed_observations':describe(missed),'extra_observations':describe(extra),
        'limitation':'Strict text matching flags possible field differences; not an independent legal truth test.'}


def aggregate(results):
    if not results:raise ValueError('At least one benchmark result needed')
    if len({x['document_id'] for x in results})!=len(results):raise ValueError('Duplicate benchmark document')
    r=sum(x['reference_count'] for x in results)
    e=sum(x['extraction_count'] for x in results)
    m=sum(x['matched_count'] for x in results)
    all_verified=all(x['reference_is_independently_verified'] and x['reference_complete_source_checked'] for x in results)
    return {'schema':'m8-benchmark-summary.1','agreements':len(results),
        'complete_records':sum(bool(x['complete_record']) for x in results),
        'reference_observations':r,'extracted_observations':e,'exact_field_matches':m,
        'strict_precision_proxy':round(m/e,5) if e else None,
        'strict_recall_proxy':round(m/r,5) if r else None,
        'measured_accuracy_claim_permitted':False,
        'all_reference_provenance_verified':all_verified,
        'notice':'These are strict field-agreement proxies against user-supplied references, not statistical royalty recall or audit certification.'}
