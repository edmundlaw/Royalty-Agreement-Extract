"""Adversarial tests for source-preserving splits and subscription CLI safety.

Fake CLI binaries deliberately NEVER contact a model or the network.
"""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from royalty_research.mapping import map_contract,validate_map
from royalty_research.m2_packets import make_packets
from royalty_research.storage import read_json,sha256,json_bytes
from royalty_research.m4_operator import (
    _check_packet,create_plan,load_plan,status,run_next,authorize_retry,
    clear_limit,merge_plan,_task_state,_attempts,FORBIDDEN_ENV,
)

ROOT=Path(__file__).resolve().parent.parent

FAKE = r'''#!PYTHON_PATH
import json,sys,re,os
from pathlib import Path
payload=sys.stdin.read()
head=re.search(r'RUN HEADER: reader.engine=([^;]+); reader.model=([^;]+); reader.run_id=([^\.]+)\.',payload)
assert head, 'bad header'
engine,model,runid=head.groups()
src=json.loads(payload.split('INPUT (UNTRUSTED SOURCE TEXT):\n')[-1])
mode=os.environ.get('FAKE_MODE','ok')
if mode=='limit':
 print('usage limit reached; resets in 5 hours',file=sys.stderr)
 sys.exit(1)
if mode=='fail':
 print('some generic CLI failure',file=sys.stderr)
 sys.exit(2)
res={'schema':'m3-chunk.1','document_id':src['document_id'],
 'source_text_sha256':src['source_text_sha256'],'packet_sha256':src['packet_sha256'],
 'chunk_index':src['chunk_index'],'chunk_count':src['chunk_count'],
 'reviewed_passage_ids':src['reviewed_passage_ids'],
 'reader':{'engine':engine,'model':model,'run_id':runid},
 'agreement':{'title':None,'field_evidence':{}},
 'royalty_terms':[],'other_payments':[],'evidence':[],'dispositions':[],'open_issues':[],
 'amendment_status':'NOT_CHECKED'}
if mode=='wrong':res['source_text_sha256']='bad'
if engine=='claude':
 print(json.dumps({'is_error':False,'result':json.dumps(res)}))
else:
 path=Path(sys.argv[sys.argv.index('--output-last-message')+1])
 path.write_text(json.dumps(res),encoding='utf8')
'''

