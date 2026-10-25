"""Single frozen coordinate on copied B45 short risk, never on long risk."""
from copy import deepcopy
from .bear_short_overlay import SHORT_RISK

TRAILING_DISTANCE = .12


def with_short_trailing(targets, permissions, enabled=True):
    if type(enabled) is not bool or len(targets) != len(permissions):
        raise ValueError('invalid short trailing identity')
    output = deepcopy(targets)
    if enabled:
        for row in output:
            if row['risk']['short'] != SHORT_RISK:
                raise ValueError('unexpected parent short risk')
            row['risk']['short']['trailing_stop'] = TRAILING_DISTANCE
    return output, list(permissions)
