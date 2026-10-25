"""Predeclared validation contract; no selection by validation outcomes."""
from datetime import date,timedelta

TRAIN_START='2017-01-01'
TRAIN_END='2025-12-31'
VALIDATION_END='2026-10-23'
WINDOWS={'H1_TO_JUN29':('2026-01-01','2026-06-29'),
         'JUN30_TO_OCT23':('2026-06-30','2026-10-23')}
STRATEGIES=('LP35','TS04','ME01','MX03','B88A_S03','K02','Y01','C02','C04')
FAMILIES=('base_tree','stop44','price47','short_huber','short_median','mining58')
SEEDS=(101,307,509,701,907,1103,1701)

def calendar(first,last):
 a,b=date.fromisoformat(first),date.fromisoformat(last)
 return [(a+timedelta(days=i)).isoformat()for i in range((b-a).days+1)]

def validate_clock(days,prices,*,training=False,end=None):
 ceiling=TRAIN_END if training else VALIDATION_END
 if not days or days[-1]>ceiling or days!=calendar(TRAIN_START,days[-1]):
  raise ValueError('wrong physical training/validation date prefix')
 if end is not None and days[-1]!=end:raise ValueError('incomplete requested endpoint')
 import math
 if len(days)!=len(prices)or any(type(p)not in(int,float)or not math.isfinite(p)or p<=0 for p in prices):
  raise ValueError('invalid positive reference prices')
 return True
