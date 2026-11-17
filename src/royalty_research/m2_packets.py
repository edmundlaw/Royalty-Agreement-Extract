"""Offline, deterministic source packets; no model calls or external services.

Selected packets are intentionally not a proof of complete contract review. Full
coverage packets enumerate every passage and fail on character-bound problems.
"""
from __future__ import annotations

from collections import defaultdict
from .mapping import validate_map
from .storage import sha256

PACKET_VERSION = "m2-packet.1"


def _validate_map_or_raise(mapping: dict):
    failures = validate_map(mapping)
    if failures:
        raise ValueError("Invalid source map: " + ", ".join(failures))


def deterministic_unflagged_sample(mapping: dict, *, minimum: int = 3, fraction: float = 0.10) -> list[str]:
    """Stable section-stratified sample; not a statistical recall estimate.

    Includes at least one passage per section if budget permits. Long sections
    get proportional additional coverage. Hash ordering prevents cherry picking.
    """
    _validate_map_or_raise(mapping)
    flagged = set(mapping["candidate_passages"])
    unflagged = [p for p in mapping["passages"] if p["passage_id"] not in flagged]
    if not unflagged:
        return []
    import math
    goal = min(len(unflagged), max(minimum, math.ceil(len(unflagged) * fraction)))
    by_section = defaultdict(list)
    for p in unflagged:
        by_section[p.get("section_guess") or "PREAMBLE_OR_UNNUMBERED"].append(p)
    rank = lambda p: sha256((mapping["text_sha256"] + ":" + p["passage_id"]).encode("utf-8"))
    selected = []
    for sec in sorted(by_section):
        selected.append(min(by_section[sec], key=rank))
    if len(selected) > goal:
        selected = sorted(selected, key=rank)[:goal]
    chosen = {p["passage_id"] for p in selected}
    for p in sorted(unflagged, key=rank):
        if len(chosen) >= goal:
            break
        chosen.add(p["passage_id"])
    order = {p["passage_id"]: i for i, p in enumerate(mapping["passages"])}
    return sorted(chosen, key=lambda pid: order[pid])


def select_passages(mapping: dict, mode: str = "selected", neighbor_radius: int = 1,
                    sample_fraction: float = 0.10) -> tuple[list[str], list[str]]:
    _validate_map_or_raise(mapping)
    if mode not in {"selected", "full"}:
        raise ValueError("mode must be 'selected' or 'full'")
    passages = mapping["passages"]
    ids = [p["passage_id"] for p in passages]
    if mode == "full":
        return ids, []
    if not 0 <= neighbor_radius <= 5:
        raise ValueError("neighbor radius out of range")
    if not 0 <= sample_fraction <= 1:
        raise ValueError("sample fraction out of range")
    selected = set(mapping["candidate_passages"])
    positions = {pid: i for i, pid in enumerate(ids)}
    for pid in list(selected):
        i = positions[pid]
        selected.update(ids[max(0, i - neighbor_radius):min(len(ids), i + neighbor_radius + 1)])
    sample = deterministic_unflagged_sample(mapping, fraction=sample_fraction)
    selected.update(sample)
    # A section map includes every section even if no passage in that section is selected.
    return [pid for pid in ids if pid in selected], sample


