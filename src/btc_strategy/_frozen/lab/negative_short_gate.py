"""Fixed signed forecast entry permission; held-position desired exits are unchanged."""
from copy import deepcopy
import math

SCORE_THRESHOLD = 0.


def negative_short_entry(targets, permissions, scores, enabled=True):
    if type(enabled) is not bool or not len(targets) == len(permissions) == len(scores):
        raise ValueError('unaligned negative short gate')
    if any(type(v) is not bool for v in permissions):
        raise ValueError('invalid entry permissions')
    if any(v is not None and not math.isfinite(v) for v in scores):
        raise ValueError('nonfinite frozen score')
    out = deepcopy(targets)
    entry = list(permissions)
    if enabled:
        for i, row in enumerate(out):
            if row['direction'] == -1:
                entry[i] = entry[i] and scores[i] is not None and scores[i] < SCORE_THRESHOLD
    return out, entry
