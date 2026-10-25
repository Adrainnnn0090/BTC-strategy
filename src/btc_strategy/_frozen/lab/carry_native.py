"""B22 native companion: optional carry of existing positions across calendar years.

Copied from the frozen B18 adapter; default annual settlement is identical.
Only calendar-only liquidation is optional. Entry-owned risk and financing persist.
"""
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal,ROUND_DOWN
import hashlib,json,math,signal
from nautilus_trader.backtest import BacktestEngine,BacktestEngineConfig
from nautilus_trader.common import LoggerConfig,LogLevel
from nautilus_trader.execution import DefaultFillModel,MakerTakerFeeModel,StaticLatencyModel
from nautilus_trader.model import AccountType,Currency,CurrencyPair,Money,OmsType,OrderSide,Price,Quantity,QuoteTick,TimeInForce
from nautilus_trader.trading import Strategy
from binance_robot.execution import INSTRUMENT,VENUE
from binance_robot.runner import paper_instrument
from .native import CASES,quote_prices
D=Decimal;USDT=Currency.from_str('USDT');BORROW={'BASE':.05,'STRESS':.1,'SEVERE':.3,'DELAY':.1}

class MarginResearch(Strategy):
 def __new__(cls,*a,**k):return super().__new__(cls)
 def __init__(self,frames,fee,lag,annual,risk,last,annual_settlement):
  super().__init__();self.frames=frames;self.fee=D(str(fee));self.lag=lag;self.annual=D(str(annual));self.risk=risk;self.last=last;self.annual_settlement=annual_settlement
  self.fills=[];self.orders=[];self.marks=[];self.trades=[];self.events=[];self.financing=[]
  self.entry=None;self.pending=None;self.allowed=0;self.debt=D(0);self.current=None;self.reason=None;self.failure=None
 def on_start(self):self.subscribe_quotes(INSTRUMENT)
 def raw_cash(self):return self.cache.account_for_venue(VENUE).balance_total(USDT).as_decimal()
 def on_quote(self,q):
  if self.failure:return
  try:self.process(q)
  except Exception as e:self.failure=e
 def process(self,q):
  frame=self.frames[q.ts_event];self.current=frame;i=frame['index'];bid=q.bid_price.as_decimal();ask=q.ask_price.as_decimal()
  if frame['phase']=='fill':return
  if frame['phase']=='decision' and self.entry and self.entry['direction']==-1:
   cost=self.entry['q']*D(str(frame['price']))*self.annual/D(365);self.debt+=cost
   self.financing.append({'date':frame['date'],'quantity':str(self.entry['q']),'reference':str(frame['price']),'annual':str(self.annual),'cost':str(cost),'cumulative':str(self.debt)})
  raw=self.raw_cash();pnl=D(0);exitfee=D(0)
  if self.entry:
   mark=bid if self.entry['direction']==1 else ask;pnl=self.entry['direction']*self.entry['q']*(mark-self.entry['px']);exitfee=self.entry['q']*mark*self.fee
  equity=raw-self.debt+pnl-exitfee
  if equity<=0:raise ValueError('nonpositive financing-adjusted equity')
  if frame['phase']=='mark':
   positions=self.cache.positions_open();expected=D(0) if self.entry is None else self.entry['direction']*self.entry['q'];actual=sum((D(str(p.signed_qty)) for p in positions),D(0))
   if actual!=expected:raise ValueError('native position differs from tracked complete fills')
   self.marks.append({'date':frame['date'],'index':i,'raw_cash':str(raw),'financing_total':str(self.debt),'signed_qty':str(expected),'bid':str(bid),'ask':str(ask),'unrealized_pnl':str(pnl),'exit_fee_reserve':str(exitfee),'equity':str(equity),'reference_price':frame['price']});return
  desired=frame['direction']
  if self.entry:
   own=self.entry['risk']['long' if self.entry['direction']==1 else 'short'];asset_pnl=pnl-self.entry['fee']-exitfee-(self.debt-self.entry['debt_at_entry']);notional=self.entry['q']*self.entry['px']+self.entry['fee']
   self.entry['peak']=max(self.entry['peak'],notional+asset_pnl)
   trailing=own.get('trailing_stop',0.) and self.entry['peak']>=notional*(1+D(str(own.get('trail_arm',0.)))) and notional+asset_pnl<=self.entry['peak']*(1-D(str(own.get('trailing_stop',0.))))
   if self.pending is None:
    reason='STOP_LOSS' if asset_pnl<=-notional*D(str(own['stop_loss'])) else 'TRAIL_STOP' if trailing else 'TAKE_PROFIT' if asset_pnl>=notional*D(str(own['take_profit'])) else None
    if reason:self.pending={'due':i+self.lag,'trigger':i,'reason':reason};self.events.append({'event':'TRIGGER','date':frame['date'],**self.pending})
   due=self.pending is not None and self.pending['due']<=i
   if i!=self.last and not (self.annual_settlement and frame['date'].endswith('-12-31')) and desired==self.entry['direction'] and not due:return
   quantity=self.entry['q'];side=OrderSide.SELL if self.entry['direction']==1 else OrderSide.BUY
   self.reason='TERMINAL' if i==self.last else 'PERIOD_CLOSE' if self.annual_settlement and frame['date'].endswith('-12-31') else self.pending['reason'] if due else 'SIGNAL';action='CLOSE'
  else:
   if not frame['entry_allowed'] or not desired or i<self.allowed or i==self.last or frame['date'].endswith('-12-31') or frame['policy_year']!=int(frame['date'][:4]):return
   price=ask if desired==1 else bid;budget=equity*D(str(frame['long_fraction'] if desired==1 else frame['short_fraction']))
   quantity=((budget-D('.01'))/(price*(1+self.fee))).quantize(D('.00001'),rounding=ROUND_DOWN)
   side=OrderSide.BUY if desired==1 else OrderSide.SELL;self.reason='ENTRY';action='OPEN'
  price=ask if side==OrderSide.BUY else bid
  if quantity<=0 or quantity*price<5:raise ValueError('minimum notional makes registered trade infeasible')
  order=self.order_factory.market(instrument_id=INSTRUMENT,order_side=side,quantity=Quantity.from_str(f'{quantity:.5f}'),time_in_force=TimeInForce.GTC)
  self.orders.append({'date':frame['date'],'index':i,'action':action,'side':'BUY' if side==OrderSide.BUY else 'SELL','quantity':str(quantity),'reason':self.reason,'client_order_id':str(order.client_order_id)})
  self.submit_order(order)
 def on_order_rejected(self,e):self.failure=ValueError('native rejected: '+str(e))
 def on_order_denied(self,e):self.failure=ValueError('native denied: '+str(e))
 def on_order_filled(self,e):
  try:
   q=e.last_qty.as_decimal();px=e.last_px.as_decimal();fee=e.commission.as_decimal();order=self.orders[-1]
   if str(e.client_order_id)!=order['client_order_id'] or D(order['quantity'])!=q or e.commission.currency.code!='USDT':raise ValueError('partial/unregistered native fill or commission')
   row={**order,'price':str(px),'fee':str(fee),'fee_asset':'USDT','ts_event':e.ts_event};self.fills.append(row)
   if self.entry is None:
    self.entry={'date':row['date'],'index':row['index'],'direction':1 if row['side']=='BUY' else -1,'q':q,'px':px,'fee':fee,'debt_at_entry':self.debt,'peak':q*px+fee,'risk':self.current['risk'],'policy_year':self.current['policy_year']}
   else:
    entry=self.entry;gross=entry['direction']*q*(px-entry['px']);borrow=self.debt-entry['debt_at_entry'];pnl=gross-entry['fee']-fee-borrow
    self.trades.append({'entry_date':entry['date'],'exit_date':row['date'],'direction':entry['direction'],'quantity':str(q),'entry_price':str(entry['px']),'exit_price':str(px),'gross_pnl':str(gross),'fees':str(entry['fee']+fee),'financing':str(borrow),'pnl':str(pnl),'terminal':row['reason'] in ('TERMINAL','PERIOD_CLOSE'),'exit_reason':row['reason'],'policy_year':entry['policy_year']})
    if self.pending:
     own=entry['risk']['long' if entry['direction']==1 else 'short'];self.allowed=row['index']+own['cooldown_days']+1;self.events.append({'event':'CLOSED','date':row['date'],'next_allowed_index':self.allowed,**self.pending})
    self.entry=None;self.pending=None
  except Exception as exc:self.failure=exc

