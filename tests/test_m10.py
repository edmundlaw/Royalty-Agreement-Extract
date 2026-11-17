"""M10 generalized source obligations; synthetic fixtures, not a recall benchmark."""
import copy
import unittest
from royalty_research.mapping import map_contract
from royalty_research.m10_obligation_gate import check_source_obligations
from royalty_research.m7_occurrences import issue_occurrences
from royalty_research.m7_ledger_tasks import prepare_ledger_tasks, merge_ledger_chunks


def mk(lines):
    m=map_contract(lines,{'document_id':'M10-SYN','source_url':'https://www.sec.gov/Archives/edgar/data/1/2/sample.htm'})
    evidence=[{'evidence_id':f'E{i+1}','passage_id':p['passage_id'],'quote':p['text']}
              for i,p in enumerate(m['passages'])]
    return m,evidence


def blank(evidence):return {'evidence':evidence,'royalty_terms':[],'other_payments':[],'open_issues':[]}


def term(tid,family, eids, tiers=None, rate=None, conditions=None):
    return {'term_id':tid,'family':family,'rate_value':rate,'rate_evidence_ids':eids,
            'tiers':tiers or [],'conditions':conditions or [],'adjustments':[]}


class SourceIndependentSignals(unittest.TestCase):
    def codes(self,m,e):return {x['code'] for x in check_source_obligations(m,e)['errors']}

    def test_band_first_percent_last_table_and_omission(self):
        m,ev=mk(['5.2 Royalties. Licensee shall pay net-sales royalties according to the following royalty rate table:',
                 'Sales amount | Royalty Rate',
                 'Not more than $500,000 | Six percent (6%)',
                 'Between $500,000 and $1,000,000 | Eight percent (8%)',
                 'Over $1,000,000 | Ten percent (10%)'])
        e=blank(ev)
        self.assertEqual(sum(t['type']=='CONTEXTUAL_RATE_TABLE_ROW' for t in check_source_obligations(m,e)['tested']),3)
        self.assertIn('M10_TIER_ROW_MISSING',self.codes(m,e))
        e['royalty_terms']=[term('T','PRODUCT_SALES',['E1'],[
            {'rate_value':r,'rate_unit':'PERCENT','evidence_ids':[f'E{i}']}
            for i,r in [(3,'6'),(4,'8'),(5,'10')]])]
        self.assertNotIn('M10_TIER_ROW_MISSING',self.codes(m,e))
        e['royalty_terms'][0]['tiers'].pop()
        self.assertIn('M10_TIER_ROW_MISSING',self.codes(m,e))

    def test_redacted_table_each_row_requires_one_linked_tier(self):
        m,ev=mk(['7.6 Earned Royalty. Licensee shall pay earned royalties on annual Net Sales:',
                 'Annual Net Sales | Royalty Percentage',
                 '< USD [**] | [**] percent ([**]%)',
                 '> USD [**] < USD [**] | [**] percent ([**]%)',
                 'Above USD [**] | [**] percent ([**]%)'])
        e=blank(ev)
        out=check_source_obligations(m,e)
        self.assertEqual(len([t for t in out['tested'] if t['type']=='CONTEXTUAL_RATE_TABLE_ROW']),3)
        self.assertEqual(len([a for a in out['errors'] if a['code']=='M10_TIER_ROW_MISSING']),3)
        e['royalty_terms']=[term('T','PRODUCT_SALES',['E1'],[
            {'rate_value':None,'rate_unit':'REDACTED','evidence_ids':[f'E{i}']}
            for i in (3,4,5)])]
        self.assertFalse(check_source_obligations(m,e)['errors'])
        e['royalty_terms'][0]['tiers'][1]['rate_value']='7'
        self.assertIn('M10_REDACTED_TIER_UNACCOUNTED',self.codes(m,e))

    def test_fee_first_sublicense_and_no_waiver_by_open_issue(self):
        m,ev=mk(['4.6 Sharing of Nonroyalty Sublicensing Consideration. Licensee shall pay a portion of sublicense income:',
                 '(A) | Sublicense before milestone: [**]% of Nonroyalty Sublicensing Consideration',
                 '(B) | Sublicense after milestone: [**]% of Nonroyalty Sublicensing Consideration'])
        e=blank(ev);e['open_issues']=[{'severity':'HIGH','status':'OPEN','passage_ids':[x['passage_id'] for x in m['passages']]}]
        self.assertIn('M10_TIER_ROW_MISSING',self.codes(m,e))

    def test_step_up_minimums_and_installment_not_separate_obligation(self):
        m,ev=mk(['Royalties. Licensee shall pay a royalty of three percent (3%) of Net Sales which shall increase to five percent (5%) after termination.',
                 'Guaranteed Minimum Royalty. Licensee shall pay $200,000 during the first 24 months and $300,000 per year thereafter ($25,000 per month).',
                 'Audit. If the payment discrepancy exceeds four percent (4%), Licensee shall pay the inspection cost.'])
        e=blank(ev)
        self.assertIn('M10_EXPLICIT_RATE_MISSING',self.codes(m,e))
        self.assertIn('M10_SPECIAL_PAYMENT_AMOUNT_MISSING',self.codes(m,e))
        e['royalty_terms']=[term('T','PRODUCT_SALES',['E1'],[
            {'rate_value':'3','evidence_ids':['E1']},{'rate_value':'5','evidence_ids':['E1']}])]
        e['royalty_terms'][0]['adjustments']=[{'description':'Step-up from 3% to 5%','evidence_ids':['E1']}]
        e['other_payments']=[{'payment_id':'P1','kind':'MINIMUM_ROYALTY','amount_value':'200000','evidence_ids':['E2']},
                             {'payment_id':'P2','kind':'MINIMUM_ROYALTY','amount_value':'300000','basis':'$25,000 per month','evidence_ids':['E2']}]
        self.assertFalse(check_source_obligations(m,e)['errors'])
        e['royalty_terms'][0]['tiers'].pop()
        self.assertIn('M10_CHANGED_RATE_NOT_STRUCTURED',self.codes(m,e))
        e['royalty_terms'][0]['tiers'].append({'rate_value':'5','evidence_ids':['E1']})
        e['other_payments']=[]
        self.assertIn('M10_SPECIAL_PAYMENT_MISSING',self.codes(m,e))

    def test_upfront_fee_removed_and_equity_spelled_rate(self):
        m,ev=mk(['4.1 Upfront Fee. Licensee shall pay to Licensor $1,000,000 in cash within 30 days.',
                 'In lieu of equity, Licensee shall pay Licensor five percent of Net Sales.'])
        e=blank(ev)
        c=self.codes(m,e)
        self.assertIn('M10_SPECIAL_PAYMENT_AMOUNT_MISSING',c)
        self.assertIn('M10_EXPLICIT_RATE_MISSING',c)
        e['other_payments']=[{'payment_id':'P','kind':'UPFRONT','amount_value':'1000000','evidence_ids':['E1']}]
        e['royalty_terms']=[term('T','PRODUCT_SALES',['E2'],rate='5')]
        self.assertFalse(check_source_obligations(m,e)['errors'])
        e['royalty_terms'][0]['family']='SUBLICENSING_RECEIPTS'
        self.assertIn('M10_RATE_FAMILY_CONTRADICTION',self.codes(m,e))

    def test_equity_interest_and_audit_are_not_automatic_royalties(self):
        m,ev=mk(['Stockholders | Equity Percentage','Investor A | 30%','Investor B | 70%',
                 'Interest on late payment will accrue at five percent (5%) annually.',
                 'Audit shortfall exceeding ten percent (10%) shifts inspection costs to Licensee.'])
        self.assertFalse(check_source_obligations(m,blank(ev))['errors'])

    def test_unquantified_passthrough_not_silently_ignored(self):
        m,ev=mk(['Under the existing License Agreement, Licensee shall pay all running royalties and annual minimum payments as and when required by that agreement.'])
        e=blank(ev)
        self.assertIn('M10_INDIRECT_OBLIGATION_MISSING',self.codes(m,e))
        e['royalty_terms']=[term('PASS','OTHER',['E1'],rate=None)]
        e['royalty_terms'][0]['evidence_ids']=['E1']
        self.assertNotIn('M10_INDIRECT_OBLIGATION_MISSING',self.codes(m,e))

    def test_redacted_conditional_adjustment_is_not_tier(self):
        m,ev=mk(['5.2 Royalties. Licensee will pay net sales royalty rates as stated in the following table.',
                 'Sales tier | Royalty Rate',
                 'Under $1 million | Five percent (5%)',
                 '(c) | If a third-party license is required, the royalties due to Licensor shall be reduced by [**]%'])
        e=blank(ev)
        tested=check_source_obligations(m,e)['tested']
        self.assertEqual(len([x for x in tested if x['type']=='CONTEXTUAL_RATE_TABLE_ROW']),1)
        self.assertIn('M10_ADJUSTMENT_MISSING',self.codes(m,e))
        e['royalty_terms']=[term('T','PRODUCT_SALES',['E3'],[{'rate_value':'5','evidence_ids':['E3']}])]
        e['royalty_terms'][0]['adjustments']=[{'description':'Redacted third-party royalty deduction','evidence_ids':['E4']}]
        self.assertFalse(check_source_obligations(m,e)['errors'])

    def test_no_broad_issue_excuses_minimum(self):
        m,ev=mk(['Licensee shall pay an annual minimum royalty of $10,000.'])
        e=blank(ev);e['open_issues']=[{'severity':'HIGH','status':'OPEN','passage_ids':[m['passages'][0]['passage_id']]}]
        self.assertIn('M10_SPECIAL_PAYMENT_AMOUNT_MISSING',self.codes(m,e))


