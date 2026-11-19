"""Offline regression tests: no network calls, no LLM consumption."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from royalty_research.cli import main
from royalty_research.discovery import (
    SearchCoverageError, discover,
    parse_master_idx, parse_search_page, search_range, source_url,
)
from royalty_research.inventory import parse_filing_index_html
from royalty_research.mapping import map_contract, validate_map
from royalty_research.parsing import ParseError, UnsupportedDocument, parse_document
from royalty_research.sec_client import SECClient, SECRequestError, validate_sec_url, validate_user_agent
from royalty_research.storage import read_json, sha256

FIX = Path(__file__).parent / "fixtures"


def make_hit(acc="0001493152-25-000001", fname="test.htm"):
    return {"_id": f"{acc}:{fname}", "_source": {
        "ciks": ["0001520358"], "file_type": "EX-10.2", "file_date": "2025-01-02",
        "file_description": "license agreement", "form": "10-K", "display_names": ["Example Co"],
    }}


def page(records, total=None, relation="eq"):
    return json.dumps({"hits": {"total": {"value": len(records) if total is None else total,
                                           "relation": relation}, "hits": records}}).encode()


class FakeClient:
    def __init__(self, fn):
        self.fn = fn
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return self.fn(url)


class TestSecUrlAndSecurity(unittest.TestCase):
    def test_sec_url_strict_allowlist(self):
        good = "https://www.sec.gov/Archives/edgar/data/12/file.htm"
        validate_sec_url(good)
        for bad in ["http://www.sec.gov/x", "https://sec.gov.evil.example/x",
                    "https://www.sec.gov.evil/x", "file:///etc/passwd",
                    "https://evil.example/x", "https://www.sec.gov:8443/x",
                    "https://joe:secret@www.sec.gov/x"]:
            with self.assertRaises(ValueError, msg=bad):
                validate_sec_url(bad)

    def test_source_document_urls(self):
        self.assertEqual(
            source_url("0001520358", "0001493152-13-000675", "ex10-2.htm"),
            "https://www.sec.gov/Archives/edgar/data/1520358/000149315213000675/ex10-2.htm",
        )
        for name in ["../secrets", "subfolder/terms.htm", "", ".htaccess", "terms.html?x=1"]:
            with self.assertRaises(ValueError):
                source_url("1520358", "0001493152-13-000675", name)

    def test_user_agent_requires_real_contact(self):
        with self.assertRaises(ValueError):
            validate_user_agent("PythonBot")
        validate_user_agent("Royalty Research Company Contact analyst@company.example")

    def test_http_403_fails_without_evasion_or_retry(self):
        client = SECClient("Royalty Research analyst@company.example", requests_per_second=1)
        def forbidden(*args, **kwargs):
            raise HTTPError(args[0].full_url, 403, "Forbidden", {}, None)
        with patch.object(client._opener, "open", side_effect=forbidden) as req:
            with self.assertRaises(SECRequestError) as ctx:
                client.fetch("https://www.sec.gov/Archives/x.htm")
            self.assertEqual(req.call_count, 1)
            self.assertEqual(ctx.exception.status, "HTTP_403")


class TestDiscovery(unittest.TestCase):
    def test_master_idx_and_form_filter(self):
        text = (FIX / "master.idx").read_text()
        allrows = parse_master_idx(text)
        self.assertEqual(len(allrows), 2)
        self.assertEqual(len(parse_master_idx(text, forms={"10-K"})), 1)
        self.assertEqual(allrows[0]["cik"], "1520358")
        self.assertEqual(allrows[0]["accession"], "0001493152-25-000001")
        self.assertIn("index.html", allrows[0]["inventory_url"])
        with self.assertRaises(ValueError):
            parse_master_idx("random unrelated file")
        with self.assertRaises(ValueError):
            parse_master_idx(text + "\nmalformed|row")

    def test_filing_index_separates_exhibits_and_filing(self):
        records = parse_filing_index_html((FIX / "filing_index.html").read_text(),
                                          "1520358", "0001493152-25-000001")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["file_type"], "EX-10.2")
        self.assertEqual(records[0]["candidate_route"], "CONTRACT_EXHIBIT")
        self.assertEqual(records[1]["candidate_route"], "OTHER_DOCUMENT")
        self.assertTrue(records[0]["source_url"].endswith("/ex10-2.htm"))

    def test_parse_efts_page(self):
        total, rel, hits = parse_search_page(page([make_hit()]))
        self.assertEqual((total, rel, len(hits)), (1, "eq", 1))
        with self.assertRaises(SearchCoverageError):
            parse_search_page(b"{not valid json")

    def test_single_day_saturation_hard_fails(self):
        c = FakeClient(lambda url: page([make_hit()], total=10_000, relation="gte"))
        with self.assertRaises(SearchCoverageError):
            search_range(c, "royalty", date(2025, 1, 2), date(2025, 1, 2))

    def test_split_saturated_window_and_exhaust(self):
        def handler(url):
            if "startdt=2025-01-01&enddt=2025-01-02" in url:
                return page([make_hit()], total=10_000, relation="gte")
            if "startdt=2025-01-01&enddt=2025-01-01" in url:
                return page([make_hit(fname="one.htm")])
            if "startdt=2025-01-02&enddt=2025-01-02" in url:
                return page([make_hit(fname="two.htm")])
            raise AssertionError(url)
        c = FakeClient(handler)
        rows = search_range(c, "royalty", date(2025, 1, 1), date(2025, 1, 2))
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(c.urls), 3)

    def test_duplicate_pages_split_and_requery_entire_window(self):
        def handler(url):
            if "startdt=2025-01-01&enddt=2025-01-02" in url:
                # Both pages contain the same hit; an unseen result may be missing.
                return page([make_hit(fname="duplicate.htm")], total=2)
            if "startdt=2025-01-01&enddt=2025-01-01" in url:
                return page([make_hit(fname="one.htm")])
            if "startdt=2025-01-02&enddt=2025-01-02" in url:
                return page([make_hit(fname="two.htm")])
            raise AssertionError(url)
        c = FakeClient(handler)
        rows = search_range(c, "royalty", date(2025, 1, 1), date(2025, 1, 2), page_size=1)
        self.assertEqual([hit["_id"].split(":")[1] for hit in rows], ["one.htm", "two.htm"])
        self.assertEqual(len(c.urls), 4)

    def test_single_day_duplicate_pages_fail(self):
        c = FakeClient(lambda url: page([make_hit()], total=2))
        with self.assertRaisesRegex(SearchCoverageError, "single-day.*unstable pagination"):
            search_range(c, "royalty", date(2025, 1, 1), date(2025, 1, 1), page_size=1)
        self.assertEqual(len(c.urls), 2)

    def test_split_window_propagates_single_day_instability(self):
        c = FakeClient(lambda url: page([make_hit()], total=2))
        with self.assertRaisesRegex(SearchCoverageError, "single-day.*unstable pagination"):
            search_range(c, "royalty", date(2025, 1, 1), date(2025, 1, 2), page_size=1)
        self.assertEqual(len(c.urls), 4)

    def test_detect_incomplete_page(self):
        c = FakeClient(lambda u: page([make_hit()], total=200))
        with self.assertRaises(SearchCoverageError):
            search_range(c, "royalty", date(2025, 1, 1), date(2025, 1, 1))

    def test_deduplicate_across_queries_preserving_discovery_trail(self):
        c = FakeClient(lambda u: page([make_hit()]))
        rows = discover(c, ["royalty", "license"], date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["matched_queries"], ["royalty", "license"])
        self.assertEqual(rows[0]["candidate_route"], "CONTRACT_EXHIBIT")


class TestParsingAndMapping(unittest.TestCase):
    def _map(self, name):
        raw = (FIX / name).read_bytes()
        paragraphs, parser = parse_document(raw, name)
        result = map_contract(paragraphs, {
            "document_id": "DOC-SYNTH", "source_url": "https://www.sec.gov/Archives/example/synthetic.htm"
        }, raw_hash=sha256(raw), parser_type=parser)
        return result

    def test_synthetic_complex_agreement(self):
        m = self._map("synthetic_licence.html")
        self.assertEqual(validate_map(m), [])
        texts = [x["text"] for x in m["passages"]]
        self.assertFalse(any("99%" in x for x in texts))  # excluded script
        self.assertTrue(any("6%" in x and "4%" in x for x in texts))
        self.assertTrue(any("25%" in x and "10%" in x for x in texts))
        self.assertTrue(any("1.5%" in x for x in texts))  # kept, AI must classify
        self.assertTrue(any("[***]" in x for x in texts))
        self.assertTrue(any("$2 per device" in x for x in texts))
        self.assertIn("Net Sales", [x["term"] for x in m["definitions"]])
        self.assertIn("CROSS_REFERENCE", m["candidate_reason_counts"])
        self.assertEqual(m["screening_priority"], "HIGH_REVIEW_PRIORITY")
        self.assertEqual(sum(len(x["passage_ids"]) for x in m["sections"]), m["total_passages"])
        self.assertEqual(m["screening_conclusion"], "UNKNOWN_NEEDS_AI_SCREENING")
        self.assertEqual(m["total_passages"], len(m["passages"]))
        self.assertTrue(all(x["review_disposition"] == "UNREVIEWED" for x in m["passages"]))

    def test_unflagged_passages_preserved_for_sampling(self):
        m = self._map("synthetic_no_number.html")
        self.assertGreater(len(m["passages"]), m["total_candidates"])
        self.assertTrue(all("text" in p for p in m["passages"]))
        self.assertEqual(validate_map(m), [])

    def test_empty_document_is_error_not_no_royalty(self):
        with self.assertRaises(ParseError):
            parse_document((FIX / "synthetic_empty.html").read_bytes(), "synthetic_empty.html")

    def test_pdf_unsupported_is_not_silent(self):
        with self.assertRaises((UnsupportedDocument, ParseError)):
            parse_document(b"%PDF-1.7\nnot a real pdf", "scan.pdf")

    def test_multidocument_sgml_is_refused(self):
        sgml = b"<DOCUMENT><TYPE>EX-10<TEXT>one</TEXT></DOCUMENT>\n<DOCUMENT><TEXT>two</TEXT></DOCUMENT>"
        with self.assertRaises(UnsupportedDocument):
            parse_document(sgml, "submission.txt")

    def test_corrupted_map_hash_detected(self):
        m = self._map("synthetic_licence.html")
        m["passages"][2]["text"] = "CORRUPTED"
        self.assertIn("TEXT_HASH_MISMATCH", validate_map(m))

    def test_map_command_atomic_and_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "map.json"
            argv = ["map", "--input", str(FIX / "synthetic_licence.html"),
                    "--source-url", "https://www.sec.gov/Archives/edgar/data/1/2/test.htm",
                    "--out", str(out)]
            self.assertEqual(main(argv), 0)
            self.assertTrue(out.exists())
            self.assertEqual(main(argv), 2)  # no accidental overwrite
            self.assertEqual(main(argv + ["--skip-existing"]), 0)
            self.assertEqual(main(["validate-map", "--input", str(out)]), 0)
            self.assertIn("original_sha256", read_json(out))

    def test_unreadable_source_creates_exception_record(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "bad.json"
            code = main(["map", "--input", str(FIX / "synthetic_empty.html"), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertFalse(out.exists())
            fail = read_json(str(out) + ".failed.json")
            self.assertEqual(fail["status"], "EXCEPTION")


if __name__ == "__main__":
    unittest.main()
