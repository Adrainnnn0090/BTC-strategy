"""Only change the entry-owned short profit trail while core heads are missing."""
from copy import deepcopy
import math

ARMS=tuple(dict(id=f'TS{x:02d}',trailing_stop=x/100)for x in (4,6,8,16))


def patch_risk(scores,targets,permissions,arm):
    if arm is not None and arm not in ARMS:raise ValueError('unregistered cold profit trail')
    n=len(targets)
    if len(permissions)!=n or any(len(scores[k])!=n for k in ('BASE_TREE','CAL44_STOP'))or any(type(p)is not bool for p in permissions):raise ValueError('unaligned cold risk')
    if any(v is not None and not math.isfinite(v)for k in ('BASE_TREE','CAL44_STOP')for v in scores[k]):raise ValueError('invalid core head')
    out=[];cold=changed=0
    for i,original in enumerate(targets):
        row=deepcopy(original)
        if not math.isfinite(row['risk']['short']['trailing_stop']):raise ValueError('invalid original short trail')
        if scores['BASE_TREE'][i]is None or scores['CAL44_STOP'][i]is None:
            cold+=1
            if arm is not None:
                before=row['risk']['short']['trailing_stop'];row['risk']['short']['trailing_stop']=arm['trailing_stop'];changed+=int(before!=arm['trailing_stop'])
        out.append(row)
    return out,list(permissions),dict(cold_risk_rows=cold,changed_risk_rows=changed)
