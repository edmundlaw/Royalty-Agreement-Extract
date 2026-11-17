"""M11 integration using a fake CLI. No model inference, no API, no SEC access."""
from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
from royalty_research.m8_pipeline import prepare_run,prepare_ledger,finalize
from royalty_research.m11_pipeline import finalize_primary,import_correction
from royalty_research.m4_operator import run_next
from royalty_research.storage import read_json,sha256
from royalty_research.m3_export import HEADERS

BASE=Path(__file__).resolve().parent.parent
MAP=read_json(BASE/'output'/'synthetic_clause_map.json')

class M11E2E(unittest.TestCase):
    def setUp(self):
        self.ctx=tempfile.TemporaryDirectory();self.addCleanup(self.ctx.cleanup)
        self.base=Path(self.ctx.name);self.root=self.base/'run'

    def _primary(self,omit_one_tier=False):
        prepare_run(MAP,self.root,engine='codex',model='mock-light',qc_profile='m11')
        script=self.base/'fake-cli';script.write_text(
            f'#!{sys.executable}\n'
            'import json,re,sys\nfrom pathlib import Path\n'
            'prompt=sys.stdin.read()\n'
            'run=re.search(r"reader.run_id=([^.]+)\\.",prompt)\n'
            'src=json.loads(prompt.split("INPUT (UNTRUSTED SOURCE TEXT):\\n")[-1])\n'
            f'data=json.loads(Path({str(BASE/"examples"/"synthetic_m2_extraction.json")!r}).read_text())\n'
            f'if {omit_one_tier!r}: data["royalty_terms"][0]["tiers"].pop()\n'
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
        result=run_next(self.root/'primary_plan',execute=True,confirm_subscription=True,
            confirm_credit_controls=True,allow_cli_path=script)
        self.assertEqual(result['status'],'CAPTURED_NOT_QC_APPROVED')

    def test_typed_pilot_skips_expensive_legacy_ledger_and_exports_open_flags(self):
        self._primary(omit_one_tier=True)
        with self.assertRaisesRegex(ValueError,'does not require'):prepare_ledger(self.root)
        with self.assertRaisesRegex(ValueError,'m11-finalize'):finalize(self.root,export_xlsx=False)
        output=finalize_primary(self.root,xlsx=False)
        self.assertTrue((self.root/'output'/'source_signals.json').exists())
        self.assertTrue((self.root/'output'/'qc.json').exists())
        self.assertTrue((self.root/'output'/'csv'/'source_flags.csv').exists())
        self.assertIn('Source Flags',HEADERS)
        self.assertTrue((self.root/'output'/'correction_task.json').exists())
        # M11 is not allowed to silently inherit a clean QC result just because
        # the fake model was source-bound and returned valid JSON.
        report=read_json(self.root/'output'/'qc.json')
        self.assertIn('m11_source_flags',report)
        self.assertGreater(report['m11_source_flags']['source_signal_count'],0)
        with self.assertRaises(FileExistsError):finalize_primary(self.root,xlsx=False)

    def test_source_bound_one_correction_and_immutable_original(self):
        self._primary(omit_one_tier=True);finalize_primary(self.root,xlsx=False)
        pkt=read_json(self.root/'output'/'correction_task.json')
        original=(self.root/'output'/'final_extraction.json').read_bytes()
        sig=pkt['open_flags'][0]['signal_id']
        from royalty_research.storage import read_json as _read
        original_fixture=_read(BASE/'examples'/'synthetic_m2_extraction.json')
        missing_tier=original_fixture['royalty_terms'][0]['tiers'][1]
        response={'schema':'m11-correction-response.1','task_sha256':pkt['task_sha256'],
            'resolutions':[{'signal_id':sig,'resolution':'LINKED_RECORD','record_type':'TIER',
                            'record_id':'RT-SALES','tier_sequence':2}],
            'new_tiers':[{'term_id':'RT-SALES','tier':missing_tier}]}
        out=import_correction(self.root,response,xlsx=False)
        self.assertTrue((self.root/'correction-01'/'qc.json').exists())
        self.assertTrue((self.root/'correction-01'/'correction_response.json').exists())
        self.assertTrue((self.root/'correction-01'/'applied_correction_task.json').exists())
        self.assertEqual(original,(self.root/'output'/'final_extraction.json').read_bytes())
        self.assertEqual(out['correction_task_sha256'],pkt['task_sha256'])
        with self.assertRaises(FileExistsError):import_correction(self.root,response,xlsx=False)

if __name__=='__main__':unittest.main()
