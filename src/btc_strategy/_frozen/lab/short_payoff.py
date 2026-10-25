"""B51 auxiliary short payoff, independent of portfolio signals and capital path.

One synthetic 100-USDT account, a .25 entry budget, STRESS costs, 60-day
expiry, entry-owned short risk and no annual settlement. This is a simple
return on the executed entry basis, never the negative of a long log label.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN
import math
import numpy as np
from .sgd import matured

D = Decimal
KIND = 'SHORT_NET'
HORIZON = 60
FEE, SLIP, ANNUAL = D('.003'), D('.001'), D('.1')
CAPITAL, FRACTION, RESERVE = D(100), D('.25'), D('.01')
RISK = dict(stop_loss=.12, take_profit=.5, trailing_stop=.12, trail_arm=.1, cooldown_days=3)


def validate_calendar(days):
    if not days:
        raise ValueError('empty short label calendar')
    first = date.fromisoformat(days[0])
    if days != [(first + timedelta(days=i)).isoformat() for i in range(len(days))]:
        raise ValueError('non-daily short label calendar')


def quote(price):
    p = D(str(price))
    if not p.is_finite() or p <= 0:
        raise ValueError('invalid short label price')
    bid = (p * (1-SLIP)).quantize(D('.01'), rounding=ROUND_FLOOR)
    ask = (p * (1+SLIP)).quantize(D('.01'), rounding=ROUND_CEILING)
    if bid <= 0:
        raise ValueError('nonpositive quantized short quote')
    return bid, ask


def commission(q, p):
    return (q*p*FEE).quantize(D('.00000001'), rounding=ROUND_HALF_EVEN)


def path_label(days, prices, index):
    if type(index) is not int or index < 0 or len(days) != len(prices):
        raise ValueError('unaligned short label inputs')
    entry, end = index+1, index+HORIZON+1
    if end >= len(days):
        raise ValueError('short label horizon is not mature')
    head = dict(index=index, maturity_index=end)
    if days[entry].endswith('-12-31'):
        return dict(**head, status='UNEXECUTABLE', reason='FORBIDDEN_YEAR_END_ENTRY', simple_return=None)
    bid, _ = quote(prices[entry])
    q = ((CAPITAL*FRACTION-RESERVE)/(bid*(1+FEE))).quantize(D('.00001'), rounding=ROUND_FLOOR)
    if q <= 0 or q*bid < 5:
        return dict(**head, status='UNEXECUTABLE', reason='MINIMUM_NOTIONAL', simple_return=None)
    open_fee = commission(q, bid)
    basis, borrow = q*bid+open_fee, D(0)
    peak, pending = basis, None
    for j in range(entry+1, end+1):
        _, ask = quote(prices[j])
        borrow += q*D(str(prices[j]))*ANNUAL/D(365)
        # Risk uses the unrounded hypothetical liquidation fee, as Native does.
        marked = -q*(ask-bid)-open_fee-q*ask*FEE-borrow
        peak = max(peak, basis+marked)
        trailing = peak >= basis*D('1.1') and basis+marked <= peak*D('.88')
        if pending is None:
            reason = 'STOP_LOSS' if marked <= -basis*D('.12') else 'TRAIL_STOP' if trailing else 'TAKE_PROFIT' if marked >= basis*D('.5') else None
            if reason:
                pending = dict(trigger=j, due=j+1, reason=reason)
        if j == end or pending is not None and j >= pending['due']:
            fees = open_fee+commission(q, ask)
            pnl = -q*(ask-bid)-fees-borrow
            return dict(**head, status='DEFINED', entry_index=entry, exit_index=j,
                        trigger_index=pending['trigger'] if pending else None,
                        due_index=pending['due'] if pending else None,
                        reason='HORIZON_CLOSE' if j == end else pending['reason'],
                        simple_return=float(pnl/basis), quantity=str(q), entry_price=str(bid),
                        exit_price=str(ask), fees=str(fees), financing=str(borrow),
                        pnl=str(pnl), basis=str(basis), peak_value=str(peak))
    raise AssertionError('short label did not expire')


def eligible_ids(days, cut):
    if not 0 <= cut < len(days):
        raise ValueError('short training cut outside prefix')
    ids = matured(cut, HORIZON)
    ids = np.array([i for i in ids if not days[int(i)+1].endswith('-12-31')], dtype=int)
    if len(ids) < 128:
        raise ValueError('insufficient executable short labels')
    return ids


def records(days, prices, cut):
    if cut != len(days)-1 or len(days) != len(prices):
        raise ValueError('short labels require physical training prefix')
    validate_calendar(days)
    return [path_label(days, prices, int(i)) for i in matured(cut, HORIZON)]


def target_vector(rows, length):
    target = np.full(length, np.nan)
    seen = set()
    for row in rows:
        i = row['index']
        if i in seen or not 0 <= i < row['maturity_index'] < length:
            raise ValueError('duplicate or invalid short label boundary')
        seen.add(i)
        if row['status'] == 'UNEXECUTABLE':
            if row['simple_return'] is not None:
                raise ValueError('unexecutable short label must stay undefined')
        elif row['status'] == 'DEFINED' and math.isfinite(row['simple_return']):
            target[i] = row['simple_return']
        else:
            raise ValueError('invalid short label status or payoff')
    return target
