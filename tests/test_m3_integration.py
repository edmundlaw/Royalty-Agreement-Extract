"""M3 command-line, workbook content and review-link integrity integration tests."""
from __future__ import annotations
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from royalty_research.storage import read_json,json_bytes,sha256
from royalty_research.m3_workspace import (init,register_map,register_extraction,record_human_review,
                                           register_second_reader,list_documents,select_attempt)
from royalty_research.m3_linkage import validate_linkage
from royalty_research.m3_export import build_rows,export_manifest
from royalty_research.m3_workbook import write_xlsx

HERE=Path(__file__).resolve().parent.parent
MAP=read_json(HERE/'output/synthetic_clause_map.json')
EXTRACTION=read_json(HERE/'examples/synthetic_m2_extraction.json')

class M3IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();self.addCleanup(self.td.cleanup)
        self.tmp=Path(self.td.name)
        self.root=self.tmp/'research'
        init(self.root)
        self.m=copy.deepcopy(MAP)
        self.x=copy.deepcopy(EXTRACTION)
        register_map(self.root,self.m)
        self.did=self.m['document_id']
    def test_source_packet_text_edit_detected_even_when_packet_hash_recomputed(self):
        from royalty_research.m2_packets import make_packets
        from royalty_research.m3_chunks import merge_chunks
        p=make_packets(self.m,mode='full',max_chars=2000)
        p['chunks'][0]['passages'][0]['text']='SYNTHETIC CHANGED HEADER'
        with self.assertRaisesRegex(ValueError,'differs from authoritative'):
            merge_chunks(self.m,p,[])
    def test_second_reader_comparison_bound_to_primary_digest(self):
        a=register_extraction(self.root,self.did,self.x,select=True)
        b=copy.deepcopy(self.x)
        b['reader']['engine']='codex'
        b['reader']['model']='fictional-second-engine'
        b['reader']['run_id']='fictional-second-run'
        rv=register_second_reader(self.root,self.did,b)
        self.assertEqual(rv['status'],'NO_DETECTED_DISAGREEMENT_NOT_PROOF_OF_ACCURACY')
        self.assertEqual(len(list_documents(self.root)[0]['ai_reviews']),1)
        changed=copy.deepcopy(self.x)
        changed['reader']['run_id']='third-run'
        c=register_extraction(self.root,self.did,changed,select=True)
        self.assertEqual(len(list_documents(self.root)[0]['ai_reviews']),0)
        select_attempt(self.root,self.did,a['extraction_sha256'])
        self.assertEqual(len(list_documents(self.root)[0]['ai_reviews']),1)
    def test_export_all_records_without_human_signoff(self):
        self.m['source_url']='https://www.sec.gov/Archives/edgar/data/1/000000000000000001/fictional.htm'
        self.x['source_url']=self.m['source_url']
        fresh=self.tmp/'fresh';init(fresh);register_map(fresh,self.m)
        self.x['open_issues'][0]['status']='RESOLVED'
        register_extraction(fresh,self.did,self.x,select=True)
        rows=build_rows(fresh)
        self.assertEqual(list_documents(fresh)[0]['state'],'QC_PASSED_NOT_PROFESSIONALLY_VERIFIED')
        self.assertEqual(len(rows['Royalty Terms']),4)
        self.assertNotIn('Human Reviewed', rows)
        self.assertNotIn('Human_Review_Status', rows['Documents'][0])
        self.assertNotIn('Human_Review_Reported',rows['QC'][0])
        outfile=self.tmp/'research_without_approval.xlsx'
        write_xlsx(rows,outfile)
        from openpyxl import load_workbook
        wb=load_workbook(str(outfile))
        self.assertNotIn('Human Reviewed',wb.sheetnames)
        hdr=rows['Documents'][0]
        cell=wb['Documents'].cell(row=2,column=hdr.index('Open_Source')+1)
        self.assertIn('HYPERLINK',str(cell.value))
    def test_real_cli_end_to_end_offline(self):
        from royalty_research.cli import main
        map_path=self.tmp/'source_map.json'; map_path.write_text(json.dumps(self.m),encoding='utf-8')
        ext_path=self.tmp/'extraction.json'; ext_path.write_text(json.dumps(self.x),encoding='utf-8')
        self.assertEqual(main(['m3-register-map','--workspace',str(self.root),'--map',str(map_path)]),0)
        self.assertEqual(main(['m3-ingest','--workspace',str(self.root),'--document-id',self.did,
                               '--extraction',str(ext_path),'--select']),0)
        status_path=self.tmp/'jobs.json'
        self.assertEqual(main(['m3-status','--workspace',str(self.root),'--out',str(status_path)]),0)
        self.assertEqual(read_json(status_path)['documents'],1)
        out=self.tmp/'publish'
        self.assertEqual(main(['m3-export','--workspace',str(self.root),'--outdir',str(out),'--format','both']),0)
        self.assertTrue((out/'Royalty_Research_Historical_Staging.xlsx').is_file())
        manifest=read_json(out/'export_manifest.json')
        self.assertEqual(manifest['sheet_row_counts']['Royalty Terms'],3)
        for name,hash_ in manifest['file_sha256'].items():
            self.assertEqual(sha256((out/name).read_bytes()),hash_)
        self.assertNotEqual(main(['m3-export','--workspace',str(self.root),'--outdir',str(out),'--format','both']),0)
    def test_linkage_unknown_doc_rejected(self):
        bad={'schema':'m3-linkage.1','groups':[{'agreement_id':'AGR-1','status':'AI_PROPOSED',
             'document_ids':['DOC-NOPE']}], 'relations':[]}
        with self.assertRaises(ValueError):validate_linkage(bad,list_documents(self.root))

if __name__=='__main__':unittest.main()
