"""Independent Decimal reconstruction of native fills, balances and daily risk."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
import math

D=Decimal


def check(condition, message):
    if not condition:raise ValueError(message)


def close(actual, expected, message, tolerance=1e-8):
    check(math.isfinite(float(actual)) and abs(float(actual)-float(expected))<=tolerance,message)


def audit_account(account, days, prices, targets, costs, risk):
    fee,slip,lag=costs;fee=D(str(fee));slip=D(str(slip))
    cash=D(100);btc=D(0);peak=D(100);drawdown=D(0);fees=D(0);turnover=D(0)
    fills=account['fills'];orders=account['orders'];marks=account['marks']
    check(len(fills)==len(orders),'unfilled or duplicate native order')
    check(not account['skips'],'minimum-size constraint prevented registered execution')
    byday={f['date']:f for f in fills}
    check(len(byday)==len(fills),'more than one fill per day')
    check(len(marks)==(date.fromisoformat(marks[-1]['date'])-date.fromisoformat(marks[0]['date'])).days+1,'missing daily mark')
    expected_trades=[];expected_events=[];pending=None;allowed=0;entry=None;positive=[]
    for mark in marks:
        i=days.index(mark['date']);check(mark['index']==i,'index/date mismatch')
        p=D(str(prices[i]));bid=(p*(1-slip)).quantize(D('.01'),rounding=ROUND_FLOOR);ask=(p*(1+slip)).quantize(D('.01'),rounding=ROUND_CEILING)
        check(D(mark['bid'])==bid and D(mark['ask'])==ask,'quote spread/rounding changed')
        desired=targets[i-lag]['long'];last=mark is marks[-1];fill=byday.get(mark['date'])
        if btc and risk and pending is None:
            liquid=btc*bid*(1-fee)
            reason='STOP_LOSS' if liquid <= entry['cost']*(1-D(str(risk['stop_loss']))) else 'TAKE_PROFIT' if liquid>=entry['cost']*(1+D(str(risk['take_profit']))) else None
            if reason:
                pending={'due':i+lag,'reason':reason,'trigger':i}
                expected_events.append({'event':'TRIGGER','date':mark['date'],**pending})
        due=pending is not None and pending['due']<=i
        sell=bool(btc and (last or not desired or due))
        buy=bool(not btc and desired and i>=allowed and not last)
        check(bool(fill)==(sell or buy),'native execution differs from lagged signal / risk / cooldown')
        if fill:
            order=orders[fills.index(fill)]
            check(order['client_order_id']==fill['client_order_id'] and order['quantity']==fill['quantity'] and order['side']==fill['side'] and order['reason']==fill['reason'],'order/fill mismatch')
            at=datetime.combine(date.fromisoformat(mark['date'])+timedelta(days=1),time(),timezone.utc)
            check(fill['ts_event']==int(at.timestamp())*10**9+10_000_000,'fill before registered execution quote')
            q=D(fill['quantity']);px=D(fill['price']);charged=D(fill['fee'])
            check(fill['fee_asset']=='USDT' and q>0 and q%D('.00001')==0,'fee or size precision changed')
            close(charged,q*px*fee,'wrong native commission',1.01e-8)
            check(q*px>=5,'native minimum notional violated')
            fees+=charged;turnover+=q*px
            if buy:
                expected=((cash*D(str(targets[i-lag]['fraction']))-D('.01'))/(ask*(1+fee))).quantize(D('.00001'),rounding=ROUND_FLOOR)
                check(fill['side']=='BUY' and fill['reason']=='ENTRY' and px==ask and q==expected,'buy signal / size / quote mismatch')
                cost=q*px+charged;cash-=cost;btc+=q;entry={'date':mark['date'],'cost':cost}
            else:
                reason='TERMINAL' if last else pending['reason'] if due else 'SIGNAL'
                check(fill['side']=='SELL' and fill['reason']==reason and px==bid and q==btc,'sell signal / size / quote mismatch')
                proceeds=q*px-charged;cash+=proceeds;btc-=q;pnl=proceeds-entry['cost']
                expected_trades.append({'entry_date':entry['date'],'exit_date':mark['date'],'entry_cost':str(entry['cost']),'proceeds':str(proceeds),'pnl':str(pnl),'terminal':last,'exit_reason':reason})
                if not last and pnl>0:positive.append(pnl)
                if pending:
                    allowed=i+risk['cooldown_days']+1
                    expected_events.append({'event':'CLOSED','date':mark['date'],'next_allowed_index':allowed,**pending})
                pending=None;entry=None
        check(cash>=0 and btc>=0,'negative reconstructed spot balance')
        close(mark['cash'],cash,'native cash conservation failed');close(mark['btc'],btc,'native BTC conservation failed',1e-12)
        equity=cash+btc*bid*(1-fee)
        close(mark['equity'],equity,'daily net liquidation mismatch')
        peak=max(peak,equity);drawdown=max(drawdown,1-equity/peak)
    check(btc==0,'terminal inventory not flat')
    check(expected_events==account['risk_events'],'risk trigger clock changed')
    check(expected_trades==account['trades'],'episode attribution changed')
    s=account['summary'];close(s['return_pct'],cash-100,'return mismatch');close(s['max_drawdown_pct'],drawdown*100,'drawdown mismatch')
    close(s['fee_usdt'],fees,'fee sum mismatch');close(s['turnover_usdt'],turnover,'turnover mismatch',1e-6)
    naturals=[t for t in expected_trades if not t['terminal']]
    check(s['natural_trades']==len(naturals) and s['terminal_trades']==len(expected_trades)-len(naturals),'trade count mismatch')
    if positive:close(s['best_two_positive_contribution_fraction'],sum(sorted(positive,reverse=True)[:2])/sum(positive),'concentration mismatch')
    else:check(s['best_two_positive_contribution_fraction'] is None,'undefined concentration')
    prior=D(100);positive_years=0
    for year in s['annual']:
        value=D([m for m in marks if m['date'].startswith(year['year'])][-1]['equity'])
        close(year['return_pct'],100*(value/prior-1),'annual compounding mismatch');positive_years+=value>prior;prior=value
    check(s['positive_years']==positive_years,'positive-year count mismatch')
    check(s['flat'] and D(s['ending_cash'])==cash and D(s['ending_btc'])==0,'ending summary mismatch')
    return {'status':'PASS','marks':len(marks),'fills':len(fills),'trades':len(expected_trades),'risk_events':len(expected_events),'ending_cash':str(cash)}
