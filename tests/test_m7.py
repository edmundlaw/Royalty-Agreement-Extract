"""M7 source-issued IDs, triage, omission attacks and approval-free export.

These are deterministic adversarial tests, NOT measured contract recall.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal

from royalty_research.storage import read_json,json_bytes,sha256
from royalty_research.m7_occurrences import issue_occurrences, verify_issued_manifest, check_m7_occurrences
from royalty_research.m7_triage import compact_packet,triage_document
from royalty_research.m7_ledger_tasks import prepare_ledger_tasks,merge_ledger_chunks,attach_ledger
from royalty_research.m6_source_risk import number,_evidence_passages
from royalty_research.m2_validation import validate_extraction
from royalty_research.m3_workspace import init,register_map,register_extraction,list_documents
from royalty_research.m3_export import build_rows

BASE=Path(__file__).resolve().parent.parent
M=read_json(BASE/'output/synthetic_clause_map.json')
E=read_json(BASE/'examples/synthetic_m2_extraction.json')
MARKET=read_json(BASE/'tests/fixtures/m6/market_finders_mapped.json')


def ready_map(mapping):
    mapping=copy.deepcopy(mapping)
    mapping['quality_control_profile']='M7_ISSUED_OCCURRENCES'
    mapping['occurrence_manifest_sha256']=issue_occurrences(mapping)['manifest_sha256']
    return mapping


def valid_test_extraction(mapping,extraction):
    """Synthetic fixture helper, not a production classification algorithm."""
    x=copy.deepcopy(extraction)
    h=issue_occurrences(mapping)
    eids={v.get('evidence_id'):v.get('passage_id') for v in x['evidence']}
    ledger=[]
    for occ in h['occurrences']:
        pid=occ['passage_id'];kind=occ['kind'];value=number(occ['normalized'])
        classification='NON_ROYALTY';term=None;payment=None
        if kind=='PERCENT':
            for t in x['royalty_terms']:
                for tier in t.get('tiers',[]):
                    if value==number(tier.get('rate_value')) and pid in _evidence_passages(x,tier.get('evidence_ids',[])):
                        classification='ROYALTY_RATE';term=t['term_id']
                if value==number(t.get('rate_value')) and pid in _evidence_passages(x,t.get('rate_evidence_ids',[])):
                    classification='ROYALTY_RATE';term=t['term_id']
        if kind=='MONEY':
            for pay in x['other_payments']:
                if value==number(pay.get('amount_value')) and pid in _evidence_passages(x,pay.get('evidence_ids',[])):
                    classification='OTHER_PAYMENT';payment=pay['payment_id']
        ledger.append({'occurrence_id':occ['id'],'classification':classification,
                       'term_id':term,'payment_id':payment,
                       'rationale':'Source-ledger unit fixture classification, not a legal conclusion'})
    x['occurrence_manifest_sha256']=h['manifest_sha256'];x['occurrence_dispositions']=ledger
    return x


class M7OccurrenceTests(unittest.TestCase):
    def setUp(self):
        self.m=ready_map(M);self.x=valid_test_extraction(self.m,E)
    def test_issued_manifest_is_exact_and_stable(self):
        a=issue_occurrences(self.m);b=issue_occurrences(copy.deepcopy(self.m))
        self.assertEqual(a,b)
        self.assertTrue(verify_issued_manifest(self.m,a))
        self.assertEqual(len({z['id'] for z in a['occurrences']}),len(a['occurrences']))
        self.assertEqual(a['source_text_sha256'],self.m['text_sha256'])
    def test_tampered_manifest_detected(self):
        a=issue_occurrences(self.m);a['occurrences'][0]['literal']='FAKE'
        with self.assertRaisesRegex(ValueError,'MANIFEST_MISMATCH'):
            verify_issued_manifest(self.m,a)
    def test_correct_synthetic_fixture_reconciles(self):
        self.assertEqual(check_m7_occurrences(self.m,self.x)['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
        self.assertEqual(validate_extraction(self.m,self.x)['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
    def test_missing_occurrence_fails(self):
        self.x['occurrence_dispositions'].pop(1)
        codes={v['code'] for v in check_m7_occurrences(self.m,self.x)['errors']}
        self.assertIn('M7_OCCURRENCE_COVERAGE_INCOMPLETE',codes)
    def test_wrong_issuer_id_fails(self):
        self.x['occurrence_dispositions'][0]['occurrence_id']='OCC-fake'
        codes={v['code'] for v in check_m7_occurrences(self.m,self.x)['errors']}
        self.assertIn('M7_UNISSUED_OCCURRENCE_ID',codes)
    def test_repeat_duplicate_fails(self):
        self.x['occurrence_dispositions'].append(copy.deepcopy(self.x['occurrence_dispositions'][0]))
        codes={v['code'] for v in check_m7_occurrences(self.m,self.x)['errors']}
        self.assertIn('M7_DUPLICATE_OCCURRENCE',codes)
    def test_dismiss_6pct_as_unrelated_fails_even_when_model_changes_ledger(self):
        first=self.x['occurrence_dispositions'][0]
        self.assertEqual(first['classification'],'ROYALTY_RATE')
        first.update(classification='NON_ROYALTY',term_id=None)
        codes={v['code'] for v in check_m7_occurrences(self.m,self.x)['errors']}
        self.assertTrue({'M7_HIGH_RISK_DISMISSAL','M7_RATE_RISK_CLASSIFICATION'}&codes,codes)
    def test_royalty_rate_pointing_to_wrong_term_fails(self):
        self.x['occurrence_dispositions'][0]['term_id']='RT-SUB'
        codes={v['code'] for v in check_m7_occurrences(self.m,self.x)['errors']}
        self.assertIn('M7_WRONG_TERM_RATE',codes)
    def test_manifest_hash_from_other_map_fails(self):
        self.x['occurrence_manifest_sha256']='0'*64
        codes={v['code'] for v in validate_extraction(self.m,self.x)['errors']}
        self.assertIn('M7_MANIFEST_BINDING_MISMATCH',codes)
    def test_legacy_extraction_cannot_pass_strict_map(self):
        codes={v['code'] for v in validate_extraction(self.m,E)['errors']}
        self.assertIn('M7_OCCURRENCE_LEDGER_MISSING',codes)
    def test_new_workspace_does_not_require_human_signoff(self):
        with tempfile.TemporaryDirectory() as td:
            init(td);register_map(td,self.m);register_extraction(td,self.m['document_id'],self.x,select=True)
            doc=list_documents(td)[0]
            self.assertIn(doc['state'],('QC_PASSED_NOT_PROFESSIONALLY_VERIFIED','QC_PASSED_OPEN_HIGH_ISSUE'))
            rows=build_rows(td)
            self.assertNotIn('Human Reviewed',rows)
            self.assertNotIn('Human_Review_Status',rows['Documents'][0])
            self.assertEqual(len(rows['Royalty Terms']),4)


class M7TriageTests(unittest.TestCase):
    def test_focus_and_remainder_cover_every_source_passage(self):
        for mapping in (M,MARKET):
            focus=compact_packet(mapping,stage='focus',max_chars=18000)
            rest=compact_packet(mapping,stage='remainder',max_chars=18000)
            f=set(focus['included_passage_ids']);r=set(rest['included_passage_ids'])
            all_ids={p['passage_id'] for p in mapping['passages']}
            self.assertEqual(f&r,set())
            self.assertEqual(f|r,all_ids)
            self.assertEqual(focus['manifest_sha256'],rest['manifest_sha256'])
            self.assertEqual(focus['read_scope'],'FOCUSED_ONLY_NOT_COMPLETE')
    def test_no_relevance_autorejection(self):
        a=triage_document(M)
        self.assertTrue(a['priority'])
        self.assertIn('no automatic exclusion',a['notice'])
    def test_long_passage_raises_without_truncation(self):
        from royalty_research.mapping import map_contract
        longmap=map_contract(['The royalty payable is 5% of Net Sales. '+'x'*2800],
            {'document_id':'LONG-M7','source_url':'https://www.sec.gov/Archives/edgar/data/1/2/test.htm'},segment_chars=5000)
        with self.assertRaisesRegex(ValueError,'Oversized'):
            compact_packet(longmap,stage='full',max_chars=2000)
    def test_market_real_map_has_source_occurrence_inventory(self):
        h=issue_occurrences(MARKET)
        lits=[x['literal'] for x in h['occurrences'] if x['kind']=='PERCENT']
        for x in ['6%','4%','2%','1%']:
            self.assertIn(x,lits)


class M7LedgerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.m=ready_map(M);self.x=copy.deepcopy(E)
        self.finished=valid_test_extraction(self.m,E)
    def _responses(self,tasks):
        d={z['occurrence_id']:z for z in self.finished['occurrence_dispositions']}
        return [{'schema':'m7-occurrence-response.1','document_id':self.m['document_id'],
                'source_text_sha256':self.m['text_sha256'],
                'occurrence_manifest_sha256':tasks[i]['occurrence_manifest_sha256'],
                'extraction_sha256':tasks[i]['extraction_sha256'],
                'chunk_index':tasks[i]['chunk_index'],'chunk_count':len(tasks),
                'task_sha256':tasks[i]['task_sha256'],
                'occurrence_dispositions':[d[z['occurrence_id']] for z in tasks[i]['items']]}
                for i in range(len(tasks))]
    def test_task_merging_and_attachment_passes_strict_qc(self):
        tasks=prepare_ledger_tasks(self.m,self.x,max_chars=3500)
        self.assertGreater(len(tasks),1)
        outputs=self._responses(tasks)
        merged=merge_ledger_chunks(self.m,self.x,outputs,tasks=tasks)
        attached=attach_ledger(self.m,self.x,merged)
        issued=issue_occurrences(self.m)
        self.assertEqual({x['occurrence_id'] for x in attached['occurrence_dispositions']},
                         {x['id'] for x in issued['occurrences']})
        # M10 preserves redaction-marker identities deterministically, rather
        # than asking Sonnet to classify each masking symbol individually.
        actual={x['occurrence_id']:x for x in attached['occurrence_dispositions']}
        original={x['occurrence_id']:x for x in self.finished['occurrence_dispositions']}
        for hit in issued['occurrences']:
            if hit['kind']=='REDACTION':
                self.assertEqual(actual[hit['id']]['classification'],'REDACTION')
            else:
                self.assertEqual(actual[hit['id']],original[hit['id']])
        self.assertEqual(validate_extraction(self.m,attached)['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
    def test_source_task_tampering_fails(self):
        tasks=prepare_ledger_tasks(self.m,self.x,max_chars=3500)
        responses=self._responses(tasks)
        tasks[0]['items'][0]['literal']='FALSE'
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            merge_ledger_chunks(self.m,self.x,responses,tasks=tasks)
    def test_missing_response_fails(self):
        tasks=prepare_ledger_tasks(self.m,self.x,max_chars=3500)
        responses=self._responses(tasks)
        with self.assertRaises(ValueError):
            merge_ledger_chunks(self.m,self.x,responses[:-1],tasks=tasks)
    def test_model_invents_id_fails(self):
        tasks=prepare_ledger_tasks(self.m,self.x,max_chars=3500)
        responses=self._responses(tasks)
        responses[0]['occurrence_dispositions'][0]['occurrence_id']='OCC-unknown'
        with self.assertRaisesRegex(ValueError,'exact source-issued'):
            merge_ledger_chunks(self.m,self.x,responses,tasks=tasks)
    def test_original_extraction_changes_no_ledger_reuse(self):
        tasks=prepare_ledger_tasks(self.m,self.x,max_chars=3500)
        responses=self._responses(tasks)
        merged=merge_ledger_chunks(self.m,self.x,responses,tasks=tasks)
        changed=copy.deepcopy(self.x);changed['reader']['run_id']='changed-run'
        with self.assertRaisesRegex(ValueError,'LEDGER_EXTRACTION_CHANGED'):
            attach_ledger(self.m,changed,merged)
    def test_merger_rejects_duplicate_task(self):
        tasks=prepare_ledger_tasks(self.m,self.x,max_chars=3500)
        with self.assertRaisesRegex(ValueError,'issued tasks'):
            merge_ledger_chunks(self.m,self.x,self._responses(tasks),tasks=tasks+[tasks[0]])

if __name__=='__main__': unittest.main()

class M7CLITests(unittest.TestCase):
    def test_prepare_ledger_attach_validate_from_cli(self):
        from royalty_research.cli import main
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'input.json';source.write_text(json.dumps(M))
            prepared=root/'prepared'
            self.assertEqual(main(['m7-prepare','--map',str(source),'--outdir',str(prepared)]),0)
            m=read_json(prepared/'m7_map.json')
            self.assertEqual(m['quality_control_profile'],'M7_ISSUED_OCCURRENCES')
            self.assertFalse(set(read_json(prepared/'focus_packet.json')['included_passage_ids']) &
                             set(read_json(prepared/'remainder_packet.json')['included_passage_ids']))
            raw=root/'raw.json';raw.write_text(json.dumps(E))
            tasks=root/'tasks'
            self.assertEqual(main(['m7-ledger-tasks','--map',str(prepared/'m7_map.json'),
                '--extraction',str(raw),'--outdir',str(tasks),'--max-chars','3500']),0)
            tk=[read_json(q) for q in sorted(tasks.glob('ledger_task_*.json'))]
            fake=M7LedgerWorkflowTests()
            fake.m=m;fake.x=copy.deepcopy(E);fake.finished=valid_test_extraction(m,E)
            responses=fake._responses(tk)
            response_files=[]
            for ix,res in enumerate(responses):
                f=root/f'answer_{ix:04d}.json';f.write_text(json.dumps(res));response_files.append(f)
            merged=root/'merged_ledger.json'
            argv=['m7-merge-ledger','--map',str(prepared/'m7_map.json'),'--extraction',str(raw)]
            for f in response_files:argv.extend(['--response',str(f)])
            for f in sorted(tasks.glob('ledger_task_*.json')):argv.extend(['--task',str(f)])
            argv.extend(['--out',str(merged)])
            self.assertEqual(main(argv),0)
            joined=root/'enriched.json'
            self.assertEqual(main(['m7-attach-ledger','--map',str(prepared/'m7_map.json'),
                '--extraction',str(raw),'--ledger',str(merged),'--out',str(joined)]),0)
            report=root/'report.json'
            self.assertEqual(main(['m7-validate','--map',str(prepared/'m7_map.json'),
                '--extraction',str(joined),'--out',str(report)]),0)
            self.assertEqual(read_json(report)['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
            self.assertNotIn('m3-human-review',__import__('royalty_research.cli',fromlist=['build_parser']).build_parser()._subparsers._group_actions[0].choices)


class M7WrittenAndIndirectRiskTests(unittest.TestCase):
    """A numeric-only ledger must not silently bless clearly expressed written obligations."""
    def _map_and_empty_ledger(self, text):
        from royalty_research.mapping import map_contract
        mapping=map_contract([text],{'document_id':'M7-WRITTEN-CASE',
            'source_url':'https://www.sec.gov/Archives/edgar/data/1/2/written.htm'})
        manifest=issue_occurrences(mapping)
        extraction={'document_id':mapping['document_id'],'source_text_sha256':mapping['text_sha256'],
            'occurrence_manifest_sha256':manifest['manifest_sha256'],
            'royalty_terms':[],'other_payments':[],'evidence':[],'open_issues':[],
            'occurrence_dispositions':[{'occurrence_id':occ['id'], 'classification':'NON_ROYALTY',
                'rationale':'The model marked this as unrelated without enough support.'}
                for occ in manifest['occurrences']]}
        return mapping, extraction, manifest
    def test_written_five_percent_cannot_be_discarded_without_issue(self):
        mapping,extraction,manifest=self._map_and_empty_ledger(
            'Licensee shall pay a royalty of five percent of Net Sales each quarter.')
        hits=[x for x in manifest['occurrences'] if x['kind']=='SPELLED_RATE']
        self.assertTrue(hits)
        self.assertTrue(all(h['risk']=='POTENTIAL_SPELLED_RATE' for h in hits))
        failures={x['code'] for x in check_m7_occurrences(mapping,extraction)['errors']}
        self.assertIn('M7_HIGH_RISK_DISMISSAL',failures)
        self.assertIn('M7_RATE_RISK_CLASSIFICATION',failures)
    def test_indirect_payment_schedule_cannot_be_dismissed_without_issue(self):
        mapping,extraction,manifest=self._map_and_empty_ledger(
            'Licensee shall pay licensing consideration as specified in Schedule B.')
        hits=[x for x in manifest['occurrences'] if x['kind']=='INDIRECT_ECONOMICS']
        self.assertTrue(hits)
        self.assertTrue(all(h['risk']=='POTENTIAL_INDIRECT_PAYMENT' for h in hits))
        failures={x['code'] for x in check_m7_occurrences(mapping,extraction)['errors']}
        self.assertIn('M7_INDIRECT_PAYMENT_UNACCOUNTED',failures)
    def test_written_rate_must_cite_own_source_passage(self):
        mapping,extraction,manifest=self._map_and_empty_ledger(
            'Licensee shall pay a royalty of five percent of Net Sales each quarter.')
        occ=next(x for x in manifest['occurrences'] if x['kind']=='SPELLED_RATE')
        extraction['royalty_terms']=[{'term_id':'RT-FAKE','rate_value':'5','tiers':[],
                                    'evidence_ids':[], 'rate_evidence_ids':[]}]
        for d in extraction['occurrence_dispositions']:
            if d['occurrence_id']==occ['id']:
                d.update(classification='ROYALTY_RATE',term_id='RT-FAKE')
        failures={x['code'] for x in check_m7_occurrences(mapping,extraction)['errors']}
        self.assertIn('M7_RATE_TERM_SOURCE_MISMATCH',failures)

class M7MachineIssueTests(unittest.TestCase):
    def test_unresolved_source_occurrence_auto_records_machine_issue(self):
        mapping=ready_map(M)
        extraction=copy.deepcopy(E)
        tasks=prepare_ledger_tasks(mapping,extraction,max_chars=3500)
        bridge=M7LedgerWorkflowTests()
        bridge.m=mapping;bridge.x=extraction;bridge.finished=valid_test_extraction(mapping,E)
        responses=bridge._responses(tasks)
        unresolved=responses[0]['occurrence_dispositions'][0]
        unresolved.update(classification='UNRESOLVED', term_id=None, payment_id=None,
                          rationale='Context is insufficient to confirm legal economics')
        ledger=merge_ledger_chunks(mapping,extraction,responses,tasks=tasks)
        attached=attach_ledger(mapping,extraction,ledger)
        source=issue_occurrences(mapping)['occurrences'][0]
        flagged=[i for i in attached['open_issues'] if i['kind']=='M7_AUTOMATED_OCCURRENCE_UNRESOLVED']
        self.assertEqual(len(flagged),1)
        self.assertEqual(flagged[0]['passage_ids'],[source['passage_id']])
        self.assertEqual(flagged[0]['status'],'OPEN')
        self.assertEqual(check_m7_occurrences(mapping,attached)['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
        self.assertNotIn('human',str(flagged[0]['kind']).lower())
