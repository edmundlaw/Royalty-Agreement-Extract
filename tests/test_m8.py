"""M8 local end-to-end regression tests with fake CLI, never real inference.

Synthetic reference labels are test fixtures, not independent legal ground truth.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from royalty_research.storage import read_json, json_bytes, sha256
from royalty_research.m8_pipeline import (prepare_run,status,prepare_ledger,import_ledger_response,
     finalize, inspect_cross_references, ledger_run_next,ledger_authorize_retry,
     recover_ledger_receipt)
from royalty_research.m8_benchmark import extraction_observations,compare_to_reference,aggregate
from royalty_research.m4_operator import run_next
from royalty_research.m7_occurrences import issue_occurrences
from royalty_research.m6_source_risk import number,_evidence_passages

BASE=Path(__file__).resolve().parent.parent
M=read_json(BASE/'output/synthetic_clause_map.json')
E=read_json(BASE/'examples/synthetic_m2_extraction.json')


def synthetic_dispositions(mapping,extraction):
    """Fictional expected classifications hand-coded from one synthetic fixture.

    Not a general-purpose classification heuristic, and not a benchmark label.
    """
    manifest=issue_occurrences(mapping)
    out=[]
    for occ in manifest['occurrences']:
        pid=occ['passage_id'];kind=occ['kind'];value=number(occ.get('normalized'))
        classification='NON_ROYALTY';term=None;payment=None
        if kind=='PERCENT':
            for t in extraction['royalty_terms']:
                for tier in t.get('tiers',[]):
                    if (value==number(tier.get('rate_value')) and
                        pid in _evidence_passages(extraction,tier.get('evidence_ids',[]))):
                        classification='ROYALTY_RATE';term=t['term_id']
                if (value==number(t.get('rate_value')) and
                    pid in _evidence_passages(extraction,t.get('rate_evidence_ids',[]))):
                    classification='ROYALTY_RATE';term=t['term_id']
        if kind=='MONEY':
            for pay in extraction['other_payments']:
                if (value==number(pay.get('amount_value')) and
                    pid in _evidence_passages(extraction,pay.get('evidence_ids',[]))):
                    classification='OTHER_PAYMENT';payment=pay['payment_id']
        out.append({'occurrence_id':occ['id'],'classification':classification,
                    'term_id':term,'payment_id':payment,
                    'rationale':'Explicit synthetic test-fixture classification only'})
    return {x['occurrence_id']:x for x in out}


class M8PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.run=self.base/'run'
        self.m=copy.deepcopy(M)
        self.primary_fake=None

    def prepare(self,max_chars=64000,ledger_max_chars=14000):
        return prepare_run(self.m,self.run,engine='codex',model='mock-light',
                   max_chars=max_chars,ledger_max_chars=ledger_max_chars)

    def primary(self):
        self.prepare()
        script=self.base/'fake_primary'
        text=(f'#!{sys.executable}\n'
            'import json,sys,re\nfrom pathlib import Path\n'
            'prompt=sys.stdin.read()\n'
            'header=re.search(r"reader.run_id=([^.]+)\\.",prompt)\n'
            'assert header\n'
            'src=json.loads(prompt.split("INPUT (UNTRUSTED SOURCE TEXT):\\n")[-1])\n'
            f'data=json.loads(Path({str(BASE/"examples"/"synthetic_m2_extraction.json")!r}).read_text())\n'
            'obj={"schema":"m3-chunk.1","document_id":src["document_id"],'
            '"source_text_sha256":src["source_text_sha256"],"packet_sha256":src["packet_sha256"],'
            '"chunk_index":src["chunk_index"],"chunk_count":src["chunk_count"],'
            '"reviewed_passage_ids":src["reviewed_passage_ids"],'
            '"reader":{"engine":"codex","model":"mock-light","run_id":header.group(1)},'
            '"agreement":data["agreement"],"royalty_terms":data["royalty_terms"],'
            '"other_payments":data["other_payments"],"evidence":data["evidence"],'
            '"dispositions":data["dispositions"],"open_issues":data["open_issues"],'
            '"amendment_status":data["amendment_status"]}\n'
            'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps(obj))\n')
        script.write_text(text);script.chmod(0o755)
        r=run_next(self.run/'primary_plan',execute=True,confirm_subscription=True,
                   confirm_credit_controls=True,allow_cli_path=script)
        self.assertEqual(r['status'],'CAPTURED_NOT_QC_APPROVED')
        self.assertEqual(status(self.run)['primary']['captured'],1)

    def ledger(self,invalid=False):
        prepare_ledger(self.run)
        manifest=issue_occurrences(self.m)
        resolved=synthetic_dispositions(self.m,E)
        n=read_json(self.run/'ledger'/'manifest.json')['task_count']
        for i in range(1,n+1):
            task=read_json(self.run/'ledger'/'tasks'/f'ledger_{i:04d}.json')
            items=[resolved[v['occurrence_id']].copy() for v in task['items']]
            if invalid:
                for item in items:
                    item['classification']='NON_ROYALTY';item['term_id']=None
                    item['payment_id']=None
            response={'schema':'m7-occurrence-response.1','document_id':task['document_id'],
                'source_text_sha256':task['source_text_sha256'],
                'occurrence_manifest_sha256':task['occurrence_manifest_sha256'],
                'extraction_sha256':task['extraction_sha256'],
                'chunk_index':task['chunk_index'],'chunk_count':task['chunk_count'],
                'task_sha256':task['task_sha256'],
                'occurrence_dispositions':items}
            import_ledger_response(self.run,response)
        self.assertEqual(status(self.run)['ledger']['captured'],n)

    def test_prepare_is_full_source_not_focus_only(self):
        report=self.prepare()
        self.assertEqual(report['tasks'],1)
        src=read_json(self.run/'source'/'full_packet.json')
        self.assertEqual(src['mode'],'full')
        self.assertEqual(src['included_passage_ids'],[p['passage_id'] for p in M['passages']])
        self.assertEqual(status(self.run)['primary']['captured'],0)
        self.assertEqual(status(self.run)['ledger']['prepared'],False)
        with self.assertRaises(FileExistsError):self.prepare()

    def test_tampered_packets_rejected_before_model_calls(self):
        self.prepare()
        focus=self.run/'source'/'focus_packet.json'
        data=read_json(focus);data['chunks'][0]['passages'][0]['text']='tampered'
        focus.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'content was altered'):status(self.run)

    def test_ledger_cannot_begin_before_full_primary_captured(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError,'incomplete'):prepare_ledger(self.run)

    def test_m8_primary_dry_run_without_model(self):
        self.prepare()
        self.assertEqual(run_next(self.run/'primary_plan')['status'],'DRY_RUN_NO_AI_CALLED')
        self.assertEqual(status(self.run)['primary']['captured'],0)

    def test_complete_synthetic_end_to_end_export_without_signoff(self):
        self.primary();self.ledger()
        result=finalize(self.run)
        self.assertEqual(result['qc_status'],'PASS_DETERMINISTIC_ONLY')
        self.assertTrue(Path(result['spreadsheet']).is_file())
        self.assertEqual(status(self.run)['final']['qc_status'],'PASS_DETERMINISTIC_ONLY')
        manifest=read_json(self.run/'output'/'output_manifest.json')
        for name,digest in manifest['output_files_sha256'].items():
            self.assertEqual(sha256((self.run/'output'/name).read_bytes()),digest)
        self.assertFalse((self.run/'output'/'Human Reviewed.csv').exists())
        with self.assertRaises(FileExistsError):finalize(self.run)

    def test_misclassified_rates_still_export_but_qc_fails(self):
        self.primary();self.ledger(invalid=True)
        result=finalize(self.run,export_xlsx=False)
        self.assertEqual(result['qc_status'],'FAIL')
        self.assertGreater(result['errors'],0)
        self.assertTrue((self.run/'output'/'csv'/'qc.csv').exists())

    def test_response_replay_and_tampering_rejected(self):
        self.primary();self.ledger()
        p=self.run/'ledger'/'responses'/'ledger_0001.json'
        original=read_json(p)
        self.assertEqual(import_ledger_response(self.run,original)['status'],'EXISTING_IDENTICAL_RESPONSE')
        original['occurrence_dispositions'][0]['classification']='UNRESOLVED'
        with self.assertRaisesRegex(ValueError,'different bytes'):import_ledger_response(self.run,original)
        p.write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError,'Stale or changed'):status(self.run)

    def test_missing_response_blocks_finalize(self):
        self.primary();prepare_ledger(self.run)
        self.assertEqual(status(self.run)['ledger']['captured'],0)
        with self.assertRaisesRegex(ValueError,'Not all occurrence'):finalize(self.run)

    def test_missing_receipt_is_recoverable_without_model_call(self):
        self.primary();self.ledger()
        receipt=self.run/'ledger'/'responses'/'ledger_0001.receipt.json'
        receipt.unlink()
        with self.assertRaisesRegex(ValueError,'Incomplete ledger response receipt'):status(self.run)
        restored=recover_ledger_receipt(self.run,1)
        self.assertEqual(restored['status'],'RECEIPT_RECOVERED_NO_MODEL_CALLED')
        self.assertGreater(status(self.run)['ledger']['captured'],0)

    def test_ledger_runner_dry_by_default_and_requires_subscription_flags(self):
        self.primary();prepare_ledger(self.run)
        self.assertEqual(ledger_run_next(self.run)['status'],'DRY_RUN_NO_MODEL_CALLED')
        with self.assertRaisesRegex(ValueError,'Explicit'):
            ledger_run_next(self.run,execute=True,confirm_subscription=True)
        self.assertEqual(status(self.run)['ledger']['captured'],0)

    def test_ledger_runner_blocks_api_key_before_attempt(self):
        self.primary();prepare_ledger(self.run)
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'WRONG_ROUTE'}):
            with self.assertRaisesRegex(RuntimeError,'NO CLI call'):
                ledger_run_next(self.run,execute=True,confirm_subscription=True,confirm_credit_controls=True)
        self.assertFalse((self.run/'ledger'/'attempts').exists())

    def test_explicit_retry_release_not_contract_approval(self):
        self.primary();prepare_ledger(self.run)
        fake=self.base/'bad-cli';fake.write_text('#!'+sys.executable+'\nimport sys\nprint("oops",file=sys.stderr)\nsys.exit(1)\n');fake.chmod(0o755)
        err=ledger_run_next(self.run,execute=True,confirm_subscription=True,
                            confirm_credit_controls=True,allow_cli_path=fake)
        self.assertEqual(err['status'],'FAILED_NO_AUTORETRY')
        with self.assertRaisesRegex(RuntimeError,'explicitly authorize retry'):
            ledger_run_next(self.run,execute=True,confirm_subscription=True,
                            confirm_credit_controls=True,allow_cli_path=fake)
        self.assertEqual(ledger_authorize_retry(self.run,1,'Simulated failed local CLI test')['status'],
                         'RETRY_RELEASED_NO_MODEL_CALLED')

    def test_reference_resolution_does_not_claim_semantics(self):
        report=inspect_cross_references(M)
        self.assertEqual(report['total_refs'],len(report['references']))
        self.assertTrue(all('status' in e for e in report['references']))


class M8BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.e=copy.deepcopy(E)
        self.ref={'schema':'m8-gold.1','document_id':E['document_id'],
            'source_text_sha256':E['source_text_sha256'],
            'reference_provenance':'Fictional benchmark fixture, never independent real contract truth',
            'complete_source_checked':True,'independently_verified':False,
            'observations':extraction_observations(E)}

    def test_identical_structures_are_exact_proxy_matches_not_claims(self):
        r=compare_to_reference(self.ref,self.e)
        self.assertTrue(r['complete_record']);self.assertEqual(r['missed_count'],0)
        overall=aggregate([r]);self.assertFalse(overall['measured_accuracy_claim_permitted'])
        self.assertFalse(overall['all_reference_provenance_verified'])

    def test_dropped_tier_and_wrong_base_detected(self):
        e=copy.deepcopy(self.e)
        e['royalty_terms'][0]['tiers'].pop()
        e['royalty_terms'][1]['base']='Gross Sales, not Net Sales'
        r=compare_to_reference(self.ref,e)
        self.assertGreater(r['missed_count'],0)
        self.assertGreater(r['extra_count'],0)
        self.assertFalse(r['complete_record'])

    def test_reference_source_mismatch_is_fatal(self):
        self.ref['source_text_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source mismatch'):
            compare_to_reference(self.ref,self.e)

    def test_duplicate_results_dont_create_false_population(self):
        r=compare_to_reference(self.ref,self.e)
        with self.assertRaisesRegex(ValueError,'Duplicate benchmark'):
            aggregate([r,r])

    def test_numeric_reference_formatting_is_normalized(self):
        self.ref['observations'][0]['rate_value']=float(self.ref['observations'][0]['rate_value'])
        self.ref['observations'][0]['base']=self.ref['observations'][0]['base'].upper()
        self.assertEqual(compare_to_reference(self.ref,self.e)['missed_count'],0)

    def test_reference_provenance_required(self):
        self.ref.pop('reference_provenance')
        with self.assertRaisesRegex(ValueError,'provenance'):
            compare_to_reference(self.ref,self.e)

class M8AdditionalHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.root=self.base/'doc'

    def test_long_contract_is_split_but_every_passage_supplied(self):
        from royalty_research.mapping import map_contract
        words=['The annual licence royalty is based on revenues as provided by Schedule B.']
        words.extend(f'{i}.0 The company agreed to account for sales of licensed devices.' for i in range(2,180))
        m=map_contract(words,{'document_id':'M8-LONG-SYNTHETIC'},segment_chars=12000)
        prepare_run(m,self.root,engine='claude',model='mock-light',max_chars=4000)
        report=status(self.root)
        self.assertGreater(report['primary']['total'],1)
        self.assertEqual(report['source_passages'],report['full_document_passages_assigned'])
        with self.assertRaisesRegex(ValueError,'incomplete'):prepare_ledger(self.root)

    def test_run_model_settings_fingerprinted(self):
        prepare_run(M,self.root,engine='codex',model='mock-light')
        path=self.root/'m8_run.json'
        obj=read_json(path)
        obj['ledger_model']='premium-model-injected'
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'immutable run settings'):status(self.root)

    def test_ledger_prompt_tamper_is_rejected(self):
        obj=M8PipelineTests('test_prepare_is_full_source_not_focus_only')
        obj.tmp=tempfile.TemporaryDirectory();self.addCleanup(obj.tmp.cleanup)
        obj.base=Path(obj.tmp.name);obj.run=obj.base/'run';obj.m=copy.deepcopy(M)
        obj.primary();prepare_ledger(obj.run)
        p=obj.run/'ledger'/'tasks'/'ledger_0001.prompt.txt'
        p.write_text(p.read_text()+'\nINJECTED')
        with self.assertRaisesRegex(ValueError,'ledger prompt modified'):status(obj.run)

    def test_cross_chunk_source_fragment_gets_automatic_issue(self):
        from royalty_research.mapping import map_contract
        from royalty_research.m2_packets import make_packets
        from royalty_research.m8_pipeline import _append_context_risk_issues
        long='The license fee is 3 percent of annual Net Sales under section 4.2. '+('contract context ' * 120)
        m=map_contract([long,'4.2 Section contains defined terms.'],
            {'document_id':'M8-BROKEN-PARA'},segment_chars=1000)
        packet=make_packets(m,mode='full',max_chars=2000)
        self.assertGreater(len(packet['chunks']),1)
        result=_append_context_risk_issues(m,packet,{'open_issues':[]})
        self.assertIn('M8_ORIGINAL_PARAGRAPH_SPLIT_ACROSS_AI_TASKS',
                     {x['kind'] for x in result['open_issues']})

    def test_zero_occurrences_need_no_second_model_and_still_export(self):
        """Negative-contract edge case: full-source primary read still required."""
        from royalty_research.mapping import map_contract
        from royalty_research.m4_operator import run_next
        m=map_contract(['Ordinary office instructions and internal staffing description.'],
            {'document_id':'M8-EMPTY-NEGATIVE'})
        self.assertEqual(issue_occurrences(m)['occurrences'],[])
        prepare_run(m,self.root,engine='codex',model='mock-light')
        script=self.base/'fake_empty'
        script.write_text('#!'+sys.executable+'\n'
            'import json,sys,re\nfrom pathlib import Path\n'
            'p=sys.stdin.read();r=re.search(r"reader.run_id=([^.]+)\\.",p)\n'
            'd=json.loads(p.split("INPUT (UNTRUSTED SOURCE TEXT):\\n")[-1])\n'
            'a={"schema":"m3-chunk.1","document_id":d["document_id"],'
            '"source_text_sha256":d["source_text_sha256"],"packet_sha256":d["packet_sha256"],'
            '"chunk_index":d["chunk_index"],"chunk_count":d["chunk_count"],'
            '"reviewed_passage_ids":d["reviewed_passage_ids"],'
            '"reader":{"engine":"codex","model":"mock-light","run_id":r.group(1)},'
            '"agreement":{},"royalty_terms":[],"other_payments":[],"evidence":[],"dispositions":[],"open_issues":[],"amendment_status":"NONE_IDENTIFIED_IN_DOCUMENT"}\n'
            'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps(a))\n')
        script.chmod(0o755)
        r=run_next(self.root/'primary_plan',execute=True,confirm_subscription=True,
                   confirm_credit_controls=True,allow_cli_path=script)
        self.assertEqual(r['status'],'CAPTURED_NOT_QC_APPROVED')
        led=prepare_ledger(self.root)
        self.assertEqual(led['status'],'LEDGER_NOT_NEEDED_ZERO_SOURCE_OCCURRENCES')
        self.assertEqual(status(self.root)['ledger']['total'],0)
        done=finalize(self.root,export_xlsx=False)
        self.assertEqual(done['status'],'EXPORTED_WITH_AUTOMATED_QC_STATUS')
        self.assertTrue((self.root/'output'/'csv'/'documents.csv').exists())

    def test_benchmark_does_not_mix_duplicate_golds(self):
        e=copy.deepcopy(E)
        reference={'schema':'m8-gold.1','document_id':e['document_id'],
            'source_text_sha256':e['source_text_sha256'],
            'reference_provenance':'Not verified, synthetic test case',
            'complete_source_checked':False,'independently_verified':False,
            'observations':extraction_observations(e)}
        # Two duplicate economics are matched only when reference contains two.
        reference['observations'].append(copy.deepcopy(reference['observations'][0]))
        r=compare_to_reference(reference,e)
        self.assertEqual(r['missed_count'],1)
        self.assertFalse(r['complete_record'])

class M8LedgerMockCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.helper=M8PipelineTests('test_prepare_is_full_source_not_focus_only')
        self.helper.tmp=self.tmp
        self.helper.base=self.base
        self.helper.run=self.base/'run'
        self.helper.m=copy.deepcopy(M)
        self.helper.primary();prepare_ledger(self.helper.run)

    def mock_ledger(self,*,mode='ok'):
        file=self.base/'fake_ledger'
        code=('#!'+sys.executable+'\n'
            'import json,sys\nfrom pathlib import Path\n'
            'p=sys.stdin.read()\n'
            'data=json.loads(p.split("ISSUED TASK:\\n")[-1])\n'
            'out={"schema":"m7-occurrence-response.1",'
            '"document_id":data["document_id"],'
            '"source_text_sha256":data["source_text_sha256"],'
            '"extraction_sha256":data["extraction_sha256"],'
            '"occurrence_manifest_sha256":data["occurrence_manifest_sha256"],'
            '"chunk_index":data["chunk_index"],"chunk_count":data["chunk_count"],'
            '"task_sha256":data["task_sha256"],'
            '"occurrence_dispositions":[{"occurrence_id":x["occurrence_id"],'
            '"classification":"UNRESOLVED","term_id":None,"payment_id":None,'
            '"rationale":"Context deliberately unresolved for synthetic CLI integration test"}'
            ' for x in data["items"]]}\n')
        if mode=='limit':
            code+='print("usage limit reached; resets in 4 hours",file=sys.stderr)\nsys.exit(1)\n'
        else:
            code+='Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps(out))\n'
        file.write_text(code);file.chmod(0o755)
        return file

    def test_cli_capture_is_unverified_and_creates_machine_open_issues(self):
        exe=self.mock_ledger()
        out=ledger_run_next(self.helper.run,execute=True,confirm_subscription=True,
                            confirm_credit_controls=True,allow_cli_path=exe)
        self.assertEqual(out['status'],'CAPTURED_UNVERIFIED_NOT_HUMAN_APPROVED')
        self.assertEqual(status(self.helper.run)['ledger']['captured'],1)
        result=finalize(self.helper.run,export_xlsx=False)
        self.assertGreater(result['open_issues'],0)
        self.assertTrue((self.helper.run/'output'/'csv'/'open_issues.csv').is_file())
        with self.assertRaisesRegex(FileExistsError,'already exists'):
            # No duplicate finalization of already exported records.
            finalize(self.helper.run,export_xlsx=False)

    def test_ledger_limit_stop_is_fail_closed(self):
        exe=self.mock_ledger(mode='limit')
        out=ledger_run_next(self.helper.run,execute=True,confirm_subscription=True,
                            confirm_credit_controls=True,allow_cli_path=exe)
        self.assertEqual(out['status'],'FAILED_NO_AUTORETRY')
        self.assertTrue((self.helper.run/'ledger'/'limit_stop.json').is_file())
        with self.assertRaisesRegex(RuntimeError,'stop active'):
            ledger_run_next(self.helper.run,execute=True,confirm_subscription=True,
                            confirm_credit_controls=True,allow_cli_path=exe)
