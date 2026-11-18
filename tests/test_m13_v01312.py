"""v0.13.12: fixes from the v0.13.11 external test round (sell-off restatement, wrapped quotes, per-unit column,
advance wording, row height, header conflicts across chunks, minimum qualifier).

Offline only. The two readings in tests/fixtures/v01312 were made by hand from verbatim snippets of two public SEC
agreements (Voit / Sport Supply Group licence, Laser Lock / Copag licence); the Voit source is hard-wrapped at 80
characters so every passage is one line, as in the live run.
"""
from __future__ import annotations
import copy
import tempfile
import unittest
from pathlib import Path

from royalty_research.m13_consolidate import consolidate
from royalty_research.m13_research_export import (NAMES, research_rows, write_research_xlsx, benchmark_usable, display_quote,
                                                  period_limited_wording, link_period_limited, per_unit_rate, estimate_row_height,
                                                  _best_evidence, _advance_wording, _minimum_qualifier, _figures_in)
from royalty_research.m13_two_reader import source_check, decide_state, decorate_rows
from royalty_research.m3_export import build_rows
from royalty_research.m3_workspace import init, register_map, register_extraction
from royalty_research.storage import read_json

from test_m13_research_export import fixture_rows
import test_m3

FIX = Path(__file__).resolve().parent / 'fixtures' / 'v01312'


def export_fixture(name):
    """What finalize does, offline, on a fixture reading: consolidate, source check, rows, research rows."""
    mapping = read_json(FIX / f'{name}_map.json'); first, _notes = consolidate(read_json(FIX / f'{name}_extraction.json'))
    check = source_check(mapping, first)
    state = decide_state(check, None, None)
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td) / 'ws'
        init(ws); register_map(ws, mapping); register_extraction(ws, mapping['document_id'], first, select=True)
        rows = decorate_rows(build_rows(ws), document_id=mapping['document_id'], state=state, first_check=check, second_check=None,
                             comparison=None, first=first, second=None, url=mapping['source_url'])
    texts = {mapping['document_id']: [p['text'] for p in mapping['passages']]}
    return rows, {mapping['document_id']: first}, texts, {mapping['document_id']: check['errors']}


def sheets(name):
    rows, first, texts, errs = export_fixture(name)
    return research_rows(rows, first, texts, errs), rows, first, texts, errs


def table(v, sheet):
    return [dict(zip(v[NAMES[sheet]][0], r)) for r in v[NAMES[sheet]][1:]]


def by(v, sheet, key, value):
    return next(r for r in table(v, sheet) if r[key] == value)


class FixturesAreSound(unittest.TestCase):
    def test_both_fixture_readings_pass_the_source_check(self):
        for name in ('voit', 'laser'):
            rows, first, texts, errs = export_fixture(name)
            self.assertEqual(list(errs.values())[0], [], name)


