"""M5 engineering regressions, including carefully LABELLED paraphrases of SEC facts.

These are not complete original SEC documents or a model accuracy benchmark.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from royalty_research.m5_probe import ProbeError, probe, probe_manifest
from royalty_research.cli import main
from royalty_research.m2_validation import validate_extraction
from royalty_research.mapping import FINANCE, CROSSREF, map_contract, validate_map
from royalty_research.parsing import parse_document, ParseError
from royalty_research.storage import sha256

ROOT = Path(__file__).resolve().parents[1]
F = ROOT/'tests'/'fixtures'/'m5'
GOOD = json.loads((ROOT/'examples'/'synthetic_m2_extraction.json').read_text())
MAP = json.loads((ROOT/'output'/'synthetic_clause_map.json').read_text())
MANIFEST = json.loads((F/'anchor_manifest.json').read_text())


def errcodes(report): return {e['code'] for e in report['errors']}


class SourceAnchors(unittest.TestCase):
    def test_manifest_all_anchors_detected_but_not_recall(self):
        result=probe_manifest(F,MANIFEST)
        self.assertEqual(result['status'],'ALL_ANCHORS_PASS_NOT_RECALL_VALIDATED')
        self.assertEqual(len(result['results']),3)
        self.assertTrue(result['not_a_gold_standard'])
        self.assertEqual(sum(len(x['anchors']) for x in result['results']),14)
        self.assertTrue(all(a['pass'] for r in result['results'] for a in r['anchors']))
        self.assertTrue(all('Full-contract semantic recall' in r['not_validated'] for r in result['results']))

    def test_market_four_rates_share_one_passage(self):
        raw=(F/'market_excerpt_paraphrase.html').read_bytes()
        paragraphs,_=parse_document(raw,'x.html')
        mapped=map_contract(paragraphs,{'document_id':'M5-MARKET','source_url':'https://www.sec.gov/Archives/example.htm'})
        self.assertEqual(validate_map(mapped),[])
        found=[p for p in mapped['passages'] if all(x in p['text'] for x in ('6%','4%','2%','1%'))]
        self.assertEqual(len(found),1)
        self.assertIn(found[0]['passage_id'],mapped['candidate_passages'])

    def test_market_unrelated_interest_indeed_screened_not_economically_classified(self):
        raw=(F/'market_excerpt_paraphrase.html').read_bytes()
        paragraphs,_=parse_document(raw,'x.html')
        mapped=map_contract(paragraphs,{'document_id':'M5-MARKET','source_url':None})
        found=[p for p in mapped['passages'] if '.5%' in p['text']]
        self.assertEqual(len(found),1)
        self.assertIn('PERCENT',found[0]['candidate_reasons'])
        self.assertEqual(found[0]['review_disposition'],'UNREVIEWED')

    def test_uc_separate_sublicensing_rows_not_silently_lost(self):
        raw=(F/'neurogesx_excerpt_paraphrase.html').read_bytes()
        paragraphs,_=parse_document(raw,'uc.html')
        mapped=map_contract(paragraphs,{'document_id':'M5-UC','source_url':None})
        for rate in ('25%','10%','5%'):
            found=[p for p in mapped['passages'] if rate in p['text']]
            self.assertTrue(found)
            self.assertTrue(any(p['passage_id'] in mapped['candidate_passages'] for p in found))
        self.assertTrue(any('25%' in p['text'] and '250,000' in p['text'] for p in mapped['passages']))

    def test_uc_non_royalty_equity_mentioned_without_autoclassification(self):
        raw=(F/'neurogesx_excerpt_paraphrase.html').read_bytes()
        paragraphs,_=parse_document(raw,'uc.html')
        m=map_contract(paragraphs,{'document_id':'M5-UC','source_url':None})
        passage=next(p for p in m['passages'] if '1% of stock' in p['text'])
        self.assertIn('PERCENT',passage['candidate_reasons'])
        self.assertEqual(passage['review_disposition'],'UNREVIEWED')

    def test_qualitative_obligations_flagged_without_numbers(self):
        raw=(F/'indirect_payment.html').read_bytes()
        paragraphs,_=parse_document(raw,'indirect.html')
        mapped=map_contract(paragraphs,{'document_id':'M5-INDIRECT','source_url':None})
        for term in ('Annex C','Attachment D','Addendum A'):
            found=[p for p in mapped['passages'] if term in p['text']]
            self.assertTrue(found)
            self.assertTrue(all('CROSS_REFERENCE' in p['candidate_reasons'] for p in found))

    def test_missing_anchor_fails_and_not_silently_skipped(self):
        a=copy.deepcopy(MANIFEST)
        a['records'][0]['anchors'].append({'id':'nonexistent','regex':'xyz-royalty-absent','candidate':True})
        result=probe_manifest(F,a)
        self.assertEqual(result['status'],'ANCHOR_FAILURE')
        self.assertFalse(result['results'][0]['anchors'][-1]['pass'])

    def test_probe_with_empty_document_fails(self):
        with self.assertRaises(ProbeError):probe(b'','a.htm','https://www.sec.gov/Archives/a',[])

    def test_probe_with_non_sec_url_refused(self):
        with self.assertRaises(ProbeError):
            probe(b'x','x.htm','https://attacker.example/x',[{'id':'x','regex':'x'}])

    def test_manifest_rejects_path_traversal(self):
        a=copy.deepcopy(MANIFEST)
        a['records'][0]['filename']='../market_excerpt_paraphrase.html'
        with self.assertRaises(ProbeError):probe_manifest(F,a)

    def test_manifest_rejects_invalid_regex(self):
        a=copy.deepcopy(MANIFEST)
        a['records'][0]['anchors'][0]['regex']='('
        with self.assertRaises(ProbeError):probe_manifest(F,a)

    def test_probe_cli_writes_auditable_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'probe.json'
            self.assertEqual(main(['m5-probe-manifest','--fixtures',str(F),'--manifest',str(F/'anchor_manifest.json'),'--out',str(p)]),0)
            self.assertEqual(json.loads(p.read_text())['status'],'ALL_ANCHORS_PASS_NOT_RECALL_VALIDATED')
            self.assertEqual(main(['m5-probe-manifest','--fixtures',str(F),'--manifest',str(F/'anchor_manifest.json'),'--out',str(p)]),2)


class HTMLSourceIntegrity(unittest.TestCase):
    def test_script_does_not_leak_fake_royalty(self):
        raw=b'<html><body><script>royalty 99%</script><p>Royalty 5% of Net Sales</p></body></html>'
        paragraphs,_=parse_document(raw,'x.htm')
        self.assertFalse(any('99%' in x for x in paragraphs))
        self.assertTrue(any('5%' in x for x in paragraphs))

    def test_unclosed_ignored_html_fails_instead_of_losing_tail(self):
        raw=b'<html><body><p>Royalties 5%</p><script>document.write("")'
        with self.assertRaises(ParseError):parse_document(raw,'x.htm')

    def test_table_row_retains_its_percent_threshold_pair(self):
        raw=b'<html><table><tr><td>25%</td><td>$250,000</td></tr></table></html>'
        paragraphs,_=parse_document(raw,'x.htm')
        self.assertTrue(any('25%' in p and '$250,000' in p for p in paragraphs))

    def test_html_entities_decoded_without_losing_rate(self):
        raw=b'<p>Licensee pays 5&#37; based on revenue &amp; charges.</p>'
        paragraphs,_=parse_document(raw,'x.htm')
        self.assertTrue(any('5%' in p and '& charges' in p for p in paragraphs))

    def test_source_text_hash_changes_on_economic_change(self):
        a=b'<p>Licensee shall pay 5% of Net Sales.</p>'
        b=b'<p>Licensee shall pay 4% of Net Sales.</p>'
        atext,_=parse_document(a,'x.htm');btext,_=parse_document(b,'x.htm')
        x=map_contract(atext,{'document_id':'D','source_url':None});y=map_contract(btext,{'document_id':'D','source_url':None})
        self.assertNotEqual(x['text_sha256'],y['text_sha256'])
        self.assertEqual(validate_map(x),[])


class UnknownDispositionGate(unittest.TestCase):
    def test_unknown_percent_without_high_issue_fails(self):
        x=copy.deepcopy(GOOD)
        for d in x['dispositions']:
            if d['percentage_dispositions']:
                d['percentage_dispositions'][0]['classification']='UNKNOWN'
                pid=d['passage_id']
                break
        x['open_issues']=[]
        report=validate_extraction(MAP,x)
        self.assertIn('UNKNOWN_PERCENT_WITHOUT_BLOCKING_ISSUE',errcodes(report))

    def test_uncertain_passage_without_high_issue_fails(self):
        x=copy.deepcopy(GOOD)
        x['dispositions'][0]['categories']=['UNCERTAIN']
        x['open_issues']=[]
        report=validate_extraction(MAP,x)
        self.assertIn('UNCERTAIN_WITHOUT_BLOCKING_ISSUE',errcodes(report))

    def test_low_issue_does_not_authorize_unresolved_percent(self):
        x=copy.deepcopy(GOOD)
        d=next(d for d in x['dispositions'] if d['percentage_dispositions'])
        d['percentage_dispositions'][0]['classification']='UNKNOWN'
        x['open_issues']=[{'issue_id':'I-LOW','severity':'LOW','kind':'UNCLASSIFIED','description':'Cannot classify royalty',
                           'status':'OPEN','passage_ids':[d['passage_id']]}]
        self.assertIn('UNKNOWN_PERCENT_WITHOUT_BLOCKING_ISSUE',errcodes(validate_extraction(MAP,x)))

    def test_unresolved_percent_with_high_issue_is_blocked_not_approved(self):
        x=copy.deepcopy(GOOD)
        d=next(d for d in x['dispositions'] if d['percentage_dispositions'])
        d['percentage_dispositions'][0]['classification']='UNKNOWN'
        x['open_issues'].append({'issue_id':'I-HIGH','severity':'HIGH','kind':'UNCLASSIFIED',
                                  'description':'Potential royalty percentage classification unresolved',
                                  'status':'OPEN','passage_ids':[d['passage_id']]})
        r=validate_extraction(MAP,x)
        self.assertNotIn('UNKNOWN_PERCENT_WITHOUT_BLOCKING_ISSUE',errcodes(r))
        self.assertFalse(r['can_claim_complete'])
        self.assertTrue(any(w['code']=='BLOCKING_OPEN_ISSUE' for w in r['warnings']))


class ValidatorUpgradeSafety(unittest.TestCase):
    def test_previous_validator_revision_requires_explicit_revalidation(self):
        from royalty_research.m3_workspace import init, register_map, register_extraction, load_attempt, _document_dir
        from royalty_research.storage import atomic_json
        with tempfile.TemporaryDirectory() as d:
            init(d)
            register_map(d,MAP)
            info=register_extraction(d,MAP['document_id'],GOOD,select=True)
            self.assertEqual(load_attempt(d,MAP['document_id'],info['extraction_sha256'])[2]['validator_revision'],
                             'm10.0-source-led-and-unchanged-extraction-history')
            attempt_file=_document_dir(d,MAP['document_id'])/'attempts'/info['extraction_sha256']/'attempt.json'
            old=json.loads(attempt_file.read_text())
            old.pop('validator_revision')  # simulate an existing M4-era check
            atomic_json(attempt_file,old)
            with self.assertRaisesRegex(ValueError,'EXTRACTION_CHECKER_REVISION_CHANGED'):
                load_attempt(d,MAP['document_id'],info['extraction_sha256'])


if __name__=='__main__':unittest.main()
