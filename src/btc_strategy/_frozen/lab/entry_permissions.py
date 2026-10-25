"""Causal permissions for new entries; these never alter desired holding direction."""
import math
from .b05 import forecast_year

GATES = ('POS1', 'POS3')


def permissions(days, values, gate):
    if len(days) != len(values) or gate not in ('NONE', *GATES):
        raise ValueError('unregistered entry gate or mismatched score clock')
    if gate == 'NONE':
        return [True] * len(days)
    result = []
    previous_year = None
    streak = 0
    for day, score in zip(days, values, strict=True):
        year = forecast_year(day)
        if year != previous_year:
            streak = 0
            previous_year = year
        if score is not None and not math.isfinite(score):
            raise ValueError('nonfinite entry score')
        streak = streak + 1 if score is not None and score > 0 else 0
        result.append(streak >= (1 if gate == 'POS1' else 3))
    return result
