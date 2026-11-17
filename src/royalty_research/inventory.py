"""Read document-type and filename metadata from an SEC filing detail page."""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

from .discovery import source_url
from .sec_client import validate_sec_url
from .storage import stable_id


class _FilingTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.anchor_href = None
        self.current_href = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            if self.table is None:
                self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = []
            self.current_href = None
        elif tag == "a" and self.cell is not None:
            self.anchor_href = a.get("href")
            if self.anchor_href and self.current_href is None:
                self.current_href = self.anchor_href

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None and self.row is not None:
            self.row.append({"text": " ".join("".join(self.cell).split()), "href": self.current_href})
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None
        elif tag == "a":
            self.anchor_href = None


def parse_filing_index_html(html: str, cik: str, accession: str) -> list[dict]:
    base = source_url(cik, accession, accession + "-index.html")
    p = _FilingTables()
    p.feed(html)
    results = []
    for table in p.tables:
        if not table:
            continue
        headings = [x["text"].strip().lower() for x in table[0]]
        if not {"document", "type"}.issubset(set(headings)):
            continue
        cmap = {name: pos for pos, name in enumerate(headings)}
        for row in table[1:]:
            if len(row) <= max(cmap["document"], cmap["type"]):
                continue
            filename = row[cmap["document"]]["text"].strip()
            file_type = row[cmap["type"]]["text"].strip()
            if not filename or not file_type or filename.lower() == "complete submission text file":
                continue
            href = row[cmap["document"]]["href"]
            if not href:
                # Can't certify document link without an actual URL.
                continue
            resolved = urljoin(base, href)
            validate_sec_url(resolved)
            description = row[cmap["description"]]["text"] if "description" in cmap and len(row) > cmap["description"] else None
            results.append({
                "document_id": stable_id("DOC", cik, accession, filename),
                "filing_id": stable_id("FIL", cik, accession),
                "cik": str(int(cik)), "accession": accession,
                "filename": filename, "file_type": file_type,
                "file_description": description,
                "source_url": resolved,
                "source_inventory_url": base,
                "candidate_route": "CONTRACT_EXHIBIT" if file_type.upper().startswith(("EX-10", "EX-4", "EX-2", "EX-99", "EX-6")) else "OTHER_DOCUMENT",
                "review_status": "UNSCREENED",
            })
    if not results:
        raise ValueError("No document-format table with verifiable document links found")
    if len({r["document_id"] for r in results}) != len(results):
        raise ValueError("Duplicate document filenames in filing inventory")
    return results
