"""One registered convex mean, with exact source availability semantics."""
import math


def half_mean(original,other):
    if len(original)!=len(other):raise ValueError('short fusion shape mismatch')
    result=[]
    for a,b in zip(original,other,strict=True):
        if(a is None)!=(b is None):raise ValueError('short fusion availability mismatch')
        if a is None:result.append(None);continue
        if not math.isfinite(a)or not math.isfinite(b):raise ValueError('nonfinite short fusion source')
        value=(a+b)/2
        if not math.isfinite(value):raise ValueError('nonfinite short fusion mean')
        result.append(value)
    return result
