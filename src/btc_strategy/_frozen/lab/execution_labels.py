"""Matured single-entry labels with fixed quotes, fees, calendar and exit rules.

Labels describe return on the entry basis per unit, with cash after exit. They do
not include account sizing, lot rounding, minimum notional, or a second entry.
"""
import math
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
import numpy as np
from .sgd import matured

D = Decimal
FEE = D('.003')
SLIP = D('.001')
HORIZON = 60
KINDS = ('CLOSE', 'STOP', 'RISK')


def quotes(price):
    p = D(str(price))
    if not p.is_finite() or p <= 0:
        raise ValueError('invalid positive label quote')
    bid = (p * (1-SLIP)).quantize(D('.01'), rounding=ROUND_FLOOR)
    ask = (p * (1+SLIP)).quantize(D('.01'), rounding=ROUND_CEILING)
    if bid <= 0 or ask <= 0:
        raise ValueError('invalid positive label quote')
    return bid, ask


def path_label(days, prices, index, kind):
    if kind not in KINDS or len(days) != len(prices) or index < 0:
        raise ValueError('unregistered label recipe or clock')
    entry, maturity = index+1, index+HORIZON+1
    if maturity >= len(days):
        raise ValueError('label horizon is not mature')
    if days[entry].endswith('-12-31'):
        return dict(index=index, maturity_index=maturity, entry_index=None, exit_index=None,
                    trigger_index=None, reason='FORBIDDEN_YEAR_END_ENTRY', log_return=0.)
    deadline = next((j for j in range(entry+1, maturity+1) if days[j].endswith('-12-31')), maturity)
    _, ask = quotes(prices[entry]); basis = ask*(1+FEE); peak = basis
    pending = None
    for j in range(entry+1, deadline+1):
        bid, _ = quotes(prices[j]); liquidation = bid*(1-FEE)
        peak = max(peak, liquidation)
        if pending is None and kind != 'CLOSE':
            reason = 'STOP_LOSS' if liquidation <= basis*D('.85') else None
            if reason is None and kind == 'RISK':
                if peak >= basis*D('1.5') and liquidation <= peak*D('.9'):
                    reason = 'TRAIL_STOP'
                elif liquidation >= basis*D('2'):
                    reason = 'TAKE_PROFIT'
            if reason:
                pending = dict(due=j+1, trigger=j, reason=reason)
        if j == deadline or (pending is not None and j >= pending['due']):
            reason = ('HORIZON_CLOSE' if j == maturity else 'YEAR_CLOSE') if j == deadline else pending['reason']
            return dict(index=index, maturity_index=maturity, entry_index=entry, exit_index=j,
                        trigger_index=pending['trigger'] if pending else None, reason=reason,
                        log_return=math.log(float(liquidation/basis)))
    raise AssertionError('label failed to close')


def records(days, prices, cut, kind):
    if cut != len(days)-1:
        raise ValueError('label construction requires the physical training prefix')
    ids = matured(cut, HORIZON)
    return [path_label(days, prices, int(i), kind) for i in ids]


def target_vector(rows, length):
    values = np.full(length, np.nan)
    for row in rows:
        if not 0 <= row['index'] < row['maturity_index'] < length or not math.isfinite(row['log_return']):
            raise ValueError('invalid label endpoint or value')
        if math.isfinite(values[row['index']]):
            raise ValueError('duplicate label decision')
        values[row['index']] = row['log_return']
    return values