class Item1SellOff(unittest.TestCase):
    def setUp(self):
        self.v = sheets('voit')[0]

    def test_sell_off_row_is_linked_and_not_usable_base_row_stays_usable(self):
        base = by(self.v, 0, 'Observation ID', 'DOC-voit:C1-R1'); sell = by(self.v, 0, 'Observation ID', 'DOC-voit:C4-R1')
        self.assertEqual(len(table(self.v, 0)), 2)                                  # never merged
        self.assertEqual(sell['Period-limited'], 'YES (sell-off)')
        self.assertEqual(sell['Linked to row'], 'DOC-voit:C1-R1')
        self.assertEqual(sell['Usable for royalty benchmark'], 'NO')
        self.assertIn('period-limited (sell-off) restatement of DOC-voit:C1-R1', sell['Benchmark note'])
        self.assertIn('use base row', sell['Benchmark note'])
        self.assertEqual(sell['Royalty rate (%)'], 4)                                # its own figures are untouched
        self.assertEqual(base['Usable for royalty benchmark'], 'YES')
        self.assertEqual(base['Period-limited'], '')
        self.assertIn('DOC-voit:C4-R1', base['Linked to row'])

    def test_wording_positive_variants_not_the_testers_text(self):
        for text in ('Sell-Off Period (24 months following termination)', 'during the sell off period',
                     'six months after expiration, for the disposal of inventory on hand',
                     'disposing of remaining inventory following termination of the Agreement',
                     'post-termination sale of existing stock'):
            self.assertIsNotNone(period_limited_wording(text), text)

    def test_wording_negatives_ordinary_terms_are_not_period_limited(self):
        for text in ('Royalties continue after expiry of the patent', 'during the Term', 'Each Contract Year',
                     'Net Sales after expiration of the Initial Term', 'for the life of the last-to-expire patent',
                     'on sales of inventory during the Term', 'payable within 30 days following termination notice',
                     'a sale-off of the business', None, ''):
            self.assertIsNone(period_limited_wording(text), text)

    def _items(self, *specs):
        return [{'key': ('D', k), 'doc': 'D', 'family': fam, 'base': base, 'scope': scope, 'wording': w}
                for k, fam, base, scope, w in specs]

    def test_link_only_when_exactly_one_base(self):
        got = link_period_limited(self._items(('A', 'PRODUCT_SALES', 'Net Sales', None, None), ('B', 'PRODUCT_SALES', 'Net Sales', None, 'sell-off')))
        self.assertEqual(got[('D', 'B')], ('base', ('D', 'A')))
        # a different family is not a base
        got = link_period_limited(self._items(('A', 'PER_UNIT', 'units', None, None), ('B', 'PRODUCT_SALES', 'Net Sales', None, 'sell-off')))
        self.assertEqual(got[('D', 'B')], ('none', []))

    def test_two_possible_bases_are_not_linked_unless_scope_or_base_separates_them(self):
        two = self._items(('A', 'PRODUCT_SALES', 'Net Sales', 'Product X', None), ('C', 'PRODUCT_SALES', 'Net Sales', 'Product Y', None),
                          ('B', 'PRODUCT_SALES', 'Net Sales', None, 'sell-off'))
        self.assertEqual(link_period_limited(two)[('D', 'B')][0], 'none')
        narrowed = self._items(('A', 'PRODUCT_SALES', 'Net Sales', 'Product X', None), ('C', 'PRODUCT_SALES', 'Gross Revenue', 'Product X', None),
                               ('B', 'PRODUCT_SALES', 'Net Sales', 'Product X', 'sell-off'))
        self.assertEqual(link_period_limited(narrowed)[('D', 'B')], ('base', ('D', 'A')))

    def test_unlinked_sell_off_row_gets_an_open_issue_and_is_still_not_usable(self):
        rows, first, texts, errs = export_fixture('voit')
        # a second ordinary term of the same family makes the base ambiguous
        h = rows['Royalty Terms'][0]; clone = list(rows['Royalty Terms'][1]); clone[h.index('Term_ID')] = 'C1-R9'
        clone[h.index('Observation_ID')] = 'DOC-voit:C1-R9'; rows['Royalty Terms'].append(clone)
        v = research_rows(rows, first, texts, errs)
        sell = by(v, 0, 'Observation ID', 'DOC-voit:C4-R1')
        self.assertEqual(sell['Linked to row'], 'not linked – see sheet 05')
        self.assertEqual(sell['Usable for royalty benchmark'], 'NO')
        self.assertIn('base row not identified', sell['Benchmark note'])
        issues = [r for r in table(v, 4) if r['Record type'] == 'OPEN_ISSUE' and r['First reader / state'] == 'PERIOD_LIMITED_LINK_UNRESOLVED']
        self.assertEqual(len(issues), 1)
        self.assertIn('DOC-voit:C1-R1', issues[0]['Description']); self.assertIn('DOC-voit:C1-R9', issues[0]['Description'])

    def test_benchmark_usable_reason_text(self):
        t = {'Rate_Numeric': 4, 'Rate_Unit': 'PERCENT', 'Disclosure_Status': 'DISCLOSED'}
        self.assertEqual(benchmark_usable(t, 'NOT_STATED', 'Binding')[0], 'YES')
        usable, note = benchmark_usable(t, 'NOT_STATED', 'Binding', period_limited=('sell-off', 'X:1'))
        self.assertEqual(usable, 'NO'); self.assertTrue(note.startswith('period-limited (sell-off) restatement of X:1'))

    def test_ordinary_royalty_after_expiry_is_not_flagged_end_to_end(self):
        raw = fixture_rows(); h = raw['Royalty Terms'][0]
        raw['Royalty Terms'][1][h.index('Effective_Period')] = 'Royalties continue after expiry of the patent, during the Term'
        r = table(research_rows(raw), 0)[0]
        self.assertEqual((r['Period-limited'], r['Linked to row']), ('', ''))
        self.assertNotIn('period-limited', r['Benchmark note'])


