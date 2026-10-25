"""Loosen only positive inherited volatility caps within original long entry budget."""
from copy import deepcopy
import math
from .b05 import forecast_year

ARMS=(dict(id='VX01',parent='P02',cap=1.),dict(id='VX02',parent='P02',cap=None),dict(id='VX03',parent='PX03',cap=1.),dict(id='VX04',parent='PX03',cap=None))


def patch_budget(days,targets,permissions,policies,cap):
    if cap is not None and cap!='IDENTITY'and(type(cap)is not float or cap!=1.):raise ValueError('unregistered long volatility cap')
    if len(days)!=len(targets)or len(days)!=len(permissions)or any(type(x)is not bool for x in permissions):raise ValueError('unaligned budget inputs')
    out=[deepcopy(t)for t in targets];changed=positive=uncapped=0
    for day,row in zip(days,out,strict=True):
        p=policies[forecast_year(day)];v,f=p['vol_target'],p['fraction'];old=row['long_fraction']
        if not all(math.isfinite(x)for x in (v,f,old))or not 0<=v or not 0<old<=f<=.95:raise ValueError('invalid original long budget')
        positive+=int(v>0);uncapped+=int(v==0)
        if cap!='IDENTITY'and v>0:
            if cap is None:row['long_fraction']=f
            elif cap>v:row['long_fraction']=f*min(1.,(old/f)*(cap/v))
        changed+=int(row['long_fraction']!=old)
        if not old<=row['long_fraction']<=f:raise ValueError('long budget must only relax to original maximum')
    return out,list(permissions),dict(changed_budget_rows=changed,positive_cap_rows=positive,uncapped_policy_rows=uncapped)
