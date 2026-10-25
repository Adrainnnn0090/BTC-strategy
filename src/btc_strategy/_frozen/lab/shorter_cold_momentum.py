"""Change only shorter cold-short fresh-entry momentum; every held target remains exact."""
import math
ARMS=(dict(id='MX01',lag=1,mode='REPLACE'),dict(id='MX02',lag=3,mode='REPLACE'),dict(id='MX03',lag=1,mode='AND5'),dict(id='MX04',lag=3,mode='AND5'))


def patch_entry(days,prices,scores,targets,permissions,arm):
    if arm not in ARMS:raise ValueError('unregistered cold entry momentum')
    n=len(days)
    if not all(len(x)==n for x in(prices,targets,permissions,*scores.values()))or any(type(x)is not bool for x in permissions):raise ValueError('unaligned cold entry')
    if any(not math.isfinite(p)or p<=0 for p in prices)or any(v is not None and not math.isfinite(v)for k in('BASE_TREE','CAL44_STOP')for v in scores[k]):raise ValueError('invalid cold entry source')
    if days and(days[0]!='2017-01-01'or days[-1]>'2025-12-31'):raise ValueError('cold entry clock beyond development')
    out=list(permissions);eligible=added=removed=allowed=0
    for i,t in enumerate(targets):
        if scores['BASE_TREE'][i]is not None and scores['CAL44_STOP'][i]is not None:continue
        if t['direction']!=-1:continue
        if i<252:raise ValueError('unregistered pre-warmup cold short')
        negative=bool(prices[i]<prices[i-arm['lag']]);out[i]=negative if arm['mode']=='REPLACE'else bool(permissions[i]and negative)
        eligible+=1;added+=int(out[i]and not permissions[i]);removed+=int(permissions[i]and not out[i]);allowed+=int(out[i])
    return targets,out,dict(eligible_cold_short_decisions=eligible,added_fresh_permissions=added,removed_fresh_permissions=removed,new_cold_entry_permission_days=allowed)
