"""Compose retained strategies with the original pure rules and frozen contexts."""
from copy import deepcopy
from .validation import development_market
from .artifacts import read,restore,config
from ._runtime.conditional_short import component
from ._runtime.exit_coordinate import desired,parent_score,patch_policy
from ._runtime.patient_profit_exit import ARMS as PROFIT_ARMS,patch_profit_exit
from ._runtime.long_vol_budget import patch_budget
from ._runtime.faster_cold_short import ARMS as COLD_ARMS,apply_cold_gate
from ._runtime.cold_entry_momentum import ARMS as ENTRY_ARMS,patch_entry
from ._runtime.shorter_cold_momentum import ARMS as SHORTER_ARMS,patch_entry as shorter_entry
from ._runtime.cold_short_profit_trailing import ARMS as TRAIL_ARMS,patch_risk as patch_trail
from ._runtime.long_profit_local_coordinate import ARMS as CAP_ARMS,patch_risk as patch_cap
from ._runtime.cold_budget import targets as budget_targets


def context(name):return restore(read('artifacts/contexts/'+config(name)['context']+'.json.gz'))


def compose(name,ctx=None):
 cfg=config(name);ctx=context(name)if ctx is None else ctx
 clock=ctx[0]if cfg['context']in('high_return','median')else dict(days=ctx[0],prices=ctx[1])
 development_market(clock['days'],clock['prices'],full=True)
 if cfg['context']=='high_return':
  values,bank,carry=ctx;days,prices=values['days'],values['prices']
  if name=='Y01':return days,prices,*desired(days,prices,parent_score(bank['scores'],'H03'),bank['policies']['Y01'])
  t,e=component(days,prices,values['scores'],{'Y01':values['policies']},values['flags'],values['learner'],.5,'MODEL')
  t,e,_=patch_profit_exit(t,e,PROFIT_ARMS[2]);t,e,_=patch_budget(days,t,e,values['policies'],None)
  t,e,_=apply_cold_gate(days,prices,values['scores'],values['flags'],values['policies'],t,e,COLD_ARMS[1])
  t,e,_=patch_entry(days,prices,values['scores'],t,e,ENTRY_ARMS[0])
  if name=='MX03':t,e,_=shorter_entry(days,prices,values['scores'],t,e,SHORTER_ARMS[2])
  if name in ('TS04','LP35'):t,e,_=patch_trail(values['scores'],t,e,TRAIL_ARMS[0])
  if name=='LP35':t,e,_=patch_cap(values['scores'],t,e,CAP_ARMS[1])
 elif cfg['context']=='median':
  values,scores,_=ctx;days,prices=values['days'],values['prices']
  t,e=component(days,prices,values['scores'],{'Y01':values['policies']},values['flags'],scores['MEDIAN'],.5,'MODEL')
 elif cfg['context']=='budget':
  days,prices,bank,learner=ctx;t,e=budget_targets(days,prices,bank,learner,.25,.25)
 elif cfg['context']=='sizing':
  days,prices,scores,policies,choices,ranks,active,*_=ctx
  if name=='C02':
   pp={y:patch_policy(p,choices['H03'][y])for y,p in policies['U02'].items()}
   t,e=desired(days,prices,parent_score(scores,'H03'),pp);key='Y01'
  else:t,e=desired(days,prices,scores['EXTRA_DYNAMICS_L60'],policies['U02']);key='Y04'
  t=[{**row,'long_fraction':row['long_fraction']*(.75 if a else 1.)}for row,a in zip(t,active[key],strict=True)]
 else:raise ValueError('unsupported context')
 if days[0]!='2017-01-01'or days[-1]!='2025-12-31':raise ValueError('development context boundary')
 return days,prices,t,e


def verify_targets(name):
 days,prices,target,entry=compose(name);expected=read('artifacts/targets/'+name+'.json.gz')
 assert target==expected['targets'],name+' target mismatch'
 assert entry==expected['entry_permission'],name+' permission mismatch'
 return dict(id=name,positions=len(days),targets_exact=True,permissions_exact=True)
