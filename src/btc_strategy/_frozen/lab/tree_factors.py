"""Causal path/calendar factors and numeric-only stochastic tree estimators."""
import calendar
from datetime import date
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor
from .sgd import matrix as price_matrix, matured, labels

GROUPS = ('PRICE20', 'PATH36', 'CAL44')
SEED = 1701
PROFILES = {
    'SGB': [dict(n_estimators=96, learning_rate=.03, max_depth=2,
                 min_samples_leaf=16, subsample=.65),
            dict(n_estimators=96, learning_rate=.06, max_depth=3,
                 min_samples_leaf=32, subsample=.85)],
    'EXTRA': [dict(n_estimators=96, max_depth=5, min_samples_leaf=16, max_features=.7),
              dict(n_estimators=96, max_depth=8, min_samples_leaf=32, max_features=.7)],
}
PATH_NAMES = ['skew20', 'skew60', 'kurt20', 'kurt60', 'autocorr20', 'autocorr60',
              'sign_balance20', 'sign_balance60', 'down_variance_share20',
              'down_variance_share60', 'log_vol5_60', 'log_vol20_120',
              'signed_streak20', 'days_since_high60', 'largest_move_share20',
              'variance_ratio5_100']
CAL_NAMES = ['weekday_sin', 'weekday_cos', 'month_phase_sin', 'month_phase_cos',
             'year_phase_sin', 'year_phase_cos', 'first3_of_month', 'last3_of_month']


def matrix(days, prices, group):
    if group not in GROUPS or len(days) != len(prices):
        raise ValueError('unknown feature group or unequal input lengths')
    base = price_matrix(prices, 'PRICE20')
    if group == 'PRICE20':
        return base
    p = np.asarray(prices, dtype=float)
    r = pd.Series(np.r_[0., np.diff(np.log(p))])
    columns = []
    for statistic in ('skew', 'kurt'):
        columns.extend(getattr(r.rolling(n), statistic)().fillna(0).to_numpy()
                       for n in (20, 60))
    columns.extend(r.rolling(n).corr(r.shift(1)).replace([np.inf, -np.inf], 0)
                   .fillna(0).to_numpy() for n in (20, 60))
    columns.extend(np.sign(r).rolling(n).mean().fillna(0).to_numpy() for n in (20, 60))
    for n in (20, 60):
        den = (r**2).rolling(n).sum().to_numpy()
        num = (r.clip(upper=0)**2).rolling(n).sum().to_numpy()
        columns.append(np.divide(num, den, out=np.zeros(len(p)), where=den > 1e-20))
    for short, long in ((5, 60), (20, 120)):
        a, b = r.rolling(short).std(ddof=0), r.rolling(long).std(ddof=0)
        columns.append(np.log((a + 1e-12)/(b + 1e-12)).fillna(0).to_numpy())
    streak = np.zeros(len(p))
    for i in range(1, len(p)):
        sign = np.sign(r.iloc[i])
        streak[i] = np.clip(streak[i-1] + sign if np.sign(streak[i-1]) == sign else sign, -20, 20)
    columns.append(streak/20)
    columns.append(pd.Series(p).rolling(60).apply(
        lambda x: np.argmax(x[::-1])/59, raw=True).fillna(0).to_numpy())
    den, num = r.abs().rolling(20).sum().to_numpy(), r.abs().rolling(20).max().to_numpy()
    columns.append(np.divide(num, den, out=np.zeros(len(p)), where=den > 1e-20))
    den = 5*r.rolling(100).var(ddof=0).to_numpy()
    num = r.rolling(5).sum().rolling(100).var(ddof=0).to_numpy()
    columns.append(np.divide(num, den, out=np.zeros(len(p)), where=den > 1e-20))
    assert len(columns) == len(PATH_NAMES) == 16
    if group == 'CAL44':
        dates = [date.fromisoformat(d) for d in days]
        weekday = np.array([d.weekday()/7 for d in dates])
        month = np.array([(d.day-1)/calendar.monthrange(d.year, d.month)[1] for d in dates])
        year = np.array([(d.timetuple().tm_yday-1)/(366 if calendar.isleap(d.year) else 365)
                         for d in dates])
        for phase in (weekday, month, year):
            columns.extend((np.sin(2*np.pi*phase), np.cos(2*np.pi*phase)))
        columns.extend((np.array([d.day <= 3 for d in dates], dtype=float),
                        np.array([calendar.monthrange(d.year, d.month)[1]-d.day < 3
                                  for d in dates], dtype=float)))
    out = np.column_stack([base, *columns])
    out[:252] = 0
    if not np.isfinite(out).all():
        raise ValueError('nonfinite causal factors')
    return out


