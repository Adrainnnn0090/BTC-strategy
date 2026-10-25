"""Fixed loss-family coordinate on unchanged common-support SHORT_NET labels."""
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from .boosted_stop import PROFILE
from .lagged_short import HEADS
from .tree_factors import tree_state, predict

LOSSES = (dict(id='HUBER', loss='huber', alpha=.9),
          dict(id='SQUARE', loss='squared_error', alpha=.9),
          dict(id='MEDIAN', loss='absolute_error', alpha=.9),
          dict(id='Q65', loss='quantile', alpha=.65))


def fit(rows, vector, ids, cut, head, spec, seed):
    if head not in HEADS or spec not in LOSSES:
        raise ValueError('unregistered short loss or clock')
    if len(ids) < 128 or ids[0] < 252 or np.any(np.diff(ids) <= 0) or ids[-1]+62 > cut-6:
        raise ValueError('common short maturity/embargo boundary')
    if len(rows) != len(vector) or len(rows) != cut+1 or rows.shape[1] != 44 or not np.isfinite(rows).all() or not np.isfinite(vector[ids]).all():
        raise ValueError('invalid physical prefix or training inputs')
    model = GradientBoostingRegressor(loss=spec['loss'], alpha=spec['alpha'], random_state=seed,
        n_iter_no_change=None, **PROFILE).fit(rows[ids], vector[ids])
    state = dict(family='SGB', spec=spec, seed=seed, n_features=44, profile=PROFILE,
        initial=float(model.init_.constant_[0, 0]), weight=PROFILE['learning_rate'],
        trees=[tree_state(t) for t in model.estimators_.ravel()],
        label_kind='SHORT_NET', execution_lag=head['lag'], common_sample=True)
    error = float(np.max(np.abs(predict(state, rows)-model.predict(rows))))
    if error > 2e-12:
        raise ValueError('numeric model serialization differs')
    return state, dict(cut=cut, first=int(ids[0]), last=int(ids[-1]), count=len(ids),
        last_label=int(ids[-1]+60+head['lag']), common_last_label=int(ids[-1]+62),
        serialization_max_error=error, learned_scaler=False, random_validation=False,
        selection_calls=0, label_kind='SHORT_NET', execution_lag=head['lag'])
