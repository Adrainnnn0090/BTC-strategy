"""Matched existing estimators, now accepting the frozen mining feature matrices."""
import numpy as np
from . import kernel_models as kernel
from . import tree_stability as trees
from .tree_factors import predict as tree_predict


def tune(rows,prices,cut,family):
    if family=='RFF_RIDGE':
        members,receipt=kernel.tune(rows,prices,cut,60,family)
        return members,dict(family=family,details=receipt,model_fits=27)
    if family!='EXTRA':raise ValueError('unknown mining-model family')
    pairs=[trees.tune(rows,prices,cut,seed)for seed in trees.SEEDS]
    return [s for s,r in pairs],dict(family=family,details=[r for s,r in pairs],model_fits=35)


def infer(members,rows):
    if members[0]['family']=='EXTRA':
        return np.mean([tree_predict(s,rows)for s in members],axis=0)
    return kernel.infer(members,rows)
