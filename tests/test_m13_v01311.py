"""v0.13.11: fixes from the v0.13.10 external test round (A1-A4, B1-B6, C1)."""
from __future__ import annotations
import unittest
from pathlib import Path

from royalty_research.m13_consolidate import consolidate
from royalty_research.m13_research_export import NAMES, research_rows, benchmark_usable
from royalty_research.m13_two_reader import source_check
from royalty_research.m2_schema_check import validate_shape
from royalty_research.m3_export import _number
from royalty_research.storage import read_json

from test_m13_v01310 import term, unrated, cond, reading, ids
from test_m13_research_export import fixture_rows

FIX = Path(__file__).resolve().parent / 'fixtures' / 'm13_consolidate'


def quotes(ext, **by_id):
    have = {e['evidence_id'] for e in ext['evidence']}
    ext['evidence'] += [{'evidence_id': k, 'passage_id': 'P1'} for k in by_id if k not in have]
    for e in ext['evidence']: e['quote'] = by_id.get(e['evidence_id'], e.get('quote') or 'quote')
    return ext


def row(sheet, headers_row, **want):
    head = sheet[0]
    for r in sheet[1:]:
        d = dict(zip(head, r))
        if all(d.get(k) == v for k, v in want.items()): return d
    raise AssertionError(f'no row {want}')


class A1ShortQuotes(unittest.TestCase):
    def test_short_exact_quote_is_a_warning_not_a_failure(self):
        mapping = read_json(FIX / 'vxm01_map.json'); ext = read_json(FIX / 'vxm01_extraction.json')
        import re
        target = None
        for e in ext['evidence']:
            m = re.search(r'\d+(?:\.\d+)?%', e['quote'])
            if m and e['quote'].count(m.group()) >= 1: target = (e, m.group()); break
        self.assertIsNotNone(target)
        e, short = target
        self.assertLess(len(short), 8)
        e['quote'] = short
        self.assertEqual(validate_shape(ext), [])                      # schema no longer has a length rule beyond non-empty
        report = source_check(mapping, ext)
        self.assertFalse([x for x in report['errors'] if x['code'] in ('M13_SCHEMA', 'M13_QUOTE_NOT_IN_SOURCE')])
        self.assertIn(('M13_QUOTE_VERY_SHORT', e['evidence_id']), [(w['code'], w['ref']) for w in report['warnings']])
        self.assertEqual(next(c for c in report['checks'] if c['check'] == 'QUOTES_ARE_IN_SOURCE')['status'], 'PASS')

    def test_short_quote_still_has_to_be_in_the_source(self):
        mapping = read_json(FIX / 'vxm01_map.json'); ext = read_json(FIX / 'vxm01_extraction.json')
        ext['evidence'][0]['quote'] = '99.9%'
        report = source_check(mapping, ext)
        self.assertIn('M13_QUOTE_NOT_IN_SOURCE', [x['code'] for x in report['errors']])

    def test_both_schema_copies_identical(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / 'schemas' / 'm2_extraction.schema.json').read_text(),
                         (root / 'src' / 'royalty_research' / 'schemas' / 'm2_extraction.schema.json').read_text())


