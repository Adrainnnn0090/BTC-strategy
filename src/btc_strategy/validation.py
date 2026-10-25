"""Validate the complete economic clock before calculating any features."""
from datetime import date,timedelta
import math

def development_market(days,prices,full=False):
 if not days or len(days)!=len(prices):raise ValueError('unaligned economic data')
 first=date(2017,1,1)
 if days[0]!=first.isoformat()or days[-1]>'2025-12-31':raise ValueError('economic clock outside2017–2025')
 if full and days[-1]!='2025-12-31':raise ValueError('full development context required')
 if any(not isinstance(d,str)or d!=(first+timedelta(days=i)).isoformat()for i,d in enumerate(days)):raise ValueError('economic dates must be unique, contiguous and ordered; no2026')
 if any(type(p)is bool or not isinstance(p,(int,float))or not math.isfinite(p)or p<=0 for p in prices):raise ValueError('invalid reference price')
 return True
