"""Offline full-source production regression and controller tests."""
import json
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from royalty_research.storage import read_json, sha256, json_bytes
from royalty_research.m13_production import prepare_one,run_boundary,batch,candidate_rank,licence_gate,document_metadata
from royalty_research.licence_grant import document_title,title_kind,grant_hits
import subprocess,os
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
            consolidation = read_json(run/'output/consolidation.json')
            self.assertEqual(consolidation['terms_before'], consolidation['terms_after'])
            self.assertEqual(consolidation['notes'], [])

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
                client.return_value.fetch.return_value=b'LICENSE AGREEMENT. Licensee shall pay a royalty of 5% of Net Sales. Royalties are due quarterly. Royalty reports follow.'
                result=batch(candidates,root/'batch',user_agent='Research name email@example.com',mode='manual',
                    engine='codex',model='chosen-ai',max_agreements=1)
                self.assertEqual(client.return_value.fetch.call_count,1)
            index=read_json(root/'batch/candidate_register.json')
            self.assertEqual(result['candidates'],2)
            self.assertEqual(index[1]['status'],'NOT_PREPARED_AGREEMENT_LIMIT')

    def test_candidate_order_puts_licence_exhibits_first(self):
        base='https://www.sec.gov/Archives/edgar/data/1/123/'
        rows=[{'source_url':base+'pricing.htm','file_type':'424B2','candidate_route':'NARRATIVE_OR_OTHER','matched_queries':['royalties','license agreement']},
              {'source_url':base+'ex4.htm','file_type':'EX-4.1','candidate_route':'CONTRACT_EXHIBIT','matched_queries':['royalties']},
              {'source_url':base+'ex10.htm','file_type':'EX-10.1','candidate_route':'CONTRACT_EXHIBIT','matched_queries':['royalties']}]
        self.assertEqual([r['file_type'] for r in sorted(rows,key=candidate_rank)],['EX-10.1','EX-4.1','424B2'])

    def test_low_signal_download_does_not_use_up_agreement_limit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);base='https://www.sec.gov/Archives/edgar/data/1/123/'
            candidates=root/'candidates.jsonl'
            candidates.write_text('\n'.join(json.dumps({'source_url':base+n,'file_type':'EX-10.1','candidate_route':'CONTRACT_EXHIBIT'})
                                            for n in ('a.txt','b.txt','c.txt')))
            pages={base+'a.txt':b'Pricing supplement for notes. Interest is payable quarterly.',
                   base+'b.txt':b'LICENSE AGREEMENT. Licensee shall pay a royalty of 5% of Net Sales. Royalties are due quarterly. Royalty reports follow.',
                   base+'c.txt':b'LICENSE AGREEMENT. Licensee shall pay a royalty of 3% of Net Sales. Royalties are due quarterly. Royalty reports follow.'}
            with patch('royalty_research.m13_production.SECClient') as client:
                client.return_value.fetch.side_effect=lambda url:pages[url]
                result=batch(candidates,root/'batch',user_agent='Research name email@example.com',mode='manual',
                    engine='codex',model='chosen-ai',max_agreements=1)
            index=read_json(root/'batch/candidate_register.json')
            self.assertEqual([i['status'] for i in index],
                             ['LOW_SIGNAL_REVIEW_REQUIRED','FULL_SOURCE_PREPARED','NOT_PREPARED_AGREEMENT_LIMIT'])
            self.assertEqual(result['prepared'],1)

    def test_licence_gate_rejects_purchase_agreement_boilerplate(self):
        page=lambda t:{'passages':[{'text':t}]}
        boiler=page('ASSET PURCHASE AGREEMENT. '+'Buyer acquires the assets. '*3000+'no royalties are payable; no royalty.')
        self.assertFalse(licence_gate(boiler)['passed'])
        self.assertTrue(licence_gate(page('EXCLUSIVE LICENSE AGREEMENT. Royalty 5%. Royalties quarterly. Royalty report.'))['passed'])

