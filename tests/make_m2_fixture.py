"""Construct an independent, fictional fixture. NOT evidence of real extraction accuracy."""
from pathlib import Path
import json
from royalty_research.storage import atomic_json

base=Path(__file__).parent.parent
mapping=json.load(open(base/'output/synthetic_clause_map.json'))
passages=mapping['passages']
P=lambda n: passages[n-1]['passage_id']
E=lambda n: f'EV{n:02d}'
ev=[{'evidence_id':E(n),'passage_id':P(n),'quote':passages[n-1]['text'],'role':'OTHER'} for n in [1,3,4,5,6,7,8,10,11]]

def tier(seq, rate, low, high, eid):
 return {'sequence':seq,'rate_value':rate,'rate_unit':'PERCENT','lower':low,'upper':high,
   'calculation':'MARGINAL','measurement_period':'AGREEMENT_YEAR','threshold_basis':'NET_SALES',
   'evidence_ids':[eid],'threshold_evidence_ids':[eid]}

def term(tid,family,structure,rv,unit,base,evidence,rate_evidence,base_evidence,tiers,conditions=None,adjustments=None):
 return {'term_id':tid,'family':family,'structure':structure,'disclosure_status':'DISCLOSED',
    'rate_value':rv,'rate_unit':unit,'base':base,'base_definition':None,'product_scope':None,
    'territory_scope':None,'effective_period':None,'conditions':conditions or [],'adjustments':adjustments or [],
    'tiers':tiers,'evidence_ids':evidence,'rate_evidence_ids':rate_evidence,'base_evidence_ids':base_evidence}
terms=[
 term('RT-SALES','PRODUCT_SALES','TIERED',None,'PERCENT','Net Sales',[E(3),E(4),E(7),E(11)],[E(4)],[E(3),E(4)],
      [tier(1,'6','0','500000',E(4)),tier(2,'4','500000',None,E(4))],
      adjustments=[{'description':'Patent-expiry reduction refers to Section 7.2; redacted amount unresolved','evidence_ids':[E(7),E(11)]}]),
 term('RT-SUB','SUBLICENSING_RECEIPTS','TIERED',None,'PERCENT','sublicense receipts',[E(5)],[E(5)],[E(5)],
      [tier(1,'25','0','250000',E(5)),tier(2,'10','250000',None,E(5))]),
 term('RT-UNIT','PER_UNIT','FLAT','2','CURRENCY_PER_UNIT','per device',[E(10)],[E(10)],[E(10)],[]),
]
disposition_choices={3:(['DEFINITION'],[],[]),4:(['ROYALTY_TERM'],['RT-SALES'],[]),5:(['ROYALTY_TERM'],['RT-SUB'],[]),
 6:(['UNRELATED_PERCENT','OTHER_PAYMENT'],[],['OP-INTEREST']),7:(['ROYALTY_TERM','CROSS_REFERENCE'],['RT-SALES'],[]),
 8:(['CROSS_REFERENCE'],[],[]),10:(['ROYALTY_TERM'],['RT-UNIT'],[]),11:(['ROYALTY_TERM','REDACTED'],['RT-SALES'],[])}
D=[]
from royalty_research.mapping import PERCENT
for n,(categories,tids,pids) in disposition_choices.items():
 D.append({'passage_id':P(n),'categories':categories,'term_ids':tids,'payment_ids':pids,'evidence_ids':[E(n)],
  'rationale':'Mapped passage inspected; classified based on whether an economic licensing obligation is established.',
  'percentage_dispositions':[{'literal':match.group(0),
    'classification':'UNRELATED' if n==6 else 'ROYALTY_RATE',
    'term_id':None if n==6 else tids[0],
    'rationale':'A late-payment interest percentage, not a royalty' if n==6 else 'A contractual royalty percentage assigned to this rate rule'}
    for match in PERCENT.finditer(passages[n-1]['text'])]})
record={'schema_version':'m2.0','document_id':mapping['document_id'],'source_text_sha256':mapping['text_sha256'],
  'source_url':mapping['source_url'], 'reader':{'engine':'fixture','model':'synthetic-human-authored-test',
      'run_id':'TEST-FIXTURE-001','read_scope':'FULL_DOCUMENT','reviewed_passage_ids':[p['passage_id'] for p in passages]},
  'agreement':{'title':passages[0]['text'],'licensor':None,'licensee':None,'industry':None,'licensed_ip':None,
      'execution_date':None,'effective_date':None,'duration':None,'territory':None,'exclusivity':None,
      'contractual_status':None,'field_evidence':{'title':[E(1)]}},
  'royalty_terms':terms,
  'other_payments':[{'payment_id':'OP-INTEREST','kind':'INTEREST','amount_value':None,'currency':None,
       'basis':'Overdue payment','condition':'If payment is late','evidence_ids':[E(6)]}],
  'evidence':ev,'dispositions':D,'amendment_status':'NOT_CHECKED','open_issues':[{'issue_id':'ISSUE-RED-1',
      'severity':'HIGH','kind':'REDACTED_ADJUSTMENT','description':'Exact patent-expiry adjusted rate is redacted',
      'status':'OPEN','passage_ids':[P(11)]}]}
atomic_json(base/'examples/synthetic_m2_extraction.json',record)