def summarize(strategy,case):
 marks=strategy.marks;values=[100]+[float(m['equity']) for m in marks];peak=100;dd=0
 for v in values:peak=max(peak,v);dd=max(dd,1-v/peak)
 annual=[];prior=100
 for year in sorted({m['date'][:4] for m in marks}):
  end=float([m for m in marks if m['date'].startswith(year)][-1]['equity']);annual.append({'year':year,'return_pct':100*(end/prior-1)});prior=end
 naturals=[t for t in strategy.trades if not t['terminal']];positive=sorted([float(t['pnl']) for t in naturals if float(t['pnl'])>0],reverse=True)
 return {'case':case,'return_pct':values[-1]-100,'max_drawdown_pct':dd*100,'natural_trades':len(naturals),'terminal_trades':len(strategy.trades)-len(naturals),'short_trades':sum(t['direction']==-1 for t in naturals),'short_pnl':sum(float(t['pnl']) for t in strategy.trades if t['direction']==-1),'long_pnl':sum(float(t['pnl']) for t in strategy.trades if t['direction']==1),'best_two_positive_contribution_fraction':sum(positive[:2])/sum(positive) if positive else None,'annual':annual,'positive_years':sum(a['return_pct']>0 for a in annual),'financing_usdt':str(strategy.debt),'ending_raw_cash':marks[-1]['raw_cash'],'ending_adjusted_equity':marks[-1]['equity'],'flat':strategy.entry is None,'path_sha256':hashlib.sha256(json.dumps(marks,sort_keys=True).encode()).hexdigest(),'max_gross_exposure_pct':max(abs(float(m['signed_qty']))*m['reference_price']/float(m['equity'])*100 for m in marks),'average_gross_exposure_pct':sum(abs(float(m['signed_qty']))*m['reference_price']/float(m['equity'])*100 for m in marks)/len(marks),'short_days':sum(float(m['signed_qty'])<0 for m in marks),'financing_scope':'modeled separate from native wallet; deducted from all net marks and subsequent entry budgets'}

