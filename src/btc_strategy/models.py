"""Reconstruct annual forecasts from actual numeric trees, never from pickle."""
import numpy as np
from bisect import bisect_left
from .validation import development_market
from .artifacts import read,restore,read_verified
from .strategies import context
from ._runtime.tree_factors import matrix,predict
from ._runtime.volume_short_factors import append_volume
from ._runtime.mining_ablation import ablate

FAMILIES=('base_tree','stop44','price47','short_huber','short_median','mining58')

def feature_matrix(family,market):
 if family not in FAMILIES:raise ValueError('unknown feature family')
 days,prices=market['days'],market['prices'];development_market(days,prices)
 if family=='price47':return append_volume(days,prices,None,7,'PRICE47')
 x=matrix(days,prices,'CAL44')
 if family=='mining58':return ablate(x,market['mining'],'DYNAMICS',60)
 return x


def annual_states(family,year):
 if family not in FAMILIES or type(year)is not int or year not in range(2018,2026):raise ValueError('unknown model family/year')
 m=next(x for x in read('models/manifest.json')if x['family']==family and x['fold_year']==year)
 if year==2018:
  if m.get('missing')is not True or m.get('files')!=[]:raise ValueError('2018 must preserve missing model state')
  return []
 if m.get('missing')is not False:raise ValueError('invalid missing-state contract')
 result=[]
 for item in m['files']:
  if item['path'].split('/')[:3]!=['models',family,str(year)]:raise ValueError('model year/family path mismatch')
  state=read_verified(item['path'],item['sha256'])
  if 'cutoff'in state and state['cutoff']!=f'{year-1}-12-31':raise ValueError('model cutoff mismatch')
  result.extend(state['members']if 'members'in state else[state.get('state',state)])
 result=sorted(result,key=lambda s:(s.get('execution_lag',0),s['seed']))
 seeds=[101,307,509,701,907,1103,1701]
 if family.startswith('short_'):
  if len(result)!=14 or any([s['seed']for s in result if s['execution_lag']==lag]!=seeds for lag in(1,2)):raise ValueError('incomplete short member roster')
 elif len(result)!=7 or[s['seed']for s in result]!=seeds:raise ValueError('incomplete long member roster')
 if any(s['n_features']!=m['feature_width']for s in result):raise ValueError('model feature width mismatch')
 return result


def reconstruct(family,market=None):
 if family not in FAMILIES:raise ValueError('unknown family')
 if market is None:
  market=read('artifacts/factors/prices.json.gz')
  if family=='mining58':market.update(read('artifacts/factors/mining.json.gz'))
 days=market['days'];x=feature_matrix(family,market);out=[None]*len(days)
 for year in range(2018,2026):
  first=bisect_left(days,f'{year-1}-12-31');last=bisect_left(days,f'{year}-12-31')
  if first==last:continue
  states=annual_states(family,year)
  if not states:continue
  rows=x[first:last]
  if family.startswith('short_'):
   heads=[np.mean([predict(s,rows)for s in states if s['execution_lag']==lag],axis=0).tolist()for lag in (1,2)]
   values=[(a+b)/2 for a,b in zip(*heads,strict=True)]
  else:values=np.mean([predict(s,rows)for s in states],axis=0).tolist()
  out[first:last]=values
 return out


def expected(family):
 high=context('LP35');size=context('C04');median=context('B88A_S03')
 return {'base_tree':high[0]['scores']['BASE_TREE'],'price47':high[0]['scores']['CAL44_STOP'],'stop44':high[1]['scores']['CAL44_STOP'],'short_huber':high[0]['learner'],'short_median':median[1]['MEDIAN'],'mining58':size[2]['EXTRA_DYNAMICS_L60']}[family]


def verify_family(family):
 values=reconstruct(family);reference=expected(family);assert len(values)==len(reference)
 assert all((a is None)==(b is None)for a,b in zip(values,reference,strict=True)),family+' availability mismatch'
 errors=[abs(a-b)for a,b in zip(values,reference,strict=True)if a is not None]
 error=max(errors,default=0.)
 if error>2e-12:raise AssertionError(family+' numeric forecast mismatch '+str(error))
 return dict(family=family,positions=len(values),finite=sum(v is not None for v in values),max_error=error,tolerance=2e-12,availability_exact=True,actual_numeric_models_used=True)


from functools import lru_cache
@lru_cache(maxsize=6)
def _rebuilt(family):return tuple(reconstruct(family))

def rebuild_context(name):
 ctx=context(name)
 def stream(family):return list(_rebuilt(family))
 if name in ('LP35','TS04','ME01','MX03'):
  ctx[0]['scores']['BASE_TREE']=stream('base_tree');ctx[0]['scores']['CAL44_STOP']=stream('price47');ctx[0]['learner']=stream('short_huber')
 elif name=='Y01':
  ctx[1]['scores']['BASE_TREE']=stream('base_tree');ctx[1]['scores']['CAL44_STOP']=stream('stop44')
 elif name=='B88A_S03':
  ctx[0]['scores']['BASE_TREE']=stream('base_tree');ctx[0]['scores']['CAL44_STOP']=stream('price47');ctx[1]['MEDIAN']=stream('short_median')
 elif name=='K02':
  ctx[2]['scores']['BASE_TREE']=stream('base_tree');ctx[2]['scores']['CAL44_STOP']=stream('stop44');ctx[3]=stream('short_huber')
 elif name=='C02':
  ctx[2]['BASE_TREE']=stream('base_tree');ctx[2]['CAL44_STOP']=stream('stop44')
 elif name=='C04':ctx[2]['EXTRA_DYNAMICS_L60']=stream('mining58')
 else:raise ValueError('unknown strategy')
 return ctx


if __name__=='__main__':
 import json
 for family in FAMILIES:print(json.dumps(verify_family(family)),flush=True)