class A2UnratedFold(unittest.TestCase):
    def pair(self, u1_scope='Cosmeceutical Licensed Products', u2_scope='All other Licensed Products'):
        r1 = term('1-R01', product_scope='Cosmeceutical Licensed Products', rate_value='5')
        r2 = term('1-R02', product_scope='All other Licensed Products', rate_value='4')
        adj = lambda t: [{'description': 'deduct up to 50% of litigation costs', 'evidence_ids': ['x']}]
        u1 = unrated('2-R01', product_scope=u1_scope, adjustments=adj(1))
        u2 = unrated('2-R02', product_scope=u2_scope, adjustments=adj(2))
        return r1, r2, u1, u2

    def test_unemed_two_products_fold_to_the_right_rate(self):
        out, notes = consolidate(reading(*self.pair()))
        self.assertEqual(ids(out), ['1-R01', '1-R02'])
        for t in out['royalty_terms']: self.assertEqual(len(t['adjustments']), 1)
        self.assertEqual({(n['kept'], n['removed'][0]) for n in notes}, {('1-R01', '2-R01'), ('1-R02', '2-R02')})

    def test_all_other_is_not_compatible_with_a_named_scope(self):
        r1, r2, u1, u2 = self.pair(u1_scope='All other Licensed Products', u2_scope=None)
        # u1 ("all other") may only match the residual term; u2 has no scope so it cannot be placed
        out, notes = consolidate(reading(r1, r2, u1, u2))
        self.assertIn('2-R01', [n['removed'][0] for n in notes if n['rule'] == 'FOLD'])
        self.assertEqual([n['kept'] for n in notes if n['rule'] == 'FOLD'], ['1-R02'])
        self.assertIn('2-R02', ids(out))

    def test_still_ambiguous_attaches_nothing_and_raises_a_high_issue(self):
        r1, r2, u1, u2 = self.pair(u1_scope=None, u2_scope=None)
        ext = reading(r1, r2, u1)
        out, notes = consolidate(ext)
        self.assertEqual(ids(out), ['1-R01', '1-R02', '2-R01'])
        for t in out['royalty_terms'][:2]: self.assertEqual(t['adjustments'], [])
        issue = next(i for i in out['open_issues'] if i['kind'] == 'UNRESOLVED_DUPLICATE')
        self.assertEqual((issue['severity'], issue['status']), ('HIGH', 'OPEN'))
        self.assertIn('term 2-R01 has no rate', issue['description'])
        self.assertEqual(notes[0]['rule'], 'UNRESOLVED')
        self.assertEqual(sorted(issue), sorted(['issue_id', 'severity', 'kind', 'description', 'status', 'passage_ids']))

    def test_export_marks_unresolved_row_no(self):
        raw = fixture_rows()
        h = raw['Open Issues'][0]
        raw['Open Issues'].append([{'Document_ID': 'DOC-DEMO', 'Kind': 'UNRESOLVED_DUPLICATE', 'Severity': 'HIGH', 'Status': 'OPEN',
                                    'Issue_ID': 'U', 'Description': 'UNRESOLVED CROSS-CHUNK DUPLICATE: term R1 has no rate quoted and could be'}.get(k) for k in h])
        v = research_rows(raw)
        d = row(v[NAMES[0]], None, **{'Observation ID': 'DOC-DEMO:R1'})
        self.assertEqual(d['Usable for royalty benchmark'], 'NO')
        self.assertIn('unresolved cross-chunk duplicate', d['Benchmark note'])
        self.assertNotIn('not disclosed', d['Benchmark note'])


class A3TieredLabel(unittest.TestCase):
    def tiered_rows(self, status='DISCLOSED'):
        raw = fixture_rows()
        head = raw['Royalty Terms'][0]; t = dict(zip(head, raw['Royalty Terms'][1]))
        t.update(Structure='TIERED', Rate_Numeric=None, Rate_Value_Text=None, Disclosure_Status=status, Tier_Count=2)
        raw['Royalty Terms'][1] = [t.get(k) for k in head]
        th = raw['Tiers'][0]; base = dict(zip(th, raw['Tiers'][1]))
        raw['Tiers'] = [th]
        for n, rate in ((1, 4.0), (2, 7.0)):
            raw['Tiers'].append([dict(base, Sequence=n, Rate_Numeric=rate, Rate_Value_Text=str(rate)).get(k) for k in th])
        return raw

    def test_tiered_term_is_labelled_not_undisclosed(self):
        d = row(research_rows(self.tiered_rows())[NAMES[0]], None, **{'Observation ID': 'DOC-DEMO:R1'})
        self.assertIsNone(d['Royalty rate (%)'])                                   # never collapsed to one number
        self.assertEqual(d['Royalty rate as reported'], 'TIERED 4%–7% – see sheet 02')
        self.assertIn('tiered rate', d['Benchmark note']); self.assertNotIn('not disclosed', d['Benchmark note'])
        self.assertEqual(d['Usable for royalty benchmark'], 'NO')

    def test_redacted_tiered_term_shows_disclosed_tiers_but_is_not_usable(self):
        d = row(research_rows(self.tiered_rows('REDACTED'))[NAMES[0]], None, **{'Observation ID': 'DOC-DEMO:R1'})
        self.assertIn('partly redacted; disclosed tier 4%–7%', d['Benchmark note'])
        self.assertEqual(d['Royalty rate as reported'], 'PARTLY REDACTED – disclosed tier 4%–7%, see sheet 02')
        self.assertIsNone(d['Royalty rate (%)'])

    def test_plain_missing_rate_unchanged(self):
        note = benchmark_usable({'Rate_Numeric': None, 'Rate_Unit': 'PERCENT', 'Disclosure_Status': 'DISCLOSED', 'Family': 'PRODUCT_SALES'}, 'NO', '')[1]
        self.assertIn('not disclosed', note)


