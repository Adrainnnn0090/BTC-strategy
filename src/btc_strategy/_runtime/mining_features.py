"""Lagged, observer-bounded header features. A reconstruction, not PIT certification."""
import bisect
import math
from datetime import datetime,timezone
import numpy as np

LAGS=(60,120)
CONFIRMATIONS=100
CLOCK_BUFFER_SECONDS=7200
MAX_AGE_DAYS=3.
NAMES=('difficulty_growth_1epoch','difficulty_growth_3epoch','difficulty_growth_6epoch',
       'difficulty_growth_12epoch','hashpower_ratio_1_3epoch','hashpower_ratio_3_6epoch',
       'production_speed_1epoch','production_speed_3epoch','difficulty_epoch_phase',
       'subsidy_epoch_phase','log2_subsidy_relative_genesis','log_difficulty_scaled')
MASK_NAMES=('observation_fresh','log_progress_age_days')


def timestamp(day):
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


def advancing_observations(observations):
    """Only already-observed advances in known chain height can move the frontier."""
    events=sorted((int(ms),int(h))for h,ms in observations)
    out=[];frontier=-1
    for ms,h in events:
        if h>frontier:out.append((ms,h));frontier=h
    return out


def block_values(height,times,targets,work):
    if height<24192 or height>=len(times):raise ValueError('insufficient verified block prefix')
    difficulty=lambda h:targets[0]/targets[h]
    columns=[math.log(difficulty(height)/difficulty(height-n))for n in (2016,6048,12096,24192)]
    def rate(n):
        elapsed=int(times[height])-int(times[height-n])
        if elapsed<=0:raise ValueError('nonpositive completed-block elapsed time')
        return (work[height+1]-work[height-n+1])/elapsed
    columns += [math.log(rate(2016)/rate(6048)),math.log(rate(6048)/rate(12096))]
    columns += [math.log(n*600/(int(times[height])-int(times[height-n])))for n in (2016,6048)]
    columns += [(height%2016)/2016,(height%210000)/210000,-(height//210000),
                math.log(difficulty(height))/40]
    assert len(columns)==len(NAMES)
    if not np.isfinite(columns).all():raise ValueError('nonfinite mining factor')
    return columns


def feature_rows(days,times,targets,work,observations,lags=LAGS):
    events=advancing_observations(observations)
    clocks=[x[0]for x in events]
    if any(h>=len(times)for _,h in events):raise ValueError('observation outside verified prefix')
    output=[];cache={}
    for day in days:
        lagged={}
        for lag in lags:
            cutoff_ms=(timestamp(day)-lag*86400-CLOCK_BUFFER_SECONDS)*1000
            ix=bisect.bisect_right(clocks,cutoff_ms)-1
            if ix<0:
                h,ms,age=-1,None,90.
            else:
                ms,h=events[ix];age=(cutoff_ms-ms)/86400000
            confirmed=h-CONFIRMATIONS
            fresh=ms is not None and age<=MAX_AGE_DAYS and confirmed>=24192
            values=[0.]*len(NAMES)
            if fresh:
                if confirmed not in cache:cache[confirmed]=block_values(confirmed,times,targets,work)
                values=cache[confirmed]
            mask=[float(fresh),math.log1p(min(age,90.))/math.log(91)]
            lagged[str(lag)]=dict(values=values,mask=mask,trace=dict(
                cutoff_ms=cutoff_ms,observed_at_ms=ms,observed_height=h,confirmed_height=confirmed,
                age_days=age,fresh=fresh,confirmation_depth=CONFIRMATIONS,
                availability='observer-recorded frontier; ancestor access and canonical survival assumed'))
        output.append(dict(date=day,lagged=lagged))
    return output


def append_to_prices(base,records,kind,lag):
    if kind not in ('MASK','MINER')or lag not in LAGS or len(base)!=len(records):
        raise ValueError('unregistered factor schema')
    extra=[r['lagged'][str(lag)]['mask']+
           (r['lagged'][str(lag)]['values']if kind=='MINER'else [])for r in records]
    out=np.column_stack((base,np.asarray(extra,dtype=float)));out[:252]=0.
    if not np.isfinite(out).all():raise ValueError('nonfinite joined factors')
    return out
