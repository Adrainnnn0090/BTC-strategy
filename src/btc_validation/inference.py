"""Numeric-only frozen2026 predictions and original annual-rule contexts."""
from copy import deepcopy
import numpy as np
from .protocol import SEEDS,validate_clock
from ._signals.tree_factors import matrix,predict
from ._signals.volume_short_factors import append_volume
from ._signals.mining_ablation import ablate
from ._signals.bear_short_overlay import price_flags

def restore(x):
 if isinstance(x,list):return [restore(v)for v in x]
 if isinstance(x,dict):return {int(k)if k.isdigit()else k:restore(v)for k,v in x.items()}
 return x

def states(read,family):
 p=read('models/'+family+'.json.gz')
 if p['cutoff']!='2025-12-31'or p['family']!=family:raise ValueError('wrong frozen model cutoff/family')
 members=sorted(p['members'],key=lambda s:(s.get('execution_lag',0),s['seed']))
 if family.startswith('short_'):
  if len(members)!=14 or any([s['seed']for s in members if s.get('execution_lag')==lag]!=list(SEEDS)for lag in(1,2)):
   raise ValueError('incomplete short member roster')
 elif len(members)!=7 or [s['seed']for s in members]!=list(SEEDS):raise ValueError('incomplete tree member roster')
 width=47 if family=='price47'else 58 if family=='mining58'else 44
 if any(s['n_features']!=width for s in members):raise ValueError('model feature schema mismatch')
 return members

def forecast(read,market,allow_mining=False):
 days,prices=market['days'],market['prices'];validate_clock(days,prices)
 first=days.index('2025-12-31');x=matrix(days,prices,'CAL44');x47=append_volume(days,prices,None,7,'PRICE47')
 matrices={'base_tree':x,'stop44':x,'price47':x47,'short_huber':x,'short_median':x};scores={}
 if allow_mining:
  if 'mining'not in market:raise ValueError('missing actual PIT mining continuation')
  matrices['mining58']=ablate(x,market['mining'],'DYNAMICS',60)
 for family,xx in matrices.items():
  mm=states(read,family)
  if family.startswith('short_'):
   heads=[np.mean([predict(s,xx[first:])for s in mm if s['execution_lag']==lag],axis=0)for lag in(1,2)]
   values=(heads[0]+heads[1])/2
  else:values=np.mean([predict(s,xx[first:])for s in mm],axis=0)
  if not np.isfinite(values).all():raise ValueError('nonfinite frozen prediction')
  scores[family]=[None]*first+values.tolist()
 return scores

def expanded_context(read,name,market,scores):
 kind='median'if name=='B88A_S03'else'budget'if name=='K02'else'sizing'if name in('C02','C04')else'high_return'
 ctx=restore(read('contexts/'+kind+'.json.gz'));pol=read('policies.json');days,prices=market['days'],market['prices'];n=len(days);first=days.index('2025-12-31')
 old_n=3287
 def merge(old,new):
  if len(old)!=old_n:raise ValueError('unexpected original history length')
  out=list(old)+[None]*(n-old_n);out[first:]=new[first:];return out
 def bank_scores(bank,stop):
  for key in bank:bank[key]=list(bank[key])+[None]*(n-len(bank[key]))
  for key,fam in (('BASE_TREE','base_tree'),('CAL44_STOP',stop)):
   old=bank[key];old[first:]=scores[fam][first:]
 def flags(old):
  ff=price_flags(days,prices)
  for k in('bear','negative20'):
   old[k]=list(old[k])+ff[k][old_n:];old[k][first:]=ff[k][first:]
  old['available']=list(old['available'])+[True]*(n-old_n);old['available'][first:]=[True]*(n-first)
 def parent(bank):
  bank_scores(bank['scores'],'stop44');bank['policies']['Y01'][2026]=deepcopy(pol['y01']);flags(bank['flags'])
 def values(v):
  if v['days']!=days[:old_n]or v['prices']!=prices[:old_n]:raise ValueError('historical price prefix changed')
  v['days'],v['prices']=days,prices;bank_scores(v['scores'],'price47');v['policies'][2026]=deepcopy(pol['y01']);flags(v['flags'])
  if 'learner'in v:v['learner']=merge(v['learner'],scores['short_huber'])
 if kind=='high_return':
  values(ctx[0]);parent(ctx[1])
 elif kind=='median':
  values(ctx[0]);ctx[1]['MEDIAN']=merge(ctx[1]['MEDIAN'],scores['short_median'])
 elif kind=='budget':
  if ctx[0]!=days[:old_n]or ctx[1]!=prices[:old_n]:raise ValueError('budget history changed')
  ctx[0],ctx[1]=days,prices;parent(ctx[2]);ctx[3]=merge(ctx[3],scores['short_huber'])
 else:
  if ctx[0]!=days[:old_n]or ctx[1]!=prices[:old_n]:raise ValueError('sizing history changed')
  ctx[0],ctx[1]=days,prices;bank_scores(ctx[2],'stop44')
  if name=='C04':
   if 'mining58'not in scores:raise ValueError('C04 blocked: missing actual mining factors')
   ctx[2]['EXTRA_DYNAMICS_L60'][first:]=scores['mining58'][first:]
  ctx[3]['U02'][2026]=deepcopy(pol['u02']);ctx[4]['H03'][2026]=deepcopy(pol['h03_exit_choice'])
  for key in ctx[6]:
   ctx[6][key]=list(ctx[6][key])+[bool(pol['sizing_active_2026'][key])]*(n-old_n)
   ctx[6][key][first:]=[bool(pol['sizing_active_2026'][key])]*(n-first)
 return ctx
