"""Earlier positive forecast distributions and bounded entry-budget multipliers."""
from bisect import bisect_left,bisect_right
from datetime import date
import math
from .exit_coordinate import parent_score

PARENTS=('Y01','Y04')
PARENT_SCORE={'Y01':'H03','Y04':'H04'}
MAPS=('QUARTER','HALF','RAMP')
MIN_SAMPLES=128


def observations(forecasts,year,parent):
    if parent not in PARENTS or not 2018<=year<=2025:raise ValueError('unregistered rank parent or year')
    out=[]
    for prior,record in sorted(forecasts.items()):
        if not 2018<=prior<year:raise ValueError('current or future rank source forbidden')
        ds=record['dates']
        if not ds or ds[0]!=f'{prior-1}-12-31'or ds[-1]!=f'{prior}-12-30':raise ValueError('wrong prior decision clock')
        values=parent_score(record['scores'],PARENT_SCORE[parent])
        out.extend(dict(date=d,score=v,forecast_year=prior)for d,v in zip(ds,values,strict=True))
    return out


def fit(rows,cutoff):
    if date.fromisoformat(cutoff).isoformat()!=cutoff:raise ValueError('noncanonical cutoff')
    previous=None;positive=[]
    for row in rows:
        day=row['date']
        if date.fromisoformat(day).isoformat()!=day:raise ValueError('noncanonical observation date')
        if day>=cutoff or (previous is not None and day<=previous):raise ValueError('rank dates not strictly prior/unique')
        previous=day;value=row['score']
        if value is not None and not math.isfinite(value):raise ValueError('nonfinite rank observation')
        if value is not None and value>0:positive.append(float(value))
    active=len(positive)>=MIN_SAMPLES
    return dict(cutoff=cutoff,observation_count=len(rows),positive_count=len(positive),active=active,
                minimum_samples=MIN_SAMPLES,sorted_positive_scores=sorted(positive)if active else [],
                fallback=None if active else 'INSUFFICIENT_PRIOR_POSITIVE_FORECASTS')


def ranks(state,values):
    ordered=state['sorted_positive_scores'];n=len(ordered)
    if state['active']and (n<MIN_SAMPLES or ordered!=sorted(ordered)or any(not math.isfinite(x)or x<=0 for x in ordered)):
        raise ValueError('invalid fitted rank distribution')
    if not state['active']and ordered:raise ValueError('inactive state has numeric transform')
    out=[]
    for value in values:
        if value is not None and not math.isfinite(value):raise ValueError('nonfinite query forecast')
        if not state['active']or value is None:out.append(None);continue
        out.append((bisect_left(ordered,value)+bisect_right(ordered,value))/(2*n))
    return out


def multipliers(values,method):
    if method not in MAPS:raise ValueError('unregistered sizing map')
    result=[]
    for value in values:
        if value is None:result.append(1.);continue
        if not math.isfinite(value)or not 0<=value<=1:raise ValueError('invalid empirical rank')
        result.append(.5+.5*value if method=='RAMP'else .5 if value<(.25 if method=='QUARTER'else .5)else 1.)
    return result
