"""Bounded quarter-budget post-cold shorts alongside the immutable cold core."""
from copy import deepcopy
import math
from .bear_short_overlay import overlay
from .short_trailing import with_short_trailing
from .short_payoff import RISK
from .exit_coordinate import parent_score
from .signals import Features
from .b05 import forecast_year

GATES = ('PRICE', 'NEG_LONG', 'EXTRA_STOP', 'HUBER_STOP', 'EXTRA_SHORT_NET', 'HUBER_SHORT_NET')


def targets_and_permissions(days, prices, scores, policies, flags, fraction, gate, enabled=True):
    if fraction not in (.5, .75) or gate not in GATES or type(enabled) is not bool:
        raise ValueError('unregistered post-cold short recipe')
    core = overlay(days, prices, scores, policies, flags,
                   dict(scope='COLD_ONLY', fraction=fraction, entry_filter='NEG20'))
    targets, entry = with_short_trailing(*core)
    if not enabled:
        return targets, entry
    original = parent_score(scores, 'H03')
    learner = scores[gate] if gate not in ('PRICE', 'NEG_LONG') else original
    if len(learner) != len(days) or any(v is not None and not math.isfinite(v) for v in learner):
        raise ValueError('invalid short gate forecast')
    volatility = Features(prices).vol(20)
    for i, row in enumerate(targets):
        if original[i] is None or row['direction'] == 1:
            continue
        # The original cold position closes at its causal model-availability
        # transition, even if the post-cold gate would otherwise want a short.
        if i == 0 or original[i-1] is None:
            row['direction'] = 0
            entry[i] = False
            continue
        year = forecast_year(days[i]); policy = policies['Y01'][year]
        scale = 1.
        if policy['vol_target']:
            sigma = float(volatility[i])
            if not math.isfinite(sigma):
                if i >= 252:
                    raise ValueError('missing post-cold volatility after warmup')
            else:
                scale = min(1., policy['vol_target']/max(sigma, 1e-12))
        row['short_fraction'] = .25*scale
        row['risk']['short'] = deepcopy(RISK)
        active = days[i] >= f'{year-1}-12-31' and flags['available'][i] and flags['bear'][i] and policy['model'] != 'CASH'
        if active:
            row['direction'] = -1
            value = learner[i]
            entry[i] = gate == 'PRICE' or value is not None and (value < 0 if gate in ('NEG_LONG', 'EXTRA_STOP', 'HUBER_STOP') else value > 0)
    return targets, entry
