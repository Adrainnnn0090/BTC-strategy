"""Fixed, lagged network information; no economic screening or learned transforms."""
from datetime import date,timedelta
import numpy as np
from .tree_factors import matrix

FIELDS=('AdrActCnt','TxCnt','TxTfrCnt','FeeTotNtv','BlkCnt')
LAGS=(7,30)
GROUPS=('PAD55','ACT55')


def append_activity(days,prices,observations,lag,group):
    if lag not in LAGS or group not in GROUPS: raise ValueError('unregistered activity features')
    if not days or [r['date'] for r in observations]!=list(days): raise ValueError('activity dates must match price role')
    start=date(2017,1,1)
    if list(days)!=[(start+timedelta(days=i)).isoformat() for i in range(len(days))] or days[-1]>'2025-12-31':
        raise ValueError('activity calendar outside registered prefix')
    raw=np.asarray([[float(r['metrics'][f]) for f in FIELDS] for r in observations])
    if not np.isfinite(raw).all() or np.any(raw[:,3]<0): raise ValueError('invalid activity values')
    counts=raw[:,[0,1,2,4]]
    if np.any(counts<=0) or np.any(counts!=np.floor(counts)): raise ValueError('invalid activity counts')
    p=np.asarray(prices,dtype=float)
    if len(p)!=len(days) or not np.isfinite(p).all() or np.any(p<=0): raise ValueError('invalid prices')
    streams=np.column_stack((raw[:,:3],raw[:,3]/raw[:,1],raw[:,1]/raw[:,4]))
    extra=np.zeros((len(days),11))
    for i in range(252,len(days)):
        j=i-lag
        assert j>=89
        extra[i,0]=1.
        if group=='PAD55': continue
        long=streams[j-89:j+1].mean(axis=0)
        for k,window in enumerate((7,30)):
            short=streams[j-window+1:j+1].mean(axis=0)
            extra[i,1+5*k:6+5*k]=np.clip(np.log((short+1e-12)/(long+1e-12)),-5,5)
    out=np.column_stack((matrix(days,prices,'CAL44'),extra))
    if not np.isfinite(out).all(): raise ValueError('nonfinite activity factors')
    return out
