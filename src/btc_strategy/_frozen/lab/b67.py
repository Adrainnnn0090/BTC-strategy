"""Frozen common-sample lag1/lag2 supervision and full continuous Native replay."""
import argparse,subprocess,sys
from importlib.metadata import version
import numpy as np
from threadpoolctl import threadpool_limits
from .io import ROOT,read,write,sha
from .walkforward_io import FOLDS,load_fold
from .b67_io import STUDY,SOURCE,PREVIOUS,LEGACY,install_guard
from .lagged_short import HEADS,LOSS,records,target_vector,fit,combine
from .conditional_short import component
from .tree_factors import matrix,predict
from .tree_stability import SEEDS
from .full_retained import load_bank
from .b64a import RECIPES as OLD_RECIPES,targets as old_targets
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

STREAMS=('L1','L2','MEAN','BOTH')
RECIPES=[dict(id=f'L{i+1:02}',kind='MODEL',stream=s,fraction=f) for i,(s,f) in enumerate((s,f) for s in STREAMS for f in (.25,.5))]
RECIPES += [dict(id=n,kind='LEGACY') for n in LEGACY]
SOURCES=('lab/b67.py','lab/b67_io.py','lab/lagged_short.py','tools/lagged_short_reference.py',
         'tests/test_b67.py','tools/verify_b67.py','notes/RESEARCH_2025_SCOPE_AUTHORIZED.md',
         'studies/B67-lag-matched-short-supervision/spec.md')


