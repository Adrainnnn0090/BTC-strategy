"""Causal price mechanisms with discrete, predeclared neighborhoods."""
from functools import lru_cache
import numpy as np
import pandas as pd

FAMILIES=['BAND','EMA_CROSS','BREAKOUT','MOMENTUM','ZLEMA','KAMA','SLOPE','MACD','PULLBACK','RSI','DUAL_MOM','TREND_VOTE']
SPACE={
 'BAND':{'n':[30,50,75,100,125,150,200],'band':[0.,.01,.02,.03,.05,.08]},
 'EMA_CROSS':{'fast':[5,10,15,20,30,40,60],'slow':[60,80,100,125,150,200],'band':[0.,.01,.02,.03]},
 'BREAKOUT':{'n':[10,20,30,40,60,90,120],'exit':[5,10,15,20,30,40,60]},
 'MOMENTUM':{'n':[10,20,40,60,90,120,180,252],'threshold':[0.,.02,.05,.1]},
 'ZLEMA':{'n':[20,30,50,75,100,125,150],'band':[0.,.01,.02,.03,.05]},
 'KAMA':{'n':[10,20,30,40,60],'fast':[2,3,5,8],'slow':[20,30,40,60],'band':[0.,.01,.02,.03]},
 'SLOPE':{'n':[20,30,50,75,100,150],'quality':[0.,.1,.2,.3,.4,.5],'threshold':[0.,.02,.05]},
 'MACD':{'fast':[5,8,12,16,24],'slow':[20,26,40,60,80],'signal':[5,9,15,20]},
 'PULLBACK':{'n':[60,100,150,200],'fast':[5,10,15,20,30],'dip':[.01,.02,.03,.05,.08],'recovery':[0.,.01,.03]},
 'RSI':{'n':[2,3,5,7,10,14],'entry':[10,15,20,25,30,35],'exit':[50,60,70,80],'trend':[0,100,200]},
 'DUAL_MOM':{'fast':[5,10,20,30,60],'slow':[60,90,120,180,252],'weight':[.25,.5,.75],'threshold':[0.,.02,.05]},
 'TREND_VOTE':{'n':[20,30,50,75,100],'votes':[1,2,3],'band':[0.,.01,.03]},
}
RISK_SPACE={'stop_loss':[.08,.1,.12,.15,.18,.22,.28],'take_profit':[.3,.5,.8,1.,1.5,2.,3.,5.],'cooldown_days':[0,1,3,5,10], 'vol_target':[0.,.3,.4,.5,.6,.8,1.]}


def valid(config):
 p=config['params'];f=config['family']
 return not ((f in ('EMA_CROSS','MACD','DUAL_MOM') and p['fast']>=p['slow']) or (f=='BREAKOUT' and p['exit']>=p['n']) or (f=='KAMA' and p['fast']>=p['slow']))


