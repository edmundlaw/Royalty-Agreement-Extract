"""SEC EDGAR full-text discovery and quarterly-index corroboration.

Full-text search's JSON endpoint is an observed interface, not a guaranteed
stable SEC API. Saturated windows raise rather than silently truncate results.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from urllib.parse import urlencode

from .storage import stable_id

EFTS = "https://efts.sec.gov/LATEST/search-index"
INDEX_RE = re.compile(r"^\s*(\d+)\|([^|]*)\|([^|]*)\|(\d{4}-\d{2}-\d{2})\|(edgar/data/[^|\s]+)\s*$")
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
CONTRACT_PREFIXES = ("EX-10", "EX-4", "EX-2", "EX-99", "EX-6")


class SearchCoverageError(RuntimeError):
    """The full set could not be demonstrated: fail closed."""


def source_url(cik: str, accession: str, filename: str) -> str:
    if not ACCESSION_RE.fullmatch(accession):
        raise ValueError("Invalid accession number")
    cik = str(int(cik))
    if (not filename or filename.startswith(".") or "/" in filename or "\\" in filename
            or "?" in filename or "#" in filename or ".." in filename):
        raise ValueError("Unsafe SEC exhibit filename")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{filename}"


def index_url(year: int, quarter: int) -> str:
    if year < 1994 or not 1 <= quarter <= 4:
        raise ValueError("Invalid year or SEC quarter")
    return f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"


def parse_master_idx(text: str, forms: set[str] | None = None) -> list[dict]:
    """Parse the SEC's pipe-delimited quarterly master.idx, retaining filing identity."""
    rows = []
    header_seen = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("CIK|Company Name|Form Type|Date Filed|Filename"):
            header_seen = True
            continue
        if not header_seen:
            continue
        if not line.strip() or line.startswith("-"):
            continue
        match = INDEX_RE.match(line)
        if match is None:
            raise ValueError(f"Malformed master.idx row {lineno}: {line[:120]}")
        cik, company, form, filed, rel = match.groups()
        if forms and form.upper() not in forms:
            continue
        accession = rel.rsplit("/", 1)[-1].removesuffix(".txt")
        if not ACCESSION_RE.fullmatch(accession):
            raise ValueError(f"Missing valid accession on row {lineno}")
        rows.append({"filing_id": stable_id("FIL", cik, accession),
                     "cik": str(int(cik)), "company": company.strip(), "form": form.strip(),
                     "filing_date": filed, "accession": accession,
                     "complete_submission_url": "https://www.sec.gov/Archives/" + rel,
                     "inventory_url": source_url(cik, accession, accession + "-index.html")})
    if not header_seen:
        raise ValueError("SEC master.idx header missing")
    return rows


def hit_to_record(hit: dict, query: str) -> dict:
    src = hit.get("_source") or {}
    hit_id = hit.get("_id", "")
    if ":" not in hit_id:
        raise SearchCoverageError(f"EFTS hit lacks accession:filename: {hit_id!r}")
    accession, filename = hit_id.split(":", 1)
    ciks = src.get("ciks") or []
    if not ciks:
        raise SearchCoverageError(f"EFTS hit lacks CIK: {hit_id!r}")
    cik = str(int(ciks[0]))
    # A file's type is the exhibit identifier; root form is the submitting form.
    file_type = (src.get("file_type") or "").strip()
    doc_id = stable_id("DOC", cik, accession, filename)
    return {
        "document_id": doc_id, "filing_id": stable_id("FIL", cik, accession),
        "cik": cik, "accession": accession, "filename": filename,
        "source_url": source_url(cik, accession, filename),
        "file_type": file_type or None, "file_description": src.get("file_description"),
        "form": src.get("form"), "filing_date": src.get("file_date"),
        "company": (src.get("display_names") or [None])[0],
        "matched_queries": [query],
        "candidate_route": "CONTRACT_EXHIBIT" if file_type.upper().startswith(CONTRACT_PREFIXES)
                           else "NARRATIVE_OR_OTHER",
        "review_status": "UNSCREENED",
    }


