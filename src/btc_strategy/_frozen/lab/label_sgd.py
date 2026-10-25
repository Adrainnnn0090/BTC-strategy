"""Explicit STOP-label linear/Huber SGD; original optimizer, identity regression link."""
import math
import numpy as np
from .sgd import matured, PROFILES, SEEDS

FAMILIES = ('LINEAR', 'HUBER')


def gradient(x, y, w, b, family, l2):
    if family not in FAMILIES:
        raise ValueError('unregistered regression family')
    error = x @ w + b - y
    if family == 'HUBER':
        error = np.clip(error, -1, 1)
    error = error / len(y)
    return x.T @ error + l2*w, float(error.sum())


def prediction(state, rows):
    if state['family'] not in FAMILIES or state['link'] != 'identity':
        raise ValueError('not a registered regression state')
    x = np.clip((np.asarray(rows)-np.asarray(state['mean']))/np.asarray(state['scale']), -5, 5)
    return (x @ np.asarray(state['parameters']['w']) + state['parameters']['b'][0]) * state['label_scale']


def fit(rows, targets, ids, cut, family, profile, seed):
    if family not in FAMILIES or profile not in PROFILES or seed not in SEEDS:
        raise ValueError('unregistered SGD recipe')
    if len(ids)<128 or ids[0]<252 or np.any(np.diff(ids)<=0) or ids[-1]+61>cut-6 or cut>=len(rows):
        raise ValueError('SGD training maturity violated')
    if len(rows)!=len(targets) or not np.isfinite(targets[ids]).all() or not np.isfinite(rows[ids]).all():
        raise ValueError('unavailable matured input')
    x = np.asarray(rows[ids],dtype=float)
    mean, scale = x.mean(0), x.std(0)
    scale = np.where(scale<1e-12, 1., scale)
    x = np.clip((x-mean)/scale,-5,5)
    label_scale = max(float(np.std(targets[ids])),1e-8)
    y = np.asarray(targets[ids],dtype=float)/label_scale
    w, v, total = [np.zeros(x.shape[1]) for _ in range(3)]
    b = vb = total_b = 0.
    rng = np.random.default_rng(seed)
    updates = clipped = 0
    for epoch in range(40):
        order = rng.permutation(len(ids))
        lr = profile['lr']/math.sqrt(1+epoch/10)
        for j in range(0,len(ids),64):
            batch = order[j:j+64]
            gw, gb = gradient(x[batch],y[batch],w,b,family,profile['l2'])
            norm = math.sqrt(float(gw@gw)+gb*gb)
            factor = min(1.,5/max(norm,1e-12))
            clipped += int(factor<1)
            v = .9*v + factor*gw
            vb = .9*vb + factor*gb
            w -= lr*v
            b -= lr*vb
            updates += 1
        if epoch>=20:
            total += w
            total_b += b
    state = dict(family=family,link='identity',label_kind='STOP',horizon=60,n_features=x.shape[1],
                 profile=profile,seed=seed,mean=mean.tolist(),scale=scale.tolist(),label_scale=label_scale,
                 parameters=dict(w=(total/20).tolist(),b=[total_b/20]))
    if not np.isfinite(prediction(state,rows[:cut+1])).all():
        raise ValueError('SGD divergence')
    return state,dict(cut=cut,first=int(ids[0]),last=int(ids[-1]),last_label=int(ids[-1]+61),
                      train_count=len(ids),updates=updates,clipped_updates=clipped,learned_scaler=True,
                      label_kind='STOP',average_epochs=20,epochs=40,batch_size=64)


def fit_pair(rows,targets,ids,cut,family,profile):
    pairs = [fit(rows,targets,ids,cut,family,profile,seed) for seed in SEEDS]
    return [p[0] for p in pairs],[p[1] for p in pairs]


def infer(members,rows):
    return np.mean([prediction(m,rows) for m in members],axis=0)


def tune(rows,targets,cut,family):
    ids = matured(cut,60)
    trials = []
    for profile in PROFILES:
        folds = []
        for held in (ids[-120:-60],ids[-60:]):
            train = matured(int(held[0]),60)
            members, receipts = fit_pair(rows,targets,train,int(held[0]),family,profile)
            loss = float(np.mean((infer(members,rows[held])-targets[held])**2))
            if not np.isfinite(loss):raise ValueError('nonfinite selection loss')
            folds.append(dict(first=int(held[0]),last=int(held[-1]),label_end=int(held[-1]+61),loss=loss,receipts=receipts))
        trials.append(dict(profile=profile,folds=folds,loss=float(np.mean([f['loss'] for f in folds]))))
    chosen = min(range(len(trials)),key=lambda i:(trials[i]['loss'],i))
    members, receipts = fit_pair(rows,targets,ids,cut,family,PROFILES[chosen])
    return members,dict(selected=chosen,trials=trials,receipts=receipts,model_fits=18)
