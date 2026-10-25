"""Fixed entry-owned long profit caps on unchanged TS04 forecasts and exposures."""
from copy import deepcopy
import math

ARMS=tuple(dict(id=f'LP{x:02d}',take_profit=x/10)for x in (25,35,40,50))


def patch_risk(scores,targets,permissions,arm):
    if arm is not None and arm not in ARMS:raise ValueError('unregistered long profit cap')
    n=len(targets)
    if len(permissions)!=n or any(len(scores[k])!=n for k in ('BASE_TREE','CAL44_STOP'))or any(type(p)is not bool for p in permissions):raise ValueError('unaligned profit inputs')
    if any(v is not None and not math.isfinite(v)for k in ('BASE_TREE','CAL44_STOP')for v in scores[k]):raise ValueError('invalid core head')
    out=[];changed=0
    for original in targets:
        row=deepcopy(original);before=row['risk']['long']['take_profit']
        if not math.isfinite(before)or before<=0:raise ValueError('invalid original profit cap')
        if arm is not None:
            row['risk']['long']['take_profit']=arm['take_profit'];changed+=int(before!=arm['take_profit'])
        out.append(row)
    return out,list(permissions),dict(risk_rows=n,changed_profit_rows=changed)
