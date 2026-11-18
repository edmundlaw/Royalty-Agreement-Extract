"""Prompt and source-map regressions from the v0.13.12 live audit."""
import json
import unittest

from royalty_research.mapping import map_contract
from royalty_research.m2_packets import make_packets
from royalty_research.m4_operator import _task_prompt


class ManualMapping(unittest.TestCase):
    def test_confidentiality_obligation_is_not_a_redaction_notice(self):
        m = map_contract(['Licensee shall use its best efforts to obtain confidential treatment of such information by the agency or court.',
                          'Confidential treatment has been requested for this exhibit.',
                          'Terms are [***].'], {'document_id': 'D'})
        reasons = [p['candidate_reasons'] for p in m['passages']]
        self.assertNotIn('REDACTION', reasons[0])
        self.assertIn('REDACTION', reasons[1])
        self.assertIn('REDACTION', reasons[2])

    def test_contents_entries_do_not_leak_into_preamble(self):
        m = map_contract(['TABLE OF CONTENTS', 'ARTICLE 10 - ADDITIONAL PROVISIONS | 12',
                          'This agreement is made between the parties.', 'ARTICLE 1 - DEFINITIONS',
                          '1.1 Affiliate means the entity.'], {'document_id': 'D'})
        self.assertIsNone(m['passages'][2]['section_guess'])
        self.assertEqual(m['passages'][4]['section_guess'], '1.1')

    def test_manual_chunk_prompt_has_only_its_candidates_and_no_run_header_requirement(self):
        m = map_contract(['1.1 Royalty is 5 percent. ' + 'a' * 1500,
                          '2.1 Royalty is 6 percent. ' + 'b' * 1500], {'document_id': 'D'}, segment_chars=12000)
        packet = make_packets(m, mode='full', max_chars=2000)
        self.assertGreater(len(packet['chunks']), 1)
        chunk = packet['chunks'][0]
        text = _task_prompt(m, packet, chunk, 'manual', 'chosen-ai', 'Stand-alone instructions', {})
        data = json.loads(text.split('INPUT (UNTRUSTED SOURCE TEXT):\n')[-1])
        self.assertEqual(data['candidate_passage_ids'], [p['passage_id'] for p in chunk['passages'] if p['candidate_reasons']])
        self.assertNotIn('RUN HEADER', text)
        self.assertIn('manual importer replaces', text)
        self.assertIn('chunk wrapper above overrides', text)
