"""M12 engineering regressions. Saved SEC examples ARE NOT unseen holdouts."""
from __future__ import annotations
import copy, json, unittest
from pathlib import Path
from royalty_research.mapping import map_contract
from royalty_research.m12_economic_qc import (issue_signals, reconcile_signals,
    reconcile_with_proposals, propose_verified_closures, build_correction_packet,
    apply_correction_response)
from royalty_research.m2_validation import validate_extraction

BASE=Path(__file__).resolve().parent/'fixtures'/'m12_saved'

def probe(s):
    return map_contract(s.split('\n'), {'document_id':'PROBE-M12','source_url':'https://www.sec.gov/Archives/edgar/data/1/2/x.htm'})

def pair(n):
    m=json.loads((BASE/(n+'_map.json')).read_text())
    e=json.loads((BASE/(n+'_extraction.json')).read_text())
    m['quality_control_profile']='M12_SOURCE_FLAGS'
    e['m12_manifest_sha256']=issue_signals(m)['manifest_sha256']
    e['m12_resolutions']=propose_verified_closures(m,e)
    return m,e

class SourceDetector(unittest.TestCase):
    def test_caps_minimums_and_fees_without_pay_verb(self):
        cases=[('Royalties shall be limited to $200,000.','CAP','HARD'),
          ('Total royalties shall not exceed $200,000.','CAP','HARD'),
          ('Royalty payments may not exceed $200,000.','CAP','HARD'),
          ('An initial nonrefundable licence fee of $25,000 is payable.','UPFRONT_FEE','WARNING'),
          ('Upon approval of the licensed drug by FDA, a payment of $250,000 becomes due.','MILESTONE','WARNING'),
          ('Annual minimum royalty $100,000 during first two years and $200,000 thereafter.','MINIMUM_ROYALTY','HARD')]
        for text,kind,severity in cases:
            with self.subTest(text=text):
                flags=issue_signals(probe(text))['signals']
                self.assertIn(kind,[f['kind'] for f in flags])
                self.assertTrue(all(f['severity']==severity for f in flags if f['kind']==kind))
    def test_per_unit_and_indirect_redaction(self):
        for s in ('Licensee shall remit $2.50 for each Licensed Product sold.',
          'Licensee will pay a royalty of $2.50 per Licensed Product unit sold.'):
            self.assertIn('PER_UNIT_RATE',[f['kind'] for f in issue_signals(probe(s))['signals']])
        self.assertIn('REDACTED_ECONOMIC',[f['kind'] for f in issue_signals(probe(
          'For each Licensed Product sold, Licensee will remit [***] of net revenue.'))['signals']])
    def test_written_numbers_coalesced_only_when_exact_parenthetical(self):
        cases=[('Licensee pays three percent (3%) of Net Sales.',1),
               ('Licensee pays twenty-two percent of Net Sales.',1),
               ('Licensee pays two and one-half percent of Net Sales.',1),
               ('Licensee pays 3% of Net Sales; audit over 3% is reimbursable.',2)]
        for s,expected in cases:
            with self.subTest(s=s):
                self.assertEqual(len(issue_signals(probe(s))['signals']),expected)
    def test_mixed_role_and_no_blanket_equity_exemption(self):
        m=probe('In lieu of equity, Licensee shall pay Licensor five percent of Net Sales.')
        self.assertTrue(any(x['kind']=='RATE' for x in issue_signals(m)['signals']))
        m=probe('The late payment rate is 3% but the licensee pays a royalty of 3% of Net Sales.')
        kinds=[x['kind'] for x in issue_signals(m)['signals']]
        self.assertEqual(kinds.count('RATE'),1)
        self.assertEqual(kinds.count('NON_ECONOMIC_PERCENT'),1)
        m=probe('The running royalty is 3% of Net Sales; an audit discrepancy of 3% incurs a charge.')
        self.assertEqual([x['kind'] for x in issue_signals(m)['signals']].count('RATE'),1)
    def test_redaction_word_in_unrelated_text_not_royalty(self):
        self.assertEqual(issue_signals(probe('Licensee may request patent claims be redacted.'))['signals'],[])
    def test_long_pipe_tables_all_rows_including_redacted(self):
        lines=['Annual sales royalty shall be according to these tiers:', 'Net Sales | Royalty Rate']
        lines += [f'${i*1000:,} to ${(i+1)*1000:,} | [***]' for i in range(12)]
        flags=[x for x in issue_signals(probe('\n'.join(lines)))['signals'] if x['kind']=='TABLE_ROW']
        self.assertEqual(len(flags),12)
        self.assertTrue(all(x['detail']['redacted'] for x in flags))
        self.assertEqual(len({x['passage_id'] for x in flags}),12)
    def test_separate_cell_table_detects_all_rows(self):
        m=probe('\n'.join(['Sublicense fee schedule','Percentage','Aggregate Sublicense Fees',
          '25%','Below $250,000','10%','$250,000 to $2,000,000','5%','Above $2,000,000']))
        rows=[f for f in issue_signals(m)['signals'] if f['kind']=='TABLE_ROW']
        self.assertEqual(len(rows),3)
        self.assertEqual(len({f['passage_id'] for f in rows}),3)
        self.assertTrue(all(len(f['related_passage_ids'])==1 for f in rows))

