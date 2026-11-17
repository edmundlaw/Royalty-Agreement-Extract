"""M11 design tests. Synthetic cases are NOT unseen benchmark evidence."""
import copy
import unittest
from royalty_research.mapping import map_contract
from royalty_research.m11_signal_qc import issue_signals,reconcile_signals,build_correction_packet


def base(lines):
    m=map_contract(lines,{'document_id':'DOC-M11','source_url':'https://www.sec.gov/Archives/edgar/data/1/2/sample.htm'})
    e={'document_id':m['document_id'],'source_text_sha256':m['text_sha256'],
       'evidence':[{'evidence_id':f'E{i}','passage_id':p['passage_id'],'quote':p['text']} for i,p in enumerate(m['passages'],1)],
       'royalty_terms':[],'other_payments':[],'open_issues':[]}
    return m,e


def term(tid,rate=None,eid='E1',family='PRODUCT_SALES',tiers=None,adjustments=None,structure='FLAT',redacted=False):
    return {'term_id':tid,'family':family,'structure':structure,'rate_value':rate,
      'disclosure_status':'REDACTED' if redacted else 'DISCLOSED','rate_unit':'REDACTED' if redacted else 'PERCENT',
      'rate_evidence_ids':[eid], 'evidence_ids':[eid], 'tiers':tiers or [], 'adjustments':adjustments or [],'conditions':[]}


def payment(pid,kind,amount,eid,redacted=False):
    return {'payment_id':pid,'kind':kind,'amount_value':amount,'currency':'USD','basis':None,
        'condition':None,'evidence_ids':[eid], 'disclosure_status':'REDACTED' if redacted else 'DISCLOSED'}


def close(m,e, *,mapping=None):
    """Construct only verified, source-cited closures. Does not change extraction."""
    resolutions=[]
    rules=mapping or {}
    for s in issue_signals(m)['signals']:
        details=rules.get(s['signal_id']) or rules.get(s['kind'])
        if details:resolutions.append({'signal_id':s['signal_id'],**details})
    return resolutions


