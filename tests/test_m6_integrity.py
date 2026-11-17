"""M6 real-source adversarial regressions and workspace fail-closed tests.

Market Finders map/extraction were supplied by the independent Fable reviewer:
https://www.sec.gov/Archives/edgar/data/1520358/000149315213000675/ex10-2.htm
They are NOT a human-verified gold standard and give NO statistical recall.
"""
from __future__ import annotations
import copy,json,tempfile,unittest
from pathlib import Path

from royalty_research.m2_validation import validate_extraction,compare_independent_extractions
from royalty_research.m6_source_risk import source_hits
from royalty_research.m3_workspace import (init,register_map,register_extraction,record_human_review,
                                            list_documents,_document_dir,select_attempt)
from royalty_research.m3_export import build_rows
from royalty_research.storage import read_json

HERE=Path(__file__).parent
F=HERE/'fixtures'/'m6'
MAP=read_json(F/'market_finders_mapped.json')
EXT=read_json(F/'market_finders_extraction.json')
SYNMAP=read_json(HERE.parent/'output'/'synthetic_clause_map.json')
SYNEXT=read_json(HERE.parent/'examples'/'synthetic_m2_extraction.json')

def codes(report):return {v['code'] for v in report['errors']}


class SourceLedgers(unittest.TestCase):
    def test_audit_examination_threshold_not_treated_as_royalty(self):
        from royalty_research.mapping import map_contract
        text='10.2 Books and records: if an error in royalties of more than five percent (5%) of the total royalties is discovered in any examination, Licensee bears the fees.'
        mm=map_contract([text],{'source_url':'https://www.sec.gov/Archives/edgar/data/1/2/a.htm'})
        candidates=[x for x in source_hits(mm) if x['literal']=='5%']
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['risk'],'INVENTORY_ONLY')
    def test_original_reviewed_extraction_passes(self):
        self.assertEqual(validate_extraction(MAP,EXT)['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
    def test_every_hit_is_deterministically_bound(self):
        a=source_hits(MAP);b=source_hits(MAP)
        self.assertEqual(a,b)
        self.assertEqual(len({v['id'] for v in a}),len(a))
        self.assertTrue(any(x['literal']=='1%' and x['risk']=='POTENTIAL_RUNNING_RATE' for x in a))
    def test_market_finders_audit_shortfall_is_not_royalty(self):
        self.assertTrue(any(x['literal']=='5%' and x['risk']=='INVENTORY_ONLY' for x in source_hits(MAP)))
    def test_drop_fourth_tier_and_relabel_unrelated_fails(self):
        x=copy.deepcopy(EXT)
        term=next(t for t in x['royalty_terms'] if len(t['tiers'])==4)
        term['tiers'].pop()
        for d in x['dispositions']:
            for v in d.get('percentage_dispositions',[]):
                if v.get('literal')=='1%' and v.get('classification')=='ROYALTY_RATE':
                    v['classification']='UNRELATED';v['term_id']=None
        r=validate_extraction(MAP,x)
        self.assertIn('SOURCE_RATE_UNACCOUNTED',codes(r))
    def test_entire_running_royalty_removed_fails(self):
        x=copy.deepcopy(EXT)
        x['royalty_terms']=[]
        for d in x['dispositions']:
            if 'ROYALTY_TERM' in d['categories']:
                d['categories']=['BACKGROUND'];d['term_ids']=[]
            for v in d.get('percentage_dispositions',[]):
                if v.get('classification')=='ROYALTY_RATE':
                    v['classification']='UNRELATED';v['term_id']=None
        self.assertIn('SOURCE_RATE_UNACCOUNTED',codes(validate_extraction(MAP,x)))
    def test_removed_minimum_and_cap_payments_flag_source_risk(self):
        x=copy.deepcopy(EXT)
        x['other_payments']=[]
        for d in x['dispositions']:
            d['payment_ids']=[]
            d['categories']=[z for z in d['categories'] if z!='OTHER_PAYMENT'] or ['BACKGROUND']
        self.assertIn('SOURCE_SPECIAL_PAYMENT_UNACCOUNTED',codes(validate_extraction(MAP,x)))
    def test_swapped_rates_are_independently_flagged_in_same_source_paragraph(self):
        # Narrow order-based check is useful but NOT proof of tier semantics;
        # a blind independent read and human acceptance benchmark remain required.
        x=copy.deepcopy(EXT)
        tier=x['royalty_terms'][0]['tiers']
        tier[0]['rate_value'],tier[1]['rate_value']=tier[1]['rate_value'],tier[0]['rate_value']
        first=copy.deepcopy(EXT);first['reader']['engine']='codex';first['reader']['run_id']='another-run'
        self.assertIn('SOURCE_TIER_RATE_ORDER_CONFLICT',codes(validate_extraction(MAP,x)))
        comparison=compare_independent_extractions(MAP,first,x)
        self.assertIn('ECONOMIC_FIELD_MISMATCH',comparison['disagreements'])
        self.assertTrue(any('tiers' in v['field'] for v in comparison['field_differences']))
    def test_extraction_paraphrase_does_not_falsely_count_as_changed_economics(self):
        b=copy.deepcopy(EXT)
        b['reader']['engine']='codex';b['reader']['run_id']='independent-run'
        b['royalty_terms'][0]['base']='Net Sales as defined in the agreement'
        c=compare_independent_extractions(MAP,EXT,b)
        self.assertEqual(c['disagreements'],[])
        self.assertEqual(c['status'],'NO_DETECTED_DISAGREEMENT_NOT_PROOF_OF_ACCURACY')
    def test_gross_sales_claim_conflicts_with_net_sales_source(self):
        b=copy.deepcopy(EXT)
        b['royalty_terms'][0]['base']='Gross Sales'
        self.assertIn('SOURCE_RATE_BASE_CONTRADICTION',codes(validate_extraction(MAP,b)))
    def test_sublicense_family_claim_conflicts_with_sales_source(self):
        b=copy.deepcopy(EXT)
        b['royalty_terms'][0]['family']='SUBLICENSING_RECEIPTS'
        self.assertIn('SOURCE_RATE_FAMILY_CONTRADICTION',codes(validate_extraction(MAP,b)))
    def test_base_change_is_field_disagreement(self):
        b=copy.deepcopy(EXT)
        b['reader']['engine']='codex';b['reader']['run_id']='independent-run'
        b['royalty_terms'][0]['base']='Gross Sales'
        self.assertIn('ECONOMIC_FIELD_MISMATCH',compare_independent_extractions(MAP,EXT,b)['disagreements'])


class WorkspaceNoSilentLoss(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=Path(self.tmp.name);init(self.ws)
        self.m=copy.deepcopy(SYNMAP);self.x=copy.deepcopy(SYNEXT)
        self.m['source_url']='https://www.sec.gov/Archives/edgar/data/1/000000000000000001/fictional.htm'
        self.x['source_url']=self.m['source_url']
        self.x['open_issues'][0]['status']='RESOLVED'
        self.did=self.m['document_id']
        register_map(self.ws,self.m)
        self.info=register_extraction(self.ws,self.did,self.x,select=True)
    def test_no_human_approval_or_workbook_sheet(self):
        self.assertEqual(list_documents(self.ws)[0]['state'],'QC_PASSED_NOT_PROFESSIONALLY_VERIFIED')
        with self.assertRaisesRegex(ValueError,'HUMAN_APPROVAL_DISABLED'):
            record_human_review(self.ws, {})
        self.assertNotIn('Human Reviewed',build_rows(self.ws))
    def test_lost_document_folder_detected(self):
        import shutil
        shutil.rmtree(_document_dir(self.ws,self.did))
        with self.assertRaisesRegex(ValueError,'EXPECTED_DOCUMENT_SET_MISMATCH'):
            list_documents(self.ws)
    def test_selected_pointer_removed_detected(self):
        (_document_dir(self.ws,self.did)/'selected.json').unlink()
        with self.assertRaisesRegex(ValueError,'SELECTED_ATTEMPT_POINTER_MISSING'):
            list_documents(self.ws)
    def test_selected_pointer_swapped_detected(self):
        from royalty_research.storage import atomic_json
        p=_document_dir(self.ws,self.did)/'selected.json'
        obj=read_json(p);obj['extraction_sha256']='0'*64
        atomic_json(p,obj)
        with self.assertRaisesRegex(ValueError,'SELECTED_ATTEMPT_REGISTER_MISMATCH'):
            list_documents(self.ws)
    def test_registry_loss_detected(self):
        (self.ws/'expected_documents.json').unlink()
        with self.assertRaisesRegex(ValueError,'EXPECTED_DOCUMENT_REGISTER_MISSING'):
            list_documents(self.ws)

if __name__=='__main__':unittest.main()