class RedactionEfficiency(unittest.TestCase):
    def test_redaction_markers_do_not_require_240_model_classifications(self):
        lines=['Earned Royalties shall be payable on Net Sales','Net Sales | Royalty Rate']
        lines+=['< USD [**] | [**] percent ([**]%)']*6
        lines+=['Additional redacted provision [**]']*240
        m,ev=mk(lines)
        x={'document_id':m['document_id'],'source_text_sha256':m['text_sha256'],
           'royalty_terms':[],'other_payments':[],'evidence':[]}
        h=issue_occurrences(m)
        self.assertGreater(sum(i['kind']=='REDACTION' for i in h['occurrences']),240)
        tasks=prepare_ledger_tasks(m,x,max_chars=4500)
        self.assertTrue(all(item['kind']!='REDACTION' for t in tasks for item in t['items']))
        self.assertLess(len(tasks),5)
        # A saved extractor with no royalty tiers remains rejected by M10.
        self.assertIn('M10_TIER_ROW_MISSING',
                      {e['code'] for e in check_source_obligations(m,x)['errors']})

    def test_all_redactions_auto_disposed_and_still_source_bound(self):
        m,ev=mk(['This clause is [**].','Another clause is [**].'])
        x={'document_id':m['document_id'],'source_text_sha256':m['text_sha256'],
           'royalty_terms':[],'other_payments':[],'evidence':[]}
        tasks=prepare_ledger_tasks(m,x)
        self.assertEqual(tasks,[])
        z=merge_ledger_chunks(m,x,[],tasks=[])
        self.assertEqual(z['automatically_preserved_redactions'],2)
        self.assertEqual(len(z['occurrence_dispositions']),len(issue_occurrences(m)['occurrences']))
        self.assertTrue(all(q['classification']=='REDACTION' for q in z['occurrence_dispositions']))


if __name__=='__main__':unittest.main()