class RunBoundaryContinuesAgreement(unittest.TestCase):
    """v0.13.7: all tasks of one agreement are called before the next agreement; every stop still applies."""
    def _runs(self,d,sizes):
        runs=Path(d)/'runs';state={}
        for name,n in sizes.items():
            root=runs/name;(root/'reader_a'/'prompts').mkdir(parents=True);(root/'m13_run.json').write_text('{}')
            (root/'reader_a'/'plan.json').write_text(json.dumps({'engine':'codex'}))
            for i in range(1,n+1):(root/'reader_a'/'prompts'/f'CHUNK-{i:04d}.txt').write_text('prompt')
            state[name]={'captured':0,'total':n}
        return runs,state

    def _patches(self,state):
        def status(root):return {'readers':{'reader_a':dict(state[Path(root).name])}}
        def rstatus(folder):
            st=state[Path(folder).parent.name]
            return {'tasks':[{'task_id':f'CHUNK-{i:04d}','state':'CAPTURED_NOT_QC_APPROVED' if i<=st['captured'] else 'PENDING','attempts':0}
                             for i in range(1,st['total']+1)]}
        calls=[]
        def next_call(root,**kw):
            st=state[Path(root).name];st['captured']+=1;calls.append((Path(root).name,st['captured']))
            return {'status':'ALL_READINGS_CAPTURED' if st['captured']==st['total'] else 'CAPTURED_MORE_PENDING'}
        return calls,[patch('royalty_research.m13_production.m13.status',status),
                      patch('royalty_research.m13_production.reader_status',rstatus),
                      patch('royalty_research.m13_production.m13.next_call',next_call)]

    def test_two_chunk_and_one_chunk_agreements_get_three_calls(self):
        with tempfile.TemporaryDirectory() as d:
            runs,state=self._runs(d,{'A':2,'B':1})
            calls,ps=self._patches(state)
            for x in ps:x.start();self.addCleanup(x.stop)
            out=run_boundary(runs,max_calls=6,max_prompt_chars=300000,execute=True,confirm_subscription=True,confirm_credit_controls=True)
            self.assertEqual(calls,[('A',1),('A',2),('B',1)])
            self.assertEqual(out['calls_attempted'],3)

    def test_max_calls_stops_in_the_middle_of_an_agreement(self):
        with tempfile.TemporaryDirectory() as d:
            runs,state=self._runs(d,{'A':2,'B':1})
            calls,ps=self._patches(state)
            for x in ps:x.start();self.addCleanup(x.stop)
            out=run_boundary(runs,max_calls=2,max_prompt_chars=300000,execute=True,confirm_subscription=True,confirm_credit_controls=True)
            self.assertEqual(calls,[('A',1),('A',2)]);self.assertEqual(out['calls_attempted'],2)

    def test_dry_run_lists_next_call_of_each_agreement_without_calling(self):
        with tempfile.TemporaryDirectory() as d:
            runs,state=self._runs(d,{'A':2,'B':1})
            calls,ps=self._patches(state)
            for x in ps:x.start();self.addCleanup(x.stop)
            out=run_boundary(runs,max_calls=6,max_prompt_chars=300000)
            self.assertEqual(out['calls_attempted'],0);self.assertEqual([o['run'] for o in out['outcomes']],['A','B'])

    def test_prompt_budget_still_stops(self):
        with tempfile.TemporaryDirectory() as d:
            runs,state=self._runs(d,{'A':2})
            (runs/'A'/'reader_a'/'prompts'/'CHUNK-0001.txt').write_text('x'*2000)
            calls,ps=self._patches(state)
            for x in ps:x.start();self.addCleanup(x.stop)
            out=run_boundary(runs,max_calls=6,max_prompt_chars=1000,execute=True)
            self.assertEqual(out['outcomes'][0]['status'],'STOPPED_PROMPT_BUDGET');self.assertEqual(calls,[])


