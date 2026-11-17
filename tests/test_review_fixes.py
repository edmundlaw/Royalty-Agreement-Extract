"""Regression tests for defects found in the independent review of v0.5.0 (2026-11-14).

Each test reproduces a failure first seen on a real SEC exhibit or a real subscription
model call. Excerpts are short quotations of public SEC filings:
- Market Finders / Daugherty, Exhibit 10.2 (accession 0001493152-13-000675)
- University of California / NeurogesX, Exhibit 10.6 (accession 0001193125-07-022650)
"""
import json
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from royalty_research.discovery import build_search_url
from royalty_research.m2_schema_check import validate_shape
from royalty_research.m4_operator import _task_prompt
from royalty_research.mapping import map_contract
from royalty_research.parsing import text_to_paragraphs

ROOT = Path(__file__).resolve().parents[1]

# Source line breaks exactly as filed: the clause is wrapped inside one <P>.
MARKET_FINDERS_42 = (
    '<P STYLE="margin:0">4.2&nbsp;&nbsp;<U>Royalty\nRate</U>. The Royalty Rate shall be: 6% of Net Sales up to '
    '$500,000 of Net Sales for each Agreement Year; 4% of Net Sales from\n$500,000 up to $2,500,000 of Net Sales '
    'for each Agreement Year; 2% of Net Sales from $2,500,000 up to $20,000,000 of Net Sales\nfor each Agreement '
    'Year; and 1% of Net Sales in excess of $20,000,000 of Net Sales for each Agreement Year.</P>')

# Table cells hold block elements, and the currency sign sits in its own cell, as filed.
NEUROGESX_TABLE = (
    '<TABLE><TR><TD><P>Percentage</P></TD><TD><P>Aggregate Sublicense Fees</P></TD></TR>'
    '<TR><TD><P>25%</P></TD><TD><P>&lt; $250,000</P></TD></TR>'
    '<TR><TD><P>10%</P></TD><TD><P>$250,000 -- $2,000,000</P></TD></TR>'
    '<TR><TD><P>5%</P></TD><TD><P>&gt; $2,000,000</P></TD></TR></TABLE>')
MINIMUM_TABLE = (
    '<TABLE><TR><TD><P>3rd and 4th</P></TD><TD><P>$</P></TD><TD><P>50,000.00</P></TD></TR>'
    '<TR><TD>Rate</TD><TD>25</TD><TD>%</TD></TR></TABLE>')


def _paras(body):
    return text_to_paragraphs("<html><body>" + body + "</body></html>", True)


class ParserRegression(unittest.TestCase):
    def test_wrapped_clause_is_one_passage(self):
        paras = _paras(MARKET_FINDERS_42)
        self.assertEqual(len(paras), 1)
        self.assertIn("4% of Net Sales from $500,000 up to $2,500,000", paras[0])
        self.assertIn("1% of Net Sales in excess of $20,000,000", paras[0])

    def test_table_row_keeps_rate_with_threshold(self):
        paras = _paras(NEUROGESX_TABLE)
        self.assertEqual(paras, ["Percentage | Aggregate Sublicense Fees", "25% | < $250,000",
                                 "10% | $250,000 -- $2,000,000", "5% | > $2,000,000"])

    def test_symbol_only_cells_are_glued_to_their_value(self):
        paras = _paras(MINIMUM_TABLE)
        self.assertEqual(paras, ["3rd and 4th | $50,000.00", "Rate | 25%"])
        mapped = map_contract(paras, {"source_url": "https://www.sec.gov/x"})
        self.assertIn("MONEY", mapped["passages"][0]["candidate_reasons"])
        self.assertIn("PERCENT", mapped["passages"][1]["candidate_reasons"])

    def test_layout_table_keeps_paragraph_breaks(self):
        cell = "".join(f"<p>Paragraph {i} of a page-layout cell.</p>" for i in range(1, 7))
        paras = _paras(f"<table><tr><td>{cell}</td></tr></table>")
        self.assertEqual(len(paras), 6)

    def test_no_text_is_lost_in_unclosed_row(self):
        paras = _paras("<p>before</p><table><tr><td>a1</td><td>b1")
        self.assertEqual(paras, ["before", "a1 | b1"])


class ContractRegression(unittest.TestCase):
    def test_prompt_names_the_required_schema_key(self):
        mapping = map_contract(_paras(MARKET_FINDERS_42), {"source_url": "https://www.sec.gov/x"})
        packet = {"candidate_passage_ids": mapping["candidate_passages"], "read_scope_label": "FULL_DOCUMENT_CHUNKED"}
        chunk = {"chunk_index": 1, "chunk_count": 1,
                 "passages": [{"passage_id": p["passage_id"], "section": p["section_guess"],
                               "candidate_reasons": p["candidate_reasons"], "text": p["text"]}
                              for p in mapping["passages"]]}
        prompt = _task_prompt(mapping, packet, chunk, "claude", "sonnet", "TEMPLATE", {})
        self.assertIn('"schema" (the string "m3-chunk.1"', prompt)

    def test_engine_claude_is_accepted_by_the_extraction_schema(self):
        for path in (ROOT / "schemas/m2_extraction.schema.json",
                     ROOT / "src/royalty_research/schemas/m2_extraction.schema.json"):
            schema = json.loads(path.read_text())
            self.assertIn("claude", schema["$defs"]["reader"]["properties"]["engine"]["enum"], path)
        self.assertTrue(callable(validate_shape))

    def test_multiword_query_is_sent_as_a_phrase(self):
        q = parse_qs(urlparse(build_search_url("license agreement", date(2024, 5, 8), date(2024, 5, 8), 0, 100)).query)["q"][0]
        self.assertEqual(q, '"license agreement"')
        q = parse_qs(urlparse(build_search_url("royalty", date(2024, 5, 8), date(2024, 5, 8), 0, 100)).query)["q"][0]
        self.assertEqual(q, "royalty")
        q = parse_qs(urlparse(build_search_url("royalty OR royalties", date(2024, 5, 8), date(2024, 5, 8), 0, 100)).query)["q"][0]
        self.assertEqual(q, "royalty OR royalties")


if __name__ == "__main__":
    unittest.main()
