"""Merge bounded M2 reading chunks without declaring completeness by fiat.

Every chunk must be present, source-bound, disjoint and claim exactly its
assigned passage IDs. Collision of locally named evidence/terms is fatal: the
agent must use globally unique IDs and/or a further explicit reconciliation.
"""
from __future__ import annotations

from .storage import json_bytes, sha256, stable_id
from .mapping import validate_map
from .m2_validation import validate_extraction
from .m2_schema_check import schema as _m2_schema

CHUNK_SCHEMA = "m3-chunk.1"


def agreement_scalar_fields():
    """Every agreement field the bundled schema allows, except the two that are merged as collections.

    Derived from the schema (v0.13.7) so a field added there can never again be rejected by the
    merge ("Bad agreement evidence" on related_party / licensed_ip_nature_basis in the live run).
    """
    props=_m2_schema()["$defs"]["agreement"]["properties"]
    return tuple(k for k in props if k not in ("field_evidence","other_material_terms"))


def merge_chunks(mapping: dict, packet: dict, chunk_outputs: list[dict]):
    problems = validate_map(mapping)
    if problems: raise ValueError("Source map invalid: " + str(problems))
    if (packet.get("packet_schema") != "m2-packet.1" or packet.get("document_id") != mapping["document_id"] or
        packet.get("source_text_sha256") != mapping["text_sha256"] or packet.get("mode") not in {"selected","full"}):
        raise ValueError("Packet belongs to a different map or is unsupported")
    chunks = packet.get("chunks", [])
    if not chunks or sorted(x.get("chunk_index") for x in chunks) != list(range(1,len(chunks)+1)):
        raise ValueError("Packet chunks incomplete or malformed")
    for x in chunks:
        if x.get("chunk_count")!=len(chunks):raise ValueError("Packet chunk_count mismatch")
    flat = [p["passage_id"] for chunk in chunks for p in chunk["passages"]]
    included = packet.get("included_passage_ids",[])
    all_ids = [p["passage_id"] for p in mapping["passages"]]
    source_passages={p["passage_id"]:p for p in mapping["passages"]}
    for chunk in chunks:
        for obj in chunk["passages"]:
            original=source_passages.get(obj.get("passage_id"))
            if original is None or any(obj.get(k)!=expected for k,expected in (
                ("text",original["text"]),("section",original["section_guess"]),
                ("candidate_reasons",original["candidate_reasons"]))):
                raise ValueError("Packet passage text/metadata differs from authoritative source map")
    if (packet.get("candidate_passage_ids")!=mapping["candidate_passages"] or
        packet.get("excluded_passage_ids")!=[pid for pid in all_ids if pid not in flat] or
        packet.get("definitions")!=mapping.get("definitions",[]) or
        packet.get("cross_references")!=mapping.get("cross_references",[])):
        raise ValueError("Packet inventory or definitions differ from source map")
    if flat != included or len(set(flat))!=len(flat):
        raise ValueError("Packet must preserve exact, unique passage order")
    if not set(mapping["candidate_passages"]).issubset(flat):
        raise ValueError("Packet silently excluded candidate passages")
    if packet["mode"]=="full" and flat!=all_ids:
        raise ValueError("Full packet omitted source passages")
    if len(chunk_outputs)!=len(chunks):
        raise ValueError("Cannot merge partial run: missing chunk outputs")
    by_ix={}
    for item in chunk_outputs:
        if item.get("schema") != CHUNK_SCHEMA: raise ValueError("Unsupported chunk output schema")
        idx=item.get("chunk_index")
        if type(idx) is not int or idx in by_ix or idx not in range(1,len(chunks)+1):
            raise ValueError("Duplicate, out-of-range or missing chunk index")
        if item.get("chunk_count") != len(chunks):raise ValueError("Chunk count mismatch")
        if item.get("document_id") != mapping["document_id"] or item.get("source_text_sha256") != mapping["text_sha256"]:
            raise ValueError("Chunk source binding mismatch")
        if item.get("packet_sha256") != sha256(json_bytes(packet)):
            raise ValueError("Chunk packet fingerprint stale/mismatched")
        desired=[p["passage_id"] for p in chunks[idx-1]["passages"]]
        if item.get("reviewed_passage_ids")!=desired:
            raise ValueError("Chunk read ledger does not match assigned passage IDs")
        if not isinstance(item.get("reader"),dict) or not all(item["reader"].get(k) for k in ("engine","model","run_id")):
            raise ValueError("Missing reader provenance")
        for arr in ("evidence","royalty_terms","other_payments","dispositions","open_issues"):
            if not isinstance(item.get(arr),list):raise ValueError(f"Chunk {idx}: {arr} must be a list")
        # Source evidence can only reference text within THIS chunk. Cross-chunk
        # term dependencies are permitted but require a subsequent semantic review.
        wanted=set(desired)
        if any(e.get("passage_id") not in wanted for e in item["evidence"]):
            raise ValueError("Evidence points to a passage not read in its own chunk")
        if any(d.get("passage_id") not in wanted for d in item["dispositions"]):
            raise ValueError("Disposition points outside assigned chunk")
        if item.get("amendment_status") not in {"NOT_CHECKED","NONE_IDENTIFIED_IN_DOCUMENT","REFERENCED_UNRESOLVED","REVIEWED_WITH_LINKED_DOCUMENTS"}:
            raise ValueError("Bad amendment status")
        by_ix[idx]=item
    ordered=[by_ix[i] for i in range(1,len(chunks)+1)]
    engines={(x["reader"]["engine"],x["reader"]["model"]) for x in ordered}
    if len(engines)!=1:raise ValueError("Cross-model chunk merges require a separate review stage")
    chunks_merged={key:[] for key in ("evidence","royalty_terms","other_payments","dispositions","open_issues")}
    for x in ordered:
        for name in chunks_merged:chunks_merged[name].extend(x[name])
    for kind,key in (("evidence","evidence_id"),("royalty_terms","term_id"),
                     ("other_payments","payment_id"),("dispositions","passage_id"),
                     ("open_issues","issue_id")):
        ids=[r.get(key) for r in chunks_merged[kind]]
        if any(not isinstance(v,str) or not v for v in ids) or len(ids)!=len(set(ids)):
            raise ValueError(f"Cross-chunk duplicate or missing {key}. Do not silently merge economic terms")
    base_fields=agreement_scalar_fields()
    agreement={key:None for key in base_fields}; agreement["field_evidence"]={}; agreement["other_material_terms"]=[]
    header_conflicts=[]; unbound_material_refs=[]; kept_from={}
    known_evidence_ids={e["evidence_id"] for e in chunks_merged["evidence"]}
    for part in ordered:
        part_agreement=part.get("agreement") or {}
        for k in base_fields:
            value=part_agreement.get(k)
            if value is None:continue
            if isinstance(value,list):
                # List-valued agreement fields (licensed_ip_components) are the union over the reading tasks.
                agreement[k]=(agreement[k] or [])+[x for x in value if x not in (agreement[k] or [])]
                continue
            if agreement[k] is not None and agreement[k]!=value:
                # RF-07 (v0.8.1-review): two reading tasks describe the same party or date in
                # different words (live NeurogesX run: "NeuroGesX, Inc." vs "NeurogesX, Inc."),
                # which v0.8.0 treated as fatal and so stranded every captured task of a
                # multi-task agreement. Keep the first task's value and record the difference
                # as a visible open issue instead of refusing to merge.
                header_conflicts.append((k,agreement[k],value,part.get("chunk_index"),kept_from.get(k)))
                continue
            agreement[k]=value; kept_from.setdefault(k,part.get("chunk_index"))
        for material in (part_agreement.get("other_material_terms") or []):
            if material not in agreement["other_material_terms"]: agreement["other_material_terms"].append(material)
        for k,refs in (part_agreement.get("field_evidence") or {}).items():
            if k == "other_material_terms" and isinstance(refs,list):
                # Individual terms retain their own links. General references that
                # are not linked to a term need review, not an invented association.
                if any(not isinstance(eid,str) or not eid or eid not in known_evidence_ids for eid in refs):
                    raise ValueError("Bad agreement evidence")
                material_refs={eid for item in (part_agreement.get("other_material_terms") or [])
                               for eid in item.get("evidence_ids",[])}
                extra=list(dict.fromkeys(eid for eid in refs if eid not in material_refs))
                if extra: unbound_material_refs.append((part["chunk_index"],extra))
                continue
            if k not in base_fields or not isinstance(refs,list):raise ValueError("Bad agreement evidence")
            agreement["field_evidence"].setdefault(k,[])
            for r in refs:
                if r not in agreement["field_evidence"][k]:agreement["field_evidence"][k].append(r)
    amendment_values={p["amendment_status"] for p in ordered}
    if len(amendment_values)==1:amendment_status=next(iter(amendment_values))
    elif "REFERENCED_UNRESOLVED" in amendment_values:amendment_status="REFERENCED_UNRESOLVED"
    else:amendment_status="NOT_CHECKED"
    output={
        "schema_version":"m2.0", "document_id":mapping["document_id"],
        "source_text_sha256":mapping["text_sha256"],"source_url":mapping.get("source_url"),
        "reader":{"engine":ordered[0]["reader"]["engine"],"model":ordered[0]["reader"]["model"],
                  "run_id":stable_id("MERGE",*[p["reader"]["run_id"] for p in ordered]),
                  "read_scope":"FULL_DOCUMENT" if packet["mode"]=="full" else "SELECTED_PASSAGES",
                  "reviewed_passage_ids":flat},
        "agreement":agreement, "amendment_status":amendment_status, **chunks_merged,
    }
    for field,kept,other,idx,kept_idx in header_conflicts:
        output["open_issues"]=list(output.get("open_issues",[]))+[{
            "issue_id":stable_id("ISSUE-MERGE","AGREEMENT_HEADER",field,str(idx)),
            "severity":"MEDIUM","status":"OPEN","kind":"AGREEMENT_HEADER_DIFFERS_ACROSS_AI_TASKS",
            "description":(f"Agreement field '{field}' was worded differently by two reading tasks. "
                           f"Kept (task {kept_idx}, the first to give a value): {kept!r}. Task {idx} gave: {other!r}."),
            "passage_ids":[]}]
    for idx,refs in unbound_material_refs:
        output["open_issues"].append({
            "issue_id":stable_id("ISSUE-MERGE","UNBOUND_MATERIAL_EVIDENCE",str(idx)),
            "severity":"MEDIUM","status":"OPEN","kind":"UNBOUND_MATERIAL_TERM_EVIDENCE",
            "description":(f"Task {idx} listed general material-term evidence not linked to an "
                           f"individual term: {', '.join(refs)}. Review its relevance and association."),
            "passage_ids":list(dict.fromkeys(e["passage_id"] for e in chunks_merged["evidence"]
                                             if e["evidence_id"] in refs))})
    qc=validate_extraction(mapping,output)
    report={"schema":"m3-chunk-merge.1", "document_id":mapping["document_id"],
            "packet_sha256":sha256(json_bytes(packet)),
            "source_sha256":mapping["text_sha256"], "chunks":len(chunks),
            "chunk_sha256":[sha256(json_bytes(p)) for p in ordered],
            "deterministic_status":qc["deterministic_status"],"qc_errors":qc["errors"],
            "qc_warnings":qc["warnings"],
            "notice":"All chunks accounted for by ID only. Cross-chunk contractual meaning and actual reading are NOT independently established."}
    return output,report
