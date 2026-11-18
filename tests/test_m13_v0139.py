"""v0.13.9: real-percentage rate cells, mixed IA components, valuation relevance of other terms."""
from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path

from royalty_research.m13_research_export import (NAMES, research_rows, write_research_xlsx, classify_other_term,
                                                  key_terms_summary, KEY, SUPPLEMENTARY, ADMIN)
from royalty_research.m13_two_reader import source_check
from royalty_research.m3_chunks import merge_chunks, agreement_scalar_fields
from royalty_research.m2_schema_check import validate_shape
from royalty_research.storage import read_json
from test_m13_research_export import fixture_rows
import test_m3

ROOT=Path(__file__).resolve().parents[1]


def row_of(v,sheet=0,i=1):
    return dict(zip(v[NAMES[sheet]][0],v[NAMES[sheet]][i]))


class RateCells(unittest.TestCase):
    def _cells(self,mutate=None):
        raw=fixture_rows()
        if mutate:mutate(raw)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'o.xlsx';write_research_xlsx(raw,out)
            from openpyxl import load_workbook
            return load_workbook(out),raw

    def test_percent_rate_is_stored_as_fraction_with_percent_format(self):
        w,raw=self._cells()
        c=w[NAMES[0]]['D8']
        self.assertAlmostEqual(c.value,0.035,places=12);self.assertEqual(c.number_format,'0.00%')
        t=w[NAMES[1]]['F8']   # tier "Rate numeric"
        self.assertAlmostEqual(t.value,0.035,places=12);self.assertEqual(t.number_format,'0.00%')
        self.assertEqual(raw['Royalty Terms'][1][raw['Royalty Terms'][0].index('Rate_Numeric')],3.5)   # internal data unchanged
        self.assertIn('real percentages',w[NAMES[0]]['A5'].value)

    def test_decimals_and_whole_numbers(self):
        def m(raw):
            i=raw['Royalty Terms'][0].index('Rate_Numeric');raw['Royalty Terms'][1][i]=12.5
        w,_=self._cells(m)
        self.assertEqual(w[NAMES[0]]['D8'].value,0.125)

    def test_non_percent_units_are_not_converted(self):
        def m(raw):
            h=raw['Royalty Terms'][0];r=raw['Royalty Terms'][1]
            r[h.index('Rate_Unit')]='CURRENCY_PER_UNIT';r[h.index('Rate_Numeric')]=2.5
        w,_=self._cells(m)
        # v0.13.12: a per-unit amount is no longer written to the percent column; it has its own column (E)
        c=w[NAMES[0]]['D8'];self.assertIsNone(c.value)
        c=w[NAMES[0]]['E8'];self.assertEqual(c.value,'2.5 per unit (currency not stated)');self.assertNotEqual(c.number_format,'0.00%')

    def test_benchmark_rule_still_uses_percent_points(self):
        def m(raw):
            raw['Royalty Terms'][1][raw['Royalty Terms'][0].index('Rate_Numeric')]=100
        v=research_rows((lambda r:(m(r),r)[1])(fixture_rows()))
        r=row_of(v);self.assertEqual(r['Royalty rate (%)'],100);self.assertIn('50% or more',r['Benchmark note'])


