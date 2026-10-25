"""Calendar mark attribution, entry-regime ownership and 2018 equity rebasing."""
import gzip
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path

NEW=Path('/workspace/BTC-strategy')
SOURCE=Path('/workspace/BTCStrategyResearchLedger')
OUTPUT=Path('/workspace/BTCExpertReview/workspaces/data/r09-checks.json')


def read(path):
    assert not any(part in path.parts for part in ('2026','review','verification','V01-2026-retained-validation','V02-buy-and-hold-validation'))
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def number(value):
    return F(Decimal(str(value)))


def show(value):
    with localcontext() as context:
        context.prec=40
        return str(Decimal(value.numerator)/Decimal(value.denominator))


market=read(NEW/'artifacts/factors/market.json.gz')
days=market['days'];where={day:i for i,day in enumerate(days)}
high=read(NEW/'artifacts/contexts/high_return.json.gz')
budget=read(NEW/'artifacts/contexts/budget.json.gz')
sizing=read(NEW/'artifacts/contexts/sizing.json.gz')
original_scores={'LP35':high[1]['scores'],'C02':sizing[2],'K02':budget[2]['scores']}
cold_flags={name:[a is None or b is None for a,b in zip(scores['BASE_TREE'],scores['CAL44_STOP'],strict=True)] for name,scores in original_scores.items()}
assert cold_flags['LP35']==cold_flags['K02']
assert cold_flags['LP35']==cold_flags['C02']
assert cold_flags['LP35']==[a is None or b is None for a,b in zip(high[0]['scores']['BASE_TREE'],high[0]['scores']['CAL44_STOP'],strict=True)]
catalog={item['id']:item for item in read(NEW/'artifacts/catalog.json')['strategies']}
drawdowns={}
results=[]
for name in ('LP35','C02','K02'):
    drawdowns[name]={}
    for case in ('BASE','STRESS','SEVERE','DELAY'):
        path=NEW/f'artifacts/accounts/{name}/{case}.json.gz'
        source=SOURCE/catalog[name]['source_study']/'accounts'/catalog[name]['recipe']['id']/f'{case}.json.gz'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==hashlib.sha256(source.read_bytes()).hexdigest()
        book=read(path)
        peak=100.;drawdown=0.
        for mark in book['marks']:
            value=float(mark['equity']);peak=max(peak,value);drawdown=max(drawdown,1-value/peak)
        assert 100*drawdown==book['summary']['max_drawdown_pct']
        drawdowns[name][case]=100*drawdown
    account=read(NEW/f'artifacts/accounts/{name}/STRESS.json.gz')
    marks,trades=account['marks'],account['trades']
    assert marks[0]['date']=='2018-01-01' and marks[-1]['date']=='2025-12-31' and account['summary']['flat']
    mark_by_day={mark['date']:mark for mark in marks}
    fills_by_day={fill['date']:fill for fill in account['fills']}
    previous=F(100);daily={}
    for mark in marks:
        current=number(mark['equity']);daily[mark['date']]=current-previous;previous=current
    assert sum(daily.values(),F(0))==number(marks[-1]['equity'])-100
    trade_by_day={}
    trade_regime={}
    allocation=[]
    for index,trade in enumerate(trades):
        entry,exit=where[trade['entry_date']],where[trade['exit_date']]
        regime='cold_entry' if cold_flags[name][entry-1] else 'postcold_entry'
        trade_regime[index]=regime
        by_year=defaultdict(F)
        for i in range(entry,exit+1):
            assert days[i] not in trade_by_day
            trade_by_day[days[i]]=index
            by_year[days[i][:4]]+=daily[days[i]]
        allocated=sum(by_year.values(),F(0))
        error=abs(allocated-number(trade['pnl']))
        assert error<=F(Decimal('1e-8'))
        allocation.append(dict(entry_date=trade['entry_date'],exit_date=trade['exit_date'],direction=trade['direction'],
                               entry_signal_date=days[entry-1],entry_signal_availability_regime=regime,
                               full_trade_net_pnl=trade['pnl'],calendar_mark_pnl={year:show(value) for year,value in sorted(by_year.items())},
                               marked_allocation_error=show(error)))
    assert all(change==0 for day,change in daily.items() if day not in trade_by_day)
    annual=[];previous_end=F(100);previous_accrual=F(0)
    for year in range(2018,2026):
        label=str(year);last=mark_by_day[f'{year}-12-31'];end=number(last['equity'])
        delta=sum((value for day,value in daily.items() if day.startswith(label)),F(0))
        assert delta==end-previous_end
        reported=next(row['return_pct'] for row in account['summary']['annual'] if row['year']==label)
        assert reported==100*(float(end)/float(previous_end)-1)
        realized=sum((number(trade['pnl']) for trade in trades if trade['exit_date'].startswith(label)),F(0))
        entry_cohort=sum((number(trade['pnl']) for trade in trades if trade['entry_date'].startswith(label)),F(0))
        held=[trade for trade in trades if trade['entry_date']<=last['date']<trade['exit_date']]
        assert len(held)<=1
        accrual=F(0)
        if held:
            trade=held[0];entry_fill=fills_by_day[trade['entry_date']]
            debt_since_entry=number(last['financing_total'])-number(mark_by_day[trade['entry_date']]['financing_total'])
            accrual=number(last['unrealized_pnl'])-number(entry_fill['fee'])-number(last['exit_fee_reserve'])-debt_since_entry
        reconciliation=delta-(realized+accrual-previous_accrual)
        assert abs(reconciliation)<=F(Decimal('1e-8'))
        annual.append(dict(year=label,start_equity=show(previous_end),end_equity=last['equity'],
                           calendar_mark_return_pct=reported,calendar_mark_pnl=show(delta),
                           exit_year_realized_pnl=show(realized),entry_year_full_trade_pnl=show(entry_cohort),
                           ending_open_trade_accrual=show(accrual),prior_open_trade_accrual=show(previous_accrual),
                           boundary_reconciliation_error=show(reconciliation)))
        previous_end,previous_accrual=end,accrual
    entry_cohort_daily=defaultdict(F);day_signal_regime_daily=defaultdict(F);changed_regime_days=[]
    for day,change in daily.items():
        regime='cold_signal_day' if cold_flags[name][where[day]-1] else 'postcold_signal_day'
        day_signal_regime_daily[regime]+=change
        if day in trade_by_day:
            owner=trade_regime[trade_by_day[day]]
            entry_cohort_daily[owner]+=change
            if (owner=='cold_entry')!=(regime=='cold_signal_day'):
                changed_regime_days.append(dict(date=day,position_entry_regime=owner,current_signal_regime=regime,marked_pnl=show(change)))
    positive=sorted((trade for trade in trades if not trade['terminal'] and number(trade['pnl'])>0),key=lambda trade:number(trade['pnl']),reverse=True)
    positive_total=sum((number(trade['pnl']) for trade in positive),F(0))
    top_two=sum((number(trade['pnl']) for trade in positive[:2]),F(0))
    fraction=top_two/positive_total
    assert abs(float(fraction)-account['summary']['best_two_positive_contribution_fraction'])<=1e-8
    equity_2018=number(mark_by_day['2018-12-31']['equity']);terminal=number(marks[-1]['equity'])
    multiplier=equity_2018/100;later_factor=terminal/equity_2018
    assert multiplier*later_factor==terminal/100
    results.append(dict(strategy=name,case='STRESS',annual=annual,
                        cross_year_trades=[item for item in allocation if item['entry_date'][:4]!=item['exit_date'][:4]],
                        entry_signal_regime_counts={regime:sum(value==regime for value in trade_regime.values()) for regime in ('cold_entry','postcold_entry')},
                        entry_regime_calendar_mark_pnl={key:show(value) for key,value in entry_cohort_daily.items()},
                        day_signal_regime_calendar_mark_pnl={key:show(value) for key,value in day_signal_regime_daily.items()},
                        old_position_new_signal_regime_days=changed_regime_days,
                        concentration=dict(definition='Top two profitable non-terminal trades / sum of all profitable non-terminal trade net PnL',
                                           positive_trade_count=len(positive),positive_pnl_denominator=show(positive_total),top_two_positive_pnl=show(top_two),
                                           top_two_share=float(fraction),top_two_dates=[dict(entry_date=trade['entry_date'],exit_date=trade['exit_date'],pnl=trade['pnl']) for trade in positive[:2]]),
                        capital_2018=dict(ending_equity_2018=show(equity_2018),initial_capital_multiplier=show(multiplier),
                                          full_path_growth_factor=show(terminal/100),later_path_rebased_growth_factor=show(later_factor),
                                          later_path_rebased_return_pct=show(100*(later_factor-1)),
                                          qualification='Algebraic rebasing of the same existing equity path, not a rerun deleting 2018 trades or resetting lot-sized strategy capital.')))

