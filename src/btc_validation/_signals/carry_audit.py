"""B22 annual-carry audit; independent opening decisions and original accounting. Independent raw wallet, PnL, financing, risk and net equity equations."""
from datetime import datetime,date,time,timedelta,timezone
from decimal import Decimal,ROUND_FLOOR,ROUND_CEILING
from .audit import check,close
D=Decimal

def audit(account,days,prices,targets,costs,annual,risk,entry_permission=None,annual_settlement=True):
 check(type(annual_settlement)is bool,'invalid annual settlement mode')
 if entry_permission is None:entry_permission=[True]*len(days)
 check(len(entry_permission)==len(days)and all(type(v)is bool for v in entry_permission),'invalid entry permission')
 fee,slip,lag=costs;fee=D(str(fee));slip=D(str(slip));annual=D(str(annual));wallet=D(100);debt=D(0);position=None;pending=None;allowed=0;peak=D(100);dd=D(0)
 fills=account['fills'];orders=account['orders'];marks=account['marks'];events=[];finance=[];trades=[];byday={f['date']:f for f in fills}
 check(len(byday)==len(fills)==len(orders),'partial/duplicate fill')
 for m in marks:
  i=days.index(m['date']);p=D(str(prices[i]));bid=(p*(1-slip)).quantize(D('.01'),rounding=ROUND_FLOOR);ask=(p*(1+slip)).quantize(D('.01'),rounding=ROUND_CEILING);target=targets[i-lag];last=m is marks[-1]
  if position and position['side']==-1:
   amount=position['q']*p*annual/D(365);debt+=amount;finance.append({'date':m['date'],'quantity':str(position['q']),'reference':str(prices[i]),'annual':str(annual),'cost':str(amount),'cumulative':str(debt)})
  if position:
   liquidation=bid if position['side']==1 else ask;gain=position['side']*position['q']*(liquidation-position['price']);liquidation_fee=position['q']*liquidation*fee
   rules=position['risk']['long' if position['side']==1 else 'short'];net_gain=gain-position['fee']-liquidation_fee-(debt-position['prior_debt']);basis=position['q']*position['price']+position['fee']
   position['peak']=max(position['peak'],basis+net_gain)
   trailing=rules.get('trailing_stop',0.) and position['peak']>=basis*(1+D(str(rules.get('trail_arm',0.)))) and basis+net_gain<=position['peak']*(1-D(str(rules.get('trailing_stop',0.))))
   if pending is None:
    reason='STOP_LOSS' if net_gain<=-basis*D(str(rules['stop_loss'])) else 'TRAIL_STOP' if trailing else 'TAKE_PROFIT' if net_gain>=basis*D(str(rules['take_profit'])) else None
    if reason:pending={'due':i+lag,'trigger':i,'reason':reason};events.append({'event':'TRIGGER','date':m['date'],**pending})
   due=pending is not None and pending['due']<=i;closing=last or (annual_settlement and m['date'].endswith('-12-31')) or target['direction']!=position['side'] or due;opening=False
  else:closing=False;opening=bool(entry_permission[i-lag] and target['direction'] and i>=allowed and not last and not m['date'].endswith('-12-31') and target['policy_year']==int(m['date'][:4]))
  f=byday.get(m['date']);check(bool(f)==bool(closing or opening),'entry-permission/direction/risk/cooldown mismatch')
  if f:
   o=orders[fills.index(f)];check(all(f[k]==v for k,v in o.items()),'fill/order attribution mismatch')
   q=D(f['quantity']);price=D(f['price']);charged=D(f['fee']);close(charged,q*price*fee,'native commission mismatch',1.01e-8)
   stamp=int(datetime.combine(date.fromisoformat(m['date'])+timedelta(days=1),time(),timezone.utc).timestamp())*10**9+10_000_000;check(f['ts_event']==stamp,'native fill clock mismatch')
   check(f['fee_asset']=='USDT' and q%D('.00001')==0 and q*price>=5,'native precision/minimum mismatch')
   if opening:
    side=target['direction'];expected_price=ask if side==1 else bid;fraction=D(str(target['long_fraction'] if side==1 else target['short_fraction']));expected_q=(((wallet-debt)*fraction-D('.01'))/(expected_price*(1+fee))).quantize(D('.00001'),rounding=ROUND_FLOOR)
    check(f['action']=='OPEN' and f['side']==('BUY' if side==1 else 'SELL') and f['reason']=='ENTRY' and price==expected_price and q==expected_q,'opening size or quote mismatch')
    wallet-=charged;position={'side':side,'q':q,'price':price,'fee':charged,'prior_debt':debt,'date':m['date'],'peak':q*price+charged,'risk':target['risk'],'policy_year':target['policy_year']}
   else:
    reason='TERMINAL' if last else 'PERIOD_CLOSE' if annual_settlement and m['date'].endswith('-12-31') else pending['reason'] if due else 'SIGNAL';expected_price=bid if position['side']==1 else ask
    check(f['action']=='CLOSE' and f['side']==('SELL' if position['side']==1 else 'BUY') and f['reason']==reason and q==position['q'] and price==expected_price,'close mismatch')
    gross=position['side']*q*(price-position['price']);wallet+=gross-charged;borrow=debt-position['prior_debt'];fees=position['fee']+charged
    trades.append({'entry_date':position['date'],'exit_date':m['date'],'direction':position['side'],'quantity':str(q),'entry_price':str(position['price']),'exit_price':str(price),'gross_pnl':str(gross),'fees':str(fees),'financing':str(borrow),'pnl':str(gross-fees-borrow),'terminal':reason in ('TERMINAL','PERIOD_CLOSE'),'exit_reason':reason,'policy_year':position['policy_year']})
    if pending:allowed=i+rules['cooldown_days']+1;events.append({'event':'CLOSED','date':m['date'],'next_allowed_index':allowed,**pending})
    pending=None;position=None
  gross=D(0);reserve=D(0);signed=D(0)
  if position:
   quote=bid if position['side']==1 else ask;signed=position['side']*position['q'];gross=signed*(quote-position['price']);reserve=position['q']*quote*fee
  equity=wallet-debt+gross-reserve
  close(m['raw_cash'],wallet,'native raw wallet mismatch');close(m['financing_total'],debt,'financing adjustment mismatch');close(m['signed_qty'],signed,'position mismatch',1e-12);close(m['unrealized_pnl'],gross,'unrealized PnL mismatch');close(m['exit_fee_reserve'],reserve,'liquidation fee mismatch');close(m['equity'],equity,'net equity mismatch')
  check(equity>0,'nonpositive net equity');peak=max(peak,equity);dd=max(dd,1-equity/peak)
 check(position is None,'nonflat terminal position');check(finance==account['financing'] and events==account['risk_events'] and trades==account['trades'],'financing/risk/trade attribution differs')
 s=account['summary'];close(s['return_pct'],wallet-debt-100,'summary return mismatch');close(s['max_drawdown_pct'],100*dd,'summary drawdown mismatch');close(sum(D(t['pnl']) for t in trades),wallet-debt-100,'full realized PnL conservation failed')
 previous=D(100)
 for y in s['annual']:
  finish=D([m for m in marks if m['date'].startswith(y['year'])][-1]['equity']);close(y['return_pct'],100*(finish/previous-1),'annual return mismatch');previous=finish
 natural=[t for t in trades if not t['terminal']];positive=sorted([D(t['pnl']) for t in natural if D(t['pnl'])>0],reverse=True)
 check(s['natural_trades']==len(natural) and s['short_trades']==sum(t['direction']==-1 for t in natural),'trade count mismatch')
 if positive:close(s['best_two_positive_contribution_fraction'],sum(positive[:2])/sum(positive),'concentration mismatch')
 close(s['short_pnl'],sum(D(t['pnl']) for t in trades if t['direction']==-1),'short contribution mismatch');close(s['long_pnl'],sum(D(t['pnl']) for t in trades if t['direction']==1),'long contribution mismatch')
 return {'status':'PASS','marks':len(marks),'fills':len(fills),'financing_rows':len(finance),'financing_scope':'separate modeled adjustment; raw native wallet reconciled independently'}