class Features:
 def __init__(self,prices):
  self.p=np.asarray(prices,float);self.log=np.log(self.p);self.count=len(prices)
  if not np.isfinite(self.p).all() or np.any(self.p<=0):raise ValueError('invalid reference price')
 @lru_cache(None)
 def mean(self,n):return pd.Series(self.p).rolling(n).mean().to_numpy()
 @lru_cache(None)
 def ema(self,n):return pd.Series(self.p).ewm(span=n,adjust=False,min_periods=n).mean().to_numpy()
 @lru_cache(None)
 def ret(self,n):return self.log-pd.Series(self.log).shift(n).to_numpy()
 @lru_cache(None)
 def vol(self,n):return pd.Series(np.r_[np.nan,np.diff(self.log)]).rolling(n).std(ddof=0).to_numpy()*np.sqrt(365)
 @lru_cache(None)
 def high(self,n):return pd.Series(self.p).shift(1).rolling(n).max().to_numpy()
 @lru_cache(None)
 def low(self,n):return pd.Series(self.p).shift(1).rolling(n).min().to_numpy()
 @lru_cache(None)
 def zlema(self,n):
  lag=(n-1)//2;adjusted=2*self.p-pd.Series(self.p).shift(lag).to_numpy();out=np.full(self.count,np.nan);seed=[];level=None
  for i,x in enumerate(adjusted):
   if not np.isfinite(x):continue
   if level is None:
    seed.append(x)
    if len(seed)==n:level=float(np.mean(seed))
   else:level+=2/(n+1)*(x-level)
   if level is not None:out[i]=level
  return out
 @lru_cache(None)
 def kama(self,n,fast,slow):
  change=abs(self.p-pd.Series(self.p).shift(n).to_numpy());noise=pd.Series(np.r_[np.nan,abs(np.diff(self.p))]).rolling(n).sum().to_numpy()
  rate=(np.divide(change,noise,out=np.zeros(self.count),where=noise>0)*(2/(fast+1)-2/(slow+1))+2/(slow+1))**2
  out=np.full(self.count,np.nan);out[n-1]=np.mean(self.p[:n])
  for i in range(n,self.count):out[i]=out[i-1]+rate[i]*(self.p[i]-out[i-1])
  return out
 @lru_cache(None)
 def slope(self,n):
  x=np.arange(n);x=x-x.mean();den=float(x@x);slopes=np.full(self.count,np.nan);quality=np.full(self.count,np.nan)
  windows=np.lib.stride_tricks.sliding_window_view(self.log,n);center=windows-windows.mean(1,keepdims=True);slopes[n-1:]=center@x/den
  quality[n-1:]=np.divide(slopes[n-1:]**2*den,np.sum(center**2,axis=1),out=np.zeros(len(windows)),where=np.sum(center**2,axis=1)>1e-20)
  return slopes*365,quality
 @lru_cache(None)
 def rsi(self,n):
  change=pd.Series(self.p).diff();up=change.clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean().to_numpy();down=(-change.clip(upper=0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean().to_numpy()
  return 100-100/(1+np.divide(up,down,out=np.full(self.count,np.inf),where=down>0))

 def targets(self,config):
  if not valid(config):raise ValueError('invalid signal periods')
  f=config['family'];p=config['params'];price=self.p;n=p.get('n');buy=sell=None
  if f in ('BAND','ZLEMA','KAMA'):
   mid=self.mean(n) if f=='BAND' else self.zlema(n) if f=='ZLEMA' else self.kama(n,p['fast'],p['slow'])
   buy=price>mid*(1+p['band']);sell=price<mid*(1-p['band'])
  elif f=='EMA_CROSS':
   fast=self.ema(p['fast']);slow=self.ema(p['slow']);buy=fast>slow*(1+p['band']);sell=fast<slow*(1-p['band'])
  elif f=='BREAKOUT':buy=price>self.high(n);sell=price<self.low(p['exit'])
  elif f=='MOMENTUM':buy=self.ret(n)>p['threshold'];sell=self.ret(n)<-p['threshold']
  elif f=='SLOPE':
   slope,q=self.slope(n);buy=(slope>p['threshold'])&(q>=p['quality']);sell=(slope<0)|(q<p['quality']/2)
  elif f=='MACD':
   macd=self.ema(p['fast'])-self.ema(p['slow']);signal=pd.Series(macd).ewm(span=p['signal'],adjust=False,min_periods=p['signal']).mean().to_numpy()
   buy=(macd>signal)&(macd>0);sell=macd<signal
  elif f=='PULLBACK':
   buy=(price>self.mean(n))&(price<self.mean(p['fast'])*(1-p['dip']));sell=(price<self.mean(n))|(price>self.mean(p['fast'])*(1+p['recovery']))
  elif f=='RSI':
   r=self.rsi(n);buy=r<p['entry'];sell=r>p['exit']
   if p['trend']:buy&=price>self.mean(p['trend']);sell|=price<self.mean(p['trend'])
  elif f=='DUAL_MOM':
   score=p['weight']*self.ret(p['fast'])+(1-p['weight'])*self.ret(p['slow']);buy=score>p['threshold'];sell=score<-p['threshold']
  elif f=='TREND_VOTE':
   votes=sum((price>self.mean(k)*(1+p['band'])).astype(int) for k in (n,2*n,3*n));buy=votes>=p['votes'];sell=votes<p['votes']
  else:raise ValueError('unregistered family')
  active=False;targets=[];vol=self.vol(60);v=config['risk']['vol_target']
  for i in range(self.count):
   if i<252:active=False
   elif sell[i]:active=False
   elif buy[i]:active=True
   fraction=.95 if not v or not np.isfinite(vol[i]) else .95*min(1,v/max(vol[i],1e-9))
   targets.append({'long':bool(active),'fraction':float(fraction)})
  return targets
