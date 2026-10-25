"""Read-only comparison of fixed LP35 signals under four stored cost scenarios."""
from decimal import Decimal as D, ROUND_DOWN
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
STUDY=ROOT/'studies/B109-long-profit-local-coordinate'
def read(p):
 p=Path(p)
 assert p.is_relative_to(ROOT)
 assert not any(s in p.parts for s in ('2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
 if p.suffix=='.gz':
  with gzip.open(p,'rt')as f:return json.load(f)
 return json.loads(p.read_text())
reg=read(STUDY/'registration.json')
assert reg['costs']=={'BASE':[.001,.0005,1],'STRESS':[.003,.001,1],
                     'SEVERE':[.005,.002,1],'DELAY':[.003,.001,2]}
assert reg['financing']=={'BASE':.05,'STRESS':.1,'SEVERE':.3,'DELAY':.1}
accounts={c:read(STUDY/'accounts/LP35'/f'{c}.json.gz')for c in reg['costs']}
for a in accounts.values():
 assert a['marks'][0]['date']=='2018-01-01' and a['marks'][-1]['date']=='2025-12-31'

# A controlled first-entry calculation has equal starting equity and budget;
# later quantity differences also include the changed accumulated equity path.
first_entries=[]
for case,a in accounts.items():
 fill=a['fills'][0]
 fee=D(str(reg['costs'][case][0]))
 expected=((D(100)*D('.75')-D('.01'))/(D(fill['price'])*(1+fee))).quantize(D('.00001'),rounding=ROUND_DOWN)
 assert expected==D(fill['quantity'])
 financing=a['financing'][0]
 annual=D(str(reg['financing'][case]))
 assert D(financing['cost'])==D(financing['quantity'])*D(str(financing['reference']))*annual/D(365)
 first_entries.append({'case':case,'date':fill['date'],'entry_price':fill['price'],
                       'quantity':fill['quantity'],'equal_initial_budget':'75',
                       'annual_borrow_rate':str(annual)})
assert len({x['quantity']for x in first_entries})>1

signal=read(STUDY/'folds/2020/predictions.json.gz')
i=signal['dates'].index('2020-04-29')
scores={k:v[i]for k,v in signal['scores'].items()}
assert scores['BASE_TREE']>0 and scores['CAL44_STOP']>0
same_signal=[]
for case in ('BASE','STRESS','SEVERE','DELAY'):
 a=accounts[case]
 entrydate='2020-05-01'if case=='DELAY'else'2020-04-30'
 trade=next(t for t in a['trades']if t['entry_date']==entrydate and t['direction']==1)
 fill=next(f for f in a['fills']if f['date']==entrydate and f['action']=='OPEN')
 event=next(e for e in a['risk_events']if e['event']=='TRIGGER'and entrydate<=e['date']<=trade['exit_date'])
 row={'case':case,'shared_signal_date':'2020-04-29','entry_date':entrydate,'quantity':trade['quantity'],
      'entry_price':trade['entry_price'],'trigger_date':event['date'],'trigger_reason':event['reason'],
      'exit_date':trade['exit_date'],'exit_reason':trade['exit_reason']}
 if case!='DELAY':
  m=next(m for m in a['marks']if m['date']=='2021-01-07')
  fee=D(str(reg['costs'][case][0]));q=D(trade['quantity']);px=D(trade['entry_price'])
  basis=q*px+D(fill['fee'])
  net=q*(D(m['bid'])-px)-D(fill['fee'])-q*D(m['bid'])*fee
  ratio=net/basis
  triggered=net>=basis*D('3.5')
  assert triggered==(case=='BASE')
  assert (event['date']=='2021-01-07')==triggered
  adjusted=D(m['raw_cash'])-D(m['financing_total'])+D(m['unrealized_pnl'])-D(m['exit_fee_reserve'])
  assert abs(adjusted-D(m['equity']))<=D('1e-22')
  row.update(risk_check_date='2021-01-07',net_asset_pnl_on_basis=str(ratio),
             take_profit_threshold='3.5',threshold_crossed=triggered,
             stored_NAV_identity_pass=True)
 same_signal.append(row)

# A positive pair of long model outputs is not a guarantee of realized profit.
p=read(STUDY/'folds/2019/predictions.json.gz')
idx=p['dates'].index('2019-07-01')
positive={k:v[idx]for k,v in p['scores'].items()}
assert positive['BASE_TREE']>0 and positive['CAL44_STOP']>0
negative=next(t for t in accounts['STRESS']['trades']if t['entry_date']=='2019-07-02'and t['direction']==1)
assert D(negative['pnl'])<0 and D(negative['gross_pnl'])<0
assert D(negative['gross_pnl'])-D(negative['fees'])-D(negative['financing'])==D(negative['pnl'])

result={'round':6,'all_checks_pass':True,'strategy':'LP35','scenario_costs_fee_slip_lag':reg['costs'],
 'scenario_annual_borrow':reg['financing'],'equal_initial_budget_quantity_check':first_entries,
 'shared_model_scores_2020_04_29':scores,'same_signal_different_cost_paths':same_signal,
 'positive_forecast_negative_trade':{'signal_date':'2019-07-01','scores':positive,'cost_case':'STRESS','trade':negative,
       'interpretation':'gross也已为负，不能把该次亏损全归因于费用；监督目标、持仓规则及实现不确定性均不同于利润保证。'},
 'scope':'仅四成本开发期已存账户及固定模型预报对照/算术重核，未调用native engine或任何原写入器。'}
with (OUT/'r06_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items()if k!='positive_forecast_negative_trade'},ensure_ascii=False))
