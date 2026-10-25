"""Two fixed positive stock streams; price/calendar core and four stock positions."""
from datetime import date,timedelta
import numpy as np
from .tree_factors import matrix

FIELDS=('AdrBalCnt','SplyCur')
LAGS=(7,30)
GROUPS=('PAD49','HOLD49')


def append_stocks(days,prices,observations,lag,group):
    if lag not in LAGS or group not in GROUPS:raise ValueError('unregistered stock features')
    if not days or [r['date'] for r in observations]!=list(days):raise ValueError('stock dates must match prices')
    start=date(2017,1,1)
    if list(days)!=[(start+timedelta(days=i)).isoformat() for i in range(len(days))] or days[-1]>'2025-12-31':
        raise ValueError('stock calendar outside registered prefix')
    if any(set(r)!={'date','metrics'} or set(r['metrics'])!=set(FIELDS) for r in observations):raise ValueError('unregistered stock columns')
    raw=np.asarray([[float(r['metrics'][f]) for f in FIELDS] for r in observations])
    if not np.isfinite(raw).all() or np.any(raw<=0) or np.any(raw[:,0]!=np.floor(raw[:,0])):raise ValueError('invalid stock values')
    p=np.asarray(prices,dtype=float)
    if len(p)!=len(days) or not np.isfinite(p).all() or np.any(p<=0):raise ValueError('invalid prices')
    extra=np.zeros((len(days),5))
    for i in range(252,len(days)):
        j=i-lag;assert j>=89;extra[i,0]=1.
        if group=='PAD49':continue
        long=raw[j-89:j+1].mean(axis=0)
        for k,w in enumerate((7,30)):
            short=raw[j-w+1:j+1].mean(axis=0)
            extra[i,1+2*k:3+2*k]=np.clip(np.log(short/long),-5,5)
    out=np.column_stack((matrix(days,prices,'CAL44'),extra))
    if not np.isfinite(out).all():raise ValueError('nonfinite stock factors')
    return out