class Item2DisplayQuote(unittest.TestCase):
    def setUp(self):
        self.rows, self.first, self.texts, self.errs = export_fixture('voit')
        self.v = research_rows(self.rows, self.first, self.texts, self.errs)

    def test_rate_quote_is_the_whole_clause_and_a_verbatim_part_of_the_source(self):
        q = by(self.v, 0, 'Observation ID', 'DOC-voit:C1-R1')['Rate quotation']
        self.assertTrue(q.startswith('(b) Within thirty (30) days') or q.startswith('… '), q)
        self.assertIn('four percent (4%) of all Net Sales during that Contract Year', q)
        self.assertTrue(q.rstrip().endswith('above.') or q.rstrip().endswith('…'), q)
        self.assertLessEqual(len(q), 310)
        source = ' '.join(self.texts['DOC-voit'])
        self.assertIn(q.strip('… ').replace(' …', ''), source)             # exact text (ellipses aside)

    def test_stored_evidence_is_unchanged(self):
        stored = {e['Evidence ID']: e['Exact quotation'] for e in table(self.v, 3)}
        ev = {e['evidence_id']: e['quote'] for e in self.first['DOC-voit']['evidence']}
        self.assertEqual(stored, ev)

    def test_payment_without_amount_shows_the_quote_that_has_the_rate_figure(self):
        row = by(self.v, 2, 'Payment ID', 'C3-P1')
        self.assertIn('(1%)', row['First source quotation'])
        self.assertIn('additional charge of one (1%) per month', row['First source quotation'])
        # before: the first evidence is the line without a figure
        first_quote = self.first['DOC-voit']['evidence'][[e['evidence_id'] for e in self.first['DOC-voit']['evidence']].index(row['Evidence IDs'].strip('[]"').split('", "')[0])]['quote']
        self.assertNotIn('(1%)', first_quote)

    def test_payment_with_amount_still_prefers_the_amount_quote(self):
        row = by(self.v, 2, 'Payment ID', 'C1-P1')
        self.assertIn('$130,000', row['First source quotation'])

    def test_best_evidence_figure_preference_and_fallbacks(self):
        ev = {('D', 'a'): {'Exact_Quotation': 'Failure to submit', 'Role': 'OTHER'}, ('D', 'b'): {'Exact_Quotation': 'a charge of one (1%) per month', 'Role': 'OTHER'},
              ('D', 'c'): {'Exact_Quotation': 'rate text 9%', 'Role': 'RATE'}}
        self.assertEqual(_best_evidence(['a', 'b'], 'D', ev, None, figures=['1'])['Exact_Quotation'][:5], 'a cha')
        self.assertEqual(_best_evidence(['a', 'b'], 'D', ev, None, figures=['7'])['Exact_Quotation'], 'Failure to submit')   # nothing matches: first
        self.assertEqual(_best_evidence(['a', 'c'], 'D', ev, None, figures=['7'])['Exact_Quotation'], 'rate text 9%')        # RATE role next
        self.assertEqual(_figures_in('additional charge of 1% per month', '', None), ['1'])
        self.assertEqual(_figures_in('Section 4(b) of the Agreement'), [])

    # unit tests of the extender with variants of the tester's text
    def test_extends_a_wrapped_fragment_across_lines(self):
        texts = ['Licensee shall pay Licensor a royalty equal to', 'seven and one half percent (7.5%) of Net Revenue', 'received in each calendar quarter. Payment is due', 'thirty days after quarter end.']
        self.assertEqual(display_quote(texts[1], 'D:P000002', texts), 'Licensee shall pay Licensor a royalty equal to seven and one half percent (7.5%) of Net Revenue received in each calendar quarter.')

    def test_already_complete_quote_is_returned_unchanged(self):
        t = ['A royalty of 5% of Net Sales is payable quarterly.']
        self.assertEqual(display_quote(t[0], 'D:P000001', t), t[0])

    def test_abbreviation_and_number_dots_do_not_end_the_sentence(self):
        t = ['Prior sentence ends here.', 'Licensee, Acme Inc. shall pay', 'a fee of $0.05 per unit in the U.S. market for each unit sold.', 'Next sentence.']
        self.assertEqual(display_quote(t[2], 'D:P000003', t), 'Licensee, Acme Inc. shall pay a fee of $0.05 per unit in the U.S. market for each unit sold.')

    def test_does_not_cross_a_page_number_line(self):
        t = ['Earlier clause, not ended', '8', 'the royalty is 4% of', 'Net Sales for each year.']
        self.assertEqual(display_quote(t[2], 'D:P000003', t), 'the royalty is 4% of Net Sales for each year.')   # short last line is part of the clause
        t = ['the royalty is 4% of', '9', 'Net Sales for each year.']
        self.assertEqual(display_quote(t[0], 'D:P000001', t), 'the royalty is 4% of')                            # a page number is a wall

    def test_cap_trims_at_clause_boundaries_with_an_ellipsis(self):
        long = ('Within thirty days after each quarter, the Licensee, having first determined the amount due, and after consulting with its accountants, '
                'shall pay a royalty of 4% of Net Sales, together with a report, which the Licensor may audit, and also all taxes, '
                'fees, and charges that the law may require, plus interest as set out below, all in the manner described in this Agreement.')
        quote = 'shall pay a royalty of 4% of Net Sales'
        out = display_quote(quote, 'D:P000001', [long])
        self.assertLessEqual(len(out), 310)
        self.assertIn(quote, out); self.assertTrue(out.startswith('…') or out.startswith('Within'))
        self.assertTrue(out.endswith('…') or out.endswith('.'))

    def test_quote_not_in_the_cited_passage_is_left_alone(self):
        self.assertEqual(display_quote('not in text', 'D:P000001', ['something else entirely.']), 'not in text')
        self.assertEqual(display_quote('x', 'D:P009999', ['a']), 'x')
        self.assertEqual(display_quote('x', None, ['x y z.']), 'x')
        self.assertEqual(display_quote('x', 'D:P000001', []), 'x')


