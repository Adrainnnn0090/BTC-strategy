"""Existing Huber model families on fixed dynamic factors, explicit seed ensembles."""
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from . import kernel_models as kernel
from .sgd import matured, labels
from .tree_factors import tree_state, predict as tree_predict, PROFILES as TREE_PROFILES

SEEDS = (101, 307, 509)
SGB_PROFILES = TREE_PROFILES['SGB']
RFF_PROFILES = kernel.PROFILES


def fit_boost(rows, prices, ids, cut, profile, seed):
    if len(ids) < 128 or ids[0] < 252 or ids[-1] + 61 > cut - 6:
        raise ValueError('training labels exceed embargo boundary')
    estimator = GradientBoostingRegressor(loss='huber', alpha=.9, random_state=seed,
                                         n_iter_no_change=None, **profile)
    estimator.fit(rows[ids], labels(prices, ids, 60))
    state = dict(family='SGB_HUBER', horizon=60, profile=profile, seed=seed,
                 n_features=rows.shape[1], initial=float(estimator.init_.constant_[0, 0]),
                 weight=profile['learning_rate'],
                 trees=[tree_state(tree) for tree in estimator.estimators_.ravel()])
    error = float(np.max(np.abs(tree_predict(state, rows[:cut+1]) - estimator.predict(rows[:cut+1]))))
    if error > 2e-12:
        raise ValueError('numeric boosted-tree representation mismatch')
    return state, dict(cut=cut, first=int(ids[0]), last=int(ids[-1]), train_count=len(ids),
        last_label=int(ids[-1]+61), seed=seed, learned_scaler=False,
        trees=len(state['trees']), serialization_max_error=error)


def infer(members, rows):
    if members[0]['family'] == 'RFF_HUBER':
        return kernel.infer(members, rows)
    if any(state['family'] != 'SGB_HUBER' for state in members):
        raise ValueError('unregistered robust ensemble')
    return np.mean([tree_predict(state, rows) for state in members], axis=0)


def tune(rows, prices, cut, family):
    if family == 'RFF_HUBER':
        members, receipt = kernel.tune(rows, prices, cut, 60, family)
        return members, dict(family=family, details=receipt, model_fits=27)
    if family != 'SGB_HUBER':
        raise ValueError('unknown robust family')
    ids = matured(cut, 60); trials = []
    for profile in SGB_PROFILES:
        folds = []
        for held in (ids[-120:-60], ids[-60:]):
            train = matured(int(held[0]), 60)
            pairs = [fit_boost(rows, prices, train, int(held[0]), profile, seed) for seed in SEEDS]
            predicted = infer([state for state, _ in pairs], rows[held])
            folds.append(dict(first=int(held[0]), last=int(held[-1]), label_end=int(held[-1]+61),
                              loss=float(np.mean((predicted - labels(prices, held, 60))**2)),
                              receipts=[receipt for _, receipt in pairs]))
        trials.append(dict(profile=profile, folds=folds, loss=float(np.mean([f['loss'] for f in folds]))))
    chosen = min(range(len(trials)), key=lambda i: (trials[i]['loss'], i))
    final = [fit_boost(rows, prices, ids, cut, SGB_PROFILES[chosen], seed) for seed in SEEDS]
    return [state for state, _ in final], dict(family=family, model_fits=15,
        details=dict(selected=chosen, trials=trials, receipts=[receipt for _, receipt in final]))
