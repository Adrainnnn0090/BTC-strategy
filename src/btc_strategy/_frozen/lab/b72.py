"""Six prospective cold-budget counterfactuals on frozen L05/L06 forecasts."""
import argparse
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .walkforward_io import FOLDS,load_fold
from .b72_io import STUDY,SOURCE,MODELS,ANCHOR,LEGACY,install_guard
from .cold_budget import targets as budget_targets
from .conditional_short import component
from .full_retained import load_bank
from .b64a import RECIPES as OLD_RECIPES,targets as old_targets
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit
from .quote_exposure import measure

RECIPES=[dict(id=f'K{i+1:02}',kind='BUDGET',post=p,cold=c) for i,(p,c) in enumerate((p,c) for p in (.25,.5) for c in (0.,.25,.5))]
RECIPES += [dict(id=n,kind='LEGACY') for n in LEGACY]
SOURCES=('lab/b72.py','lab/b72_io.py','lab/cold_budget.py','lab/quote_exposure.py','tools/verify_b72.py',
    'tools/quote_exposure_reference.py','tests/test_b72.py','studies/B72-cold-budget-exposure/spec.md',
    'notes/proposed-cold-budget-frontier.md','notes/RESEARCH_2025_SCOPE_AUTHORIZED.md')


def freeze():
    p=read(MODELS/'registration.json');v=read(MODELS/'verification.json');anchor=read(ANCHOR/'registration.json')
    assert v['status']=='PASS' and v['accounts']==48 and not v['validation_read']
    code={f:d for f,d in {**p['inherited_sources'],**p['sources']}.items() if not f.startswith('studies/')}
    assert all(sha(ROOT/f)==d for f,d in code.items());runtime=anchor['project_runtime_sources']
    assert all(sha(f)==d for f,d in runtime.items());binding={}
    for base in (SOURCE,MODELS,ANCHOR):
        for n in ('registration.json','verification.json'):
            path=base/n
            if path.exists():binding[str(path.relative_to(ROOT))]=sha(path)
    for base in (SOURCE,MODELS):
        for y in range(2018,2026):
            for n in ('training.json','seal.json','predictions.json.gz','test-receipt.json'):
                path=base/'folds'/str(y)/n;binding[str(path.relative_to(ROOT))]=sha(path)
    for base,n in LEGACY.values():
        for case in CASES:
            path=base/'accounts'/n/f'{case}.json.gz';binding[str(path.relative_to(ROOT))]=sha(path)
    write(STUDY/'registration.json',dict(recipes=RECIPES,source=binding,inherited_sources=code,
        sources={f:sha(ROOT/f) for f in SOURCES},versions=p['versions'],project_runtime_sources=runtime,
        manifest_sha256=sha(FOLDS/'manifest.json'),costs=CASES,financing=BORROW,model_fits=0,accounts=40,exact_controls=16,
        prescribed_replay=['K04','DELAY'],target_return_pct=10000,strict_drawdown_pct=35,equity_tolerance=2e-8,
        validation_read=False,qualification='consumed2018–2025;fixedmodels;riskallocationnotnewalpha;2026excluded'))
    print('B72 FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['recipes']==RECIPES and len(RECIPES)==10 and reg['model_fits']==0
    assert sha(FOLDS/'manifest.json')==reg['manifest_sha256']
    assert reg['costs']=={k:list(v) for k,v in CASES.items()} and reg['financing']==BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items():assert sha(ROOT/f)==d,f
    for f,d in reg['project_runtime_sources'].items():assert sha(f)==d,f
    for n,v in reg['versions'].items():assert version(n)==v


def bound(reg,p):
    assert sha(p)==reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def assemble(reg):
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    bank=load_bank(SOURCE,days,lambda p:bound(reg,p),2025);learner=[None]*len(days)
    for y in range(2018,2026):
        folder=MODELS/'folds'/str(y);tr=bound(reg,folder/'training.json');seal=bound(reg,folder/'seal.json')
        receipt=bound(reg,folder/'test-receipt.json');f=bound(reg,folder/'predictions.json.gz')
        assert seal['training_sha256']==sha(folder/'training.json') and seal['cutoff']==tr['cutoff']==f'{y-1}-12-31' and not seal['current_test_read']
        assert seal['registration_sha256']==sha(MODELS/'registration.json') and receipt['seal_sha256']==sha(folder/'seal.json')
        assert receipt['predictions_sha256']==sha(folder/'predictions.json.gz') and receipt['fitting_calls']==receipt['selection_calls']==0 and not receipt['validation_read']
        assert tr['y01_policy']==bank['policies']['Y01'][y] and f['dates']==days[where[f'{y-1}-12-31']:where[f'{y}-12-31']]
        for d,v in zip(f['dates'],f['scores']['MEAN'],strict=True):learner[where[d]]=v
    return days,prices,bank,learner


def targets(values,recipe):
    days,prices,bank,learner=values;n=recipe['id']
    if recipe['kind']=='BUDGET':return budget_targets(days,prices,bank,learner,recipe['post'],recipe['cold'])
    if n in ('L05','L06'):return component(days,prices,bank['scores'],bank['policies'],bank['flags'],learner,.25 if n=='L05' else .5,'MODEL')
    old=next(r for r in OLD_RECIPES if r['id']==n)
    return old_targets((days,prices,{'AVERAGE':bank,'POST':bank},None),old)


def replay():
    reg=read(STUDY/'registration.json');reads=install_guard('replay');verify(reg);values=assemble(reg);days,prices=values[:2];out=[]
    for recipe in RECIPES:
        target,allowed=targets(values,recipe);ss={};audits={};exposure={};failures={}
        for case in CASES:
            try:a=run_account(days,prices,target,case,{},end='2025-12-31',role='target_replay',entry_permission=allowed,annual_settlement=False)
            except ValueError as exc:failures[case]=dict(type=type(exc).__name__,message=str(exc));continue
            audits[case]=audit(a,days,prices,target,CASES[case],BORROW[case],{},allowed,False);exposure[case]=measure(a,CASES[case][0])
            if recipe['kind']=='LEGACY':
                base,n=LEGACY[recipe['id']];assert a==bound(reg,base/'accounts'/n/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a);ss[case]=a['summary']
        dd=max((s['max_drawdown_pct'] for s in ss.values()),default=None)
        passed=not failures and len(ss)==4 and ss['STRESS']['return_pct']>=10000 and dd<35
        out.append(dict(recipe=recipe,summaries=ss,audits=audits,exposure=exposure,failures=failures,goal_gate=passed))
        print('B72 RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,validation_read=False,protected_reads=sorted(reads)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','replay'));a=p.parse_args();globals()[a.command]()
