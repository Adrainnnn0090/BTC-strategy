"""Refit frozen final model configurations on physical prior-year inputs only.

This does not redo strategy selection or the historical inner search. Its scope
is parity of selected final estimators, not a new performance experiment.
"""
import argparse,json,sys,os
from pathlib import Path
from copy import deepcopy
from datetime import date
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor,GradientBoostingRegressor
from threadpoolctl import threadpool_limits
from .artifacts import ROOT,read
from .models import FAMILIES,annual_states
from ._runtime.tree_factors import tree_state


def training_read_allowed(path,family,year):
 p=Path(path).resolve()
 if any(p.is_relative_to(q)for q in (Path('/workspace/BTCStrategyResearchLedger'),Path('/workspace/BinanceTradingRobot'),Path('/workspace/Polymarket_Arbitrage_Robot'))):return False
 if not p.is_relative_to(ROOT):return True
 z=p.relative_to(ROOT).parts
 if not z:return False
 if z[0]=='training_inputs':return p==ROOT/'training_inputs'/str(year)/(family+'.json.gz')
 if z[0]=='models':return p in (ROOT/'models/manifest.json',ROOT/'models/feature_schema.json')or p.is_relative_to(ROOT/'models'/family/str(year))
 if z[0]in ('artifacts','data','provenance','review'):return False
 return True


def install_training_guard(family,year):
 reads=[]
 def hook(event,args):
  if event!='open'or not isinstance(args[0],(str,bytes)):return
  if args[1]is not None and'r'not in args[1]and'+'not in args[1]:return
  p=Path(os.fsdecode(args[0])).resolve()
  if not training_read_allowed(p,family,year):raise ValueError('training read denied: '+str(p))
  if p.is_relative_to(ROOT):reads.append(str(p.relative_to(ROOT)))
 sys.addaudithook(hook);return reads


def refit(family,year):
 if family not in FAMILIES or type(year)is not int or year not in range(2018,2026):raise ValueError('unregistered family/year')
 reads=install_training_guard(family,year);plan=read(f'training_inputs/{year}/{family}.json.gz')
 assert plan['cutoff']==plan['dates'][-1]==f'{year-1}-12-31'and plan['fold_year']==year
 assert all(date.fromisoformat(d)<=date(year-1,12,31)for d in plan['dates'])
 states=annual_states(family,year)
 if plan['model_missing']:
  assert year==2018 and not states
  return dict(family=family,fold_year=year,status='PRESERVED_MISSING',new_fits=0,protected_reads=reads)
 x=np.asarray(plan['features']);ids=np.asarray(plan['ids'],dtype=int);assert len(x)==len(plan['dates'])and np.isfinite(x).all()and len(ids)>=128
 maturity=62 if family.startswith('short_')else 61
 assert int(ids[-1])+maturity<=plan['cut_index']-6 and np.all(np.diff(ids)>0)
 exact=[]
 for old in states:
  yy=plan['targets']['L'+str(old['execution_lag'])]if family.startswith('short_')else plan['targets'];yy=np.asarray(yy)
  assert len(yy)==len(ids)and np.isfinite(yy).all()and x.shape[1]==old['n_features']
  if old['family']=='EXTRA':model=ExtraTreesRegressor(n_jobs=1,random_state=old['seed'],**old['profile'])
  else:model=GradientBoostingRegressor(loss=old['spec']['loss'],alpha=old['spec']['alpha'],random_state=old['seed'],n_iter_no_change=None,**old['profile'])
  with threadpool_limits(limits=1):model.fit(x[ids],yy)
  new=deepcopy(old);new['trees']=[tree_state(t)for t in model.estimators_.ravel()]if old['family']!='EXTRA'else[tree_state(t)for t in model.estimators_]
  if old['family']!='EXTRA':new['initial']=float(model.init_.constant_[0,0])
  if new!=old:raise AssertionError(f"refit numeric state differs {family}/{year}/seed{old['seed']}")
  exact.append(dict(seed=old['seed'],execution_lag=old.get('execution_lag'),numeric_state_exact=True))
 return dict(family=family,fold_year=year,status='PASS',cutoff=plan['cutoff'],physical_rows=len(x),training_samples=len(ids),new_fits=len(exact),states=exact,protected_reads=reads,qualification='Selected-final-estimator refit only; no new model/policy selection or OOS evidence.')


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--family',required=True,choices=FAMILIES);p.add_argument('--year',required=True,type=int,choices=range(2018,2026));a=p.parse_args();print(json.dumps(refit(a.family,a.year)),flush=True)
