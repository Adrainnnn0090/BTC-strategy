"""Read-only annual cash-PnL and cold/model availability attribution contrasts."""
from decimal import Decimal as D
import gzip,json
from pathlib import Path
ROOT=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
STUDY=ROOT/'studies/B109-long-profit-local-coordinate'
def read(p):
 p=Path(p)
 assert p.is_relative_to(ROOT)
 assert not any(z in p.parts for z in ('2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
 if p.suffix=='.gz':
  with gzip.open(p,'rt')as f:return json.load(f)
 return json.loads(p.read_text())

cold=read(STUDY/'folds/2018/predictions.json.gz')
first=read(STUDY/'folds/2019/predictions.json.gz')
assert all(all(v is None for v in values)for values in cold['scores'].values())
assert all(v is None for v in cold['learner'])
assert first['dates'][0]=='2018-12-31'
assert all(values[0]is not None for values in first['scores'].values())and first['learner'][0]is not None

accounts={name:read(STUDY/'accounts'/name/'STRESS.json.gz')for name in ('P02','ME01','MX03','TS04','LP35')}
results={}
for name,a in accounts.items():
 marks=a['marks']
 assert marks[0]['date']=='2018-01-01'and marks[-1]['date']=='2025-12-31'
 prior=D(100);annual=[]
 for year in range(2018,2026):
  ending=next(m for m in marks if m['date']==f'{year}-12-31')
  eq=D(ending['equity']);delta=eq-prior;ret=(eq/prior-1)*100
  recorded=next(x['return_pct']for x in a['summary']['annual']if x['year']==str(year))
  assert abs(float(ret)-recorded)<2e-10
  realized=sum((D(t['pnl'])for t in a['trades']if t['exit_date'].startswith(str(year))),D(0))
  annual.append({'year':year,'starting_net_equity':str(prior),'ending_net_equity':str(eq),
                 'net_equity_change_usdt':str(delta),'return_pct':str(ret),
                 'exit_book_realized_pnl_usdt':str(realized),'year_end_signed_qty':ending['signed_qty']})
  prior=eq
 assert abs(sum((D(x['net_equity_change_usdt'])for x in annual),D(0))-(prior-D(100)))<D('1e-18')
 assert abs(sum((D(t['pnl'])for t in a['trades']),D(0))-(prior-D(100)))<D('1e-18')
 entries2018=[t for t in a['trades']if t['entry_date']<'2019-01-01']
 assert all(t['direction']==-1 for t in entries2018)
 if name!='P02':
  assert D(annual[0]['year_end_signed_qty'])==0
  assert abs(D(annual[0]['net_equity_change_usdt'])-D(annual[0]['exit_book_realized_pnl_usdt']))<D('1e-18')
 positive=[x for x in annual if D(x['net_equity_change_usdt'])>0]
 top=sorted(positive,key=lambda x:D(x['net_equity_change_usdt']),reverse=True)[:2]
 positive_sum=sum((D(x['net_equity_change_usdt'])for x in positive),D(0))
 share=sum((D(x['net_equity_change_usdt'])for x in top),D(0))/positive_sum
 results[name]={'annual':annual,'2018_entry_short_trades':len(entries2018),
  'post2018_equity_growth_factor':str(prior/D(annual[0]['ending_net_equity'])),
  'top2_years_by_positive_cash_change':[x['year']for x in top],
  'top2_share_positive_annual_cash_change':str(share)}

schedules={}
for name in ('ME01','MX03','TS04'):
 schedules[name]=[(t['entry_date'],t['exit_date'],t['direction'],t['exit_reason'])
                  for t in accounts[name]['trades']if t['entry_date']>='2019-01-01']
assert schedules['ME01']==schedules['MX03']==schedules['TS04']
assert results['LP35']['annual'][0]==results['TS04']['annual'][0]

result={'round':9,'all_checks_pass':True,'cost_case':'STRESS',
 'model_availability':{'2018_fold_all_model_heads_none':True,'first_finite_decision_date':'2018-12-31',
   'first_execution_date_at_lag1':'2019-01-01','2018_entries_all_short_cold_fallback':True},
 'P02_cold_entry_cross_year_trade':next(t for t in accounts['P02']['trades']if t['entry_date']=='2018-11-14'and t['exit_date']=='2019-01-01'),
 'same_post2018_trade_schedules':['ME01','MX03','TS04'],'post2018_schedule_trades':len(schedules['ME01']),
 'LP35_TS04_2018_books_annual_exact':True,'results':results,
 'annual_pnl_definition':'net_equity_change_usdt=本年末融资/清算费调整净值-上年末净值；可能包含跨年未实现变化。exit_book_realized_pnl按退出年归集，单独报告。',
 'concentration_definition':'top2_share分母为正年度净值现金增量之和；不是样本外稳定概率、不是去除交易回测。',
 'scope':'固定已存STRESS开发期账户算术对比，无新拟合、删交易重跑、再选择策略或2026数据。'}
with (OUT/'r09_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'all_checks_pass':True,'model_availability':result['model_availability'],
 'post2018_identical_schedule_trades':len(schedules['ME01']),
 'summary':{name:{'2018_net_change':d['annual'][0]['net_equity_change_usdt'],
  'post2018_growth':d['post2018_equity_growth_factor'],
  'top2_years':d['top2_years_by_positive_cash_change'],'top2_positive_cash_share':d['top2_share_positive_annual_cash_change']}
  for name,d in results.items()}},ensure_ascii=False))
