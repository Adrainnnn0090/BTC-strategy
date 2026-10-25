"""Fixed mean ratios for reported USD volume, price-only and width controls."""
from datetime import date,timedelta
import numpy as np
from .tree_factors import matrix


def append_volume(days,prices,observations,lag,group):
    if lag not in (7,30)or group not in ('PAD47','PRICE47','VOL47'):raise ValueError('unregistered volume factor')
    if not days or len(days)!=len(prices)or days[-1]>'2025-12-31'or days!=[(date(2017,1,1)+timedelta(days=i)).isoformat()for i in range(len(days))]:
        raise ValueError('volume calendar outside authorized prefix')
    extra=np.zeros((len(days),3));extra[252:,0]=1.
    if group!='PAD47':
        if group=='VOL47':
            if observations is None or [r['date']for r in observations]!=days:raise ValueError('unaligned volume source')
            series=np.asarray([float(r['volume'])for r in observations])
        else:series=np.asarray(prices,dtype=float)
        if not np.isfinite(series).all()or np.any(series<=0):raise ValueError('invalid positive volume/price source')
        for i in range(252,len(days)):
            j=i-lag;long=series[j-89:j+1].mean()
            for k,w in enumerate((7,30)):extra[i,k+1]=np.clip(np.log((series[j-w+1:j+1].mean()+1e-12)/(long+1e-12)),-5,5)
    return np.column_stack((matrix(days,prices,'CAL44'),extra))