class M11SourceFlags(unittest.TestCase):
    def test_table_header_persists_more_than_seven_rows(self):
        lines=['Article 4 Royalty payments','Annual Net Sales | Royalty Rate']
        lines += [f'Band {i} > ${i*100000:,} | {i}%' for i in range(1,12)]
        m,e=base(lines)
        flags=[x for x in issue_signals(m)['signals'] if x['kind']=='TIER_ROW']
        self.assertEqual(len(flags),11)
        self.assertEqual(reconcile_signals(m,e)['hard_open'],11)

    def test_sales_royalty_table_with_sublicensee_word_stays_product_sales(self):
        m,e=base(['Earned royalty on Net Sales by licensee, affiliates and sublicensees:',
                  'Annual Net Sales | Royalty Rate','Under $500,000 | 6%','Above $500,000 | 4%'])
        flags=[x for x in issue_signals(m)['signals'] if x['kind']=='TIER_ROW']
        self.assertEqual([f['role'] for f in flags],['ROYALTY','ROYALTY'])

    def test_redacted_rows_cannot_be_dismissed_by_issue(self):
        m,e=base(['Sublicense income and consideration royalty shares:',
                  'Sublicense Fees | Royalty Rate','During development | [***]',
                  'After approval | [***]'])
        e['open_issues']=[{'severity':'CRITICAL','passage_ids':[x['passage_id'] for x in m['passages']]}]
        self.assertEqual(reconcile_signals(m,e)['hard_open'],2)
        flags=issue_signals(m)['signals']
        e['royalty_terms']=[term('T',eid='E3',family='SUBLICENSING_RECEIPTS',redacted=True,structure='TIERED',tiers=[
            {'sequence':1,'rate_value':None,'rate_unit':'REDACTED','evidence_ids':['E3'],'lower':None,'upper':None},
            {'sequence':2,'rate_value':None,'rate_unit':'REDACTED','evidence_ids':['E4'],'lower':None,'upper':None}])]
        resolutions=[{'signal_id':s['signal_id'],'resolution':'LINKED_RECORD','record_type':'TIER',
                       'record_id':'T','tier_sequence':i} for i,s in enumerate(flags,1)]
        self.assertEqual(reconcile_signals(m,e,resolutions)['status'],'PASS_SOURCE_FLAGS_ONLY')
        e['royalty_terms'][0]['tiers'].pop()
        self.assertEqual(reconcile_signals(m,e,resolutions)['hard_open'],1)

    def test_sublicensing_rate_not_merged_into_product_sales(self):
        m,e=base(['Sublicensing income payable to Licensor:','Sublicense Fees | Royalty Rate',
                  'Before approval | 25%','After approval | 10%'])
        e['royalty_terms']=[term('SALES',rate='25',eid='E3',tiers=[
            {'sequence':1,'rate_value':'25','rate_unit':'PERCENT','evidence_ids':['E3'],'lower':None,'upper':None}],
            structure='TIERED')]
        flags=issue_signals(m)['signals'];res=close(m,e,mapping={'TIER_ROW':{'resolution':'LINKED_RECORD','record_type':'TIER','record_id':'SALES','tier_sequence':1}})
        self.assertEqual(reconcile_signals(m,e,res)['hard_open'],2)

    def test_numeric_tier_bounds_are_needed(self):
        m,e=base(['Annual royalty on Net Sales:','Net Sales | Royalty Rate','Under $500,000 | 6%'])
        e['royalty_terms']=[term('T',eid='E3',tiers=[{'sequence':1,'rate_value':'6','rate_unit':'PERCENT','evidence_ids':['E3'],'lower':None,'upper':None}],structure='TIERED')]
        s=issue_signals(m)['signals'][0]
        res=[{'signal_id':s['signal_id'],'resolution':'LINKED_RECORD','record_type':'TIER','record_id':'T','tier_sequence':1}]
        self.assertEqual(reconcile_signals(m,e,res)['hard_open'],1)
        e['royalty_terms'][0]['tiers'][0]['upper']='500000'
        self.assertEqual(reconcile_signals(m,e,res)['hard_open'],0)

    def test_unrelated_audit_threshold_requires_typed_explanation(self):
        m,e=base(['Audit: if royalties differ by more than five percent, licensee pays audit costs.'])
        s=issue_signals(m)['signals'][0]
        res=[{'signal_id':s['signal_id'],'resolution':'TYPED_EXPLANATION','reason':'AUDIT_THRESHOLD'}]
        self.assertEqual(reconcile_signals(m,e,res)['status'],'PASS_SOURCE_FLAGS_ONLY')
        res[0]['reason']='OWNERSHIP_PERCENT'
        self.assertEqual(reconcile_signals(m,e,res)['hard_open'],1)

    def test_ownership_word_does_not_excuse_net_sales_rate(self):
        m,e=base(['In lieu of equity, Licensee shall pay Licensor five percent of Net Sales.'])
        s=issue_signals(m)['signals'][0]
        res=[{'signal_id':s['signal_id'],'resolution':'TYPED_EXPLANATION','reason':'OWNERSHIP_PERCENT'}]
        self.assertEqual(reconcile_signals(m,e,res)['hard_open'],1)

    def test_insurance_amount_not_flagged_as_license_payment(self):
        m,e=base(['Licensee shall carry insurance coverage of $1,000,000 and $5,000,000.'])
        self.assertEqual(issue_signals(m)['signals'],[])

    def test_upfront_and_milestones_not_false_pass(self):
        m,e=base(['Initial license fee of $25,000 is due immediately and payable.',
                  'Development milestones of $175,000 and $200,000 are payable.',
                  'Minimum annual royalty of $250,000 is guaranteed.'])
        q=reconcile_signals(m,e)
        self.assertEqual(q['hard_open'],1)
        self.assertEqual(q['warning_open'],3)
        e['other_payments']=[payment('MIN','MINIMUM_ROYALTY','250000','E3')]
        s=next(x for x in issue_signals(m)['signals'] if x['kind']=='MINIMUM_ROYALTY')
        res=[{'signal_id':s['signal_id'],'resolution':'LINKED_RECORD','record_type':'PAYMENT','record_id':'MIN'}]
        self.assertEqual(reconcile_signals(m,e,res)['status'],'INCOMPLETE_SUPPORTING_ECONOMICS')

    def test_kempharm_redacted_milestone_rows_covered_by_null_payments(self):
        m,e=base(['Milestones due under the agreement','Sales milestones | Payment amount',
                  'Approval of first product | [***]','Approval of second product | [***]'])
        flags=issue_signals(m)['signals']
        self.assertEqual(len(flags),2)
        self.assertTrue(all(x['kind']=='PAYMENT_ROW' for x in flags))
        e['other_payments']=[payment('M1','MILESTONE',None,'E3',redacted=True),payment('M2','MILESTONE',None,'E4',redacted=True)]
        res=[{'signal_id':f['signal_id'],'resolution':'LINKED_RECORD','record_type':'PAYMENT','record_id':f'M{i}'} for i,f in enumerate(flags,1)]
        self.assertEqual(reconcile_signals(m,e,res)['status'],'PASS_SOURCE_FLAGS_ONLY')

    def test_redaction_word_no_marker_is_not_economic_flag(self):
        m,e=base(['Licensee may request that patent claims be redacted before disclosure.'])
        self.assertEqual(issue_signals(m)['signals'],[])

    def test_changed_rates_and_stacking_explanations(self):
        m,e=base(['Royalties shall be reduced if aggregate third-party royalties exceed 11% and shall not fall below fifty percent (50%).'])
        e['royalty_terms']=[term('T',eid='E1',adjustments=[{'description':'reduction if third party royalties exceed 11% and floor is 50%','evidence_ids':['E1']}])]
        flags=issue_signals(m)['signals']
        self.assertTrue(flags)
        resolution=[]
        for f in flags:
            if f['kind']=='ADJUSTMENT':
                resolution.append({'signal_id':f['signal_id'],'resolution':'LINKED_RECORD','record_type':'ADJUSTMENT','record_id':'T'})
            else:
                resolution.append({'signal_id':f['signal_id'],'resolution':'TYPED_EXPLANATION',
                                   'reason':'STACKING_THRESHOLD' if f['value']=='11' else 'REDUCTION_FLOOR', 'target_id':'T'})
        self.assertEqual(reconcile_signals(m,e,resolution)['status'],'PASS_SOURCE_FLAGS_ONLY')

    def test_correction_packet_limited_to_open_source_flags(self):
        m,e=base(['Royalty fee shall be 3% of Net Sales.','Initial license fee $20,000 payable.'])
        pkt=build_correction_packet(m,e)
        self.assertEqual(len(pkt['open_flags']),2)
        self.assertNotIn('full_document',pkt)
        self.assertEqual(pkt['maximum_calls_per_document'],1)

    def test_stale_manifest_and_duplicate_closures(self):
        m,e=base(['Royalty fee shall be 3% of Net Sales.'])
        sig=issue_signals(m)
        self.assertEqual(reconcile_signals(m,e,manifest={'bad':'value'})['status'],'FAIL_INTEGRITY')
        s=sig['signals'][0]
        res=[{'signal_id':s['signal_id'],'resolution':'TYPED_EXPLANATION','reason':'AUDIT_THRESHOLD'}]*2
        self.assertEqual(reconcile_signals(m,e,res)['status'],'FAIL_INTEGRITY')