GRANT='Licensor hereby grants to Licensee an exclusive, royalty-bearing license under the Licensed Patents to make and sell Licensed Products. '
class LicenceGateV0137(unittest.TestCase):
    def doc(self,title,body):
        return {'passages':[{'text':'Exhibit 10.1'},{'text':title},{'text':body}]}

    def test_title_detection_skips_legends(self):
        ps=[{'text':'Exhibit 10.2'},{'text':'CERTAIN CONFIDENTIAL INFORMATION CONTAINED IN THIS DOCUMENT HAS BEEN OMITTED'},
            {'text':'SERVICES AGREEMENT'},{'text':'This Services Agreement is entered into as of today by and between the parties named below and others.'*3}]
        self.assertEqual(document_title(ps),'SERVICES AGREEMENT');self.assertEqual(title_kind('SERVICES AGREEMENT'),'NON_LICENCE')
        self.assertEqual(title_kind('BINDING TERM SHEET Global License Agreement for VXM01'),'LICENCE')
        self.assertEqual(title_kind('Schedule A Contract#: 12'),'UNKNOWN')

    def test_services_agreement_with_royalty_wording_and_no_grant_fails(self):
        g=licence_gate(self.doc('SERVICES AGREEMENT','The Company shall pay royalties of 10% of gross profit. Royalty statements quarterly. Royalty audit rights. '*3))
        self.assertFalse(g['passed']);self.assertEqual((g['title_kind'],g['grant_hits']),('NON_LICENCE',0));self.assertIn('Services',g['title'].title())

    def test_non_licence_title_with_some_grant_wording_still_fails(self):
        body='Royalty is payable to R-Bridge. Royalty reports. Royalty rate. '+'Licensor grants Licensee a license. '*12
        g=licence_gate(self.doc('ASSIGNMENT AND RELEASE AGREEMENT',body))
        self.assertFalse(g['passed']);self.assertGreaterEqual(g['grant_hits'],12)

    def test_non_licence_title_passes_only_with_strong_grant_wording(self):
        body='Royalty rate 5%. Royalty report. Royalty payments. '+GRANT*30
        self.assertTrue(licence_gate(self.doc('SUPPLY AND SERVICES AGREEMENT',body))['passed'])

    def test_licence_title_passes_without_grant_phrase(self):
        g=licence_gate(self.doc('FIRST AMENDMENT TO LICENSE AGREEMENT','Royalty rate becomes 4%. Royalty report. Royalties quarterly.'))
        self.assertTrue(g['passed'])

    def test_untitled_dense_royalty_text_needs_a_grant(self):
        base='Royalty rate 5% of Net Sales. Royalty report. Royalties are paid quarterly. The parties agree on the schedule of payments set out below in full. '
        self.assertFalse(licence_gate(self.doc('Schedule A',base))['passed'])
        self.assertTrue(licence_gate(self.doc('Schedule A',base+'The Licensor grants the Licensee a license.'))['passed'])

    def test_short_licence_with_stated_rate_and_grant_passes(self):
        body='Licensor grants Licensee an exclusive license under the Licensed Patents to make and sell Products. Licensee shall pay a royalty of 5% of Net Sales.'
        for title in ('Schedule A','PATENT LICENSE'):
            g=licence_gate(self.doc(title,body))
            self.assertTrue(g['passed'],(title,g));self.assertEqual(g['royalty_mentions'],1)
        self.assertTrue(licence_gate(self.doc('Schedule A',body.replace('5% of Net Sales','five (5%) percent of gross revenue').replace('five (5%) percent','5 percent')))['passed'])

    def test_short_document_without_grant_or_with_non_licence_title_still_fails(self):
        g=licence_gate(self.doc('SERVICES AGREEMENT','The Contractor performs services. The Company shall pay a royalty of 5% of Net Sales.'))
        self.assertFalse(g['passed'])
        g=licence_gate(self.doc('Schedule A','The Contractor performs the work described in the statement of work attached hereto. The Company shall pay a fee of 5% of Net Sales as full compensation for the work.'))
        self.assertFalse(g['passed']);self.assertIn('no licence-grant wording',g['reason'])
        # a grant without any stated rate and with fewer than 3 royalty mentions still fails
        self.assertFalse(licence_gate(self.doc('Schedule A','Licensor grants Licensee a license. A royalty is payable as agreed.'))['passed'])
        # a non-licence title is rejected even with a rate and a grant phrase
        g=licence_gate(self.doc('PURCHASE AGREEMENT','Seller grants Buyer a license. Buyer pays a royalty of 5% of Net Sales.'))
        self.assertFalse(g['passed']);self.assertIn('non-licence title',g['reason'])

    def test_grant_wording_families(self):
        for t in ('Company grants to Partner a non-exclusive licence','Licensor hereby licenses the Marks','an exclusive, worldwide license',
                  'under the Licensed Technology','a royalty-bearing license'):
            self.assertGreaterEqual(grant_hits(t),1,t)
        self.assertEqual(grant_hits('The Company provides services and pays 10% of gross profit.'),0)

    def test_known_licences_on_disk_still_pass(self):
        maps=sorted((ROOT/'tests/fixtures/m12_saved').glob('*_map.json'))+list((ROOT/'tests/fixtures/m6').glob('*mapped.json'))
        self.assertTrue(maps)
        for f in maps:
            with self.subTest(f=f.name):self.assertTrue(licence_gate(read_json(f))['passed'])

    def test_batch_records_gate_details_and_filing_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);u='https://www.sec.gov/Archives/edgar/data/1/123/a.txt'
            cand=root/'c.jsonl'
            cand.write_text(json.dumps({'source_url':u,'document_id':'DOC-X','filing_date':'2026-01-14','accession':'0001-26-000001','cik':'1','company':'Acme','file_type':'EX-10.1'}))
            with patch('royalty_research.m13_production.SECClient') as client:
                client.return_value.fetch.return_value=b'SERVICES AGREEMENT\n\nRoyalty of 5%. Royalty report. Royalties quarterly. Royalty audit.'
                batch(cand,root/'batch',user_agent='R n@example.com',mode='manual',engine='codex',model='m',max_agreements=1)
            item=read_json(root/'batch/candidate_register.json')[0]
            self.assertEqual(item['status'],'NOT_PREPARED_NOT_LICENCE_LIKE')
            self.assertEqual((item['licence_gate']['title'],item['licence_gate']['grant_hits']),('SERVICES AGREEMENT',0))
            self.assertEqual(item['filing_date'],'2026-01-14')
            self.assertEqual(read_json(root/'batch/maps/DOC-X.json')['document_metadata']['filing_date'],'2026-01-14')
        self.assertEqual(document_metadata({'filing_date':'2026-01-14','cik':'9','junk':1},'D','u'),
                         {'document_id':'D','source_url':'u','filing_date':'2026-01-14','cik':'9'})


