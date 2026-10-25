"""Original ExtraTrees/Huber SGD with matched executable sample indices.

Both SHORT_NET and matched original STOP target controls use the same calendar
filter, profiles, seeds and chronological selection blocks. The SGD core is
target-agnostic; this adapter explicitly corrects its historical STOP metadata
before returning a new-label state, without changing optimizer arithmetic.
"""
import numpy as np
from . import label_trees, label_sgd
from .short_payoff import eligible_ids, KIND
from .tree_stability import SEEDS as TREE_SEEDS
from .tree_factors import predict

ARCHITECTURES = ('EXTRA', 'HUBER')
LABELS = (KIND, 'STOP')


def fit(rows, targets, ids, cut, architecture, profile, seed, kind):
    if architecture not in ARCHITECTURES or kind not in LABELS:
        raise ValueError('unregistered short learner or label')
    profiles = label_trees.PROFILES if architecture == 'EXTRA' else label_sgd.PROFILES
    seeds = TREE_SEEDS if architecture == 'EXTRA' else label_sgd.SEEDS
    if profile not in profiles or seed not in seeds or np.any(np.diff(ids) <= 0):
        raise ValueError('unregistered short fit or unordered samples')
    if architecture == 'EXTRA':
        return label_trees.fit(rows, targets, ids, cut, profile, seed, kind)
    state, receipt = label_sgd.fit(rows, targets, ids, cut, 'HUBER', profile, seed)
    return {**state, 'label_kind': kind}, {**receipt, 'label_kind': kind}


def infer(members, rows, architecture):
    if architecture not in ARCHITECTURES:
        raise ValueError('unregistered short inference architecture')
    function = predict if architecture == 'EXTRA' else label_sgd.prediction
    return np.mean([function(state, rows) for state in members], axis=0)


def plan(days, cut):
    ids = eligible_ids(days, cut)
    held = (ids[-120:-60], ids[-60:])
    train = tuple(eligible_ids(days, int(block[0])) for block in held)
    return ids, held, train


def tune(days, rows, targets, cut, architecture, kind):
    if architecture not in ARCHITECTURES or kind not in LABELS:
        raise ValueError('unregistered short tuning recipe')
    ids, held_blocks, training_blocks = plan(days, cut)
    if len(rows) != len(days) or len(targets) != len(days) or not np.isfinite(targets[ids]).all():
        raise ValueError('undefined executable short training targets')
    profiles = label_trees.PROFILES if architecture == 'EXTRA' else label_sgd.PROFILES
    seeds = TREE_SEEDS if architecture == 'EXTRA' else label_sgd.SEEDS
    details, members = [], []
    # ExtraTrees historically selects each seed separately; SGD selects one
    # profile using the two-seed mean. Preserve these different original rules.
    groups = [(seed,) for seed in seeds] if architecture == 'EXTRA' else [seeds]
    fits = 0
    for group in groups:
        trials = []
        for profile in profiles:
            blocks = []
            for held, train in zip(held_blocks, training_blocks, strict=True):
                pairs = [fit(rows, targets, train, int(held[0]), architecture, profile, seed, kind) for seed in group]
                fits += len(group)
                loss = float(np.mean((infer([p[0] for p in pairs], rows[held], architecture)-targets[held])**2))
                if not np.isfinite(loss):
                    raise ValueError('nonfinite short selection loss')
                blocks.append(dict(first=int(held[0]), last=int(held[-1]), label_end=int(held[-1]+61),
                                   loss=loss, receipts=[p[1] for p in pairs]))
            trials.append(dict(profile=profile, folds=blocks, loss=float(np.mean([b['loss'] for b in blocks]))))
        chosen = min(range(len(trials)), key=lambda j: (trials[j]['loss'], j))
        pairs = [fit(rows, targets, ids, cut, architecture, profiles[chosen], seed, kind) for seed in group]
        fits += len(group)
        members.extend([p[0] for p in pairs])
        details.append(dict(seeds=list(group), selected=chosen, trials=trials, receipts=[p[1] for p in pairs]))
    return members, dict(architecture=architecture, label_kind=kind, details=details, model_fits=fits,
                         eligible_count=len(ids), excluded_dec30=True, original_selection_rules=True)