if __name__=='__main__': unittest.main()

class AdditionalAdversarial(unittest.TestCase):
    def test_two_redacted_shares_in_one_paragraph_need_distinct_records(self):
        m,e=base(['Sublicense fee: licensee will share [***]% of upfront sublicense revenue; '
                  'and [***]% of other sublicense income.'])
        flags=[x for x in issue_signals(m)['signals'] if x['kind']=='REDACTED_ECONOMIC']
        self.assertEqual(len(flags),2)
        e['royalty_terms']=[term('T',eid='E1',redacted=True,family='SUBLICENSING_RECEIPTS')]
        answers=[{'signal_id':x['signal_id'],'resolution':'LINKED_RECORD','record_type':'ROYALTY_TERM','record_id':'T'} for x in flags]
        report=reconcile_signals(m,e,answers)
        self.assertEqual(report['hard_open'],2)
        self.assertTrue(any(x['code']=='M11_REDACTED_RECORD_REUSED' for x in report['errors']))

    def test_missing_milestone_amount_remains_visible(self):
        m,e=base(['Sales milestones of $5,000,000 and $10,000,000 are payable.'])
        sigs=issue_signals(m)['signals']
        self.assertEqual(len(sigs),2)
        self.assertEqual(reconcile_signals(m,e)['status'],'INCOMPLETE_SUPPORTING_ECONOMICS')

    def test_audit_word_never_waives_actual_sales_rate(self):
        m,e=base(['Audit appendix: royalties are set at five percent of Net Sales.'])
        flags=issue_signals(m)['signals'];self.assertEqual(len(flags),1)
        res=[{'signal_id':flags[0]['signal_id'],'resolution':'TYPED_EXPLANATION','reason':'AUDIT_THRESHOLD'}]
        self.assertEqual(reconcile_signals(m,e,res)['hard_open'],1)