class A4QuoteChoice(unittest.TestCase):
    def test_payment_quote_contains_the_amount(self):
        raw = fixture_rows()
        raw['Other Payments'][1][raw['Other Payments'][0].index('Evidence_IDs')] = '["E3","E2"]'
        raw['Other Payments'][1][raw['Other Payments'][0].index('Amount_Text')] = '20000'
        eh = raw['Evidence'][0]
        raw['Evidence'].append([{'Document_ID': 'DOC-DEMO', 'Evidence_ID': 'E3', 'Role': 'CONDITION', 'Passage_ID': 'P20',
                                 'Exact_Quotation': 'terminate on 45 days notice'}.get(k) for k in eh])
        raw['Evidence'].append([{'Document_ID': 'DOC-DEMO', 'Evidence_ID': 'E2', 'Role': 'OTHER', 'Passage_ID': 'P13',
                                 'Exact_Quotation': 'a licence fee of $20,000'}.get(k) for k in eh])
        v = research_rows(raw)
        pay = [r for r in v[NAMES[2]][1:] if r[0] == 'P1'][0]
        self.assertEqual(pay[8],
                         'a licence fee of $20,000')

    def test_percent_amount_and_fallbacks(self):
        from royalty_research.m13_research_export import _best_evidence
        ev = {('D', 'a'): {'Role': 'CONDITION', 'Exact_Quotation': 'terminate in 45 days'},
              ('D', 'b'): {'Role': 'RATE', 'Exact_Quotation': 'something else'},
              ('D', 'c'): {'Role': 'OTHER', 'Exact_Quotation': 'equity of 9% of shares'}}
        self.assertEqual(_best_evidence(['a', 'b', 'c'], 'D', ev, '9%')['Exact_Quotation'], 'equity of 9% of shares')
        self.assertEqual(_best_evidence(['a', 'b', 'c'], 'D', ev, '77')['Exact_Quotation'], 'something else')   # RATE role
        self.assertEqual(_best_evidence(['a', 'c'], 'D', ev, None)['Exact_Quotation'], 'terminate in 45 days')  # first
        self.assertIsNone(_best_evidence(['zz'], 'D', ev, '9'))


class B1B2Variants(unittest.TestCase):
    def three(self, c1, c2, c3=None, rates=('4', '6', '8')):
        ts = [term('a', rate_value=rates[0], conditions=[cond(c1, 'c-a')] if c1 else []),
              term('b', rate_value=rates[1], conditions=[cond(c2, 'c-b')] if c2 else [])]
        if c3 is not None: ts.append(term('c', rate_value=rates[2], conditions=[cond(c3, 'c-c')] if c3 else []))
        return ts

    def test_b1_two_defaults_do_not_block_the_threshold_variants(self):
        ts = [term('d1', rate_value='5'), term('d2', rate_value='6'),
              term('t1', rate_value='7', conditions=[cond('when annual Net Sales exceed $10 million', 'c1')]),
              term('t2', rate_value='8', conditions=[cond('when annual Net Sales exceed $20 million', 'c2')])]
        out, notes = consolidate(reading(*ts))
        self.assertEqual(ids(out), ['d1', 'd2', 't1'])
        self.assertEqual(len(next(t for t in out['royalty_terms'] if t['term_id'] == 't1')['tiers']), 2)

    def test_b1_two_defaults_and_one_variant_nothing_merged(self):
        ts = [term('d1', rate_value='5'), term('d2', rate_value='6'),
              term('t1', rate_value='7', conditions=[cond('when annual Net Sales exceed $10 million', 'c1')])]
        self.assertEqual(ids(consolidate(reading(*ts))[0]), ['d1', 'd2', 't1'])

    def test_b2_phase_split_merges(self):
        ts = [term('a', rate_value='15', conditions=[cond('until the fifth anniversary of first commercial sale', 'c-a')]),
              term('b', rate_value='25', conditions=[cond('after the fifth anniversary of first commercial sale', 'c-b')])]
        out, notes = consolidate(reading(*ts))
        self.assertEqual(ids(out), ['a'])
        self.assertEqual([z['rate_value'] for z in out['royalty_terms'][0]['tiers']], ['15', '25'])

    def test_b2_ordinary_after_wording_does_not_merge(self):
        ts = [term('a', rate_value='15', conditions=[cond('payable within 30 days after quarter end', 'c-a')]),
              term('b', rate_value='25', conditions=[cond('payable within 30 days after quarter end', 'c-b')])]
        self.assertEqual(ids(consolidate(reading(*ts))[0]), ['a', 'b'])


