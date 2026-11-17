"""Fail-closed M2 source-grounded deterministic checks.

This module does not check legal/economic meaning. It verifies that claimed
numbers and quotations are source-anchored and potential omissions are explicit.
Never equate its PASS with professional verification or measured recall.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from .mapping import validate_map, PERCENT
from .m2_schema_check import validate_shape
from .storage import sha256

M2_SCHEMA = "m2.0"
# Processing semantics change when new automatic rejection conditions are added.
# M3 records the revision to avoid silently grandfathering old QC results.
M2_VALIDATOR_REVISION = "m10.0-source-led-and-unchanged-extraction-history"
M12_VALIDATOR_REVISION = 'm12.0-economic-source-signals'
M11_VALIDATOR_REVISION = "m11.0-typed-flags-source-bound"
TERMFAMILIES = {"PRODUCT_SALES", "SUBLICENSING_RECEIPTS", "PER_UNIT", "USAGE", "REVENUE_SHARE", "OTHER"}
STRUCTURES = {"FLAT", "TIERED", "STEP_UP", "STEP_DOWN", "HYBRID", "FORMULA", "UNKNOWN"}
RATES = {"PERCENT", "CURRENCY_PER_UNIT", "FORMULA", "REDACTED", "UNKNOWN"}
DISCLOSURES = {"DISCLOSED", "REDACTED", "AMBIGUOUS", "NOT_VERIFIED"}
CATEGORIES = {"ROYALTY_TERM", "OTHER_PAYMENT", "DEFINITION", "CROSS_REFERENCE", "REDACTED",
              "DUPLICATE", "UNRELATED_PERCENT", "BACKGROUND", "UNCERTAIN"}
ISSUE_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
SPELLED = {"zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
           "eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,
           "fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,"nineteen":19,
           "twenty":20,"twenty-five":25,"thirty":30,"forty":40,"fifty":50,"sixty":60,
           "seventy":70,"eighty":80,"ninety":90,"one hundred":100}


def _plain_number(value):
    """RF-08 (v0.8.1-review): accept the two harmless renderings models actually produce for an
    amount or threshold - a leading currency sign and thousands separators ("$500,000",
    "50,000.00") - and return the plain decimal string. Anything else is returned unchanged.
    In the live Market Finders run 16 of 38 QC errors were this formatting alone."""
    if isinstance(value, str):
        m = re.fullmatch(r"\s*(?:US\$|\$)?\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*", value)
        if m:
            return m.group(1).replace(",", "") + (m.group(2) or "")
    return value


def _decimal(value):
    value = _plain_number(value)
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", value):
        return None
    try:
        d = Decimal(value)
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _numeric_in_quotes(num, evidence_ids, evidence_by_id, unit):
    """A necessary check, not proof that the value has correct contractual meaning."""
    val = _decimal(num)
    if val is None:
        return False
    for eid in evidence_ids or []:
        if eid not in evidence_by_id:
            continue
        quote = evidence_by_id[eid].get("quote", "")
        # Normalized decimal characters with optional commas and trailing zeros.
        for m in re.finditer(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?!\w)", quote):
            try:
                if Decimal(m.group().replace(",", "")) == val:
                    if unit != "PERCENT":
                        return True
                    around = quote[max(0, m.start()-4):min(len(quote), m.end()+16)]
                    if re.search(r"%|per\s*cent|percent", around, re.I):
                        return True
            except InvalidOperation:
                pass
        if unit == "PERCENT":
            for phrase, number in SPELLED.items():
                if Decimal(number) != val:
                    continue
                if re.search(r"\b"+re.escape(phrase)+r"\s+(?:per\s+cent|percent)\b",quote,re.I):
                    return True
    return False


def _error_report(document_id, errors, warnings, checks):
    return {
        "document_id": document_id, "schema": "m2-qc.1",
        "deterministic_status": "FAIL" if errors else "PASS_DETERMINISTIC_ONLY",
        "can_claim_complete": False, "verification_scope": "AUTOMATED_DETERMINISTIC_ONLY",
        "errors": errors, "warnings": warnings, "checks": checks,
        "notice": "Numbers/quotes/coverage bookkeeping checks are not semantic validation or measured recall.",
    }


def validate_extraction(mapping: dict, extraction: dict) -> dict:
    """Check the complete structured output of ONE M1 document. No model invocation.

    Extraction schema and provenance are strict; however fields outside the rate
    economics remain nullable and explicitly unverified rather than inferred.
    """
    errs, warns, checks = [], [], []
    def err(code, msg, ref=None): errs.append({"code":code,"message":msg,"ref":ref})
    def warn(code,msg,ref=None): warns.append({"code":code,"message":msg,"ref":ref})
    def check(code,ok): checks.append({"check":code,"status":"PASS" if ok else "FAIL"})
    if not isinstance(mapping, dict) or not isinstance(extraction, dict):
        return _error_report(None, [{"code":"INVALID_INPUT","message":"Both must be objects","ref":None}], [], [])
    if mapping.get("quality_control_profile") == "M13_TWO_READER":
        # M13: certain source checks only (quotes, numbers, evidence, coverage). Completeness is
        # addressed by the optional independent second reader, not by keyword rules.
        from .m13_two_reader import source_check
        return source_check(mapping, extraction)
    for problem in validate_shape(extraction):
        err("M2_SCHEMA_VIOLATION", problem)
    issues = validate_map(mapping)
    if issues:
        err("INVALID_M1_MAP", ", ".join(issues))
        return _error_report(mapping.get("document_id"),errs,warns,checks)
    doc_id = mapping["document_id"]
    if extraction.get("schema_version") != M2_SCHEMA:
        err("WRONG_SCHEMA_VERSION", "Expected m2.0")
    if extraction.get("document_id") != doc_id:
        err("WRONG_DOCUMENT", "Document ID is not bound to the source map")
    if extraction.get("source_text_sha256") != mapping["text_sha256"]:
        err("SOURCE_HASH_MISMATCH", "Mapped source-text checksum does not match")
    if extraction.get("source_url") != mapping.get("source_url"):
        err("SOURCE_URL_MISMATCH", "Source URL must match mapped document")
    passages = {p["passage_id"]: p for p in mapping["passages"]}
    candidate_ids = set(mapping["candidate_passages"])
    reader = extraction.get("reader")
    if not isinstance(reader,dict):
        err("READER_METADATA_MISSING", "Reader metadata required")
        reader={}
    for fld in ("engine", "model", "run_id"):
        if not isinstance(reader.get(fld),str) or not reader[fld].strip():
            err("READER_FIELD_MISSING",f"Reader {fld} required")
    scope = reader.get("read_scope")
    if scope not in {"SELECTED_PASSAGES", "FULL_DOCUMENT", "HUMAN_MANUAL"}:
        err("UNKNOWN_READ_SCOPE", "Read scope must be explicit")
    reviewed = reader.get("reviewed_passage_ids")
    if not isinstance(reviewed,list) or any(x not in passages for x in reviewed) or len(set(reviewed))!=len(reviewed):
        err("INVALID_REVIEWED_PASSAGES", "Reviewed passage IDs must be unique and source-bound")
        reviewed=[]
    if candidate_ids - set(reviewed):
        err("UNREAD_CANDIDATES", "Some flagged candidate passages not recorded as read", sorted(candidate_ids-set(reviewed))[:12])
    if scope == "FULL_DOCUMENT" and set(reviewed) != set(passages):
        err("INCOMPLETE_FULL_READ_CLAIM", "Full document claim without all passage IDs")
    elif scope != "FULL_DOCUMENT":
        warn("FULL_DOCUMENT_RECALL_UNESTABLISHED", "Reader was not provided/recorded as reading every passage")
    if scope == "FULL_DOCUMENT":
        warn("READING_CLAIM_NOT_PROOF", "A complete ID list cannot prove actual cognitive or model reading")
    evidence = extraction.get("evidence")
    if not isinstance(evidence, list):
        err("EVIDENCE_NOT_ARRAY", "evidence must be an array");evidence=[]
    evidence_by_id={}
    for e in evidence:
        if not isinstance(e,dict):
            err("INVALID_EVIDENCE_OBJECT", "Evidence entry is not object");continue
        eid=e.get("evidence_id");pid=e.get("passage_id");quote=e.get("quote")
        if not isinstance(eid,str) or not eid:
            err("MISSING_EVIDENCE_ID", "Evidence ID required");continue
        if eid in evidence_by_id:
            err("DUPLICATE_EVIDENCE_ID", "Evidence IDs must be unique",eid);continue
        evidence_by_id[eid]=e
        if pid not in passages:
            err("UNKNOWN_EVIDENCE_PASSAGE", "Evidence passage is not in source",eid);continue
        # RF-04 (v0.5.1-review): a quote shorter than 8 characters is accepted only when it is the
        # ENTIRE passage (e.g. a lone table cell "[***]"); v0.5.0 made such source text impossible
        # to cite, forcing QC failure on correct extractions.
        if (not isinstance(quote,str) or not quote.strip() or quote not in passages[pid]["text"]
                or (len(quote.strip())<8 and quote.strip()!=passages[pid]["text"].strip())):
            err("QUOTE_NOT_IN_SOURCE", "Exact quote must occur within its cited mapped passage",eid)
        if pid not in reviewed:
            err("EVIDENCE_IN_UNREAD_PASSAGE", "Evidence refers to source not listed as read",eid)
    checks.append({"check":"EVIDENCE_SUBSTRING_CHECKED","status":"FAIL" if any(x["code"] in {"QUOTE_NOT_IN_SOURCE","UNKNOWN_EVIDENCE_PASSAGE"} for x in errs) else "PASS"})
    def valid_eids(ids,owner,required=True):
        if not isinstance(ids,list) or (required and not ids):
            err("MISSING_EVIDENCE_LINK", "Nonempty evidence_ids required",owner);return []
        for eid in ids:
            if eid not in evidence_by_id:
                err("BROKEN_EVIDENCE_LINK", "Unknown Evidence ID",f"{owner}:{eid}")
        return [eid for eid in ids if eid in evidence_by_id]
    agreement=extraction.get("agreement")
    if not isinstance(agreement,dict):
        err("AGREEMENT_MISSING", "Agreement header required");agreement={}
    agreement_field_evidence=agreement.get("field_evidence")
    if not isinstance(agreement_field_evidence,dict):
        err("AGREEMENT_FIELD_EVIDENCE_MISSING", "Agreement field_evidence mapping required");agreement_field_evidence={}
    for key in ("title","licensor","licensee","industry","licensed_ip","execution_date","effective_date",
                "duration","territory","exclusivity","contractual_status"):
        v=agreement.get(key)
        if v is not None and (not isinstance(v,str) or not v.strip()):
            err("BAD_AGREEMENT_FIELD",f"{key} must be nonempty string or null")
        if v is not None:
            # The model may infer a descriptive title, industry or historical
            # status from filing metadata rather than an exact quoted clause.
            # Preserve this as explicitly UNVERIFIED, rather than converting a
            # non-economic metadata omission into a blocking royalty QC failure.
            if key in {"title","industry","contractual_status"} and not agreement_field_evidence.get(key):
                warn("DESCRIPTIVE_HEADER_UNSUPPORTED", f"{key} lacks a source quote and is unverified",key)
            else:
                valid_eids(agreement_field_evidence.get(key),f"agreement.{key}")
    terms=extraction.get("royalty_terms")
    if not isinstance(terms,list):err("ROYALTY_TERMS_NOT_ARRAY","Royalty terms array required");terms=[]
    other=extraction.get("other_payments")
    if not isinstance(other,list):err("OTHER_PAYMENTS_NOT_ARRAY","Payments array required");other=[]
    term_ids=set()
    for t in terms:
        if not isinstance(t,dict):err("BAD_TERM","Term must be object");continue
        tid=t.get("term_id")
        if not isinstance(tid,str) or not tid or tid in term_ids:
            err("INVALID_OR_DUP_TERM_ID","Unique nonempty term ID required",tid);continue
        term_ids.add(tid)
        if t.get("family") not in TERMFAMILIES:err("BAD_TERM_FAMILY","Unknown royalty family",tid)
        if t.get("structure") not in STRUCTURES:err("BAD_STRUCTURE","Unknown royalty structure",tid)
        if t.get("rate_unit") not in RATES:err("BAD_RATE_UNIT","Unknown rate unit",tid)
        status=t.get("disclosure_status")
        if status not in DISCLOSURES:err("BAD_DISCLOSURE_STATUS","Unknown disclosure status",tid)
        eids=valid_eids(t.get("evidence_ids"),tid)
        reids=valid_eids(t.get("rate_evidence_ids"),tid,required=(status=="DISCLOSED" and t.get("rate_value") is not None))
        base=t.get("base")
        if base and status=="DISCLOSED":
            b_eids=valid_eids(t.get("base_evidence_ids"),tid)
            # Field-level quotation proof is deliberately not sufficient for semantic agreement.
            if b_eids and not any(base.lower() in evidence_by_id[eid].get("quote","").lower() for eid in b_eids):
                warn("BASE_NOT_LITERAL_IN_EVIDENCE","Basis interpretation requires semantic review",tid)
        elif status=="DISCLOSED":
            warn("NO_EXPLICIT_ROYALTY_BASE", "Rate base requires interpretation or documented absence",tid)
        rate=t.get("rate_value")
        if status=="REDACTED":
            if rate is not None or t.get("rate_unit")!="REDACTED":
                err("REDACTED_RATE_LEAK","Redacted rates must be null and unit REDACTED",tid)
            if not any(re.search(r"redact|\*\*\*|omitt|confidential", evidence_by_id[eid].get("quote", ""),re.I) for eid in eids):
                warn("REDACTION_NOT_LITERAL", "Redaction is not directly visible in supporting text",tid)
        elif status=="DISCLOSED":
            if t.get("rate_unit")=="PERCENT" and rate is not None:
                d=_decimal(rate)
                if d is None or not 0<=d<=100:
                    err("INVALID_PERCENT_VALUE", "Percent value must be 0..100 decimal string (e.g. '5')",tid)
                elif not _numeric_in_quotes(rate,reids,evidence_by_id,"PERCENT"):
                    err("RATE_NOT_FOUND_IN_QUOTE", "Rate does not appear as percentage in its rate evidence",tid)
            elif t.get("structure") not in {"TIERED","FORMULA","HYBRID"} and not rate:
                err("MISSING_DISCLOSED_RATE", "Non-tiered disclosed rate absent",tid)
            elif rate is not None and t.get("rate_unit")=="CURRENCY_PER_UNIT" and not _numeric_in_quotes(rate,reids,evidence_by_id,"CURRENCY_PER_UNIT"):
                err("UNIT_AMOUNT_NOT_FOUND_IN_QUOTE","Per-unit amount not in evidence",tid)
        if t.get("structure") in {"STEP_UP","STEP_DOWN"} and not t.get("conditions") and not t.get("adjustments"):
            err("MISSING_ADJUSTMENT_CONDITION","Step-up/down must include trigger conditions",tid)
        for k,c in enumerate(t.get("conditions") or []):
            if not isinstance(c,dict) or not isinstance(c.get("text"),str) or not c["text"]:
                err("INVALID_CONDITION", "Condition object needs text",f"{tid}:{k}")
            else:
                valid_eids(c.get("evidence_ids"),f"{tid}:condition:{k}")
        for k,adj in enumerate(t.get("adjustments") or []):
            if not isinstance(adj,dict) or not adj.get("description"):
                err("INVALID_ADJUSTMENT", "Adjustment needs description",f"{tid}:{k}")
            else:valid_eids(adj.get("evidence_ids"),f"{tid}:adjustment:{k}")
        tiers=t.get("tiers")
        if not isinstance(tiers,list):err("TIERS_NOT_ARRAY","tiers must be array",tid);tiers=[]
        if t.get("structure")=="TIERED" and len(tiers)<2:
            err("MISSING_TIERS", "Tiered contract requires at least two distinct tier records",tid)
        sequences=[]
        for j,tier in enumerate(tiers):
            if not isinstance(tier,dict):err("BAD_TIER","Tier must be object",f"{tid}:{j}");continue
            seq=tier.get("sequence");sequences.append(seq)
            if tier.get("calculation") not in {"MARGINAL","ALL_UNITS","CUMULATIVE","UNKNOWN"}:
                err("INVALID_TIER_CALCULATION", "No tier calculation status",f"{tid}:{j}")
            teids=valid_eids(tier.get("evidence_ids"),f"{tid}:tier:{j}")
            tr=tier.get("rate_value")
            if status=="DISCLOSED" and tier.get("rate_unit")=="PERCENT":
                if _decimal(tr) is None or not 0<=_decimal(tr)<=100:
                    err("INVALID_TIER_RATE","Percent tier must be 0..100 decimal string",f"{tid}:{j}")
                elif not _numeric_in_quotes(tr,teids,evidence_by_id,"PERCENT"):
                    err("TIER_RATE_NOT_IN_QUOTE","Tier percentage not supported by quoted text",f"{tid}:{j}")
            lo,up=tier.get("lower"),tier.get("upper")
            if lo is not None and _decimal(lo) is None:warn("UNPARSEABLE_TIER_LOWER","Manual threshold review required",f"{tid}:{j}")
            if up is not None and _decimal(up) is None:warn("UNPARSEABLE_TIER_UPPER","Manual threshold review required",f"{tid}:{j}")
            if _decimal(lo) is not None and _decimal(up) is not None and _decimal(lo)>_decimal(up):
                err("REVERSED_TIER_RANGE","Tier upper threshold lower than lower bound",f"{tid}:{j}")
            if (lo is not None or up is not None) and not tier.get("threshold_evidence_ids"):
                err("UNSUPPORTED_TIER_THRESHOLD","Threshold requires separate evidence reference",f"{tid}:{j}")
            if tier.get("threshold_evidence_ids"):
                te=valid_eids(tier["threshold_evidence_ids"],f"{tid}:tier:{j}:threshold")
                for bound,value in (("lower",lo),("upper",up)):
                    if value is not None and _decimal(value) is not None and _decimal(value)!=0:
                        if not _numeric_in_quotes(value,te,evidence_by_id,"CURRENCY_PER_UNIT"):
                            err("THRESHOLD_NOT_IN_QUOTE", "Tier threshold not literally supported by any linked quote",f"{tid}:{j}:{bound}")
        if sequences != list(range(1,len(sequences)+1)):
            err("NONCONSECUTIVE_TIER_SEQUENCE", "Tier sequence must be 1..N",tid)
        # Warn, not automatically reject: gaps can be real, and subsets may be discrete products.
        for left,right in zip(tiers,tiers[1:]):
            a=_decimal(left.get("upper")) if isinstance(left,dict) else None
            b=_decimal(right.get("lower")) if isinstance(right,dict) else None
            if a is not None and b is not None and a != b:
                warn("TIER_GAP_OR_OVERLAP","Thresholds differ; verify whether intentional",tid)
    payment_ids=set()
    for p in other:
        if not isinstance(p,dict):err("INVALID_PAYMENT","Payment must be object");continue
        pid=p.get("payment_id")
        if not isinstance(pid,str) or not pid or pid in payment_ids:
            err("DUPLICATE_OR_MISSING_PAYMENT_ID","Payment IDs must be unique",pid);continue
        payment_ids.add(pid)
        peids=valid_eids(p.get("evidence_ids"),pid)
        value=p.get("amount_value")
        numeric=_decimal(value)
        if value is not None and numeric is None:
            # An extraction can correctly record interest as "0.5% per month"
            # or a non-running commercial formula in a field meant for money.
            # Preserve as unnormalized text if it is supported, rather than
            # misreporting this as a fabricated running royalty. Monetary terms
            # with required numeric amounts are still strictly rejected.
            descriptive=p.get("kind") in {"INTEREST","OTHER"}
            snippets=[evidence_by_id[eid].get('quote','') for eid in peids]
            literal=str(value).strip()
            rate=re.search(r'(?<![\w.])((?:\d+(?:\.\d+)?|\.\d+))\s*%',literal)
            src_rates=[Decimal(a.replace(' ','')) for q in snippets
                for a in re.findall(r'(?<![\w.])((?:\d+(?:\.\d+)?|\.\d+))\s*%',q)]
            supported=(any(literal.casefold() in q.casefold() for q in snippets) or
                       (rate is not None and Decimal(rate.group(1)) in src_rates))
            if descriptive and supported:
                warn("DESCRIPTIVE_PAYMENT_NOT_NUMERIC", "Non-running payment detail preserved as quoted text; not usable as numeric amount",pid)
            else:
                err("INVALID_PAYMENT_AMOUNT", "Monetary payment requires a sourced numeric value, redaction or explicit text classification",pid)
        elif numeric is not None and not _numeric_in_quotes(value,peids,evidence_by_id,"CURRENCY_PER_UNIT"):
            err("PAYMENT_AMOUNT_NOT_IN_SOURCE", "Payment amount not supported by quote",pid)
    dispositions=extraction.get("dispositions")
    if not isinstance(dispositions,list):err("DISPOSITIONS_NOT_ARRAY", "dispositions must be array");dispositions=[]
    # UNKNOWN/UNCERTAIN must not be a loophole through the candidate ledger.
    # Genuine uncertainty is permitted only as an explicit unresolved high-risk
    # issue bound to the same source passage. An issue blocks human publication.
    unresolved_high_by_passage = {
        pid for issue in extraction.get("open_issues", [])
        if isinstance(issue, dict)
        and issue.get("status") != "RESOLVED"
        and issue.get("severity") in {"CRITICAL", "HIGH"}
        for pid in (issue.get("passage_ids") or [])
        if isinstance(pid, str)
    }
    seen=set()
    for d in dispositions:
        if not isinstance(d,dict):err("BAD_DISPOSITION","Disposition not object");continue
        pid=d.get("passage_id")
        if pid not in candidate_ids:
            err("DISPOSITION_NOT_CANDIDATE","Only flagged candidate passages are disposed here",pid);continue
        if pid in seen:err("DUPLICATE_DISPOSITION","Candidate has duplicate disposition",pid)
        seen.add(pid)
        cats=d.get("categories")
        if isinstance(cats,list) and "UNCERTAIN" in cats and pid not in unresolved_high_by_passage:
            source=passages[pid]['text']
            from .m6_source_risk import source_hits, POTENTIAL_RATE
            source_high=any(h['passage_id']==pid and h['risk']!='INVENTORY_ONLY'
                            for h in source_hits(mapping))
            monetary_obligation=bool(re.search(r'\b(?:shall pay|must pay|royalt(?:y|ies) payable|payments? due)\b',source,re.I))
            economic_definition=bool(re.search(r'\bnet\s+sales\b',source,re.I) and
                                     re.search(r'\b(?:means|shall mean|defined as)\b',source,re.I))
            if source_high or monetary_obligation or economic_definition:
                err("UNCERTAIN_WITHOUT_BLOCKING_ISSUE",
                    "Uncertain economic passage requires an unresolved HIGH/CRITICAL issue",pid)
            else:
                warn("UNCERTAIN_NON_ECONOMIC_PASSAGE", "Uncertainty outside a detected monetary obligation; no rate conclusion made",pid)
        if not isinstance(cats,list) or not cats or set(cats)-CATEGORIES:
            err("INVALID_DISPOSITION_CATEGORY","Unknown/empty disposition categories",pid);continue
        linked_terms=d.get("term_ids") or []
        linked_payments=d.get("payment_ids") or []
        if "ROYALTY_TERM" in cats and not linked_terms:
            err("TERM_DISPOSITION_UNLINKED","Royalty passage has no term ID",pid)
        if "OTHER_PAYMENT" in cats and not linked_payments:
            # A cross-reference to *existing* royalties or termination for
            # nonpayment is not a new payment obligation. When a term is linked
            # and the clause has no new financial amount, keep a warning rather
            # than rejecting an otherwise correct extraction.
            source=passages[pid]['text']
            has_new_amount=bool(re.search(r'(?:US\s*)?\$\s*\d|\b\d+(?:\.\d+)?\s*%',source,re.I))
            cross_reference=bool(linked_terms and not has_new_amount and
                re.search(r'\b(?:pursuant to|subject to|under section|when due|failure to pay|fails to|termination|existing|already)\b',source,re.I))
            if cross_reference:
                warn("PAYMENT_CROSS_REFERENCE_NOT_NEW", "Payment language references linked royalty without new financial consideration",pid)
            else:
                err("PAYMENT_DISPOSITION_UNLINKED","Other payment passage has no payment ID",pid)
        for tid in linked_terms:
            if tid not in term_ids:err("DISPOSITION_UNKNOWN_TERM","Disposition references unknown term",pid)
        for payid in linked_payments:
            if payid not in payment_ids:err("DISPOSITION_UNKNOWN_PAYMENT","Disposition references unknown payment",pid)
        if not isinstance(d.get("rationale"),str) or len(d.get("rationale","").strip())<12:
            err("DISPOSITION_RATIONALE_MISSING","Explain why passage is included/excluded",pid)
        # A disposition references an immutable passage ID. A separate short
        # quotation is compulsory only if it asserts a positive economic fact.
        # BACKGROUND/UNRELATED/CROSS_REFERENCE may have no quote at all.
        positive=bool(set(cats) & {"ROYALTY_TERM","OTHER_PAYMENT"})
        # A lone [***] may be a redacted wiring instruction rather than an
        # economic obligation. Preserve its source location without inventing
        # evidence or treating it as a missing royalty. Relevant redactions
        # remain covered by the independent M6 source-risk gate.
        if "REDACTED" in cats and "BACKGROUND" not in cats:
            positive=True
        if d.get("evidence_ids") or positive:
            valid_eids(d.get("evidence_ids"),f"disposition:{pid}",required=positive)
        # Passage-level reconciliation is not sufficient if multiple royalties
        # share one paragraph. Account for every literal numeric percentage.
        from collections import Counter
        m7_strict = mapping.get("quality_control_profile")=="M7_ISSUED_OCCURRENCES"
        actual_pct = Counter(m.group(0) for m in PERCENT.finditer(passages[pid]["text"]))
        recorded = d.get("percentage_dispositions")
        if not isinstance(recorded,list):
            err("PERCENT_LEDGER_MISSING", "percentage_dispositions must be a list",pid)
            recorded=[]
        logged = Counter()
        for ix, item in enumerate(recorded):
            if not isinstance(item,dict):
                err("INVALID_PERCENT_DISPOSITION", "Nonobject percent disposition",f"{pid}:{ix}")
                continue
            literal = item.get("literal")
            logged[literal]+=1
            classif=item.get("classification")
            if classif == "UNKNOWN" and pid not in unresolved_high_by_passage:
                err("UNKNOWN_PERCENT_WITHOUT_BLOCKING_ISSUE",
                    "Unclassified source percentage requires an unresolved HIGH/CRITICAL issue",f"{pid}:{literal}")
            if classif not in {"ROYALTY_RATE","ADJUSTMENT","OTHER_PAYMENT","UNRELATED","THRESHOLD","UNKNOWN"}:
                err("INVALID_PERCENT_CLASSIFICATION", "Percent classification invalid",f"{pid}:{literal}")
            if not isinstance(item.get("rationale"),str) or len(item["rationale"].strip()) < 12:
                err("PERCENT_RATIONALE_MISSING","Each percentage needs a reason",f"{pid}:{literal}")
            termid=item.get("term_id")
            if classif in {"ROYALTY_RATE","ADJUSTMENT"} and termid not in term_ids:
                err("PERCENT_TERM_UNLINKED","Royalty/adjustment percentage needs linked term",f"{pid}:{literal}")
            if classif=="ROYALTY_RATE" and termid in term_ids:
                t=next(t for t in terms if isinstance(t,dict) and t.get("term_id")==termid)
                expected=[t.get("rate_value")]+[tier.get("rate_value") for tier in (t.get("tiers") or []) if isinstance(tier,dict)]
                # Literal can be 6%, .5%, etc. The note is not an economic check.
                m=re.match(r"\s*(\d+(?:\.\d+)?|\.\d+)",literal or "")
                if m and not any(_decimal(x)==(Decimal(m.group(1)) if m else None) for x in expected if _decimal(x) is not None):
                    err("PERCENT_NOT_REFLECTED_IN_TERM","Source percentage is classified as rate but missing from linked term",f"{pid}:{literal}")
        if not m7_strict and mapping.get('quality_control_profile')!='M12_SOURCE_FLAGS' and logged != actual_pct:
            err("PERCENT_LEDGER_INCOMPLETE", "Every literal percentage occurrence needs its own disposition",pid)
        # In M7, legacy model-authored literal counts are not the authority.
        # The immutable Python-issued occurrence ledger is checked below.
    if candidate_ids-seen:
        err("UNACCOUNTED_CANDIDATES", "Candidate passage disposition ledger incomplete",sorted(candidate_ids-seen)[:15])
    if len(seen)!=len(candidate_ids):
        warn("CANDIDATE_LEDGER_NOT_CLOSED",f"{len(seen)} of {len(candidate_ids)} candidates have disposition")
    # Every referenced source passage for a rate/payment must be a candidate or explicitly escalated.
    for record,category in [(t,"ROYALTY_TERM") for t in terms if isinstance(t,dict)]+[(p,"OTHER_PAYMENT") for p in other if isinstance(p,dict)]:
        own=record.get("term_id") or record.get("payment_id")
        for eid in record.get("evidence_ids") or []:
            e=evidence_by_id.get(eid)
            if e and e.get("passage_id") not in candidate_ids:
                warn("UNFLAGGED_ECONOMIC_PASSAGE", "Term evidence in unflagged passage; improve Python discovery recall",own)
    for issue in extraction.get("open_issues",[]):
        if not isinstance(issue,dict) or issue.get("severity") not in ISSUE_SEVERITIES:
            err("BAD_OPEN_ISSUE", "Issues must specify severity")
        elif issue.get("status") != "RESOLVED" and issue["severity"] in {"CRITICAL","HIGH"}:
            warn("BLOCKING_OPEN_ISSUE", "High-risk issue still open",issue.get("issue_id"))
    # An independent source-ledger checks every original passage, including
    # anything the model relabelled BACKGROUND or UNRELATED. It is intentionally
    # conservative and cannot certify legal/semantic correctness.
    if mapping.get('quality_control_profile')=='M12_SOURCE_FLAGS':
        # Only immutable evidence/record integrity plus the M12 source-signal
        # engine govern M12. Older source heuristics remain comparison-only.
        from .m12_economic_qc import issue_signals,reconcile_with_proposals
        manifest=issue_signals(mapping)
        if extraction.get('m12_manifest_sha256') not in (None,manifest['manifest_sha256']):
            err('M12_MANIFEST_MISMATCH','Extraction references a stale/foreign source-flag manifest')
        m12=reconcile_with_proposals(mapping,extraction,extraction.get('m12_resolutions'))
        errs.extend(m12['errors']);warns.extend(m12['warnings'])
        checks.append({'check':'M12_SOURCE_ECONOMIC_FLAG_RECONCILIATION',
            'status':'PASS' if m12['status']=='PASS_SOURCE_FLAGS_ONLY' else 'INCOMPLETE',
            'source_flags':m12['source_signal_count'],'closed_flags':m12['closed_count'],
            'hard_open':m12['hard_open'],'supporting_open':m12['warning_open']})
        if m12['status']=='INCOMPLETE_SUPPORTING_ECONOMICS':
            warn('M12_SUPPORTING_ECONOMICS_INCOMPLETE',
                 'Supporting fees/milestones remain unaccounted; these are visible warnings')
    elif mapping.get('quality_control_profile')=='M11_TYPED_SIGNALS':
        # New architecture: one immutable source-flag manifest and verifiable
        # typed closures. The legacy heuristics must NOT also decide PASS/FAIL;
        # that would reintroduce the false alarms M11 was designed to avoid.
        from .m11_signal_qc import issue_signals,reconcile_with_proposals
        manifest=issue_signals(mapping)
        if extraction.get('m11_manifest_sha256') not in (None,manifest['manifest_sha256']):
            err('M11_MANIFEST_MISMATCH','Extraction references a stale or foreign source-flag manifest')
        m11=reconcile_with_proposals(mapping,extraction,extraction.get('m11_resolutions'))
        errs.extend(m11['errors'])
        warns.extend(m11['warnings'])
        if m11['status']=='INCOMPLETE_SUPPORTING_ECONOMICS':
            warn('M11_SUPPORTING_ECONOMICS_INCOMPLETE',
                 'Non-rate upfront, maintenance or milestone economics remain unaccounted; not a clean completeness result')
        checks.append({'check':'M11_SOURCE_ISSUED_TYPED_FLAG_RECONCILIATION',
            'status':'PASS' if m11['status']=='PASS_SOURCE_FLAGS_ONLY' else 'INCOMPLETE',
            'source_flags':m11['source_signal_count'],'closed_flags':m11['closed_count'],
            'hard_open':m11['hard_open'],'supporting_open':m11['warning_open']})
    else:
        from .m6_source_risk import check_source_risk
        source_risks, all_occurrences = check_source_risk(mapping, extraction)
        if mapping.get("quality_control_profile")=="M7_ISSUED_OCCURRENCES":
            from .m7_occurrences import check_m7_occurrences, issue_occurrences
            issued=issue_occurrences(mapping)
            if mapping.get("occurrence_manifest_sha256")!=issued['manifest_sha256']:
                err('M7_MAP_MANIFEST_MISMATCH','M7 map occurrence manifest does not match source text')
            occ_report=check_m7_occurrences(mapping,extraction)
            errs.extend(occ_report['errors'])
            warns.extend(occ_report['warnings'])
            checks.append({'check':'M7_SOURCE_ISSUED_OCCURRENCE_RECONCILIATION',
                           'status':'PASS' if not occ_report['errors'] else 'FAIL'})
        from .m9_context_gate import check_context_economics
        context_check = check_context_economics(mapping, extraction)
        errs.extend(context_check['errors'])
        warns.extend(context_check['warnings'])
        checks.append({'check':'M9_SOURCE_CONTEXT_ECONOMICS',
                       'status':'FAIL' if context_check['errors'] else 'PASS',
                       'tested_source_facts':len(context_check['tests'])})
        from .m10_obligation_gate import check_source_obligations
        obligations=check_source_obligations(mapping,extraction)
        errs.extend(obligations["errors"])
        checks.append({"check":"M10_SOURCE_LED_OBLIGATION_RECONCILIATION",
                       "status":"FAIL" if obligations["errors"] else "PASS",
                       "tested_source_facts":len(obligations["tested"])})
        errs.extend(source_risks)
        checks.append({"check":"INDEPENDENT_SOURCE_RISK_GATE", "status":"FAIL" if source_risks else "PASS"})
    if not terms and not other:
        warn("NO_ECONOMIC_TERMS_RECORDED", "No terms is not proof of no licensing arrangement")
    # Long-line mapping fragments are exact, but cross-fragment economics are
    # vulnerable to context separation. A forced cut inside a continuous token
    # cannot be auto-approved even when local percentage reconciliation passes.
    long_segments=(mapping.get('source_segmentation') or {}).get('split_original_paragraphs',[])
    if long_segments:
        warn('SOURCE_PARAGRAPHS_SEGMENTED',
             'Adjacent fragments reconstruct the original line but require contextual review',
             len(long_segments))
        if any(x.get('forced_boundary') for x in long_segments):
            err('FORCED_SOURCE_BOUNDARY_REQUIRES_REMAP_OR_REVIEW',
                'Forced within-token source split is ineligible for automatic QC PASS; re-map with larger segment bound or resolve source handling',
                None)
    if extraction.get("amendment_status") not in {"NOT_CHECKED","NONE_IDENTIFIED_IN_DOCUMENT","REFERENCED_UNRESOLVED","REVIEWED_WITH_LINKED_DOCUMENTS"}:
        err("AMENDMENT_CHECK_NOT_DECLARED", "Amendment status required")
    if extraction.get("amendment_status")!="REVIEWED_WITH_LINKED_DOCUMENTS":
        warn("AMENDMENT_HISTORY_NOT_VERIFIED", "Historical current status not established by this document")
    check("CANDIDATE_DISPOSITION_LEDGER",not bool(candidate_ids-seen))
    check("SOURCE_MAP_BINDING",extraction.get("document_id")==doc_id and extraction.get("source_text_sha256")==mapping["text_sha256"])
    check("ALL_CANDIDATES_LISTED_AS_READ",not bool(candidate_ids-set(reviewed)))
    report = _error_report(doc_id,errs,warns,checks)
    report["source_text_sha256"] = mapping["text_sha256"]
    if mapping.get('quality_control_profile')=='M12_SOURCE_FLAGS':
        report['m12_source_flags']=m12
        if m12['status']=='INCOMPLETE_SUPPORTING_ECONOMICS' and not errs:
            report['deterministic_status']='INCOMPLETE_SUPPORTING_ECONOMICS'
    if mapping.get('quality_control_profile')=='M11_TYPED_SIGNALS':
        report['m11_source_flags']=m11
        # A record with missing supporting economics must not be presented as
        # a clean QC pass, even though warnings do not masquerade as errors.
        if m11['status']=='INCOMPLETE_SUPPORTING_ECONOMICS' and not errs:
            report['deterministic_status']='INCOMPLETE_SUPPORTING_ECONOMICS'
    return report


def _normalized_base(value):
    """Conservative normalization: no model-based semantic equivalence claims."""
    text=re.sub(r"\s+"," ",str(value or '').lower())
    if re.search(r"\bnet\s+sales\b",text):return 'NET_SALES'
    if re.search(r"\bgross\s+sales\b",text):return 'GROSS_SALES'
    if re.search(r"\bsublicen[sc](?:e|ing)\s+(?:fees|receipts|revenue)\b",text):return 'SUBLICENSE_RECEIPTS'
    if re.search(r"\brevenue\b",text):return 'REVENUE_UNSPECIFIED'
    if re.search(r"\bsales\b",text):return 'SALES_UNSPECIFIED'
    return re.sub(r'[^a-z0-9]+',' ',text).strip() or 'UNSPECIFIED'


def _scalar(v):
    if v is None:return None
    n=_decimal(v) if isinstance(v,str) else None
    if n is None:
        return re.sub(r'\s+',' ',str(v).casefold()).strip() or None
    return str(n.normalize())


def _canonical_semantic_terms(x:dict):
    """Field-level screening signatures; free-text writing style is not identity.

    A first-tier lower bound of 0 and its implicit open start can be equivalent
    for non-negative sales. All other differences remain visible.
    """
    terms=[]
    for t in x.get('royalty_terms',[]):
        if not isinstance(t,dict):continue
        tiers=[]
        for i,v in enumerate(t.get('tiers') or []):
            lo=_scalar(v.get('lower'))
            if i==0 and lo=='0':lo=None
            tiers.append((v.get('sequence'), _scalar(v.get('rate_value')),v.get('rate_unit'),
                lo,_scalar(v.get('upper')),v.get('calculation'),
                _normalized_base(v.get('threshold_basis')) if v.get('threshold_basis') else 'UNSPECIFIED'))
        terms.append({'family':t.get('family'),'structure':t.get('structure'),
            'rate':_scalar(t.get('rate_value')),'unit':t.get('rate_unit'),
            'base':_normalized_base(t.get('base')),
            'tiers':tuple(sorted(tiers,key=repr)),
            'product_specified':bool(t.get('product_scope')),
            'territory_specified':bool(t.get('territory_scope')),
            'condition_count':len(t.get('conditions') or []),
            'adjustment_count':len(t.get('adjustments') or []),
            'disclosure':t.get('disclosure_status')})
    return sorted(terms,key=lambda v:repr(v))


def _material_payments(x):
    # Interest, penalty and audit charges do not constitute contractual licence
    # consideration. Retain them in staging, but don't spuriously disagree when
    # one reader records them only as non-economic exclusions.
    excluded={'INTEREST','LATE_INTEREST','LATE_PAYMENT_INTEREST','AUDIT_FEE','PENALTY','AUDIT_THRESHOLD'}
    out=[]
    for p in x.get('other_payments',[]):
        if not isinstance(p,dict) or str(p.get('kind') or '').upper() in excluded:continue
        out.append((p.get('kind'),_scalar(p.get('amount_value')),
                    (p.get('currency') or '').upper()))
    return sorted(out,key=repr)


def compare_independent_extractions(mapping:dict, first:dict, second:dict) -> dict:
    """Field-by-field differences, not literal-description equality.

    Agreement of two models is NOT a proof of correctness or recall. Human/strong
    model review remains required for contractual meaning and exclusions.
    """
    a=validate_extraction(mapping,first)
    b=validate_extraction(mapping,second)
    disagreement=[]
    detail=[]
    if a['deterministic_status']!='PASS_DETERMINISTIC_ONLY':
        disagreement.append('FIRST_EXTRACTION_QC_FAILED')
    if b['deterministic_status']!='PASS_DETERMINISTIC_ONLY':
        disagreement.append('SECOND_EXTRACTION_QC_FAILED')
    if first.get('reader',{}).get('run_id')==second.get('reader',{}).get('run_id'):
        disagreement.append('READERS_SHARE_RUN_ID')
    if first.get('reader',{}).get('engine')==second.get('reader',{}).get('engine'):
        disagreement.append('SAME_ENGINE_INDEPENDENCE_UNPROVEN')
    ta=_canonical_semantic_terms(first)
    tb=_canonical_semantic_terms(second)
    if len(ta)!=len(tb):
        disagreement.append('ECONOMIC_TERM_COUNT_MISMATCH')
        detail.append({'field':'royalty_terms.count','first':len(ta),'second':len(tb)})
    else:
        for i,(x,y) in enumerate(zip(ta,tb),1):
            for field in ('family','structure','rate','unit','base','tiers','product_specified',
                          'territory_specified','condition_count','adjustment_count','disclosure'):
                if x[field]!=y[field]:
                    detail.append({'field':f'royalty_terms.{i}.{field}',
                                   'first':x[field],'second':y[field]})
        if detail:
            disagreement.append('ECONOMIC_FIELD_MISMATCH')
    pa=_material_payments(first);pb=_material_payments(second)
    if pa!=pb:
        disagreement.append('MATERIAL_PAYMENT_MISMATCH')
        detail.append({'field':'other_payments.material','first':pa,'second':pb})
    return {'document_id':mapping['document_id'],'schema':'m2-comparison.2',
        'first_qc':a,'second_qc':b,'disagreements':disagreement,
        'field_differences':detail,
        'status':'REVIEW_REQUIRED' if disagreement else 'NO_DETECTED_DISAGREEMENT_NOT_PROOF_OF_ACCURACY',
        'verification_scope':'AUTOMATED_AI_COMPARISON_ONLY'}
