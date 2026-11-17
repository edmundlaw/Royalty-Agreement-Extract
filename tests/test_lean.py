import tempfile
import json
import unittest
from pathlib import Path
from royalty_research.lean import screen,validate,main,export_xlsx

class LeanResearch(unittest.TestCase):
    def test_screen_compact_and_validate_source_quote(self):
        raw=(b'LICENSE AGREEMENT\nThe licensor grants patent rights.\n'
             b'Licensee shall pay a royalty of 5% of Net Sales.\n'
             b'Administrative notice only.\n')
        packet,report,source,template=screen(raw,'agreement.txt','https://www.sec.gov/Archives/edgar/data/1/2/a.txt')
        self.assertEqual(report['status'],'READY_FOR_AI')
        self.assertEqual(report['coverage'],'SCREENED_EXCERPTS_ONLY')
        self.assertIn('5% of Net Sales',packet)
        pid=next(k for k,v in source.items() if '5%' in v)
        template['royalty_terms']=[{'type':'RUNNING_ROYALTY','value_as_reported':'5%',
           'basis':'Net Sales','period_or_trigger':None,'passage_id':pid,
           'exact_quote':'royalty of 5% of Net Sales'}]
        self.assertEqual(validate(template,source),[])
        template['royalty_terms'][0]['value_as_reported']='15%'
        self.assertTrue(validate(template,source))

    def test_export_familiar_five_sheet_template(self):
        raw=b'Licensee shall pay a royalty of 5% of Net Sales.'
        _,_,source,template=screen(raw,'a.txt',None)
        pid=next(iter(source))
        template['royalty_terms']=[{'type':'PRODUCT_SALES','value_as_reported':'5%',
          'basis':'Net Sales','period_or_trigger':None,'passage_id':pid,
          'exact_quote':'royalty of 5% of Net Sales'}]
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'summary.xlsx';export_xlsx(template,source,out)
            from openpyxl import load_workbook
            w=load_workbook(out)
            self.assertEqual(len(w.sheetnames),6)
            self.assertEqual(w.worksheets[0]['D8'].value,5)
            headers=[c.value for c in w.worksheets[0][7]]
            self.assertIn('royalty of 5%',w.worksheets[0].cell(8,headers.index('Rate quotation')+1).value)

    def test_low_signal_is_flagged_not_declared_irrelevant(self):
        _,report,_,_=screen(b'Board minutes.\nNo economics here.','memo.txt',None)
        self.assertEqual(report['status'],'LOW_SIGNAL_OR_BUDGET_EMPTY_REVIEW_BEFORE_DISCARD')
        self.assertNotIn('IRRELEVANT',report['status'])

    def test_cli_offline_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inp=root/'agreement.txt';inp.write_text('Licensee shall pay a 3% royalty on net sales.')
            out=root/'out'
            self.assertEqual(main(['screen','--input',str(inp),'--out',str(out)]),0)
            self.assertTrue((out/'packet.txt').exists())
            self.assertEqual(main(['validate','--packet-dir',str(out),'--summary',str(out/'summary_template.json')]),1)

    def test_adversarial_number_and_basis_rejected(self):
        raw=b'Licensee shall pay a royalty of 15% of Net Sales.'
        _,_,source,template=screen(raw,'a.txt',None)
        pid=next(iter(source))
        template['royalty_terms']=[{'type':'PRODUCT_SALES','value_as_reported':'5%',
          'basis':'Gross Sales','period_or_trigger':None,'passage_id':pid,
          'exact_quote':'royalty of 15% of Net Sales'}]
        errors=validate(template,source)
        self.assertTrue(any('value' in x for x in errors))
        self.assertTrue(any('basis' in x for x in errors))

    def test_batch_keeps_low_signal_in_index(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inputs=root/'inputs';inputs.mkdir()
            (inputs/'one.txt').write_text('Licensee shall pay a 3% royalty on net sales.')
            (inputs/'two.txt').write_text('Board minutes with no economic clause.')
            out=root/'batch'
            self.assertEqual(main(['batch','--input-dir',str(inputs),'--out',str(out)]),0)
            index=json.loads((out/'index.json').read_text())
            self.assertEqual(len(index),2)
            self.assertEqual(index[0]['status'],'READY_FOR_AI')
            self.assertEqual(index[1]['status'],'LOW_SIGNAL_OR_BUDGET_EMPTY_REVIEW_BEFORE_DISCARD')
