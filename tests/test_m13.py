"""M13 two-reader check. Offline only: fake local CLI, no model call, no paid API."""
from __future__ import annotations
import copy, json, sys, tempfile, unittest
from pathlib import Path

from royalty_research.m13_two_reader import (numbers_in_text, reader_value, source_check, compare_readers, decide_state,
                                             prepare, add_check, next_call, status, finalize, combine, STATE_MEANING)
from royalty_research.m2_validation import validate_extraction
from royalty_research.storage import read_json

BASE = Path(__file__).resolve().parent.parent
SAVED = BASE / 'tests' / 'fixtures' / 'm12_saved'
KEEP = {'schema_version', 'document_id', 'source_text_sha256', 'source_url', 'reader', 'agreement', 'amendment_status',
        'evidence', 'royalty_terms', 'other_payments', 'dispositions', 'open_issues'}
SYNTHETIC_MAP = read_json(BASE / 'output' / 'synthetic_clause_map.json')


def saved(name):
    """A real Sonnet reading of a real SEC exhibit, judged correct in the M8/M9 reviews."""
    m = read_json(SAVED / f'{name}_map.json')
    e = {k: v for k, v in read_json(SAVED / f'{name}_extraction.json').items() if k in KEEP}
    return m, e


def units(text): return [(t['unit'], t['value']) for t in numbers_in_text(text)]


class Numbers(unittest.TestCase):
    def test_digits_and_words(self):
        self.assertEqual(units('a royalty of three percent (3%) of Net Sales'), [('PCT', '3'), ('PCT', '3')])
        self.assertEqual(units('two-hundred thousand dollars ($200,000)'), [('USD', '200000'), ('USD', '200000')])
        self.assertEqual(units('five hundred million Dollars ($500,000,000)'), [('USD', '500000000'), ('USD', '500000000')])
        self.assertEqual(units('twenty-two percent'), [('PCT', '22')])
        self.assertEqual(units('two and one-half percent (2.5%)'), [('PCT', '2.5'), ('PCT', '2.5')])
        self.assertEqual(units('$10 million'), [('USD', '10000000')])
        self.assertEqual(units('.5% per month'), [('PCT', '0.5')])

    def test_scale_word_alone_is_not_a_number(self):
        self.assertEqual(units('$[***] million'), [])

    def test_reader_value(self):
        self.assertEqual(reader_value('$500,000'), '500000')
        self.assertEqual(reader_value('1.0'), '1')
        self.assertEqual(reader_value('1.5% per month or the highest lawful rate'), '1.5')
        self.assertEqual(reader_value('10 million'), '10000000')
        self.assertIsNone(reader_value('2x (doubling of Section 4.1 rates)'))
        self.assertIsNone(reader_value('$[***] million'))
        self.assertIsNone(reader_value('[***]%'))
        self.assertIsNone(reader_value(None))
        # Live case (Pieris/Ligand, 2026-11-15): Sonnet wrote the words with the redacted figure, Codex the number.
        self.assertEqual(reader_value('Fifty Million Dollars ($[***])'), '50000000')
        self.assertEqual(reader_value('USD 50,000,000'), '50000000')
        # Live case (UC/NeurogesX, 2026-11-15): Codex wrote the bound with a qualifier.
        self.assertEqual(reader_value('250000 exclusive'), '250000')
        self.assertEqual(reader_value('less than or equal to $2,000,000'), '2000000')
        self.assertIsNone(reader_value('$250,000 -- $2,000,000'))


