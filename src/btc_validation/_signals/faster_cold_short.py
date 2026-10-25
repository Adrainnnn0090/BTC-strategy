"""Exact decimal causal MA gates for model-missing fallback; post-cold unchanged."""
from copy import deepcopy
from decimal import Decimal as D,localcontext
import math
from .clock import forecast_year

ARMS=(dict(id='CT01',n=20,band='0'),dict(id='CT02',n=20,band='0.03'),dict(id='CT03',n=50,band='0'),dict(id='CT04',n=50,band='0.03'))


def price_flags(prices,arm):
    if arm not in ARMS:raise ValueError('unregistered cold price rule')
    values=[D(str(x))for x in prices]
    if any(not p.is_finite()or p<=0 for p in values):raise ValueError('invalid cold source price')
    out=[];n=arm['n']
    with localcontext()as ctx:
        ctx.prec=50;total=D(0);multiple=D(1)-D(arm['band'])
        for i,value in enumerate(values):
            total+=value
            if i>=n:total-=values[i-n]
            out.append(bool(i>=252 and i+1>=n and value<total/D(n)*multiple))
    return out


def apply_cold_gate(days,prices,scores,flags,policies,targets,permissions,arm):
    if arm is not None and arm not in ARMS:raise ValueError('unregistered cold arm')
    n=len(days)
    if not all(len(x)==n for x in (prices,targets,permissions,*scores.values(),*flags.values()))or any(type(x)is not bool for x in permissions):raise ValueError('unaligned cold gate')
    if any(v is not None and not math.isfinite(v)for k in ('BASE_TREE','CAL44_STOP')for v in scores[k]):raise ValueError('invalid frozen cold head')
    if days and(days[0]!='2017-01-01'or days[-1]>'2026-10-23'):raise ValueError('cold price clock outside development')
    indicator=price_flags(prices,arm)if arm is not None else None;out=[deepcopy(t)for t in targets];entry=list(permissions);cold=changed=entries=shortdays=entrydays=0
    for i,day in enumerate(days):
        if scores['BASE_TREE'][i]is not None and scores['CAL44_STOP'][i]is not None:continue
        cold+=1
        if arm is None:continue
        if targets[i]['direction']==1:raise ValueError('model-missing original long is invalid')
        active=bool(flags['available'][i]and indicator[i]and policies[forecast_year(day)]['model']!='CASH')
        out[i]['direction']=-1 if active else 0
        entry[i]=bool(active and flags['negative20'][i])
        shortdays+=int(active);entrydays+=int(entry[i]);changed+=int(out[i]['direction']!=targets[i]['direction']);entries+=int(entry[i]!=permissions[i])
    return out,entry,dict(cold_decisions=cold,changed_cold_directions=changed,changed_cold_entry_permissions=entries,desired_cold_short_days=shortdays,cold_entry_permission_days=entrydays)
