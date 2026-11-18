"""Offline adversarial tests for M3: immutability, failure modes, packet merge, export.

Fixtures are synthetic, not real SEC agreements or statistical recall claims.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from royalty_research.storage import read_json, sha256, json_bytes
from royalty_research.m2_packets import make_packets
from royalty_research.m3_workspace import (init,register_map,register_extraction,select_attempt,
                                           read_map,load_attempt,record_human_review,
                                           list_documents)
from royalty_research.m3_linkage import validate_linkage,default_linkage
from royalty_research.m3_export import build_rows,write_csvs,_txt,_number,official_sec_url
from royalty_research.m3_chunks import merge_chunks
from royalty_research.m3_workbook import write_xlsx

HERE=Path(__file__).resolve().parent.parent
MAP=read_json(HERE/'output'/'synthetic_clause_map.json')
EXTRACTION=read_json(HERE/'examples'/'synthetic_m2_extraction.json')

class M3WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root=Path(self.td.name)
        init(self.root)
        self.map=copy.deepcopy(MAP)
        self.extract=copy.deepcopy(EXTRACTION)
        self.did=self.map['document_id']
        register_map(self.root,self.map)
    def ingest(self, extraction=None, select=True):
        return register_extraction(self.root,self.did,extraction or self.extract,select=select)
    def test_init_idempotent(self):
        self.assertEqual(init(self.root)['status'],'EXISTING')
    def test_no_extraction_is_queued(self):
        records=list_documents(self.root)
        self.assertEqual(records[0]['state'],'AWAITING_EXTRACTION')
        self.assertEqual(len(build_rows(self.root)['Pending Jobs']),2)
    def test_map_cannot_be_replaced_different_text(self):
        corrupt=copy.deepcopy(self.map)
        corrupt['mapped_at_utc']='2030-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'Immutable'):
            register_map(self.root,corrupt)
        self.assertEqual(read_map(self.root,self.did),self.map)
    def test_map_can_be_registered_twice_same_bytes(self):
        self.assertEqual(register_map(self.root,self.map)['status'],'REGISTERED')
    def test_unsafe_document_id(self):
        bad=copy.deepcopy(self.map)
        bad['document_id']='../../escape'
        with self.assertRaises(ValueError):register_map(self.root,bad)
    def test_attempt_is_immutable_and_idempotent(self):
        a=self.ingest();b=self.ingest()
        self.assertEqual(a['extraction_sha256'],b['extraction_sha256'])
        self.assertEqual(len(list_documents(self.root)[0]['attempts']),1)
        digest=a['extraction_sha256'];doc_folder=next((self.root/'documents').iterdir())
        p=doc_folder/'attempts'/digest/'extraction.json'
        p.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'modified'):
            load_attempt(self.root,self.did,digest)
    def test_failure_attempt_does_not_overwrite_pass(self):
        good=self.ingest()
        wrong=copy.deepcopy(self.extract)
        wrong['royalty_terms'][0]['tiers'][0]['rate_value']='999'
        bad=self.ingest(wrong,select=False)
        self.assertNotEqual(good['extraction_sha256'],bad['extraction_sha256'])
        self.assertEqual(len(list_documents(self.root)[0]['attempts']),2)
        self.assertEqual(list_documents(self.root)[0]['state'],'QC_PASSED_OPEN_HIGH_ISSUE')
        select_attempt(self.root,self.did,bad['extraction_sha256'])
        self.assertEqual(list_documents(self.root)[0]['state'],'QC_FAILED')
        select_attempt(self.root,self.did,good['extraction_sha256'])
        self.assertEqual(list_documents(self.root)[0]['state'],'QC_PASSED_OPEN_HIGH_ISSUE')
    def test_selection_not_automatic(self):
        self.ingest(select=False)
        self.assertEqual(list_documents(self.root)[0]['state'],'AWAITING_EXTRACTION')
    def test_no_human_approval_needed_or_supported(self):
        self.ingest()
        self.assertEqual(list_documents(self.root)[0]['state'],'QC_PASSED_OPEN_HIGH_ISSUE')
        self.assertNotIn('Human Reviewed',build_rows(self.root))
        with self.assertRaisesRegex(ValueError,'HUMAN_APPROVAL_DISABLED'):
            record_human_review(self.root,{})
    def test_source_and_extraction_binding(self):
        self.ingest()
        p=next((self.root/'documents').iterdir())/'map.json'
        obj=read_json(p);obj['mapped_at_utc']='2050-01-01T00:00:00Z'
        p.write_text(json.dumps(obj),encoding='utf-8')
        with self.assertRaises(ValueError):list_documents(self.root)
    def test_invalid_url_does_not_create_curated(self):
        self.ingest()
        self.assertFalse(official_sec_url(self.map.get('source_url')))
        self.assertNotIn('Human Reviewed',build_rows(self.root))
    def test_workbook_is_bounded_and_formula_safe(self):
        self.ingest()
        rows=build_rows(self.root)
        self.assertEqual(len(rows['Royalty Terms']),4)
        self.assertEqual(len(rows['Tiers']),5)
        self.assertEqual(len(rows['Evidence']),len(self.extract['evidence'])+1)
        self.assertEqual(rows['Tiers'][1][6],6.0)
        self.assertEqual(_txt('=HYPERLINK("http://evil")')[0],"'")
        self.assertEqual(_txt('+PAYME')[0],"'")
        self.assertIsNone(_number('12345678901234567890'))
        with self.assertRaises(ValueError):_txt('x'*32768)
        with self.assertRaises(ValueError):_txt(['x'*32768])
        self.assertFalse(official_sec_url('https://www.sec.gov.evil.com/Archives/edgar/data/foo'))
        self.assertTrue(official_sec_url('https://www.sec.gov/Archives/edgar/data/123/456/test.htm'))
        dest=self.root/'exports'
        write_csvs(rows,dest)
        self.assertTrue((dest/'royalty_terms.csv').exists())
        import csv
        with open(dest/'tiers.csv',encoding='utf-8-sig',newline='') as f:
            self.assertEqual(len(list(csv.reader(f))),5)
    def test_sec_identifiers_are_derived_only_from_valid_edgar_url(self):
        from royalty_research.m3_export import sec_identifiers
        m=copy.deepcopy(self.map)
        m['source_url']='https://www.sec.gov/Archives/edgar/data/1520358/000149315213000675/ex10-2.htm'
        obj=sec_identifiers(m)
        self.assertEqual(obj['cik'],'1520358')
        self.assertEqual(obj['accession'],'0001493152-13-000675')
        self.assertEqual(obj['filename'],'synthetic_licence.html')  # preserved M1 metadata
        m['source_url']='https://www.sec.gov.evil.net/Archives/edgar/data/1520358/000149315213000675/ex10-2.htm'
        m['document_metadata']={}
        self.assertIsNone(sec_identifiers(m)['accession'])

    def test_actual_xlsx_is_valid_zip(self):
        self.ingest()
        import zipfile
        outfile=self.root/'staging.xlsx'
        write_xlsx(build_rows(self.root),outfile)
        with zipfile.ZipFile(outfile) as z:
            self.assertIn('xl/workbook.xml',z.namelist())
            self.assertGreater(len([n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]),10)

class LinkageTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.addCleanup(self.td.cleanup)
        self.root=Path(self.td.name);init(self.root)
        self.a=copy.deepcopy(MAP);self.b=copy.deepcopy(MAP)
        self.b['document_id']='DOC-OTHER'
        for p in self.b['passages']:
            p['passage_id']=p['passage_id'].replace(self.a['document_id'],self.b['document_id'])
        self.b['candidate_passages']=[x.replace(self.a['document_id'],self.b['document_id']) for x in self.b['candidate_passages']]
        for sec in self.b['sections']:
            for k in ('passage_ids','candidate_ids'):
                sec[k]=[v.replace(self.a['document_id'],self.b['document_id']) for v in sec[k]]
        for o in self.b['definitions']+self.b['cross_references']:
            o['passage_id']=o['passage_id'].replace(self.a['document_id'],self.b['document_id'])
        register_map(self.root,self.a);register_map(self.root,self.b)
        self.docs=list_documents(self.root)
        self.ids=[x['document_id'] for x in self.docs]
    def test_no_auto_dedup_even_exact_text(self):
        rows=build_rows(self.root)
        self.assertEqual(len(rows['Agreements']),3)
        self.assertEqual(len(validate_linkage(default_linkage(),self.docs)['exact_text_duplicates_unreconciled']),1)
    def group(self):
        return {'schema':'m3-linkage.1','groups':[{'agreement_id':'AGR-1',
            'document_ids':self.ids,'status':'HUMAN_CONFIRMED','reviewed_by':'Fixture Operator'}],
            'relations':[{'from_document':self.ids[0],'to_document':self.ids[1],
                'relation':'AMENDS','basis':'Fictional amendment based on signed agreement',
                'review_status':'HUMAN_CONFIRMED','reviewed_by':'Fixture Operator',
                'effective_date':'2025-03-10','supersession_scope':'SOME_TERMS'}]}
    def test_human_group_and_amendment_are_not_auto_superseded(self):
        linkage=self.group()
        self.assertEqual(len(build_rows(self.root,linkage)['Amendments']),2)
        self.assertEqual(len(build_rows(self.root,linkage)['Agreements']),2)
        self.assertEqual(len(validate_linkage(linkage,self.docs)['exact_text_duplicates_unreconciled']),0)
    def test_double_assignment_rejected(self):
        linkage=self.group();linkage['groups'].append({'agreement_id':'AGR-2',
            'document_ids':[self.ids[0]],'status':'AI_PROPOSED'})
        with self.assertRaises(ValueError):validate_linkage(linkage,self.docs)
    def test_bad_relationship_rejected(self):
        linkage=self.group();linkage['relations'][0]['to_document']='DOC-UNKNOWN'
        with self.assertRaises(ValueError):validate_linkage(linkage,self.docs)
    def test_cycle_rejected(self):
        linkage=self.group()
        rev=copy.deepcopy(linkage['relations'][0])
        rev['from_document'],rev['to_document']=rev['to_document'],rev['from_document']
        linkage['relations'].append(rev)
        with self.assertRaisesRegex(ValueError,'Cycle'):validate_linkage(linkage,self.docs)

class ChunkMergeTests(unittest.TestCase):
    def setUp(self):
        self.map=copy.deepcopy(MAP);self.extract=copy.deepcopy(EXTRACTION)
        self.packet=make_packets(self.map,mode='full',max_chars=2000)
        self.assertGreater(len(self.packet['chunks']),1)
        sha=sha256(json_bytes(self.packet))
        self.outputs=[]
        # One fictional agent reads each assigned chunk. Duplicated term IDs
        # across chunks are prohibited, so each economic record is assigned to
        # the chunk of its first evidence anchor. Other references may span chunks.
        anchors={e['evidence_id']:e['passage_id'] for e in self.extract['evidence']}
        for chunk in self.packet['chunks']:
            ids=[p['passage_id'] for p in chunk['passages']]
            mine=set(ids)
            def first_anchor(record):
                ev=record.get('evidence_ids',[])
                return anchors.get(ev[0]) if ev else None
            chunk_agreement=copy.deepcopy(self.extract['agreement']) if chunk['chunk_index']==1 else {}
            item={'schema':'m3-chunk.1','document_id':self.map['document_id'],
                  'source_text_sha256':self.map['text_sha256'],
                  'packet_sha256':sha,'chunk_index':chunk['chunk_index'],
                  'chunk_count':len(self.packet['chunks']),
                  'reviewed_passage_ids':ids,
                  'reader':{'engine':'fixture','model':'fictional-fixture','run_id':f'chunk-{chunk["chunk_index"]}'},
                  'agreement':chunk_agreement,
                  'amendment_status':self.extract['amendment_status'],
                  'evidence':[e for e in self.extract['evidence'] if e['passage_id'] in mine],
                  'royalty_terms':[t for t in self.extract['royalty_terms'] if first_anchor(t) in mine],
                  'other_payments':[p for p in self.extract['other_payments'] if first_anchor(p) in mine],
                  'dispositions':[d for d in self.extract['dispositions'] if d['passage_id'] in mine],
                  'open_issues':[i for i in self.extract['open_issues'] if i['passage_ids'][0] in mine]}
            self.outputs.append(item)
    def test_chunk_merge_recovers_complete_output(self):
        merged,report=merge_chunks(self.map,self.packet,self.outputs)
        self.assertEqual(merged['reader']['read_scope'],'FULL_DOCUMENT')
        self.assertEqual(len(merged['royalty_terms']),len(self.extract['royalty_terms']))
        self.assertEqual(report['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
    def test_missing_chunk_rejected(self):
        with self.assertRaisesRegex(ValueError,'partial'):
            merge_chunks(self.map,self.packet,self.outputs[:-1])
    def test_stale_packet_rejected(self):
        outputs=copy.deepcopy(self.outputs);outputs[0]['packet_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'fingerprint'):
            merge_chunks(self.map,self.packet,outputs)
    def test_duplicate_chunk_index_rejected(self):
        outputs=copy.deepcopy(self.outputs);outputs[1]['chunk_index']=1
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            merge_chunks(self.map,self.packet,outputs)
    def test_missing_passage_claim_rejected(self):
        outputs=copy.deepcopy(self.outputs);outputs[0]['reviewed_passage_ids'].pop()
        with self.assertRaisesRegex(ValueError,'read ledger'):
            merge_chunks(self.map,self.packet,outputs)
    def test_duplicate_evidence_id_rejected(self):
        outputs=copy.deepcopy(self.outputs)
        if len(outputs)>1 and outputs[1]['evidence']:
            outputs[1]['evidence'][0]['evidence_id']=outputs[0]['evidence'][0]['evidence_id']
            with self.assertRaisesRegex(ValueError,'duplicate'):
                merge_chunks(self.map,self.packet,outputs)
    def test_conflicting_header_kept_visible_not_fatal(self):
        # RF-07: a differently worded header in a later task must not strand captured work.
        # The first task's value is kept and the difference becomes an open issue.
        outputs=copy.deepcopy(self.outputs)
        first_title=outputs[0]['agreement'].get('title')
        outputs[1]['agreement']={'title':'Contradictory title'}
        merged,_=merge_chunks(self.map,self.packet,outputs)
        if first_title is not None:
            self.assertEqual(merged['agreement']['title'],first_title)
            kinds=[i.get('kind') for i in merged['open_issues']]
            self.assertIn('AGREEMENT_HEADER_DIFFERS_ACROSS_AI_TASKS',kinds)
        else:
            self.assertEqual(merged['agreement']['title'],'Contradictory title')
    def test_redundant_material_term_evidence_is_accepted(self):
        outputs=copy.deepcopy(self.outputs)
        first=outputs[0]
        eid=first['evidence'][0]['evidence_id']
        first['agreement']['other_material_terms']=[
            {'category':'SCOPE','text':'Scope stated in source','evidence_ids':[eid]}]
        first['agreement'].setdefault('field_evidence',{})['other_material_terms']=[eid]
        merged,_=merge_chunks(self.map,self.packet,outputs)
        self.assertNotIn('other_material_terms',merged['agreement']['field_evidence'])
        self.assertEqual(merged['agreement']['other_material_terms'][0]['evidence_ids'],[eid])
        extra=first['evidence'][1]['evidence_id']
        first['agreement']['field_evidence']['other_material_terms']=[eid,extra]
        merged,_=merge_chunks(self.map,self.packet,outputs)
        self.assertEqual(merged['agreement']['other_material_terms'][0]['evidence_ids'],[eid])
        issue=next(i for i in merged['open_issues'] if i['kind']=='UNBOUND_MATERIAL_TERM_EVIDENCE')
        self.assertIn(extra,issue['description'])
        self.assertIn(first['evidence'][1]['passage_id'],issue['passage_ids'])
        first['agreement']['field_evidence']['other_material_terms']=[extra]
        merged,_=merge_chunks(self.map,self.packet,outputs)
        self.assertEqual(merged['agreement']['other_material_terms'][0]['evidence_ids'],[eid])
        self.assertTrue(any(i['kind']=='UNBOUND_MATERIAL_TERM_EVIDENCE' for i in merged['open_issues']))
        first['agreement']['field_evidence']['other_material_terms']=['unknown-evidence']
        with self.assertRaisesRegex(ValueError,'Bad agreement evidence'):
            merge_chunks(self.map,self.packet,outputs)

if __name__=='__main__': unittest.main()