class RealSavedRegressions(unittest.TestCase):
    def test_four_saved_real_extractions_have_no_qc_false_fail(self):
        for n in ('MarketFinders','NeurogesX','Kirklands','Qualigen'):
            with self.subTest(name=n):
                m,e=pair(n)
                q=validate_extraction(m,e)
                self.assertEqual(q['errors'],[],q['errors'][:4])
                self.assertEqual(q['m12_source_flags']['hard_open'],0)
                self.assertEqual(q['m12_source_flags']['warning_open'],0)
                self.assertEqual(q['deterministic_status'],'PASS_DETERMINISTIC_ONLY')
    def test_deliberate_missing_royalties_caps_minimums_and_fees(self):
        mutations=[('MarketFinders','tier'),('MarketFinders','cap'),('MarketFinders','minimum'),
          ('NeurogesX','sublicense'),('NeurogesX','cap'),('NeurogesX','minimum'),
          ('Kirklands','stepup'),('Kirklands','minimum'),('Qualigen','upfront'),('Qualigen','running')]
        for n,kind in mutations:
            with self.subTest(n=n,kind=kind):
                m,e=pair(n);old=reconcile_with_proposals(m,e)
                x=copy.deepcopy(e)
                if kind=='tier':x['royalty_terms'][0]['tiers'].pop()
                if kind=='cap':x['other_payments']=[p for p in x['other_payments'] if p['kind']!='CAP']
                if kind=='minimum':x['other_payments']=[p for p in x['other_payments'] if p['kind']!='MINIMUM_ROYALTY']
                if kind=='sublicense':x['royalty_terms']=[t for t in x['royalty_terms'] if t['family']!='SUBLICENSING_RECEIPTS']
                if kind=='stepup':x['royalty_terms'][0]['tiers']=x['royalty_terms'][0]['tiers'][:1]
                if kind=='upfront':x['other_payments']=[p for p in x['other_payments'] if p['kind']!='UPFRONT']
                if kind=='running':x['royalty_terms']=[t for t in x['royalty_terms'] if t['family']!='PRODUCT_SALES']
                q=reconcile_with_proposals(m,x)
                self.assertGreater(q['hard_open']+q['warning_open'],old['hard_open']+old['warning_open'])
    def test_open_issue_cannot_waive_redacted_economics(self):
        m=probe('Sublicensing proceeds: Licensee shall share [***]% of signing fees and [***]% of other sublicense income.')
        e={'document_id':m['document_id'],'source_text_sha256':m['text_sha256'],
           'royalty_terms':[],'other_payments':[],'evidence':[],
           'open_issues':[{'severity':'CRITICAL','passage_ids':[m['passages'][0]['passage_id']]}]}
        self.assertGreater(reconcile_with_proposals(m,e)['hard_open'],0)
    def test_stale_manifest_source_mismatch_is_not_approved(self):
        m,e=pair('NeurogesX')
        e['source_text_sha256']='0'*64
        self.assertEqual(reconcile_with_proposals(m,e)['status'],'FAIL_INTEGRITY')

class Corrections(unittest.TestCase):
    def test_one_correction_packet_binds_source_and_attempt(self):
        m,e=pair('Qualigen')
        x=copy.deepcopy(e);x['other_payments']=[p for p in x['other_payments'] if p['kind']!='UPFRONT']
        pkt=build_correction_packet(m,x)
        self.assertTrue(pkt['correction_ready'])
        self.assertEqual(pkt['all_open_signal_count'],1)
        with self.assertRaisesRegex(ValueError,'Correction packet'):
            apply_correction_response(m,x,dict(pkt,task_sha256='wrong'),{'schema':'m12-correction-response.1'})
        with self.assertRaisesRegex(ValueError,'Empty correction'):
            apply_correction_response(m,x,pkt,{'schema':'m12-correction-response.1','task_sha256':pkt['task_sha256']})

if __name__=='__main__':unittest.main()

class MoreM12Adversarial(unittest.TestCase):
    def test_two_identical_rates_for_distinct_products_cannot_share_one_record(self):
        from tests.test_m11 import term
        m=probe('Licensed Product A carries 3% of Net Sales; Licensed Product B carries 3% of Net Sales.')
        ev={'evidence_id':'E1','passage_id':m['passages'][0]['passage_id'],'quote':m['passages'][0]['text']}
        e={'document_id':m['document_id'],'source_text_sha256':m['text_sha256'],'evidence':[ev],
           'royalty_terms':[term('T',rate='3',eid='E1')],'other_payments':[],'open_issues':[]}
        q=reconcile_with_proposals(m,e)
        self.assertGreater(q['hard_open'],0)
        self.assertTrue(any(x['code']=='M12_DISTINCT_RATE_OCCURRENCES_REUSED' for x in q['errors']))
    def test_no_generic_open_issue_can_clear_redacted_payment(self):
        m=probe('Licensee shall pay the minimum annual royalty of [***] in Year 1.')
        e={'document_id':m['document_id'],'source_text_sha256':m['text_sha256'],
           'evidence':[],'royalty_terms':[],'other_payments':[],
           'open_issues':[{'severity':'CRITICAL','description':'All rates redacted','passage_ids':[m['passages'][0]['passage_id']]}]}
        q=reconcile_with_proposals(m,e)
        self.assertGreater(q['hard_open'],0)


class AdditionalPaymentLanguage(unittest.TestCase):
    def test_triggered_fee_without_milestone_word(self):
        examples=(
            "On commercialization, Licensee owes $250,000.",
            "Upon first commercial sale, a $500,000 payment becomes due.",
            "Upon launch of Licensed Product, the payment is $100,000.",
        )
        for clause in examples:
            with self.subTest(clause=clause):
                issued=issue_signals(probe(clause))['signals']
                self.assertIn('MILESTONE',[x['kind'] for x in issued])
                self.assertTrue(any(x['severity']=='WARNING' for x in issued))
