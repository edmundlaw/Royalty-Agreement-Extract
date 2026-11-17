"""Candidate-clause inventory, without claiming semantic royalty extraction."""
from __future__ import annotations

import re
from collections import Counter

from typing import Iterable

from .__init__ import SCHEMA_VERSION
from .storage import sha256, stable_id, utc_now

# Broad by design: precision is not the target of M1 screening.
PERCENT = re.compile(r"(?<![\w\d])(?:\d+(?:\.\d+)?|\.\d+)\s*(?:%|percent\b|per\s+cent\b)", re.I)
MONEY = re.compile(r"(?<!\w)(?:US\s*\$|USD\s*|\$|€|£|¥|EUR\s*|GBP\s*|JPY\s*|HKD\s*|CAD\s*|AUD\s*)\s*\d[\d,]*(?:\.\d+)?", re.I)
FRACTION = re.compile(r"\b(?:one[- ]half|one[- ]quarter|one[- ]third|two[- ]thirds|three[- ]quarters|half\s+of\s+one\s+percent)\b", re.I)
REDACTION = re.compile(r"\b(?:redacted|confidential\s+treatment|omitted\s+and\s+filed|not\s+disclosed)\b|\[\s*\*{1,}\s*\]|\[\s*REDACTED\s*\]|(?<!\w)\*{4,}(?!\w)|\[\s*(?:\.{3,}|…+)\s*\]|[■█]{2,}", re.I)
PER_UNIT = re.compile(r"\b(?:per\s+(?:unit|device|product|copy|user|piece|transaction|download|sale)|cents?\s+for\s+each|a\s+unit\s+fee|in[- ]kind\s+(?:payments?|consideration))\b", re.I)
SPELLED_RATE = re.compile(r"\b(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|twenty[- ]five|thirty|forty|fifty|half|quarter|one[- ]twentieth|one[- ]hundredth)\s+(?:percent|per\s+cent)|\d+(?:\.\d+)?\s+(?:basis\s+points?|bps)\b|(?:share\s+equally|equal\s+shares?|split\s+equally|divided\s+equally))", re.I)
INDIRECT_ECONOMICS = re.compile(r"\b(?:most[- ]favou?r(?:ed)?|shall\s+be\s+(?:halved|reduced)|cost\s+plus|cost[- ]plus|markup|mark[- ]up|consideration\s+(?:as\s+)?(?:provided|specified|set\s+forth)\s+in|payment\s+(?:shall\s+be\s+)?(?:as\s+)?(?:provided|specified|set\s+forth)\s+in|side\s+letter|continuing\s+fees?|technical\s+service\s+charge|amount\s+in\s+words|each\s+party\s+shall\s+receive)\b",re.I)
FINANCE = re.compile(r"\b(?:royalt(?:y|ies)|licen[sc](?:e|ing)\s+fee|sublicen[sc](?:e|ing)|net\s+sales|gross\s+sales|revenue\s+shar(?:e|ing)|participation\s+fee|payment|fee\s+payable|milestone|minimum\s+guarantee|annual\s+minimum|earned\s+royalt|consideration|net\s+receipts|proceeds|payments?\s+due|threshold|patent\s+stacking|shall\s+(?:pay|remit|tender|reimburse|compensate)|profit\s+shar(?:e|ing)|remuneration|amounts?\s+payable|due\s+and\s+payable|guaranteed\s+consideration)\b", re.I)
CROSSREF = re.compile(r"\b(?:Section|Clause|Paragraph|Article|Schedule|Appendix|Exhibit|Annex|Attachment|Addendum)\s+[A-Z]?\d+(?:\.\d+)*\b|\b(?:Schedule|Appendix|Exhibit|Annex|Attachment|Addendum)\s+[A-Z]\b", re.I)
SECTION = re.compile(r"^\s*(?:(?:SECTION|Section|ARTICLE|Article|§)\s*)?(\d{1,2}(?:\.\d{1,3}){0,4})\s*[.\-)\s]+([A-Za-z][^\n]{0,150})")
HEADING = re.compile(r"^(?:ARTICLE|SECTION|SCHEDULE|APPENDIX|EXHIBIT)\s+[A-Z0-9IVX]+\b", re.I)
DEFINITION = re.compile(r"[\"“]([^\"”]{2,70})[\"”]\s+(?:shall\s+)?(?:mean|means|refer(?:s)?\s+to|is\s+defined\s+as)\b", re.I)


def _split_exact(value: str, limit: int) -> tuple[list[str], bool]:
    """Split one original normalized line without deleting or changing a character.

    Prefer whitespace near the target boundary; a forced cut is recorded so that
    later independent readers review both sides of the boundary. Nothing is
    silently truncated. The concatenation invariant is checked by the caller.
    """
    if len(value) <= limit:
        return [value], False
    result=[]
    remaining=value
    forced=False
    while len(remaining)>limit:
        left=max(1, int(limit * .70))
        position=max(remaining.rfind(' ',left,limit+1),remaining.rfind('\t',left,limit+1))
        if position <= 0:
            position=limit
            forced=True
        else:
            position+=1  # Keep separator in the preceding fragment exactly
        result.append(remaining[:position])
        remaining=remaining[position:]
    if remaining:
        result.append(remaining)
    if ''.join(result)!=value or not all(result):
        raise AssertionError('Segmentation must preserve every source character')
    return result,forced


