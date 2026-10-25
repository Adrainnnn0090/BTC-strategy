"""Independent scalar numeric-tree audit; delivery and ledger stay read-only."""
import sys
sys.dont_write_bytecode=True
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import numpy as np

LEDGER=Path('/workspace/BTCStrategyResearchLedger')
DELIVERY=Path('/workspace/BTC-strategy')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
TOL=2e-12
def deny_source_writes(event,args):
 if event!='open' or not isinstance(args[0],(str,bytes)):return
 p=Path(os.fsdecode(args[0])).resolve()
 if p.is_relative_to(LEDGER) or p.is_relative_to(DELIVERY):
  mode=args[1] or ''
  flags=args[2] if len(args)>2 else 0
  if any(c in mode for c in 'wax+') or flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
   raise AssertionError('Read-only audit blocked source/delivery write: '+str(p))
sys.addaudithook(deny_source_writes)
sys.path.insert(0,str(LEDGER))
sys.path.insert(0,str(DELIVERY/'src'))
from lab.tree_factors import matrix
from lab.volume_short_factors import append_volume
from lab.mining_ablation import ablate
import btc_strategy.models as production

def read(p):
 p=Path(p)
 assert p.is_relative_to(LEDGER) or p.is_relative_to(DELIVERY)
 assert not any(z in p.parts for z in ('2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
 if p.suffix=='.gz':
  with gzip.open(p,'rt') as f:return json.load(f)
 return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
code_sha=sha(DELIVERY/'src/btc_strategy/models.py')

# Scalar implementation intentionally uses no production tree_predict/predict.
# struct performs the required IEEE754 float32 input conversion independently.
def f32(value):return struct.unpack('<f',struct.pack('<f',float(value)))[0]
def scalar_tree(tree,row):
 node=0
 for _ in range(len(tree['left'])):
  left=tree['left'][node]
  if left==-1:
   assert tree['right'][node]==-1
   return float(tree['value'][node])
  value=f32(row[tree['feature'][node]])
  node=left if value<=tree['threshold'][node] else tree['right'][node]
 raise AssertionError('nonterminating/cyclic numeric tree')
def scalar_state(state,row):
 value=float(state['initial'])
 for tree in state['trees']:value+=float(state['weight'])*scalar_tree(tree,row)
 return value
def mean(values):return sum(values)/len(values)

# Exact threshold and float32 rounding canaries; internal node value is ignored.
tree=dict(left=[1,-1,-1],right=[2,-1,-1],feature=[0,-2,-2],
          threshold=[.5,-2.,-2.],value=[999.,-3.,7.])
canary=dict(initial=1.25,weight=.03,trees=[tree])
canary_rows=[[.5],[float(np.nextafter(.5,1.))],[float(np.nextafter(np.float32(.5),np.float32(1.)))]]
canary_scalar=[scalar_state(canary,row)for row in canary_rows]
assert canary_scalar==[1.16,1.16,1.46]
assert np.array_equal(production.predict(canary,np.asarray(canary_rows)),np.asarray(canary_scalar))

market_rows=read(LEDGER/'data/walkforward-v1/2025/train.json')+read(LEDGER/'data/walkforward-v1/2025/test.json')
mining_rows=read(LEDGER/'data/mining-lag-v1/2025/train.json.gz')+read(LEDGER/'data/mining-lag-v1/2025/test.json.gz')
days=[r['date']for r in market_rows]
prices=[r['price']for r in market_rows]
assert days[0]=='2017-01-01' and days[-1]=='2025-12-31' and [r['date']for r in mining_rows]==days
cal=matrix(days,prices,'CAL44')
features={'base_tree':cal,'stop44':cal,'price47':append_volume(days,prices,None,7,'PRICE47'),
          'short_huber':cal,'short_median':cal,'mining58':ablate(cal,mining_rows,'DYNAMICS',60)}
market={'days':days,'prices':prices,'mining':mining_rows}
manifest=read(DELIVERY/'models/manifest.json')
sources={
 'base_tree':('B10-seed-calendar-stability','MEAN_CAL44'),
 'stop44':('B20-execution-aware-labels','CAL44_STOP'),
 'price47':('B81-reported-volume-long-core','PRICE_L7'),
 'short_huber':('B67-lag-matched-short-supervision','MEAN'),
 'short_median':('B88A-short-net-loss-families','MEDIAN'),
 'mining58':('B17-mining-dimension-ablation','EXTRA_DYNAMICS_L60'),
}
seeds=[101,307,509,701,907,1103,1701]
results=[]
file_count=0
state_evals=0
sample_predictions={}
for family,(study,stream) in sources.items():
 for year in (2019,2025):
  entry=next(x for x in manifest if x['family']==family and x['fold_year']==year)
  states=[]
  for item in entry['files']:
   p=DELIVERY/item['path']
   assert sha(p)==item['sha256']==sha(LEDGER/item['source'])
   model=read(p)
   states.extend(model['members']if 'members'in model else[model.get('state',model)])
   file_count+=1
  states.sort(key=lambda s:(s.get('execution_lag',0),s['seed']))
  assert states==production.annual_states(family,year)
  if family.startswith('short_'):
   assert [(s['execution_lag'],s['seed'])for s in states]==[(lag,seed)for lag in (1,2)for seed in seeds]
  else:assert [s['seed']for s in states]==seeds
  for s in states:
   assert len(s['trees'])==96
   if s['family']=='EXTRA':assert s['initial']==0. and s['weight']==1/96
   else:assert s['family']=='SGB' and s['weight']==s['profile']['learning_rate']
  old=read(LEDGER/'studies'/study/'folds'/str(year)/'predictions.json.gz')
  first=days.index(f'{year-1}-12-31')
  offsets=[0,len(old['dates'])//2,len(old['dates'])-1]
  row_indices=[first+i for i in offsets]
  rows=features[family][row_indices]
  scalar_by_state=[[scalar_state(s,row)for row in rows]for s in states]
  delivered_by_state=[production.predict(s,rows).tolist()for s in states]
  state_error=max(abs(a-b)for scalar,actual in zip(scalar_by_state,delivered_by_state)
                  for a,b in zip(scalar,actual))
  assert state_error<=TOL
  values=[]
  for j in range(len(rows)):
   if family.startswith('short_'):
    heads=[mean([scalar_by_state[k][j]for k,s in enumerate(states)if s['execution_lag']==lag])for lag in (1,2)]
    values.append((heads[0]+heads[1])/2)
   else:values.append(mean([v[j]for v in scalar_by_state]))
  expected=[old['scores'][stream][i]for i in offsets]
  reference_error=max(abs(a-b)for a,b in zip(values,expected))
  assert reference_error<=TOL
  state_evals+=len(states)*len(rows)
  record={'family':family,'year':year,'dates':[days[i]for i in row_indices],
          'state_count':len(states),'scalar_predictions':values,'source_predictions':expected,
          'max_error_against_source':reference_error,'max_error_against_production_state_predict':state_error}
  results.append(record)
  sample_predictions[(family,year)]=(row_indices,values)

# Exercise two complete delivery reconstruction paths as well as scalar state
# comparisons: one ExtraTrees family and one two-clock SGB family.
pipeline=[]
for family in ('price47','short_median'):
 full=production.reconstruct(family,market=market)
 error=0.
 for year in (2019,2025):
  indices,expected=sample_predictions[(family,year)]
  error=max(error,max(abs(full[i]-v)for i,v in zip(indices,expected)))
 assert error<=TOL
 pipeline.append({'family':family,'sample_count':6,'max_error_vs_independent_scalar':error})

assert code_sha==sha(DELIVERY/'src/btc_strategy/models.py')
initial=read(DELIVERY/'verification/model-inference-initial.json')
result={'round':5,'all_checks_pass':True,'tolerance':TOL,
 'delivery_models_py_sha256':code_sha,'numeric_files_checked':file_count,
 'independent_scalar_state_predictions':state_evals,'aggregate_predictions_checked':sum(len(x['dates'])for x in results),
 'max_sample_error_vs_original':max(x['max_error_against_source']for x in results),
 'max_state_error_vs_delivery':max(x['max_error_against_production_state_predict']for x in results),
 'threshold_float32_canary':{'input_values':[r[0]for r in canary_rows],'scalar_predictions':canary_scalar,'pass':True},
 'complete_pipeline_samples':pipeline,'results':results,
 'root_initial_receipt_observed':{'status':initial['status'],'family_count':len(initial['families']),
     'max_error':max(x['max_error']for x in initial['families'])},
 'scope':'2019/2025每族首/中/末3个预定决策日；独立struct float32+标量节点遍历；两族完整推理函数抽样核对；无重训/原独占写入器/2026经济数据读取。'}
with (OUT/'r05_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items()if k!='results'},ensure_ascii=False))