class MixedComponents(unittest.TestCase):
    def _nature(self,agreement,texts=()):
        raw=fixture_rows()
        ev=raw['Evidence'];i=ev[0].index('Exact_Quotation')
        texts=list(texts)
        for r in ev[1:]:r[i]=texts.pop(0) if texts else r[i]
        return row_of(research_rows(raw,{'DOC-DEMO':{'agreement':agreement}}))

    def test_reader_components_listed(self):
        r=self._nature({'licensed_ip_nature':'MIXED','licensed_ip_nature_basis':'INFERRED',
                        'licensed_ip_components':['PATENT','KNOW_HOW','TRADEMARK_BRAND'],
                        'field_evidence':{'licensed_ip_nature':['E1'],'licensed_ip_components':['E2']}})
        self.assertEqual(r['Nature of IA'],'MIXED: patent, know-how, trademark/brand (inferred)')
        self.assertEqual(r['IA evidence IDs'],'E1; E2')
        r=self._nature({'licensed_ip_nature':'MIXED','licensed_ip_nature_basis':'STATED','licensed_ip_components':['PATENT','TECHNOLOGY']})
        self.assertEqual(r['Nature of IA'],'MIXED: patent, technology')

    def test_old_reading_mixed_or_undetermined_gets_keyword_hint_listing_all(self):
        txt=['Licensed Patents, know-how, software, copyrights and the Trademarks and logo, plus technical information, franchise']
        r=self._nature({'licensed_ip_nature':'MIXED','field_evidence':{'licensed_ip_nature':['E1']}},txt)
        self.assertEqual(r['Nature of IA'],'MIXED: patent, know-how/trade secret, technology/technical information, software/source code, copyright, trademark/brand/trade name/logo, franchise (keyword hint)')
        r=self._nature({'licensed_ip_nature':'UNDETERMINED','field_evidence':{'duration':['E1']}},['patent and know-how rights'])
        self.assertEqual(r['Nature of IA'],'MIXED: patent, know-how/trade secret (keyword hint)')
        self.assertIn('Keyword hint',r['IA classification detail'])

    def test_single_type_and_reader_values_unchanged(self):
        r=self._nature({'licensed_ip_nature':'PATENT','licensed_ip_components':['PATENT'],'field_evidence':{'licensed_ip_nature':['E1']}},['patent and know-how'])
        self.assertEqual(r['Nature of IA'],'PATENT')
        r=self._nature({'licensed_ip_nature':'TECHNOLOGY','licensed_ip_nature_basis':'INFERRED','field_evidence':{'licensed_ip_nature':['E1']}})
        self.assertEqual(r['Nature of IA'],'TECHNOLOGY (inferred)')
        r=self._nature({'licensed_ip_nature':'UNDETERMINED','field_evidence':{'duration':['E1']}},['patent only'])
        self.assertEqual(r['Nature of IA'],'PATENT (keyword hint)')

    def test_schema_accepts_components_and_technology(self):
        ex=read_json(ROOT/'examples'/'synthetic_m2_extraction.json')
        ex['agreement'].update(licensed_ip_nature='MIXED',licensed_ip_components=['PATENT','TECHNOLOGY'])
        self.assertEqual([p for p in validate_shape(ex) if 'licensed_ip' in str(p)],[])
        ex['agreement']['licensed_ip_components']=['MIXED']
        self.assertTrue([p for p in validate_shape(ex) if 'licensed_ip_components' in str(p)])
        self.assertEqual((ROOT/'schemas'/'m2_extraction.schema.json').read_text(),
                         (ROOT/'src'/'royalty_research'/'schemas'/'m2_extraction.schema.json').read_text())

    def test_merge_accepts_and_unions_components(self):
        base=test_m3.ChunkMergeTests('test_chunk_merge_recovers_complete_output');base.setUp()
        self.assertIn('licensed_ip_components',agreement_scalar_fields())
        eid=base.outputs[0]['evidence'][0]['evidence_id']
        outs=copy.deepcopy(base.outputs)
        outs[0]['agreement'].update(licensed_ip_nature='MIXED',licensed_ip_components=['PATENT','KNOW_HOW'])
        outs[0]['agreement'].setdefault('field_evidence',{})['licensed_ip_components']=[eid]
        outs[1]['agreement']={'licensed_ip_components':['KNOW_HOW','TECHNOLOGY']}
        merged,_=merge_chunks(base.map,base.packet,outs)
        self.assertEqual(merged['agreement']['licensed_ip_components'],['PATENT','KNOW_HOW','TECHNOLOGY'])
        self.assertEqual(merged['agreement']['field_evidence']['licensed_ip_components'],[eid])

    def test_source_check_requires_evidence_for_components(self):
        p=ROOT/'tests'/'fixtures'/'m12_saved'
        mapping=read_json(p/'Kirklands_map.json');ex=read_json(p/'Kirklands_extraction.json')
        eid=ex['evidence'][0]['evidence_id']
        a=ex['agreement'];a.update(licensed_ip_nature='MIXED',licensed_ip_components=['PATENT','KNOW_HOW'])
        a['field_evidence']['licensed_ip_nature']=[eid]
        self.assertEqual(source_check(mapping,ex)['errors'],[])          # cited under the nature: accepted
        a['field_evidence']['licensed_ip_nature']=[];a['field_evidence']['licensed_ip_components']=[]
        codes={e['code'] for e in source_check(mapping,ex)['errors']}
        self.assertIn('M13_AGREEMENT_FIELD_WITHOUT_EVIDENCE',codes)
        a['field_evidence']['licensed_ip_components']=[eid]
        self.assertEqual([e for e in source_check(mapping,ex)['errors'] if 'components' in str(e)],[])
        a['field_evidence']['licensed_ip_components']=['E-NOT-REAL']
        self.assertIn('M13_EVIDENCE_MISSING',{e['code'] for e in source_check(mapping,ex)['errors']})