class B3B5(unittest.TestCase):
    def test_b3_other_reduction_attaches_to_the_only_royalty(self):
        main = term('t1')
        red = term('t2', family='OTHER', structure='FORMULA', rate_value=None, rate_unit='UNKNOWN', disclosure_status='DISCLOSED',
                   base='Royalty payable', conditions=[cond('royalty is reduced by third-party royalties paid, but not below 2%', 'c-t2')])
        out, notes = consolidate(reading(main, red))
        self.assertEqual(ids(out), ['t1']); self.assertEqual(notes[0]['rule'], 'REDUCTION')

    def test_b3_two_royalties_stay_ambiguous(self):
        a, b = term('t1'), term('t3', base='Net Sales of Product B', product_scope='Product B')
        red = term('t2', family='OTHER', structure='FORMULA', rate_value=None, rate_unit='UNKNOWN', base='Royalty payable',
                   conditions=[cond('royalty is reduced by third-party royalties', 'c-t2')])
        self.assertEqual(ids(consolidate(reading(a, b, red))[0]), ['t1', 't3', 't2'])

    def test_b5_mixed_units_are_not_merged(self):
        a = term('a', rate_value='5', rate_unit='PERCENT', conditions=[cond('when annual Net Sales exceed $10 million', 'c1')])
        b = term('b', rate_value='2', rate_unit='CURRENCY_PER_UNIT', conditions=[cond('when annual Net Sales are less than $10 million', 'c2')])
        self.assertEqual(ids(consolidate(reading(a, b))[0]), ['a', 'b'])
        b['rate_unit'] = 'PERCENT'
        self.assertEqual(ids(consolidate(reading(a, b))[0]), ['a'])


class B4Minimum(unittest.TestCase):
    def test_label_in_condition_field_is_found(self):
        raw = fixture_rows()
        h = raw['Other Payments'][0]
        raw['Other Payments'].append([{'Payment_ID': 'G1', 'Document_ID': 'DOC-DEMO', 'Kind': 'GUARANTEE', 'Amount_Text': '100000',
                                       'Currency': 'USD', 'Basis': 'per year', 'Condition': 'Minimum annual royalty payable from 2027',
                                       'Evidence_IDs': 'E2'}.get(k) for k in h])
        d = row(research_rows(raw)[NAMES[0]], None, **{'Observation ID': 'DOC-DEMO:R1'})
        self.assertIn('G1', d['Minimum guarantee'])

    def test_unrelated_guarantee_stays_out(self):
        raw = fixture_rows()
        h = raw['Other Payments'][0]
        raw['Other Payments'].append([{'Payment_ID': 'G2', 'Document_ID': 'DOC-DEMO', 'Kind': 'GUARANTEE', 'Amount_Text': '1',
                                       'Basis': 'share price guarantee', 'Condition': 'if the minimum royalty is waived',
                                       'Evidence_IDs': 'E2'}.get(k) for k in h])
        d = row(research_rows(raw)[NAMES[0]], None, **{'Observation ID': 'DOC-DEMO:R1'})
        self.assertNotIn('G2', d['Minimum guarantee'])


