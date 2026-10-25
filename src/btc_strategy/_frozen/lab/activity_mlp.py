"""Fixed direct linear-plus-tanh8 STOP regression with explicit NumPy SGD."""
import math
import numpy as np
from .sgd import matured,PROFILES,SEEDS

FAMILIES=('SQUARE','HUBER')
KEYS=('w','b','hidden_w','hidden_b','out')
WEIGHTS=('w','hidden_w','out')
WIDTH=8
INIT_OFFSET=27000


def initial(dimension,seed):
    rng=np.random.default_rng(seed+INIT_OFFSET)
    return dict(w=np.zeros(dimension),b=np.zeros(1),hidden_w=rng.normal(0,1/math.sqrt(dimension),(dimension,WIDTH)),
        hidden_b=np.zeros(WIDTH),out=np.zeros(WIDTH))


def forward(x,p):
    h=np.tanh(x@p['hidden_w']+p['hidden_b'])
    return x@p['w']+p['b'][0]+h@p['out'],h


def gradient(x,y,p,family,l2):
    if family not in FAMILIES: raise ValueError('unregistered neural loss')
    prediction,h=forward(x,p);error=prediction-y
    score=(np.clip(error,-1,1) if family=='HUBER' else error)/len(y)
    back=score[:,None]*p['out'][None,:]*(1-h*h)
    return dict(w=x.T@score+l2*p['w'],b=np.array([score.sum()]),
        hidden_w=x.T@back+l2*p['hidden_w'],hidden_b=back.sum(axis=0),out=h.T@score+l2*p['out'])


def prediction(state,rows):
    if state['family'] not in FAMILIES or state['architecture']!='LINEAR_PLUS_TANH8': raise ValueError('unregistered neural state')
    x=np.clip((np.asarray(rows)-np.asarray(state['mean']))/np.asarray(state['scale']),-5,5)
    p={k:np.asarray(state['parameters'][k]) for k in KEYS}
    return forward(x,p)[0]*state['label_scale']


def fit(rows,targets,ids,cut,family,profile,seed):
    if family not in FAMILIES or profile not in PROFILES or seed not in SEEDS: raise ValueError('unregistered neural recipe')
    if len(ids)<128 or ids[0]<252 or np.any(np.diff(ids)<=0) or ids[-1]+61>cut-6 or cut>=len(rows):
        raise ValueError('neural training maturity violated')
    if len(rows)!=len(targets) or not np.isfinite(targets[ids]).all() or not np.isfinite(rows[ids]).all(): raise ValueError('unavailable neural input')
    raw=np.asarray(rows[ids],dtype=float);mean=raw.mean(0);scale=raw.std(0);scale=np.where(scale<1e-12,1.,scale)
    x=np.clip((raw-mean)/scale,-5,5);label_scale=max(float(np.std(targets[ids])),1e-8);y=targets[ids]/label_scale
    p=initial(x.shape[1],seed);velocity={k:np.zeros_like(p[k]) for k in KEYS};total={k:np.zeros_like(p[k]) for k in KEYS}
    rng=np.random.default_rng(seed);updates=clipped=0
    for epoch in range(40):
        order=rng.permutation(len(ids));lr=profile['lr']/math.sqrt(1+epoch/10)
        for start in range(0,len(ids),64):
            ix=order[start:start+64];grads=gradient(x[ix],y[ix],p,family,profile['l2'])
            norm=math.sqrt(sum(float((grads[k]*grads[k]).sum()) for k in KEYS));factor=min(1.,5/max(norm,1e-12))
            clipped+=int(factor<1)
            for k in KEYS:
                velocity[k]=.9*velocity[k]+factor*grads[k]
                p[k]-=lr*velocity[k]
            updates+=1
        if epoch>=20:
            for k in KEYS: total[k]+=p[k]
    state=dict(family=family,architecture='LINEAR_PLUS_TANH8',link='identity',hidden_units=WIDTH,initialization_seed=seed+INIT_OFFSET,
        label_kind='STOP',horizon=60,n_features=x.shape[1],profile=profile,seed=seed,mean=mean.tolist(),scale=scale.tolist(),
        label_scale=label_scale,parameters={k:(total[k]/20).tolist() for k in KEYS})
    if not np.isfinite(prediction(state,rows[:cut+1])).all(): raise ValueError('neural divergence')
    return state,dict(cut=cut,first=int(ids[0]),last=int(ids[-1]),last_label=int(ids[-1]+61),train_count=len(ids),
        updates=updates,clipped_updates=clipped,learned_scaler=True,label_kind='STOP',average_epochs=20,epochs=40,batch_size=64,
        hidden_units=WIDTH,initialization_seed=seed+INIT_OFFSET,parameter_count=sum(v.size for v in p.values()))


def fit_pair(rows,targets,ids,cut,family,profile):
    pairs=[fit(rows,targets,ids,cut,family,profile,seed) for seed in SEEDS]
    return [s for s,_ in pairs],[r for _,r in pairs]


def infer(members,rows):
    return np.mean([prediction(m,rows) for m in members],axis=0)


def tune(rows,targets,cut,family):
    ids=matured(cut,60);trials=[]
    for profile in PROFILES:
        folds=[]
        for held in (ids[-120:-60],ids[-60:]):
            inner_cut=int(held[0]);members,receipts=fit_pair(rows,targets,matured(inner_cut,60),inner_cut,family,profile)
            loss=float(np.mean((infer(members,rows[held])-targets[held])**2))
            if not np.isfinite(loss): raise ValueError('nonfinite neural selection loss')
            folds.append(dict(first=int(held[0]),last=int(held[-1]),label_end=int(held[-1]+61),loss=loss,receipts=receipts))
        trials.append(dict(profile=profile,folds=folds,loss=float(np.mean([f['loss'] for f in folds]))))
    chosen=min(range(4),key=lambda i:(trials[i]['loss'],i))
    members,receipts=fit_pair(rows,targets,ids,cut,family,PROFILES[chosen])
    return members,dict(selected=chosen,trials=trials,receipts=receipts,model_fits=18)
