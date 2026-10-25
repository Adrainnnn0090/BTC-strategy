"""Fixed lagged relative momentum/volatility; no current/future source values."""
from datetime import date,timedelta
import numpy as np
from lab.tree_factors import matrix

ASSETS=('ltc','xrp')
LAGS=(7,30)
GROUPS=('PAD53','REL53')


def append_cross(days,prices,records,lag,group):
    if lag not in LAGS or group not in GROUPS:raise ValueError('unregistered cross-market bank')
    start=date(2017,1,1)
    if not days or list(days)!=[(start+timedelta(days=i)).isoformat() for i in range(len(days))] or days[-1]>'2025-12-31':
        raise ValueError('cross-market calendar outside registered prefix')
    if [r['date'] for r in records]!=list(days):raise ValueError('unaligned cross-market source')
    if any(set(r)!={'date','prices'} or set(r['prices'])!=set(ASSETS) for r in records):raise ValueError('unregistered cross-market fields')
    raw=np.asarray([[float(r['prices'][a]) for a in ASSETS] for r in records]);p=np.asarray(prices,dtype=float)
    if len(p)!=len(days) or not np.isfinite(p).all() or np.any(p<=0) or not np.isfinite(raw).all() or np.any(raw<=0):
        raise ValueError('invalid cross-market reference price')
    extra=np.zeros((len(days),9));returns=np.vstack((np.zeros((1,2)),np.diff(np.log(raw),axis=0)))
    btc=np.r_[0.,np.diff(np.log(p))]
    for i in range(252,len(days)):
        end=i-lag;extra[i,0]=1.
        if group=='PAD53':continue
        for asset in range(2):
            for k,w in enumerate((7,30)):
                momentum=np.log(raw[end,asset]/raw[end-w,asset])-np.log(p[end]/p[end-w])
                av=float(returns[end-w+1:end+1,asset].std());bv=float(btc[end-w+1:end+1].std())
                if av<=0 or bv<=0:raise ValueError('undefined relative volatility after warmup')
                offset=1+4*asset+2*k
                extra[i,offset:offset+2]=np.clip([momentum,np.log(av/bv)],-5,5)
    out=np.column_stack((matrix(days,prices,'CAL44'),extra))
    if not np.isfinite(out).all():raise ValueError('nonfinite cross-market features')
    return out