class FinalizeFromRawChunks(unittest.TestCase):
    """Finalize from raw chunk results (the v0.13.6 test re-used an already merged extraction and missed the crash)."""
    def _run(self,d,discovery=None,agreement_extra=None,map_metadata=None):
        m=read_json(ROOT/'output/synthetic_clause_map.json')
        if map_metadata is not None:m['document_metadata']=map_metadata
        batch_root=Path(d)/'runs_x'
        run=batch_root/'batch'/'runs'/'one'
        prepare_one(m,run,mode='manual',engine='codex',model='chosen-ai',max_chars=64000)
        if discovery:(batch_root/'discovery.jsonl').write_text(json.dumps(dict(discovery,document_id=m['document_id']))+'\n')
        plan,packet,_=load_plan(run/'reader_a')
        src=read_json(ROOT/'examples/synthetic_m2_extraction.json')
        agreement=dict(src['agreement']);agreement['field_evidence']=dict(agreement['field_evidence'])
        agreement.update(agreement_extra or {})
        chunk=packet['chunks'][0]
        obj={'schema':'m3-chunk.1','document_id':m['document_id'],'source_text_sha256':m['text_sha256'],
             'packet_sha256':sha256(json_bytes(packet)),'chunk_index':1,'chunk_count':len(packet['chunks']),
             'reviewed_passage_ids':[p['passage_id'] for p in chunk['passages']],'reader':{},'agreement':agreement,
             'royalty_terms':src['royalty_terms'],'other_payments':src['other_payments'],'evidence':src['evidence'],
             'dispositions':src['dispositions'],'open_issues':src['open_issues'],'amendment_status':src['amendment_status']}
        response=Path(d)/'answer.json';response.write_text(json.dumps(obj))
        import_manual_result(run/'reader_a','CHUNK-0001',response)
        return run,m

    def test_new_v0136_fields_survive_merge_and_finalize(self):
        with tempfile.TemporaryDirectory() as d:
            run,m=self._run(d,agreement_extra={'related_party':'YES','licensed_ip_nature':'PATENT','licensed_ip_nature_basis':'INFERRED',
                'licensed_ip_nature_details':'The term runs to patent expiration.',
                'field_evidence':{'title':['EV01'],'related_party':['EV01'],'licensed_ip_nature':['EV01']}})
            result=finalize(run)
            self.assertEqual(result['status'],'EXPORTED')
            self.assertEqual(result['source_check_errors'],0)   # details cite the nature's evidence, as the reader prompt instructs
            ag=read_json(run/'output/final_extraction.json')['agreement']
            self.assertEqual((ag['related_party'],ag['licensed_ip_nature_basis']),('YES','INFERRED'))
            self.assertEqual(ag['field_evidence']['related_party'],['EV01'])
            from royalty_research.m3_chunks import agreement_scalar_fields
            self.assertTrue({'related_party','licensed_ip_nature_basis','licensed_ip_nature_details','exclusivity_scope'}<=set(agreement_scalar_fields()))

    def test_sec_filing_date_falls_back_to_batch_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            run,m=self._run(d,discovery={'filing_date':'2026-01-14','accession':'0001-26-000001','cik':'1'})
            finalize(run)
            rows=read_json(run/'output/rows.json')['Documents']
            self.assertEqual(rows[1][rows[0].index('Filing_Date')],'2026-01-14')
            self.assertEqual(read_json(run/'source/map.json').get('document_metadata',{}).get('filing_date'),None)  # immutable map untouched

    def test_no_discovery_leaves_filing_date_blank_without_error(self):
        with tempfile.TemporaryDirectory() as d:
            run,m=self._run(d)
            finalize(run)
            rows=read_json(run/'output/rows.json')['Documents']
            self.assertIn(rows[1][rows[0].index('Filing_Date')],(None,''))

    def test_empty_map_filing_date_uses_discovery_and_keeps_known_metadata(self):
        for empty in (None, '', '   '):
            with self.subTest(empty=empty), tempfile.TemporaryDirectory() as d:
                run,m=self._run(d,discovery={'filing_date':'2026-01-14','company':'Fallback Co'},
                                map_metadata={'filing_date':empty,'company':'Known Co'})
                finalize(run)
                rows=read_json(run/'output/rows.json')['Documents']
                self.assertEqual(rows[1][rows[0].index('Filing_Date')],'2026-01-14')
                from royalty_research.m3_workspace import read_map
                self.assertEqual(read_map(run/'workspace',m['document_id'])['document_metadata']['company'],'Known Co')