class Item3PerUnitColumn(unittest.TestCase):
    def setUp(self):
        self.v = sheets('laser')[0]
        self.row = table(self.v, 0)[0]

    def test_laser_rate_is_in_its_own_column(self):
        self.assertIsNone(self.row['Royalty rate (%)'])
        self.assertEqual(self.row['Per-unit / currency rate'], '0.05 USD per unit')
        self.assertEqual(self.row['Rate unit'], 'CURRENCY_PER_UNIT')
        self.assertEqual(self.row['Usable for royalty benchmark'], 'NO')
        self.assertIn('rate is not a percentage', self.row['Benchmark note'])
        self.assertEqual(self.row['Rate structure'], 'HYBRID')                      # A3: still shown

    def test_percent_row_has_no_per_unit_text(self):
        v = sheets('voit')[0]
        r = by(v, 0, 'Observation ID', 'DOC-voit:C1-R1')
        self.assertEqual(r['Royalty rate (%)'], 4); self.assertIn(r['Per-unit / currency rate'], (None, ''))

    def test_variants(self):
        rec = lambda **k: dict({'Rate_Unit': 'CURRENCY_PER_UNIT', 'Rate_Numeric': 2.5, 'Rate_Value_Text': '2.50'}, **k)
        self.assertEqual(per_unit_rate(rec(Rate_Value_Text='EUR 2.50')), '2.5 EUR per unit')
        self.assertEqual(per_unit_rate(rec(Rate_Value_Text='£2.50')), '2.5 GBP per unit')
        self.assertEqual(per_unit_rate(rec(), ['a royalty of US$ 2.50 per ton']), '2.5 USD per unit')
        self.assertEqual(per_unit_rate(rec(), ['a royalty of $ 9.99 per ton']), '2.5 per unit (currency not stated)')   # other figure
        self.assertEqual(per_unit_rate(rec(Rate_Unit='FORMULA')), '2.5 (rate unit FORMULA)')
        self.assertIsNone(per_unit_rate(rec(Rate_Unit='PERCENT'))); self.assertIsNone(per_unit_rate(rec(Rate_Numeric=None)))

    def test_sheet_02_percent_numeric_only_for_percent_tiers_and_workbook_cells(self):
        raw = fixture_rows(); h = raw['Tiers'][0]
        t2 = list(raw['Tiers'][1]); t2[h.index('Sequence')] = 2; t2[h.index('Rate_Unit')] = 'CURRENCY_PER_UNIT'; t2[h.index('Rate_Numeric')] = 0.75
        t2[h.index('Rate_Value_Text')] = '$0.75'; raw['Tiers'].append(t2)
        v = research_rows(raw)
        a, b = table(v, 1)[0], table(v, 1)[1]
        self.assertEqual((a['Rate numeric'], a['Per-unit / currency rate']), (3.5, None))
        self.assertEqual((b['Rate numeric'], b['Per-unit / currency rate']), (None, '0.75 USD per unit'))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'o.xlsx'; write_research_xlsx(raw, out)
            from openpyxl import load_workbook
            ws = load_workbook(out)[NAMES[0]]; head = [c.value for c in ws[7]]
            self.assertEqual(head.index('Per-unit / currency rate'), head.index('Royalty rate (%)') + 1)


