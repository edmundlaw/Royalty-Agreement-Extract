"""M3 durable workspace for M1/M2 records. Local and deliberately model-free.

A document source map cannot change after registration. Extraction attempts are
immutable, addressed by content digest, and never silently replace earlier work.
A small pointer file names a selected attempt; selection is explicit and logged.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from contextlib import contextmanager
from datetime import date

from .mapping import validate_map
from .m2_validation import validate_extraction, M2_VALIDATOR_REVISION, M11_VALIDATOR_REVISION, M12_VALIDATOR_REVISION
from .storage import atomic_json, json_bytes, read_json, sha256, stable_id, utc_now

try:
    import fcntl
except ImportError:  # pragma: no cover - Unix/Mac support required for write operations
    fcntl = None

WORKSPACE_SCHEMA = "m3-workspace.1"
REGISTRY_SCHEMA = "m6-expected-documents.1"
DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,180}$")


def _key(document_id: str) -> str:
    if not isinstance(document_id, str) or not DOCUMENT_ID_RE.fullmatch(document_id) or document_id in {".", ".."}:
        raise ValueError("Unsafe or invalid document_id")
    return stable_id("REC", document_id)


def _root(root) -> Path:
    p = Path(root).expanduser()
    if p.is_symlink():
        raise ValueError("Workspace root cannot be a symbolic link")
    return p


def _docs(root) -> Path:
    return _root(root) / "documents"


def _document_dir(root, document_id: str) -> Path:
    return _docs(root) / _key(document_id)


def _save_new(path: Path, obj) -> bool:
    """Idempotent immutable write; reject existing contradictory content."""
    raw = json_bytes(obj)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError(f"Immutable artifact already exists with different bytes: {path}")
        return False
    atomic_json(path, obj)
    return True


@contextmanager
def workspace_lock(root):
    if fcntl is None:
        raise RuntimeError("Workspace mutation requires Unix/macOS fcntl locking")
    root = _root(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".workspace.lock"
    with open(path, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _check_root(root):
    cfg = _root(root) / "workspace.json"
    if not cfg.exists() or read_json(cfg).get("schema") != WORKSPACE_SCHEMA:
        raise ValueError("Not an initialized M3 workspace: use m3-init")
    _read_registry(root)


def _read_registry(root):
    path=_root(root)/"expected_documents.json"
    if not path.is_file():
        raise ValueError("EXPECTED_DOCUMENT_REGISTER_MISSING: workspaces cannot silently lose documents")
    register=read_json(path)
    if register.get("schema")!=REGISTRY_SCHEMA or not isinstance(register.get("documents"),dict):
        raise ValueError("EXPECTED_DOCUMENT_REGISTER_INVALID")
    return register


def _save_registry(root, register):
    atomic_json(_root(root)/"expected_documents.json",register)



def init(root):
    with workspace_lock(root):
        cfg_path = _root(root) / "workspace.json"
        if cfg_path.exists():
            _check_root(root)
            return {"status": "EXISTING", "workspace": str(_root(root))}
        _docs(root).mkdir(parents=True, exist_ok=True)
        # Persistent, independent list of every expected source and its selected
        # attempt. Deleting a document or selection now fails export closed.
        atomic_json(_root(root)/"expected_documents.json",{"schema":REGISTRY_SCHEMA,"documents":{}})
        atomic_json(cfg_path, {"schema": WORKSPACE_SCHEMA, "created_at_utc": utc_now(),
                               "policy": "local JSON, no LLM inference, immutable source maps and extraction attempts"})
        return {"status": "INITIALIZED", "workspace": str(_root(root))}


def register_map(root, mapping: dict) -> dict:
    _check_root(root)
    errs = validate_map(mapping)
    if errs:
        raise ValueError(f"Invalid M1 map: {errs}")
    doc_id = mapping["document_id"]
    with workspace_lock(root):
        folder = _document_dir(root, doc_id)
        folder.mkdir(parents=True, exist_ok=True)
        metadata = {"schema": "m3-document.1", "document_id": doc_id,
                    "map_sha256": sha256(json_bytes(mapping)), "text_sha256": mapping["text_sha256"]}
        _save_new(folder / "map.json", mapping)
        _save_new(folder / "source.json", metadata)
        registry=_read_registry(root)
        expected=registry["documents"].get(doc_id)
        if expected and expected["map_sha256"]!=metadata["map_sha256"]:
            raise ValueError("EXPECTED_SOURCE_REGISTER_CONFLICT")
        if expected is None:
            registry["documents"][doc_id]={"map_sha256":metadata["map_sha256"],
                "selected_sha256":None,"selection_events":[]}
            _save_registry(root,registry)
        return {"status":"REGISTERED", "document_id":doc_id, "map_sha256":metadata["map_sha256"]}


def read_map(root, document_id):
    _check_root(root)
    folder = _document_dir(root, document_id)
    if folder.is_symlink():
        raise ValueError("Document folder must not be a symlink")
    registry=_read_registry(root)
    expected=registry["documents"].get(document_id)
    if expected is None:raise ValueError("DOCUMENT_NOT_IN_EXPECTED_REGISTER")
    meta = read_json(folder / "source.json")
    mapping = read_json(folder / "map.json")
    if (meta.get("document_id") != document_id or mapping.get("document_id") != document_id
        or meta.get("map_sha256") != expected["map_sha256"]
        or sha256(json_bytes(mapping)) != meta.get("map_sha256") or validate_map(mapping)):
        raise ValueError("Source map corrupted or changed")
    return mapping


def _mark_selection(root, document_id, digest):
    """Update the independent expected register under the workspace lock."""
    register=_read_registry(root)
    doc=register["documents"].get(document_id)
    if doc is None:raise ValueError("DOCUMENT_NOT_IN_EXPECTED_REGISTER")
    if doc.get("selected_sha256")!=digest:
        doc["selection_events"].append({"selected_sha256":digest,"at_utc":utc_now()})
        doc["selected_sha256"]=digest
        _save_registry(root,register)


def _attempt_folder(root, document_id):
    return _document_dir(root, document_id) / "attempts"


def _record_attempt(root, document_id, extraction, *, select: bool):
    mapping = read_map(root, document_id)
    qc = validate_extraction(mapping, extraction)
    digest = sha256(json_bytes(extraction))
    result = {"schema": "m3-attempt.1", "document_id": document_id,
              "extraction_sha256":digest, "map_sha256":sha256(json_bytes(mapping)),
              "deterministic_status": qc["deterministic_status"],
              "validator_revision": "m13.0-source-check-and-two-reader-comparison" if mapping.get("quality_control_profile")=="M13_TWO_READER" else M12_VALIDATOR_REVISION if mapping.get("quality_control_profile")=="M12_SOURCE_FLAGS" else (M11_VALIDATOR_REVISION if mapping.get("quality_control_profile")=="M11_TYPED_SIGNALS" else M2_VALIDATOR_REVISION),
              "blocking_issues": [v.get("issue_id") for v in extraction.get("open_issues",[])
                                 if isinstance(v,dict) and v.get("status") != "RESOLVED"
                                 and v.get("severity") in {"HIGH","CRITICAL"}],
              "created_at_utc":utc_now()}
    with workspace_lock(root):
        af = _attempt_folder(root, document_id) / digest
        af.mkdir(parents=True, exist_ok=True)
        _save_new(af / "extraction.json", extraction)
        # QC output deterministic except ordering, keep immutable and always recompute on read.
        _save_new(af / "qc.json", qc)
        # Metadata has a clock, so idempotent retry reads the original metadata.
        if (af / "attempt.json").exists():
            prior = read_json(af / "attempt.json")
            if {k:v for k,v in prior.items() if k!="created_at_utc"} != {k:v for k,v in result.items() if k!="created_at_utc"}:
                raise ValueError("Attempt metadata has changed")
            result = prior
        else:
            _save_new(af / "attempt.json", result)
        if select:
            # Selection is explicit. A failed attempt can be selected for correction
            # but cannot enter curated export.
            atomic_json(_document_dir(root, document_id) / "selected.json",
                        {"schema":"m3-selection.1","document_id":document_id,
                         "extraction_sha256":digest,"selected_at_utc":utc_now()})
            _mark_selection(root,document_id,digest)
    return result


def register_extraction(root, document_id, extraction, *, select=False):
    _check_root(root)
    return _record_attempt(root, document_id, extraction, select=select)


def select_attempt(root, document_id, extraction_sha256):
    _check_root(root)
    if not re.fullmatch(r"[0-9a-f]{64}", extraction_sha256):
        raise ValueError("Invalid extraction digest")
    load_attempt(root, document_id, extraction_sha256)
    with workspace_lock(root):
        atomic_json(_document_dir(root, document_id) / "selected.json", {
            "schema":"m3-selection.1", "document_id":document_id,
            "extraction_sha256":extraction_sha256, "selected_at_utc":utc_now()})
        _mark_selection(root,document_id,extraction_sha256)
    return {"document_id":document_id,"selected_sha256":extraction_sha256}


def load_attempt(root, document_id, digest):
    mapping = read_map(root, document_id)
    if not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
        raise ValueError("Invalid extraction digest")
    folder = _attempt_folder(root, document_id) / digest
    if folder.is_symlink():
        raise ValueError("Attempt path cannot be a symlink")
    if not (folder / "extraction.json").is_file():
        raise ValueError("Requested extraction attempt is not registered")
    extraction = read_json(folder / "extraction.json")
    if sha256(json_bytes(extraction)) != digest:
        raise ValueError("Extraction attempt was modified")
    # A new stricter validator makes old QC reports stale, not tampered.
    # Never silently adopt their prior PASS or rewrite immutable historical QC.
    info = read_json(folder / "attempt.json")
    expected_revision = "m13.0-source-check-and-two-reader-comparison" if mapping.get("quality_control_profile")=="M13_TWO_READER" else M12_VALIDATOR_REVISION if mapping.get("quality_control_profile")=="M12_SOURCE_FLAGS" else (M11_VALIDATOR_REVISION if mapping.get("quality_control_profile")=="M11_TYPED_SIGNALS" else M2_VALIDATOR_REVISION)
    if info.get("validator_revision") != expected_revision:
        raise ValueError("EXTRACTION_CHECKER_REVISION_CHANGED: previous QC remains immutable; "
                         "re-map/re-ingest in a new versioned workspace and rerun QC before export")
    qc = validate_extraction(mapping, extraction)
    stored_qc = read_json(folder / "qc.json")
    if qc != stored_qc:
        raise ValueError("QC report tampered with / validator results changed")
    info = read_json(folder / "attempt.json")
    if info.get("extraction_sha256") != digest or info.get("map_sha256") != sha256(json_bytes(mapping)):
        raise ValueError("Attempt provenance mismatch")
    return extraction, qc, info


def get_selected(root, document_id):
    path = _document_dir(root, document_id) / "selected.json"
    expected=_read_registry(root)["documents"][document_id]["selected_sha256"]
    if not path.exists():
        if expected is not None:
            raise ValueError("SELECTED_ATTEMPT_POINTER_MISSING: previously selected data was lost")
        return None
    if expected is None:
        raise ValueError("UNREGISTERED_SELECTION_POINTER")
    selected = read_json(path)
    if selected.get("document_id") != document_id:
        raise ValueError("Selected attempt document mismatch")
    if selected.get("extraction_sha256")!=expected:
        raise ValueError("SELECTED_ATTEMPT_REGISTER_MISMATCH")
    return load_attempt(root, document_id, selected["extraction_sha256"])


def record_human_review(root, review):
    """Removed from M7: no review sign-off is collected or required."""
    raise ValueError('HUMAN_APPROVAL_DISABLED: M7 exports all extraction records with their automated QC states')



def list_documents(root):
    _check_root(root)
    registry=_read_registry(root)["documents"]
    expected_folders={_key(did) for did in registry}
    actual_folders={p.name for p in _docs(root).iterdir() if p.is_dir()}
    if actual_folders!=expected_folders:
        raise ValueError("EXPECTED_DOCUMENT_SET_MISMATCH: a registered document disappeared or an unknown folder appeared")
    result=[]
    for folder in sorted(_docs(root).iterdir()):
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("Invalid document folder")
        source=read_json(folder / "source.json")
        doc_id=source["document_id"]
        if folder.name != _key(doc_id):
            raise ValueError("Document folder ID mismatch")
        mapping=read_map(root, doc_id)
        picked=get_selected(root,doc_id)
        attempts=[]
        af = folder / "attempts"
        if af.exists():
            for f in sorted(af.iterdir()):
                if f.is_symlink() or not f.is_dir():raise ValueError("Invalid attempt directory")
                load_attempt(root,doc_id,f.name)
                attempts.append(f.name)
        if picked is None:
            state="AWAITING_EXTRACTION"
            active=None
            qc=None
            reviews=[]
            ai_reviews=[]
        else:
            active,qc,info=picked
            digest=info["extraction_sha256"]
            reviews=[]  # M7 does not collect human approval or review decisions.
            ai_reviews=find_ai_reviews(root,doc_id,digest)
            model_high_issues=[v.get('issue_id') for v in active.get('open_issues',[])
                if isinstance(v,dict) and v.get('status')!='RESOLVED' and v.get('severity') in {'HIGH','CRITICAL'}]
            ai_disagreements=[v for v in ai_reviews
                if v['comparison']['status']=='REVIEW_REQUIRED']
            if qc["deterministic_status"]=="INCOMPLETE_SUPPORTING_ECONOMICS":state="QC_INCOMPLETE_SUPPORTING_ECONOMICS"
            elif qc["deterministic_status"]!="PASS_DETERMINISTIC_ONLY":state="QC_FAILED"
            elif model_high_issues:state="QC_PASSED_OPEN_HIGH_ISSUE"
            elif ai_disagreements:state="QC_PASSED_AI_DISAGREEMENT"
            else:state="QC_PASSED_NOT_PROFESSIONALLY_VERIFIED"
        result.append({"document_id":doc_id,"map":mapping,"selected":active,
                       "qc":qc,"reviews":reviews,"ai_reviews":ai_reviews,"state":state,"attempts":attempts,
                       "selected_sha256":sha256(json_bytes(active)) if active is not None else None})
    return result


def register_second_reader(root, document_id: str, extraction: dict) -> dict:
    """Store independent reader's result and comparison to CURRENT selected first read.

    An AI comparison is independent only if metadata supports it. No automatic
    'audited' status; a later change of selected first attempt invalidates this
    comparison for that newly selected attempt.
    """
    from .m2_validation import compare_independent_extractions
    picked=get_selected(root,document_id)
    if picked is None:
        raise ValueError("Select first-reader extraction before recording second reader")
    first,_,first_info=picked
    second_info=register_extraction(root,document_id,extraction,select=False)
    comparison=compare_independent_extractions(read_map(root,document_id),first,extraction)
    packet={"schema":"m3-ai-review.1","document_id":document_id,
            "first_sha256":first_info["extraction_sha256"],
            "second_sha256":second_info["extraction_sha256"],
            "comparison":comparison,
            "semantic_review_notice":"AI agreement is not a proof of completeness or contractual correctness"}
    digest=sha256(json_bytes(packet))
    with workspace_lock(root):
        out=_document_dir(root,document_id)/"ai_reviews"/(digest+".json")
        _save_new(out,packet)
    return {"status":comparison["status"],"review_sha256":digest,
            "first_sha256":packet["first_sha256"],"second_sha256":packet["second_sha256"]}


def find_ai_reviews(root, document_id, first_digest):
    folder=_document_dir(root,document_id)/"ai_reviews"
    results=[]
    for path in sorted(folder.glob("*.json")):
        if path.is_symlink():raise ValueError("AI review symlink not allowed")
        obj=read_json(path)
        if sha256(json_bytes(obj))!=path.stem or obj.get("document_id")!=document_id:
            raise ValueError("AI review file modified/mismatched")
        if obj["first_sha256"]!=first_digest:continue
        first,_,_=load_attempt(root,document_id,first_digest)
        second,_,_=load_attempt(root,document_id,obj["second_sha256"])
        from .m2_validation import compare_independent_extractions
        fresh=compare_independent_extractions(read_map(root,document_id),first,second)
        if fresh!=obj["comparison"]:
            raise ValueError("AI review no longer agrees with source/checker")
        results.append(obj)
    return results
