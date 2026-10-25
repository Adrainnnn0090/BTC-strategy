"""Two preregistered equal model averages; missing constituents remain missing."""
import math

BANKS=('PAD53','REL53_L7','REL53_L30')
AVERAGES=[dict(id=f'{kind}_{bank}',kind=kind,bank=bank,
               models=[f'{arch}_{bank}' for arch in (('LINEAR','MLP8') if kind=='PAIR' else ('EXTRA','LINEAR','MLP8'))])
          for kind in ('PAIR','TRIO') for bank in BANKS]


def fixed_averages(scores):
    output={}
    for spec in AVERAGES:
        streams=[scores[k] for k in spec['models']]
        if len({len(v) for v in streams})!=1:raise ValueError('unaligned average constituents')
        values=[]
        for row in zip(*streams,strict=True):
            if any(v is not None and not math.isfinite(v) for v in row):raise ValueError('nonfinite average constituent')
            value=None if any(v is None for v in row) else .5*(row[0]+row[1]) if spec['kind']=='PAIR' else math.fsum(row)/3.
            if value is not None and not math.isfinite(value):raise ValueError('nonfinite average')
            values.append(value)
        output[spec['id']]=values
    return output
