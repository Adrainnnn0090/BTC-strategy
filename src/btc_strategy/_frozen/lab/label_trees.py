"""Original seven-seed ExtraTrees contract with an explicit matured label vector."""
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from .tree_stability import SEEDS
from .tree_factors import tree_state,predict,PROFILES as TREE_PROFILES
from .sgd import matured

PROFILES = TREE_PROFILES['EXTRA']


def fit(rows, targets, ids, cut, profile, seed, kind):
    if len(ids)<128 or ids[0]<252 or ids[-1]+61>cut-6:
        raise ValueError('training labels exceed embargo boundary')
    if len(targets)!=len(rows) or not np.isfinite(targets[ids]).all():
        raise ValueError('unavailable matured training targets')
    estimator=ExtraTreesRegressor(n_jobs=1,random_state=seed,**profile)
    estimator.fit(rows[ids],targets[ids])
    state=dict(family='EXTRA',horizon=60,label_kind=kind,profile=profile,seed=seed,
               n_features=rows.shape[1],initial=0.,weight=1/len(estimator.estimators_),
               trees=[tree_state(tree)for tree in estimator.estimators_])
    error=float(np.max(np.abs(predict(state,rows[:cut+1])-estimator.predict(rows[:cut+1]))))
    if error>2e-12:raise ValueError('numeric label-tree representation mismatch')
    return state,dict(cut=cut,first=int(ids[0]),last=int(ids[-1]),train_count=len(ids),
        last_label=int(ids[-1]+61),learned_scaler=False,serialization_max_error=error,
        label_kind=kind,trees=len(estimator.estimators_))


def tune_seed(rows,targets,cut,seed,kind):
    ids=matured(cut,60);trials=[]
    for profile in PROFILES:
        folds=[]
        for held in (ids[-120:-60],ids[-60:]):
            state,receipt=fit(rows,targets,matured(int(held[0]),60),int(held[0]),profile,seed,kind)
            loss=float(np.mean((predict(state,rows[held])-targets[held])**2))
            folds.append(dict(first=int(held[0]),last=int(held[-1]),label_end=int(held[-1]+61),
                              loss=loss,receipt=receipt))
        trials.append(dict(profile=profile,folds=folds,loss=float(np.mean([f['loss']for f in folds]))))
    chosen=min(range(len(trials)),key=lambda i:(trials[i]['loss'],i))
    state,receipt=fit(rows,targets,ids,cut,PROFILES[chosen],seed,kind)
    return state,dict(selected=chosen,trials=trials,receipt=receipt)


def tune(rows,targets,cut,kind):
    pairs=[tune_seed(rows,targets,cut,seed,kind)for seed in SEEDS]
    return [state for state,_ in pairs],dict(details=[receipt for _,receipt in pairs],model_fits=35)


def infer(members,rows):
    return np.mean([predict(state,rows)for state in members],axis=0)
