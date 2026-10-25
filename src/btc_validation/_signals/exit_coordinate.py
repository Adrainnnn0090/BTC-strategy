"""Small fixed exit coordinate search; chronological forecast eligibility."""
import hashlib
import json
import math
from .b12_signals import SignalFactory
from .entry_permissions import permissions

PARENTS=('H03','H04')
SPACE={'take_profit':(None,1.,2.,3.),'trailing_stop':(None,.08,.1,.15,.2),'cooldown_days':(None,1,3,7)}
IDENTITY={k:None for k in SPACE}
PASSES=2
MAX_EVALUATIONS=21
MIN_PRIOR_FOLDS=2
MIN_VALID_DECISIONS=300


def config_id(config):
    if set(config)!=set(SPACE)or any(config[k]not in SPACE[k]for k in SPACE):
        raise ValueError('unregistered exit coordinate')
    return hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]


def parent_score(scores,parent):
    if parent=='H04':return list(scores['EXTRA_DYNAMICS_L60'])
    if parent=='H03':return [None if a is None or b is None else .5*(a+b)
        for a,b in zip(scores['CAL44_STOP'],scores['BASE_TREE'],strict=True)]
    raise ValueError('unregistered parent')


def prior_scores(days,forecasts,year,parent):
    if not 2018<=year<=2025 or days[-1]!=f'{year-1}-12-31':raise ValueError('wrong training cutoff')
    where={d:i for i,d in enumerate(days)};out=[None]*len(days);counts={}
    for prior,record in sorted(forecasts.items()):
        if not 2018<=prior<year:raise ValueError('current or future fold forbidden')
        dates=record['dates']
        if not dates or dates[0]!=f'{prior-1}-12-31'or dates[-1]!=f'{prior}-12-30':
            raise ValueError('wrong historical decision clock')
        if len(dates)!=len(set(dates))or dates!=sorted(dates):raise ValueError('duplicate or unordered decisions')
        values=parent_score(record['scores'],parent)
        for day,value in zip(dates,values,strict=True):
            if day not in where or day>=days[-1]:raise ValueError('decision exceeds historical prefix')
            if value is not None and not math.isfinite(value):raise ValueError('nonfinite frozen forecast')
            out[where[day]]=value
        counts[str(prior)]=sum(v is not None for v in values)
    assert out[-1]is None
    eligible=year>=2021 and sum(n>=MIN_VALID_DECISIONS for n in counts.values())>=MIN_PRIOR_FOLDS
    return out,dict(valid_decisions_by_prior_fold=counts,eligible=eligible,last_training_decision_missing=True)


def patch_policy(policy,config):
    config_id(config)
    return {**policy,**{k:v for k,v in config.items()if v is not None}}


def desired(days,prices,score,policies):
    chosen={y:{**p,'model':'CASH'if p['model']=='CASH'else 'NEW'}for y,p in policies.items()}
    if any(p['short_mode']!='NONE'for p in chosen.values()):raise ValueError('only original long parent')
    return SignalFactory(days,prices,{'NEW':score}).targets(chosen),permissions(days,score,'POS1')


def objective(summaries,failures):
    if failures or set(summaries)!={'BASE','STRESS','SEVERE','DELAY'}:return None
    if any(not math.isfinite(s['return_pct'])or s['return_pct']<=-100 or
           not math.isfinite(s['max_drawdown_pct'])or s['max_drawdown_pct']>=35 for s in summaries.values()):return None
    return min(math.log1p(s['return_pct']/100)for s in summaries.values())


def search(evaluate):
    cache={};order=[]
    def get(config):
        name=config_id(config)
        if name not in cache:
            if len(cache)>=MAX_EVALUATIONS:raise ValueError('registered search budget exceeded')
            value=evaluate(dict(config))
            if value is not None and not math.isfinite(value):raise ValueError('invalid objective')
            cache[name]=dict(config=dict(config),objective=value);order.append(name)
        return name,cache[name]['objective']
    current=dict(IDENTITY);current_id,current_score=get(current);trace=[]
    for sweep in range(PASSES):
        for coordinate,levels in SPACE.items():
            before=current_id;best=dict(current);best_id,best_score=current_id,current_score;neighbors=[]
            for value in levels:
                candidate={**current,coordinate:value};name,score=get(candidate);neighbors.append(name)
                if score is not None and (best_score is None or score>best_score+1e-12):
                    best,best_id,best_score=candidate,name,score
            current,current_id,current_score=best,best_id,best_score
            trace.append(dict(sweep=sweep,coordinate=coordinate,before=before,neighbors=neighbors,after=current_id))
    return dict(selected_config=current,selected_id=current_id,selected_objective=current_score,
                fallback='NO_ADMISSIBLE_CANDIDATE_KEEP_ORIGINAL'if current_score is None else None,
                trace=trace,evaluated=cache,evaluation_order=order,evaluation_count=len(cache))
