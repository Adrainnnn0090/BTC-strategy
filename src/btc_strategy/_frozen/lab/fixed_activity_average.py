"""One fixed direct-model average; no fitted weights, routing or renormalization."""
import math
from .architecture_choice import PAIRS as ORIGINAL_PAIRS

PAIRS = [{**p,'id':p['id'].replace('CHOOSE_','AVERAGE_',1)} for p in ORIGINAL_PAIRS]


def average_record(record):
    scores = {}
    for pair in PAIRS:
        a,b = record['scores'][pair['linear']],record['scores'][pair['neural']]
        if len(a) != len(record['dates']) or len(b) != len(record['dates']):
            raise ValueError('unaligned parent predictions')
        values = []
        for x,y in zip(a,b,strict=True):
            if any(v is not None and not math.isfinite(v) for v in (x,y)):
                raise ValueError('nonfinite parent prediction')
            value = None if x is None or y is None else .5*(x+y)
            if value is not None and not math.isfinite(value):
                raise ValueError('nonfinite averaged prediction')
            values.append(value)
        scores[pair['id']] = values
    return scores
