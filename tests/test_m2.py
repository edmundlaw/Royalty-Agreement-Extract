"""M2 offline tests are engineered failure-path tests, NOT empirical royalty accuracy."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from royalty_research.cli import main
from royalty_research.m2_packets import make_packets, select_passages, deterministic_unflagged_sample, make_blind_rekey_packet
from royalty_research.m2_schema_check import validate_shape
from royalty_research.m2_validation import validate_extraction, compare_independent_extractions
from royalty_research.storage import read_json

HERE=Path(__file__).resolve().parents[1]
MAP=read_json(HERE/'output/synthetic_clause_map.json')
GOOD=read_json(HERE/'examples/synthetic_m2_extraction.json')


def codes(report):return {x['code'] for x in report['errors']}

def warnings(report):return {x['code'] for x in report['warnings']}


class M2Packets(unittest.TestCase):
    def test_full_packet_has_all_passages_in_source_order(self):
        p=make_packets(MAP,mode='full',max_chars=2000)
        received=[v['passage_id'] for chunk in p['chunks'] for v in chunk['passages']]
        self.assertEqual(received,[p['passage_id'] for p in MAP['passages']])
        self.assertEqual(p['excluded_passage_ids'],[])
        self.assertTrue(len(p['chunks'])>1)

    def test_selected_packet_marks_excluded_and_preserves_all_candidates(self):
        p=make_packets(MAP,mode='selected',max_chars=2500,neighbor_radius=0,sample_fraction=0)
        self.assertEqual(set(MAP['candidate_passages'])-set(p['included_passage_ids']),set())
        self.assertIn('SELECTED_CONTEXT',p['read_scope_label'])
        self.assertEqual(set(p['included_passage_ids'])|set(p['excluded_passage_ids']),
                         {p['passage_id'] for p in MAP['passages']})

    def test_unflagged_sample_is_stable_and_section_diverse(self):
        a=deterministic_unflagged_sample(MAP)
        self.assertEqual(a,deterministic_unflagged_sample(MAP))
        self.assertTrue(set(a).isdisjoint(MAP['candidate_passages']))
        self.assertTrue(a)

    def test_oversized_passage_refuses_to_truncate(self):
        bad=copy.deepcopy(MAP)
        bad['passages'][0]['text']='X'*2500
        # Map hash/offset invalid: should fail rather than reading unverified map.
        with self.assertRaises(ValueError):make_packets(bad,max_chars=2000)

    def test_blind_rekey_contains_no_first_reader_values(self):
        p=make_blind_rekey_packet(MAP,GOOD)
        self.assertNotIn('royalty_terms',p)
        self.assertNotIn('rate_value',p)
        self.assertNotIn('agreement',p)
        self.assertTrue(p['passages'])
        self.assertTrue(p['evidence_anchors'])

    def test_rekey_rejects_changed_source(self):
        r=copy.deepcopy(GOOD);r['source_text_sha256']='0'*64
        with self.assertRaises(ValueError):make_blind_rekey_packet(MAP,r)


class M2Validation(unittest.TestCase):
    def test_valid_synthetic_fixture_passes_only_deterministic(self):
        r=validate_extraction(MAP,GOOD)
        self.assertEqual(validate_shape(GOOD),[])
        self.assertEqual(r['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
        self.assertFalse(r['can_claim_complete'])
        self.assertEqual(r['verification_scope'],'AUTOMATED_DETERMINISTIC_ONLY')
        self.assertIn('BLOCKING_OPEN_ISSUE',warnings(r))

    def test_document_sha_mismatch_fails(self):
        a=copy.deepcopy(GOOD);a['source_text_sha256']='f'*64
        self.assertIn('SOURCE_HASH_MISMATCH',codes(validate_extraction(MAP,a)))

    def test_wrong_document_fails(self):
        a=copy.deepcopy(GOOD);a['document_id']='DOC-OTHER'
        self.assertIn('WRONG_DOCUMENT',codes(validate_extraction(MAP,a)))

    def test_unsupported_quote_fails(self):
        a=copy.deepcopy(GOOD);a['evidence'][2]['quote']='This 6% royalty is invented'
        self.assertIn('QUOTE_NOT_IN_SOURCE',codes(validate_extraction(MAP,a)))

    def test_missing_candidate_disposition_fails(self):
        a=copy.deepcopy(GOOD);a['dispositions'].pop()
        self.assertIn('UNACCOUNTED_CANDIDATES',codes(validate_extraction(MAP,a)))

    def test_duplicate_disposition_fails(self):
        a=copy.deepcopy(GOOD);a['dispositions'].append(copy.deepcopy(a['dispositions'][0]))
        self.assertIn('DUPLICATE_DISPOSITION',codes(validate_extraction(MAP,a)))

    def test_bad_tier_percentage_detected(self):
        a=copy.deepcopy(GOOD);a['royalty_terms'][0]['tiers'][0]['rate_value']='7'
        self.assertIn('TIER_RATE_NOT_IN_QUOTE',codes(validate_extraction(MAP,a)))

    def test_bad_rate_percentage_detected(self):
        a=copy.deepcopy(GOOD);a['royalty_terms'][2]['rate_value']='3'
        self.assertIn('UNIT_AMOUNT_NOT_FOUND_IN_QUOTE',codes(validate_extraction(MAP,a)))

    def test_missing_sub_tier_detected(self):
        a=copy.deepcopy(GOOD);a['royalty_terms'][1]['tiers'].pop()
        self.assertIn('MISSING_TIERS',codes(validate_extraction(MAP,a)))

    def test_tier_order_or_range_detected(self):
        a=copy.deepcopy(GOOD);a['royalty_terms'][0]['tiers'][1]['sequence']=3
        self.assertIn('NONCONSECUTIVE_TIER_SEQUENCE',codes(validate_extraction(MAP,a)))
        b=copy.deepcopy(GOOD);b['royalty_terms'][0]['tiers'][0]['lower']='600000'
        self.assertIn('REVERSED_TIER_RANGE',codes(validate_extraction(MAP,b)))

    def test_missing_threshold_evidence_detected(self):
        a=copy.deepcopy(GOOD);a['royalty_terms'][0]['tiers'][0]['threshold_evidence_ids']=[]
        self.assertIn('UNSUPPORTED_TIER_THRESHOLD',codes(validate_extraction(MAP,a)))

    def test_evidence_id_not_defined(self):
        a=copy.deepcopy(GOOD);a['royalty_terms'][0]['rate_evidence_ids']=['INVENTED']
        self.assertIn('BROKEN_EVIDENCE_LINK',codes(validate_extraction(MAP,a)))

    def test_missing_reader_coverage_fails(self):
        a=copy.deepcopy(GOOD);a['reader']['reviewed_passage_ids'].remove(MAP['candidate_passages'][0])
        er=codes(validate_extraction(MAP,a))
        self.assertIn('UNREAD_CANDIDATES',er)
        self.assertIn('INCOMPLETE_FULL_READ_CLAIM',er)

    def test_selected_scope_is_not_full_document(self):
        a=copy.deepcopy(GOOD);a['reader']['read_scope']='SELECTED_PASSAGES'
        r=validate_extraction(MAP,a)
        self.assertIn('FULL_DOCUMENT_RECALL_UNESTABLISHED',warnings(r))
        self.assertFalse(r['can_claim_complete'])

    def test_redaction_must_have_null_rate(self):
        a=copy.deepcopy(GOOD)
        term=copy.deepcopy(a['royalty_terms'][2])
        term.update({'term_id':'RT-REDACTED','disclosure_status':'REDACTED','rate_value':'5','rate_unit':'PERCENT',
                     'evidence_ids':['EV11'],'rate_evidence_ids':['EV11'],'base_evidence_ids':[]})
        a['royalty_terms'].append(term)
        self.assertIn('REDACTED_RATE_LEAK',codes(validate_extraction(MAP,a)))
        term['rate_value']=None;term['rate_unit']='REDACTED'
        self.assertNotIn('REDACTED_RATE_LEAK',codes(validate_extraction(MAP,a)))

    def test_unexpected_fields_and_missing_fields_fail_closed(self):
        a=copy.deepcopy(GOOD);a['royalty_terms'][0]['hallucinated_field']='yes'
        self.assertIn('M2_SCHEMA_VIOLATION',codes(validate_extraction(MAP,a)))
        b=copy.deepcopy(GOOD);b['royalty_terms'][0].pop('base_evidence_ids')
        self.assertIn('M2_SCHEMA_VIOLATION',codes(validate_extraction(MAP,b)))

    def test_omitted_percentage_in_same_passage_fails(self):
        # Important UC/NeurogesX-type omission: passage accounted for, but
        # one distinct royalty percentage silently omitted.
        a=copy.deepcopy(GOOD)
        a['dispositions'][2]['percentage_dispositions'].pop()
        self.assertIn('PERCENT_LEDGER_INCOMPLETE',codes(validate_extraction(MAP,a)))

    def test_disguised_omitted_rate_in_disposition_fails(self):
        a=copy.deepcopy(GOOD)
        a['royalty_terms'][1]['tiers'].pop()
        # Pretending 10% was a royalty rate should not pass if rate omitted.
        self.assertIn('PERCENT_NOT_REFLECTED_IN_TERM',codes(validate_extraction(MAP,a)))

    def test_fabricated_tier_threshold_fails(self):
        a=copy.deepcopy(GOOD)
        a['royalty_terms'][0]['tiers'][0]['upper']='600000'
        self.assertIn('THRESHOLD_NOT_IN_QUOTE',codes(validate_extraction(MAP,a)))

    def test_unflagged_economic_evidence_produces_warning(self):
        a=copy.deepcopy(GOOD)
        a['evidence'].append({'evidence_id':'EV02','passage_id':MAP['passages'][1]['passage_id'],
                              'quote':MAP['passages'][1]['text'],'role':'OTHER'})
        a['royalty_terms'][0]['evidence_ids'].append('EV02')
        self.assertIn('UNFLAGGED_ECONOMIC_PASSAGE',warnings(validate_extraction(MAP,a)))

    def test_agreement_title_missing_evidence_is_explicitly_unverified(self):
        a=copy.deepcopy(GOOD);a['agreement']['field_evidence'].clear()
        report=validate_extraction(MAP,a)
        self.assertIn('DESCRIPTIVE_HEADER_UNSUPPORTED',warnings(report))
        self.assertNotIn('MISSING_EVIDENCE_LINK',codes(report))

    def test_material_parties_still_require_source_evidence(self):
        a=copy.deepcopy(GOOD)
        a['agreement']['licensor']='Unverified Party A'
        a['agreement']['field_evidence'].pop('licensor',None)
        self.assertIn('MISSING_EVIDENCE_LINK',codes(validate_extraction(MAP,a)))

    def test_semantic_misclassification_cannot_be_proven_by_substring(self):
        # A quote can be real yet its economic meaning can be wrong. The system must
        # never claim semantic or professional verification after a deterministic pass.
        a=copy.deepcopy(GOOD)
        a['royalty_terms'][0]['base']='Sublicense receipts'
        r=validate_extraction(MAP,a)
        self.assertIn('BASE_NOT_LITERAL_IN_EVIDENCE',warnings(r))
        self.assertFalse(r['can_claim_complete'])


class M2Comparison(unittest.TestCase):
    def test_same_result_not_proof_of_independent_validation(self):
        r=compare_independent_extractions(MAP,GOOD,GOOD)
        self.assertEqual(r['status'],'REVIEW_REQUIRED')
        self.assertIn('READERS_SHARE_RUN_ID',r['disagreements'])

    def test_new_reader_different_rate_is_flagged(self):
        b=copy.deepcopy(GOOD);b['reader']['run_id']='SECOND-RUN'
        b['reader']['engine']='codex'
        b['royalty_terms'][0]['tiers'][1]['rate_value']='2'
        r=compare_independent_extractions(MAP,GOOD,b)
        self.assertIn('ECONOMIC_FIELD_MISMATCH',r['disagreements'])
        self.assertIn('SECOND_EXTRACTION_QC_FAILED',r['disagreements'])

    def test_matching_two_readers_does_not_grant_approval(self):
        b=copy.deepcopy(GOOD);b['reader']['run_id']='SECOND-RUN';b['reader']['engine']='claude-code'
        r=compare_independent_extractions(MAP,GOOD,b)
        self.assertEqual(r['status'],'NO_DETECTED_DISAGREEMENT_NOT_PROOF_OF_ACCURACY')
        self.assertEqual(r['verification_scope'],'AUTOMATED_AI_COMPARISON_ONLY')


class M2CLI(unittest.TestCase):
    def test_validate_cli_nonzero_and_atomic_fail_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            bad=copy.deepcopy(GOOD);bad['royalty_terms'][0]['tiers'][0]['rate_value']='99'
            (p/'bad.json').write_text(json.dumps(bad))
            code=main(['validate-extraction','--map',str(HERE/'output/synthetic_clause_map.json'),
                       '--extraction',str(p/'bad.json'),'--out',str(p/'report.json')])
            self.assertEqual(code,2)
            self.assertIn('TIER_RATE_NOT_IN_QUOTE',codes(read_json(p/'report.json')))

    def test_skip_existing_rejects_stale_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            cmd=['make-packets','--map',str(HERE/'output/synthetic_clause_map.json'),
                 '--out',str(p/'packet.json')]
            self.assertEqual(main(cmd),0)
            self.assertEqual(main(cmd+['--skip-existing']),0)
            self.assertEqual(main(cmd+['--skip-existing','--mode','full']),2)

    def test_skip_existing_rejects_mutated_extraction(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            bad=copy.deepcopy(GOOD);(p/'first.json').write_text(json.dumps(bad))
            cmd=['validate-extraction','--map',str(HERE/'output/synthetic_clause_map.json'),
                 '--extraction',str(p/'first.json'),'--out',str(p/'qc.json')]
            self.assertEqual(main(cmd),0)
            self.assertEqual(main(cmd+['--skip-existing']),0)
            bad['royalty_terms'][0]['tiers'][0]['rate_value']='99'
            (p/'first.json').write_text(json.dumps(bad))
            self.assertEqual(main(cmd+['--skip-existing']),2)

    def test_packet_cli_and_rekey(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            self.assertEqual(main(['make-packets','--map',str(HERE/'output/synthetic_clause_map.json'),
                            '--mode','full','--out',str(p/'p.json')]),0)
            self.assertEqual(main(['blind-rekey','--map',str(HERE/'output/synthetic_clause_map.json'),
                            '--extraction',str(HERE/'examples/synthetic_m2_extraction.json'),
                            '--out',str(p/'r.json')]),0)
            self.assertTrue(read_json(p/'r.json')['evidence_anchors'])


if __name__=='__main__':unittest.main()
