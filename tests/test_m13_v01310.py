"""v0.13.10: deterministic consolidation of one reading's royalty terms (fold, threshold variants, reductions)."""
from __future__ import annotations
import copy
import unittest
from pathlib import Path

from royalty_research.m13_consolidate import consolidate
from royalty_research.m13_two_reader import source_check
from royalty_research.m2_schema_check import validate_shape
from royalty_research.storage import read_json

FIX = Path(__file__).resolve().parent / 'fixtures' / 'm13_consolidate'


def term(tid, **kw):
    t = {'term_id': tid, 'family': 'PRODUCT_SALES', 'structure': 'FLAT', 'disclosure_status': 'DISCLOSED',
         'rate_value': '5', 'rate_unit': 'PERCENT', 'base': 'Net Sales', 'base_definition': None, 'product_scope': None,
         'territory_scope': None, 'effective_period': None, 'conditions': [], 'adjustments': [], 'tiers': [],
         'evidence_ids': [f'e-{tid}'], 'rate_evidence_ids': [f'e-{tid}'], 'base_evidence_ids': [f'e-{tid}']}
    t.update(kw)
    return t


def unrated(tid, **kw):
    d = dict(rate_value=None, rate_unit='UNKNOWN', structure='UNKNOWN', disclosure_status='NOT_VERIFIED', rate_evidence_ids=[])
    d.update(kw)
    return term(tid, **d)


def cond(text, eid):
    return {'text': text, 'evidence_ids': [eid]}


def reading(*terms):
    ids = sorted({e for t in terms for k in ('evidence_ids', 'rate_evidence_ids', 'base_evidence_ids') for e in t[k]})
    return {'royalty_terms': list(terms), 'evidence': [{'evidence_id': e, 'passage_id': 'P1'} for e in ids],
            'dispositions': [{'passage_id': 'P1', 'term_ids': [t['term_id'] for t in terms], 'percentage_dispositions': []}],
            'open_issues': []}


def ids(ext): return [t['term_id'] for t in ext['royalty_terms']]


class Fold(unittest.TestCase):
    def test_unrated_folds_into_quoted_same_base(self):
        a = unrated('1-t1', base='Net Sales of Licensed Products and Licensed Processes',
                    adjustments=[{'description': 'No multiple royalties', 'evidence_ids': ['x1']}], evidence_ids=['e-1-t1', 'x1'])
        b = term('c2-t1', base='Net Sales')
        out, notes = consolidate(reading(a, b))
        self.assertEqual(ids(out), ['c2-t1'])
        t = out['royalty_terms'][0]
        self.assertEqual(t['rate_value'], '5')
        self.assertIn('x1', t['evidence_ids']); self.assertIn('e-1-t1', t['evidence_ids'])
        self.assertEqual(t['adjustments'][0]['description'], 'No multiple royalties')
        self.assertEqual(out['dispositions'][0]['term_ids'], ['c2-t1'])
        self.assertEqual(notes[0]['rule'], 'FOLD')
        issue = out['open_issues'][0]
        self.assertEqual((issue['kind'], issue['status'], issue['severity']), ('CONSOLIDATED', 'RESOLVED', 'LOW'))
        self.assertIn('CONSOLIDATED: 1-t1 folded into c2-t1 (same family and base, no rate quoted)', issue['description'])

    def test_sublicense_wording_matches(self):
        a = unrated('1-t2', family='SUBLICENSING_RECEIPTS', base='All revenue received by Licensee from sublicensees of the Patent Rights')
        b = term('c2-t3', family='SUBLICENSING_RECEIPTS', base='Sublicense Revenue received by Licensee or Affiliates')
        self.assertEqual(ids(consolidate(reading(a, b))[0]), ['c2-t3'])

    def test_must_not_fold(self):
        base = reading(unrated('u', base='Net Sales'), term('q', base='Government Sales'))
        self.assertEqual(ids(consolidate(base)[0]), ['u', 'q'])                     # different base
        fam = reading(unrated('u', base='Net Sales'), term('q', family='SUBLICENSING_RECEIPTS', base='Net Sales'))
        self.assertEqual(ids(consolidate(fam)[0]), ['u', 'q'])                      # different family
        two = reading(unrated('u', base='Net Sales'), term('q1', base='Net Sales', product_scope='Product A'),
                      term('q2', base='Net Sales', product_scope='Product B'))
        self.assertEqual(len(consolidate(two)[0]['royalty_terms']), 3)              # ambiguous target (but q1/q2 not variants)
        both = reading(term('a', base='Net Sales'), term('b', base='Net Sales', rate_value='7', evidence_ids=['e-b']))
        self.assertEqual(ids(consolidate(both)[0]), ['a', 'b'])                     # both quoted: never folded
        scope = reading(unrated('u', base='Net Sales', product_scope='Software'), term('q', base='Net Sales', product_scope='Devices'))
        self.assertEqual(ids(consolidate(scope)[0]), ['u', 'q'])                    # conflicting scope


