"""Local, source-bound candidate screening probes; no AI and no inferred recall.

A probe can prove that explicitly enumerated anchors are present and mapped.
It cannot show that unenumerated royalty terms were captured, nor that the
source is a complete authentic filing. This distinction is intentional.
"""
from __future__ import annotations

import re
from pathlib import Path
from .mapping import map_contract, validate_map
from .parsing import parse_document
from .storage import sha256, stable_id


class ProbeError(ValueError):
    pass


def probe(raw: bytes, filename: str, source_url: str, anchors: list[dict]) -> dict:
    if not isinstance(raw, bytes) or not raw:
        raise ProbeError("Input source is empty")
    if not isinstance(source_url, str) or not source_url.startswith("https://www.sec.gov/Archives/"):
        raise ProbeError("A source SEC URL is required; local samples are not verified originals")
    if not isinstance(anchors, list) or not anchors:
        raise ProbeError("Pre-registered, nonempty test anchors are required")
    paragraphs, parser = parse_document(raw, filename)
    source = {"source_url": source_url, "document_id": stable_id("DOC", source_url, sha256(raw))}
    mapping = map_contract(paragraphs, source, raw_hash=sha256(raw), parser_type=parser)
    problems = validate_map(mapping)
    if problems:
        raise ProbeError("Internal map validation failed: " + ", ".join(problems))
    candidate = set(mapping["candidate_passages"])
    outcomes = []
    for anchor in anchors:
        ident = anchor.get("id")
        pattern = anchor.get("regex")
        expected = anchor.get("candidate", True)
        if not isinstance(ident, str) or not ident or not isinstance(pattern, str) or not pattern or len(pattern) > 250:
            raise ProbeError("Invalid anchor name or regular expression")
        if type(expected) is not bool:
            raise ProbeError("Anchor candidate must be Boolean")
        try:
            expr = re.compile(pattern, re.I)
        except re.error as exc:
            raise ProbeError(f"Invalid anchor regex {ident}: {exc}") from exc
        found = [p for p in mapping["passages"] if expr.search(p["text"])]
        candidate_found = [p for p in found if p["passage_id"] in candidate]
        ok = bool(found) and (bool(candidate_found) if expected else True)
        outcomes.append({"anchor_id": ident, "present": bool(found),
                         "candidate_detected": bool(candidate_found), "passage_ids": [p["passage_id"] for p in found],
                         "pass": ok})
    return {"schema": "m5-probe.1", "source_url": source_url, "source_filename": filename,
            "input_sha256": sha256(raw), "text_sha256": mapping["text_sha256"],
            "parser": parser, "passage_count": len(mapping["passages"]),
            "candidate_count": len(candidate), "unflagged_count": len(mapping["passages"])-len(candidate),
            "anchors": outcomes, "status": "ANCHORS_PASS_NOT_RECALL_VALIDATED" if all(x["pass"] for x in outcomes) else "ANCHORS_FAIL",
            "not_validated": ["Complete original document authentication", "Full-contract semantic recall", "Model interpretation accuracy", "SEC link availability", "Subscription CLI"],
            "note": "Anchor matches are deterministic screening tests only. Input may be a paraphrase, not the SEC document."}


def probe_manifest(fixtures: str | Path, manifest: dict) -> dict:
    if not isinstance(manifest,dict) or manifest.get("schema") != "m5-anchor-manifest.1":
        raise ProbeError("Unknown anchor manifest")
    source_root = Path(fixtures).resolve()
    records = manifest.get("records")
    if not isinstance(records,list) or not records:
        raise ProbeError("Manifest needs at least one source record")
    out = []
    for entry in records:
        filename = entry.get("filename")
        if not isinstance(filename,str) or filename in {"", ".", ".."} or Path(filename).name != filename:
            raise ProbeError("Unsafe fixture filename")
        path = (source_root/filename).resolve()
        if not path.is_relative_to(source_root) or not path.is_file() or path.is_symlink():
            raise ProbeError("Fixture must be regular file within fixture directory")
        report = probe(path.read_bytes(), filename, entry["source_url"], entry["anchors"])
        report["case_label"] = entry.get("label")
        out.append(report)
    return {"schema":"m5-manifest-probes.1", "results":out,
            "status":"ALL_ANCHORS_PASS_NOT_RECALL_VALIDATED" if all(x["status"]=="ANCHORS_PASS_NOT_RECALL_VALIDATED" for x in out) else "ANCHOR_FAILURE",
            "not_a_gold_standard": True}