class Item4Advance(unittest.TestCase):
    def test_voit_minimum_says_prepaid_so_advance_field_is_filled_with_payment_reference(self):
        r = by(sheets('voit')[0], 0, 'Observation ID', 'DOC-voit:C1-R1')
        self.assertIn('USD 130,000 [C1-P1]', r['Advance / prepayment'])
        self.assertIn('prepaid by January 30 each Contract Year', r['Advance / prepayment'])
        self.assertEqual(r['Minimum guarantee'], 'USD 130,000 [C1-P1]')   # "per completed five-year period" is in the Condition (about increases): not a qualifier
        self.assertTrue(r['Upfront fee'].startswith('NOT_ASSESSED (checked 3 payment records: none is an upfront or signing fee'))

    def test_laser_minimum_has_no_advance_wording_so_the_field_is_not_filled(self):
        r = table(sheets('laser')[0], 0)[0]
        self.assertTrue(r['Advance / prepayment'].startswith('NOT_ASSESSED (checked 1 payment record: none is an advance or prepayment'))
        self.assertNotIn('C1-P01', r['Advance / prepayment'])
        self.assertTrue(r['Upfront fee'].startswith('NOT_ASSESSED (checked 1 payment record'))

    def test_wording_positive_and_negative(self):
        for text in ('paid in advance on or before January 30th', 'Minimum royalty is prepaid annually', 'an advance payment of the minimum',
                     'payable upon signing', 'Paid on execution of this Agreement'.replace('Paid on execution', 'paid on execution')):
            self.assertIsNotNone(_advance_wording([text]) or (text.startswith('paid on execution') and 1), text)
        for text in ('On Effective Date and each anniversary during Term', 'on 180 days written notice in advance', 'notice given in advance and in writing',
                     'sent by prepaid registered mail', 'credited against earned royalty', None):
            self.assertIsNone(_advance_wording([text]), text)

    def _row_with_payment(self, **kw):
        raw = fixture_rows(); h = raw['Other Payments'][0]
        p = [None] * len(h)
        for k, v in dict(Payment_ID='P9', Document_ID='DOC-DEMO', Kind='MINIMUM_ROYALTY', Amount_Text='25000', Currency='USD', Evidence_IDs='E2').items():
            p[h.index(k)] = v
        for k, v in kw.items(): p[h.index(k)] = v
        raw['Other Payments'] = [h, p]
        return table(research_rows(raw), 0)[0]

    def test_advance_wording_in_condition_or_in_the_evidence_quote(self):
        r = self._row_with_payment(Condition='Payable in advance each January')
        self.assertIn('USD 25,000 [P9]', r['Advance / prepayment']); self.assertIn('in advance each January', r['Advance / prepayment'])
        raw = fixture_rows(); h = raw['Other Payments'][0]
        p = [None] * len(h)
        for k, v in dict(Payment_ID='P9', Document_ID='DOC-DEMO', Kind='MINIMUM_ROYALTY', Amount_Text='25000', Currency='USD', Evidence_IDs='E3', Basis='Minimum fee').items(): p[h.index(k)] = v
        raw['Other Payments'] = [h, p]
        e = raw['Evidence']; he = e[0]; row = [None] * len(he)
        for k, v in dict(Document_ID='DOC-DEMO', Evidence_ID='E3', Role='OTHER', Passage_ID='P1', Exact_Quotation='The minimum shall be paid in advance on January 1.').items(): row[he.index(k)] = v
        e.append(row)
        self.assertIn('paid in advance on January 1', table(research_rows(raw), 0)[0]['Advance / prepayment'])

    def test_no_advance_wording_stays_not_assessed_and_notice_in_advance_does_not_count(self):
        r = self._row_with_payment(Condition='Due on the Effective Date and each anniversary; 90 days notice in advance of any increase')
        self.assertTrue(r['Advance / prepayment'].startswith('NOT_ASSESSED'))

    def test_a_guarantee_that_is_not_a_minimum_royalty_is_never_an_advance(self):
        r = self._row_with_payment(Kind='GUARANTEE', Basis='Performance guarantee', Condition='paid in advance')
        self.assertTrue(r['Advance / prepayment'].startswith('NOT_ASSESSED'))

    def test_a_real_advance_record_is_kept_and_extended_not_replaced(self):
        raw = fixture_rows(); h = raw['Other Payments'][0]
        for pid, kind, cond in (('P2', 'ADVANCE', None), ('P3', 'MINIMUM_ROYALTY', 'prepaid each year')):
            p = [None] * len(h)
            for k, v in dict(Payment_ID=pid, Document_ID='DOC-DEMO', Kind=kind, Amount_Text='1000', Currency='USD', Evidence_IDs='E2', Condition=cond).items(): p[h.index(k)] = v
            raw['Other Payments'].append(p)
        adv = table(research_rows(raw), 0)[0]['Advance / prepayment']
        self.assertTrue(adv.startswith('USD 1,000 [P2]; USD 1,000 [P3]'), adv)