def run_account(days,prices,targets,case,risk,start='2018-01-01',end='2022-12-31',role='fold_train',entry_permission=None,annual_settlement=True):
 if type(annual_settlement)is not bool:raise ValueError('invalid annual settlement mode')
 if role not in ('fold_train','target_replay') or case not in CASES:raise ValueError('unregistered role/cost')
 if entry_permission is None:entry_permission=[True]*len(days)
 if len(entry_permission)!=len(days)or any(type(v)is not bool for v in entry_permission):raise ValueError('invalid entry permission')
 ceiling='2024-12-31' if role=='fold_train' else '2025-12-31'
 if role=='target_replay' and (start,end)!=('2018-01-01','2025-12-31'):raise ValueError('target cannot be shortened')
 if len(days)!=len(prices) or len(days)!=len(targets) or not '2017-01-01'<=days[0]<=start<=end<=days[-1]<=ceiling:raise ValueError('registered clock boundary')
 if any(date.fromisoformat(b)-date.fromisoformat(a)!=timedelta(days=1) for a,b in zip(days,days[1:])) or any(not math.isfinite(p) or p<=0 for p in prices):raise ValueError('bad price clock')
 if any(set(t)!={'direction','long_fraction','short_fraction','risk','policy_year'} or type(t['direction'])is not int or t['direction']not in(-1,0,1) or not 0<t['long_fraction']<=.95 or not 0<=t['short_fraction']<=.75 for t in targets):raise ValueError('invalid exposure')
 for t in targets:
  if not 2018<=t['policy_year']<=2025:raise ValueError('unregistered policy year')
  for own in t['risk'].values():
   if not 0<own['stop_loss']<1 or not own['take_profit']>0 or own['cooldown_days']<0 or not 0<=own.get('trailing_stop',0)<1 or own.get('trail_arm',0)<0:raise ValueError('invalid risk policy')
 fee,slip,lag=CASES[case];first=days.index(start);last=days.index(end)
 if first<lag:raise ValueError('missing signal prefix')
 quotes=[];frames={}
 for i in range(first,last+1):
  ts=int(datetime.combine(date.fromisoformat(days[i])+timedelta(days=1),time(),timezone.utc).timestamp())*10**9;bid,ask=quote_prices(prices[i],slip)
  for dt,phase in ((0,'decision'),(10_000_000,'fill'),(20_000_000,'mark')):
   t=ts+dt;frames[t]={'index':i,'date':days[i],'price':prices[i],'phase':phase,'entry_allowed':entry_permission[i-lag],**targets[i-lag]};quotes.append(QuoteTick(INSTRUMENT,Price.from_str(f'{bid:.2f}'),Price.from_str(f'{ask:.2f}'),Quantity.from_str('10000.00000'),Quantity.from_str('10000.00000'),t,t))
 engine=BacktestEngine(BacktestEngineConfig(logging=LoggerConfig(stdout_level=LogLevel.ERROR),run_analysis=False));strategy=MarginResearch(frames,fee,lag,BORROW[case],risk,last,annual_settlement)
 def timeout(signum,frame):raise TimeoutError('native account 90second budget')
 old=signal.signal(signal.SIGALRM,timeout);signal.alarm(90)
 try:
  engine.add_venue(venue=VENUE,oms_type=OmsType.NETTING,account_type=AccountType.MARGIN,base_currency=USDT,starting_balances=[Money.from_str('100 USDT')],default_leverage=D(1),allow_cash_borrowing=False,use_random_ids=False,liquidation_enabled=True,liquidity_consumption=True,fill_model=DefaultFillModel(1.,0.,17),fee_model=MakerTakerFeeModel(),latency_model=StaticLatencyModel(insert_latency_nanos=1_000_000))
  meta=CurrencyPair.to_dict(paper_instrument(quotes[0].ts_event));meta.update(maker_fee=str(fee),taker_fee=str(fee),margin_init='1',margin_maint='.5');engine.add_instrument(CurrencyPair.from_dict(meta));engine.add_strategy(strategy);engine.add_data(quotes);engine.run()
  if strategy.failure:raise strategy.failure
  return {'summary':summarize(strategy,case),'marks':strategy.marks,'fills':strategy.fills,'orders':strategy.orders,'trades':strategy.trades,'risk_events':strategy.events,'financing':strategy.financing,'native_account_report':json.loads(engine.generate_account_report(VENUE).to_json(orient='split',date_format='iso'))}
 finally:signal.alarm(0);signal.signal(signal.SIGALRM,old);engine.dispose()