class MoreM11QC(unittest.TestCase):
    def test_minimum_annual_and_monthly_installment_not_double_counted(self):
        from royalty_research.m11_signal_qc import reconcile_with_proposals
        m,e=base(['Guaranteed Minimum Royalty: licensee owes $300,000 a year ($25,000 per month).'])
        e['other_payments']=[payment('M','MINIMUM_ROYALTY','300000','E1')]
        e['other_payments'][0]['condition']='$25,000 per month is an instalment of the annual minimum'
        q=reconcile_with_proposals(m,e)
        self.assertEqual(q['status'],'PASS_SOURCE_FLAGS_ONLY')
        e['other_payments'][0]['condition']='No amount recorded'
        self.assertEqual(reconcile_with_proposals(m,e)['hard_open'],1)

    def test_flat_rate_rows_do_not_require_tiers(self):
        from royalty_research.m11_signal_qc import reconcile_with_proposals
        m,e=base(['Earned royalty rates under exclusive patent licence:',
                  'Royalty Category | Rate','Patent valid claim | 3%',
                  'Know-how only | 1.5%'])
        e['royalty_terms']=[term('T1','3','E3'),term('T2','1.5','E4')]
        self.assertEqual(reconcile_with_proposals(m,e)['status'],'PASS_SOURCE_FLAGS_ONLY')

    def test_missing_royalty_cap_is_blocking_not_issue_waived(self):
        m,e=base(['Annual royalty cap shall be $1,000,000.'])
        e['open_issues']=[{'severity':'HIGH','passage_ids':[m['passages'][0]['passage_id']]}]
        self.assertEqual(reconcile_signals(m,e)['status'],'INCOMPLETE_CORE_ECONOMICS')
        e['other_payments']=[payment('CAP','CAP','1000000','E1')]
        s=issue_signals(m)['signals'][0]
        res=[{'signal_id':s['signal_id'],'resolution':'LINKED_RECORD','record_type':'PAYMENT','record_id':'CAP'}]
        self.assertEqual(reconcile_signals(m,e,res)['status'],'PASS_SOURCE_FLAGS_ONLY')

    def test_selloff_crossreference_not_a_new_rate_signal(self):
        m,e=base(['After termination, sell-off royalties remain payable as required by Article 4.'])
        self.assertEqual(issue_signals(m)['signals'],[])

class MixedContextRegression(unittest.TestCase):
    def test_audit_explanation_only_closes_audit_percent_in_mixed_clause(self):
        m,e=base(['Licensee shall pay 10% of sublicense fees; audit discrepancy over 5% makes licensee bear costs.'])
        flags=issue_signals(m)['signals'];self.assertEqual(len(flags),2)
        reason={f['value']:'AUDIT_THRESHOLD' for f in flags}
        res=[{'signal_id':f['signal_id'],'resolution':'TYPED_EXPLANATION','reason':reason[f['value']]} for f in flags]
        self.assertEqual(reconcile_signals(m,e,res)['hard_open'],1)
        e['royalty_terms']=[term('SUB',rate='10',eid='E1',family='SUBLICENSING_RECEIPTS')]
        res[0]={'signal_id':flags[0]['signal_id'],'resolution':'LINKED_RECORD','record_type':'ROYALTY_TERM','record_id':'SUB'}
        self.assertEqual(reconcile_signals(m,e,res)['status'],'PASS_SOURCE_FLAGS_ONLY')

    def test_identical_audit_and_royalty_rate_cannot_share_one_record(self):
        m,e=base(['Licensee shall pay 3% of Net Sales; audit threshold is 3% of reported royalties.'])
        flags=issue_signals(m)['signals'];self.assertEqual(len(flags),2)
        e['royalty_terms']=[term('T','3','E1')]
        bad=[{'signal_id':f['signal_id'],'resolution':'LINKED_RECORD','record_type':'ROYALTY_TERM','record_id':'T'} for f in flags]
        self.assertGreater(reconcile_signals(m,e,bad)['hard_open'],0)
        good=[bad[0],{'signal_id':flags[1]['signal_id'],'resolution':'TYPED_EXPLANATION','reason':'AUDIT_THRESHOLD'}]
        self.assertEqual(reconcile_signals(m,e,good)['status'],'PASS_SOURCE_FLAGS_ONLY')
