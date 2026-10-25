"""Common-sample short supervision at fixed one/two-day execution clocks."""
from decimal import Decimal as D,ROUND_FLOOR
import numpy as np
from .short_payoff import quote,commission,path_label as lag1,RISK,validate_calendar,target_vector
from .boosted_stop import fit as boosted_fit

HEADS=[dict(id='L1',lag=1),dict(id='L2',lag=2)]
LOSS=dict(id='HUBER',loss='huber',alpha=.9)


def label(days,prices,index,lag):
    if lag not in (1,2):raise ValueError('unregistered execution lag')
    if lag==1:return lag1(days,prices,index)
    if type(index)is not int or index<0 or len(days)!=len(prices):raise ValueError('unaligned lagged label')
    entry,end=index+lag,index+lag+60
    if end>=len(days):raise ValueError('lagged short horizon not mature')
    head=dict(index=index,maturity_index=end)
    if days[entry].endswith('-12-31'):
        return dict(**head,status='UNEXECUTABLE',reason='FORBIDDEN_YEAR_END_ENTRY',simple_return=None)
    bid,_=quote(prices[entry]);q=((D('24.99'))/(bid*D('1.003'))).quantize(D('.00001'),rounding=ROUND_FLOOR)
    if q<=0 or q*bid<5:return dict(**head,status='UNEXECUTABLE',reason='MINIMUM_NOTIONAL',simple_return=None)
    paid=commission(q,bid);basis=q*bid+paid;peak=basis;borrow=D(0);pending=None
    for j in range(entry+1,end+1):
        _,ask=quote(prices[j]);borrow+=q*D(str(prices[j]))*D('.1')/365
        marked=q*(bid-ask)-paid-q*ask*D('.003')-borrow;peak=max(peak,basis+marked)
        if pending is None:
            why='STOP_LOSS' if marked<=-basis*D('.12') else 'TRAIL_STOP' if peak>=basis*D('1.1') and basis+marked<=peak*D('.88') else 'TAKE_PROFIT' if marked>=basis*D('.5') else None
            if why:pending=dict(trigger=j,due=j+lag,reason=why)
        if j==end or pending is not None and j>=pending['due']:
            fees=paid+commission(q,ask);pnl=q*(bid-ask)-fees-borrow
            return dict(**head,status='DEFINED',entry_index=entry,exit_index=j,
                trigger_index=pending['trigger'] if pending else None,due_index=pending['due'] if pending else None,
                reason='HORIZON_CLOSE' if j==end else pending['reason'],simple_return=float(pnl/basis),
                quantity=str(q),entry_price=str(bid),exit_price=str(ask),fees=str(fees),financing=str(borrow),
                pnl=str(pnl),basis=str(basis),peak_value=str(peak))
    raise AssertionError('lagged short did not expire')


def records(days,prices,cut):
    if cut!=len(days)-1 or len(days)!=len(prices):raise ValueError('physical lagged training prefix required')
    validate_calendar(days);ids=list(range(252,cut-67))
    if len(ids)<128:ids=[]
    banks={h['id']:[label(days,prices,i,h['lag']) for i in ids] for h in HEADS}
    chosen=np.asarray([i for pos,i in enumerate(ids) if all(banks[k][pos]['status']=='DEFINED' for k in banks)],dtype=int)
    return banks,chosen


def fit(rows,vector,ids,cut,head,seed):
    if head not in HEADS or len(ids)<128 or np.any(np.diff(ids)<=0) or ids[-1]+62>cut-6:
        raise ValueError('common maturity/plan boundary')
    state,rec=boosted_fit(rows,vector,ids,cut,LOSS,seed)
    return {**state,'label_kind':'SHORT_NET','execution_lag':head['lag'],'common_sample':True}, {
        **rec,'label_kind':'SHORT_NET','execution_lag':head['lag'],'last_label':int(ids[-1]+60+head['lag']),
        'common_last_label':int(ids[-1]+62)}


def combine(scores):
    a,b=scores['L1'],scores['L2'];out={k:list(v) for k,v in scores.items()}
    out['MEAN']=[None if x is None or y is None else (x+y)/2 for x,y in zip(a,b,strict=True)]
    out['BOTH']=[None if x is None or y is None else min(x,y) for x,y in zip(a,b,strict=True)]
    return out
