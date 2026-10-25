"""Dispatch unchanged direct learners; one fixed mean of each architecture pair."""
import math
from . import label_sgd,activity_mlp

PROFILES=label_sgd.PROFILES
SEEDS=label_sgd.SEEDS
assert PROFILES==activity_mlp.PROFILES and SEEDS==activity_mlp.SEEDS
ARCHITECTURES=('LINEAR','MLP8')
LOSSES=('SQUARE','HUBER')


def family(architecture,loss):
    if architecture not in ARCHITECTURES or loss not in LOSSES:raise ValueError('unregistered direct stock learner')
    return 'LINEAR' if architecture=='LINEAR' and loss=='SQUARE' else loss


def tune(rows,targets,cut,architecture,loss):
    kind=family(architecture,loss);learner=label_sgd if architecture=='LINEAR' else activity_mlp
    return learner.tune(rows,targets,cut,kind)


def infer(members,rows,architecture):
    if architecture not in ARCHITECTURES:raise ValueError('unregistered direct stock architecture')
    return (label_sgd if architecture=='LINEAR' else activity_mlp).infer(members,rows)


def averages(record,pairs):
    result={}
    for p in pairs:
        a,b=record[p['linear']],record[p['neural']]
        if len(a)!=len(b):raise ValueError('unaligned stock forecasts')
        values=[]
        for x,y in zip(a,b,strict=True):
            if any(v is not None and not math.isfinite(v) for v in (x,y)):raise ValueError('nonfinite direct stock forecast')
            value=None if x is None or y is None else .5*(x+y)
            if value is not None and not math.isfinite(value):raise ValueError('nonfinite stock average')
            values.append(value)
        result[p['id']]=values
    return result