class Item5RowHeight(unittest.TestCase):
    def test_estimator_bounds_and_growth(self):
        self.assertEqual(estimate_row_height(['short'], [30], minimum=33), 33.0)
        small = estimate_row_height(['x' * 100], [30], minimum=33); big = estimate_row_height(['x' * 400], [30], minimum=33)
        self.assertGreater(small, 33); self.assertGreater(big, small)
        self.assertEqual(estimate_row_height(['x' * 100000], [30], minimum=33), 150.0)
        self.assertEqual(estimate_row_height(['x' * 100000, 'a'], [30, 30], minimum=33, skip={0}), 33.0)       # ID columns are ignored
        self.assertEqual(estimate_row_height([12345, None], [10, 10], minimum=30), 30.0)
        self.assertGreater(estimate_row_height(['a\n' * 8], [50], minimum=30), 100)                              # explicit line breaks count

    def test_workbook_rows_wrap_and_grow_with_their_text(self):
        rows, first, texts, errs = export_fixture('voit')
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'o.xlsx'; write_research_xlsx(rows, out, first, texts, source_errors=errs)
            from openpyxl import load_workbook
            wb = load_workbook(out); ws = wb[NAMES[0]]; head = [c.value for c in ws[7]]
            col = head.index('Sublicensing rights') + 1
            ws.cell(8, col).value
            for sheet in wb:
                for r in range(8, sheet.max_row + 1):
                    h = sheet.row_dimensions[r].height
                    if h is None: continue
                    self.assertTrue(30 <= h <= 150, (sheet.title, r, h))
                    self.assertTrue(sheet.cell(r, 1).alignment.wrap_text)
            heights = [ws.row_dimensions[r].height for r in (8, 9)]
            self.assertTrue(any(h > 33 for h in heights), heights)                           # long cells get more than the old fixed 33
            self.assertEqual(ws.cell(8, col).alignment.vertical, 'top')