class M4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.mapping=map_contract([
            '1.0 The Licensee shall pay five percent (5%) of Net Sales.',
            '2.0 Late payment shall bear interest at 1.5% per annum.',
            '3.0 Sublicense income fees are described in Schedule A.',
        ],{'document_id':'DOC-M4-FAKE','source_url':'https://www.sec.gov/Archives/edgar/data/1/123/test.htm'})
        self.packet=make_packets(self.mapping,mode='full',max_chars=2000)
        self.instructions=(ROOT/'prompts/FIRST_READER.md').read_text()
        self.schema=read_json(ROOT/'schemas/m2_extraction.schema.json')

    def make_plan(self,engine='claude',packet=None):
        path=self.base/'plan'
        create_plan(self.mapping,packet or self.packet,path,engine=engine,model='mock-light',
                    instructions=self.instructions,schema=self.schema)
        return path

    def make_fake(self):
        p=self.base/'mock_cli';p.write_text(FAKE.replace('PYTHON_PATH',sys.executable),encoding='utf-8')
        p.chmod(0o755)
        return p

    def test_long_line_is_split_with_byte_exact_parent_reconstruction(self):
        huge='10.0 Royalty '+('special terms and conditions ' * 200)+'5% net sales '+('end of clause ' * 200)
        mapping=map_contract([huge,'11.0 Term: ten years.'],{'document_id':'DOC-LONG'},segment_chars=1000)
        self.assertGreater(mapping['total_passages'],2)
        self.assertEqual(validate_map(mapping),[])
        manifest=mapping['source_segmentation']['split_original_paragraphs'][0]
        reconstructed=''.join(mapping['passages'][i-1]['text'] for i in manifest['fragment_indices'])
        self.assertEqual(reconstructed,huge)
        self.assertEqual(sha256(reconstructed.encode()),manifest['original_sha256'])
        self.assertTrue(all('SOURCE_SPLIT_ADJACENCY_REVIEW' in mapping['passages'][i-1]['candidate_reasons']
                            for i in manifest['fragment_indices']))
        packet=make_packets(mapping,mode='full',max_chars=2000)
        self.assertEqual(len(packet['included_passage_ids']),mapping['total_passages'])

    def test_forced_split_does_not_drop_character(self):
        huge='Z'*2207
        mapping=map_contract([huge],{'document_id':'DOC-FORCE'},segment_chars=1000)
        self.assertEqual(''.join(p['text'] for p in mapping['passages']),huge)
        self.assertTrue(mapping['source_segmentation']['split_original_paragraphs'][0]['forced_boundary'])

    def test_manifest_tampering_blocks_registration(self):
        m=map_contract(['C'*2200],{'document_id':'DOC-CHEAT'},segment_chars=1000)
        m['source_segmentation']['split_original_paragraphs'][0]['fragment_lengths'][0]=20
        self.assertIn('SEGMENT_SOURCE_PRESERVATION_FAILED',validate_map(m))

    def test_invalid_segmentation_bound_rejected(self):
        with self.assertRaises(ValueError):map_contract(['hello'],{'document_id':'DOC'},segment_chars=99)

    def test_plan_verifies_input_and_prompt_before_any_call(self):
        root=self.make_plan()
        self.assertEqual(status(root)['total'],len(self.packet['chunks']))
        self.assertEqual(run_next(root)['status'],'DRY_RUN_NO_AI_CALLED')
        with self.assertRaises(FileExistsError):self.make_plan()
        text=root/'prompts/CHUNK-0001.txt';text.write_text(text.read_text()+'bad')
        with self.assertRaisesRegex(ValueError,'prompt altered'):status(root)

    def test_packet_text_tampering_rejected_even_with_new_packet_digest(self):
        corrupt=copy.deepcopy(self.packet);corrupt['chunks'][0]['passages'][0]['text']='fraud'
        with self.assertRaisesRegex(ValueError,'source passage mismatch'):create_plan(
            self.mapping,corrupt,self.base/'bad',engine='claude',model='mock-light',
            instructions=self.instructions,schema=self.schema)

    def test_full_packet_requires_every_source_passage(self):
        wrong=copy.deepcopy(self.packet)
        wrong['chunks'][0]['passages']=wrong['chunks'][0]['passages'][:-1]
        with self.assertRaises(ValueError):_check_packet(self.mapping,wrong)

    def test_must_confirm_subscription_and_credit_controls(self):
        root=self.make_plan();exe=self.make_fake()
        with self.assertRaisesRegex(ValueError,'Explicit'):
            run_next(root,execute=True,confirm_subscription=True,allow_cli_path=exe)
        self.assertEqual(status(root)['tasks'][0]['attempts'],0)

    def test_api_key_variable_blocks_model_before_spend(self):
        root=self.make_plan();exe=self.make_fake()
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'SHOULD_NOT_BE_SENT'}):
            with self.assertRaisesRegex(RuntimeError,'NO CLI call'):
                run_next(root,execute=True,confirm_subscription=True,
                         confirm_credit_controls=True,allow_cli_path=exe)
        self.assertEqual(status(root)['tasks'][0]['attempts'],0)

    def test_success_capture_requires_separate_merge_qc(self):
        root=self.make_plan();exe=self.make_fake()
        with patch.dict(os.environ,{'FAKE_MODE':'ok'}):
            output=run_next(root,execute=True,confirm_subscription=True,
                            confirm_credit_controls=True,allow_cli_path=exe)
        self.assertEqual(output['status'],'CAPTURED_NOT_QC_APPROVED')
        self.assertEqual(status(root)['captured'],1)
        self.assertEqual(status(root)['tasks'][0]['state'],'CAPTURED_NOT_QC_APPROVED')
        # The mock did not extract the real 5% and 1.5%: merge MUST fail QC.
        merged=merge_plan(root)
        self.assertEqual(merged['status'],'FAIL')
        self.assertNotEqual(read_json(root/'merged_validation.json')['qc_errors'],[])
        with self.assertRaises(FileExistsError):merge_plan(root)

    def test_codex_backend_capture_requires_output_file(self):
        root=self.make_plan(engine='codex');exe=self.make_fake()
        with patch.dict(os.environ,{'FAKE_MODE':'ok'}):
            outcome=run_next(root,execute=True,confirm_subscription=True,
                             confirm_credit_controls=True,allow_cli_path=exe)
        self.assertEqual(outcome['status'],'CAPTURED_NOT_QC_APPROVED')
        self.assertEqual(read_json(root/'results/CHUNK-0001.json')['reader']['engine'],'codex')

    def test_model_fabricated_source_hash_never_captured(self):
        root=self.make_plan();exe=self.make_fake()
        with patch.dict(os.environ,{'FAKE_MODE':'wrong'}):
            res=run_next(root,execute=True,confirm_subscription=True,
                         confirm_credit_controls=True,allow_cli_path=exe)
        self.assertTrue(res['status'].startswith('FAILED'))
        self.assertEqual(status(root)['captured'],0)
        self.assertEqual(status(root)['tasks'][0]['state'],'FAILED_REQUIRES_MANUAL_RETRY')
        with self.assertRaisesRegex(RuntimeError,'authorize a retry'):
            run_next(root,execute=True,confirm_subscription=True,confirm_credit_controls=True,
                     allow_cli_path=exe)
        authorize_retry(root,'CHUNK-0001','Model returned corrupted hash; manually retesting')
        self.assertEqual(status(root)['tasks'][0]['state'],'PENDING')
        with patch.dict(os.environ,{'FAKE_MODE':'ok'}):
            self.assertEqual(run_next(root,execute=True,confirm_subscription=True,
                confirm_credit_controls=True,allow_cli_path=exe)['status'],'CAPTURED_NOT_QC_APPROVED')
        self.assertEqual(status(root)['tasks'][0]['attempts'],2)

    def test_interruption_cannot_autoretry_and_explicit_release_works(self):
        root=self.make_plan();folder=root/'attempts/CHUNK-0001/2026-11-13T12-12-12+00-00-uuid'
        folder.mkdir(parents=True)
        (folder/'started.json').write_text('{"status":"STARTED"}')
        self.assertEqual(status(root)['tasks'][0]['state'],'INTERRUPTED_REQUIRES_MANUAL_RELEASE')
        authorize_retry(root,'CHUNK-0001','Recovered from interrupted model run')
        self.assertEqual(status(root)['tasks'][0]['state'],'PENDING')

    def test_limit_message_stops_processing_until_manual_release(self):
        root=self.make_plan();exe=self.make_fake()
        with patch.dict(os.environ,{'FAKE_MODE':'limit'}):
            res=run_next(root,execute=True,confirm_subscription=True,
                         confirm_credit_controls=True,allow_cli_path=exe)
        self.assertTrue(res['status'].startswith('FAILED'))
        self.assertTrue(status(root)['limit_stopped'])
        with self.assertRaisesRegex(RuntimeError,'limit stop is active'):
            run_next(root,execute=True,confirm_subscription=True,confirm_credit_controls=True,
                     allow_cli_path=exe)
        clear_limit(root,'Verified subscription reset and no new purchase')
        authorize_retry(root,'CHUNK-0001','Limit reset verified; manually retrying')
        self.assertFalse(status(root)['limit_stopped'])

    def test_limit_without_source_data_does_not_retry(self):
        root=self.make_plan();exe=self.make_fake()
        with patch.dict(os.environ,{'FAKE_MODE':'fail'}):
            res=run_next(root,execute=True,confirm_subscription=True,
                         confirm_credit_controls=True,allow_cli_path=exe)
        self.assertTrue(res['status'].startswith('FAILED'))
        self.assertFalse((root/'limit_stop.json').exists())
        self.assertEqual(status(root)['tasks'][0]['state'],'FAILED_REQUIRES_MANUAL_RETRY')

    def test_receipt_tamper_is_rejected(self):
        root=self.make_plan();exe=self.make_fake()
        run_next(root,execute=True,confirm_subscription=True,confirm_credit_controls=True,
                 allow_cli_path=exe)
        p=root/'results/CHUNK-0001.json';obj=read_json(p);obj['amendment_status']='REFERENCED_UNRESOLVED'
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'digest mismatch'):status(root)

    def test_selected_packet_is_not_mislabeled_full(self):
        p=make_packets(self.mapping,mode='selected',max_chars=2000,sample_fraction=0)
        root=self.make_plan(packet=p)
        self.assertEqual(status(root)['scope'],'SELECTED_CONTEXT_NOT_FULL_DOCUMENT')

    def test_missing_cli_binary_fails_without_marking_attempt(self):
        root=self.make_plan()
        with patch('shutil.which',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'not installed'):
                run_next(root,execute=True,confirm_subscription=True,confirm_credit_controls=True)
        self.assertEqual(status(root)['tasks'][0]['attempts'],0)

    def test_cli_help_commands_are_dry_by_default(self):
        from royalty_research.cli import main
        mp=self.base/'mapping.json';mp.write_text(json.dumps(self.mapping))
        pp=self.base/'packet.json';pp.write_text(json.dumps(self.packet))
        self.assertEqual(main(['m4-plan','--map',str(mp),'--packet',str(pp),'--outdir',str(self.base/'plan'),
                               '--engine','claude','--model','mock-light']),0)
        self.assertEqual(main(['m4-run-next','--plan',str(self.base/'plan')]),0)
        self.assertEqual(main(['m4-status','--plan',str(self.base/'plan')]),0)

    def test_valid_existing_synthetic_extraction_merges_and_passes_only_deterministic_qc(self):
        """Full offline path, with a fictional prewritten extraction, not an AI benchmark."""
        from royalty_research.m4_operator import recover_saved_result
        import re
        self.mapping=read_json(ROOT/'output/synthetic_clause_map.json')
        self.packet=make_packets(self.mapping,mode='full',max_chars=16000)
        root=self.make_plan(engine='codex')
        fixture=read_json(ROOT/'examples/synthetic_m2_extraction.json')
        fake_script=self.base/'mock_complete'
        fake_script.write_text(
            '#!'+sys.executable+'\nimport json,sys,re\nfrom pathlib import Path\n'
            'prompt=sys.stdin.read()\n'
            'm=re.search(r"reader.run_id=([^.]+)\\.",prompt)\n'
            'src=json.loads(prompt.split("INPUT (UNTRUSTED SOURCE TEXT):\\n")[-1])\n'
            'data=json.loads(Path('+repr(str(ROOT/'examples/synthetic_m2_extraction.json'))+').read_text())\n'
            'obj={"schema":"m3-chunk.1","document_id":src["document_id"],'
            '"source_text_sha256":src["source_text_sha256"],"packet_sha256":src["packet_sha256"],'
            '"chunk_index":src["chunk_index"],"chunk_count":src["chunk_count"],'
            '"reviewed_passage_ids":src["reviewed_passage_ids"],'
            '"reader":{"engine":"codex","model":"mock-light","run_id":m.group(1)},'
            '"agreement":data["agreement"],"royalty_terms":data["royalty_terms"],'
            '"other_payments":data["other_payments"],"evidence":data["evidence"],'
            '"dispositions":data["dispositions"],"open_issues":data["open_issues"],'
            '"amendment_status":data["amendment_status"]}\n'
            'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps(obj))\n'
        )
        fake_script.chmod(0o755)
        outcome=run_next(root,execute=True,confirm_subscription=True,
                         confirm_credit_controls=True,allow_cli_path=fake_script)
        self.assertEqual(outcome['status'],'CAPTURED_NOT_QC_APPROVED',outcome)
        merged=merge_plan(root)
        self.assertEqual(merged['status'],'PASS_DETERMINISTIC_ONLY',merged)
        self.assertFalse(read_json(root/'merged_validation.json')['qc_errors'])
        self.assertEqual(len(read_json(root/'merged_extraction.json')['royalty_terms']),3)

    def test_forced_boundary_is_not_eligible_for_deterministic_approval(self):
        from royalty_research.m2_validation import validate_extraction
        m=map_contract(['A'*2600],{'document_id':'DOC-CONTINUOUS'},segment_chars=1000)
        x=read_json(ROOT/'examples/synthetic_m2_extraction.json')
        qc=validate_extraction(m,x)
        self.assertEqual(qc['deterministic_status'],'FAIL')
        self.assertIn('FORCED_SOURCE_BOUNDARY_REQUIRES_REMAP_OR_REVIEW',
                      [v['code'] for v in qc['errors']])