assert max(drawdowns['C02'].values())<max(drawdowns['LP35'].values())
result=dict(status='PASS',strategies=['LP35','C02'],auxiliary_regime_example='K02',primary_case='STRESS',results=results,
            observed_four_cost_max_drawdown_pct=drawdowns,
            cold_definition='Original H03 core availability: .5*(BASE_TREE+CAL44_STOP) exists only when both heads exist, evaluated at actual entry signal index i-lag; not auxiliary missingness or entry-year as a definition.',
            annual_definition='Year-end marked financing-adjusted equity / preceding year-end marked equity - 1; 2018 starts at capital 100.',
            limitations=['Trade-cohort entry-year and exit-year PnL are alternative ownership views, not calendar mark returns.',
                         'Trade mark allocations telescope from original equity marks; no strategy or source-data changes were run.',
                         '2018 capital decomposition is algebraic path rebasing, not a causal counterfactual or independent sample.',
                         'No writer, refit, account replay, 2026 economic data or expert/chair review artifact was read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps(dict(status=result['status'],strategies=result['strategies'],primary_case=result['primary_case'],
                      observed_four_cost_max_drawdown_pct=drawdowns,
                      summaries=[dict(strategy=row['strategy'],cross_year_trades=len(row['cross_year_trades']),
                                      concentration=row['concentration'],capital_2018=row['capital_2018'],
                                      old_position_new_signal_regime_days=row['old_position_new_signal_regime_days']) for row in results]),ensure_ascii=False,indent=2))
