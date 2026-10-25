"""Synthetic, read-only factor causality/schema check. No economic data reads."""
import sys
sys.dont_write_bytecode=True
from datetime import date,timedelta
import json
from pathlib import Path
import numpy as np

ROOT=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
sys.path.insert(0,str(ROOT))
from lab.tree_factors import matrix,PATH_NAMES,CAL_NAMES
from lab.volume_short_factors import append_volume
from lab.mining_ablation import ablate
from lab.mining_features import feature_rows,timestamp,NAMES,MASK_NAMES
from lab.volume_long_core import replace_stop

length=900
cut=500
days=[(date(2017,1,1)+timedelta(days=i)).isoformat()for i in range(length)]
t=np.arange(length,dtype=float)
prices=np.exp(8+.0009*t+.04*np.sin(t/13)+.015*np.cos(t/5))
changed=prices.copy()
changed[cut:]*=np.exp(.7+.2*np.sin(t[cut:]/3))
cal=matrix(days,prices,'CAL44')
cal_changed=matrix(days,changed,'CAL44')
cal_prefix=matrix(days[:cut],prices[:cut],'CAL44')
price=append_volume(days,prices,None,7,'PRICE47')
price_changed=append_volume(days,changed,None,7,'PRICE47')
price_prefix=append_volume(days[:cut],prices[:cut],None,7,'PRICE47')
records=[dict(date=d,lagged={'60':{'mask':[1.,.2], 'values':[float(i+k)/1000 for k in range(12)]}})
         for i,d in enumerate(days)]
records_changed=[dict(date=d,lagged={'60':{'mask':[1.,.2], 'values':[float(i+k)/1000 for k in range(12)]}})
                 if i<cut else dict(date=d,lagged={'60':{'mask':[0.,1.], 'values':[0.]*12}})
                 for i,d in enumerate(days)]
mining=ablate(cal,records,'DYNAMICS',60)
mining_changed=ablate(cal_changed,records_changed,'DYNAMICS',60)
mining_prefix=ablate(cal_prefix,records[:cut],'DYNAMICS',60)
checks={}
for name,full,modified,prefix,width in (
 ('CAL44',cal,cal_changed,cal_prefix,44),
 ('PRICE47',price,price_changed,price_prefix,47),
 ('MINING58_DYNAMICS_L60',mining,mining_changed,mining_prefix,58)):
 assert full.shape==(length,width)
 assert np.array_equal(full[:cut],modified[:cut])
 assert np.array_equal(full[:cut],prefix)
 assert np.isfinite(full).all() and np.array_equal(full[:252],np.zeros((252,width)))
 checks[name]={'shape':list(full.shape),'suffix_mutation_prefix_max_error':float(np.max(np.abs(full[:cut]-modified[:cut]))),
               'truncated_prefix_max_error':float(np.max(np.abs(full[:cut]-prefix))),
               'first_252_all_zero':True}
assert np.array_equal(price[:,:44],cal) and np.array_equal(mining[:,:44],cal)
assert np.array_equal(price[252:,44],np.ones(length-252))
assert np.array_equal(mining[252:,44:46],np.tile([1.,.2],(length-252,1)))
assert np.array_equal(mining[252:,46:54],np.asarray([r['lagged']['60']['values'][:8]for r in records[252:]]))
assert np.array_equal(mining[:,54:58],np.zeros((length,4)))
for i in (252,400,899):
 j=i-7
 long=prices[j-89:j+1].mean()
 expected=np.asarray([np.clip(np.log((prices[j-w+1:j+1].mean()+1e-12)/(long+1e-12)),-5,5)for w in (7,30)])
 assert np.array_equal(price[i,45:47],expected)

class MustNotRead:
 def __iter__(self):raise AssertionError('PRICE47 accessed external observations')
 def __getitem__(self,key):raise AssertionError('PRICE47 accessed external observations')
assert np.array_equal(price,append_volume(days,prices,MustNotRead(),7,'PRICE47'))

# Mining source clock: an observation one millisecond after the lagged cutoff
# must not change that day's reconstructed source frontier.
day='2018-01-01'
cutoff_ms=(timestamp(day)-60*86400-7200)*1000
headers=30000
times=np.arange(headers,dtype=np.int64)*600+timestamp('2016-01-01')
targets=[10**30]*headers
work=np.arange(headers+1,dtype=float)*1000
past=[[27000,cutoff_ms-1]]
future=past+[[28000,cutoff_ms+1]]
a=feature_rows([day],times,targets,work,past,lags=(60,))
b=feature_rows([day],times,targets,work,future,lags=(60,))
assert a==b
trace=a[0]['lagged']['60']['trace']
assert trace['cutoff_ms']==cutoff_ms and trace['observed_height']==27000 and trace['confirmed_height']==26900
stale_day=(date.fromisoformat(day)+timedelta(days=4)).isoformat()
stale=feature_rows([stale_day],times,targets,work,past,lags=(60,))[0]['lagged']['60']
assert stale['mask'][0]==0. and stale['values']==[0.]*12 and stale['trace']['fresh'] is False
assert stale['mask'][1]>0
scores={'BASE_TREE':[None,.1,0.],'CAL44_STOP':[None,-.1,0.]}
assert replace_stop(scores,[None,.2,0.])['CAL44_STOP']==[None,.2,0.]
rejected=False
try:replace_stop(scores,[0.,.2,0.])
except ValueError:rejected=True
assert rejected

base_names=['logret5','logret20','logret60','logret120','logret252',
 'log_price_mean20','log_price_mean100','log_price_mean200','annualized_vol20','annualized_vol60',
 'price_rollinghigh60_minus1','efficiency20','logret1','logret3','logret10','annualized_vol5',
 'annualized_downside20','rsi14_div100','price_rollinghigh20_minus1','efficiency5']
cal_names=base_names+list(PATH_NAMES)+list(CAL_NAMES)
assert len(cal_names)==44
schema={
 'CAL44':[{'index':i,'name':n}for i,n in enumerate(cal_names)],
 'PRICE47':[{'index':i,'name':n}for i,n in enumerate(cal_names+['postwarmup_constant1','price_log_mean7_mean90_lag7','price_log_mean30_mean90_lag7'])],
 'MINING58_DYNAMICS_L60':[{'index':i,'name':n,'forced_zero':54<=i<58}for i,n in enumerate(cal_names+list(MASK_NAMES)+list(NAMES))]
}
with (OUT/'r04_feature_schema.json').open('x')as f:json.dump(schema,f,ensure_ascii=False,indent=2)
result={'round':4,'all_checks_pass':True,'synthetic_rows':length,'unaltered_prefix_rows':cut,
 'factor_prefix_checks':checks,'schema_order_checks':{'CAL44_prefix_in_PRICE47_and_MINING58':True,'PRICE_L7_extra_formula_rows':[252,400,899],
 'MINING58_masks_at':[44,45],'MINING58_dynamics_at':[46,53],'MINING58_forced_zero_state_at':[54,57]},
 'PRICE47_external_observations_not_accessed':True,'mining_future_observation_ignored':True,
 'mining_asof_trace':trace,'stale_mining_mask':stale['mask'],'stale_mining_values_all_zero':True,
 'None_to_zero_STOP_replacement_rejected':True,
 'scope':'只用2017–2019合成价格/源事件与冻结因子函数，未训练模型或读取经济数据；禁止bytecode写入。'}
with (OUT/'r04_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
