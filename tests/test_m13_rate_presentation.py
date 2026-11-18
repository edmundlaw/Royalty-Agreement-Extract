"""Regression coverage for rate presentation in the v0.13.12 live audit."""
import unittest

from royalty_research.m13_research_export import NAMES, research_rows, benchmark_usable, display_quote
from test_m13_research_export import fixture_rows


class RatePresentation(unittest.TestCase):
    def _export(self, family, status, unit, structure, tiers, base=None, quote=None):
        rows = fixture_rows()
        header, row = rows['Royalty Terms']
        for key, value in dict(Family=family, Disclosure_Status=status, Rate_Unit=unit,
                               Structure=structure, Rate_Numeric=None, Rate_Value_Text=None,
                               QC_State='SINGLE_READER_NOT_CHECKED').items():
            row[header.index(key)] = value
        if base is not None:row[header.index('Royalty_Base')]=base
        if quote is not None:rows['Evidence'][1][rows['Evidence'][0].index('Exact_Quotation')]=quote
        th = rows['Tiers'][0]
        rows['Tiers'] = [th] + [[dict(Document_ID='DOC-DEMO', Term_ID='R1',
                                      Observation_ID='DOC-DEMO:R1', Sequence=i, **tier).get(k)
                                for k in th] for i, tier in enumerate(tiers, 1)]
        v = research_rows(rows)
        return dict(zip(v[NAMES[0]][0], v[NAMES[0]][1]))

    def test_partial_redaction_shows_disclosed_tier_but_never_scalar(self):
        row = self._export('PRODUCT_SALES', 'REDACTED', 'REDACTED', 'TIERED', [
            dict(Rate_Unit='REDACTED'), dict(Rate_Unit='PERCENT', Rate_Numeric=20)])
        self.assertIsNone(row['Royalty rate (%)'])
        self.assertEqual(row['Royalty rate as reported'], 'PARTLY REDACTED – disclosed tier 20%, see sheet 02')
        self.assertEqual(row['Usable for royalty benchmark'], 'NO')

    def test_fully_redacted_and_no_tier_show_redaction(self):
        row = self._export('PRODUCT_SALES', 'REDACTED', 'REDACTED', 'TIERED', [dict(Rate_Unit='REDACTED')])
        self.assertEqual(row['Royalty rate as reported'], 'REDACTED – see sheet 02')
        row = self._export('PRODUCT_SALES', 'REDACTED', 'REDACTED', 'UNKNOWN', [])
        self.assertEqual(row['Royalty rate as reported'], 'REDACTED')

    def test_revenue_share_formula_not_misrepresented_as_undisclosed(self):
        row = self._export('REVENUE_SHARE', 'DISCLOSED', 'FORMULA', 'FORMULA', [],
                           'Residual litigation recoveries', 'The remaining balance shall be divided equally between the parties.')
        self.assertEqual(row['Usable for royalty benchmark'], 'NO')
        self.assertIn('litigation recovery split, not a royalty rate', row['Benchmark note'])
        self.assertNotIn('rate not disclosed or unclear', row['Benchmark note'])

    def test_royalty_free_is_not_an_undisclosed_rate(self):
        usable, note = benchmark_usable(dict(Rate_Value_Text='royalty-free', Rate_Unit='UNKNOWN'), '', '')
        self.assertEqual(usable, 'NO')
        self.assertIn('royalty-free licence', note)
        self.assertNotIn('rate not disclosed', note)

    def test_quote_completion_stops_before_next_numbered_clause(self):
        quote = '[***] | Twenty Percent (20%)'
        self.assertEqual(display_quote(quote, 'DOC:P000001', [quote, '12.', 'Section 7.6 is amended.']), quote)
        self.assertEqual(display_quote('5%', 'DOC:P000001', ['The rate is 5%', 'of Net Sales.']),
                         'The rate is 5% of Net Sales.')
