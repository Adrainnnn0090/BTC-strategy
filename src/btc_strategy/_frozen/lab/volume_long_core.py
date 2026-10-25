"""Only replace STOP head, preserving original BASE_TREE and cold availability."""
import math


def replace_stop(scores,new_stop):
    if not {'BASE_TREE','CAL44_STOP'}<=set(scores)or len(new_stop)!=len(scores['CAL44_STOP'])or len(scores['BASE_TREE'])!=len(new_stop):
        raise ValueError('long-core head alignment')
    if any((a is None)!=(b is None)for a,b in zip(scores['CAL44_STOP'],new_stop,strict=True)):
        raise ValueError('long-core cold availability changed')
    if any(x is not None and not math.isfinite(x)for x in new_stop):raise ValueError('invalid new STOP forecast')
    return {**scores,'CAL44_STOP':list(new_stop)}
