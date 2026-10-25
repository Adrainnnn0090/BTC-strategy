"""Constant 58-position mining ablations; no fitting or feature recomputation."""
import numpy as np
from .mining_features import append_to_prices

ARMS = ('PAD', 'DYNAMICS', 'STATE')


def ablate(base, records, arm, lag):
    if arm not in ARMS:
        raise ValueError('unregistered ablation')
    out = append_to_prices(base, records, 'MINER', lag)
    # CAL44 | observation masks 2 | dynamics 8 | protocol/level state 4.
    if out.shape[1] != 58:
        raise ValueError('ablation requires CAL44 plus 14 mining positions')
    if arm in ('PAD', 'STATE'):
        out[:, 46:54] = 0.
    if arm in ('PAD', 'DYNAMICS'):
        out[:, 54:58] = 0.
    assert np.isfinite(out).all()
    return out
