"""Fixed functional-gradient models on mature original STOP labels."""
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from .tree_factors import PROFILES, tree_state, predict

PROFILE = {**PROFILES['SGB'][0], 'max_depth': 3}
MODELS = [dict(id='SQUARE', loss='squared_error', alpha=.9),
          dict(id='HUBER', loss='huber', alpha=.9),
          dict(id='MEDIAN', loss='absolute_error', alpha=.9),
          dict(id='Q35', loss='quantile', alpha=.35)]


def fit(rows, labels, ids, cut, spec, seed):
    if spec not in MODELS:
        raise ValueError('unregistered loss')
    if len(ids) < 128 or ids[0] < 252 or ids[-1] + 61 > cut - 6:
        raise ValueError('training maturity/embargo boundary')
    if len(rows) != len(labels) or not np.isfinite(rows).all() or not np.isfinite(labels[ids]).all():
        raise ValueError('invalid training inputs')
    model = GradientBoostingRegressor(loss=spec['loss'], alpha=spec['alpha'],
        random_state=seed, n_iter_no_change=None, **PROFILE)
    model.fit(rows[ids], labels[ids])
    state = dict(family='SGB', spec=spec, seed=seed, n_features=rows.shape[1],
        profile=PROFILE, initial=float(model.init_.constant_[0, 0]),
        weight=PROFILE['learning_rate'], trees=[tree_state(t) for t in model.estimators_.ravel()])
    error = float(np.max(np.abs(predict(state, rows) - model.predict(rows))))
    if error > 2e-12:
        raise ValueError('boosted numeric state differs from estimator')
    return state, dict(cut=cut, first=int(ids[0]), last=int(ids[-1]), count=len(ids),
        last_label=int(ids[-1]+61), serialization_max_error=error,
        learned_scaler=False, random_validation=False, selection_calls=0)


def infer(members, rows):
    return np.mean([predict(state, rows) for state in members], axis=0)
