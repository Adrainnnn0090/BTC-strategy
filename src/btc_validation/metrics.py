"""Period metrics and descriptive paired block-bootstrap; never used for selection."""
import math
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING,ROUND_HALF_EVEN
import numpy as np

def equity(m):return float(m['equity'])

def summarize(account):
 marks=account['marks'];eq=np.asarray([100.]+[equity(m)for m in marks]);rets=eq[1:]/eq[:-1]-1;n=len(rets)
 if not np.isfinite(eq).all()or np.any(eq<=0):raise ValueError('nonpositive/nonfinite equity')
 dd=float(np.max(1-eq/np.maximum.accumulate(eq)));std=float(np.std(rets,ddof=1))if n>1 else 0.;down=float(np.sqrt(np.mean(np.minimum(rets,0.)**2)))
 cagr=float((eq[-1]/100.)**(365/n)-1);trades=account['trades'];fees=sum(float(f['fee'])for f in account['fills']);fin=sum(float(x['cost'])for x in account.get('financing',[]))
 qty=[abs(float(m.get('signed_qty',m.get('btc',0))))for m in marks]
 return dict(start=marks[0]['date'],end=marks[-1]['date'],days=n,net_return_pct=100*(eq[-1]/100-1),max_daily_drawdown_pct=100*dd,
  annualized_volatility_pct=100*std*math.sqrt(365),sharpe_365_rf0=math.sqrt(365)*float(np.mean(rets))/std if std else None,
  sortino_365_rf0=math.sqrt(365)*float(np.mean(rets))/down if down else None,cagr_pct=100*cagr,calmar=cagr/dd if dd else None,
  completed_trades=len(trades),natural_trades=sum(not t['terminal']for t in trades),terminal_trades=sum(t['terminal']for t in trades),
  long_trades=sum(t.get('direction',1)==1 for t in trades),short_trades=sum(t.get('direction',1)==-1 for t in trades),
  win_rate_pct=100*sum(float(t['pnl'])>0 for t in trades)/len(trades)if trades else None,
  invested_days=sum(q>0 for q in qty),invested_day_fraction=sum(q>0 for q in qty)/n,fees_usdt=fees,financing_usdt=fin,
  turnover_usdt=sum(float(f['quantity'])*float(f['price'])for f in account['fills']),ending_equity=eq[-1],
  note='Post-fill daily marks; period-end liquidation included. Short-period annualization is descriptive only.')

def paired_bootstrap(account,baseline,block=14,iterations=2000,seed=20261025):
 a=np.asarray([100.]+[equity(m)for m in account['marks']]);b=np.asarray([100.]+[equity(m)for m in baseline['marks']])
 if len(a)!=len(b):raise ValueError('unaligned paired accounts')
 z=np.diff(np.log(a))-np.diff(np.log(b));n=len(z);rng=np.random.default_rng(seed);starts=rng.integers(0,n,size=(iterations,math.ceil(n/block)))
 idx=((starts[:,:,None]+np.arange(block))%n).reshape(iterations,-1)[:,:n];values=np.expm1(z[idx].sum(axis=1))*100
 return dict(block_days=block,iterations=iterations,relative_wealth_excess_pct=100*math.expm1(float(z.sum())),
  descriptive_95pct_interval=np.quantile(values,[.025,.975]).tolist(),qualification='Dependent overlapping strategies and reused history; not an alpha significance or causal certificate.')

def audit_buy_hold(account,prices_by_day,fee,slip):
 D=Decimal;fee=D(str(fee));slip=D(str(slip));fills=account['fills']
 if len(fills)!=2 or fills[0]['side']!='BUY'or fills[1]['side']!='SELL':raise AssertionError('B&H must have exactly two full fills')
 tick=D('.01');p0=D(str(prices_by_day[account['marks'][0]['date']]));ask=(p0*(1+slip)).quantize(tick,rounding=ROUND_CEILING)
 q=((D(100)-D('.01'))/(ask*(1+fee))).quantize(D('.00001'),rounding=ROUND_FLOOR)
 paid=(q*ask*fee).quantize(D('.00000001'),rounding=ROUND_HALF_EVEN);cash=D(100)-q*ask-paid
 if D(fills[0]['quantity'])!=q or D(fills[0]['price'])!=ask:raise AssertionError('B&H opening quote/size mismatch')
 for i,m in enumerate(account['marks']):
  bid=(D(str(prices_by_day[m['date']]))*(1-slip)).quantize(tick,rounding=ROUND_FLOOR)
  expected=cash+q*bid*(1-fee)
  if i==len(account['marks'])-1:
   close_fee=(q*bid*fee).quantize(D('.00000001'),rounding=ROUND_HALF_EVEN);expected=cash+q*bid-close_fee
  if abs(D(m['equity'])-expected)>D('.00000003'):raise AssertionError('B&H independent cash/equity mismatch')
 return dict(status='PASS',marks=len(account['marks']),fills=2,method='Independent Decimal spot cash, full budget, lot/quote precision, fees and liquidation marks')
