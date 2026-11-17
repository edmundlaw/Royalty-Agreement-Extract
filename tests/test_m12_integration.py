"""M12 end-to-end integration with fake local CLI. No model calls or paid API."""
from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
from royalty_research.m8_pipeline import prepare_run,prepare_ledger,finalize
from royalty_research.m11_pipeline import finalize_primary_m12,import_correction_m12
from royalty_research.m4_operator import run_next
from royalty_research.storage import read_json
from royalty_research.m3_export import HEADERS
from royalty_research.m12_economic_qc import build_correction_packet,apply_correction_response

BASE=Path(__file__).resolve().parent.parent
MAP=read_json(BASE/'output'/'synthetic_clause_map.json')

class M12E2E(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.root=self.base/'run'
    def _run(self,omit=False):
        prepare_run(MAP,self.root,engine='codex',model='mock-light',qc_profile='m12')
        script=self.base/'fake_cli';script.write_text(
           f'#!{sys.executable}\n'
           'import json,re,sys\nfrom pathlib import Path\n'
           'prompt=sys.stdin.read()\n'
           'run=re.search(r"reader.run_id=([^.]+)\\.",prompt)\n'
           'src=json.loads(prompt.split("INPUT (UNTRUSTED SOURCE TEXT):\\n")[-1])\n'
           f'data=json.loads(Path({str(BASE/"examples"/"synthetic_m2_extraction.json")!r}).read_text())\n'
           f'if {omit!r}: data["royalty_terms"][0]["tiers"].pop()\n'
           'obj={"schema":"m3-chunk.1","document_id":src["document_id"],'
           '"source_text_sha256":src["source_text_sha256"],"packet_sha256":src["packet_sha256"],'
           '"chunk_index":src["chunk_index"],"chunk_count":src["chunk_count"],'
           '"reviewed_passage_ids":src["reviewed_passage_ids"],'
           '"reader":{"engine":"codex","model":"mock-light","run_id":run.group(1)},'
           '"agreement":data["agreement"],"royalty_terms":data["royalty_terms"],'
           '"other_payments":data["other_payments"],"evidence":data["evidence"],'
           '"dispositions":data["dispositions"],"open_issues":data["open_issues"],'
           '"amendment_status":data["amendment_status"]}\n'
           'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps(obj))\n')
        script.chmod(0o755)
        captured=run_next(self.root/'primary_plan',execute=True,confirm_subscription=True,
                          confirm_credit_controls=True,allow_cli_path=script)
        self.assertEqual(captured['status'],'CAPTURED_NOT_QC_APPROVED')
    def test_m12_profile_exports_qc_and_never_requires_ledger(self):
        self._run(omit=True)
        with self.assertRaisesRegex(ValueError,'does not require'):prepare_ledger(self.root)
        with self.assertRaisesRegex(ValueError,'m12-finalize'):finalize(self.root,export_xlsx=False)
        result=finalize_primary_m12(self.root,xlsx=False)
        self.assertTrue((self.root/'output'/'source_signals.json').exists())
        qc=read_json(self.root/'output'/'qc.json')
        self.assertIn('m12_source_flags',qc)
        self.assertGreater(qc['m12_source_flags']['source_signal_count'],0)
        self.assertTrue((self.root/'output'/'csv'/'source_flags.csv').exists())
        self.assertTrue((self.root/'output'/'correction_task.json').exists())
        self.assertEqual(result['m12_status'],qc['m12_source_flags']['status'])
        self.assertIn('M12_Flag_Status',HEADERS['QC'])
        self.assertTrue((self.root/'output'/'output_manifest.json').exists())
        with self.assertRaises(FileExistsError):finalize_primary_m12(self.root,xlsx=False)
    def test_saved_correction_is_immutable_and_append_only(self):
        import copy
        from tests.test_m12 import pair
        m,e=pair('Qualigen')
        x=copy.deepcopy(e)
        paid=next(p for p in x['other_payments'] if p['kind']=='UPFRONT')
        x['other_payments']=[p for p in x['other_payments'] if p['kind']!='UPFRONT']
        x['m12_resolutions']=[]
        pkt=build_correction_packet(m,x)
        unchanged=json.dumps(x,sort_keys=True)
        result=apply_correction_response(m,x,pkt,{
            'schema':'m12-correction-response.1','task_sha256':pkt['task_sha256'],
            'new_payments':[paid]})
        self.assertEqual(json.dumps(x,sort_keys=True),unchanged)
        self.assertEqual(result['qc']['warning_open'],0)
        self.assertEqual(result['qc']['hard_open'],0)
        self.assertEqual(len(result['updated_extraction']['other_payments']),len(e['other_payments']))

if __name__=='__main__':unittest.main()

class ExcelRoundTrip(unittest.TestCase):
    def test_m12_exports_valid_xlsx_without_human_approval(self):
        from tests.test_m12_integration import M12E2E
        import zipfile,xml.etree.ElementTree as ET
        subject=M12E2E('test_m12_profile_exports_qc_and_never_requires_ledger')
        subject.setUp()
        try:
            subject._run(omit=False)
            result=finalize_primary_m12(subject.root,xlsx=True)
            xlsx=Path(result['spreadsheet'])
            self.assertTrue(xlsx.is_file())
            with zipfile.ZipFile(xlsx) as z:
                self.assertIsNone(z.testzip())
                root=ET.fromstring(z.read('xl/workbook.xml'))
                ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                names=[x.get('name') for x in root.findall('.//x:sheet',ns)]
                self.assertIn('Source Flags',names)
                self.assertIn('QC',names)
                self.assertNotIn('Human Reviewed',names)
        finally:subject.tearDown()