class B6TierBounds(unittest.TestCase):
    def merged(self, c1, c2, q1, q2):
        a = term('a', rate_value='4', conditions=[cond(c1, 'c-a')], rate_evidence_ids=['r-a'])
        b = term('b', rate_value='6', conditions=[cond(c2, 'c-b')], rate_evidence_ids=['r-b'])
        ext = reading(a, b)
        quotes(ext, **{'c-a': q1, 'c-b': q2})
        out, _ = consolidate(ext)
        return out, out['royalty_terms'][0]['tiers']

    def test_bounds_from_less_than_and_or_more(self):
        out, tiers = self.merged('when annual Net Sales are less than $5 million', 'when annual Net Sales are $5 million or more',
                                 'when annual Net Sales are less than $5 million', 'when annual Net Sales are $5 million or more')
        self.assertEqual([(z['lower'], z['upper']) for z in tiers], [(None, '5000000'), ('5000000', None)])
        self.assertEqual(tiers[0]['measurement_period'], 'annual')
        self.assertIn('less than $5 million', tiers[0]['threshold_basis'])
        self.assertFalse([i for i in out['open_issues'] if i['kind'] == 'TIER_BOUNDS_NOT_PARSED'])

    def test_exceed_between_and_up_to(self):
        out, tiers = self.merged('Net Sales exceed $250,000,000 up to $500,000,000', 'Net Sales between 1 million and 2 million',
                                 'Net Sales exceed $250,000,000 up to $500,000,000', 'Net Sales between 1 million and 2 million')
        self.assertEqual([(z['lower'], z['upper']) for z in tiers], [('250000000', '500000000'), ('1000000', '2000000')])

    def test_bound_not_in_cited_quote_is_not_written(self):
        out, tiers = self.merged('when annual Net Sales are less than $5 million', 'when annual Net Sales are $5 million or more',
                                 'a quote without the figure', 'another quote without the figure')
        self.assertEqual([(z['lower'], z['upper']) for z in tiers], [(None, None), (None, None)])
        issue = [i for i in out['open_issues'] if i['kind'] == 'TIER_BOUNDS_NOT_PARSED']
        self.assertEqual((issue[0]['status'], issue[0]['severity']), ('OPEN', 'LOW'))
        self.assertIn('could not be read', next(i for i in out['open_issues'] if i['kind'] == 'CONSOLIDATED')['description'])

    def test_redacted_threshold_has_no_bound(self):
        out, tiers = self.merged('when annual Government Sales are less than [***] of total', 'when annual Government Sales are [***] or more',
                                 'less than [***] of total', '[***] or more')
        self.assertEqual([(z['lower'], z['upper']) for z in tiers], [(None, None), (None, None)])

    def test_stated_calculation_method(self):
        out, tiers = self.merged('only on that portion of Net Sales above $5 million', 'Net Sales of $5 million or less',
                                 'only on that portion of Net Sales above $5 million', 'Net Sales of $5 million or less')
        self.assertEqual(tiers[0]['calculation'], 'MARGINAL'); self.assertEqual(tiers[1]['calculation'], 'UNKNOWN')

    def test_section_numbers_are_not_bounds(self):
        out, tiers = self.merged('as provided in Section 4 above', 'when Net Sales exceed $3 million',
                                 'as provided in Section 4 above', 'when Net Sales exceed $3 million')
        # the first text has no threshold wording at all (so it is a default), the second reads a lower bound
        self.assertEqual([(z['lower'], z['upper']) for z in tiers], [(None, None), ('3000000', None)])

    def test_merged_reading_passes_schema_and_source_check_on_real_fixture(self):
        mapping = read_json(FIX / 'coldquanta_gov_map.json'); raw = read_json(FIX / 'coldquanta_gov_extraction.json')
        out, _ = consolidate(raw)
        self.assertEqual(validate_shape(out), [])
        self.assertEqual(source_check(mapping, out)['errors'], [])


class C1Percent(unittest.TestCase):
    def test_percent_sign_is_stripped_for_rates_only(self):
        for text in ('5%', '5.5 %', '5 percent', '5 per cent', ' 12.5% '):
            self.assertIsNotNone(_number(text, True), text)
        self.assertEqual(_number('5%', True), 5.0); self.assertEqual(_number('5.5 %', True), 5.5)
        self.assertIsNone(_number('5%'))                                           # amounts and thresholds are untouched
        self.assertEqual(_number('$5'), 5.0); self.assertEqual(_number('5', True), 5.0)
        self.assertIsNone(_number('5% of Net Sales', True))


if __name__ == '__main__':
    unittest.main()