def freeze():
    p=read(PREVIOUS/'registration.json');v=read(PREVIOUS/'verification.json');s=read(SOURCE/'registration.json')
    assert v['status']=='PASS' and v['accounts']==180 and not v['validation_read']
    code={f:d for f,d in {**p['sources'],**p['inherited_sources'],**s['sources']}.items() if not f.startswith('studies/')}
    assert all(sha(ROOT/f)==d for f,d in code.items());binding={}
    for base in (SOURCE,PREVIOUS):
        path=base/'registration.json';binding[str(path.relative_to(ROOT))]=sha(path)
        for y in range(2018,2026):
            names=('training.json','seal.json','predictions.json.gz','test-receipt.json') if base==SOURCE else ('seal.json','predictions.json.gz','test-receipt.json')
            for n in names:
                path=base/'folds'/str(y)/n;binding[str(path.relative_to(ROOT))]=sha(path)
    path=PREVIOUS/'verification.json';binding[str(path.relative_to(ROOT))]=sha(path)
    for base,n in LEGACY.values():
        for case in CASES:
            path=base/'accounts'/n/f'{case}.json.gz';binding[str(path.relative_to(ROOT))]=sha(path)
    write(STUDY/'registration.json',dict(heads=HEADS,loss=LOSS,recipes=RECIPES,seeds=SEEDS,
        source=binding,inherited_sources=code,sources={f:sha(ROOT/f) for f in SOURCES},versions=p['versions'],
        manifest_sha256=sha(FOLDS/'manifest.json'),costs=CASES,financing=BORROW,max_member_fits=98,
        accounts=48,exact_controls=16,prescribed_replay=['L04','DELAY'],fixed_refit_year=2025,fixed_refit_seed=101,
        native_label_dates=['2019-02-12','2021-05-12','2024-03-01'],score_tolerance=2e-12,label_cash_tolerance=2e-10,
        target_return_pct=10000,strict_drawdown_pct=35,validation_read=False,
        qualification='consumed2018–2025;common-labelsupport/maturity;fixedclockcoordinate;2026excluded'))
    print('B67 FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['heads']==HEADS and reg['loss']==LOSS and reg['recipes']==RECIPES and len(RECIPES)==12
    assert reg['seeds']==list(SEEDS) and sha(FOLDS/'manifest.json')==reg['manifest_sha256']
    assert reg['costs']=={k:list(v) for k,v in CASES.items()} and reg['financing']==BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items():assert sha(ROOT/f)==d,f
    for n,v in reg['versions'].items():assert version(n)==v


def bound(reg,p):
    assert sha(p)==reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def train(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'train');verify(reg)
    old=bound(reg,SOURCE/'folds'/str(year)/'training.json');os=bound(reg,SOURCE/'folds'/str(year)/'seal.json')
    assert old['cutoff']==os['cutoff']==f'{year-1}-12-31' and not os['current_test_read']
    days,prices=load_fold(year);cut=len(days)-1;rows=matrix(days,prices,'CAL44');banks,ids=records(days,prices,cut)
    folder=STUDY/'folds'/str(year);write(folder/'labels.json.gz',banks);states={};receipts={};count=0
    for head in HEADS:
        key=head['id'];receipts[key]=[]
        if len(ids)<128:continue
        vector=target_vector(banks[key],len(days))
        for seed in SEEDS:
            with threadpool_limits(limits=1):state,rec=fit(rows,vector,ids,cut,head,seed)
            p=folder/'models'/f'{key}-{seed}.json.gz';write(p,state);states[str(p.relative_to(folder))]=sha(p)
            receipts[key].append(rec);count+=1
    write(folder/'training.json',dict(year=year,cutoff=days[-1],fits=count,selection_calls=0,
        y01_policy=old['y01_policy'],model_states=states,receipts=receipts,common_ids=ids.tolist(),
        labels_sha256=sha(folder/'labels.json.gz'),protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(training_sha256=sha(folder/'training.json'),train_sha256=sha(FOLDS/str(year)/'train.json'),
        cutoff=days[-1],current_test_read=False,registration_sha256=sha(STUDY/'registration.json')))
    print('B67 TRAIN',year,count,len(ids),flush=True)


def test(year):
    reg=read(STUDY/'registration.json');reads=install_guard(year,'test');verify(reg);folder=STUDY/'folds'/str(year)
    tr=read(folder/'training.json');seal=read(folder/'seal.json')
    assert sha(folder/'training.json')==seal['training_sha256'] and sha(STUDY/'registration.json')==seal['registration_sha256']
    old=bound(reg,SOURCE/'folds'/str(year)/'predictions.json.gz');days,prices=load_fold(year,include_test=True)
    first=days.index(f'{year-1}-12-31');last=days.index(f'{year}-12-31');assert old['dates']==days[first:last]
    rows=matrix(days,prices,'CAL44')[first:last];scores={}
    for head in HEADS:
        key=head['id']
        if not tr['receipts'][key]:scores[key]=[None]*len(rows);continue
        pred=[]
        for seed in SEEDS:
            p=folder/'models'/f'{key}-{seed}.json.gz';assert sha(p)==tr['model_states'][str(p.relative_to(folder))]
            pred.append(predict(read(p),rows))
        scores[key]=np.mean(pred,axis=0).tolist()
    write(folder/'predictions.json.gz',dict(dates=old['dates'],scores=combine(scores)))
    write(folder/'test-receipt.json',dict(seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),
        test_sha256=sha(FOLDS/str(year)/'test.json'),fitting_calls=0,selection_calls=0,validation_read=False,protected_reads=sorted(reads)))
    print('B67 TEST',year,flush=True)


def assemble(reg):
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    bank=load_bank(SOURCE,days,lambda p:bound(reg,p),2025);scores={s:[None]*len(days) for s in (*STREAMS,'ORIGINAL')}
    for y in range(2018,2026):
        folder=STUDY/'folds'/str(y);tr=read(folder/'training.json');seal=read(folder/'seal.json');receipt=read(folder/'test-receipt.json')
        assert sha(folder/'training.json')==seal['training_sha256'] and sha(folder/'seal.json')==receipt['seal_sha256']
        assert sha(folder/'predictions.json.gz')==receipt['predictions_sha256'] and tr['y01_policy']==bank['policies']['Y01'][y]
        f=read(folder/'predictions.json.gz');old=bound(reg,PREVIOUS/'folds'/str(y)/'predictions.json.gz')
        oldseal=bound(reg,PREVIOUS/'folds'/str(y)/'seal.json');oldrec=bound(reg,PREVIOUS/'folds'/str(y)/'test-receipt.json')
        assert oldseal['registration_sha256']==sha(PREVIOUS/'registration.json')
        assert oldrec['seal_sha256']==sha(PREVIOUS/'folds'/str(y)/'seal.json') and oldrec['predictions_sha256']==sha(PREVIOUS/'folds'/str(y)/'predictions.json.gz')
        assert f['dates']==old['dates']
        for key,vals in {**f['scores'],'ORIGINAL':old['scores']['ALL_D2_HUBER']}.items():
            for d,val in zip(f['dates'],vals,strict=True):scores[key][where[d]]=val
    return days,prices,bank,scores


def targets(values,recipe):
    days,prices,bank,scores=values;n=recipe['id']
    if recipe['kind']=='LEGACY' and n in ('T12','Y01'):
        old=next(r for r in OLD_RECIPES if r['id']==n)
        return old_targets((days,prices,{'AVERAGE':bank,'POST':bank},None),old)
    stream=recipe['stream'] if recipe['kind']=='MODEL' else 'ORIGINAL'
    fraction=recipe['fraction'] if recipe['kind']=='MODEL' else (.25 if n=='Q04' else .5)
    return component(days,prices,bank['scores'],bank['policies'],bank['flags'],scores[stream],fraction,'MODEL')


def replay():
    reg=read(STUDY/'registration.json');reads=install_guard(2025,'replay');verify(reg);values=assemble(reg);days,prices=values[:2];out=[]
    for recipe in RECIPES:
        target,allowed=targets(values,recipe);ss={};audits={};failures={}
        for case in CASES:
            try:a=run_account(days,prices,target,case,{},end='2025-12-31',role='target_replay',entry_permission=allowed,annual_settlement=False)
            except ValueError as exc:failures[case]=dict(type=type(exc).__name__,message=str(exc));continue
            audits[case]=audit(a,days,prices,target,CASES[case],BORROW[case],{},allowed,False)
            if recipe['kind']=='LEGACY':
                b,n=LEGACY[recipe['id']];assert a==bound(reg,b/'accounts'/n/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a);ss[case]=a['summary']
        dd=max((s['max_drawdown_pct'] for s in ss.values()),default=None)
        passed=not failures and len(ss)==4 and ss['STRESS']['return_pct']>=10000 and dd<35
        out.append(dict(recipe=recipe,summaries=ss,audits=audits,failures=failures,goal_gate=passed))
        print('B67 RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,validation_read=False,protected_reads=sorted(reads)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','train','test','replay','run'));p.add_argument('--year',type=int);a=p.parse_args()
    if a.command in ('train','test'):
        if a.year is None:p.error('--year required')
        globals()[a.command](a.year)
    elif a.command=='run':
        for y in range(2018,2026):
            for stage in ('train','test'):subprocess.run([sys.executable,'-m','lab.b67',stage,'--year',str(y)],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','lab.b67','replay'],cwd=ROOT,check=True)
    else:globals()[a.command]()