class ResumeScript(unittest.TestCase):
    def sh(self,*args):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
        return subprocess.run(['bash',str(ROOT/'royalty.sh'),*args],capture_output=True,text=True,env=env,timeout=120,cwd=ROOT)

    def test_resume_rejects_a_non_runs_folder(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.sh('--resume',d);self.assertEqual(r.returncode,2);self.assertIn('Not a runs folder',r.stderr)

    def test_resume_dry_run_skips_discover_and_makes_no_call(self):
        m=read_json(ROOT/'output/synthetic_clause_map.json')
        with tempfile.TemporaryDirectory() as d:
            prepare_one(m,Path(d)/'batch'/'runs'/'one',mode='single',engine='codex',model='mock-a',effort='low')
            r=self.sh('--resume',d)
            self.assertEqual(r.returncode,0,r.stderr+r.stdout)
            self.assertIn('DRY_RUN_NO_AI_CALLED',r.stdout);self.assertIn('discover and prepare skipped',r.stdout)
            self.assertNotIn('Discover SEC',r.stdout);self.assertIn('Dry run finished',r.stdout)

    def test_workbook_version_suffix_is_the_package_version(self):
        # v0.13.8 live run named a workbook _v0.8.1: royalty.sh imported the package with `python -I`,
        # which ignores PYTHONPATH and found an old editable install of another checkout.
        import royalty_research
        r=self.sh('--version');self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.strip(),royalty_research.__version__)
        self.assertNotRegex((ROOT/'royalty.sh').read_text(),r'-I -c .import royalty_research')


if __name__=='__main__':unittest.main()
