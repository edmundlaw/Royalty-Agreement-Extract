"""Regression tests for M13 research export and optional licensing fields."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from royalty_research.m13_two_reader import source_check
from royalty_research.storage import read_json
from royalty_research.m13_research_export import NAMES, research_rows, write_research_xlsx, benchmark_usable
from royalty_research.m3_export import HEADERS

ROOT=Path(__file__).resolve().parents[1]


def fixture_rows():
    rows={name:[list(cols)] for name, cols in HEADERS.items()}
    did='DOC-DEMO'
    def add(name,values):
        cols=rows[name][0]
        rows[name].append([values.get(k) for k in cols])
    add('Documents',dict(Document_ID=did, Agreement_ID='AGR',Licensed_IP='Registered patent for X',
                         Exclusivity='Non-exclusive', Industry='Technology',Source_URL='https://www.sec.gov/Archives/demo',
                         Effective='2026-01-01', Extraction_Status='TWO_READERS_DIFFER',
                         Second_AI_Review_Status='1 core difference', Licensor='Alpha',Licensee='Beta'))
    add('Royalty Terms',dict(Observation_ID='DOC-DEMO:R1',Document_ID=did,Agreement_ID='AGR',
                             Term_ID='R1',Family='PRODUCT_SALES', Structure='FLAT',Rate_Numeric=3.5,
                             Rate_Unit='PERCENT',Royalty_Base='Net Sales',Product_Scope='Product X',
                             Rate_Evidence_IDs='E1',Evidence_IDs='E1',Source_URL='https://www.sec.gov/Archives/demo',
                             Disclosure_Status='DISCLOSED',QC_State='TWO_READERS_DIFFER'))
    add('Tiers',dict(Observation_ID='DOC-DEMO:R1',Document_ID=did, Term_ID='R1', Sequence=1,
                     Rate_Value_Text='3.5',Rate_Numeric=3.5,Rate_Unit='PERCENT',
                     Lower_Threshold_Text='0',Upper_Threshold_Text='100000',
                     Evidence_IDs='E1',QC_State='TWO_READERS_DIFFER'))
    add('Other Payments',dict(Payment_ID='P1',Document_ID=did,Kind='UPFRONT',Amount_Text='250000',Amount_Numeric=250000,
                              Currency='USD',Evidence_IDs='E2',Source_URL='https://www.sec.gov/Archives/demo'))
    add('Evidence',dict(Document_ID=did,Evidence_ID='E1',Role='RATE',Passage_ID='P12',
                        Exact_Quotation='3.5 percent of Net Sales',Source_URL='https://www.sec.gov/Archives/demo'))
    add('Evidence',dict(Document_ID=did,Evidence_ID='E2',Role='PAYMENT',Passage_ID='P13',
                        Exact_Quotation='a signing payment of USD 250,000',Source_URL='https://www.sec.gov/Archives/demo'))
    add('Conditions',dict(Document_ID=did,Term_ID='R1', Condition_Text='Applies in Product X territory',Evidence_IDs='E1'))
    add('Adjustments',dict(Document_ID=did,Term_ID='R1', Adjustment_Description='Annual reset',Evidence_IDs='E1'))
    add('Open Issues',dict(Document_ID=did,Issue_ID='I1',Severity='MEDIUM',Kind='UNKNOWN_RENEWAL',Description='Renewal not determined'))
    rows['Reader Check']=[['Document_ID','State','Meaning','What_To_Do','First_Reader','Second_Reader','Facts_Both_Readers_Recorded','Source_URL'],
                          [did,'TWO_READERS_DIFFER','Discrepancy','Review','Sonnet','Codex',1,'https://www.sec.gov/Archives/demo']]
    rows['Reader Differences']=[['Document_ID','Level','Value','What_Differs','First_Reader','Second_Reader','Passage_ID','Section','Source_Excerpt','Source_URL'],
                               [did,'CORE','3.5%','Rate mismatch','3.5','4.0','P12','5.1','3.5 percent of Net Sales','https://www.sec.gov/Archives/demo']]
    return rows


class ResearchRows(unittest.TestCase):
    def test_legacy_fields_not_invented_and_all_records_preserved(self):
        raw=fixture_rows(); v=research_rows(raw)
        self.assertEqual(list(v),list(NAMES))
        self.assertEqual([len(v[n])-1 for n in NAMES],[1,3,1,2,3,0])
        row=dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        self.assertEqual(row['Nature of IA'],'NOT_ASSESSED')
        self.assertEqual(row['Sublicensing rights'],'NOT_ASSESSED')
        self.assertEqual(row['Royalty rate (%)'],3.5)
        self.assertEqual(row['Exclusivity'],'Non-exclusive')
        self.assertEqual(row['Royalty base'],'Net Sales')
        self.assertEqual(row['Rate evidence ID'],'E1')
        self.assertEqual([x[0] for x in v[NAMES[1]][1:]],['TIER','CONDITION','ADJUSTMENT'])
        self.assertEqual(v[NAMES[2]][1][3],250000)
        self.assertEqual(v[NAMES[4]][2][2],'CORE')
        self.assertEqual(len(raw['Evidence'])-1,2)  # legacy rows never changed

    def test_new_optional_metadata_is_visible_with_its_citations(self):
        raw=fixture_rows()
        extraction={'agreement':{'licensed_ip_nature':'PATENT','sublicensing_rights':'Requires prior written consent',
                       'field_evidence':{'licensed_ip_nature':['E1'],'sublicensing_rights':['E2']},
                       'other_material_terms':[{'category':'TERMINATION','text':'Termination for cause','evidence_ids':['E2']}]}}
        v=research_rows(raw,{'DOC-DEMO':extraction})
        row=dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        self.assertEqual(row['Nature of IA'],'PATENT')
        self.assertIn('Requires prior written consent',row['Sublicensing rights'])
        self.assertEqual(row['Other material terms'],'TERM/TERMINATION (1 key term) \u2013 see sheet 06; 1 condition(s), 1 adjustment(s) \u2013 see sheet 02')
        t6=v[NAMES[5]]
        self.assertEqual(len(t6)-1,1)
        self.assertEqual(dict(zip(t6[0],t6[1]))['Text'],'Termination for cause')
        self.assertEqual(row['IA evidence IDs'],'E1')
        self.assertEqual(row['Sublicensing evidence IDs'],'E2')

    @staticmethod
    def _with_state(raw,state):
        for sheet,col in (('Documents','Extraction_Status'),('Royalty Terms','QC_State'),('Tiers','QC_State')):
            c=raw[sheet][0].index(col)
            for r in raw[sheet][1:]:r[c]=state
        return raw

    def _hint_row(self,agreement,texts,status=None,source=None,state='SINGLE_READER_NOT_CHECKED',errors=None):
        raw=self._with_state(fixture_rows(),state)
        ev=raw['Evidence'];i=ev[0].index('Exact_Quotation')
        for r in ev[1:]:r[i]=texts.pop(0) if texts else r[i]
        if status:raw['Documents'][1][raw['Documents'][0].index('Contract_Status')]=status
        v=research_rows(raw,{'DOC-DEMO':{'agreement':agreement}},source,errors)
        return dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))

    def test_ia_nature_inferred_and_keyword_hint_never_override_reader(self):
        r=self._hint_row({'licensed_ip_nature':'PATENT','licensed_ip_nature_basis':'INFERRED','field_evidence':{'licensed_ip_nature':['E1']}},[])
        self.assertEqual(r['Nature of IA'],'PATENT (inferred)')
        r=self._hint_row({'licensed_ip_nature':'UNDETERMINED','field_evidence':{'duration':['E1']}},['until expiry of the patents worldwide'])
        self.assertEqual(r['Nature of IA'],'PATENT (keyword hint)')
        self.assertIn("'patents'",r['IA classification detail'])
        r=self._hint_row({'licensed_ip_nature':'TRADEMARK_BRAND','field_evidence':{'duration':['E1']}},['patent expiry'])
        self.assertEqual(r['Nature of IA'],'TRADEMARK_BRAND')
        r=self._hint_row({'licensed_ip_nature':'UNDETERMINED','field_evidence':{'duration':['E1','E2']}},['patent expiry','software and trade secrets'])
        self.assertTrue(r['Nature of IA'].startswith('MIXED'))

    def test_related_party_and_benchmark_rules(self):
        r=self._hint_row({'related_party':'YES'},[])
        self.assertEqual((r['Related party'],r['Usable for royalty benchmark']),('YES','NO'))
        r=self._hint_row({'related_party':'NOT_STATED'},[])
        self.assertEqual((r['Related party'],r['Usable for royalty benchmark']),('NOT_STATED','YES'))
        r=self._hint_row({'licensor':'A'},[],source={'DOC-DEMO':['This is a related-party transaction.']})
        self.assertTrue(r['Related party'].startswith('YES (keyword hint'))
        r=self._hint_row({'licensor':'A'},[],source={'DOC-DEMO':['This is not a related-party transaction.']})
        self.assertEqual(r['Related party'],'NOT_ASSESSED')
        r=self._hint_row({'related_party':'NOT_STATED'},[],status='Signed binding term sheet')
        self.assertEqual(r['Usable for royalty benchmark'],'NO');self.assertIn('term sheet',r['Benchmark note'])

    def test_qc_state_matrix_for_benchmark_flag(self):
        expected={'SOURCE_CHECK_FAILED':'NO','SECOND_READER_FAILED_SOURCE_CHECK':'NO','TWO_READERS_DIFFER':'NO',
                  'TWO_READERS_AGREE_ON_NUMBERS':'YES','TWO_READERS_AGREE':'YES','SINGLE_READER_NOT_CHECKED':'YES'}
        for state,flag in expected.items():
            r=self._hint_row({'related_party':'NOT_STATED'},[],state=state)
            self.assertEqual(r['Usable for royalty benchmark'],flag,state)
            if flag=='NO':self.assertTrue(r['Benchmark note'].startswith('needs review: '+state),r['Benchmark note'])
        r=self._hint_row({'related_party':'NOT_STATED'},[],state='TWO_READERS_AGREE_ON_NUMBERS')
        self.assertIn('STRUCTURE',r['Benchmark note'])
        r=self._hint_row({'related_party':'NOT_STATED'},[],state='SINGLE_READER_NOT_CHECKED')
        self.assertEqual(r['Benchmark note'],'No exclusion rule triggered; still confirm at point of use')
        # needs-review reason comes first even when other reasons exist
        r=self._hint_row({'related_party':'YES'},[],state='SOURCE_CHECK_FAILED')
        self.assertTrue(r['Benchmark note'].startswith('needs review: SOURCE_CHECK_FAILED; '))

    def test_record_level_source_error_forces_no_only_on_its_row(self):
        err=[{'code':'M13_RATE_NOT_IN_QUOTE','message':'x','ref':'R1:tier1'}]
        r=self._hint_row({'related_party':'NOT_STATED'},[],errors={'DOC-DEMO':err})
        self.assertEqual(r['Usable for royalty benchmark'],'NO')
        self.assertIn('M13_RATE_NOT_IN_QUOTE',r['Benchmark note'])
        other=[{'code':'M13_RATE_NOT_IN_QUOTE','message':'x','ref':'R10'},{'code':'M13_NOT_FULL_READ','message':'x','ref':None}]
        r=self._hint_row({'related_party':'NOT_STATED'},[],errors={'DOC-DEMO':other})
        self.assertEqual(r['Usable for royalty benchmark'],'YES')   # R10 is not R1; document-level error has no row

    def test_unconditional_is_not_conditional(self):
        term={'Rate_Numeric':3.5,'Rate_Unit':'PERCENT','Family':'PRODUCT_SALES','Disclosure_Status':'DISCLOSED'}
        for text,flag in (('Unconditional and binding license agreement','YES'),('unconditional','YES'),('Binding license agreement','YES'),
                          ('Non-binding term sheet','NO'),('nonbinding','NO'),('Conditional license','NO'),
                          ('Agreement is conditional on closing','NO'),('Subject to the satisfaction of certain conditions','NO')):
            self.assertEqual(benchmark_usable(term,'NOT_STATED',text)[0],flag,text)

    def test_payment_summary_keeps_four_distinct_categories_and_source_ids(self):
        raw=fixture_rows()
        headers=raw['Other Payments'][0]
        def add(**kw): raw['Other Payments'].append([kw.get(k) for k in headers])
        add(Payment_ID='P2',Document_ID='DOC-DEMO',Kind='ADVANCE',Amount_Text='50000',Currency='USD',
            Basis='Creditable against future royalties; payable upon execution',Evidence_IDs='E1')
        add(Payment_ID='P3',Document_ID='DOC-DEMO',Kind='MINIMUM_ROYALTY',Amount_Text='100000',Currency='USD',
            Basis='Minimum royalty each year',Evidence_IDs='E1')
        add(Payment_ID='P4',Document_ID='DOC-DEMO',Kind='CAP',Amount_Text='500000',Currency='USD',
            Basis='Cap on total royalties',Evidence_IDs='E1')
        add(Payment_ID='P5',Document_ID='DOC-DEMO',Kind='GUARANTEE',Amount_Text='250000',Currency='USD',
            Basis='Performance guarantee unrelated to minimum royalty',Evidence_IDs='E1')
        add(Payment_ID='P6',Document_ID='DOC-DEMO',Kind='OTHER',Amount_Text='20000',Currency='USD',
            Basis='Separate deferred installment of advance',Evidence_IDs='E1')
        add(Payment_ID='P7',Document_ID='DOC-DEMO',Kind='GUARANTEE',Amount_Text='30000',Currency='USD',
            Basis='Annual minimum marketing expenditure',Evidence_IDs='E1')
        add(Payment_ID='P8',Document_ID='DOC-DEMO',Kind='GUARANTEE',Amount_Text='40000',Currency='USD',
            Basis='Minimum guarantee of share price',Evidence_IDs='E1')
        v=research_rows(raw)
        row=dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        self.assertEqual(row['Upfront fee'],'USD 250,000 [P1]')
        self.assertEqual(row['Advance / prepayment'],'USD 50,000 [P2]')
        self.assertEqual(row['Minimum guarantee'],'USD 100,000 [P3]')
        self.assertEqual(row['Royalty cap'],'USD 500,000 [P4]')
        self.assertNotIn('P2',row['Upfront fee']) # signing advance cannot be counted twice
        self.assertNotIn('P5',row['Minimum guarantee']) # unrelated guarantee is not minimum royalty
        self.assertNotIn('P6',row['Advance / prepayment']) # do not guess OTHER's accounting
        self.assertIn('ADVANCE:P2:E1',row['Payment source IDs'])
        self.assertEqual(len(v[NAMES[2]])-1,8) # original detail unaffected

    def test_json_evidence_ids_link_quotes_and_records(self):
        raw=fixture_rows()
        raw['Royalty Terms'][1][raw['Royalty Terms'][0].index('Rate_Evidence_IDs')]='["E1"]'
        raw['Other Payments'][1][raw['Other Payments'][0].index('Evidence_IDs')]='["E2"]'
        out=research_rows(raw)
        main=dict(zip(out[NAMES[0]][0],out[NAMES[0]][1]))
        payment=dict(zip(out[NAMES[2]][0],out[NAMES[2]][1]))
        evidence=dict(zip(out[NAMES[3]][0],out[NAMES[3]][1]))
        self.assertEqual(main['Rate quotation'],'3.5 percent of Net Sales')
        self.assertEqual(payment['First source quotation'],'a signing payment of USD 250,000')
        self.assertIn('Royalty Terms:R1',evidence['Linked extracted records'])

    def test_ambiguous_amount_is_not_called_undisclosed(self):
        raw=fixture_rows();p=raw['Other Payments'][1];h=raw['Other Payments'][0]
        p[h.index('Kind')]='ADVANCE';p[h.index('Amount_Text')]=None
        p[h.index('Disclosure_Status')]='AMBIGUOUS'
        main=dict(zip(research_rows(raw)[NAMES[0]][0],research_rows(raw)[NAMES[0]][1]))
        self.assertEqual(main['Advance / prepayment'],'USD AMOUNT_AMBIGUOUS [P1]')

    def test_optional_exclusivity_scope_legacy_fallback(self):
        raw=fixture_rows()
        v=research_rows(raw)
        row=dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        self.assertEqual(row['Exclusivity'],'Non-exclusive')
        self.assertEqual(row['Exclusivity scope'],'NOT_ASSESSED')
        self.assertEqual(row['Royalty cap'],'NOT_ASSESSED')
        # v0.13.12: with payment records present the cell says what was checked, but still starts with NOT_ASSESSED
        self.assertTrue(row['Advance / prepayment'].startswith('NOT_ASSESSED (checked 1 payment record: none is an advance'))
        self.assertEqual(row['Minimum guarantee'],'NOT_ASSESSED')
        v=research_rows(raw,{'DOC-DEMO':{'agreement':{
            'exclusivity_scope':'Product X in the United States, through 2030',
            'field_evidence':{'exclusivity_scope':['E1']}}}})
        row=dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        self.assertEqual(row['Exclusivity scope'],'Product X in the United States, through 2030')
        self.assertEqual(row['Exclusivity scope evidence IDs'],'E1')

    def test_excel_default_sheets_are_pwc_formatted(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'out.xlsx'; write_research_xlsx(fixture_rows(),out)
            from openpyxl import load_workbook
            w=load_workbook(out)
            self.assertEqual(w.sheetnames,list(NAMES))
            s=w[NAMES[0]]
            self.assertFalse(s.sheet_view.showGridLines)
            self.assertEqual(s.freeze_panes,'D8')
            self.assertEqual(s['A1'].font.name,'Georgia')
            self.assertEqual(s['A7'].font.name,'Arial')
            self.assertEqual(s['A7'].border.bottom.color.rgb[-6:].upper(),'FD5108')
            self.assertEqual(s['D8'].value,0.035)
            self.assertIsInstance(s['D8'].value,float)
            self.assertEqual(s['D8'].number_format,'0.00%')


class AdditionalSourceEvidence(unittest.TestCase):
    def setUp(self):
        p=ROOT/'tests'/'fixtures'/'m12_saved'
        self.mapping=read_json(p/'Kirklands_map.json')
        self.extraction=read_json(p/'Kirklands_extraction.json')
        self.assertEqual(source_check(self.mapping,self.extraction)['errors'],[])

    def test_legacy_still_valid(self):
        self.assertNotIn('licensed_ip_nature',self.extraction['agreement'])
        self.assertEqual(source_check(self.mapping,self.extraction)['errors'],[])

    def test_new_fields_require_real_evidence_ids(self):
        a=self.extraction['agreement']
        a['licensed_ip_nature']='TRADEMARK_BRAND'
        a['sublicensing_rights']='Sublicensing allowed'
        a['field_evidence']['licensed_ip_nature']=[]
        a['field_evidence']['sublicensing_rights']=['E-NOT-REAL']
        a['other_material_terms']=[{'category':'TERMINATION','text':'Terminated on notice','evidence_ids':[]}]
        errors={e['code'] for e in source_check(self.mapping,self.extraction)['errors']}
        self.assertIn('M13_AGREEMENT_FIELD_WITHOUT_EVIDENCE',errors)
        self.assertIn('M13_EVIDENCE_MISSING',errors)

    def test_exclusivity_scope_requires_source_evidence(self):
        a=self.extraction['agreement']
        a['exclusivity_scope']='Exclusive for Product A in Canada'
        a['field_evidence']['exclusivity_scope']=[]
        errors={e['code'] for e in source_check(self.mapping,self.extraction)['errors']}
        self.assertIn('M13_AGREEMENT_FIELD_WITHOUT_EVIDENCE',errors)
        a['field_evidence']['exclusivity_scope']=[self.extraction['evidence'][0]['evidence_id']]
        self.assertEqual(source_check(self.mapping,self.extraction)['errors'],[])

    def test_new_fields_with_existing_citations_do_not_change_numeric_check(self):
        a=self.extraction['agreement']; eid=self.extraction['evidence'][0]['evidence_id']
        a.update(licensed_ip_nature='OTHER',licensed_ip_nature_details='Rights described in supplied clause',
                 sublicensing_rights='Qualified grant',other_material_terms=[
                     {'category':'TERMINATION','text':'Original condition in clause','evidence_ids':[eid]}])
        for k in ('licensed_ip_nature','licensed_ip_nature_details','sublicensing_rights'):
            a['field_evidence'][k]=[eid]
        self.assertEqual(source_check(self.mapping,self.extraction)['errors'],[])

class V0137Rules(unittest.TestCase):
    def test_royalty_cap_column_ignores_caps_on_service_consideration(self):
        raw=fixture_rows(); headers=raw['Other Payments'][0]
        def add(**kw): raw['Other Payments'].append([kw.get(k) for k in headers])
        add(Payment_ID='P9',Document_ID='DOC-DEMO',Kind='CAP',Amount_Text='1000000',Currency='USD',
            Basis='Absolute aggregate cap on deferred cash service consideration installments',
            Condition='Cumulative installments shall not exceed US$1,000,000.',Evidence_IDs='E1')
        v=research_rows(raw)
        row=dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        self.assertEqual(row['Royalty cap'],'NOT_ASSESSED')
        self.assertIn('P9',[r[0] for r in v[NAMES[2]][1:]])       # still listed in sheet 03
        add(Payment_ID='P10',Document_ID='DOC-DEMO',Kind='CAP',Amount_Text='500000',Currency='USD',
            Condition='Annual royalties shall not exceed this amount',Evidence_IDs='E1')
        v=research_rows(raw)
        row=dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        self.assertEqual(row['Royalty cap'],'USD 500,000 [P10]')

    def test_benchmark_note_says_no_licence_for_undetermined_nature_without_grant(self):
        term={'Rate_Numeric':3.5,'Rate_Unit':'PERCENT','Family':'PRODUCT_SALES','Disclosure_Status':'DISCLOSED'}
        usable,note=benchmark_usable(term,'NOT_STATED',None,nature='UNDETERMINED',grant_found=False)
        self.assertEqual(usable,'NO');self.assertTrue(note.startswith('no IP licence grant found'))
        usable,note=benchmark_usable(term,'NOT_STATED',None,nature='UNDETERMINED',grant_found=True)
        self.assertEqual(usable,'YES')
        usable,note=benchmark_usable(term,'NOT_STATED',None,nature='PATENT',grant_found=False)
        self.assertEqual(usable,'YES')                           # a reader-classified nature is never overridden
        bad=dict(term,Rate_Numeric=None)
        usable,note=benchmark_usable(bad,'NOT_STATED',None,nature='UNDETERMINED',grant_found=False)
        self.assertTrue(note.startswith('no IP licence grant found'));self.assertIn('rate not disclosed',note)

    def test_exporter_uses_source_text_for_grant_detection(self):
        raw=fixture_rows()
        def row(texts):
            v=research_rows(raw,{'DOC-DEMO':{'agreement':{'licensed_ip_nature':'UNDETERMINED'}}},{'DOC-DEMO':texts})
            return dict(zip(v[NAMES[0]][0],v[NAMES[0]][1]))
        r=row(['N2OFF provides services and receives a share of gross profit.'])
        self.assertEqual(r['Usable for royalty benchmark'],'NO');self.assertIn('no IP licence grant',r['Benchmark note'])
        r=row(['Licensor hereby grants Licensee an exclusive license under the Licensed Patents.'])
        self.assertNotIn('no IP licence grant',r['Benchmark note'])


if __name__=='__main__':unittest.main()
