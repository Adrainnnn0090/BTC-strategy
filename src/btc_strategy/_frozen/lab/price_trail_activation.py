"""One long risk coordinate, unchanged forecasts/short risk and prior-only choice."""
import math
from .conditional_short import component
from .bear_short_overlay import price_flags

ARMS=[dict(id='IDENTITY',arm=None),dict(id='ARM25',arm=.25),dict(id='ARM10',arm=.1)]
MIN_FOLDS=2
MIN_DECISIONS=300
TIE=1e-12


def patch_arm(policy,arm):
    if arm not in (None,.25,.1):raise ValueError('unregistered long trailing activation')
    return dict(policy)if arm is None else{**policy,'trail_arm':arm}


def score_objective(summaries,failures):
    if failures or set(summaries)!={'BASE','STRESS','SEVERE','DELAY'}:return None
    if any(not math.isfinite(s['return_pct'])or s['return_pct']<=-100 or not math.isfinite(s['max_drawdown_pct'])or s['max_drawdown_pct']>=35 for s in summaries.values()):return None
    return min(math.log1p(s['return_pct']/100)for s in summaries.values())


def choose(evaluations):
    if [e['id']for e in evaluations]!=[a['id']for a in ARMS]:raise ValueError('incomplete activation candidates')
    if any(e['objective']is not None and not math.isfinite(e['objective'])for e in evaluations):raise ValueError('invalid activation objective')
    best=evaluations[0]
    for candidate in evaluations[1:]:
        v=candidate['objective']
        if v is not None and(not math.isfinite(v)):raise ValueError('invalid activation objective')
        if v is not None and(best['objective']is None or v>best['objective']+TIE):best=candidate
    if best['objective']is None:return dict(id='IDENTITY',arm=None,objective=None,fallback='NO_ADMISSIBLE_KEEP_IDENTITY')
    return dict(id=best['id'],arm=next(a['arm']for a in ARMS if a['id']==best['id']),objective=best['objective'],fallback=None)


def frame(days,prices,records,policies):
    where={d:i for i,d in enumerate(days)};scores={k:[None]*len(days)for k in ('BASE_TREE','CAL44_STOP')};learner=[None]*len(days)
    flags={k:[False]*len(days)for k in ('bear','negative20','available')};expected=price_flags(days,prices);counts={}
    for year,r in sorted(records.items()):
        assert r['dates'][0]==f'{year-1}-12-31'and r['dates'][-1]==f'{year}-12-30'and len(r['dates'])==len(set(r['dates']))and r['dates']==sorted(r['dates'])
        assert all(len(v)==len(r['dates'])for v in [*r['scores'].values(),r['learner'],*r['flags'].values()])
        valid=0
        for pos,day in enumerate(r['dates']):
            assert day in where;i=where[day]
            for key in scores:scores[key][i]=r['scores'][key][pos]
            learner[i]=r['learner'][pos];flags['available'][i]=True
            for key in ('bear','negative20'):
                assert type(r['flags'][key][pos])is bool and r['flags'][key][pos]==expected[key][i];flags[key][i]=r['flags'][key][pos]
            a,b=scores['BASE_TREE'][i],scores['CAL44_STOP'][i]
            if a is not None and b is not None:
                assert math.isfinite(a)and math.isfinite(b);valid+=1
        counts[str(year)]=valid
    return dict(days=days,prices=prices,scores=scores,learner=learner,flags=flags,policies=policies),counts


def eligibility(counts):
    folds=sum(v>0 for v in counts.values());decisions=sum(counts.values())
    return dict(eligible=folds>=MIN_FOLDS and decisions>=MIN_DECISIONS,finite_folds=folds,valid_decisions=decisions,by_fold=counts)


def target_frame(values,arms):
    p={y:patch_arm(policy,arms[y])for y,policy in values['policies'].items()}
    return component(values['days'],values['prices'],values['scores'],{'Y01':p},values['flags'],values['learner'],.5,'MODEL')
