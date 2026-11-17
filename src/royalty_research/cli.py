"""Local M1 discovery plus M2 evidence-first, offline extraction QC."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from . import __version__
from .discovery import discover, index_url, parse_master_idx
from .inventory import parse_filing_index_html
from .mapping import map_contract, validate_map
from .m2_packets import make_packets, make_blind_rekey_packet
from .m2_validation import validate_extraction, compare_independent_extractions
from .parsing import parse_document
from .m5_probe import probe_manifest
from .sec_client import SECClient
from .storage import atomic_json, atomic_jsonl, read_json, read_jsonl, sha256, json_bytes, utc_now
from .m3_workspace import (init as m3_init, register_map, read_map, register_extraction, select_attempt,
                           register_second_reader, list_documents)
from .m3_chunks import merge_chunks
from .m3_linkage import validate_linkage, default_linkage
from .m3_export import build_rows, write_csvs, export_manifest
from .m3_workbook import write_xlsx
from .m4_operator import (create_plan, status as m4_status, run_next as m4_run_next,
                          authorize_retry as m4_authorize_retry, clear_limit as m4_clear_limit,
                          merge_plan as m4_merge_plan, recover_saved_result as m4_recover_saved_result)


def _client(args):
    if not args.user_agent:
        raise ValueError("Live SEC access requires --user-agent 'Your research project contact@yourdomain.com'")
    return SECClient(args.user_agent, requests_per_second=args.rate, retries=args.retries)


def _available(path: Path, *, force=False, skip_existing=False) -> bool:
    if not path.exists():
        return True
    if skip_existing:
        print(f"SKIP_EXISTS {path}")
        return False
    if not force:
        raise FileExistsError(f"Output exists. Pass --force to overwrite or --skip-existing to skip: {path}")
    return True


def _date(s: str):
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Date must be YYYY-MM-DD") from exc


def _add_sec_options(p):
    p.add_argument("--user-agent", help="SEC required descriptive user agent with real contact email")
    p.add_argument("--rate", type=float, default=1.0, help="Requests/sec; 1 default, max 5")
    p.add_argument("--retries", type=int, default=2)


def _add_output_options(p):
    p.add_argument("--out", type=Path, required=True)
    actions = p.add_mutually_exclusive_group()
    actions.add_argument("--force", action="store_true")
    actions.add_argument("--skip-existing", action="store_true")


def _read_source(args) -> tuple[bytes, str | None]:
    if args.input:
        return args.input.read_bytes(), None
    return _client(args).fetch(args.url), utc_now()


def build_parser():
    p = argparse.ArgumentParser(prog="royalty-research", description="SEC research foundation + M2 source-grounded AI output checks (no API calls)")
    p.add_argument("--version", action="version", version=__version__)
    s = p.add_subparsers(dest="command", required=True)

    q=s.add_parser("m8-prepare",help="Create full-document subscription reading plan and source/occurrence manifests (no AI call)")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--engine",choices=["claude","codex"],required=True)
    q.add_argument("--model",required=True)
    q.add_argument("--max-chars",type=int,default=64000)
    q.add_argument("--ledger-max-chars",type=int,default=14000)
    q.add_argument("--ledger-engine",choices=["claude","codex"],help="Optional different engine for cheaper second-stage work")
    q.add_argument("--ledger-model",help="Optional lightweight ledger model, e.g. sonnet")
    q.add_argument("--qc-profile",choices=["legacy","m11","m12"],default="legacy",
                   help="M11 uses typed source signals and skips the costly M7 occurrence ledger")

    q=s.add_parser("m13-prepare",help="M13: prepare one agreement for reading; second reader optional (no AI call)")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--engine",choices=["claude","codex"],required=True,help="First reader CLI")
    q.add_argument("--model",required=True,help="First reader model label, e.g. sonnet")
    q.add_argument("--check-engine",choices=["claude","codex"],help="Optional independent second reader CLI")
    q.add_argument("--check-model",help="Optional second reader model label")
    q.add_argument("--max-chars",type=int,default=64000)
    q=s.add_parser("m13-add-check",help="M13: add a second reader to an existing run (no AI call)")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--engine",choices=["claude","codex"],required=True)
    q.add_argument("--model",required=True)
    q=s.add_parser("m13-next",help="M13: run the next reading call; dry run unless --execute")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--execute",action="store_true")
    q.add_argument("--confirm-subscription",action="store_true")
    q.add_argument("--confirm-credit-controls",action="store_true")
    q.add_argument("--all",action="store_true",help="Run every remaining call of THIS agreement; stops at the first task not captured")
    q.add_argument("--timeout",type=int,default=900)
    q=s.add_parser("m13-status",help="M13: progress of the reading(s) and exported result; no AI call")
    q.add_argument("--root",type=Path,required=True)
    q=s.add_parser("m13-combine",help="M13: five-sheet PwC research workbook from finished runs; no AI call")
    q.add_argument("--runs",type=Path,required=True,help="Folder that contains the run folders")
    q.add_argument("--out",type=Path,required=True,help="New .xlsx file")
    q.add_argument("--legacy-xlsx",action="store_true",help="Also export the original detailed 16-sheet XLSX")
    q=s.add_parser("m13-finalize",help="M13: source check, reader comparison when a second reader exists, Excel export; no AI call")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--csv-only",action="store_true")
    q.add_argument("--legacy-xlsx",action="store_true",help="Also export the original detailed 16-sheet XLSX")
    q.add_argument("--without-check",action="store_true",help="Export the first reading although a prepared second reader is unfinished")

    q=s.add_parser("m12-finalize",help="After M12 full-source reading, export source-accounted Excel; no model call")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--csv-only",action="store_true")
    q=s.add_parser("m12-import-correction",help="Import one immutable M12 source-bound correction")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--response",type=Path,required=True)
    q.add_argument("--csv-only",action="store_true")
    q=s.add_parser("m12-signals",help="Issue M12 source economic flags without AI")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)
    q=s.add_parser("m12-check",help="Check extraction against source economic flags")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--extraction",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)

    q=s.add_parser("m11-finalize",help="After all M11 primary chunks, issue typed source flags, export Excel and one optional correction task; no AI call")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--csv-only",action="store_true")

    q=s.add_parser("m11-import-correction",help="Import ONE source-bound Sonnet correction response; append immutable new attempt; no AI call")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--response",type=Path,required=True)
    q.add_argument("--csv-only",action="store_true")

    q=s.add_parser("m11-signals",help="Issue independent source economic flags from a numbered map; no model call")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)

    q=s.add_parser("m11-check",help="Validate source-bound typed closures; free-text open issues never close flags")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--extraction",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)

    q=s.add_parser("m8-status",help="Audit primary/ledger progress and source integrity; no inference")
    q.add_argument("--root",type=Path,required=True)

    q=s.add_parser("m8-primary-next",help="Run one primary CLI task only with explicit subscription/credit confirmations")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--execute",action="store_true")
    q.add_argument("--confirm-subscription",action="store_true")
    q.add_argument("--confirm-credit-controls",action="store_true")
    q.add_argument("--timeout",type=int,default=900)

    q=s.add_parser("m8-ledger-prepare",help="Prepare bounded occurrence tasks after full primary capture (no AI call)")
    q.add_argument("--root",type=Path,required=True)

    q=s.add_parser("m8-ledger-next",help="Run one Sonnet/Codex occurrence-classification task; dry run by default")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--execute",action="store_true")
    q.add_argument("--confirm-subscription",action="store_true")
    q.add_argument("--confirm-credit-controls",action="store_true")
    q.add_argument("--timeout",type=int,default=900)

    q=s.add_parser("m8-ledger-import",help="Import one externally generated, source-bound ledger response with receipt")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--response",type=Path,required=True)

    q=s.add_parser("m8-ledger-retry",help="Release one failed ledger task for another model call; not contract approval")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--chunk",type=int,required=True)
    q.add_argument("--reason",required=True)

    q=s.add_parser("m8-ledger-clear-limit",help="Release a recorded ledger usage stop after external account check")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--reason",required=True)

    q=s.add_parser("m8-ledger-recover",help="Recover missing receipt for saved identical response, without model call")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--chunk",type=int,required=True)

    q=s.add_parser("m8-finalize",help="Validate all occurrence results and export CSV/Excel including unresolved QC failures")
    q.add_argument("--root",type=Path,required=True)
    q.add_argument("--csv-only",action="store_true")

    q=s.add_parser("m8-crossrefs",help="Inspect section references conservatively; unresolved labels remain visible")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)

    q=s.add_parser("m8-benchmark",help="Compare extraction with externally supplied reference, without inferring truth")
    q.add_argument("--reference",type=Path,required=True)
    q.add_argument("--extraction",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)

    q=s.add_parser("m7-prepare",help="Prepare source-issued occurrence IDs, relevance triage and complementary focus/remainder packets; no model call")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--outdir",type=Path,required=True)
    q.add_argument("--max-chars",type=int,default=22000)

    q=s.add_parser("m7-ledger-tasks",help="Issue compact, resumable Sonnet tasks from an existing extraction; does not call AI")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--extraction",type=Path,required=True)
    q.add_argument("--outdir",type=Path,required=True)
    q.add_argument("--max-chars",type=int,default=14000)

    q=s.add_parser("m7-merge-ledger",help="Merge source-bound model occurrence classifications; fail on any missing ID")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--extraction",type=Path,required=True)
    q.add_argument("--response",type=Path,action="append",required=True)
    q.add_argument("--task",type=Path,action="append",required=True,help="Exact issued task files matching model responses")
    q.add_argument("--out",type=Path,required=True)

    q=s.add_parser("m7-attach-ledger",help="Attach verified occurrence responses to original extraction without overwriting it")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--extraction",type=Path,required=True)
    q.add_argument("--ledger",type=Path,required=True)
    q.add_argument("--out",type=Path,required=True)

    q=s.add_parser("m7-validate",help="Strict source-issued occurrence QC on full M7 extraction; no model call")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--extraction",type=Path,required=True)
    _add_output_options(q)

    q = s.add_parser("m5-probe-manifest", help="Run local, source-bound anchor probes; no AI/SEC calls; NOT a recall estimate")
    q.add_argument("--fixtures", type=Path, required=True)
    q.add_argument("--manifest", type=Path, required=True)
    _add_output_options(q)

    q = s.add_parser("discover", help="Search SEC full-text by multiple queries, detect saturated date windows")
    q.add_argument("--start", type=_date, required=True)
    q.add_argument("--end", type=_date, required=True)
    q.add_argument("--query", action="append", required=True, help="Repeat for independent vocabularies")
    q.add_argument("--max-days", type=int, default=31,
                   help="Fail before long uncheckpointed searches; default 31 days. One-day runs recommended")
    _add_sec_options(q)
    _add_output_options(q)

    q = s.add_parser("master-index", help="Download or parse SEC quarterly master.idx; does not include individual exhibits")
    q.add_argument("--year", type=int, required=True)
    q.add_argument("--quarter", type=int, required=True)
    q.add_argument("--input", type=Path, help="Use offline index file instead of SEC")
    q.add_argument("--form", action="append", help="Exact SEC form type, e.g. 10-K, 8-K, S-1")
    _add_sec_options(q)
    _add_output_options(q)

    q = s.add_parser("filing-inventory", help="Get individual exhibit types and filenames from SEC filing -index.html")
    q.add_argument("--cik", required=True)
    q.add_argument("--accession", required=True)
    q.add_argument("--input", type=Path, help="Offline filing index HTML")
    _add_sec_options(q)
    _add_output_options(q)

    q = s.add_parser("map", help="Parse an original exhibit and create complete, numbered passage inventory")
    src = q.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path)
    src.add_argument("--url", help="Allowlisted SEC exhibit URL; raw file not persisted")
    q.add_argument("--source-url", help="SEC URL for an offline file; evidence reference only")
    q.add_argument("--document-id", help="Known document identifier, otherwise stable hash of URL")
    q.add_argument("--segment-chars", type=int, default=12000,
                   help="Exact character-preserving split threshold for unusually long original lines")
    _add_sec_options(q)
    _add_output_options(q)

    q = s.add_parser("validate-map", help="Check a mapped JSON document for internal evidence integrity")
    q.add_argument("--input", type=Path, required=True)

    q = s.add_parser("make-packets", help="Prepare source-bound AI reading packets; NEVER invokes an AI model")
    q.add_argument("--map", type=Path, required=True)
    q.add_argument("--mode", choices=["selected", "full"], default="selected")
    q.add_argument("--max-chars", type=int, default=16000)
    q.add_argument("--neighbor-radius", type=int, default=1)
    q.add_argument("--sample-fraction", type=float, default=.1)
    _add_output_options(q)

    q = s.add_parser("validate-extraction", help="Check AI JSON against M1 map, exact quotes and passage ledger")
    q.add_argument("--map", type=Path, required=True)
    q.add_argument("--extraction", type=Path, required=True)
    _add_output_options(q)

    q = s.add_parser("blind-rekey", help="Make evidence-only blind re-key packet; hides first AI answers")
    q.add_argument("--map", type=Path, required=True)
    q.add_argument("--extraction", type=Path, required=True)
    _add_output_options(q)

    q = s.add_parser("compare-extractions", help="Compare independently created, source-checked extraction JSONs")
    q.add_argument("--map", type=Path, required=True)
    q.add_argument("--first", type=Path, required=True)
    q.add_argument("--second", type=Path, required=True)
    _add_output_options(q)
    q = s.add_parser("m3-init", help="Create local checkpointed workspace; no AI model invoked")
    q.add_argument("--workspace",type=Path,required=True)

    q = s.add_parser("m3-register-map",help="Register immutable M1 document map")
    q.add_argument("--workspace",type=Path,required=True)
    q.add_argument("--map",type=Path,required=True)

    q = s.add_parser("m3-ingest",help="Store immutable M2 extraction attempt with fresh deterministic QC")
    q.add_argument("--workspace",type=Path,required=True)
    q.add_argument("--document-id",required=True)
    q.add_argument("--extraction",type=Path,required=True)
    q.add_argument("--select",action="store_true",help="Explicitly make this the active attempt, even when QC fails")

    q = s.add_parser("m3-select",help="Explicitly select previously ingested attempt by digest")
    q.add_argument("--workspace",type=Path,required=True)
    q.add_argument("--document-id",required=True)
    q.add_argument("--sha256",required=True)

    q = s.add_parser("m3-second-reader",help="Store blind second extraction and source-checked comparison")
    q.add_argument("--workspace",type=Path,required=True)
    q.add_argument("--document-id",required=True)
    q.add_argument("--extraction",type=Path,required=True)

    q = s.add_parser("m3-status",help="List all mapped documents, incomplete work, attempts and QC statuses")
    q.add_argument("--workspace",type=Path,required=True)
    q.add_argument("--out",type=Path,help="Optional durable JSON status snapshot")

    q = s.add_parser("m3-merge-chunks",help="Combine independent agent chunk JSONs; FAIL on missing/contradictory chunks")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--packet",type=Path,required=True)
    q.add_argument("--chunk",type=Path,action="append",required=True)
    q.add_argument("--out",type=Path,required=True)
    q.add_argument("--force",action="store_true")

    q = s.add_parser("m3-validate-linkage",help="Validate explicit grouping/amendment relationships")
    q.add_argument("--workspace",type=Path,required=True)
    q.add_argument("--linkage",type=Path,required=True)

    q = s.add_parser("m3-export",help="Create auditable source-bound CSV and/or Excel workbook, without model APIs")
    q.add_argument("--workspace",type=Path,required=True)
    q.add_argument("--linkage",type=Path)
    q.add_argument("--outdir",type=Path,required=True)
    q.add_argument("--format",choices=["csv","xlsx","both"],default="both")
    q.add_argument("--force",action="store_true",help="Replace previously generated outputs in destination")
    q=s.add_parser("m4-plan", help="Prepare immutable source-bound single-chunk model tasks; NEVER invokes a model")
    q.add_argument("--map",type=Path,required=True)
    q.add_argument("--packet",type=Path,required=True)
    q.add_argument("--outdir",type=Path,required=True)
    q.add_argument("--engine",choices=["claude","codex"],required=True)
    q.add_argument("--model",required=True,help="Explicit model available to your locally signed-in subscription")

    q=s.add_parser("m4-status",help="Show exact resume state; no model calls")
    q.add_argument("--plan",type=Path,required=True)

    q=s.add_parser("m4-run-next",help="DRY RUN by default; --execute calls exactly ONE CLI model task")
    q.add_argument("--plan",type=Path,required=True)
    q.add_argument("--execute",action="store_true")
    q.add_argument("--confirm-subscription",action="store_true",help="You checked the CLI uses subscription sign-in")
    q.add_argument("--confirm-credit-controls",action="store_true",help="You checked account credit/billing controls externally")
    q.add_argument("--timeout",type=int,default=900)

    q=s.add_parser("m4-authorize-retry",help="Explicitly release failed or interrupted task; no model call")
    q.add_argument("--plan",type=Path,required=True)
    q.add_argument("--task-id",required=True)
    q.add_argument("--reason",required=True)

    q=s.add_parser("m4-clear-limit",help="Release recorded limit stop after verifying plan/account reset")
    q.add_argument("--plan",type=Path,required=True)
    q.add_argument("--reason",required=True)

    q=s.add_parser("m4-recover-result",help="Manually restore receipt for already saved model JSON after interruption")
    q.add_argument("--plan",type=Path,required=True)
    q.add_argument("--task-id",required=True)
    q.add_argument("--confirm-recovery",action="store_true")

    q=s.add_parser("m4-merge-plan",help="Merge ALL captured chunks through M3 QC; no model call")
    q.add_argument("--plan",type=Path,required=True)
    return p


def run(args):
    if args.command.startswith('m13-'):
        from . import m13_two_reader as m13
        if args.command=='m13-prepare':
            result=m13.prepare(read_json(args.map),args.root,engine=args.engine,model=args.model,
                check_engine=args.check_engine,check_model=args.check_model,max_chars=args.max_chars)
        elif args.command=='m13-add-check':
            result=m13.add_check(args.root,engine=args.engine,model=args.model)
        elif args.command=='m13-next':
            result=m13.next_call(args.root,execute=args.execute,confirm_subscription=args.confirm_subscription,
                confirm_credit_controls=args.confirm_credit_controls,run_all=args.all,timeout=args.timeout)
        elif args.command=='m13-status':result=m13.status(args.root)
        elif args.command=='m13-combine':result=m13.combine(args.runs,args.out,legacy_xlsx=args.legacy_xlsx)
        else:
            result=m13.finalize(args.root,export_xlsx=not args.csv_only,without_check=args.without_check,
                                 legacy_xlsx=args.legacy_xlsx)
        print(json.dumps(result,ensure_ascii=False))
        return 2 if result.get('status')=='STOPPED_TASK_NOT_CAPTURED' or result.get('state')=='SOURCE_CHECK_FAILED' else 0
    if args.command.startswith('m12-'):
        from .m12_economic_qc import issue_signals,reconcile_with_proposals
        from . import m11_pipeline as typedpipe
        if args.command=='m12-finalize':
            result=typedpipe.finalize_primary_m12(args.root,xlsx=not args.csv_only)
        elif args.command=='m12-import-correction':
            result=typedpipe.import_correction_m12(args.root,read_json(args.response),xlsx=not args.csv_only)
        elif args.command=='m12-signals':
            if args.out.exists():raise FileExistsError('M12 immutable source manifest exists')
            signals=issue_signals(read_json(args.map))
            atomic_json(args.out,signals)
            result={'status':'SOURCE_FLAGS_ISSUED_NOT_VALIDATED','count':len(signals['signals']),'output':str(args.out)}
        elif args.command=='m12-check':
            if args.out.exists():raise FileExistsError('M12 immutable QC report exists')
            mapping=read_json(args.map);extraction=read_json(args.extraction)
            report=reconcile_with_proposals(mapping,extraction,extraction.get('m12_resolutions'))
            atomic_json(args.out,report)
            result={'status':report['status'],'hard_open':report['hard_open'],
                'supporting_open':report['warning_open'],'output':str(args.out)}
        else:raise ValueError('Unsupported M12 command')
        print(json.dumps(result,ensure_ascii=False))
        return 2 if result.get('status') in {'FAIL_INTEGRITY','INCOMPLETE_CORE_ECONOMICS'} else 0
    if args.command.startswith('m11-'):
        from .m11_signal_qc import issue_signals,reconcile_with_proposals
        from . import m11_pipeline as m11pipe
        if args.command=='m11-finalize':
            result=m11pipe.finalize_primary(args.root,xlsx=not args.csv_only)
        elif args.command=='m11-import-correction':
            result=m11pipe.import_correction(args.root,read_json(args.response),xlsx=not args.csv_only)
        elif args.command=='m11-signals':
            if args.out.exists():raise FileExistsError('M11 immutable source manifest exists')
            result=issue_signals(read_json(args.map))
            atomic_json(args.out,result)
            result={'status':'SOURCE_FLAGS_ISSUED_NOT_VALIDATED','count':len(result['signals']),'output':str(args.out)}
        elif args.command=='m11-check':
            if args.out.exists():raise FileExistsError('M11 immutable QC report exists')
            mapping=read_json(args.map);extraction=read_json(args.extraction)
            result=reconcile_with_proposals(mapping,extraction,extraction.get('m11_resolutions'))
            atomic_json(args.out,result)
            result={'status':result['status'],'hard_open':result['hard_open'],
                    'supporting_open':result['warning_open'],'output':str(args.out)}
        else:raise ValueError('Unsupported M11 command')
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result.get('status') not in {'FAIL_INTEGRITY','INCOMPLETE_CORE_ECONOMICS'} else 2
    if args.command.startswith("m8-"):
        from . import m8_pipeline as pipe
        if args.command=="m8-prepare":
            result=pipe.prepare_run(read_json(args.map),args.root,engine=args.engine,model=args.model,
                max_chars=args.max_chars,ledger_max_chars=args.ledger_max_chars,
                ledger_engine=args.ledger_engine,ledger_model=args.ledger_model,qc_profile=args.qc_profile)
        elif args.command=="m8-status":result=pipe.status(args.root)
        elif args.command=="m8-primary-next":
            from .m4_operator import run_next
            pipe.status(args.root)  # verify complete M8 source and primary plan first
            result=run_next(args.root/'primary_plan',execute=args.execute,
                confirm_subscription=args.confirm_subscription,
                confirm_credit_controls=args.confirm_credit_controls,timeout=args.timeout)
        elif args.command=="m8-ledger-prepare":result=pipe.prepare_ledger(args.root)
        elif args.command=="m8-ledger-next":result=pipe.ledger_run_next(args.root,
                execute=args.execute,confirm_subscription=args.confirm_subscription,
                confirm_credit_controls=args.confirm_credit_controls,timeout=args.timeout)
        elif args.command=="m8-ledger-import":result=pipe.import_ledger_response(args.root,read_json(args.response))
        elif args.command=="m8-ledger-retry":result=pipe.ledger_authorize_retry(args.root,args.chunk,args.reason)
        elif args.command=="m8-ledger-clear-limit":result=pipe.ledger_clear_limit(args.root,args.reason)
        elif args.command=="m8-ledger-recover":result=pipe.recover_ledger_receipt(args.root,args.chunk)
        elif args.command=="m8-finalize":result=pipe.finalize(args.root,export_xlsx=not args.csv_only)
        elif args.command=="m8-crossrefs":
            if args.out.exists():raise FileExistsError('Cross-reference audit output already exists')
            result=pipe.inspect_cross_references(read_json(args.map))
            atomic_json(args.out,result)
        elif args.command=="m8-benchmark":
            from .m8_benchmark import compare_to_reference
            if args.out.exists():raise FileExistsError('Benchmark output already exists')
            result=compare_to_reference(read_json(args.reference),read_json(args.extraction))
            atomic_json(args.out,result)
        else:raise ValueError('Unsupported M8 command')
        print(json.dumps(result,ensure_ascii=False))
        return 2 if result.get('status') in {'FAIL','FAILED_NO_AUTORETRY','FAILED_TIMEOUT_NO_AUTORETRY'} else 0
    if args.command=="m7-prepare":
        from .m7_occurrences import issue_occurrences
        from .m7_triage import compact_packet,triage_document
        mapping=read_json(args.map)
        manifest=issue_occurrences(mapping)
        if args.outdir.exists():
            raise FileExistsError('M7 output directory exists. Use a new versioned path, no destructive overwrite.')
        args.outdir.mkdir(parents=True)
        enriched=dict(mapping)
        enriched['quality_control_profile']='M7_ISSUED_OCCURRENCES'
        enriched['occurrence_manifest_sha256']=manifest['manifest_sha256']
        atomic_json(args.outdir/'m7_map.json',enriched)
        atomic_json(args.outdir/'source_occurrences.json',manifest)
        triage=triage_document(mapping)
        atomic_json(args.outdir/'triage.json',triage)
        focus=compact_packet(mapping,stage='focus',max_chars=args.max_chars)
        rest=compact_packet(mapping,stage='remainder',max_chars=args.max_chars)
        if (set(focus['included_passage_ids'])&set(rest['included_passage_ids']) or
            set(focus['included_passage_ids'])|set(rest['included_passage_ids']) !=
            {p['passage_id'] for p in mapping['passages']}):
            raise AssertionError('Focus and remainder fail source coverage reconciliation')
        atomic_json(args.outdir/'focus_packet.json',focus)
        atomic_json(args.outdir/'remainder_packet.json',rest)
        result={'status':'PREPARED_NO_AI_CALLED_NO_SOURCE_EXCLUDED',
             'document_id':mapping['document_id'],'priority':triage['priority'],
             'occurrences':len(manifest['occurrences']),
             'source_chars_fraction_in_focus':focus['character_budget_proxy']['fraction_of_source_text'],
             'output_dir':str(args.outdir)}
        print(json.dumps(result,ensure_ascii=False))
        return 0
    if args.command=="m7-ledger-tasks":
        from .m7_ledger_tasks import prepare_ledger_tasks
        tasks=prepare_ledger_tasks(read_json(args.map),read_json(args.extraction),max_chars=args.max_chars)
        if args.outdir.exists():raise FileExistsError('M7 ledger task folder exists; create a new path')
        args.outdir.mkdir(parents=True)
        for i,task in enumerate(tasks,1):
            atomic_json(args.outdir/f'ledger_task_{i:04d}.json',task)
        print(json.dumps({'status':'LEDGER_TASKS_PREPARED_NO_AI_CALLED','tasks':len(tasks),
           'output_dir':str(args.outdir)}))
        return 0
    if args.command=="m7-merge-ledger":
        from .m7_ledger_tasks import merge_ledger_chunks
        if args.out.exists():raise FileExistsError('Merged ledger exists; never overwrite')
        result=merge_ledger_chunks(read_json(args.map),read_json(args.extraction),
            [read_json(v) for v in args.response],tasks=[read_json(v) for v in args.task])
        atomic_json(args.out,result)
        print(json.dumps({'status':'ALL_SOURCE_OCCURRENCES_MERGED_NOT_SEMANTICALLY_VERIFIED',
            'output':str(args.out),'occurrences':len(result['occurrence_dispositions'])}))
        return 0
    if args.command=="m7-attach-ledger":
        from .m7_ledger_tasks import attach_ledger
        if args.out.exists():raise FileExistsError('Combined extraction exists; never overwrite')
        result=attach_ledger(read_json(args.map),read_json(args.extraction),read_json(args.ledger))
        atomic_json(args.out,result)
        print(json.dumps({'status':'LEDGER_ATTACHED_REQUIRES_STRICT_M7_VALIDATION',
            'output':str(args.out)}))
        return 0
    if args.command=="m7-validate":
        from .m7_occurrences import issue_occurrences
        mapping=read_json(args.map)
        if mapping.get('quality_control_profile')!='M7_ISSUED_OCCURRENCES':
            raise ValueError('M7 validation requires map prepared with m7-prepare')
        report=validate_extraction(mapping,read_json(args.extraction))
        if args.out.exists() and not args.force:
            raise FileExistsError('QC output exists; do not overwrite immutable prior result')
        atomic_json(args.out,report)
        print(json.dumps({'status':report['deterministic_status'],'output':str(args.out),
            'errors':len(report['errors'])},ensure_ascii=False))
        return 0 if report['deterministic_status']=='PASS_DETERMINISTIC_ONLY' else 2
    if args.command == "m5-probe-manifest":
        # Never allow a stale report to be silently accepted when the source changes.
        if args.out.exists() and not args.force:
            raise FileExistsError("M5 probe report already exists; use a new path or --force")
        result=probe_manifest(args.fixtures, read_json(args.manifest))
        atomic_json(args.out,result)
        print(json.dumps({"status":result["status"],"cases":len(result["results"]),
                          "anchors":sum(len(r["anchors"]) for r in result["results"]),"output":str(args.out)}))
        return 0 if result["status"]=="ALL_ANCHORS_PASS_NOT_RECALL_VALIDATED" else 2
    if args.command.startswith("m4-"):
        if args.command=="m4-plan":
            source=read_json(args.map);packet=read_json(args.packet)
            project=Path(__file__).resolve().parents[2]
            instructions=(project/"prompts"/"FIRST_READER.md").read_text(encoding="utf-8")
            schema=read_json(project/"schemas"/"m2_extraction.schema.json")
            result=create_plan(source,packet,args.outdir,engine=args.engine,model=args.model,
                               instructions=instructions,schema=schema)
        elif args.command=="m4-status":result=m4_status(args.plan)
        elif args.command=="m4-run-next":
            result=m4_run_next(args.plan,execute=args.execute,
                    confirm_subscription=args.confirm_subscription,
                    confirm_credit_controls=args.confirm_credit_controls,timeout=args.timeout)
        elif args.command=="m4-authorize-retry":
            result=m4_authorize_retry(args.plan,args.task_id,args.reason)
        elif args.command=="m4-clear-limit":result=m4_clear_limit(args.plan,args.reason)
        elif args.command=="m4-recover-result":
            result=m4_recover_saved_result(args.plan,args.task_id,confirmed=args.confirm_recovery)
        elif args.command=="m4-merge-plan":result=m4_merge_plan(args.plan)
        else:raise ValueError("Unhandled M4 command")
        print(json.dumps(result,ensure_ascii=False))
        return (2 if result.get("status","") == "FAIL" or result.get("status","").startswith("FAILED") else 0)
    if args.command.startswith("m3-"):
        if args.command == "m3-init":
            result=m3_init(args.workspace)
        elif args.command == "m3-register-map":
            result=register_map(args.workspace,read_json(args.map))
        elif args.command == "m3-ingest":
            result=register_extraction(args.workspace,args.document_id,read_json(args.extraction),select=args.select)
        elif args.command == "m3-select":
            result=select_attempt(args.workspace,args.document_id,args.sha256)
        elif args.command == "m3-second-reader":
            result=register_second_reader(args.workspace,args.document_id,read_json(args.extraction))
        elif args.command == "m3-status":
            docs=list_documents(args.workspace)
            from collections import Counter
            result={"schema":"m3-status.1", "documents":len(docs),
                    "states":dict(Counter(d["state"] for d in docs)),
                    "jobs":[{"document_id":d["document_id"],"state":d["state"],
                             "attempts":len(d["attempts"]),"ai_reviews":len(d["ai_reviews"]),"selected_sha256":d["selected_sha256"]}
                            for d in docs]}
            if args.out:atomic_json(args.out,result)
        elif args.command == "m3-merge-chunks":
            if args.out.exists() and not args.force:
                raise FileExistsError("Merged output exists; use --force explicitly")
            merged,report=merge_chunks(read_json(args.map),read_json(args.packet),[read_json(x) for x in args.chunk])
            atomic_json(args.out,merged)
            atomic_json(str(args.out)+".merge-report.json",report)
            result={"status":report["deterministic_status"],"output":str(args.out),
                    "report":str(args.out)+".merge-report.json"}
            print(json.dumps(result))
            return 0 if report["deterministic_status"]=="PASS_DETERMINISTIC_ONLY" else 2
        elif args.command == "m3-validate-linkage":
            docs=list_documents(args.workspace)
            v=validate_linkage(read_json(args.linkage),docs)
            result={"status":"LINKAGE_SCHEMA_VALID_NOT_SUBSTANTIVELY_VERIFIED", 
                    "group_count":len(set(x["agreement_id"] for x in v["group_for"].values())),
                    "relationships":len(v["relations"]),
                    "unreconciled_duplicates":v["exact_text_duplicates_unreconciled"]}
        elif args.command == "m3-export":
            if args.outdir.exists() and any(args.outdir.iterdir()) and not args.force:
                raise FileExistsError("Export directory is not empty; specify --force or a new empty directory")
            linkage=read_json(args.linkage) if args.linkage else default_linkage()
            rows=build_rows(args.workspace,linkage)
            outputs=[]
            if args.format in {"csv","both"}:
                write_csvs(rows,args.outdir/"csv")
                outputs.append("csv/")
            if args.format in {"xlsx","both"}:
                fn=args.outdir/"Royalty_Research_Historical_Staging.xlsx"
                write_xlsx(rows,fn)
                outputs.append(fn.name)
            manifest=export_manifest(rows,args.workspace,linkage,outputs)
            # Persist exact output file fingerprints so an exported workbook or
            # CSV cannot be modified without detection by a subsequent reviewer.
            manifest["file_sha256"]={str(p.relative_to(args.outdir)):sha256(p.read_bytes())
                for p in sorted(args.outdir.rglob("*")) if p.is_file() and p.name!="export_manifest.json"}
            atomic_json(args.outdir/"export_manifest.json",manifest)
            result={"status":"EXPORTED_ALL_EXTRACTIONS_WITH_AUTOMATED_QC_STATUS",
                    "output":str(args.outdir),"row_counts":manifest["sheet_row_counts"],
                    "snapshot_sha256":manifest["snapshot_sha256"]}
        else:
            raise ValueError("Unhandled M3 command")
        print(json.dumps(result,ensure_ascii=False))
        return 0
    if args.command in {"make-packets", "validate-extraction", "blind-rekey", "compare-extractions"}:
        # Never skip an extraction/QC report simply because an output filename
        # already exists. A changed source/model result or packet option must
        # invalidate the idempotency fingerprint.
        mapping = read_json(args.map)
        inputs = {"command": args.command, "map": mapping}
        if args.command in {"validate-extraction", "blind-rekey"}:
            inputs["extraction"] = read_json(args.extraction)
        elif args.command == "compare-extractions":
            inputs["first"] = read_json(args.first)
            inputs["second"] = read_json(args.second)
        else:
            inputs.update({"mode":args.mode,"max_chars":args.max_chars,
                           "neighbor_radius":args.neighbor_radius,"sample_fraction":args.sample_fraction})
        request_sha256 = sha256(json_bytes(inputs))
        if args.out.exists():
            if args.skip_existing:
                existing = read_json(args.out)
                if not isinstance(existing,dict) or existing.get("request_sha256") != request_sha256:
                    raise ValueError("Cannot skip stale M2 artifact: source, extraction, or options differ")
                print(f"SKIP_VALIDATED {args.out}")
                return 0
            if not args.force:
                raise FileExistsError(f"Output exists; use --force or --skip-existing: {args.out}")
        if args.command == "make-packets":
            record = make_packets(mapping, mode=args.mode, max_chars=args.max_chars,
                                  neighbor_radius=args.neighbor_radius, sample_fraction=args.sample_fraction)
        elif args.command == "validate-extraction":
            record = validate_extraction(mapping,read_json(args.extraction))
        elif args.command == "blind-rekey":
            record = make_blind_rekey_packet(mapping,read_json(args.extraction))
        else:
            record = compare_independent_extractions(mapping,read_json(args.first),read_json(args.second))
        record["request_sha256"] = request_sha256
        atomic_json(args.out, record)
        print(json.dumps({"status": record.get("deterministic_status") or record.get("status") or "PACKET_PREPARED",
                          "output": str(args.out), "document_id":mapping["document_id"]}))
        return 2 if record.get("deterministic_status") == "FAIL" else 0

    if args.command == "validate-map":
        errors = validate_map(read_json(args.input))
        print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}))
        return 0 if not errors else 2

    if not _available(args.out, force=args.force, skip_existing=args.skip_existing):
        if args.command == "map":
            old = read_json(args.out)
            failures = validate_map(old)
            if failures:
                raise ValueError(f"Existing map invalid; will not silently skip: {failures}")
        else:
            old = read_jsonl(args.out)
            if not isinstance(old, list) or any(not isinstance(row, dict) for row in old):
                raise ValueError("Existing JSONL output corrupt; cannot skip")
        return 0

    def clear_prior_failure():
        p = Path(str(args.out) + ".failed.json")
        if p.exists():
            p.unlink()

    if args.command == "discover":
        days = (args.end - args.start).days + 1
        if days < 1 or args.max_days < 1 or days > args.max_days:
            raise ValueError(f"Search window {days} days is invalid/too long; run bounded daily or monthly tasks")
        records = discover(_client(args), args.query, args.start, args.end)
        atomic_jsonl(args.out, records)
        clear_prior_failure()
        print(json.dumps({"status": "COMPLETE_WITHIN_SEARCH_QUERIES", "unique_hits": len(records),
                          "contract_exhibits": sum(r["candidate_route"] == "CONTRACT_EXHIBIT" for r in records),
                          "output": str(args.out)}))
        return 0

    if args.command == "master-index":
        url = index_url(args.year, args.quarter)
        raw = args.input.read_bytes() if args.input else _client(args).fetch(url)
        text = raw.decode("utf-8-sig", errors="strict")
        forms = set(s.upper() for s in args.form) if args.form else None
        records = parse_master_idx(text, forms=forms)
        atomic_jsonl(args.out, records)
        clear_prior_failure()
        print(json.dumps({"status": "COMPLETE_FOR_SELECTED_INDEX", "filings": len(records), "source": url, "output": str(args.out)}))
        return 0

    if args.command == "filing-inventory":
        from .discovery import source_url
        url = source_url(args.cik, args.accession, args.accession + "-index.html")
        raw = args.input.read_bytes() if args.input else _client(args).fetch(url)
        records = parse_filing_index_html(raw.decode("utf-8-sig"), args.cik, args.accession)
        atomic_jsonl(args.out, records)
        clear_prior_failure()
        print(json.dumps({"status": "COMPLETE_FOR_SELECTED_FILING", "documents": len(records), "output": str(args.out)}))
        return 0

    if args.command == "map":
        # Map failures receive a durable exception record, not an empty/successful result.
        try:
            raw, fetched_at = _read_source(args)
            filename = (args.input.name if args.input else args.url.split("/", 1)[-1].split("/")[-1].split("?")[0])
            paragraphs, parser_type = parse_document(raw, filename)
            source = args.source_url or args.url
            doc = {"document_id": args.document_id, "source_url": source, "filename": filename,
                   "input_mode": "LOCAL" if args.input else "SEC_LIVE"}
            mapped = map_contract(paragraphs, doc, raw_hash=sha256(raw), fetched_at=fetched_at, parser_type=parser_type,
                                  segment_chars=args.segment_chars)
            problems = validate_map(mapped)
            if problems:
                raise ValueError("Map validation failed: " + ", ".join(problems))
            atomic_json(args.out, mapped)
            clear_prior_failure()
            print(json.dumps({"status": "MAPPED_NOT_INTERPRETED", "passages": mapped["total_passages"],
                              "candidates": mapped["total_candidates"], "output": str(args.out)}))
            return 0
        except Exception as exc:
            atomic_json(str(args.out) + ".failed.json", {
                "status": "EXCEPTION", "failure_type": type(exc).__name__,
                "message": str(exc), "at_utc": utc_now(),
                "source": args.url or str(args.input),
            })
            raise
    raise ValueError("Unhandled command")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError, UnicodeError) as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        if hasattr(args, "out") and not isinstance(exc, FileExistsError):
            # Every failed command leaves a machine-readable exception, while
            # preserving any already completed output for independent review.
            failure_path = str(args.out) + ".failed.json"
            atomic_json(failure_path, {
                "status": "EXCEPTION", "failure_type": type(exc).__name__,
                "message": str(exc), "command": args.command, "at_utc": utc_now(),
            })
        return 2


if __name__ == "__main__":
    sys.exit(main())
