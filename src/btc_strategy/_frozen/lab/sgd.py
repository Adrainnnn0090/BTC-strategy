"""Transparent mini-batch SGD with matured labels and local preprocessing."""
import math
import numpy as np
from .signals import Features

SEEDS=(712,913)
PROFILES=[{'lr':lr,'l2':l2} for lr in (.01,.03) for l2 in (.001,.01)]
FAMILIES=('LOGIT','HUBER','MLP')

def matured(cut,horizon):
 ids=np.arange(252,cut-horizon-6,dtype=int)
 if len(ids)<128 or ids[-1]+horizon+1>cut-6:raise ValueError('insufficient mature prefix')
 return ids

def matrix(prices,group):
 f=Features(prices);p=f.p;columns=[f.ret(n) for n in (5,20,60,120,252)]+[np.log(p/f.mean(n)) for n in (20,100,200)]+[f.vol(n) for n in (20,60)]
 import pandas as pd
 high=pd.Series(p).rolling(60).max().to_numpy();path=pd.Series(np.r_[np.nan,abs(np.diff(p))]).rolling(20).sum().to_numpy()
 efficiency=np.divide(abs(p-pd.Series(p).shift(20).to_numpy()),path,out=np.zeros(len(p)),where=path>0)
 columns+=[p/high-1,efficiency]
 if group=='PRICE20':
  ret=np.r_[np.nan,np.diff(np.log(p))];downside=np.sqrt(pd.Series(np.minimum(ret,0)**2).rolling(20).mean().to_numpy())*np.sqrt(365)
  path5=pd.Series(np.r_[np.nan,abs(np.diff(p))]).rolling(5).sum().to_numpy();eff5=np.divide(abs(p-pd.Series(p).shift(5).to_numpy()),path5,out=np.zeros(len(p)),where=path5>0)
  columns += [f.ret(1),f.ret(3),f.ret(10),f.vol(5),downside,f.rsi(14)/100,p/pd.Series(p).rolling(20).max().to_numpy()-1,eff5]
 elif group!='PRICE12':raise ValueError('unknown feature group')
 x=np.column_stack(columns);x[:252]=0
 if not np.isfinite(x).all():raise ValueError('nonfinite causal features')
 return x

def labels(prices,ids,horizon):
 p=np.asarray(prices);cost=math.log((1+.001)/((1-.001)*(1-.003)**2))
 return np.log(p[ids+horizon+1]/p[ids+1])-cost

def sigmoid(x):return 1/(1+np.exp(-np.clip(x,-40,40)))

def prediction(state,rows):
 x=np.clip((rows-np.array(state['mean']))/np.array(state['scale']),-5,5);pars={k:np.array(v) for k,v in state['parameters'].items()}
 raw=np.tanh(x@pars['w1']+pars['b1'])@pars['w2']+pars['b2'][0] if 'w1' in pars else x@pars['w']+pars['b'][0]
 return raw*state['label_scale'] if state['family']=='HUBER' else sigmoid(raw)

def fit(rows,prices,ids,cut,horizon,family,profile,seed):
 if len(ids)<128 or ids[-1]+horizon+1>cut-6:raise ValueError('label maturity violated before fit')
 x=rows[ids];mean=x.mean(0);scale=x.std(0);scale=np.where(scale<1e-12,1.,scale);x=np.clip((x-mean)/scale,-5,5)
 raw=labels(prices,ids,horizon);label_scale=max(float(raw.std()),1e-8) if family=='HUBER' else 1.
 y=raw/label_scale if family=='HUBER' else (raw>0).astype(float)
 rng=np.random.default_rng(seed);dims=x.shape[1]
 if family=='MLP':params={'w1':rng.normal(0,math.sqrt(2/(dims+8)),(dims,8)),'b1':np.zeros(8),'w2':rng.normal(0,.01,8),'b2':np.zeros(1)}
 else:params={'w':np.zeros(dims),'b':np.zeros(1)}
 velocity={k:np.zeros_like(v) for k,v in params.items()};average={k:np.zeros_like(v) for k,v in params.items()};losses=[];updates=0
 for epoch in range(40):
  order=rng.permutation(len(ids));lr=profile['lr']/math.sqrt(1+epoch/10)
  for j in range(0,len(ids),64):
   batch=order[j:j+64];xb=x[batch];yb=y[batch]
   if family=='MLP':hidden=np.tanh(xb@params['w1']+params['b1']);score=hidden@params['w2']+params['b2'][0]
   else:score=xb@params['w']+params['b'][0]
   err=np.clip(score-yb,-1,1) if family=='HUBER' else sigmoid(score)-yb;err/=len(batch)
   if family=='MLP':
    hidden_grad=err[:,None]*params['w2']*(1-hidden**2);grad={'w1':xb.T@hidden_grad,'b1':hidden_grad.sum(0),'w2':hidden.T@err,'b2':np.array([err.sum()])}
   else:grad={'w':xb.T@err,'b':np.array([err.sum()])}
   for k in grad:
    if k.startswith('w'):grad[k]+=profile['l2']*params[k]
   norm=math.sqrt(sum(float(np.sum(v*v)) for v in grad.values()));clip=min(1,5/max(norm,1e-12))
   for k in params:velocity[k]=.9*velocity[k]+clip*grad[k];params[k]-=lr*velocity[k]
   updates+=1
  if epoch>=20:
   for k in params:average[k]+=params[k]
 state={'family':family,'horizon':horizon,'profile':profile,'seed':seed,'mean':mean.tolist(),'scale':scale.tolist(),'label_scale':label_scale,'parameters':{k:(v/20).tolist() for k,v in average.items()}}
 if any(not np.isfinite(np.asarray(v)).all() for v in state['parameters'].values()):raise ValueError('SGD divergence')
 return state,{'cut':cut,'train_count':len(ids),'first':int(ids[0]),'last':int(ids[-1]),'last_label':int(ids[-1]+horizon+1),'updates':updates}

def fit_pair(rows,prices,ids,cut,horizon,family,profile):
 members=[];receipts=[]
 for seed in SEEDS:
  model,rec=fit(rows,prices,ids,cut,horizon,family,profile,seed);members.append(model);receipts.append(rec)
 return members,receipts

def infer(members,rows):return np.mean([prediction(m,rows) for m in members],axis=0)

def tune(rows,prices,cut,horizon,family):
 ids=matured(cut,horizon);trials=[]
 for profile in PROFILES:
  folds=[]
  for held in (ids[-120:-60],ids[-60:]):
   train=matured(int(held[0]),horizon);members,recs=fit_pair(rows,prices,train,int(held[0]),horizon,family,profile);pred=infer(members,rows[held]);truth=labels(prices,held,horizon)
   if family=='HUBER':loss=float(np.mean((pred-truth)**2))
   else:
    y=(truth>0).astype(float);prob=np.clip(pred,1e-8,1-1e-8);loss=float(-np.mean(y*np.log(prob)+(1-y)*np.log(1-prob)))
   folds.append({'first':int(held[0]),'last':int(held[-1]),'label_end':int(held[-1]+horizon+1),'loss':loss,'receipts':recs})
  trials.append({'profile':profile,'folds':folds,'loss':float(np.mean([f['loss'] for f in folds]))})
 chosen=min(range(len(trials)),key=lambda i:(trials[i]['loss'],i));members,recs=fit_pair(rows,prices,ids,cut,horizon,family,PROFILES[chosen])
 return members,{'selected':chosen,'trials':trials,'receipts':recs}