def tree_state(estimator):
    t = estimator.tree_
    return dict(left=t.children_left.tolist(), right=t.children_right.tolist(),
                feature=t.feature.tolist(), threshold=t.threshold.tolist(),
                value=t.value[:, 0, 0].tolist())


def tree_predict(tree, rows):
    # sklearn's public tree API casts input features to float32 before branching.
    rows = np.asarray(rows, dtype=np.float32)
    left, right = np.asarray(tree['left']), np.asarray(tree['right'])
    feature, threshold = np.asarray(tree['feature']), np.asarray(tree['threshold'])
    node = np.zeros(len(rows), dtype=int)
    for _ in range(len(left)):
        active = left[node] != -1
        if not active.any():
            return np.asarray(tree['value'])[node]
        ix = np.flatnonzero(active)
        n = node[ix]
        node[ix] = np.where(rows[ix, feature[n]] <= threshold[n], left[n], right[n])
    raise ValueError('tree did not terminate')


def predict(state, rows):
    pred = np.full(len(rows), state['initial'], dtype=float)
    for tree in state['trees']:
        pred += state['weight']*tree_predict(tree, rows)
    return pred


def fit(rows, prices, ids, cut, horizon, family, profile):
    if len(ids) < 128 or ids[0] < 252 or ids[-1]+horizon+1 > cut-6:
        raise ValueError('training labels exceed embargo boundary')
    kwargs = dict(profile, random_state=SEED)
    estimator = (GradientBoostingRegressor(loss='huber', alpha=.9, **kwargs)
                 if family == 'SGB' else ExtraTreesRegressor(n_jobs=1, **kwargs)
                 if family == 'EXTRA' else None)
    if estimator is None:
        raise ValueError('unknown tree family')
    estimator.fit(rows[ids], labels(prices, ids, horizon))
    trees = estimator.estimators_.ravel() if family == 'SGB' else estimator.estimators_
    state = dict(family=family, horizon=horizon, profile=profile, seed=SEED,
                 n_features=rows.shape[1],
                 initial=float(estimator.init_.constant_[0, 0]) if family == 'SGB' else 0.,
                 weight=profile['learning_rate'] if family == 'SGB' else 1/len(trees),
                 trees=[tree_state(t) for t in trees])
    # Check representation against sklearn on ALL available training-prefix rows.
    err = float(np.max(np.abs(predict(state, rows[:cut+1])-estimator.predict(rows[:cut+1]))))
    if err > 2e-12:
        raise ValueError('numeric tree representation differs from fitted estimator')
    receipt = dict(cut=cut, first=int(ids[0]), last=int(ids[-1]), train_count=len(ids),
                   last_label=int(ids[-1]+horizon+1), trees=len(trees),
                   serialization_max_error=err, learned_scaler=False)
    return state, receipt


def tune(rows, prices, cut, horizon, family):
    ids = matured(cut, horizon)
    trials = []
    for profile in PROFILES[family]:
        folds = []
        for held in (ids[-120:-60], ids[-60:]):
            train = matured(int(held[0]), horizon)
            state, receipt = fit(rows, prices, train, int(held[0]), horizon, family, profile)
            loss = float(np.mean((predict(state, rows[held])-labels(prices, held, horizon))**2))
            folds.append(dict(first=int(held[0]), last=int(held[-1]),
                              label_end=int(held[-1]+horizon+1), loss=loss, receipt=receipt))
        trials.append(dict(profile=profile, folds=folds, loss=float(np.mean([f['loss'] for f in folds]))))
    chosen = min(range(len(trials)), key=lambda i: (trials[i]['loss'], i))
    state, receipt = fit(rows, prices, ids, cut, horizon, family, PROFILES[family][chosen])
    return state, dict(selected=chosen, trials=trials, receipt=receipt)
