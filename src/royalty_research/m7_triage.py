"""Deterministic, explainable *priority* and compact source reading packs.

A low priority is NOT a statement that no license exists. Every source remains
in the durable inventory for alternate discovery, sampling or later reading.
The headline cost estimate is character-based, not observed model token usage.
"""
from __future__ import annotations

import re
from collections import Counter
from .mapping import PERCENT, MONEY, CROSSREF
from .m2_packets import deterministic_unflagged_sample
from .m7_occurrences import issue_occurrences
from .storage import sha256, json_bytes

IP = re.compile(r'\b(?:patent(?:s|ed)?|trademark(?:s)?|trade\s*mark|copyright|software|source\s+code|know[- ]how|technology|technologies|intellectual\s+property|brand(?:\s+name)?|franchis(?:e|ing)|licen[sc](?:e|ing)\s+agreement|exclusive\s+licen[sc]e|field\s+of\s+use)\b',re.I)
ROYALTY = re.compile(r'\b(?:royalt(?:y|ies)|sublicen[sc](?:e|ing)|net\s+sales|revenue\s+shar(?:e|ing)|profit\s+participation|licen[sc](?:e|ing)\s+fee|per[- ]unit\s+fee|milestone\s+payment|minimum\s+annual\s+payment)\b',re.I)
OBLIGATION = re.compile(r'\b(?:shall|must|agrees?\s+to|pay(?:able|ment|s)?|remit|subject\s+to|in\s+consideration|receive|entitled\s+to|calculated|based\s+on|equal\s+to)\b',re.I)
MINERAL = re.compile(r'\b(?:mineral\s+interests?|oil\s+and\s+gas|mining\s+claim|overriding\s+royalt(?:y|ies)|working\s+interest|hydrocarbon|royalty\s+acre|petroleum\s+lease)\b',re.I)
BOILER = re.compile(r'\b(?:executive\s+employment|severance|audit\s+fees?|leasehold|insurance|tax\s+receivable|debt\s+indenture|stock\s+option|restricted\s+stock|service\s+agreement)\b',re.I)


def passage_score(passage):
    """Explainable tier scoring; never automatically removes source passages."""
    text=passage['text']; reasons=[];score=0
    if ROYALTY.search(text):score+=5;reasons.append('PAYMENT_OR_ROYALTY_VOCAB')
    if IP.search(text):score+=3;reasons.append('LICENSED_IP_VOCAB')
    if OBLIGATION.search(text):score+=2;reasons.append('PAYMENT_OBLIGATION_VOCAB')
    if PERCENT.search(text) or MONEY.search(text):score+=1;reasons.append('NUMERIC_ECONOMICS')
    if ROYALTY.search(text) and (PERCENT.search(text) or MONEY.search(text)):
        score+=5;reasons.append('ECONOMIC_VALUE_NEAR_ROYALTY')
    if MINERAL.search(text):score-=4;reasons.append('POSSIBLE_NON_IP_MINERAL')
    return score,reasons


def triage_document(mapping):
    from .mapping import validate_map
    errors=validate_map(mapping)
    if errors:raise ValueError('Invalid map: '+', '.join(errors))
    scored=[(p, *passage_score(p)) for p in mapping['passages']]
    text_head=' '.join(p['text'][:1500] for p in mapping['passages'][:4])
    high=sum(score>=9 for _,score,_ in scored)
    mid=sum(4<=score<9 for _,score,_ in scored)
    has_ip=any(IP.search(p['text']) for p in mapping['passages'])
    has_royalty=any(ROYALTY.search(p['text']) for p in mapping['passages'])
    mineral=bool(MINERAL.search(text_head))
    boiler=bool(BOILER.search(text_head))
    if high and has_ip and not (mineral and not IP.search(text_head)):
        priority='HIGH_VALUE_FULL_EXTRACTION'
    elif high or (has_ip and has_royalty):
        priority='MEDIUM_VERIFY_IP_SCOPE'
    else:
        priority='LOW_SIGNAL_REQUIRES_TRIAGE_OR_SAMPLING'
    if mineral and not IP.search(text_head):
        priority='MINERAL_ROYALTY_CHECK_IP_SCOPE'
    return {'schema':'m7-triage.1','document_id':mapping['document_id'],
        'source_text_sha256':mapping['text_sha256'],'priority':priority,
        'high_signal_passage_count':high,'medium_signal_passage_count':mid,
        'document_has_ip_vocab':has_ip,'document_has_royalty_vocab':has_royalty,
        'header_suggests_mineral_interest':mineral,'header_suggests_other_contract':boiler,
        'passage_scores':[{'passage_id':p['passage_id'],'score':s,'reasons':why} for p,s,why in scored],
        'notice':'Priority only; no automatic exclusion and not evidence of negative contract classification'}


