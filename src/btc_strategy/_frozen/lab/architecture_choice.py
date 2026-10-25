"""Annual direct-model choice from sealed, prior-training inner-loss receipts."""
import math
from datetime import date
from .sgd import PROFILES

EPSILON = 1e-12
BANKS = ('PAD55', 'ACT55_L7', 'ACT55_L30')
PAIRS = [dict(id=f'CHOOSE_{loss}_{bank}', loss=loss, bank=bank,
              linear=f'{"LINEAR" if loss == "SQUARE" else "HUBER"}_{bank}',
              neural=f'MLP8_{loss}_{bank}')
         for loss in ('SQUARE', 'HUBER') for bank in BANKS]


def cutoff_index(year):
    if year not in range(2018, 2026):
        raise ValueError('unregistered year')
    return (date(year-1, 12, 31)-date(2017, 1, 1)).days


def eligible(cut):
    return cut-67-119-67-252+1 >= 128


def loss_choice(linear, neural):
    if any(not math.isfinite(v) or v < 0 for v in (linear, neural)):
        raise ValueError('invalid selection loss')
    return 'NEURAL' if neural < linear-EPSILON else 'LINEAR'


def checked_loss(record, cut):
    if record['model_fits'] != 18 or len(record['trials']) != 4:
        raise ValueError('unregistered parent fitting scope')
    def check_receipts(receipts, boundary):
        if len(receipts) != 2:
            raise ValueError('wrong seed count')
        for r in receipts:
            expected = dict(cut=boundary, first=252, last=boundary-67,
                            last_label=boundary-6, train_count=boundary-318)
            if any(r[k] != v for k,v in expected.items()) or r['train_count'] < 128:
                raise ValueError('unmatured or mismatched training prefix')
    losses = []
    for profile, trial in zip(PROFILES, record['trials'], strict=True):
        if trial['profile'] != profile or len(trial['folds']) != 2:
            raise ValueError('wrong inner profiles')
        block_losses = []
        for first, fold in zip((cut-186, cut-126), trial['folds'], strict=True):
            if (fold['first'], fold['last'], fold['label_end']) != (first, first+59, first+120):
                raise ValueError('mismatched held indices')
            if not math.isfinite(fold['loss']) or fold['loss'] < 0:
                raise ValueError('invalid block loss')
            check_receipts(fold['receipts'], first)
            block_losses.append(fold['loss'])
        value = math.fsum(block_losses)/2
        if value != trial['loss']:
            raise ValueError('incorrect mean loss')
        losses.append(value)
    chosen = min(range(4), key=lambda i:(losses[i], i))
    if chosen != record['selected']:
        raise ValueError('incorrect selected profile')
    check_receipts(record['receipts'], cut)
    return chosen, losses[chosen]


def select(linear, neural, cut, pair):
    if pair not in PAIRS:
        raise ValueError('unregistered model pair')
    if not eligible(cut):
        if linear is not None or neural is not None:
            raise ValueError('unexpected cold model')
        return dict(eligible=False, decision='LINEAR', source_score=pair['linear'],
                    linear_profile=None, neural_profile=None, linear_loss=None, neural_loss=None)
    if linear is None or neural is None:
        raise ValueError('missing paired model')
    lp, ll = checked_loss(linear, cut); np, nl = checked_loss(neural, cut)
    decision = loss_choice(ll, nl)
    return dict(eligible=True, decision=decision, source_score=pair[decision.lower()],
                linear_profile=lp, neural_profile=np, linear_loss=ll, neural_loss=nl)


def route(record, choices):
    if set(choices) != {p['id'] for p in PAIRS}:
        raise ValueError('wrong routing universe')
    result = {}
    for pair in PAIRS:
        source = choices[pair['id']]
        if source not in (pair['linear'], pair['neural']):
            raise ValueError('cross-pair routing forbidden')
        values = list(record['scores'][source])
        if len(values) != len(record['dates']) or any(v is not None and not math.isfinite(v) for v in values):
            raise ValueError('invalid routed forecast')
        result[pair['id']] = values
    return result
