"""Research-only daily quote adapter to the project's pinned native CASH engine."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import hashlib
import json
import math
import signal

from nautilus_trader.backtest import BacktestEngine, BacktestEngineConfig
from nautilus_trader.common import LoggerConfig, LogLevel
from nautilus_trader.execution import DefaultFillModel, MakerTakerFeeModel, StaticLatencyModel
from nautilus_trader.model import AccountType, Currency, CurrencyPair, Money, OmsType, OrderSide, Price, Quantity, QuoteTick, TimeInForce
from nautilus_trader.trading import Strategy
from btc_strategy.instrument import INSTRUMENT, VENUE
from btc_strategy.instrument import paper_instrument

CASES={'BASE':(.001,.0005,1),'STRESS':(.003,.001,1),'SEVERE':(.005,.002,1),'DELAY':(.003,.001,2)}
USDT=Currency.from_str('USDT');BTC=Currency.from_str('BTC')
RISK={'stop_loss':.15,'take_profit':1.,'cooldown_days':3}


def quote_prices(price, slip):
    price=Decimal(str(price));s=Decimal(str(slip));tick=Decimal('.01')
    return ((price*(1-s)).quantize(tick,rounding=ROUND_DOWN),(price*(1+s)).quantize(tick,rounding=ROUND_UP))


class ResearchStrategy(Strategy):
    def __new__(cls,*args,**kwargs):return super().__new__(cls)
    def __init__(self,frames,fee,lag,risk,last):
        super().__init__()
        self.frames,self.fee,self.lag,self.risk,self.last=frames,Decimal(str(fee)),lag,risk,last
        self.fills=[];self.marks=[];self.trades=[];self.risk_events=[];self.orders=[]
        self.pending=None;self.allowed=0;self.entry=None;self.episode_risk=None
        self.current=None;self.reason=None;self.failure=None;self.skips=[]
    def on_start(self):self.subscribe_quotes(INSTRUMENT)
    def balances(self):
        account=self.cache.account_for_venue(VENUE)
        return account.balance_total(USDT).as_decimal(),account.balance_total(BTC).as_decimal()
    def on_quote(self,quote):
        if self.failure is not None:return
        try:self.process(quote)
        except Exception as exc:self.failure=exc
    def process(self,quote):
        frame=self.frames.get(quote.ts_event)
        if frame is None:return
        self.current=frame
        if frame['phase']=='fill':return
        cash,qty=self.balances();bid=quote.bid_price.as_decimal();ask=quote.ask_price.as_decimal()
        i=frame['index']
        if frame['phase']=='mark':
            net=cash+qty*bid*(1-self.fee)
            self.marks.append({'date':frame['date'],'index':i,'cash':str(cash),'btc':str(qty),'bid':str(bid),'ask':str(ask),'equity':str(net),'reference_price':frame['price']})
            if cash<0 or qty<0:raise ValueError('native CASH balance negative')
            return
        desired=frame['long']
        risk=self.episode_risk
        if qty>0 and risk and self.pending is None:
            net=qty*bid*(1-self.fee);spent=self.entry['cost']
            reason='STOP_LOSS' if net <= spent*(1-Decimal(str(risk['stop_loss']))) else 'TAKE_PROFIT' if net>=spent*(1+Decimal(str(risk['take_profit']))) else None
            if reason:
                self.pending={'due':i+self.lag,'reason':reason,'trigger':i}
                self.risk_events.append({'event':'TRIGGER','date':frame['date'],**self.pending})
        due=self.pending is not None and self.pending['due']<=i
        closing=qty>0 and (i==self.last or not desired or due)
        if closing:
            self.reason='TERMINAL' if i==self.last else self.pending['reason'] if due else 'SIGNAL'
            q=qty.quantize(Decimal('.00001'),rounding=ROUND_DOWN)
            if q*bid<5:
                self.skips.append({'date':frame['date'],'reason':'SELL_MIN5','btc':str(q)});return
            side=OrderSide.SELL
        elif qty==0 and desired and i>=self.allowed and i!=self.last:
            self.reason='ENTRY';side=OrderSide.BUY
            budget=cash*Decimal(str(frame['fraction']))
            # One quote-currency cent reserve absorbs native fee rounding.
            q=((budget-Decimal('.01'))/(ask*(1+self.fee))).quantize(Decimal('.00001'),rounding=ROUND_DOWN)
            if q<=0 or q*ask<5:
                self.skips.append({'date':frame['date'],'reason':'BUY_MIN5','cash':str(cash)});return
        else:return
        order=self.order_factory.market(instrument_id=INSTRUMENT,order_side=side,quantity=Quantity.from_str(f'{q:.5f}'),time_in_force=TimeInForce.GTC)
        self.orders.append({'date':frame['date'],'index':i,'side':'BUY' if side==OrderSide.BUY else 'SELL','quantity':str(q),'reason':self.reason,'client_order_id':str(order.client_order_id)})
        self.submit_order(order)
    def on_order_rejected(self,event):self.failure=ValueError('native order rejected: '+str(event))
    def on_order_denied(self,event):self.failure=ValueError('native order denied: '+str(event))
    def on_order_filled(self,event):
        try:
            qty=event.last_qty.as_decimal();price=event.last_px.as_decimal();commission=event.commission.as_decimal();asset=event.commission.currency.code
            if asset!='USDT':raise ValueError('registered native fee model must debit USDT')
            side='BUY' if event.order_side==OrderSide.BUY else 'SELL'
            row={'date':self.current['date'],'index':self.current['index'],'ts_event':event.ts_event,'side':side,'quantity':str(qty),'price':str(price),'fee':str(commission),'fee_asset':asset,'reason':self.reason,'client_order_id':str(event.client_order_id)}
            if not self.orders or self.orders[-1]['client_order_id'] != row['client_order_id'] or Decimal(self.orders[-1]['quantity']) != qty:
                raise ValueError('research adapter requires one complete fill per order')
            self.fills.append(row)
            if side=='BUY':
                self.entry={'date':row['date'],'index':row['index'],'cost':qty*price+commission,'quantity':qty,'price':price}
                self.episode_risk=dict(self.risk) if self.risk else None
            else:
                proceeds=qty*price-commission
                self.trades.append({'entry_date':self.entry['date'],'exit_date':row['date'],'entry_cost':str(self.entry['cost']),'proceeds':str(proceeds),'pnl':str(proceeds-self.entry['cost']),'terminal':self.reason=='TERMINAL','exit_reason':self.reason})
                if self.pending:
                    self.allowed=row['index']+self.episode_risk['cooldown_days']+1
                    self.risk_events.append({'event':'CLOSED','date':row['date'],'next_allowed_index':self.allowed,**self.pending})
                self.entry=None;self.episode_risk=None;self.pending=None
        except Exception as exc:self.failure=exc


def summarize(strategy,case):
    marks=strategy.marks
    if not marks:raise ValueError('native engine produced no account marks')
    equity=[100.]+[float(m['equity']) for m in marks]
    peak=100.;dd=0.
    for value in equity:peak=max(peak,value);dd=max(dd,1-value/peak)
    annual=[];prior=100.
    for year in sorted({m['date'][:4] for m in marks}):
        rows=[m for m in marks if m['date'].startswith(year)]
        last=float(rows[-1]['equity']);annual.append({'year':year,'return_pct':(last/prior-1)*100});prior=last
    naturals=[t for t in strategy.trades if not t['terminal']]
    positive=sorted([float(t['pnl']) for t in naturals if float(t['pnl'])>0],reverse=True)
    concentration=sum(positive[:2])/sum(positive) if positive else None
    years=len(marks)/365.25;cagr=((equity[-1]/100)**(1/years)-1)*100
    path=hashlib.sha256(json.dumps([{k:v for k,v in m.items() if k not in ('ask','bid')} for m in marks],sort_keys=True).encode()).hexdigest()
    return {'case':case,'initial_cash':100,'start':marks[0]['date'],'end':marks[-1]['date'],'return_pct':equity[-1]-100,'max_drawdown_pct':dd*100,'cagr_pct':cagr,'calmar':cagr/(dd*100) if dd>0 else None,'natural_trades':len(naturals),'terminal_trades':len(strategy.trades)-len(naturals),'best_two_positive_contribution_fraction':concentration,'positive_years':sum(a['return_pct']>0 for a in annual),'annual':annual,'ending_cash':marks[-1]['cash'],'ending_btc':marks[-1]['btc'],'flat':Decimal(marks[-1]['btc'])==0,'fee_usdt':sum(float(f['fee']) for f in strategy.fills),'turnover_usdt':sum(float(f['quantity'])*float(f['price']) for f in strategy.fills),'average_daily_exposure_pct':100*sum(float(m['btc'])*m['reference_price']/float(m['equity']) for m in marks)/len(marks),'risk_triggers':sum(r['event']=='TRIGGER' for r in strategy.risk_events),'path_sha256':path,'skip_count':len(strategy.skips)}

