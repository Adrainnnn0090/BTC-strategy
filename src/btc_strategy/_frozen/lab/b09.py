"""Annual tree-path-calendar models, evaluated through unchanged native hard-position accounts."""
import argparse
import itertools
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .b09_io import STUDY,UPSTREAM,FOLDS,install_guard,load_fold
from .tree_factors import tune,predict,matrix,GROUPS,PROFILES,PATH_NAMES,CAL_NAMES
from .sgd import matured
from .sgd import infer
from .b05 import forecast_year,desired_targets,RECIPES as B05_RECIPES,policy
from .signals import Features
from .margin_walkforward import run_account,CASES,BORROW
from .margin_walkforward_audit import audit

MODELS=[dict(id=f'{family}_{group}_H{h}',family=family,group=group,horizon=h)
        for family,group,h in itertools.product(('SGB','EXTRA'),GROUPS,(20,60))]
RECIPES=[dict(id=f'P{i+1:02}',model=m['id'],threshold=t,mode=mode)
         for i,(m,t,mode) in enumerate(itertools.product(MODELS,(0.,.03),('ENTRY','DYNAMIC')))]
CONTROL='P49'
RISK=dict(long=dict(stop_loss=.15,take_profit=1.,cooldown_days=3,trailing_stop=.1,trail_arm=.5),
          short=dict(stop_loss=.12,take_profit=.5,cooldown_days=3,trailing_stop=0.,trail_arm=.1))


def targets(days,prices,scores,recipe):
    parents=Features(prices).targets(dict(family='BAND',params=dict(n=100,band=.03),risk=dict(vol_target=0.)))
    active,negative,current=False,0,None
    out=[]
    for i,(day,score) in enumerate(zip(days,scores,strict=True)):
        year=forecast_year(day)
        if current!=year:
            active,negative,current=False,0,year
        if score is None or not parents[i]['long']:
            active,negative=False,0
        else:
            negative=negative+1 if score<-.01 else 0
            if recipe['mode']=='DYNAMIC' and negative>=2:
                active=False
            elif not active and score>recipe['threshold']:
                active=True
        out.append(dict(direction=int(active),long_fraction=.8,short_fraction=0.,
                        policy_year=year,risk=RISK))
    return out


def verify():
    r=read(STUDY/'registration.json')
    for name,digest in r['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source differs: '+name)
    if sha(FOLDS/'manifest.json')!=r['data_manifest_sha256']:raise ValueError('input manifest changed')
    for name,expected in r['versions'].items():
        if version(name)!=expected:raise ValueError('dependency version changed')
    return r


def freeze():
    names=['lab/b09.py','lab/b09_io.py','lab/tree_factors.py','lab/b05.py','lab/sgd.py',
           'lab/signals.py','lab/io.py','lab/native.py','lab/audit.py','lab/search.py','lab/walkforward_io.py',
           'lab/margin_walkforward.py','lab/margin_walkforward_audit.py','tests/test_b09.py','tools/verify_b09.py',
           'WALKFORWARD_AUTHORIZATION.md','studies/B09-tree-path-calendar/spec.md','studies/B09-tree-path-calendar/sources.md']
    controls={}
    for year in range(2018,2026):
        p=UPSTREAM/f'folds/{year}/seal.json'
        seal=read(p)
        controls[str(year)]=dict(seal_sha256=sha(p),
                                model_sha256=seal['model_sha256'].get('HUBER_PRICE20_H60'))
    write(STUDY/'registration.json',dict(models=MODELS,recipes=RECIPES,control=CONTROL,
                                         model_member_fits_cap=420,final_accounts_cap=196,
                                         profiles=PROFILES,path_names=PATH_NAMES,calendar_names=CAL_NAMES,
                                         sources={p:sha(ROOT/p)for p in names},controls=controls,
                                         data_manifest_sha256=sha(FOLDS/'manifest.json'),
                                         versions={p:version(p)for p in ('scikit-learn','numpy','pandas','nautilus-trader')},
                                         target_return_pct=10000,max_drawdown_strict_pct=35,
                                         risk=RISK,costs=CASES,financing=BORROW,
                                         scope='stochastic trees; causal path and calendar ablations; consumed history'))
    print('B09 FROZEN',sha(STUDY/'registration.json'),flush=True)


def train(year):
    reads=install_guard(year,'train');verify()
    folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve existing fold')
    days,prices=load_fold(year);cut=len(days)-1
    rows={g:matrix(days,prices,g) for g in GROUPS};models={};fits=0;cold=[]
    for m in MODELS:
        try:
            ids=matured(cut,m['horizon'])
            matured(int(ids[-120:-60][0]),m['horizon'])
        except (ValueError,IndexError):
            cold.append(m['id']);continue
        state,receipt=tune(rows[m['group']],prices,cut,m['horizon'],m['family'])
        p=folder/f"models/{m['id']}.json.gz"
        write(p,dict(spec=m,state=state,receipt=receipt,cutoff=days[-1]))
        models[m['id']]=sha(p);fits+=5
        print('B09 MODEL',year,m['id'],'fits',fits,flush=True)
    write(folder/'training.json',dict(year=year,cutoff=days[-1],model_fits=fits,cold_models=cold,
                                      protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,model_sha256=models,
                                  train_sha256=sha(FOLDS/str(year)/'train.json'),
                                  training_sha256=sha(folder/'training.json'),
                                  registration_sha256=sha(STUDY/'registration.json')))
    print('B09 TRAIN SEALED',year,'fits',fits,flush=True)


