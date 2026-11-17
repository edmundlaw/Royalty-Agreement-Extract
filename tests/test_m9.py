"""M9 adversarial checks: not a human-reviewed accuracy benchmark."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from royalty_research.mapping import map_contract
from royalty_research.m9_context_gate import check_context_economics
from royalty_research.m4_operator import (
    _check_billing_environment, _safe_environment, _structured_limit_error,
    _parse_fenced_or_plain_json, _parse_provider_output, _preflight_subscription,
)


class ContextualScheduleTests(unittest.TestCase):
    def setUp(self):
        self.source=map_contract([
            '3.2 Licensee shall pay Licensor a percentage of all fees received from sublicensees as sublicense fees.',
            '3.2.1 Sublicense fees shall be paid as the following percentages of sublicense fees.',
            'Percentage | Aggregate Sublicense Fees',
            '25% | < $250,000',
            '10% | $250,000 -- $2,000,000',
            '5% | > $2,000,000',
            '7.1 Licensee shall pay an earned royalty of one percent (1%) of Net Sales up to a maximum of one million dollars ($1,000,000) per year.',
            '7.3 In no event shall Licensee pay Licensor more than twenty-five (25%) of total annual revenue derived from Licensed Products.',
            '10.2 On audit examination, an error above five percent (5%) shifts inspection costs.',
        ],{'document_id':'M9-SYNTHETIC','source_url':None})
        pids=[p['passage_id'] for p in self.source['passages']]
        self.extraction={
            'evidence':[{'evidence_id':f'E{i}','passage_id':pids[i-1],
                         'quote':self.source['passages'][i-1]['text']} for i in range(1,10)],
            'royalty_terms':[
                {'term_id':'T1','family':'SUBLICENSING_RECEIPTS',
                 'tiers':[{'rate_value':'25','lower':None,'upper':'250000','evidence_ids':['E4']},
                          {'rate_value':'10','lower':'250000','upper':'2000000','evidence_ids':['E5']},
                          {'rate_value':'5','lower':'2000000','upper':None,'evidence_ids':['E6']}]},
            ],
            'other_payments':[{'payment_id':'CAP1','kind':'CAP','amount_value':'1000000',
                               'evidence_ids':['E7']}],
            'royalty_cap_conditions':[{'text':'No more than 25% of annual revenue','evidence_ids':['E8']}]
        }
        self.extraction['royalty_terms'][0]['conditions']=self.extraction.pop('royalty_cap_conditions')

    def codes(self,x):
        return {z['code'] for z in check_context_economics(self.source,x)['errors']}

    def test_complete_sublicense_and_cap_are_accepted(self):
        r=check_context_economics(self.source,self.extraction)
        self.assertEqual(r['errors'],[])
        self.assertEqual(len(r['tests']),5)

    def test_missing_entire_schedule_rejected_even_if_ledger_relabelled(self):
        x=copy.deepcopy(self.extraction);x['royalty_terms']=[]
        self.assertIn('M9_TIER_TABLE_ROW_MISSING',self.codes(x))

    def test_one_missing_tier_is_rejected(self):
        x=copy.deepcopy(self.extraction);x['royalty_terms'][0]['tiers'].pop(1)
        self.assertIn('M9_TIER_TABLE_ROW_MISSING',self.codes(x))

    def test_rate_swap_is_rejected(self):
        x=copy.deepcopy(self.extraction)
        x['royalty_terms'][0]['tiers'][0]['rate_value']='10'
        x['royalty_terms'][0]['tiers'][1]['rate_value']='25'
        self.assertIn('M9_TIER_RATE_ROW_MISMATCH',self.codes(x))

    def test_wrong_rate_family_rejected(self):
        x=copy.deepcopy(self.extraction);x['royalty_terms'][0]['family']='PRODUCT_SALES'
        self.assertIn('M9_SUBLICENSE_TIER_MISCLASSIFIED',self.codes(x))

    def test_wrong_band_rejected(self):
        x=copy.deepcopy(self.extraction);x['royalty_terms'][0]['tiers'][1]['upper']='3000000'
        self.assertIn('M9_TIER_BAND_MISMATCH',self.codes(x))

    def test_missing_royalty_cap_rejected(self):
        x=copy.deepcopy(self.extraction);x['other_payments']=[]
        self.assertIn('M9_ROYALTY_CAP_UNACCOUNTED',self.codes(x))

    def test_percentage_based_cap_omission_is_rejected(self):
        x=copy.deepcopy(self.extraction);x['royalty_terms'][0]['conditions']=[]
        self.assertIn('M9_PERCENT_ROYALTY_CAP_UNACCOUNTED',self.codes(x))

    def test_audit_percent_not_marked_table_rate(self):
        r=check_context_economics(self.source,self.extraction)
        audit_id=self.source['passages'][-1]['passage_id']
        self.assertFalse(any(z.get('ref')==audit_id for z in r['errors']))


class SubscriptionGuardTests(unittest.TestCase):
    def test_unknown_provider_api_key_shape_blocked(self):
        with patch.dict(os.environ,{'ANTHROPIC_CUSTOM_API_KEY':'do-not-forward'}):
            with self.assertRaisesRegex(RuntimeError,'NO CLI call'):
                _check_billing_environment()

    def test_unrelated_secrets_not_forwarded(self):
        with patch.dict(os.environ,{'GITHUB_TOKEN':'not-for-model','FAKE_MODE':'secret'}):
            clean=_safe_environment()
            self.assertNotIn('GITHUB_TOKEN',clean)
            self.assertNotIn('FAKE_MODE',clean)
            self.assertNotIn('OPENAI_API_KEY',clean)

    def test_limit_phrase_in_valid_answer_is_not_rate_limit(self):
        answer=json.dumps({'is_error':False,'result':json.dumps({'clause':'The rate limit reached was a contract condition'})})
        self.assertFalse(_structured_limit_error('claude',answer,'',0))
        self.assertFalse(_structured_limit_error('codex','ordinary model wording','',0))

    def test_limit_error_envelope_or_failed_stderr_stops(self):
        env=json.dumps({'is_error':True,'result':'usage limit reached'})
        self.assertTrue(_structured_limit_error('claude',env,'',0))
        self.assertTrue(_structured_limit_error('codex','', 'rate limit reached',1))
        self.assertTrue(_structured_limit_error('codex','rate limit reached','',1))

    def test_fenced_and_prose_wrapped_json_recovered(self):
        data={'schema':'m3-chunk.1','text':'hello {world}'}
        for variant in (json.dumps(data), '```json\n'+json.dumps(data)+'\n```',
                        'Result follows:\n'+json.dumps(data)+'\nThank you'):
            self.assertEqual(_parse_fenced_or_plain_json(variant),data)
        with self.assertRaises(ValueError):_parse_fenced_or_plain_json('no structured content')

    def test_claude_envelope_fenced_json_recovered(self):
        result={'schema':'m3-chunk.1'}
        stdout=json.dumps({'is_error':False,'result':'```json\n'+json.dumps(result)+'\n```'})
        self.assertEqual(_parse_provider_output('claude',stdout,Path('/no-file')),result)

    def test_preflight_subscription_rejects_api_credentials(self):
        # A fake CLI prints only authentication status; no inference happens.
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stub'
            path.write_text('#!'+sys.executable+'\nimport json\nprint(json.dumps({"authMethod":"api_key"}))\n')
            path.chmod(0o755)
            with self.assertRaisesRegex(RuntimeError,'not explicitly signed in'):
                _preflight_subscription(path,'claude',_safe_environment(),tmp)
            path.write_text('#!'+sys.executable+'\nimport json\nprint(json.dumps({"authMethod":"claude.ai"}))\n')
            self.assertEqual(_preflight_subscription(path,'claude',_safe_environment(),tmp)['auth_type'],
                             'subscription_login_verified')

    def test_codex_preflight_requires_explicit_chatgpt_signin(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'stub'
            path.write_text('#!'+sys.executable+'\nprint("Logged in using API key")\n');path.chmod(0o755)
            with self.assertRaisesRegex(RuntimeError,'ChatGPT subscription'):
                _preflight_subscription(path,'codex',_safe_environment(),tmp)
            path.write_text('#!'+sys.executable+'\nprint("Logged in using ChatGPT")\n')
            self.assertEqual(_preflight_subscription(path,'codex',_safe_environment(),tmp)['auth_type'],
                             'subscription_login_verified')


if __name__=='__main__':unittest.main()