def _phrase(query: str) -> str:
    """RF-06 (v0.5.1-review): SEC full-text search treats an unquoted multi-word query as separate
    words. On 2024-05-08 the unquoted query `license agreement` returned 55 of 77 EX-10 exhibits that
    do not contain that phrase. A multi-word query is therefore sent as an exact phrase unless the
    caller already used quotes or search operators."""
    q = query.strip()
    if " " in q and '"' not in q and not re.search(r"\b(?:AND|OR|NOT)\b|[*()]", q):
        return '"' + q + '"'
    return q


def build_search_url(query: str, start: date, end: date, offset: int, size: int) -> str:
    return EFTS + "?" + urlencode({
        "q": _phrase(query), "dateRange": "custom", "startdt": start.isoformat(),
        "enddt": end.isoformat(), "from": offset, "size": size,
    })


def parse_search_page(data: bytes) -> tuple[int, str, list[dict]]:
    try:
        result = json.loads(data)
        hits = result["hits"]
        total = hits["total"]
        count, relation = int(total["value"]), str(total["relation"])
        entries = hits["hits"]
        if count < 0 or relation not in ("eq", "gte") or not isinstance(entries, list):
            raise ValueError("Invalid count/relation/hits")
        return count, relation, entries
    except (ValueError, KeyError, TypeError) as exc:
        raise SearchCoverageError(f"Unexpected SEC EFTS search response: {exc}") from exc


def search_range(client, query: str, start: date, end: date, *, page_size: int = 100,
                 cap: int = 10_000) -> list[dict]:
    """Exhaust a query/date window or fail. Split saturated or unstable windows."""
    if end < start or page_size < 1 or page_size > 100 or cap < page_size:
        raise ValueError("Invalid date range, page size or hit cap")

    def split_window():
        mid = start + timedelta(days=(end - start).days // 2)
        return search_range(client, query, start, mid, page_size=page_size, cap=cap) + \
               search_range(client, query, mid + timedelta(days=1), end, page_size=page_size, cap=cap)

    count, relation, first = parse_search_page(client.fetch(build_search_url(query, start, end, 0, page_size)))
    if relation != "eq" or count >= cap:
        if start == end:
            raise SearchCoverageError(f"Single-day window saturated for {query}: {start}")
        return split_window()
    if count == 0:
        return []
    if len(first) != min(count, page_size):
        raise SearchCoverageError(f"First EFTS page incomplete for {query} {start}..{end}: {count} hits")
    hits = []
    ids = set()
    for offset in range(0, count, page_size):
        if offset == 0:
            batch = first
        else:
            _, _, batch = parse_search_page(client.fetch(build_search_url(query, start, end, offset, page_size)))
            expected = min(page_size, count - offset)
            if len(batch) != expected:
                raise SearchCoverageError(f"Truncated EFTS page at {offset}: expected {expected}, got {len(batch)}")
        for hit in batch:
            hit_id = hit.get("_id")
            if hit_id in ids:
                if start == end:
                    raise SearchCoverageError(
                        f"Duplicate hit identifiers in single-day EFTS page series for {query} {start}; "
                        "unstable pagination")
                return split_window()
            ids.add(hit_id)
        hits.extend(batch)
    return hits


def discover(client, queries: list[str], start: date, end: date) -> list[dict]:
    if not queries or any(not q.strip() for q in queries):
        raise ValueError("At least one nonblank query is required")
    grouped: dict[str, dict] = {}
    for q in queries:
        for hit in search_range(client, q, start, end):
            record = hit_to_record(hit, q)
            doc_id = record["document_id"]
            if doc_id in grouped:
                if q not in grouped[doc_id]["matched_queries"]:
                    grouped[doc_id]["matched_queries"].append(q)
            else:
                grouped[doc_id] = record
    return sorted(grouped.values(), key=lambda r: (r.get("filing_date") or "", r["document_id"]))