def segment_source_paragraphs(paragraphs: list[str], limit: int) -> tuple[list[str], list[dict], set[int]]:
    """Return fragments, exact parent-span manifest and boundary-review flags.

    Segment positions refer to the resulting M1 numbered passage list. Legacy
    short lines are untouched. Fragment boundaries are not license to treat
    paragraphs as economically independent clauses.
    """
    if not isinstance(limit,int) or not 1000 <= limit <= 200000:
        raise ValueError('segment_chars must be an integer between 1000 and 200000')
    out=[];manifest=[]; flagged=set()
    for ordinal,value in enumerate(paragraphs,1):
        fragments,forced=_split_exact(value,limit)
        if len(fragments)>1:
            manifest.append({
                'original_paragraph_index':ordinal,
                'original_length':len(value),
                'original_sha256':sha256(value.encode('utf-8')),
                'fragment_indices':[len(out)+i+1 for i in range(len(fragments))],
                'fragment_lengths':[len(v) for v in fragments],
                'forced_boundary':forced,
                'review_warning':'Adjacent fragments of one original paragraph must be considered together'
            })
            flagged.update(range(len(out)+1,len(out)+len(fragments)+1))
        out.extend(fragments)
    return out,manifest,flagged


def map_contract(paragraphs: list[str], document: dict, *, raw_hash: str | None = None,
                 fetched_at: str | None = None, parser_type: str = "UNKNOWN",
                 segment_chars: int = 12000) -> dict:
    if not paragraphs:
        raise ValueError("Cannot map an empty document")
    paragraphs, segment_manifest, split_passages = segment_source_paragraphs(paragraphs, segment_chars)
    text = "\n".join(paragraphs)
    doc_id = document.get("document_id") or stable_id("DOC", document.get("source_url", ""))
    source = document.get("source_url")
    records = []
    candidates = []
    definitions = []
    references = []
    section_index: dict[str, dict] = {}
    current_section = None
    start = 0
    for i, value in enumerate(paragraphs, 1):
        passage_id = f"{doc_id}:P{i:06d}"
        match = SECTION.match(value)
        if match and (len(value) <= 300 or "royalt" in value.lower()):
            current_section = match.group(1)
        elif HEADING.match(value):
            current_section = value[:120]
        reasons = []
        for name, pattern in (("PERCENT", PERCENT), ("MONEY", MONEY), ("SPELLED_FRACTION", FRACTION),
                              ("SPELLED_RATE", SPELLED_RATE), ("INDIRECT_ECONOMICS", INDIRECT_ECONOMICS),
                              ("REDACTION", REDACTION), ("PER_UNIT", PER_UNIT), ("FINANCE_VOCAB", FINANCE)):
            if pattern.search(value):
                reasons.append(name)
        if i in split_passages:
            reasons.append('SOURCE_SPLIT_ADJACENCY_REVIEW')
        refs = list(dict.fromkeys(m.group(0) for m in CROSSREF.finditer(value)))
        defs = list(dict.fromkeys(m.group(1) for m in DEFINITION.finditer(value)))
        if refs:
            reasons.append("CROSS_REFERENCE")
            references.append({"passage_id": passage_id, "references": refs})
        if defs:
            reasons.append("DEFINED_TERM")
            for term in defs:
                definitions.append({"passage_id": passage_id, "term": term})
        # No model has interpreted any of these passages.
        r = {
            "passage_id": passage_id, "sequence": i, "section_guess": current_section,
            "start_offset": start, "end_offset": start + len(value),
            "text": value, "candidate_reasons": reasons,
            "review_disposition": "UNREVIEWED",
        }
        records.append(r)
        section_key = current_section or "PREAMBLE_OR_UNNUMBERED"
        if section_key not in section_index:
            section_index[section_key] = {"section": section_key, "passage_ids": [], "candidate_ids": []}
        section_index[section_key]["passage_ids"].append(passage_id)
        if reasons:
            candidates.append(passage_id)
            section_index[section_key]["candidate_ids"].append(passage_id)
        start += len(value) + 1
    signal_counts = Counter(s for p in records for s in p["candidate_reasons"])
    has_finance = signal_counts["FINANCE_VOCAB"] > 0
    has_economic_values = any(signal_counts[k] > 0 for k in ("PERCENT", "MONEY", "PER_UNIT", "REDACTION", "SPELLED_FRACTION", "SPELLED_RATE", "INDIRECT_ECONOMICS"))
    priority = ("HIGH_REVIEW_PRIORITY" if has_finance and has_economic_values else
                "MEDIUM_REVIEW_PRIORITY" if has_finance or has_economic_values else
                "LOW_SIGNAL_REVIEW_REQUIRED")
    return {
        "schema_version": SCHEMA_VERSION, "stage": "MAPPED_NOT_INTERPRETED",
        "document_id": doc_id, "source_url": source,
        "original_sha256": raw_hash, "text_sha256": sha256(text.encode("utf-8")),
        "mapped_at_utc": utc_now(), "retrieved_at_utc": fetched_at,
        "parser_type": parser_type,
        "source_segmentation": {"schema": "m4-source-segmentation.1",
                                "fragment_limit_chars": segment_chars,
                                "split_original_paragraphs": segment_manifest,
                                "preservation": "FRAGMENTS_CONCATENATE_EXACTLY_TO_EACH_ORIGINAL_NORMALIZED_LINE"},
        "total_passages": len(records), "candidate_passages": candidates,
        "total_candidates": len(candidates),
        "candidate_reason_counts": dict(signal_counts),
        "screening_priority": priority,
        "sections": list(section_index.values()),
        "definitions": definitions, "cross_references": references,
        "passages": records,
        "quality_flags": ["ALL_PASSAGES_UNREVIEWED", "CANDIDATE_COVERAGE_NOT_ESTABLISHED"],
        "screening_conclusion": "UNKNOWN_NEEDS_AI_SCREENING",
        "document_metadata": document,
    }


