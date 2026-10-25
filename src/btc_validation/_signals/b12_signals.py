"""Entry-owned volatility budgets on original annual tree-ensemble forecasts."""
import copy
import hashlib
import json
import math
from .clock import forecast_year
from .signals import Features

MODEL_NAMES=('MEAN_PATH36','MEAN_CAL44','CASH')
SPACE=dict(model=MODEL_NAMES,fraction=(.65,.8,.95),vol_target=(0.,.5,.75,1.),
           stop_loss=(.08,.12,.15,.2),take_profit=(.5,1.,2.,3.),
           trailing_stop=(.08,.1,.15,.2),trail_arm=(.2,.5,1.),cooldown_days=(1,3,7),
           short_mode=('NONE','PRICE','SCORE','COLD_SCORE'),short_fraction=(.25,.5,.75),
           short_stop=(.08,.12,.18),short_profit=(.3,.5,1.),short_trail=(0.,.12,.2),
           short_hurdle=(.03,.06,.1))
DEFAULT=dict(model='MEAN_PATH36',fraction=.8,vol_target=0.,stop_loss=.15,take_profit=1.,
             trailing_stop=.1,trail_arm=.5,cooldown_days=3,short_mode='NONE',
             short_fraction=.5,short_stop=.12,short_profit=.5,short_trail=0.,short_hurdle=.03)


def canonical(config):
    c=copy.deepcopy(config)
    if c['model']=='CASH':return {**DEFAULT,'model':'CASH'}
    if c['short_mode']=='NONE':
        for key in ('short_fraction','short_stop','short_profit','short_trail','short_hurdle'):
            c[key]=DEFAULT[key]
    elif c['short_mode']=='PRICE':c['short_hurdle']=DEFAULT['short_hurdle']
    return c


def fingerprint(config):
    return hashlib.sha256(json.dumps(canonical(config),sort_keys=True).encode()).hexdigest()[:20]


class SignalFactory:
    def __init__(self,days,prices,scores):
        self.days,self.prices,self.scores=days,prices,scores
        f=Features(prices)
        self.parent=f.targets(dict(family='BAND',params=dict(n=100,band=.03),risk=dict(vol_target=0.)))
        self.mean=f.mean(100);self.vol=f.vol(20)

    def targets(self,policies):
        active,current=False,None;out=[]
        for i,day in enumerate(self.days):
            year=forecast_year(day);c=policies[year]
            if year!=current:active,current=False,year
            score=None if c['model']=='CASH' else self.scores[c['model']][i]
            if score is None or not self.parent[i]['long']:
                active=False
            elif not active and score>0:
                active=True
            bear=i>=252 and self.prices[i]<self.mean[i]*.97
            short=c['model']!='CASH' and c['short_mode']!='NONE' and bear
            if short and c['short_mode'] in ('SCORE','COLD_SCORE'):
                short=(c['short_mode']=='COLD_SCORE' and score is None) or (
                    score is not None and score<-(c['short_hurdle']+.1*60/365))
            direction=1 if active else -1 if short else 0
            scale=1.
            if c['vol_target']:
                sigma=float(self.vol[i])
                if not math.isfinite(sigma):
                    if i>=252:raise ValueError('missing volatility after warmup')
                    scale=1.  # Unused warmup budgets must satisfy the native positive-budget contract.
                else:scale=min(1.,c['vol_target']/max(sigma,1e-12))
            risk=dict(long={k:c[k]for k in ('stop_loss','take_profit','cooldown_days','trailing_stop','trail_arm')},
                      short=dict(stop_loss=c['short_stop'],take_profit=c['short_profit'],cooldown_days=3,
                                 trailing_stop=c['short_trail'],trail_arm=.1))
            out.append(dict(direction=direction,long_fraction=c['fraction']*scale,
                            short_fraction=c['short_fraction']*scale if c['short_mode']!='NONE'else 0.,
                            policy_year=year,risk=risk))
        return out