class Variants(unittest.TestCase):
    def variants(self):
        scope = 'Licensed Products that are not Licensed Software Products'
        return [term('t1', rate_value=None, rate_unit='REDACTED', disclosure_status='REDACTED', product_scope=scope + '; Non-Government Sales'),
                term('t2', rate_value=None, rate_unit='REDACTED', disclosure_status='REDACTED', product_scope=scope + '; Government Sales',
                     conditions=[cond('annual Government Sales are less than a redacted share', 'c-t2')]),
                term('t3', rate_value=None, rate_unit='REDACTED', disclosure_status='REDACTED', product_scope=scope + '; Government Sales',
                     conditions=[cond('annual Government Sales are a redacted share or more', 'c-t3')])]

    def test_threshold_variants_become_tiers(self):
        out, notes = consolidate(reading(*self.variants()))
        self.assertEqual(ids(out), ['t1'])
        t = out['royalty_terms'][0]
        self.assertEqual(t['structure'], 'TIERED'); self.assertEqual(len(t['tiers']), 3)
        self.assertEqual([z['sequence'] for z in t['tiers']], [1, 2, 3])
        self.assertEqual(t['tiers'][0]['threshold_basis'], 'Non-Government Sales')
        self.assertIn('less than', t['tiers'][1]['threshold_basis'])
        self.assertEqual(t['tiers'][2]['threshold_evidence_ids'], ['c-t3'])
        self.assertTrue({'e-t1', 'e-t2', 'e-t3'} <= set(t['evidence_ids']))
        self.assertEqual(out['dispositions'][0]['term_ids'], ['t1'])
        self.assertEqual(notes[0]['removed'], ['t2', 't3'])

    def test_numeric_rates_keep_each_tier_rate(self):
        v = self.variants()
        for t, r in zip(v, ('3', '4', '5')): t.update(rate_value=r, rate_unit='PERCENT')
        t = consolidate(reading(*v))[0]['royalty_terms'][0]
        self.assertEqual([z['rate_value'] for z in t['tiers']], ['3', '4', '5'])
        self.assertIsNone(t['rate_value'])

    def test_different_bases_and_scopes_stay_separate(self):
        gov = term('g', base='Government Sales', conditions=[cond('less than X', 'cg')])
        net = term('n', base='Net Sales')
        self.assertEqual(ids(consolidate(reading(net, gov))[0]), ['n', 'g'])
        soft = term('s', base='Net Sales', product_scope='Licensed Software Products', conditions=[cond('more than X', 'cs')])
        hard = term('h', base='Net Sales', product_scope='Licensed Products that are not Licensed Software Products')
        self.assertEqual(ids(consolidate(reading(hard, soft))[0]), ['h', 's'])
        terr = [term('a', territory_scope='US'), term('b', territory_scope='EU', conditions=[cond('more than X', 'cb')])]
        self.assertEqual(ids(consolidate(reading(*terr))[0]), ['a', 'b'])

    def test_not_confident_stays_separate(self):
        nonthr = [term('a', conditions=[cond('sold in a store', 'ca')]), term('b', conditions=[cond('sold online', 'cb')])]
        self.assertEqual(ids(consolidate(reading(*nonthr))[0]), ['a', 'b'])         # conditions are not thresholds
        twodef = [term('a'), term('b'), term('c', conditions=[cond('more than X', 'cc')])]
        self.assertEqual(len(consolidate(reading(*twodef))[0]['royalty_terms']), 3)  # two terms without any threshold
        same = [term('a', conditions=[cond('more than X', 'ca')]), term('b', conditions=[cond('more than X', 'cb')])]
        self.assertEqual(ids(consolidate(reading(*same))[0]), ['a', 'b'])           # identical threshold: not distinguishable