def make_packets(mapping: dict, *, mode="selected", max_chars=16000,
                 neighbor_radius=1, sample_fraction=.10) -> dict:
    """Create bounded chunks with full coverage manifest and source-hash binding.

    No silent truncation: any passage longer than max_chars is an explicit error.
    """
    if not 2000 <= max_chars <= 250_000:
        raise ValueError("max_chars must be 2,000 to 250,000")
    ids, sample = select_passages(mapping, mode, neighbor_radius, sample_fraction)
    included = set(ids)
    all_ids = [p["passage_id"] for p in mapping["passages"]]
    chunks = []
    current = []
    size = 0
    for p in mapping["passages"]:
        if p["passage_id"] not in included:
            continue
        # Including ID, section metadata, and text envelope overestimate.
        approximate = len(p["text"]) + len(p["passage_id"]) + 200
        if approximate > max_chars:
            raise ValueError("Oversize passage, must split at M1 mapping stage: " + p["passage_id"])
        if current and size + approximate > max_chars:
            chunks.append(current)
            current = []
            size = 0
        current.append({
            "passage_id": p["passage_id"], "section": p["section_guess"],
            "candidate_reasons": p["candidate_reasons"], "text": p["text"],
        })
        size += approximate
    if current:
        chunks.append(current)
    covered = [p["passage_id"] for chunk in chunks for p in chunk]
    if covered != ids:
        raise AssertionError("Packet passage coverage mismatch")
    if mode == "full" and covered != all_ids:
        raise AssertionError("Full packet did not cover full document")
    return {
        "packet_schema": PACKET_VERSION,
        "document_id": mapping["document_id"],
        "source_url": mapping["source_url"],
        "source_text_sha256": mapping["text_sha256"],
        "source_original_sha256": mapping.get("original_sha256"),
        "mode": mode,
        "read_scope_label": ("FULL_DOCUMENT_CHUNKED" if mode == "full" else "SELECTED_CONTEXT_NOT_FULL_DOCUMENT"),
        "source_passage_count": len(all_ids),
        "included_passage_ids": ids,
        "excluded_passage_ids": [p for p in all_ids if p not in included],
        "candidate_passage_ids": mapping["candidate_passages"],
        "unflagged_sample_ids": sample,
        "section_inventory": [{"section": s["section"], "passage_count": len(s["passage_ids"]),
                               "candidate_count": len(s["candidate_ids"])} for s in mapping["sections"]],
        "definitions": mapping.get("definitions", []),
        "cross_references": mapping.get("cross_references", []),
        "chunks": [{"chunk_index": i + 1, "chunk_count": len(chunks), "passages": chunk}
                   for i, chunk in enumerate(chunks)],
        "warning": ("Selected excerpts do NOT establish full-document completeness" if mode == "selected"
                    else "Full document passages supplied; model reading/completeness NOT independently established"),
    }


def make_blind_rekey_packet(mapping: dict, extraction: dict, *, neighbor_radius=1) -> dict:
    """Independent reader gets *source text*, never extracted values, structures, or answers.

    Evidence identifiers are included to align responses; this is a semantic
    second read of already found clauses, not an independent omission search.
    """
    _validate_map_or_raise(mapping)
    if extraction.get("document_id") != mapping.get("document_id") or extraction.get("source_text_sha256") != mapping.get("text_sha256"):
        raise ValueError("Extraction source binding mismatch")
    evidence = extraction.get("evidence") or []
    passage_ids = {e["passage_id"] for e in evidence if isinstance(e, dict) and "passage_id" in e}
    ids = [p["passage_id"] for p in mapping["passages"]]
    pos = {pid: i for i, pid in enumerate(ids)}
    wanted = set()
    for pid in passage_ids:
        if pid not in pos:
            raise ValueError("Unknown evidence passage")
        i = pos[pid]
        wanted.update(ids[max(0, i-neighbor_radius):i+neighbor_radius+1])
    return {
        "rekey_packet_schema": "m2-rekey-packet.1", "document_id": mapping["document_id"],
        "source_text_sha256": mapping["text_sha256"],
        "evidence_anchors": [{"evidence_id": e["evidence_id"], "passage_id": e["passage_id"]} for e in evidence],
        "passages": [{"passage_id": p["passage_id"], "section": p["section_guess"], "text": p["text"]}
                     for p in mapping["passages"] if p["passage_id"] in wanted],
        "definitions": [d for d in mapping.get("definitions", []) if d["passage_id"] in wanted],
        "warning": "Blinded to first extraction; validates semantics of supplied evidence, not missing clauses elsewhere",
    }
