"""One-component ablation: remove calendar liquidation from a CLOSE label.

Actual trading still settles annually. This is a hypothetical forecasting target,
not permission to carry a native position across the calendar boundary.
"""
import math
from .execution_labels import quotes,FEE,HORIZON
from .sgd import matured


def path_label(days,prices,index,kind='NOCALENDAR'):
    if kind!='NOCALENDAR'or len(days)!=len(prices)or index<0:
        raise ValueError('unregistered calendar label or clock')
    entry,maturity=index+1,index+HORIZON+1
    if maturity>=len(days):raise ValueError('label horizon is not mature')
    if days[entry].endswith('-12-31'):
        return dict(index=index,maturity_index=maturity,entry_index=None,exit_index=None,
                    trigger_index=None,reason='FORBIDDEN_YEAR_END_ENTRY',log_return=0.)
    _,ask=quotes(prices[entry]);bid,_=quotes(prices[maturity])
    return dict(index=index,maturity_index=maturity,entry_index=entry,exit_index=maturity,
                trigger_index=None,reason='HORIZON_CLOSE',log_return=math.log(float(bid*(1-FEE)/(ask*(1+FEE)))))


def records(days,prices,cut,kind='NOCALENDAR'):
    if cut!=len(days)-1:raise ValueError('label construction requires the physical training prefix')
    return [path_label(days,prices,int(i),kind)for i in matured(cut,HORIZON)]
