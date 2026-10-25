"""Read-only semantic and maturity audit of actual 2019 training labels."""
from collections import Counter
from decimal import Decimal as D, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
def read(p):
 p=Path(p)
 assert p.is_relative_to(ROOT) and '/2019/' in str(p)
 if p.suffix=='.gz':
  with gzip.open(p,'rt') as f:return json.load(f)
 return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
year=2019
rows=read(ROOT/'data/walkforward-v1/2019/train.json')
days=[r['date'] for r in rows]
prices=[D(str(r['price'])) for r in rows]
cut=len(rows)-1
assert cut==729 and days[-1]=='2018-12-31'
base=ROOT/'studies/B10-seed-calendar-stability/folds/2019'
long=ROOT/'studies/B20-execution-aware-labels/folds/2019'
vol=ROOT/'studies/B36-network-activity-factors/folds/2019'
short=ROOT/'studies/B67-lag-matched-short-supervision/folds/2019'
loss=ROOT/'studies/B88A-short-net-loss-families/folds/2019'
stop=read(long/'labels/STOP.json.gz')
stop_source=read(vol/'labels/STOP.json.gz')
banks=read(short/'labels.json.gz')
tr=read(short/'training.json')
loss_tr=read(loss/'training.json')
assert stop==stop_source
assert sha(long/'labels/STOP.json.gz')==read(long/'seal.json')['label_sha256']['STOP']
assert sha(vol/'labels/STOP.json.gz')==read(vol/'seal.json')['label_sha256']['STOP']
assert sha(short/'labels.json.gz')==tr['labels_sha256']==loss_tr['source_labels_sha256']
assert [x['index'] for x in stop]==list(range(252,cut-60-6))
assert all(x['maturity_index']==x['index']+61<=cut-6 for x in stop)
assert all(x['exit_index'] is None or x['exit_index']<=x['maturity_index'] for x in stop)
assert all([x['index'] for x in banks[h]]==list(range(252,cut-67)) for h in ('L1','L2'))
for h,lag in [('L1',1),('L2',2)]:
 assert all(x['maturity_index']==x['index']+60+lag<=cut-6 for x in banks[h])
 assert all(x.get('exit_index',0)<=x['maturity_index'] for x in banks[h])
common=[a['index'] for a,b in zip(banks['L1'],banks['L2'])
        if a['status']==b['status']=='DEFINED']
assert common==tr['common_ids']==loss_tr['common_ids']
for t in (tr,loss_tr):
 for key,recs in t['receipts'].items():
  for rec in recs:
   assert rec['cut']==cut and rec['last']==common[-1]
   assert rec['common_last_label']==common[-1]+62<=cut-6
   assert rec['last_label']==common[-1]+60+rec['execution_lag']

def quote(p):
 return ((p*D('.999')).quantize(D('.01'),rounding=ROUND_FLOOR),
         (p*D('1.001')).quantize(D('.01'),rounding=ROUND_CEILING))
def fee(q,p):return (q*p*D('.003')).quantize(D('.00000001'),rounding=ROUND_HALF_EVEN)
stop_examples=[]
for index in (252,362,662):
 x=next(x for x in stop if x['index']==index)
 entry,exit=x['entry_index'],x['exit_index']
 basis=quote(prices[entry])[1]*D('1.003')
 liquidation=quote(prices[exit])[0]*D('.997')
 expected=math.log(float(liquidation/basis))
 assert abs(expected-x['log_return'])<2e-15
 if x['reason']=='STOP_LOSS':
  assert quote(prices[x['trigger_index']])[0]*D('.997')<=basis*D('.85')
  assert exit==x['trigger_index']+1
 if x['reason']=='YEAR_CLOSE':assert days[exit].endswith('-12-31') and exit<x['maturity_index']
 stop_examples.append({**x,'entry_date':days[entry],'exit_date':days[exit],
                       'holding_days':exit-entry,'recomputed_log_return':expected})

short_examples=[]
for h,index in [('L1',252),('L2',252),('L1',661),('L2',661),('L1',362)]:
 x=next(x for x in banks[h] if x['index']==index)
 q=D(x['quantity']);bid=D(x['entry_price']);ask=D(x['exit_price'])
 assert bid==quote(prices[x['entry_index']])[0] and ask==quote(prices[x['exit_index']])[1]
 assert q==(D('24.99')/(bid*D('1.003'))).quantize(D('.00001'),rounding=ROUND_FLOOR)
 fees=fee(q,bid)+fee(q,ask)
 financing=D(0)
 for j in range(x['entry_index']+1,x['exit_index']+1):financing+=q*prices[j]*D('.1')/D(365)
 basis=q*bid+fee(q,bid)
 pnl=q*(bid-ask)-fees-financing
 assert abs(fees-D(x['fees']))<=D('1e-24')
 assert abs(financing-D(x['financing']))<=D('1e-24')
 assert abs(pnl-D(x['pnl']))<=D('1e-24')
 assert basis==D(x['basis']) and abs(float(pnl/basis)-x['simple_return'])<=2e-15
 short_examples.append({**x,'holding_days':x['exit_index']-x['entry_index'],
                        'entry_date':days[x['entry_index']],'exit_date':days[x['exit_index']]})

for index,head in [(363,'L1'),(362,'L2')]:
 x=next(x for x in banks[head] if x['index']==index)
 assert x['status']=='UNEXECUTABLE' and x['simple_return'] is None and index not in common
forbidden=next(x for x in stop if x['index']==363)
assert forbidden['log_return']==0 and forbidden['entry_index'] is None
base_state=read(base/'models/EXTRA_CAL44_H60_S101.json.gz')
assert base_state['receipt']['receipt']['last']==662
assert base_state['receipt']['receipt']['last_label']==723==cut-6
base_cost=math.log(1.001/(.999*.997**2))
index=252
base_log=math.log(float(prices[index+61]/prices[index+1]))-base_cost
first_short=short_examples[0]['simple_return']
assert not math.isclose(first_short,-base_log,abs_tol=1e-12)
assert not math.isclose(first_short,-stop_examples[0]['log_return'],abs_tol=1e-12)
assert 663+61>cut-6 and 662+62>cut-6
result={
 'round':3,'all_checks_pass':True,'train_year':2019,'cut':cut,'cutoff':days[-1],
 'stop_count':len(stop),'stop_reason_counts':dict(Counter(x['reason'] for x in stop)),
 'short_bank_counts':{h:len(a) for h,a in banks.items()},'short_common_count':len(common),
 'long_max_id':662,'long_maturity':723,'short_common_max_id':common[-1],
 'short_l1_maturity':common[-1]+61,'short_l2_maturity':common[-1]+62,
 'embargo_boundary':cut-6,'next_long_id_rejected':663,'next_common_short_id_rejected':662,
 'baseline_label_at_252':{'value':base_log,'cost':base_cost,'entry_index':253,'maturity_index':313},
 'stop_examples':stop_examples,'short_examples':short_examples,
 'year_end_unexecutable_difference':{'long_index_363':forbidden,
   'short_excluded_pairs':[[363,'L1'],[362,'L2']]},
 'scope':'只读2019训练前缀/实际标签/receipt；重算若干现金及标签恒等式，未调用原写入器/训练器，未查看测试期或2026经济数据。'
}
with (OUT/'r03_checks.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items() if k not in ('stop_examples','short_examples','year_end_unexecutable_difference')},ensure_ascii=False))
