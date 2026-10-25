"""Fixed-seed tree stability and a price-independent calendar phase control."""
import calendar
from datetime import date, timedelta
import hashlib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from .tree_factors import matrix as original_matrix, tree_state, predict, PROFILES
from .sgd import matured, labels

GROUPS = ('PRICE20', 'PATH36', 'CAL44', 'PLACEBO44')
SEEDS = (101, 307, 509, 701, 907, 1103, 1701)


def placebo_dates(days):
    out = []
    for text in days:
        d = date.fromisoformat(text)
        n = 366 if calendar.isleap(d.year) else 365
        digest = hashlib.sha256(f'B10-calendar-phase-v1:{d.year}'.encode()).digest()
        shift = 1 + int.from_bytes(digest[:8], 'big') % (n-1)
        ordinal = ((d-date(d.year,1,1)).days + shift) % n
        out.append((date(d.year,1,1)+timedelta(days=ordinal)).isoformat())
    return out


def matrix(days, prices, group):
    if group == 'PLACEBO44':
        # Only the known calendar coordinate changes. All price transforms stay causal.
        return original_matrix(placebo_dates(days), prices, 'CAL44')
    if group not in GROUPS:
        raise ValueError('unknown stability factor group')
    return original_matrix(days, prices, group)


def fit(rows, prices, ids, cut, profile, seed):
    horizon = 60
    if len(ids)<128 or ids[0]<252 or ids[-1]+horizon+1>cut-6:
        raise ValueError('training labels exceed embargo boundary')
    estimator = ExtraTreesRegressor(n_jobs=1, random_state=seed, **profile)
    estimator.fit(rows[ids], labels(prices, ids, horizon))
    trees = estimator.estimators_
    state = dict(family='EXTRA', horizon=horizon, profile=profile, seed=seed,
                 n_features=rows.shape[1], initial=0., weight=1/len(trees),
                 trees=[tree_state(t) for t in trees])
    err = float(np.max(np.abs(predict(state,rows[:cut+1])-estimator.predict(rows[:cut+1]))))
    if err>2e-12:
        raise ValueError('numeric tree representation mismatch')
    return state,dict(cut=cut,first=int(ids[0]),last=int(ids[-1]),train_count=len(ids),
                      last_label=int(ids[-1]+horizon+1),trees=len(trees),
                      serialization_max_error=err,learned_scaler=False)


def tune(rows, prices, cut, seed):
    ids=matured(cut,60);trials=[]
    for profile in PROFILES['EXTRA']:
        folds=[]
        for held in (ids[-120:-60],ids[-60:]):
            state,receipt=fit(rows,prices,matured(int(held[0]),60),int(held[0]),profile,seed)
            loss=float(np.mean((predict(state,rows[held])-labels(prices,held,60))**2))
            folds.append(dict(first=int(held[0]),last=int(held[-1]),label_end=int(held[-1]+61),
                              loss=loss,receipt=receipt))
        trials.append(dict(profile=profile,folds=folds,loss=float(np.mean([f['loss']for f in folds]))))
    chosen=min(range(len(trials)),key=lambda i:(trials[i]['loss'],i))
    state,receipt=fit(rows,prices,ids,cut,PROFILES['EXTRA'][chosen],seed)
    return state,dict(selected=chosen,trials=trials,receipt=receipt)


def ensemble_scores(scores):
    out={}
    for group in GROUPS:
        rows=[scores[f'EXTRA_{group}_H60_S{s}'] for s in SEEDS]
        if all(all(v is None for v in row) for row in rows):
            out['MEAN_'+group]=[None]*len(rows[0])
        else:
            if any(any(v is None for v in row) for row in rows):
                raise ValueError('partial seed ensemble is forbidden')
            out['MEAN_'+group]=np.mean(np.asarray(rows,dtype=float),axis=0).tolist()
    return out