def validate_map(result: dict) -> list[str]:
    problems = []
    passages = result.get("passages") or []
    candidate_ids = result.get("candidate_passages") or []
    ids = [p.get("passage_id") for p in passages]
    if not passages or result.get("total_passages") != len(passages):
        problems.append("PASSAGE_COUNT_MISMATCH")
    if len(set(ids)) != len(ids):
        problems.append("DUPLICATE_PASSAGE_IDS")
    if result.get("total_candidates") != len(candidate_ids):
        problems.append("CANDIDATE_COUNT_MISMATCH")
    if set(candidate_ids) != {p["passage_id"] for p in passages if p.get("candidate_reasons")}:
        problems.append("CANDIDATE_COVERAGE_MISMATCH")
    offset = 0
    for p in passages:
        if p.get("start_offset") != offset or p.get("end_offset") != offset + len(p.get("text", "")):
            problems.append("OFFSET_INCONSISTENT")
            break
        offset += len(p["text"]) + 1
    if passages:
        text = "\n".join(p["text"] for p in passages)
        if result.get("text_sha256") != sha256(text.encode("utf-8")):
            problems.append("TEXT_HASH_MISMATCH")
    seg = result.get('source_segmentation')
    if seg is not None:
        if seg.get('schema') != 'm4-source-segmentation.1':
            problems.append('SEGMENT_SCHEMA_INVALID')
        declared_indices=[]
        previous_parent=0
        extra_passages=0
        for item in seg.get('split_original_paragraphs',[]):
            try:
                indexes=item['fragment_indices']; lengths=item['fragment_lengths']
                values=[passages[ix-1]['text'] for ix in indexes]
                exact=''.join(values)
                parent=item['original_paragraph_index']
                # Each prior split adds (fragment count - 1) to passage ordinals.
                valid_origin=(isinstance(parent,int) and parent>previous_parent and
                              indexes[0]==parent+extra_passages)
                if (len(indexes)<2 or indexes!=list(range(indexes[0],indexes[-1]+1))
                    or lengths!=[len(v) for v in values] or len(exact)!=item['original_length']
                    or sha256(exact.encode('utf-8'))!=item['original_sha256'] or not valid_origin
                    or any('SOURCE_SPLIT_ADJACENCY_REVIEW' not in passages[ix-1].get('candidate_reasons',[]) for ix in indexes)):
                    problems.append('SEGMENT_SOURCE_PRESERVATION_FAILED')
                declared_indices.extend(indexes)
                previous_parent=parent
                extra_passages+=len(indexes)-1
            except (ValueError, KeyError, IndexError, TypeError):
                problems.append('SEGMENT_MANIFEST_INVALID')
        observed_indices=[ix for ix,p in enumerate(passages,1)
                          if 'SOURCE_SPLIT_ADJACENCY_REVIEW' in p.get('candidate_reasons',[])]
        if sorted(declared_indices)!=observed_indices or len(declared_indices)!=len(set(declared_indices)):
            problems.append('SEGMENT_MANIFEST_COVERAGE_MISMATCH')
    if result.get("stage") != "MAPPED_NOT_INTERPRETED":
        problems.append("WRONG_STAGE")
    sections = result.get("sections") or []
    assigned = [pid for sec in sections for pid in sec.get("passage_ids", [])]
    if len(assigned) != len(ids) or set(assigned) != set(ids):
        problems.append("SECTION_PASSAGE_COVERAGE_MISMATCH")
    section_candidates = [pid for sec in sections for pid in sec.get("candidate_ids", [])]
    if sorted(section_candidates) != sorted(candidate_ids):
        problems.append("SECTION_CANDIDATE_COVERAGE_MISMATCH")
    return problems