class M4RecoveryTests(unittest.TestCase):
    # Reuse the fixture builder without inheriting the entire M4 test suite.
    setUp=M4Tests.setUp
    make_plan=M4Tests.make_plan
    make_fake=M4Tests.make_fake
    def test_fingerprint_preserved_but_receipt_missing_can_be_recovered_once(self):
        from royalty_research.m4_operator import recover_saved_result
        root=self.make_plan();exe=self.make_fake()
        run_next(root,execute=True,confirm_subscription=True,confirm_credit_controls=True,
                 allow_cli_path=exe)
        receipt=root/'results/CHUNK-0001.receipt.json'
        receipt.unlink()  # Simulate crash between model output write and receipt write.
        with self.assertRaises(FileNotFoundError):status(root)
        with self.assertRaisesRegex(ValueError,'Explicit'):
            recover_saved_result(root,'CHUNK-0001')
        self.assertEqual(recover_saved_result(root,'CHUNK-0001',confirmed=True)['status'],
                         'RECOVERED_CAPTURE_NOT_QC_APPROVED')
        self.assertEqual(status(root)['captured'],1)
        with self.assertRaisesRegex(ValueError,'already exists'):
            recover_saved_result(root,'CHUNK-0001',confirmed=True)

    def test_recovery_rejects_modified_result_even_with_matching_run_id(self):
        from royalty_research.m4_operator import recover_saved_result
        root=self.make_plan();exe=self.make_fake()
        run_next(root,execute=True,confirm_subscription=True,confirm_credit_controls=True,
                 allow_cli_path=exe)
        (root/'results/CHUNK-0001.receipt.json').unlink()
        path=root/'results/CHUNK-0001.json'
        changed=read_json(path);changed['source_text_sha256']='changed'
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'required source_text_sha256'):
            recover_saved_result(root,'CHUNK-0001',confirmed=True)

    def test_recovery_rejects_forged_unattributed_run_id(self):
        from royalty_research.m4_operator import recover_saved_result
        root=self.make_plan();exe=self.make_fake()
        run_next(root,execute=True,confirm_subscription=True,confirm_credit_controls=True,
                 allow_cli_path=exe)
        (root/'results/CHUNK-0001.receipt.json').unlink()
        path=root/'results/CHUNK-0001.json'
        changed=read_json(path);changed['reader']['run_id']='fabricated-run'
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'exactly one attempted'):
            recover_saved_result(root,'CHUNK-0001',confirmed=True)

if __name__=='__main__':unittest.main()