def test(year):
    reads=install_guard(year,'test');reg=verify();folder=STUDY/f'folds/{year}'
    seal=read(folder/'seal.json')
    if seal['current_test_read']or seal['cutoff']!=f'{year-1}-12-31':raise ValueError('invalid seal clock')
    if sha(folder/'training.json')!=seal['training_sha256']or sha(STUDY/'registration.json')!=seal['registration_sha256']:
        raise ValueError('sealed training changed')
    if sha(FOLDS/str(year)/'train.json')!=seal['train_sha256']:raise ValueError('training file changed')
    models={}
    for name,digest in seal['model_sha256'].items():
        p=folder/f'models/{name}.json.gz'
        if sha(p)!=digest:raise ValueError('model changed')
        models[name]=read(p)
    meta=reg['controls'][str(year)];p=UPSTREAM/f'folds/{year}/seal.json'
    if sha(p)!=meta['seal_sha256']:raise ValueError('control seal changed')
    control=None
    if meta['model_sha256']:
        p=UPSTREAM/f'folds/{year}/models/HUBER_PRICE20_H60.json.gz'
        if sha(p)!=meta['model_sha256']:raise ValueError('control model changed')
        control=read(p)
    # The first current-year price access follows verification of all frozen models.
    days,prices=load_fold(year,include_test=True)
    rows={g:matrix(days,prices,g) for g in GROUPS}
    first,last=days.index(f'{year-1}-12-31'),days.index(f'{year}-12-31')
    scores={m['id']:predict(models[m['id']]['state'],rows[m['group']][first:last]).tolist()
            if m['id']in models else [None]*(last-first) for m in MODELS}
    scores[CONTROL]=infer(control['members'],rows['PRICE20'][first:last]).tolist()if control else [None]*(last-first)
    write(folder/'predictions.json.gz',dict(dates=days[first:last],scores=scores))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
                                          predictions_sha256=sha(folder/'predictions.json.gz'),
                                          test_sha256=sha(FOLDS/str(year)/'test.json'),fitting_calls=0,
                                          protected_reads=sorted(reads),reserved_validation_read=False))
    print('B09 TEST FROZEN',year,flush=True)


def replay():
    reads=install_guard(2025,'replay');verify()
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    scores={m['id']:[None]*len(days)for m in MODELS};scores[CONTROL]=[None]*len(days);folds=[]
    for year in range(2018,2026):
        folder=STUDY/f'folds/{year}'
        seal,receipt,training=[read(folder/n)for n in ('seal.json','test-receipt.json','training.json')]
        if sha(folder/'seal.json')!=receipt['seal_sha256']or sha(folder/'training.json')!=seal['training_sha256']:
            raise ValueError('fold chain changed')
        if sha(folder/'predictions.json.gz')!=receipt['predictions_sha256']:raise ValueError('forecast changed')
        forecast=read(folder/'predictions.json.gz')
        for name,values in forecast['scores'].items():
            for day,value in zip(forecast['dates'],values,strict=True):scores[name][where[day]]=value
        folds.append(dict(year=year,model_fits=training['model_fits'],test_receipt_sha256=sha(folder/'test-receipt.json')))
    results=[]
    for recipe in [*RECIPES,dict(id=CONTROL)]:
        name=recipe['id']
        if name==CONTROL:
            c=policy(B05_RECIPES[1],'HUBER_PRICE20_H60')
            desired=desired_targets(days,prices,{'HUBER_PRICE20_H60':scores[CONTROL]},
                                    {y:c for y in range(2018,2026)})
        else:desired=targets(days,prices,scores[recipe['model']],recipe)
        summaries,audits={},{}
        for case in CASES:
            a=run_account(days,prices,desired,case,{},end='2025-12-31',role='target_replay')
            audits[case]=audit(a,days,prices,desired,CASES[case],BORROW[case],{})
            if name==CONTROL and a!=read(UPSTREAM/'accounts/W02'/f'{case}.json.gz'):
                raise ValueError('matched control changed')
            write(STUDY/'accounts'/name/f'{case}.json.gz',a);summaries[case]=a['summary']
        passed=summaries['STRESS']['return_pct']>=10000 and max(s['max_drawdown_pct']for s in summaries.values())<35
        results.append(dict(id=name,recipe=recipe,summaries=summaries,audits=audits,target_pass=passed))
        print('B09 RESULT',name,round(summaries['STRESS']['return_pct'],2),
              round(max(s['max_drawdown_pct']for s in summaries.values()),2),passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
                                    reserved_validation_read=False,
                                    scope='native hard-position outcomes; all preregistered factor ablations reported'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b09',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b09','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
