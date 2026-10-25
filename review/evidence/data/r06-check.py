"""Benchmark data joins and two-cost LP35 accounting check; never executes an account writer."""
import gzip
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal as D, ROUND_FLOOR, ROUND_CEILING
from pathlib import Path

ROOT = Path('/workspace/BTC-strategy')
SOURCE = Path('/workspace/BTCStrategyResearchLedger')
OUTPUT = Path('/workspace/BTCExpertReview/workspaces/data/r06-checks.json')
CASES = dict(BASE=('.001','.0005',1,'.05'), STRESS=('.003','.001',1,'.1'),
             SEVERE=('.005','.002',1,'.3'), DELAY=('.003','.001',2,'.1'))


def read(path):
    assert not any(item in path.parts for item in ('2026','review','verification','V01-2026-retained-validation','V02-buy-and-hold-validation'))
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


market = read(ROOT/'artifacts/factors/market.json.gz')
days,prices = market['days'],market['prices']
where = {day:i for i,day in enumerate(days)}
expected_days = [(date(2018,1,1)+timedelta(days=i)).isoformat() for i in range(2922)]
assert days[0]=='2017-01-01' and days[-1]=='2025-12-31'
catalog = read(ROOT/'artifacts/catalog.json')['strategies']
assert len(catalog)==9
basic = []
deep = []
for strategy in catalog:
    identifier = strategy['id']
    target_packet = read(ROOT/f'artifacts/targets/{identifier}.json.gz')
    targets,permissions = target_packet['targets'],target_packet['entry_permission']
    assert len(targets)==len(permissions)==len(days)
    assert all(type(value) is bool for value in permissions)
    for case,(fee_text,slip_text,lag,annual_text) in CASES.items():
        fee,slip,annual = D(fee_text),D(slip_text),D(annual_text)
        path = ROOT/f'artifacts/accounts/{identifier}/{case}.json.gz'
        account = read(path)
        source_path = SOURCE/strategy['source_study']/'accounts'/strategy['recipe']['id']/f'{case}.json.gz'
        assert sha(path)==sha(source_path)
        marks,fills,orders,finance = [account[key] for key in ('marks','fills','orders','financing')]
        assert [mark['date'] for mark in marks]==expected_days
        assert len(fills)==len(orders)==len({row['date'] for row in fills})==len({row['client_order_id'] for row in fills})
        assert [row['index'] for row in fills]==sorted(row['index'] for row in fills)
        assert len(finance)==len({row['date'] for row in finance})
        for mark in marks:
            i=where[mark['date']]
            p=D(str(prices[i]))
            bid=(p*(1-slip)).quantize(D('.01'),rounding=ROUND_FLOOR)
            ask=(p*(1+slip)).quantize(D('.01'),rounding=ROUND_CEILING)
            assert mark['index']==i and mark['reference_price']==prices[i]
            assert D(mark['bid'])==bid and D(mark['ask'])==ask
        for fill,order in zip(fills,orders,strict=True):
            assert all(fill[key]==value for key,value in order.items())
            i=where[fill['date']]
            assert fill['index']==i
            p=D(str(prices[i]))
            expected_price=(p*(1+slip)).quantize(D('.01'),rounding=ROUND_CEILING) if fill['side']=='BUY' else (p*(1-slip)).quantize(D('.01'),rounding=ROUND_FLOOR)
            assert D(fill['price'])==expected_price and fill['fee_asset']=='USDT'
            assert abs(D(fill['fee'])-D(fill['quantity'])*expected_price*fee)<=D('.0000000101')
            expected_stamp=int(datetime.combine(date.fromisoformat(fill['date'])+timedelta(days=1),time(),timezone.utc).timestamp())*10**9+10_000_000
            assert fill['ts_event']==expected_stamp
            if fill['action']=='OPEN':
                signal=targets[i-lag]
                assert permissions[i-lag]
                assert signal['direction']==(1 if fill['side']=='BUY' else -1)
                assert signal['policy_year']==int(fill['date'][:4])
                assert not fill['date'].endswith('-12-31') and fill['date']!='2025-12-31'
        expected_finance=[]
        for trade in account['trades']:
            if trade['direction']!=-1:
                assert D(trade['financing'])==0
                continue
            entry,exit=where[trade['entry_date']],where[trade['exit_date']]
            for i in range(entry+1,exit+1):
                expected_finance.append((days[i],trade['quantity']))
        expected_finance.sort()
        assert [(row['date'],row['quantity']) for row in finance]==expected_finance
        debt=D(0)
        for row in finance:
            assert set(row)=={'date','quantity','reference','annual','cost','cumulative'}
            p=D(str(prices[where[row['date']]]))
            amount=D(row['quantity'])*p*annual/D(365)
            debt+=amount
            assert D(row['reference'])==p and D(row['annual'])==annual
            assert D(row['cost'])==amount and D(row['cumulative'])==debt
        assert D(account['summary']['financing_usdt'])==debt
        native=account['native_account_report']
        assert len(native['data'])==len(native['index'])==len(fills)+1
        assert native['index']==sorted(set(native['index']))
        assert all(len(row)==len(native['columns']) for row in native['data'])
        native_time=[datetime.fromisoformat(value.replace('Z','+00:00')) for value in native['index'][1:]]
        assert [int(value.timestamp()*1000) for value in native_time]==[fill['ts_event']//1_000_000 for fill in fills]
        basic.append(dict(strategy=identifier,case=case,source_account_bytes_exact=True,marks=len(marks),
                          fills=len(fills),orders=len(orders),financing_rows=len(finance),
                          dates_quotes_fill_clocks_exact=True,i_minus_lag_open_signals_exact=True,
                          missing_or_duplicate_financing_rows=0))
        if identifier!='LP35' or case not in ('BASE','DELAY'):
            continue
        byday={fill['date']:fill for fill in fills}
        finance_byday={row['date']:row for row in finance}
        cash,debt=D(100),D(0)
        position=None
        trade_index=0
        fill_index=0
        aligned_signals=[]
        max_equity_error=D(0)
        max_raw_cash_error=D(0)
        for mark in marks:
            i=where[mark['date']]
            p=D(str(prices[i]));bid=D(mark['bid']);ask=D(mark['ask'])
            if position and position['direction']==-1:
                amount=position['q']*p*annual/D(365)
                debt+=amount
                row=finance_byday[mark['date']]
                assert D(row['cost'])==amount and D(row['cumulative'])==debt
            else:
                assert mark['date'] not in finance_byday
            fill=byday.get(mark['date'])
            signal=targets[i-lag]
            if fill:
                q,execution_price,charged=D(fill['quantity']),D(fill['price']),D(fill['fee'])
                if fill['action']=='OPEN':
                    assert position is None
                    fraction=D(str(signal['long_fraction'] if signal['direction']==1 else signal['short_fraction']))
                    expected_q=(((cash-debt)*fraction-D('.01'))/(execution_price*(1+fee))).quantize(D('.00001'),rounding=ROUND_FLOOR)
                    assert q==expected_q
                    cash-=charged
                    position=dict(q=q,price=execution_price,direction=signal['direction'],fee=charged,
                                  entry_date=mark['date'],entry_debt=debt,policy_year=signal['policy_year'])
                    aligned_signals.append(dict(account_date=mark['date'],signal_date=days[i-lag],policy_year=signal['policy_year']))
                else:
                    assert position and q==position['q']
                    assert fill['side']==('SELL' if position['direction']==1 else 'BUY')
                    if fill['reason']=='SIGNAL':
                        assert signal['direction']!=position['direction']
                    gross=position['direction']*q*(execution_price-position['price'])
                    cash+=gross-charged
                    borrow=debt-position['entry_debt']
                    trade=account['trades'][trade_index]
                    assert trade['entry_date']==position['entry_date'] and trade['exit_date']==mark['date']
                    assert trade['direction']==position['direction'] and trade['policy_year']==position['policy_year']
                    for key,value in dict(quantity=q,entry_price=position['price'],exit_price=execution_price,
                                          gross_pnl=gross,fees=position['fee']+charged,financing=borrow,
                                          pnl=gross-position['fee']-charged-borrow).items():
                        assert D(trade[key])==value,(case,mark['date'],key)
                    trade_index+=1
                    position=None
                native_cash=D(native['data'][fill_index+1][native['columns'].index('total')])
                assert native_cash==cash
                fill_index+=1
            unrealized,reserve,signed=D(0),D(0),D(0)
            if position:
                quote=bid if position['direction']==1 else ask
                signed=position['direction']*position['q']
                unrealized=signed*(quote-position['price'])
                reserve=position['q']*quote*fee
            equity=cash-debt+unrealized-reserve
            max_equity_error=max(max_equity_error,abs(D(mark['equity'])-equity))
            max_raw_cash_error=max(max_raw_cash_error,abs(D(mark['raw_cash'])-cash))
            assert D(mark['raw_cash'])==cash and D(mark['financing_total'])==debt
            assert D(mark['signed_qty'])==signed and D(mark['unrealized_pnl'])==unrealized
            assert D(mark['exit_fee_reserve'])==reserve and D(mark['equity'])==equity
        assert position is None and trade_index==len(account['trades'])
        assert D(account['summary']['ending_adjusted_equity'])==cash-debt
        deep.append(dict(strategy=identifier,case=case,lag=lag,marks=len(marks),fills=len(fills),trades=trade_index,
                         financing_rows=len(finance),financing_total=str(debt),
                         exact_daily_equity=True,max_decimal_equity_error=str(max_equity_error),
                         max_decimal_raw_wallet_error=str(max_raw_cash_error),
                         first_open_signal=aligned_signals[0],last_open_signal=aligned_signals[-1],
                         terminal_flat=True,native_wallet_fill_reports_exact=True))

result=dict(status='PASS',benchmark_accounts=len(basic),basic=basic,deep=deep,
            scope='36 benchmark data joins; LP35 BASE and DELAY independently reconstructed from existing fills/marks only',
            total_daily_mark_rows=sum(row['marks'] for row in basic),
            missing_or_duplicate_financing_rows=0,
            limitations=['No native execution engine or frozen account writer was run.',
                         'The deep check reconstructs supplied fills and entry sizes; it does not independently reevaluate every stop/trailing trigger threshold.',
                         'Dates are original daily price labels; fill timestamps are label+1 day UTC plus 10ms.',
                         'No 2026 economic observations, expert opinions, review artifacts, or verification conclusions were read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({key:value for key,value in result.items() if key!='basic'},ensure_ascii=False,indent=2))