class OtherTermTiers(unittest.TestCase):
    def test_each_tier(self):
        cases=[('TERMINATION','Licensor may terminate if Licensee has no sales within 5 years',KEY),
               ('OTHER','Licensee bears all patent prosecution and maintenance costs',KEY),
               ('OTHER','Royalty step-down of 50% after generic entry',KEY),
               ('OTHER','Licensee shall use commercially reasonable efforts (diligence) to launch',KEY),
               ('SCOPE','Field of use limited to dermatology',KEY),
               ('SUBLICENSING','Licensor receives 20% of sublicense income',KEY),
               ('EXCLUSIVITY','Exclusive in the Territory',KEY),
               ('OTHER','Most favoured licensee clause',KEY),
               ('ASSIGNMENT','On a change of control the royalty rate increases',KEY),
               ('OTHER','Payments in US dollars converted at the exchange rate on the payment date',SUPPLEMENTARY),
               ('AUDIT_REPORTING','Licensee provides quarterly reports of net sales',SUPPLEMENTARY),
               ('TERMINATION','Either party may terminate on the other party\'s insolvency or bankruptcy',SUPPLEMENTARY),
               ('TERMINATION','Either party may terminate for uncured material breach, bankruptcy or dissolution',KEY),
               ('ASSIGNMENT','Neither party may assign without consent',SUPPLEMENTARY),
               ('OTHER','Warranties limited to fees paid; indemnity capped',SUPPLEMENTARY),
               ('OTHER','Licensee shall not use the Licensor\'s name in publicity without consent',ADMIN),
               ('OTHER','Notices shall be given in writing to the addresses above',ADMIN),
               ('OTHER','This agreement may be executed in counterparts',ADMIN),
               ('OTHER','Entire agreement; headings are for convenience only',ADMIN),
               ('SCOPE','Press release requires prior approval',ADMIN)]
        for cat,text,tier in cases:
            self.assertEqual(classify_other_term(cat,text)[0],tier,(cat,text))

    def test_unsure_is_supplementary_never_dropped(self):
        self.assertEqual(classify_other_term('OTHER','Something unusual about the parties')[0],SUPPLEMENTARY)
        self.assertEqual(classify_other_term(None,None)[0],SUPPLEMENTARY)

    def test_sheet_01_summary_only_key_terms(self):
        m=[{'category':'TERMINATION','text':'May terminate if no sales within 5 years'},
           {'category':'OTHER','text':'Licensee pays patent prosecution costs'},
           {'category':'OTHER','text':'Diligence milestones apply'},
           {'category':'OTHER','text':'Notices in writing'},
           {'category':'AUDIT_REPORTING','text':'Annual audit'}]
        s=key_terms_summary(m)
        self.assertEqual(s,'TERM/TERMINATION, COSTS, DILIGENCE (3 key terms) – see sheet 06');self.assertLessEqual(len(s),120)
        self.assertIn('no key terms',key_terms_summary(m[3:]))
        self.assertEqual(key_terms_summary([]),'none recorded')
        self.assertLessEqual(len(key_terms_summary([{'category':c,'text':t} for c,t in
            [('SCOPE','field of use'),('EXCLUSIVITY','exclusive'),('SUBLICENSING','x'),('TERMINATION','x'),('OTHER','most favoured'),('OTHER','prosecution costs'),('OTHER','diligence'),('OTHER','step-down')]])),120)

    def test_sheet_06_sorted_filtered_and_greyed(self):
        raw=fixture_rows()
        mt=[{'category':'OTHER','text':'Notices in writing','evidence_ids':['E1']},
            {'category':'AUDIT_REPORTING','text':'Quarterly reports','evidence_ids':['E1']},
            {'category':'TERMINATION','text':'Terminate if no sales within 5 years','evidence_ids':['E1']}]
        ex={'DOC-DEMO':{'agreement':{'other_material_terms':mt}}}
        v=research_rows(raw,ex)
        h=v[NAMES[5]][0];self.assertEqual(h[4:6],['Category','Valuation relevance'])
        self.assertEqual([r[5] for r in v[NAMES[5]][1:]],['KEY','SUPPLEMENTARY','ADMIN'])
        self.assertEqual(row_of(v)['Other material terms'][:30],'TERM/TERMINATION (1 key term) ')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'o.xlsx';write_research_xlsx(raw,out,ex)
            from openpyxl import load_workbook
            ws=load_workbook(out)[NAMES[5]]
            self.assertTrue(ws.auto_filter.ref)
            self.assertEqual(ws['F8'].value,'KEY');self.assertEqual(ws['F10'].value,'ADMIN')
            self.assertEqual(ws['G10'].font.color.rgb[-6:],'808080');self.assertNotEqual(ws['G8'].font.color.rgb[-6:],'808080')



class KeyCategoryLabelTests(unittest.TestCase):
    def test_reader_key_category_names_the_term(self):
        from royalty_research.m13_research_export import classify_other_term,key_terms_summary
        text='Earned royalty payments and reports continue after termination for Licensed Products made before termination.'
        self.assertEqual(classify_other_term('TERMINATION',text),('KEY','TERM/TERMINATION'))
        self.assertIn('TERM/TERMINATION',key_terms_summary([{'category':'SCOPE','text':'Field of Use: All Fields.'},
                                                         {'category':'TERMINATION','text':text}]))


if __name__=='__main__':unittest.main()
