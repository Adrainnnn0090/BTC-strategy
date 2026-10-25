"""Past-only, same-USD ETH/BTC features; fixed masks and matched padding."""
import numpy as np
from .tree_factors import matrix

LAGS = (2, 7)
GROUPS = ('PAD54', 'ETH54')


def append_eth(days, prices, observations, lag, group):
    if lag not in LAGS or group not in GROUPS:
        raise ValueError('unregistered ETH features')
    if [r['date'] for r in observations] != list(days):
        raise ValueError('ETH dates must exactly match physical BTC role')
    if any(d < '2017-01-01' or d > '2025-12-31' for d in days):
        raise ValueError('ETH date outside registered research period')
    btc = np.asarray(prices, dtype=float)
    eth = np.array([np.nan if r['price_usd'] is None else float(r['price_usd']) for r in observations])
    if not np.isfinite(btc).all() or np.any(btc <= 0) or np.any(np.isfinite(eth) & (eth <= 0)) or np.isinf(eth).any():
        raise ValueError('invalid BTC/ETH values')
    base = matrix(days, prices, 'CAL44')
    extra = np.zeros((len(days), 10), dtype=float)
    for i in range(252, len(days)):
        j = i - lag
        for w, mask, horizons, vol_col, corr_col in ((20, 0, (1, 5, 20), 6, 8), (60, 1, (60,), 7, 9)):
            if j < w:
                continue
            e, b = eth[j-w:j+1], btc[j-w:j+1]
            if not np.isfinite(e).all():
                continue
            extra[i, mask] = 1.
            if group == 'PAD54':
                continue
            for h in horizons:
                col = 2 + (1, 5, 20, 60).index(h)
                extra[i, col] = np.log(eth[j] / eth[j-h]) - np.log(btc[j] / btc[j-h])
            er, br = np.diff(np.log(e)), np.diff(np.log(b))
            es, bs = np.std(er), np.std(br)
            extra[i, vol_col] = np.log((es + 1e-12) / (bs + 1e-12))
            if es > 1e-12 and bs > 1e-12:
                extra[i, corr_col] = float(np.clip(np.mean((er - er.mean()) * (br - br.mean())) / (es * bs), -1, 1))
    return np.column_stack((base, extra))
