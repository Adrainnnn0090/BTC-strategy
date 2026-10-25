"""Fixed single-coordinate and joint long-profit patience, original stop/sizing."""
from copy import deepcopy
import math

ARMS=(dict(id='PX01',trail_arm=1.,trailing_stop=None,take_profit=None),dict(id='PX02',trail_arm=None,trailing_stop=.2,take_profit=None),dict(id='PX03',trail_arm=None,trailing_stop=None,take_profit=3.),dict(id='PX04',trail_arm=1.,trailing_stop=.2,take_profit=3.))


def patch_profit_exit(targets,permissions,arm):
    if arm is not None and arm not in ARMS:raise ValueError('unregistered profit patience')
    if len(targets)!=len(permissions)or any(type(p)is not bool for p in permissions):raise ValueError('unaligned risk inputs')
    out=[deepcopy(t)for t in targets];counts=dict(trail_arm=0,trailing_stop=0,take_profit=0);changed=0
    for row in out:
        long=dict(row['risk']['long']);row['risk']['long']=long;before=dict(long)
        for key in counts:
            if not math.isfinite(long[key]):raise ValueError('invalid original long profit risk')
            if arm is not None and arm[key]is not None:
                long[key]=max(long[key],arm[key]);counts[key]+=int(long[key]!=before[key])
        changed+=int(long!=before)
    return out,list(permissions),dict(patched_rows=changed,fields_changed=counts)