class SourceCheck(unittest.TestCase):
    def test_correct_real_readings_pass(self):
        for name in ('MarketFinders', 'NeurogesX', 'Qualigen', 'Kirklands'):
            m, e = saved(name)
            report = source_check(m, e)
            self.assertEqual(report['errors'], [], name)
            self.assertEqual(report['deterministic_status'], 'PASS_DETERMINISTIC_ONLY')

    def test_profile_routes_the_validator_to_the_source_check(self):
        m, e = saved('Qualigen')
        m = dict(m); m['quality_control_profile'] = 'M13_TWO_READER'
        self.assertEqual(validate_extraction(m, e)['schema'], 'm13-source-check.1')

    def test_changed_rate_is_caught(self):
        m, e = saved('Qualigen')
        e['royalty_terms'][0]['rate_value'] = '10'
        self.assertIn('M13_RATE_NOT_IN_QUOTE', {x['code'] for x in source_check(m, e)['errors']})

    def test_changed_threshold_and_amount_are_caught(self):
        m, e = saved('MarketFinders')
        e['royalty_terms'][0]['tiers'][0]['upper'] = '500'
        e['other_payments'][0]['amount_value'] = '123456789'
        codes = {x['code'] for x in source_check(m, e)['errors']}
        self.assertIn('M13_THRESHOLD_NOT_IN_QUOTE', codes); self.assertIn('M13_AMOUNT_NOT_IN_QUOTE', codes)

    def test_altered_quote_is_caught(self):
        m, e = saved('Kirklands')
        e['evidence'][0]['quote'] = e['evidence'][0]['quote'][:-1] + '~'
        self.assertIn('M13_QUOTE_NOT_IN_SOURCE', {x['code'] for x in source_check(m, e)['errors']})

    def test_quote_differing_only_in_case_is_a_warning_not_a_failure(self):
        m, e = saved('Kirklands')
        q = e['evidence'][0]['quote']
        e['evidence'][0]['quote'] = q[0].swapcase() + q[1:] if q[0].isalpha() else q.upper()
        report = source_check(m, e)
        self.assertEqual(report['errors'], [])
        self.assertIn('M13_QUOTE_DIFFERS_IN_CASE_OR_SPACING', {x['code'] for x in report['warnings']})

    def test_formula_rate_is_not_read_as_a_percentage(self):
        # Live case (Genprex, Codex, 2026-11-15): rate_value "2 x otherwise applicable running royalty rate", unit FORMULA.
        m, e = saved('Qualigen')
        e['royalty_terms'][0]['rate_value'] = '2 x otherwise applicable running royalty rate'
        e['royalty_terms'][0]['rate_unit'] = 'FORMULA'
        self.assertNotIn('M13_RATE_NOT_IN_QUOTE', {x['code'] for x in source_check(m, e)['errors']})

    def test_short_quote_on_a_fee_is_a_warning_but_not_on_a_minimum(self):
        m, e = saved('Qualigen')          # upfront fee $1,000,000
        fee = next(p for p in e['other_payments'] if p['kind'] == 'UPFRONT')
        ev = next(x for x in e['evidence'] if x['evidence_id'] == fee['evidence_ids'][0])
        cut = ev['quote'].index('$1,000,000')
        fee['evidence_ids'] = fee['evidence_ids'][:1]; ev['quote'] = ev['quote'][:cut].rstrip()
        self.assertGreaterEqual(len(ev['quote']), 8)
        report = source_check(m, e)
        self.assertNotIn('M13_AMOUNT_NOT_IN_QUOTE', {x['code'] for x in report['errors']})
        self.assertIn('M13_AMOUNT_IN_PASSAGE_NOT_IN_QUOTE', {x['code'] for x in report['warnings']})
        fee['kind'] = 'MINIMUM_ROYALTY'
        self.assertIn('M13_AMOUNT_NOT_IN_QUOTE', {x['code'] for x in source_check(m, e)['errors']})
        fee['kind'] = 'UPFRONT'; fee['amount_value'] = '123456789'      # not in the passage at all
        self.assertIn('M13_AMOUNT_NOT_IN_QUOTE', {x['code'] for x in source_check(m, e)['errors']})

    def test_record_without_evidence_is_caught(self):
        m, e = saved('Kirklands')
        e['other_payments'][0]['evidence_ids'] = []
        self.assertIn('M13_RECORD_WITHOUT_EVIDENCE', {x['code'] for x in source_check(m, e)['errors']})

    def test_unaccounted_flagged_passage_is_caught(self):
        m, e = saved('Qualigen')
        cited = {x['passage_id'] for x in e['evidence']}
        victim = next(d for d in e['dispositions'] if d['passage_id'] not in cited)
        e['dispositions'].remove(victim)
        self.assertIn('M13_PASSAGE_NOT_ACCOUNTED', {x['code'] for x in source_check(m, e)['errors']})

    def test_open_issues_play_no_part(self):
        m, e = saved('Qualigen')
        base = source_check(m, e)
        e['open_issues'] = []
        self.assertEqual(source_check(m, e)['errors'], base['errors'])