def compact_packet(mapping, *, stage='focus', max_chars=22000, neighbor_radius=1, sample_fraction=.05):
    """Small diagnostic context pack with no false claim of contract completeness.

    Stage 'focus' selects strong signals, payment-linked definitions and nearby
    passages, including source-issued occurrence IDs. Stage 'remainder' reads ALL
    passages excluded from focus (deterministically), enabling complete coverage
    when two stages are run. Neither stage means the model actually read them.
    """
    if stage not in {'focus','remainder','full'}:raise ValueError('Invalid stage')
    if not isinstance(max_chars,int) or max_chars<2000:raise ValueError('max_chars too small')
    triage=triage_document(mapping)
    passages=mapping['passages']; all_ids=[p['passage_id'] for p in passages]; positions={pid:i for i,pid in enumerate(all_ids)}
    ranks={x['passage_id']:x['score'] for x in triage['passage_scores']}
    picked=set()
    for p in passages:
        if ranks[p['passage_id']]>=7 or (p['candidate_reasons'] and ranks[p['passage_id']]>=4):
            i=positions[p['passage_id']]
            picked.update(all_ids[max(0,i-neighbor_radius):min(len(all_ids),i+neighbor_radius+1)])
        # Keep dictionary / schedule references even without a numeric rate nearby.
        if any(k in p['candidate_reasons'] for k in ('DEFINED_TERM','SOURCE_SPLIT_ADJACENCY_REVIEW')):
            picked.add(p['passage_id'])
    picked.update(deterministic_unflagged_sample(mapping,minimum=2,fraction=sample_fraction))
    if stage=='remainder':picked=set(all_ids)-picked
    if stage=='full':picked=set(all_ids)
    picked_ids=[pid for pid in all_ids if pid in picked]
    manifest=issue_occurrences(mapping)
    hits_by_pid={}
    for h in manifest['occurrences']:hits_by_pid.setdefault(h['passage_id'],[]).append(h)
    chunks=[];current=[];size=0
    for p in passages:
        if p['passage_id'] not in picked:continue
        record={'id':p['passage_id'],'section':p['section_guess'], 'text':p['text'],
                'occurrence_ids':[h['id'] for h in hits_by_pid.get(p['passage_id'],[])]}
        envelope=len(p['text'])+len(p['passage_id'])+120+sum(len(x) for x in record['occurrence_ids'])
        if envelope>max_chars:raise ValueError('Oversized passage requires M1 exact segmentation: '+p['passage_id'])
        if current and size+envelope>max_chars:
            chunks.append(current);current=[];size=0
        current.append(record);size+=envelope
    if current:chunks.append(current)
    covered=[x['id'] for chunk in chunks for x in chunk]
    if covered!=picked_ids:raise AssertionError('Source passages lost from compact pack')
    full_original_chars=sum(len(p['text']) for p in passages)
    selected_chars=sum(len(p['text']) for p in passages if p['passage_id'] in picked)
    return {'schema':'m7-compact-packet.1','document_id':mapping['document_id'],
       'source_text_sha256':mapping['text_sha256'], 'manifest_sha256':manifest['manifest_sha256'],
       'stage':stage,'triage_priority':triage['priority'],'read_scope':'FOCUSED_ONLY_NOT_COMPLETE' if stage=='focus' else 'REMAINDER_NOT_COMPLETE' if stage=='remainder' else 'FULL_DOCUMENT_SUPPLIED_NOT_VERIFIED',
       'included_passage_ids':picked_ids,'excluded_passage_ids':[pid for pid in all_ids if pid not in picked],
       'all_candidate_ids':mapping['candidate_passages'],
       'all_occurrence_ids':[h['id'] for h in manifest['occurrences']],
       'selected_occurrences':[h for h in manifest['occurrences'] if h['passage_id'] in picked],
       'section_inventory':[{'section':x['section'],'passage_count':len(x['passage_ids'])} for x in mapping['sections']],
       'definitions':mapping.get('definitions',[]), 'cross_references':mapping.get('cross_references',[]),
       'chunks':[{'index':i+1,'count':len(chunks),'passages':c} for i,c in enumerate(chunks)],
       'character_budget_proxy':{'source_chars':full_original_chars,'selected_source_chars':selected_chars,
          'source_chars_avoided_in_this_stage':full_original_chars-selected_chars,
          'fraction_of_source_text':round(selected_chars/max(1,full_original_chars),3)},
       'warning':'A focused packet is NOT proof of full-document completeness. Process remainder or full-document verification before any completeness claim.'}
