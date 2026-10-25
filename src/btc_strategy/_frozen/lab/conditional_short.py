"""Feature-conditioned auxiliary short-return regression and entry gates."""
from copy import deepcopy
import math
import numpy as np
from .boosted_stop import MODELS as LOSS_SPECS,fit as fit2
from .boosted_stop_depth3 import fit as fit3
from .bear_short_overlay import price_flags,overlay
from .short_trailing import with_short_trailing
from .short_payoff import RISK
from .signals import Features
from .exit_coordinate import parent_score
from .b05 import forecast_year

LOSSES=[s for s in LOSS_SPECS if s['id'] in ('SQUARE','HUBER')]
HEADS=[dict(id=f'{ctx}_D{depth}_{s["id"]}',context=ctx,depth=depth,spec=s)
       for ctx in ('ALL','BEAR') for depth in (2,3) for s in LOSSES]
MATCHED=[dict(id=f'MATCHED_D{depth}_{s["id"]}',source=f'ALL_D{depth}_{s["id"]}',
             required=f'BEAR_D{depth}_{s["id"]}') for depth in (2,3) for s in LOSSES]


def selected_ids(days,prices,labels,context):
    if context not in ('ALL','BEAR'):raise ValueError('unknown training context')
    ids=np.asarray([r['index'] for r in labels if r['status']=='DEFINED'],dtype=int)
    if context=='BEAR':
        f=price_flags(days,prices)
        ids=ids[[f['bear'][int(i)] and f['negative20'][int(i)] for i in ids]]
    return ids


def fit(rows,vector,ids,cut,head,seed):
    if head not in HEADS or len(ids)<128 or np.any(np.diff(ids)<=0):raise ValueError('invalid short training plan')
    state,receipt=(fit2 if head['depth']==2 else fit3)(rows,vector,ids,cut,head['spec'],seed)
    return {**state,'label_kind':'SHORT_NET','training_context':head['context']}, {
        **receipt,'label_kind':'SHORT_NET','training_context':head['context']}


def matched_scores(scores):
    out={k:list(v) for k,v in scores.items()}
    for m in MATCHED:
        a,b=out[m['source']],out[m['required']]
        out[m['id']]=[None if defined is None else value for value,defined in zip(a,b,strict=True)]
    return out


def component(days,prices,scores,policies,flags,learner,fraction,gate):
    if fraction not in (.25,.5,.75) or gate not in ('MODEL','PRICE','NEG_LONG'):raise ValueError('unregistered post-cold rule')
    if len(learner)!=len(days) or any(v is not None and not math.isfinite(v) for v in learner):raise ValueError('invalid auxiliary score')
    rows,entry=with_short_trailing(*overlay(days,prices,scores,policies,flags,
        dict(scope='COLD_ONLY',fraction=.75,entry_filter='NEG20')))
    original=parent_score(scores,'H03');vol=Features(prices).vol(20)
    for i,row in enumerate(rows):
        if original[i] is None or row['direction']==1:continue
        if i==0 or original[i-1] is None:
            row['direction']=0;entry[i]=False;continue
        p=policies['Y01'][forecast_year(days[i])];scale=1.
        if p['vol_target']:
            sigma=float(vol[i])
            if not math.isfinite(sigma):
                if i>=252:raise ValueError('missing post-cold volatility')
            else:scale=min(1.,p['vol_target']/max(sigma,1e-12))
        row['short_fraction']=fraction*scale;row['risk']['short']=deepcopy(RISK)
        active=flags['available'][i] and flags['bear'][i] and flags['negative20'][i] and p['model']!='CASH'
        if active:
            row['direction']=-1
            value=learner[i]
            entry[i]=bool(gate=='PRICE' or (original[i]<0 if gate=='NEG_LONG' else value is not None and value>0))
    return rows,entry
