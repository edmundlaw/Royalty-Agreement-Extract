"""Explicit, source-aware agreement grouping and amendment links.

Never deduplicate by the parties' names or silently convert a filing into the
'currently effective' contract. Unlinked documents remain provisional.
"""
from __future__ import annotations

from datetime import date
from .storage import stable_id

LINK_SCHEMA="m3-linkage.1"
AMENDMENT_TYPES={"AMENDS","RESTATES","SUPERSEDES","RELATED_EXHIBIT","EXACT_DUPLICATE_FILING"}

def validate_linkage(linkage: dict, docs: list[dict]):
    doc_ids={d["document_id"] for d in docs}
    if not isinstance(linkage,dict) or linkage.get("schema")!=LINK_SCHEMA:
        raise ValueError("Linkage must specify m3-linkage.1")
    groups=linkage.get("groups",[])
    edges=linkage.get("relations",[])
    if not isinstance(groups,list) or not isinstance(edges,list):raise ValueError("groups/relations must be lists")
    grouped={};group_ids=set()
    for g in groups:
        gid=g.get("agreement_id")
        if not isinstance(gid,str) or not gid.startswith("AGR-") or gid in group_ids:
            raise ValueError("Duplicate/invalid agreement_id")
        group_ids.add(gid)
        if g.get("status") not in {"AI_PROPOSED","HUMAN_CONFIRMED","SOURCE_EVIDENCED"}:
            raise ValueError("Group status must be explicit")
        members=g.get("document_ids")
        if not isinstance(members,list) or not members:
            raise ValueError("Empty agreement group")
        if len(members)!=len(set(members)):
            raise ValueError("Repeated document in group")
        for doc_id in members:
            if doc_id not in doc_ids:raise ValueError("Linkage references unknown document")
            if doc_id in grouped:raise ValueError("Document assigned to multiple agreements")
            grouped[doc_id]=g
    graph={k:set() for k in doc_ids}
    used=set()
    for e in edges:
        a,b=e.get("from_document"),e.get("to_document")
        if a not in doc_ids or b not in doc_ids or a==b:
            raise ValueError("Amendment relation references missing or identical document")
        if e.get("relation") not in AMENDMENT_TYPES:raise ValueError("Unknown relation type")
        if not isinstance(e.get("basis"),str) or len(e["basis"].strip())<12:
            raise ValueError("Relation must have a substantive basis/explanation")
        if e.get("review_status") not in {"AI_PROPOSED","HUMAN_CONFIRMED","SOURCE_EVIDENCED"}:
            raise ValueError("Relation review status required")
        effective=e.get("effective_date")
        if effective is not None:
            try:date.fromisoformat(effective)
            except (ValueError,TypeError) as exc:raise ValueError("Invalid relation effective date") from exc
        if e.get("supersession_scope") not in {"NONE","SOME_TERMS","ALL_TERMS","UNKNOWN"}:
            raise ValueError("Explicit supersession_scope required")
        if grouped.get(a)!=grouped.get(b) or a not in grouped:
            raise ValueError("Relation endpoints must belong to the same explicit agreement group")
        key=(a,b,e["relation"])
        if key in used:raise ValueError("Duplicate amendment relation")
        used.add(key)
        if e["relation"] not in {"RELATED_EXHIBIT","EXACT_DUPLICATE_FILING"}:
            graph[a].add(b)
    visited=set();active=set()
    def visit(n):
        if n in active:raise ValueError("Cycle in directional amendment relationships")
        if n in visited:return
        active.add(n)
        for x in graph[n]:visit(x)
        active.remove(n);visited.add(n)
    for n in graph:visit(n)
    # Suggest exact duplicates, but never create links automatically.
    hashes={};dups=[]
    for d in docs:
        h=d["map"]["text_sha256"]
        if h in hashes and (d["document_id"] not in grouped or hashes[h] not in grouped or grouped[d["document_id"]] != grouped[hashes[h]]):
            dups.append([hashes[h],d["document_id"]])
        hashes.setdefault(h,d["document_id"])
    return {"group_for":grouped,"relations":edges,"exact_text_duplicates_unreconciled":dups}


def default_linkage():
    return {"schema":LINK_SCHEMA,"groups":[],"relations":[],
            "notice":"No grouping asserted. Each SEC document is provisional, NOT a distinct verified agreement."}


def agreement_of(doc_id: str, verified:dict):
    group=verified["group_for"].get(doc_id)
    if group:return group["agreement_id"],group["status"]
    return stable_id("PROVISIONAL", doc_id),"UNLINKED_PROVISIONAL"
