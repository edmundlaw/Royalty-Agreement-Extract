"""Offline full-source production regression and controller tests."""
import json
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from royalty_research.storage import read_json, sha256, json_bytes
from royalty_research.m13_production import prepare_one,run_boundary,batch
from royalty_research.m4_operator import import_manual_result, load_plan, _command, _usage
from royalty_research.m13_two_reader import finalize, source_check, _in_quotes
from royalty_research.lean import validate as lean_validate

ROOT=Path(__file__).resolve().parents[1]
SAVED=ROOT/'tests/fixtures/m12_saved'

class FullSourceProduction(unittest.TestCase):
    def test_historical_evidence_all_available_in_full_packet(self):
        for name in ('MarketFinders','NeurogesX','Qualigen','Kirklands'):
            m=read_json(SAVED/(name+'_map.json'))
            e=read_json(SAVED/(name+'_extraction.json'))
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                run=Path(d)/'run'
                prepare_one(m,run,mode='manual',engine='codex',model='chosen-ai')
                packet=read_json(run/'source/full_packet.json')
                ids=[p['passage_id'] for c in packet['chunks'] for p in c['passages']]
                self.assertEqual(ids,[p['passage_id'] for p in m['passages']])
                self.assertEqual(sum(x['passage_id'] in ids for x in e['evidence']),len(e['evidence']))
                self.assertEqual(source_check(m,e)['errors'],[])

    def test_manual_import_and_excel_no_model_call(self):
        m=read_json(ROOT/'output/synthetic_clause_map.json')
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)/'runs'/'one'
            prepare_one(m,run,mode='manual',engine='codex',model='chosen-ai',max_chars=64000)
            result=run_boundary(run.parent,max_calls=1,max_prompt_chars=300000,execute=True)
            self.assertEqual(result['calls_attempted'],0)
            self.assertEqual(result['outcomes'][0]['status'],'MANUAL_RESULT_REQUIRED')
            plan,packet,_=load_plan(run/'reader_a')
            self.assertEqual(plan['engine'],'manual')
            src=read_json(ROOT/'examples/synthetic_m2_extraction.json')
            chunk=packet['chunks'][0]
            obj={'schema':'m3-chunk.1','document_id':m['document_id'],
              'source_text_sha256':m['text_sha256'],'packet_sha256':sha256(json_bytes(packet)),
              'chunk_index':1,'chunk_count':len(packet['chunks']),
              'reviewed_passage_ids':[p['passage_id'] for p in chunk['passages']],
              'reader':{},'agreement':src['agreement'],'royalty_terms':src['royalty_terms'],
              'other_payments':src['other_payments'],'evidence':src['evidence'],
              'dispositions':src['dispositions'],'open_issues':src['open_issues'],
              'amendment_status':src['amendment_status']}
            response=Path(d)/'answer.json';response.write_text(json.dumps(obj))
            self.assertEqual(import_manual_result(run/'reader_a','CHUNK-0001',response)['model_calls'],0)
            self.assertEqual(finalize(run)['state'],'SINGLE_READER_NOT_CHECKED')
            self.assertTrue((run/'output/Royalty_Research_M13.xlsx').exists())

    def test_effort_command_and_budget(self):
        self.assertIn('model_reasoning_effort="low"',_command('codex','mock-a','out','low'))
        self.assertIn('--effort',_command('claude','mock-a','out','high'))
        m=read_json(ROOT/'output/synthetic_clause_map.json')
        with tempfile.TemporaryDirectory() as d:
            run=Path(d)/'runs'/'one'
            prepare_one(m,run,mode='single',engine='codex',model='mock-a',effort='low')
            plan,_,_=load_plan(run/'reader_a')
            self.assertEqual(plan['reasoning_effort'],'low')
            self.assertEqual(run_boundary(run.parent,max_calls=1,max_prompt_chars=1000)['outcomes'][0]['status'],'STOPPED_PROMPT_BUDGET')
            with self.assertRaises(ValueError):
                run_boundary(run.parent,max_calls=1,max_prompt_chars=300000,max_reported_tokens=0)
        self.assertEqual(_usage('codex','{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":8,"output_tokens":3}}'),
                         {'input_tokens':10,'cached_input_tokens':8,'output_tokens':3})

    def test_lean_adversarial_substring_rejected(self):
        source={'P1':'Licensee shall pay a royalty of 15% of Net Sales.'}
        summary={'coverage':'SCREENED_EXCERPTS_ONLY','royalty_terms':[{'type':'PRODUCT_SALES',
          'value_as_reported':'5%','basis':'Gross Sales','passage_id':'P1',
          'exact_quote':source['P1']}], 'other_payments':[]}
        self.assertTrue(lean_validate(summary,source))
        self.assertFalse(_in_quotes('3',['E1'],{'E1':{'quote':'30% of Net Sales'}},percent=True))
        self.assertFalse(_in_quotes('5',['E1'],{'E1':{'quote':'15% of Net Sales'}},percent=True))

    def test_full_source_adversarial_values_and_identity(self):
        m=read_json(SAVED/'Qualigen_map.json')
        original=read_json(SAVED/'Qualigen_extraction.json')
        for wrong in ('3','30'):
            e=copy.deepcopy(original);e['royalty_terms'][0]['rate_value']=wrong
            if wrong!=original['royalty_terms'][0]['rate_value']:
                self.assertIn('M13_RATE_NOT_IN_QUOTE',{x['code'] for x in source_check(m,e)['errors']})
        e=copy.deepcopy(original);e['source_url']='https://www.sec.gov/Archives/edgar/data/9/wrong.txt'
        self.assertIn('M13_BINDING',{x['code'] for x in source_check(m,e)['errors']})
        e=copy.deepcopy(original);e['document_id']='DOC-WRONG'
        self.assertIn('M13_BINDING',{x['code'] for x in source_check(m,e)['errors']})
        e=copy.deepcopy(original);e['royalty_terms']=[];e['other_payments']=[]
        result=source_check(m,e)
        self.assertFalse(result['can_claim_complete'])
        self.assertNotEqual(result['deterministic_status'],'PASS_SEMANTIC_VERIFIED')

    def test_semantic_fields_never_claim_verified(self):
        m=read_json(SAVED/'Qualigen_map.json');e=read_json(SAVED/'Qualigen_extraction.json')
        e['agreement']['licensor']='Invented licensor'
        e['agreement']['exclusivity']='Exclusive'
        result=source_check(m,e)
        self.assertFalse(result['can_claim_complete'])
        self.assertEqual(result['verification_scope'],'SOURCE_CHECK_ONLY')

    def test_batch_deduplicates_and_limits_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);u='https://www.sec.gov/Archives/edgar/data/1/123/a.txt'
            candidates=root/'candidates.jsonl'
            candidates.write_text('\n'.join(json.dumps({'source_url':x}) for x in (u,u,u.replace('a.txt','b.txt'))))
            with patch('royalty_research.m13_production.SECClient') as client:
                client.return_value.fetch.return_value=b'Licensee shall pay 5% royalty on Net Sales.'
                result=batch(candidates,root/'batch',user_agent='Research name email@example.com',mode='manual',
                    engine='codex',model='chosen-ai',max_agreements=1)
                self.assertEqual(client.return_value.fetch.call_count,1)
            index=read_json(root/'batch/candidate_register.json')
            self.assertEqual(result['candidates'],2)
            self.assertEqual(index[1]['status'],'NOT_PREPARED_AGREEMENT_LIMIT')

if __name__=='__main__':unittest.main()