class Comparison(unittest.TestCase):
    def test_identical_readings_agree(self):
        for name in ('MarketFinders', 'NeurogesX', 'Qualigen', 'Kirklands'):
            m, e = saved(name)
            c = compare_readers(m, e, copy.deepcopy(e))
            self.assertEqual((c['core'], c['structure'], c['note']), (0, 0, 0), name)
            self.assertGreater(c['facts_both_recorded'], 0)
            self.assertEqual(decide_state(source_check(m, e), source_check(m, e), c), 'TWO_READERS_AGREE')

    def test_wording_differences_are_not_differences(self):
        m, e = saved('NeurogesX')
        other = copy.deepcopy(e)
        for t in other['royalty_terms']:
            t['base'] = 'reworded ' + str(t.get('base'))
            for c in t.get('conditions') or []: c['text'] = 'Reworded: ' + str(c.get('text'))
        other['open_issues'] = []
        c = compare_readers(m, e, other)
        self.assertEqual((c['core'], c['structure']), (0, 0))

    def test_reader_that_misses_the_sublicensing_schedule(self):
        m, e = saved('NeurogesX')
        other = copy.deepcopy(e)
        other['royalty_terms'] = [t for t in other['royalty_terms'] if t['family'] != 'SUBLICENSING_RECEIPTS']
        for first, second in ((e, other), (other, e)):
            c = compare_readers(m, first, second)
            self.assertGreaterEqual(c['core'], 3)
            self.assertEqual(decide_state(source_check(m, first), source_check(m, second), c), 'TWO_READERS_DIFFER')

    def test_reader_that_misses_one_tier(self):
        m, e = saved('MarketFinders')
        other = copy.deepcopy(e); other['royalty_terms'][0]['tiers'].pop()
        self.assertGreaterEqual(compare_readers(m, e, other)['core'], 1)

    def test_family_conflict_is_core(self):
        m, e = saved('Qualigen')
        other = copy.deepcopy(e); other['royalty_terms'][0]['family'] = 'SUBLICENSING_RECEIPTS'
        c = compare_readers(m, e, other)
        self.assertIn('FAMILY_DIFFERS', {d['kind'] for d in c['differences'] if d['level'] == 'CORE'})

    def test_marginal_versus_all_units_is_core(self):
        m, e = saved('MarketFinders')
        other = copy.deepcopy(e)
        for z in other['royalty_terms'][0]['tiers']: z['calculation'] = 'ALL_UNITS'
        c = compare_readers(m, e, other)
        self.assertIn('CALCULATION_DIFFERS', {d['kind'] for d in c['differences'] if d['level'] == 'CORE'})

    def test_same_number_arranged_differently_is_structure(self):
        m, e = saved('Kirklands')   # 3% rising to 5%: one reader keeps 5% as a tier, the other only as a condition
        other = copy.deepcopy(e)
        other['royalty_terms'][0]['tiers'] = [z for z in other['royalty_terms'][0]['tiers'] if str(z['rate_value']) != '5']
        c = compare_readers(m, e, other)
        self.assertEqual(c['core'], 0); self.assertGreaterEqual(c['structure'], 1)
        self.assertEqual(decide_state(source_check(m, e), source_check(m, other), c), 'TWO_READERS_AGREE_ON_NUMBERS')

    def test_missing_minimum_is_core_and_missing_upfront_fee_is_note(self):
        m, e = saved('Kirklands')
        other = copy.deepcopy(e)
        other['other_payments'] = [p for p in other['other_payments'] if p['kind'] != 'MINIMUM_ROYALTY']
        self.assertGreaterEqual(compare_readers(m, e, other)['core'], 1)
        m, e = saved('Qualigen')
        other = copy.deepcopy(e)
        other['other_payments'] = [p for p in other['other_payments'] if p['kind'] != 'UPFRONT']
        c = compare_readers(m, e, other)
        self.assertEqual(c['core'], 0); self.assertGreaterEqual(c['note'], 1)

    def test_valueless_record_by_one_reader(self):
        # Qualigen c1-t03: a sublicensing clause recorded as a term with no rate. If the other reader dismissed the clause
        # as background it is a CORE difference; if the other reader noticed the clause it is a STRUCTURE difference.
        m, e = saved('Qualigen')
        target = next(t for t in e['royalty_terms'] if t['term_id'] == 'c1-t03')
        ev = {x['evidence_id']: x['passage_id'] for x in e['evidence']}
        cited = {ev[i] for i in target['evidence_ids'] + (target.get('rate_evidence_ids') or [])}
        other = copy.deepcopy(e)
        other['royalty_terms'] = [t for t in other['royalty_terms'] if t['term_id'] != 'c1-t03']
        self.assertEqual(compare_readers(m, e, other)['core'], 0)
        self.assertGreaterEqual(compare_readers(m, e, other)['structure'], 1)
        for d in other['dispositions']:
            if d['passage_id'] in cited: d['categories'] = ['BACKGROUND']; d['term_ids'] = []; d['payment_ids'] = []
        keep = {x['evidence_id'] for x in other['evidence'] if x['passage_id'] not in cited}
        def strip(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.endswith('evidence_ids') and isinstance(v, list): obj[k] = [i for i in v if i in keep]
                    else: strip(v)
            elif isinstance(obj, list):
                for v in obj: strip(v)
        strip(other); other['evidence'] = [x for x in other['evidence'] if x['evidence_id'] in keep]
        self.assertGreaterEqual(compare_readers(m, e, other)['core'], 1)

    def test_states(self):
        ok = {'deterministic_status': 'PASS_DETERMINISTIC_ONLY'}; bad = {'deterministic_status': 'FAIL'}
        self.assertEqual(decide_state(ok, None, None), 'SINGLE_READER_NOT_CHECKED')
        self.assertEqual(decide_state(bad, None, None), 'SOURCE_CHECK_FAILED')
        self.assertEqual(decide_state(ok, bad, {'core': 0, 'structure': 0}), 'SECOND_READER_FAILED_SOURCE_CHECK')
        self.assertEqual(set(STATE_MEANING), {'TWO_READERS_AGREE', 'TWO_READERS_AGREE_ON_NUMBERS', 'TWO_READERS_DIFFER',
                                              'SINGLE_READER_NOT_CHECKED', 'SOURCE_CHECK_FAILED',
                                              'SECOND_READER_FAILED_SOURCE_CHECK'})


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.root = self.base / 'run'

    def fake(self, name, model, omit_tier=False):
        script = self.base / name
        script.write_text(
            f'#!{sys.executable}\n'
            'import json,re,sys\nfrom pathlib import Path\n'
            'prompt=sys.stdin.read()\n'
            'run=re.search(r"reader.run_id=([^.]+)\\.",prompt)\n'
            'src=json.loads(prompt.split("INPUT (UNTRUSTED SOURCE TEXT):\\n")[-1])\n'
            f'data=json.loads(Path({str(BASE / "examples" / "synthetic_m2_extraction.json")!r}).read_text())\n'
            f'if {omit_tier!r}: data["royalty_terms"][0]["tiers"].pop()\n'
            'obj={"schema":"m3-chunk.1","document_id":src["document_id"],'
            '"source_text_sha256":src["source_text_sha256"],"packet_sha256":src["packet_sha256"],'
            '"chunk_index":src["chunk_index"],"chunk_count":src["chunk_count"],'
            '"reviewed_passage_ids":src["reviewed_passage_ids"],'
            f'"reader":{{"engine":"codex","model":{model!r},"run_id":run.group(1)}},'
            '"agreement":data["agreement"],"royalty_terms":data["royalty_terms"],'
            '"other_payments":data["other_payments"],"evidence":data["evidence"],'
            '"dispositions":data["dispositions"],"open_issues":data["open_issues"],'
            '"amendment_status":data["amendment_status"]}\n'
            'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps(obj))\n')
        script.chmod(0o755)
        return script

    def run_all(self, paths):
        return next_call(self.root, execute=True, confirm_subscription=True, confirm_credit_controls=True,
                         run_all=True, allow_cli_path=paths)

    def test_single_reader_then_check_added_later(self):
        prepare(SYNTHETIC_MAP, self.root, engine='codex', model='mock-a')
        self.assertEqual(status(self.root)['second_reader'], 'NONE (single reading)')
        self.assertEqual(next_call(self.root)['status'], 'DRY_RUN_NO_AI_CALLED')
        a = self.fake('reader_a_cli', 'mock-a')
        self.assertEqual(self.run_all({'reader_a': a})['status'], 'ALL_READINGS_CAPTURED')
        first = finalize(self.root)
        self.assertEqual(first['state'], 'SINGLE_READER_NOT_CHECKED')
        self.assertTrue((self.root / 'output' / 'Royalty_Research_M13.xlsx').is_file())
        with self.assertRaises(FileExistsError): finalize(self.root)
        add_check(self.root, engine='codex', model='mock-b')
        b = self.fake('reader_b_cli', 'mock-b')
        self.assertEqual(self.run_all({'reader_a': a, 'reader_b': b})['status'], 'ALL_READINGS_CAPTURED')
        second = finalize(self.root)
        self.assertEqual(second['state'], 'TWO_READERS_AGREE')
        self.assertTrue(second['output_dir'].endswith('output_checked'))
        self.assertEqual(status(self.root)['outputs'], {'output': 'SINGLE_READER_NOT_CHECKED', 'output_checked': 'TWO_READERS_AGREE'})
        self.assertEqual(read_json(self.root / 'output' / 'reader_check.json')['state'], 'SINGLE_READER_NOT_CHECKED')

    def test_second_reader_that_omits_a_tier(self):
        prepare(SYNTHETIC_MAP, self.root, engine='codex', model='mock-a', check_engine='codex', check_model='mock-b')
        a = self.fake('reader_a_cli', 'mock-a'); b = self.fake('reader_b_cli', 'mock-b', omit_tier=True)
        one = next_call(self.root, execute=True, confirm_subscription=True, confirm_credit_controls=True,
                        allow_cli_path={'reader_a': a, 'reader_b': b})
        self.assertEqual(one['status'], 'CAPTURED_MORE_PENDING')
        with self.assertRaises(ValueError): finalize(self.root)             # second reader prepared but unfinished
        self.assertEqual(self.run_all({'reader_a': a, 'reader_b': b})['status'], 'ALL_READINGS_CAPTURED')
        result = finalize(self.root, legacy_xlsx=True)
        self.assertEqual(result['state'], 'TWO_READERS_DIFFER')
        self.assertGreaterEqual(result['core_differences'], 1)
        rows = {p.stem: p.read_text(encoding='utf-8-sig') for p in (self.root / 'output' / 'csv').glob('*.csv')}
        self.assertIn('TWO_READERS_DIFFER', rows['reader_check'])
        self.assertIn('CORE', rows['reader_differences'])
        self.assertIn('Licensor', rows['royalty_terms'].splitlines()[0])
        self.assertNotIn('source_flags', rows)
        from openpyxl import load_workbook
        research = load_workbook(self.root / 'output' / 'Royalty_Research_M13.xlsx')
        self.assertEqual(research.sheetnames, ['01 Royalty Database','02 Tiers & Mechanics', '03 Other Payments', '04 Source Evidence', '05 QC & Issues', '06 Other Terms'])
        wb = load_workbook(self.root / 'output' / 'Royalty_Research_M13_Detailed.xlsx')
        self.assertEqual(wb.sheetnames[:3], ['Overview', 'Reader Check', 'Reader Differences'])
        self.assertEqual(wb['Royalty Terms'].cell(row=2, column=[c.value for c in wb['Royalty Terms'][1]].index('QC_State') + 1).value,
                         'TWO_READERS_DIFFER')

    def test_without_check_exports_first_reading(self):
        prepare(SYNTHETIC_MAP, self.root, engine='codex', model='mock-a', check_engine='codex', check_model='mock-b')
        a = self.fake('reader_a_cli', 'mock-a')
        next_call(self.root, execute=True, confirm_subscription=True, confirm_credit_controls=True,
                  allow_cli_path={'reader_a': a})
        self.assertEqual(finalize(self.root, without_check=True)['state'], 'SINGLE_READER_NOT_CHECKED')

    def test_combined_workbook(self):
        runs = self.base / 'runs'
        a = self.fake('reader_a_cli', 'mock-a'); b = self.fake('reader_b_cli', 'mock-b', omit_tier=True)
        self.root = runs / 'single'
        prepare(SYNTHETIC_MAP, self.root, engine='codex', model='mock-a'); self.run_all({'reader_a': a}); finalize(self.root)
        self.root = runs / 'checked'
        prepare(SYNTHETIC_MAP, self.root, engine='codex', model='mock-a', check_engine='codex', check_model='mock-b')
        self.run_all({'reader_a': a, 'reader_b': b}); finalize(self.root)
        prepare(SYNTHETIC_MAP, runs / 'not_started', engine='codex', model='mock-a')
        out = self.base / 'all.xlsx'
        result = combine(runs, out, legacy_xlsx=True)
        self.assertEqual(result['agreements'], 2)
        self.assertEqual(result['states'], {'TWO_READERS_DIFFER': 1, 'SINGLE_READER_NOT_CHECKED': 1})
        self.assertEqual(result['not_finished'], ['not_started'])
        from openpyxl import load_workbook
        research = load_workbook(out)
        self.assertEqual(len(research.sheetnames), 6)
        wb = load_workbook(self.base / 'all_Detailed.xlsx')
        self.assertEqual(wb['Reader Check'].max_row, 3)
        rate = [c.value for c in wb['Tiers'][1]].index('Rate_Numeric') + 1
        self.assertIsInstance(wb['Tiers'].cell(row=2, column=rate).value, (int, float))
        with self.assertRaises(FileExistsError): combine(runs, out)
        (runs / 'checked' / 'output' / 'rows.json').write_text('{}')
        with self.assertRaises(ValueError): combine(runs, self.base / 'again.xlsx')

    def test_run_folder_is_never_overwritten_and_is_tamper_evident(self):
        prepare(SYNTHETIC_MAP, self.root, engine='codex', model='mock-a')
        with self.assertRaises(FileExistsError): prepare(SYNTHETIC_MAP, self.root, engine='codex', model='mock-a')
        meta = self.root / 'm13_run.json'
        data = json.loads(meta.read_text()); data['max_chars'] = 1; meta.write_text(json.dumps(data))
        with self.assertRaises(ValueError): status(self.root)


if __name__ == '__main__':
    unittest.main()