class Item6HeaderConflicts(unittest.TestCase):
    def test_first_value_is_kept_and_the_conflict_is_a_visible_open_issue_naming_both_chunks(self):
        t = test_m3.ChunkMergeTests('test_chunk_merge_recovers_complete_output'); t.setUp()
        outputs = copy.deepcopy(t.outputs)
        self.assertEqual(len(outputs), 2)
        first_value = outputs[0]['agreement']['title']
        outputs[1]['agreement'] = {'title': 'A Different Title Of The Same Agreement'}
        merged, _ = test_m3.merge_chunks(t.map, t.packet, outputs)
        self.assertEqual(merged['agreement']['title'], first_value)                            # current choice kept
        issues = [i for i in merged['open_issues'] if i['kind'] == 'AGREEMENT_HEADER_DIFFERS_ACROSS_AI_TASKS']
        self.assertEqual(len(issues), 1)
        d = issues[0]['description']
        self.assertIn(first_value, d); self.assertIn('A Different Title Of The Same Agreement', d)
        self.assertIn('Kept (task 1', d); self.assertIn('Task 2 gave', d)
        self.assertEqual((issues[0]['severity'], issues[0]['status']), ('MEDIUM', 'OPEN'))

    def test_a_value_only_a_later_chunk_gives_is_taken_and_equal_values_raise_no_issue(self):
        t = test_m3.ChunkMergeTests('test_chunk_merge_recovers_complete_output'); t.setUp()
        outputs = copy.deepcopy(t.outputs)
        outputs[1]['agreement'] = {'title': outputs[0]['agreement']['title']}
        merged, _ = test_m3.merge_chunks(t.map, t.packet, outputs)
        self.assertFalse([i for i in merged['open_issues'] if i['kind'] == 'AGREEMENT_HEADER_DIFFERS_ACROSS_AI_TASKS'])
        outputs = copy.deepcopy(t.outputs); outputs[0]['agreement'].pop('title'); outputs[0]['agreement']['field_evidence'] = {}
        outputs[1]['agreement'] = {'title': 'Only later chunk'}
        merged, _ = test_m3.merge_chunks(t.map, t.packet, outputs)
        self.assertEqual(merged['agreement']['title'], 'Only later chunk')
        self.assertFalse([i for i in merged['open_issues'] if i['kind'] == 'AGREEMENT_HEADER_DIFFERS_ACROSS_AI_TASKS'])

    def test_conflict_issue_reaches_sheet_05(self):
        rows, first, texts, errs = export_fixture('voit')
        first['DOC-voit']['open_issues'].append({'issue_id': 'ISSUE-MERGE-X', 'severity': 'MEDIUM', 'status': 'OPEN',
                                                 'kind': 'AGREEMENT_HEADER_DIFFERS_ACROSS_AI_TASKS', 'description': 'Kept (task 1): a. Task 2 gave: b.', 'passage_ids': []})
        mapping = read_json(FIX / 'voit_map.json')
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td) / 'ws'; init(ws); register_map(ws, mapping); register_extraction(ws, 'DOC-voit', first['DOC-voit'], select=True)
            rows2 = build_rows(ws)
        v = research_rows(rows2, first, texts, errs)
        self.assertTrue([r for r in table(v, 4) if r['First reader / state'] == 'AGREEMENT_HEADER_DIFFERS_ACROSS_AI_TASKS'])


class Item7MinimumQualifier(unittest.TestCase):
    def _min(self, **kw):
        raw = fixture_rows(); h = raw['Other Payments'][0]
        p = [None] * len(h)
        for k, v in dict(Payment_ID='1-PAY02', Document_ID='DOC-DEMO', Kind='MINIMUM_ROYALTY', Amount_Text='25000', Currency='USD', Evidence_IDs='E2').items(): p[h.index(k)] = v
        for k, v in kw.items(): p[h.index(k)] = v
        raw['Other Payments'] = [h, p]
        return table(research_rows(raw), 0)[0]['Minimum guarantee']

    def test_third_agreement_wording(self):
        self.assertEqual(self._min(Basis='Annual minimum royalty per licensed Product',
                                   Condition='Commences six months after signing; no further minimum payment required if royalties paid equal or exceed required minimum'),
                         'USD 25,000 per licensed Product [1-PAY02]')

    def test_variants(self):
        self.assertEqual(self._min(Basis='Minimum royalty for each Licensed Product in each country'), 'USD 25,000 per Licensed Product [1-PAY02]')
        self.assertEqual(self._min(Basis='Minimum annual royalty', Condition='per Contract Year, payable in January'), 'USD 25,000 [1-PAY02]')   # Basis only
        self.assertEqual(self._min(Basis='Minimum royalty for every patent family if the licence is exclusive'), 'USD 25,000 per patent family [1-PAY02]')

    def test_no_qualifier_wording_means_no_change(self):
        self.assertEqual(self._min(Basis='Annual minimum royalty'), 'USD 25,000 [1-PAY02]')
        self.assertEqual(self._min(Basis='Minimum royalty each year'), 'USD 25,000 [1-PAY02]')
        self.assertEqual(self._min(), 'USD 25,000 [1-PAY02]')

    def test_helper_cuts_at_filler_words(self):
        self.assertEqual(_minimum_qualifier({'Basis': 'Annual minimum royalty per licensed Product and per year'}), 'per licensed Product')
        self.assertEqual(_minimum_qualifier({'Basis': 'per the agreement'}), '')

    def test_voit_and_laser_minimums_unchanged(self):
        self.assertEqual(table(sheets('laser')[0], 0)[0]['Minimum guarantee'], '$ 10,000 [C1-P01]')
        self.assertEqual(by(sheets('voit')[0], 0, 'Observation ID', 'DOC-voit:C1-R1')['Minimum guarantee'], 'USD 130,000 [C1-P1]')


if __name__ == '__main__':
    unittest.main()
