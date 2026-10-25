"""Full-budget CASH baseline through the original project Native spot strategy."""
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal as D
import json,math,signal
from . import cash_native as n


def run_account(days,prices,targets,case,risk,start,end,role='validation',entry_permission=None,annual_settlement=False):
    windows=(('2026-01-01','2026-06-29'),('2026-06-30','2026-10-23'),('2026-01-01','2026-10-23'))
    if role!='validation'or case not in n.CASES:raise ValueError('unregistered role/cost')
    if (start,end)not in windows:raise ValueError('unregistered validation interval or incomplete daily close')
    if risk or annual_settlement:raise ValueError('buy-and-hold risk exits must stay disabled')
    if len(days)!=len(prices)or len(days)!=len(targets)or not '2017-01-01'<=days[0]<=start<end==days[-1]<='2026-10-23':raise ValueError('registered clock boundary')
    if any(date.fromisoformat(b)-date.fromisoformat(a)!=timedelta(days=1)for a,b in zip(days,days[1:]))or any(not math.isfinite(p)or p<=0 for p in prices):raise ValueError('invalid daily prices')
    intent=(date.fromisoformat(start)-timedelta(days=n.CASES[case][2])).isoformat();disabled=dict(stop_loss=None,take_profit=None,cooldown_days=0,trailing_stop=None,trail_arm=None)
    if entry_permission!=[d==intent for d in days]:raise ValueError('unregistered buy intent')
    for d,t in zip(days,targets,strict=True):
        if t['long_fraction']!=1. or t['short_fraction']!=0. or t['direction']!=int(d>=intent):raise ValueError('invalid exposure')
        if t['risk']!=dict(long=disabled,short=disabled):raise ValueError('buy-and-hold risk exits must stay disabled')
    fee,slip,lag=n.CASES[case];first=days.index(start);last=days.index(end);frames={};quotes=[]
    for i in range(first,last+1):
        ts=int(datetime.combine(date.fromisoformat(days[i])+timedelta(days=1),time(),timezone.utc).timestamp())*10**9
        bid,ask=n.quote_prices(prices[i],slip)
        for delta,phase in ((0,'decision'),(10_000_000,'fill'),(20_000_000,'mark')):
            stamp=ts+delta;frames[stamp]=dict(index=i,date=days[i],phase=phase,price=prices[i],long=bool(targets[i-lag]['direction']),fraction=1.)
            quotes.append(n.QuoteTick(n.INSTRUMENT,n.Price.from_str(f'{bid:.2f}'),n.Price.from_str(f'{ask:.2f}'),n.Quantity.from_str('10000.00000'),n.Quantity.from_str('10000.00000'),stamp,stamp))
    engine=n.BacktestEngine(n.BacktestEngineConfig(logging=n.LoggerConfig(stdout_level=n.LogLevel.ERROR),run_analysis=False))
    strategy=n.ResearchStrategy(frames,fee,lag,{},last)
    def timeout(signum,frame):raise TimeoutError('buy-and-hold90secondNativebudget')
    prior=signal.signal(signal.SIGALRM,timeout);signal.alarm(90)
    try:
        engine.add_venue(venue=n.VENUE,oms_type=n.OmsType.NETTING,account_type=n.AccountType.CASH,
            starting_balances=[n.Money.from_str('100 USDT'),n.Money.from_str('0 BTC')],allow_cash_borrowing=False,
            use_random_ids=False,liquidity_consumption=True,fill_model=n.DefaultFillModel(1.,0.,17),fee_model=n.MakerTakerFeeModel(),
            latency_model=n.StaticLatencyModel(insert_latency_nanos=1_000_000,cancel_latency_nanos=1_000_000))
        metadata=n.CurrencyPair.to_dict(n.paper_instrument(quotes[0].ts_event));metadata.update(maker_fee=str(fee),taker_fee=str(fee))
        engine.add_instrument(n.CurrencyPair.from_dict(metadata));engine.add_strategy(strategy);engine.add_data(quotes);engine.run()
        if strategy.failure:raise strategy.failure
        summary=n.summarize(strategy,case);summary['max_gross_exposure_pct']=max(float(m['btc'])*m['reference_price']/float(m['equity'])*100 for m in strategy.marks)
        return dict(summary=summary,marks=strategy.marks,fills=strategy.fills,orders=strategy.orders,trades=strategy.trades,
            risk_events=strategy.risk_events,financing=[],skips=strategy.skips,account_type='CASH',
            native_account_report=json.loads(engine.generate_account_report(n.VENUE).to_json(orient='split',date_format='iso')))
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,prior);engine.dispose()
