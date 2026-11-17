"""Additional fail-closed and formal-schema compatibility checks."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

from royalty_research.cli import main
from royalty_research.inventory import parse_filing_index_html
from royalty_research.parsing import parse_document
from royalty_research.sec_client import _AllowlistedRedirect
from royalty_research.storage import read_json

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / 'tests' / 'fixtures'

class QualityEdgeCases(unittest.TestCase):
    def test_refuse_redirect_to_third_party(self):
        h = _AllowlistedRedirect()
        with self.assertRaises(ValueError):
            h.redirect_request(Request('https://www.sec.gov/Archives/x'), None,
                               302, 'Moved', {}, 'https://evil.example/capture')

    def test_live_missing_contact_creates_failure_record(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'hits.jsonl'
            result = main(['discover', '--start', '2025-01-01', '--end', '2025-01-01',
                           '--query', 'royalty', '--out', str(f)])
            self.assertEqual(result, 2)
            self.assertFalse(f.exists())
            self.assertEqual(read_json(str(f)+'.failed.json')['status'], 'EXCEPTION')

    def test_refuse_unbounded_bulk_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'hits.jsonl'
            result = main(['discover', '--start', '2021-01-01', '--end', '2025-12-31',
                           '--query', 'royalty', '--out', str(f),
                           '--user-agent', 'Royalty Research contact@company.example'])
            self.assertEqual(result, 2)
            self.assertFalse(f.exists())
            self.assertIn('too long', read_json(str(f)+'.failed.json')['message'])

    def test_unreadable_filing_inventory_fails_explicitly(self):
        with self.assertRaises(ValueError):
            parse_filing_index_html('<table><tr><td>not an inventory</td></tr></table>',
                                    '1520358', '0001493152-25-000001')

    def test_parsed_source_keeps_multiple_numeric_forms(self):
        paragraphs,_=parse_document((FIX/'synthetic_licence.html').read_bytes(), 'synthetic_licence.html')
        s=' '.join(paragraphs)
        for token in ['6%', '4%', '25%', '10%', '1.5%', '$2 per device', '[***]', 'Schedule B']:
            self.assertIn(token,s)

    def test_formal_schema_internal_refs_resolve(self):
        schema=json.loads((ROOT/'schemas'/'agreement.schema.json').read_text())
        defs=schema['$defs']
        def walk(node):
            if isinstance(node,dict):
                if '$ref' in node:
                    ref=node['$ref']
                    self.assertTrue(ref.startswith('#/$defs/'), ref)
                    self.assertIn(ref.split('/')[-1], defs)
                for v in node.values():walk(v)
            elif isinstance(node,list):
                for v in node:walk(v)
        walk(schema)
        self.assertIn('rights',schema['properties'])
        self.assertIn('amendments',schema['properties'])
        self.assertIn('document_agreements',schema['properties'])

if __name__=='__main__':unittest.main()
