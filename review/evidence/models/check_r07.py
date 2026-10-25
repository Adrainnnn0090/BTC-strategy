"""Read-only target field and actual cross-year entry-risk ownership audit."""
import sys
sys.dont_write_bytecode=True
from datetime import date
import gzip,json,math
from pathlib import Path
import numpy as np
ROOT=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
sys.path.insert(0,str(ROOT))
from lab.full_retained import load_bank
from lab.price_trail_activation import frame
from lab.conditional_short import component
from lab.patient_profit_exit import patch_profit_exit,ARMS as P_ARMS
from lab.long_vol_budget import patch_budget
from lab.faster_cold_short import apply_cold_gate,ARMS as C_ARMS
from lab.cold_entry_momentum import patch_entry,ARMS as E_ARMS
from lab.shorter_cold_momentum import patch_entry as shorter_entry,ARMS as X_ARMS
from lab.cold_short_profit_trailing import patch_risk as patch_trail,ARMS as T_ARMS
from lab.long_profit_local_coordinate import patch_risk as patch_cap,ARMS as L_ARMS
from lab.cold_budget import targets as budget_targets
from lab.signals import Features
from lab.b05 import forecast_year

def read(p):
 p=Path(p)
 assert p.is_relative_to(ROOT)
 assert not any(s in p.parts for s in ('2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
 if p.suffix=='.gz':
  with gzip.open(p,'rt')as f:return json.load(f)
 return json.loads(p.read_text())
market=read(ROOT/'data/walkforward-v1/2025/train.json')+read(ROOT/'data/walkforward-v1/2025/test.json')
days=[r['date']for r in market];prices=[r['price']for r in market]
where={d:i for i,d in enumerate(days)}
source=ROOT/'studies/B50-cross-market-fixed-averages'
bank=load_bank(source,days,read,2025)
policies=bank['policies']['Y01']
records={y:read(ROOT/'studies/B109-long-profit-local-coordinate/folds'/str(y)/'predictions.json.gz')for y in range(2018,2026)}
values,_=frame(days,prices,records,policies)
baseline,base_entry=component(days,prices,values['scores'],{'Y01':policies},values['flags'],values['learner'],.5,'MODEL')
px,pe,_=patch_profit_exit(baseline,base_entry,P_ARMS[2])
vx,ve,budget_diag=patch_budget(days,px,pe,policies,None)
ct,ce,_=apply_cold_gate(days,prices,values['scores'],values['flags'],policies,vx,ve,C_ARMS[1])
me,ee,_=patch_entry(days,prices,values['scores'],ct,ce,E_ARMS[0])
mx,xe,_=shorter_entry(days,prices,values['scores'],me,ee,X_ARMS[2])
ts,te,_=patch_trail(values['scores'],me,ee,T_ARMS[0])
lp,le,_=patch_cap(values['scores'],ts,te,L_ARMS[1])
k02,ke=budget_targets(days,prices,bank,values['learner'],.25,.25)
median=[None]*len(days)
for y in range(2018,2026):
 p=read(ROOT/'studies/B88A-short-net-loss-families/folds'/str(y)/'predictions.json.gz')
 for d,v in zip(p['dates'],p['scores']['MEDIAN']):median[where[d]]=v
md,de=component(days,prices,values['scores'],{'Y01':policies},values['flags'],median,.5,'MODEL')

def reg_arm(study,name):
 p=read(ROOT/'studies'/study/'registration.json')
 return next(x for x in p['recipes']if x['id']==name)['arm']
assert E_ARMS[0]==reg_arm('B105-cold-entry-momentum','ME01')
assert X_ARMS[2]==reg_arm('B106-shorter-cold-entry-momentum','MX03')
assert T_ARMS[0]==reg_arm('B107-cold-short-profit-trailing','TS04')
assert L_ARMS[1]==reg_arm('B109-long-profit-local-coordinate','LP35')

cold=[a is None or b is None for a,b in zip(values['scores']['BASE_TREE'],values['scores']['CAL44_STOP'])]
assert ct==me==mx
assert te==ee==le
counts={'ME01_permission_changes_from_CT02':0,'MX03_permission_changes_from_ME01':0,
        'TS04_short_trail_rows_changed':0,'LP35_long_take_profit_rows_changed':0,
        'positive_long_vol_discount_rows_removed':0}
for i,d in enumerate(days):
 p=policies[forecast_year(d)]
 assert me[i]['long_fraction']==mx[i]['long_fraction']==ts[i]['long_fraction']==lp[i]['long_fraction']==p['fraction']
 assert baseline[i]['long_fraction']==k02[i]['long_fraction']==md[i]['long_fraction']
 counts['positive_long_vol_discount_rows_removed']+=int(baseline[i]['long_fraction']<lp[i]['long_fraction'])
 if ce[i]!=ee[i]:assert cold[i] and me[i]['direction']==-1;counts['ME01_permission_changes_from_CT02']+=1
 if ee[i]!=xe[i]:assert cold[i] and me[i]['direction']==-1;counts['MX03_permission_changes_from_ME01']+=1
 if not cold[i]:assert ce[i]==ee[i]==xe[i]
 before=dict(me[i]['risk']['short']);after=dict(ts[i]['risk']['short'])
 expected=dict(before,trailing_stop=.04)if cold[i]else before
 assert after==expected
 counts['TS04_short_trail_rows_changed']+=int(before!=after)
 assert {**ts[i],'risk':me[i]['risk']}==me[i]
 long=dict(ts[i]['risk']['long']);long['take_profit']=3.5
 assert lp[i]['risk']['long']==long and lp[i]['risk']['short']==ts[i]['risk']['short']
 assert {**lp[i],'risk':ts[i]['risk']}==ts[i]
 counts['LP35_long_take_profit_rows_changed']+=int(lp[i]['risk']['long']!=ts[i]['risk']['long'])

vol=Features(prices).vol(20)
exposures={name:{'cold_active_short_rows':0,'post_active_short_rows':0,'max_long_fraction':0.,'max_short_fraction':0.}
           for name in ('LP35','TS04','ME01','MX03','K02','B88A_S03')}
for name,target in [('LP35',lp),('TS04',ts),('ME01',me),('MX03',mx),('K02',k02),('B88A_S03',md)]:
 for i,row in enumerate(target):
  e=exposures[name]
  e['max_long_fraction']=max(e['max_long_fraction'],row['long_fraction'])
  e['max_short_fraction']=max(e['max_short_fraction'],row['short_fraction'])
  if row['direction']!=-1:continue
  p=policies[forecast_year(days[i])]
  scale=min(1.,p['vol_target']/max(float(vol[i]),1e-12))if p['vol_target']and math.isfinite(float(vol[i]))else 1.
  multiplier=.25 if name=='K02'else .75 if cold[i]else .5
  assert row['short_fraction']==multiplier*scale
  e['cold_active_short_rows'if cold[i]else'post_active_short_rows']+=1

# Actual trade spans a policy-year change. Its pending-event cooldown uses the
# entry-owned 2020 risk rather than the contemporaneous 2021 target risk.
a=read(ROOT/'studies/B109-long-profit-local-coordinate/accounts/LP35/BASE.json.gz')
trade=next(x for x in a['trades']if x['entry_date']=='2020-04-30'and x['direction']==1)
assert trade['exit_date']=='2021-01-08'and trade['policy_year']==2020
entry_row=lp[where[trade['entry_date']]-1]
current_row=lp[where[trade['exit_date']]-1]
entry_risk=entry_row['risk']['long'];current_risk=current_row['risk']['long']
assert entry_risk['cooldown_days']==3 and current_risk['cooldown_days']==1
closed=next(x for x in a['risk_events']if x['event']=='CLOSED'and x['date']==trade['exit_date'])
exit_index=where[trade['exit_date']]
assert closed['next_allowed_index']==exit_index+entry_risk['cooldown_days']+1
assert closed['next_allowed_index']!=exit_index+current_risk['cooldown_days']+1
result={'round':7,'all_checks_pass':True,'target_rows_compared':len(days),
 'field_change_counts':counts,'long_budget_patch_diagnostic':budget_diag,'exposure_contracts':exposures,
 'entry_owned_cross_year':{'trade':trade,'entry_signal_date':days[where[trade['entry_date']]-1],
   'entry_risk':entry_risk,'current_signal_risk_at_exit':current_risk,'closed_event':closed,
   'exit_index':exit_index,'entry_owned_next_allowed_index':exit_index+entry_risk['cooldown_days']+1,
   'incorrect_current_year_next_allowed_index':exit_index+current_risk['cooldown_days']+1},
 'scope':'由冻结预报/年度策略通过纯目标补丁重建3287行；只读比较一个实际跨年账户事件，无账户重放/模型训练/原写入器。'}
with (OUT/'r07_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
