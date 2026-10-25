"""Train-only standardized linear + random Fourier maps; numeric model states."""
import numpy as np
from sklearn.linear_model import Ridge, SGDRegressor
from threadpoolctl import threadpool_limits
from .sgd import matured, labels

SEEDS=(101,307,509)
COMPONENTS=256
PROFILES=[dict(gamma_scale=g,l2=l2)for g in (.25,1.)for l2 in (.001,.01)]


def design(state, rows):
    x=np.clip((np.asarray(rows)-np.asarray(state['mean']))/np.asarray(state['scale']),-5,5)
    z=np.sqrt(2/COMPONENTS)*np.cos(x@np.asarray(state['frequencies'])+np.asarray(state['phases']))
    return np.column_stack((x/np.sqrt(x.shape[1]),z))


def prediction(state, rows):
    return (design(state,rows)@np.asarray(state['coef'])+state['intercept'])*state['label_scale']


def infer(members, rows):
    return np.mean([prediction(s,rows)for s in members],axis=0)


def fit(rows,prices,ids,cut,horizon,family,profile,seed):
    if len(ids)<128 or ids[0]<252 or ids[-1]+horizon+1>cut-6:
        raise ValueError('training labels exceed embargo boundary')
    x=np.asarray(rows)[ids];mean=x.mean(0);scale=x.std(0)
    scale=np.where(scale<1e-12,1.,scale);rng=np.random.default_rng(seed)
    frequencies=rng.normal(0,np.sqrt(2*profile['gamma_scale']/x.shape[1]),(x.shape[1],COMPONENTS))
    phases=rng.uniform(0,2*np.pi,COMPONENTS);y=labels(prices,ids,horizon)
    label_scale=max(float(y.std()),1e-8)
    state=dict(family=family,horizon=horizon,profile=profile,seed=seed,mean=mean.tolist(),
               scale=scale.tolist(),frequencies=frequencies.tolist(),phases=phases.tolist(),label_scale=label_scale)
    z=design(state,x)
    if family=='RFF_RIDGE':
        estimator=Ridge(alpha=len(ids)*profile['l2'],fit_intercept=True,solver='cholesky')
    elif family=='RFF_HUBER':
        estimator=SGDRegressor(loss='huber',epsilon=.5,penalty='l2',alpha=profile['l2'],
            max_iter=80,tol=None,shuffle=True,random_state=seed,learning_rate='invscaling',
            eta0=.03,power_t=.25,average=40*len(ids),early_stopping=False)
    else:raise ValueError('unknown kernel model')
    with threadpool_limits(limits=1):estimator.fit(z,y/label_scale)
    state.update(coef=estimator.coef_.tolist(),intercept=float(np.asarray(estimator.intercept_).reshape(-1)[0]))
    error=float(np.max(np.abs(prediction(state,rows[:cut+1])-estimator.predict(design(state,rows[:cut+1]))*label_scale)))
    if not np.isfinite(prediction(state,rows[:cut+1])).all()or error>2e-12:
        raise ValueError('nonfinite or inconsistent numeric predictor')
    receipt=dict(cut=cut,first=int(ids[0]),last=int(ids[-1]),train_count=len(ids),
        last_label=int(ids[-1]+horizon+1),seed=seed,serialization_max_error=error,
        learned_scaler=True,scaler_rows='matured train decisions only',
        epochs=80 if family=='RFF_HUBER' else 0,
        updates=int(estimator.t_-1)if family=='RFF_HUBER'else 0)
    return state,receipt


def tune(rows,prices,cut,horizon,family):
    ids=matured(cut,horizon);trials=[]
    for profile in PROFILES:
        folds=[]
        for held in (ids[-120:-60],ids[-60:]):
            train=matured(int(held[0]),horizon)
            pairs=[fit(rows,prices,train,int(held[0]),horizon,family,profile,seed)for seed in SEEDS]
            pred=infer([s for s,_ in pairs],rows[held])
            folds.append(dict(first=int(held[0]),last=int(held[-1]),label_end=int(held[-1]+horizon+1),
                loss=float(np.mean((pred-labels(prices,held,horizon))**2)),receipts=[r for _,r in pairs]))
        trials.append(dict(profile=profile,folds=folds,loss=float(np.mean([f['loss']for f in folds]))))
    chosen=min(range(len(trials)),key=lambda i:(trials[i]['loss'],i))
    final=[fit(rows,prices,ids,cut,horizon,family,PROFILES[chosen],seed)for seed in SEEDS]
    return [s for s,_ in final],dict(selected=chosen,trials=trials,receipts=[r for _,r in final])