class Reductions(unittest.TestCase):
    def test_reduction_with_explicit_id_reference(self):
        main = term('t1', rate_value=None, rate_unit='REDACTED', disclosure_status='REDACTED', structure='TIERED',
                    adjustments=[{'description': 'Third-party royalty stacking reduction (see t2)', 'evidence_ids': ['e-t1']}])
        red = term('t2', family='OTHER', structure='UNKNOWN', rate_value=None, rate_unit='REDACTED', disclosure_status='REDACTED',
                   base='Net Sales of a given Licensed Product (aggregate royalties to all recipients)',
                   conditions=[cond('Applies when total royalties exceed a redacted share', 'c-t2')],
                   adjustments=[{'description': 'Each recipient reduced proportionally', 'evidence_ids': ['a-t2']}])
        out, notes = consolidate(reading(main, red))
        self.assertEqual(ids(out), ['t1'])
        adj = out['royalty_terms'][0]['adjustments']
        self.assertEqual(len(adj), 2)
        self.assertIn('reduced proportionally', adj[1]['description'])
        self.assertTrue({'e-t2', 'c-t2', 'a-t2'} <= set(adj[1]['evidence_ids']))
        self.assertEqual(notes[0]['rule'], 'REDUCTION')

    def test_stacking_floor_with_figures_single_candidate(self):
        main = term('t1')
        red = term('t2', rate_value='50', base='Royalty reduction for third-party royalties (offset), not below 2%',
                   conditions=[cond('reduced by 50% of third-party royalties but not below 2%', 'c-t2')])
        out, _ = consolidate(reading(main, red))
        self.assertEqual(ids(out), ['t1'])
        d = out['royalty_terms'][0]['adjustments'][0]['description']
        self.assertIn('50', d); self.assertIn('not below 2%', d)

    def test_ambiguous_target_stays_separate(self):
        a, b = term('t1'), term('t2', base='Net Sales of Product B', product_scope='Product B')
        red = term('t3', base='Anti-stacking reduction of royalty', rate_value='50')
        self.assertEqual(len(consolidate(reading(a, b, red))[0]['royalty_terms']), 3)

    def test_ordinary_royalty_with_adjustment_text_is_not_a_reduction(self):
        t = term('t1', adjustments=[{'description': 'Royalty reduced by 50% if third-party royalties are paid', 'evidence_ids': ['e-t1']}])
        other = term('t2', base='Net Sales of Product B', product_scope='Product B')
        self.assertEqual(ids(consolidate(reading(t, other))[0]), ['t1', 't2'])

    def test_other_family_term_without_reduction_wording_is_kept(self):
        main = term('t1', adjustments=[{'description': 'see t2', 'evidence_ids': ['e-t1']}])
        other = term('t2', family='OTHER', rate_value=None, rate_unit='REDACTED', base='Earned Royalty rates under Section 7.6',
                     conditions=[cond('Applies if licensee challenges a patent', 'c-t2')])
        self.assertEqual(ids(consolidate(reading(main, other))[0]), ['t1', 't2'])


class RealData(unittest.TestCase):
    def load(self, name):
        return read_json(FIX / f'{name}_map.json'), read_json(FIX / f'{name}_extraction.json')

    def evidence_of(self, ext):
        return {e for t in ext['royalty_terms'] for e in _all(t)}

    def check(self, name, before, after, rule_count):
        mapping, raw = self.load(name)
        raw_copy = copy.deepcopy(raw)
        out, notes = consolidate(raw)
        self.assertEqual(raw, raw_copy)                                              # input never modified
        self.assertEqual((len(raw['royalty_terms']), len(out['royalty_terms'])), (before, after))
        self.assertEqual(len(notes), rule_count)
        self.assertEqual(validate_shape(out), [])
        self.assertTrue(self.evidence_of(raw) <= self.evidence_of(out))             # every cited evidence ID preserved
        self.assertEqual(source_check(mapping, raw)['errors'], [])
        self.assertEqual(source_check(mapping, out)['errors'], [])
        self.assertEqual(sum(1 for i in out['open_issues'] if i['kind'] == 'CONSOLIDATED'), rule_count)
        return out

    def test_coldquanta_government_sales_variants(self):
        out = self.check('coldquanta_gov', 5, 3, 1)
        t = out['royalty_terms'][0]
        self.assertEqual((t['term_id'], len(t['tiers'])), ('c3-t1', 3))
        self.assertIn('c3-t4', ids(out)); self.assertIn('c3-t5', ids(out))          # software and sublicense stay separate

    def test_coldquanta_chunk_duplicates(self):
        out = self.check('coldquanta_chunks', 5, 3, 2)
        self.assertEqual(ids(out), ['c2-t1', 'c2-t2', 'c2-t3'])

    def test_vxm01_unchanged(self):
        out = self.check('vxm01', 3, 3, 0)
        self.assertEqual(len(out['royalty_terms']), 3)

    def test_kala_anti_stacking_terms_become_adjustments(self):
        raw = read_json(FIX / 'kala_antistacking_extraction.json')
        out, notes = consolidate(raw)
        self.assertEqual({n['removed'][0] for n in notes}, {'C2-T02', 'C2-T03'})
        main = next(t for t in out['royalty_terms'] if t['term_id'] == 'C2-T01')
        self.assertEqual(len(main['adjustments']), len(next(t for t in raw['royalty_terms'] if t['term_id'] == 'C2-T01')['adjustments']) + 2)
        self.assertIn('C2-T04', ids(out))                                            # patent-challenge rate change stays


def _all(t):
    out = set(t['evidence_ids'] + t['rate_evidence_ids'] + t['base_evidence_ids'])
    for z in t['conditions'] + t['adjustments']: out |= set(z['evidence_ids'])
    for z in t['tiers']: out |= set(z['evidence_ids']) | set(z['threshold_evidence_ids'])
    return out


if __name__ == '__main__':
    unittest.main()
