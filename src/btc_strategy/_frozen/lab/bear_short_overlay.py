"""Bounded price-bear shorts alongside the immutable Y01long desired policy."""
import copy
import math
from datetime import date,timedelta
from .signals import Features
from .b05 import forecast_year
from .exit_coordinate import desired,parent_score

SHORTS=[dict(scope=scope,fraction=fraction,entry_filter=gate)
        for scope in ('FULL','COLD_ONLY') for fraction in (.25,.5,.75) for gate in ('PRICE','NEG20')]
SHORT_RISK=dict(stop_loss=.12,take_profit=.5,cooldown_days=3,trailing_stop=0.,trail_arm=.1)


def price_flags(days,prices):
    if not days or len(days)!=len(prices):raise ValueError('unaligned short price calendar')
    first=date(2017,1,1)
    if list(days)!=[(first+timedelta(days=i)).isoformat() for i in range(len(days))] or days[-1]>'2025-12-31':
        raise ValueError('short price calendar outside bounded prefix')
    feature=Features(prices);mean=feature.mean(100)
    return dict(bear=[bool(i>=252 and prices[i]<.97*mean[i]) for i in range(len(days))],
                negative20=[bool(i>=20 and prices[i]<prices[i-20]) for i in range(len(days))])


def overlay(days,prices,scores,policies,flags,spec):
    values=parent_score(scores,'H03');base,permission=desired(days,prices,values,policies['Y01'])
    if spec is None:return base,permission
    if spec not in SHORTS:raise ValueError('unregistered short overlay')
    if set(flags)!={'bear','negative20','available'} or any(len(v)!=len(days) or any(type(b)is not bool for b in v) for v in flags.values()):
        raise ValueError('invalid short flag roles')
    if any(v is not None and not math.isfinite(v) for v in values):raise ValueError('nonfinite frozen long forecast')
    volatility=Features(prices).vol(20);targets=copy.deepcopy(base);entry=list(permission)
    for i,row in enumerate(targets):
        year=forecast_year(days[i]);policy=policies['Y01'][year];scale=1.
        if policy['vol_target']:
            sigma=float(volatility[i])
            if not math.isfinite(sigma):
                if i>=252:raise ValueError('missing volatility after warmup')
            else:scale=min(1.,policy['vol_target']/max(sigma,1e-12))
        row['short_fraction']=spec['fraction']*scale;row['risk']['short']=dict(SHORT_RISK)
        eligible=days[i]>=f'{year-1}-12-31' and flags['available'][i] and flags['bear'][i] and policy['model']!='CASH' and row['direction']!=1
        if spec['scope']=='COLD_ONLY':eligible=eligible and values[i] is None
        if eligible:
            row['direction']=-1
            entry[i]=spec['entry_filter']=='PRICE' or flags['negative20'][i]
    return targets,entry
