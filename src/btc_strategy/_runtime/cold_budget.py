"""Fixed original-score availability defines cold risk; never auxiliary missingness."""
from copy import deepcopy
import math
from .signals import Features
from .clock import forecast_year
from .exit_coordinate import parent_score
from .conditional_short import component


def adjust(days,prices,rows,entry,original,policies,budget):
    if budget not in (0.,.25,.5,.75):raise ValueError('unregistered cold budget')
    if not len(days)==len(prices)==len(rows)==len(entry)==len(original):raise ValueError('unaligned cold calendar')
    out=deepcopy(rows);allowed=list(entry);vol=Features(prices).vol(20)
    for i,row in enumerate(out):
        if original[i] is not None:continue
        if budget==0.:
            row['direction']=0;row['short_fraction']=0.;allowed[i]=False;continue
        p=policies['Y01'][forecast_year(days[i])];scale=1.
        if p['vol_target']:
            sigma=float(vol[i])
            if not math.isfinite(sigma):
                if i>=252:raise ValueError('missing cold volatility')
            else:scale=min(1.,p['vol_target']/max(sigma,1e-12))
        row['short_fraction']=budget*scale
    return out,allowed


def targets(days,prices,bank,learner,post,cold):
    rows,entry=component(days,prices,bank['scores'],bank['policies'],bank['flags'],learner,post,'MODEL')
    return adjust(days,prices,rows,entry,parent_score(bank['scores'],'H03'),bank['policies'],cold)
