"""Source-faithful, non-publishing workbook row sets for local Excel/CSV.

No field is silently selected from an amendment or converted into a currently
operative term. All rate rows are source-document-specific observations.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

from .m3_workspace import list_documents
from .m3_linkage import default_linkage, validate_linkage, agreement_of
from .storage import json_bytes, sha256, atomic_json, utc_now

EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_CHARS = 32_767
HEADERS={
 "Overview": ["Metric","Value","Interpretation"],
 "Agreements": ["Agreement_ID","Link_Status","Document_Count","Document_IDs","Title_Provisional","Licensor_Provisional","Licensee_Provisional","Historical_Not_Current","Grouping_Comment"],
 "Documents": ["Document_ID","Agreement_ID","Link_Status","Source_URL","Open_Source","CIK","Accession","Filing_Date","Exhibit_Type","Source_Filename","Retrieved_UTC","Text_SHA256","Original_SHA256","Extraction_Status","Selected_Extraction_SHA256","Amendment_Review_Status","Title","Licensor","Licensee","Industry","Licensed_IP","Executed","Effective","Duration","Territory","Exclusivity","Contract_Status","Warnings_Count","Errors_Count","High_Open_Issues","Second_AI_Review_Status","Reader_Engine","Reader_Model","Reader_Scope"],
 "Royalty Terms": ["Observation_ID","Document_ID","Agreement_ID","Term_ID","Family","Structure","Rate_Value_Text","Rate_Numeric","Rate_Unit","Royalty_Base","Base_Definition","Product_Scope","Territory","Effective_Period","Disclosure_Status","Tier_Count","Condition_Count","Adjustment_Count","Evidence_IDs","Rate_Evidence_IDs","Base_Evidence_IDs","Source_URL","QC_State","Historical_Not_Current"],
 "Tiers": ["Observation_ID","Document_ID","Agreement_ID","Term_ID","Sequence","Rate_Value_Text","Rate_Numeric","Rate_Unit","Lower_Threshold_Text","Lower_Numeric","Upper_Threshold_Text","Upper_Numeric","Calculation","Measurement_Period","Threshold_Basis","Evidence_IDs","Source_URL","QC_State"],
 "Other Payments": ["Payment_Record_ID","Document_ID","Agreement_ID","Payment_ID","Kind","Amount_Text","Currency","Basis","Condition","Evidence_IDs","Source_URL","QC_State","Amount_Numeric","Disclosure_Status"],
 "Source Flags": ["Document_ID","Agreement_ID","Flag_ID","Passage_ID","Kind","Severity","Value","Role","Resolution_Status","Resolution_Type","Linked_Record","Source_Excerpt","Source_URL"],
 "Evidence": ["Evidence_Record_ID","Document_ID","Agreement_ID","Evidence_ID","Passage_ID","Role","Exact_Quotation","Source_URL","Passage_Section","Extraction_SHA256"],
 "Conditions": ["Condition_Record_ID","Document_ID","Agreement_ID","Term_ID","Condition_Text","Evidence_IDs","Source_URL"],
 "Adjustments": ["Adjustment_Record_ID","Document_ID","Agreement_ID","Term_ID","Adjustment_Description","Evidence_IDs","Source_URL"],
 "Amendments": ["From_Document_ID","To_Document_ID","Agreement_ID","Relation","Effective_Date","Supersession_Scope","Evidence_Status","Basis","DO_NOT_INFER_CURRENT_RATE"],
 "QC": ["Document_ID","Agreement_ID","State","Deterministic_Result","Errors","Warnings","High_Unresolved_Issues","Read_Scope","Candidate_Passages","Source_Passages","Second_AI_Review_Status","Source_URL","Selected_Extraction_SHA256","M11_Flag_Status","M11_Hard_Open","M11_Supporting_Open","M12_Flag_Status","M12_Hard_Open","M12_Supporting_Open","M12_Unflagged_Financial_Candidates"],
 "Open Issues": ["Document_ID","Agreement_ID","Issue_ID","Severity","Kind","Description","Status","Source_Passage_IDs","Source_URL"],
 "Pending Jobs": ["Document_ID","State","Attempt_Count","Selected_Extraction_SHA256","Source_URL","What_Next"],
 "Data Dictionary": ["Sheet","Purpose","Caution"],
}


def _number(value):
    """Add optional Excel-sortable value while preserving exact textual amount.

    Excel numeric precision is limited; return blank if more than 15 significant
    digits are present. Redactions and formulas remain absent, never zero.
    """
    from .m2_validation import _plain_number   # RF-08: "$500,000" / "50,000.00" are numbers
    value=_plain_number(value)
    if not isinstance(value,str) or not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?",value):
        return None
    try:
        d=Decimal(value)
        sig=len(d.as_tuple().digits)
        if d.is_finite() and sig<=15 and abs(d)<=Decimal('1e14'):
            return float(d)
    except (ValueError,InvalidOperation):pass
    return None


def _txt(value):
    if value is None:return ""
    if type(value) in (int,float,bool):return value
    if isinstance(value,(list,dict)):
        value=json.dumps(value,ensure_ascii=False,sort_keys=True)
    elif not isinstance(value,(str,int,float,bool)):
        raise ValueError("Unsupported export cell type")
    value=str(value)
    if len(value)>EXCEL_MAX_CHARS:
        raise ValueError("Source content exceeds Excel cell limit; must store across linked evidence segments without truncating")
    # CSV/Excel formula injection. Preserve the literal leading character in the
    # saved files (Excel's in-cell apostrophe is intentional; no formulas needed).
    if value and (value[0] in "=+@" or (value[0]=="-" and not re.fullmatch(r"-\d+(?:\.\d+)?",value))
                  or value[0] in "\t\r\n"):
        value="'"+value
    return value


def sec_identifiers(mapping):
    """Preserve known M1 metadata; derive only mechanically verifiable URL IDs.

    Accession/CIK inferred from SEC URL is an identifier, not verification that
    the source is accessible, complete, or actually a licensing agreement.
    """
    meta=mapping.get("document_metadata") or {}
    url=mapping.get("source_url")
    values={k:meta.get(k) for k in ("cik","accession","filing_date","file_type","filename")}
    if official_sec_url(url):
        parts=urlparse(url).path.split("/")
        # ['', 'Archives','edgar','data', CIK, access18, filename, ...]
        if len(parts)>=7 and parts[4].isdigit() and re.fullmatch(r"\d{18}",parts[5]):
            values["cik"]=values.get("cik") or str(int(parts[4]))
            d=parts[5]
            values["accession"]=values.get("accession") or f"{d[:10]}-{d[10:12]}-{d[12:]}"
            values["filename"]=values.get("filename") or parts[6]
    return values


def official_sec_url(url):
    if not isinstance(url,str):return False
    try:
        p=urlparse(url)
        return p.scheme=="https" and p.hostname in {"www.sec.gov","sec.gov"} and p.path.startswith("/Archives/edgar/data/")
    except ValueError:
        return False


def _row(sheet, *values):
    cols=HEADERS[sheet]
    if len(values)!=len(cols):
        raise AssertionError(f"Bad row for {sheet}: {len(values)} != {len(cols)}")
    return [_txt(x) for x in values]


def build_rows(root, linkage=None):
    docs=list_documents(root)
    if linkage is None:linkage=default_linkage()
    checked=validate_linkage(linkage,docs)
    rows={name:[header.copy()] for name,header in HEADERS.items()}
    status_count=Counter(x["state"] for x in docs)
    group_docs=defaultdict(list)
    for doc in docs:
        did=doc["document_id"]
        gid,gstatus=agreement_of(did,checked)
        group_docs[gid].append((doc,gstatus))
    for group_id in sorted(group_docs):
        members=group_docs[group_id]
        names=[v["selected"]["agreement"] for v,_ in members if v["selected"]]
        title=names[0].get("title") if len(names)==1 else "MULTIPLE_SOURCES_ASK_REVIEW"
        licensor=names[0].get("licensor") if len(names)==1 else "MULTIPLE_SOURCES_ASK_REVIEW"
        licensee=names[0].get("licensee") if len(names)==1 else "MULTIPLE_SOURCES_ASK_REVIEW"
        link_status=members[0][1]
        rows["Agreements"].append(_row("Agreements",group_id,link_status,len(members),
            ", ".join(doc["document_id"] for doc,_ in members),title,licensor,licensee,
            "HISTORICAL_TERMS_ONLY", "Manual grouping never implies current effective royalty"))
    for doc in docs:
        did=doc["document_id"]
        m=doc["map"]
        ext=doc["selected"]
        qc=doc["qc"] or {"deterministic_status":"NOT_RUN","errors":[],"warnings":[]}
        gid,gstatus=agreement_of(did,checked)
        url=m.get("source_url") or ""
        identifiers=sec_identifiers(m)
        a=ext.get("agreement",{}) if ext else {}
        info=ext.get("reader",{}) if ext else {}
        open_high=[x for x in (ext.get("open_issues",[]) if ext else []) if x.get("status")!="RESOLVED" and x.get("severity") in {"HIGH","CRITICAL"}]
        ai_reviews=doc.get("ai_reviews",[])
        ai_label=("REVIEW_REQUIRED" if any(r["comparison"]["status"]=="REVIEW_REQUIRED" for r in ai_reviews)
                 else "NO_DETECTED_DISAGREEMENT_NOT_PROOF" if ai_reviews else "NOT_PERFORMED")
        rows["Documents"].append(_row("Documents",did,gid,gstatus,url,"SEC SOURCE" if official_sec_url(url) else "",
                identifiers.get("cik"),identifiers.get("accession"),identifiers.get("filing_date"),
                identifiers.get("file_type"),identifiers.get("filename"),m.get("retrieved_at_utc"),
                m["text_sha256"],m.get("original_sha256"),
                doc["state"],doc["selected_sha256"],ext.get("amendment_status") if ext else "NOT_CHECKED",
                a.get("title"),a.get("licensor"),a.get("licensee"),a.get("industry"),a.get("licensed_ip"),
                a.get("execution_date"),a.get("effective_date"),a.get("duration"),a.get("territory"),
                a.get("exclusivity"),a.get("contractual_status"),len(qc["warnings"]),len(qc["errors"]),
                len(open_high),ai_label,info.get("engine"),info.get("model"),info.get("read_scope")))
        m11=qc.get('m11_source_flags') or {}
        m12=qc.get('m12_source_flags') or {}
        rows["QC"].append(_row("QC",did,gid,doc["state"],qc["deterministic_status"],
                "; ".join(x["code"] for x in qc["errors"]),"; ".join(x["code"] for x in qc["warnings"]),
                len(open_high),info.get("read_scope"),m.get("total_candidates"),m.get("total_passages"),
                ai_label,url,doc["selected_sha256"],m11.get('status'),m11.get('hard_open'),m11.get('warning_open'),
                m12.get('status'),m12.get('hard_open'),m12.get('warning_open'),
                m12.get('unflagged_financial_candidate_count')))
        if doc["state"]=="AWAITING_EXTRACTION":next_step="Obtain subscription AI extraction JSON; run m3-ingest"
        elif doc["state"]=="QC_FAILED":next_step="Review QC errors against original clauses and ingest corrected attempt"
        elif doc["state"]=="QC_PASSED_OPEN_HIGH_ISSUE":next_step="Resolve high or critical issues; do not publish"
        elif doc["state"]=="QC_PASSED_AI_DISAGREEMENT":next_step="Resolve independent AI discrepancies; do not publish"
        else:next_step="Review source status and unresolved semantic uncertainty if needed; no approval gate"
        rows["Pending Jobs"].append(_row("Pending Jobs",did,doc["state"],len(doc["attempts"]),
                    doc["selected_sha256"],url,next_step))
        if m11 or m12:
            if m12:
                from .m12_economic_qc import issue_signals
            else:
                from .m11_signal_qc import issue_signals
            flags=issue_signals(m)['signals']
            closed={x['signal_id']:x for x in (m12 or m11).get('closed',[])}
            for flag in flags:
                answer=closed.get(flag['signal_id'])
                rows["Source Flags"].append(_row("Source Flags",did,gid,flag['signal_id'],
                    flag['passage_id'],flag['kind'],flag['severity'],flag.get('value'),
                    flag.get('role'),'CLOSED_VERIFIED_BINDING' if answer else 'OPEN',
                    answer.get('resolution') if answer else None,
                    answer.get('target') if answer else None,flag.get('excerpt'),url))
        if not ext:continue
        section_by_passage={p["passage_id"]:p.get("section_guess") for p in m["passages"]}
        for e in ext.get("evidence",[]):
            rows["Evidence"].append(_row("Evidence", f"{did}:{e['evidence_id']}",did,gid,e["evidence_id"],
                e["passage_id"],e.get("role"),e["quote"],url,section_by_passage.get(e["passage_id"]),doc["selected_sha256"]))
        for t in ext.get("royalty_terms",[]):
            obs=f"{did}:{t['term_id']}"
            rows["Royalty Terms"].append(_row("Royalty Terms",obs,did,gid,t["term_id"],t["family"],t["structure"],
                t.get("rate_value"),_number(t.get("rate_value")),t.get("rate_unit"),t.get("base"),t.get("base_definition"),
                t.get("product_scope"),t.get("territory_scope"),t.get("effective_period"),
                t.get("disclosure_status"),len(t.get("tiers",[])),len(t.get("conditions",[])),
                len(t.get("adjustments",[])),t.get("evidence_ids"),t.get("rate_evidence_ids"),
                t.get("base_evidence_ids"),url,doc["state"],"HISTORICAL_NOT_CURRENT") )
            for tier in t.get("tiers",[]):
                rows["Tiers"].append(_row("Tiers",obs,did,gid,t["term_id"],tier.get("sequence"),
                    tier.get("rate_value"),_number(tier.get("rate_value")),tier.get("rate_unit"),tier.get("lower"),_number(tier.get("lower")),tier.get("upper"),_number(tier.get("upper")),
                    tier.get("calculation"),tier.get("measurement_period"),tier.get("threshold_basis"),
                    tier.get("evidence_ids"),url,doc["state"]))
            for seq,cond in enumerate(t.get("conditions",[]),1):
                rows["Conditions"].append(_row("Conditions",f"{obs}:C{seq}",did,gid,t["term_id"],cond.get("text"),
                    cond.get("evidence_ids"),url))
            for seq,adj in enumerate(t.get("adjustments",[]),1):
                rows["Adjustments"].append(_row("Adjustments",f"{obs}:A{seq}",did,gid,t["term_id"],adj.get("description"),
                    adj.get("evidence_ids"),url))
        for pay in ext.get("other_payments",[]):
            rows["Other Payments"].append(_row("Other Payments",f"{did}:{pay['payment_id']}",did,gid,
                    pay["payment_id"],pay["kind"],pay.get("amount_value"),pay.get("currency"),pay.get("basis"),
                    pay.get("condition"),pay.get("evidence_ids"),url,doc["state"],
                    _number(pay.get('amount_value')),
                    pay.get('disclosure_status') or ('REDACTED' if pay.get('amount_value') is None else 'DISCLOSED')))
        for issue in ext.get("open_issues",[]):
            rows["Open Issues"].append(_row("Open Issues",did,gid,issue["issue_id"],issue["severity"],
                    issue["kind"],issue["description"],issue["status"],issue.get("passage_ids"),url))
    for r in checked["relations"]:
        g,_=agreement_of(r["from_document"],checked)
        rows["Amendments"].append(_row("Amendments",r["from_document"],r["to_document"],g,r["relation"],
                r.get("effective_date"),r["supersession_scope"],r["review_status"],
                r["basis"],"No rate automatically superseded"))
    remarks=[
       ("Total source documents",len(docs),"Documents are SEC filing items, NOT unique licensing agreements"),
       ("Provisional agreement groups",len(group_docs),"Includes one provisional group per unlinked document"),
       ("Documents with QC-passed extraction",sum(x["state"] in {"QC_PASSED_NOT_PROFESSIONALLY_VERIFIED","QC_PASSED_OPEN_HIGH_ISSUE"} for x in docs),"NOT equivalent to recall or professional correctness"),
       ("Failed/pending extraction",sum(x["state"] in {"AWAITING_EXTRACTION","QC_FAILED"} for x in docs),"These records remain in the workbook"),
       ("High unresolved issue records",status_count["QC_PASSED_OPEN_HIGH_ISSUE"],"Not eligible for curated export"),
       ("Unreconciled exact-text source duplicates",len(checked["exact_text_duplicates_unreconciled"]),"M3 never automatically deduplicates or discards sources"),
       ("Workbook scope","HISTORICAL NOT CURRENT","Amendment/effective economics require separate interpretation"),
       ("Inference billing","NONE","Local scripts do not invoke AI model APIs"),
    ]
    for x in remarks:rows["Overview"].append(_row("Overview",*x))
    defs={
        "Agreements":"Curated linkage groups and provisional one-document groups; not verified distinct transaction count",
        "Documents":"One per SEC mapped source; status and source hash bound to chosen extraction",
        "Royalty Terms":"Source-document-specific royalty rules, not contract-level unique observations",
        "Tiers":"A separate row per royalty rate tier; amounts and bounds remain literal strings",
        "Other Payments":"Upfront, milestone, interest, guarantee, and other items, not automatically running royalties",
        "Evidence":"Exact source excerpts and passage IDs; full map retained in workspace",
        "Conditions":"Conditions linked to each royalty term",
        "Adjustments":"Rate reductions and offsets linked to each royalty term",
        "Amendments":"Source-evidenced or proposed relationships; no automatic operative-rate decisions",
        "QC":"Machine checks only; PASS is not proof of correct legal/economic interpretation",
        "Open Issues":"Ambiguity/redactions and unresolved blockers",
        "Pending Jobs":"Includes incomplete/failed sources; no silent omissions from research log",
    }
    for name,description in defs.items():
        rows["Data Dictionary"].append(_row("Data Dictionary",name,description,
                               "Facts and historical rates require source and point-of-use professional review"))
    for name,values in rows.items():
        if len(values)>EXCEL_MAX_ROWS:raise ValueError(f"Excel row limit exceeded in {name}; partition exports")
    return rows


def write_csvs(rows: dict, directory):
    dest=Path(directory)
    dest.mkdir(parents=True,exist_ok=True)
    for name,table in rows.items():
        file=dest/(re.sub(r"[^A-Za-z0-9]+","_",name).lower()+".csv")
        tmp=file.with_suffix(".tmp")
        with open(tmp,"w",encoding="utf-8-sig",newline="") as f:
            writer=csv.writer(f)
            writer.writerows(table)
        tmp.replace(file)
    return str(dest)


def export_manifest(rows, workspace, linkage, output_files):
    documents=list_documents(workspace)
    out={"schema":"m3-export-manifest.1", "at_utc":utc_now(),
         "workspace":str(Path(workspace).resolve()),
         "linkage_sha256":sha256(json_bytes(linkage or default_linkage())),
         "document_inputs":[{"document_id":x["document_id"],
             "text_sha256":x["map"]["text_sha256"],
             "extraction_sha256":x["selected_sha256"]} for x in documents],
         "sheet_row_counts":{name:len(table)-1 for name,table in rows.items()},
         "sheet_content_sha256":{name:sha256(json_bytes(table)) for name,table in rows.items()},
         "outputs":output_files,
         "notice":"Export of historical extraction staging records. No automatic audit approval or proof of completeness."}
    out["snapshot_sha256"]=sha256(json_bytes({k:v for k,v in out.items() if k not in {"at_utc","outputs","workspace"}}))
    return out
