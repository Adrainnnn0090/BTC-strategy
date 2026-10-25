"""Earlier long trailing activation, fixed arms and prior-only annual selector."""
import argparse,subprocess,sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .walkforward_io import FOLDS,load_fold
from .b82_io import STUDY,PARENT,SOURCE,SHORT,CARRY,ANCHOR,LEGACY,install_guard
from .price_trail_activation import ARMS,MIN_FOLDS,MIN_DECISIONS,TIE,frame,eligibility,target_frame,score_objective,choose
from .full_retained import load_bank
from .conditional_short import component
from .b64a import RECIPES as OLD_RECIPES,targets as old_targets
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

RECIPES=[dict(id='E25',kind='STATIC',arm=.25),dict(id='E10',kind='STATIC',arm=.1),dict(id='EWF',kind='SELECTOR')]+[dict(id=n,kind='LEGACY')for n in LEGACY]
SOURCES=('lab/b82.py','lab/b82_io.py','lab/price_trail_activation.py','tools/verify_b82.py','tests/test_b82.py',
 'notes/RESEARCH_2025_SCOPE_AUTHORIZED.md','notes/proposed-price-core-trail-activation.md','studies/B82-price-core-trail-activation/spec.md')


def freeze():
    p=read(PARENT/'registration.json');v=read(PARENT/'verification.json');assert v['status']=='PASS'and v['final_members']==245 and v['exact_controls']==28 and not v['validation_read']
    code={f:d for f,d in {**p['sources'],**p['inherited_sources']}.items()if not f.startswith('studies/')};assert all(sha(ROOT/f)==d for f,d in code.items())
    runtime=p['project_runtime_sources'];assert all(sha(f)==d for f,d in runtime.items());binding={}
    for base in (PARENT,SOURCE,SHORT,CARRY,ANCHOR):
        q=base/'registration.json';binding[str(q.relative_to(ROOT))]=sha(q)
    for base in (PARENT,SHORT,CARRY,ANCHOR):
        q=base/'verification.json';binding[str(q.relative_to(ROOT))]=sha(q)
    for year in range(2018,2026):
        for base in (PARENT,SOURCE,SHORT,CARRY):
            for n in ('training.json','seal.json','predictions.json.gz','test-receipt.json'):
                q=base/'folds'/str(year)/n;binding[str(q.relative_to(ROOT))]=sha(q)
        assert read(PARENT/'folds'/str(year)/'training.json')['y01_policy']==read(SOURCE/'folds'/str(year)/'training.json')['y01_policy']
    for base,n in LEGACY.values():
        for case in CASES:
            q=base/'accounts'/n/f'{case}.json.gz';binding[str(q.relative_to(ROOT))]=sha(q)
    write(STUDY/'registration.json',dict(arms=ARMS,recipes=RECIPES,min_finite_folds=MIN_FOLDS,min_valid_decisions=MIN_DECISIONS,tie_tolerance=TIE,
        source=binding,inherited_sources=code,sources={f:sha(ROOT/f)for f in SOURCES},versions=p['versions'],project_runtime_sources=runtime,
        manifest_sha256=sha(FOLDS/'manifest.json'),costs=CASES,financing=BORROW,model_fits=0,max_calibration_configs=15,max_calibration_attempts=60,
        first_eligible_year=2021,final_attempts=36,exact_controls=24,prescribed_replay=['EWF','DELAY'],prescribed_calibration_replay=[2021,'IDENTITY','STRESS'],
        objective_tolerance=2e-12,target_return_pct=10000,strict_drawdown_pct=35,validation_read=False,
        qualification='price-only frozen P02/baseline risk;single long activation coordinate;past-only selection;consumed2018–2025;all2026excluded'))
    print('B82 FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['arms']==ARMS and reg['recipes']==RECIPES and len(RECIPES)==9 and reg['min_finite_folds']==MIN_FOLDS and reg['min_valid_decisions']==MIN_DECISIONS and reg['tie_tolerance']==TIE
    assert sha(FOLDS/'manifest.json')==reg['manifest_sha256']and reg['costs']=={k:list(v)for k,v in CASES.items()}and reg['financing']==BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items():assert sha(ROOT/f)==d,f
    for f,d in reg['project_runtime_sources'].items():assert sha(f)==d,f
    for n,v in reg['versions'].items():assert version(n)==v


def bound(reg,p):
    assert sha(p)==reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def bundle(reg,year):
    forecasts={}
    for base in (PARENT,SOURCE,SHORT):
        folder=base/'folds'/str(year);seal=bound(reg,folder/'seal.json');receipt=bound(reg,folder/'test-receipt.json');f=bound(reg,folder/'predictions.json.gz')
        assert seal['cutoff']==f'{year-1}-12-31'and not seal['current_test_read']and seal['registration_sha256']==sha(base/'registration.json')
        assert receipt['seal_sha256']==sha(folder/'seal.json')and receipt['predictions_sha256']==sha(folder/'predictions.json.gz')and receipt['fitting_calls']==0
        assert not receipt.get('validation_read',False)and not receipt.get('reserved_validation_read',False)
        forecasts[base]=f
    a,b,c=forecasts[PARENT],forecasts[SOURCE],forecasts[SHORT];assert a['dates']==b['dates']==c['dates']
    return dict(dates=a['dates'],scores={'BASE_TREE':b['scores']['BASE_TREE'],'CAL44_STOP':a['scores']['PRICE_L7']},learner=c['scores']['MEAN'],
        flags={k:b['short_flags'][k]for k in ('bear','negative20')})


def history(reg,year):
    days,prices=load_fold(year);records={};policies={}
    for prior in range(2018,year+1):
        tr=bound(reg,SOURCE/'folds'/str(prior)/'training.json');seal=bound(reg,SOURCE/'folds'/str(prior)/'seal.json')
        assert seal['cutoff']==tr['cutoff']==f'{prior-1}-12-31'and not seal['current_test_read']and seal['training_sha256']==sha(SOURCE/'folds'/str(prior)/'training.json')
        policies[prior]=tr['y01_policy']
        if prior<year:records[prior]=bundle(reg,prior)
    values,counts=frame(days,prices,records,policies)
    assert all(day<days[-1]for r in records.values()for day in r['dates'])
    assert values['scores']['BASE_TREE'][-1]is None and values['scores']['CAL44_STOP'][-1]is None and not values['flags']['available'][-1]
    return values,eligibility(counts)


def train(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'train');verify(reg);folder=STUDY/'folds'/str(year);values,eligible=history(reg,year)
    records=[];candidate_sha256={};configs=attempts=complete=rejected=0
    if eligible['eligible']:
        assert year>=2021
        for arm in ARMS:
            target,entry=target_frame(values,{y:arm['arm']for y in values['policies']});ss={};failures={};audits={};account_sha256={};path=folder/'calibration'/arm['id']
            for case in CASES:
                attempts+=1
                try:a=run_account(values['days'],values['prices'],target,case,{},end=values['days'][-1],role='fold_train',entry_permission=entry,annual_settlement=False)
                except ValueError as e:failures[case]=dict(type=type(e).__name__,message=str(e));rejected+=1;continue
                audits[case]=audit(a,values['days'],values['prices'],target,CASES[case],BORROW[case],{},entry,False)
                write(path/f'{case}.json.gz',a);account_sha256[case]=sha(path/f'{case}.json.gz');ss[case]=a['summary'];complete+=1
            record=dict(**arm,summaries=ss,failures=failures,audits=audits,account_sha256=account_sha256,objective=score_objective(ss,failures),training_end=values['days'][-1]);write(path/'candidate.json',record)
            candidate_sha256[arm['id']]=sha(path/'candidate.json')
            records.append(record);configs+=1;print('B82 CALIBRATION',year,arm['id'],record['objective'],failures,flush=True)
        choice=choose(records)
    else:choice=dict(id='IDENTITY',arm=None,objective=None,fallback='INSUFFICIENT_PRIOR_FINITE_HISTORY')
    write(folder/'training.json',dict(year=year,cutoff=values['days'][-1],eligibility=eligible,choice=choice,counts=dict(configs=configs,attempts=attempts,complete=complete,rejected=rejected),
        parent_policy=values['policies'][year],candidate_sha256=candidate_sha256,model_fits=0,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(cutoff=values['days'][-1],train_sha256=sha(FOLDS/str(year)/'train.json'),training_sha256=sha(folder/'training.json'),
        registration_sha256=sha(STUDY/'registration.json'),current_test_read=False))
    print('B82 TRAIN',year,choice,flush=True)


def test(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'test');verify(reg);folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json')
    assert seal['training_sha256']==sha(folder/'training.json')and seal['registration_sha256']==sha(STUDY/'registration.json')and not seal['current_test_read']
    f=bundle(reg,year);write(folder/'predictions.json.gz',f)
    write(folder/'test-receipt.json',dict(seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0,selection_calls=0,validation_read=False,protected_reads=sorted(reads)))
    print('B82 TEST',year,flush=True)


def assemble(reg):
    days,prices=load_fold(2025,include_test=True);records={};policies={};choices={}
    for year in range(2018,2026):
        folder=STUDY/'folds'/str(year);tr=read(folder/'training.json');seal=read(folder/'seal.json');receipt=read(folder/'test-receipt.json')
        assert seal['training_sha256']==sha(folder/'training.json')and receipt['seal_sha256']==sha(folder/'seal.json')and receipt['predictions_sha256']==sha(folder/'predictions.json.gz')
        records[year]=read(folder/'predictions.json.gz');policies[year]=tr['parent_policy'];choices[year]=tr['choice']['arm']
    values,counts=frame(days,prices,records,policies);bank=load_bank(SOURCE,days,lambda p:bound(reg,p),2025);carry=load_bank(CARRY,days,lambda p:bound(reg,p),2025)
    assert bank['policies']['Y01']==policies
    for k in ('BASE_TREE',):assert values['scores'][k]==bank['scores'][k]
    assert values['flags']==bank['flags']
    return values,choices,bank,carry


def targets(assembled,recipe):
    values,choices,bank,carry=assembled;n=recipe['id']
    if recipe['kind']in ('STATIC','SELECTOR')or n=='P02':
        arms=choices if recipe['kind']=='SELECTOR'else{y:recipe.get('arm')for y in values['policies']};return target_frame(values,arms)
    if n=='L06':return component(values['days'],values['prices'],bank['scores'],bank['policies'],bank['flags'],values['learner'],.5,'MODEL')
    old=next(r for r in OLD_RECIPES if r['id']==n);banks={'CARRY':carry}if n in ('H04','H05')else{'AVERAGE':bank,'POST':bank}
    return old_targets((values['days'],values['prices'],banks,None),old)


def replay():
    reg=read(STUDY/'registration.json');reads=install_guard(2025,'replay');verify(reg);assembled=assemble(reg);values=assembled[0];out=[]
    for recipe in RECIPES:
        target,entry=targets(assembled,recipe);ss={};failures={};audits={}
        for case in CASES:
            try:a=run_account(values['days'],values['prices'],target,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as e:failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(a,values['days'],values['prices'],target,CASES[case],BORROW[case],{},entry,False)
            if recipe['kind']=='LEGACY':
                base,name=LEGACY[recipe['id']];assert a==bound(reg,base/'accounts'/name/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a);ss[case]=a['summary']
        dd=max((s['max_drawdown_pct']for s in ss.values()),default=None);passed=not failures and len(ss)==4 and ss['STRESS']['return_pct']>=10000 and dd<35
        out.append(dict(recipe=recipe,summaries=ss,failures=failures,audits=audits,goal_gate=passed));print('B82 RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,validation_read=False,protected_reads=sorted(reads)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','train','test','replay','run'));p.add_argument('--year',type=int);a=p.parse_args()
    if a.command in ('train','test'):
        if a.year is None:p.error('--year required')
        globals()[a.command](a.year)
    elif a.command=='run':
        for year in range(2018,2026):
            for stage in ('train','test'):subprocess.run([sys.executable,'-m','lab.b82',stage,'--year',str(year)],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','lab.b82','replay'],cwd=ROOT,check=True)
    else:globals()[a.command]()
