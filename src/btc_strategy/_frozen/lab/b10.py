"""Annual seed-calendar-stability models, evaluated through unchanged native hard-position accounts."""
import argparse
import itertools
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .b10_io import STUDY,UPSTREAM,TREES,FOLDS,install_guard,load_fold
from .tree_factors import predict,PROFILES
from .tree_stability import tune,matrix,GROUPS,SEEDS,ensemble_scores
from .b09 import targets,RISK
from .sgd import matured
from .sgd import infer
from .b05 import forecast_year,desired_targets,RECIPES as B05_RECIPES,policy

from .margin_walkforward import run_account,CASES,BORROW
from .margin_walkforward_audit import audit

MODELS=[dict(id=f'EXTRA_{g}_H60_S{s}',family='EXTRA',group=g,horizon=60,seed=s)
        for g,s in itertools.product(GROUPS,SEEDS)]
RECIPES=[dict(id=f'K{i+1:02}',model=m['id'],threshold=0.,mode='ENTRY')for i,m in enumerate(MODELS)]
RECIPES += [dict(id=f'K{i+29:02}',model='MEAN_'+g,threshold=0.,mode='ENTRY')for i,g in enumerate(GROUPS)]
CONTROL='K33'
MATCHES={'K07':'P29','K14':'P37','K21':'P45'}


def verify():
    r=read(STUDY/'registration.json')
    for name,digest in r['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source differs: '+name)
    if sha(FOLDS/'manifest.json')!=r['data_manifest_sha256']:raise ValueError('input manifest changed')
    for name,expected in r['versions'].items():
        if version(name)!=expected:raise ValueError('dependency version changed')
    return r


def freeze():
    names=['lab/b10.py','lab/b10_io.py','lab/tree_factors.py','lab/tree_stability.py','lab/b09_io.py','lab/b09.py','lab/b05.py','lab/sgd.py',
           'lab/signals.py','lab/io.py','lab/native.py','lab/audit.py','lab/search.py','lab/walkforward_io.py',
           'lab/margin_walkforward.py','lab/margin_walkforward_audit.py','tests/test_b10.py','tools/verify_b10.py',
           'WALKFORWARD_AUTHORIZATION.md','studies/B10-seed-calendar-stability/spec.md','studies/B10-seed-calendar-stability/sources.md']
    controls={}
    for year in range(2018,2026):
        p=UPSTREAM/f'folds/{year}/seal.json'
        seal=read(p)
        controls[str(year)]=dict(seal_sha256=sha(p),
                                model_sha256=seal['model_sha256'].get('HUBER_PRICE20_H60'))
    retained={}
    for year in range(2018,2026):
        p=TREES/f'folds/{year}/seal.json';seal=read(p)
        retained[str(year)]=dict(seal_sha256=sha(p),models={
            g:seal['model_sha256'].get(f'EXTRA_{g}_H60')for g in GROUPS if g!='PLACEBO44'})
    write(STUDY/'registration.json',dict(models=MODELS,recipes=RECIPES,control=CONTROL,
                                         model_member_fits_cap=875,final_accounts_cap=132,
                                         new_final_states=175,reused_final_states=21,seeds=SEEDS,retained=retained,matches=MATCHES,
                                         profiles=PROFILES["EXTRA"],
                                         sources={p:sha(ROOT/p)for p in names},controls=controls,
                                         data_manifest_sha256=sha(FOLDS/'manifest.json'),
                                         versions={p:version(p)for p in ('scikit-learn','numpy','pandas','nautilus-trader')},
                                         target_return_pct=10000,max_drawdown_strict_pct=35,
                                         risk=RISK,costs=CASES,financing=BORROW,
                                         scope='seed stability and predetermined calendar phase control; consumed history'))
    print('B10 FROZEN',sha(STUDY/'registration.json'),flush=True)


def train(year):
    reads=install_guard(year,'train');reg=verify()
    folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve existing fold')
    days,prices=load_fold(year);cut=len(days)-1
    rows={g:matrix(days,prices,g) for g in GROUPS};models={};fits=0;cold=[];reused=[]
    for m in MODELS:
        try:
            ids=matured(cut,m['horizon'])
            matured(int(ids[-120:-60][0]),m['horizon'])
        except (ValueError,IndexError):
            cold.append(m['id']);continue
        source=None
        if m['seed']==1701 and m['group']!='PLACEBO44':
            meta=reg['retained'][str(year)]
            if sha(TREES/f'folds/{year}/seal.json')!=meta['seal_sha256']:raise ValueError('retained seal changed')
            source=TREES/f"folds/{year}/models/EXTRA_{m['group']}_H60.json.gz"
            if sha(source)!=meta['models'][m['group']]:raise ValueError('retained model changed')
            old=read(source)
            if old['cutoff']!=days[-1]:raise ValueError('retained model cutoff differs')
            state,receipt=old['state'],old['receipt'];reused.append(m['id'])
        else:
            state,receipt=tune(rows[m['group']],prices,cut,m['seed']);fits+=5
        p=folder/f"models/{m['id']}.json.gz"
        write(p,dict(spec=m,state=state,receipt=receipt,cutoff=days[-1],
                     reused_source=None if source is None else str(source.relative_to(ROOT)),
                     reused_sha256=None if source is None else sha(source)))
        models[m['id']]=sha(p)
        print('B10 MODEL',year,m['id'],'fits',fits,flush=True)
    write(folder/'training.json',dict(year=year,cutoff=days[-1],model_fits=fits,cold_models=cold,reused_models=reused,
                                      protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,model_sha256=models,
                                  train_sha256=sha(FOLDS/str(year)/'train.json'),
                                  training_sha256=sha(folder/'training.json'),
                                  registration_sha256=sha(STUDY/'registration.json')))
    print('B10 TRAIN SEALED',year,'fits',fits,flush=True)


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
    scores.update(ensemble_scores(scores))
    scores[CONTROL]=infer(control['members'],rows['PRICE20'][first:last]).tolist()if control else [None]*(last-first)
    write(folder/'predictions.json.gz',dict(dates=days[first:last],scores=scores))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
                                          predictions_sha256=sha(folder/'predictions.json.gz'),
                                          test_sha256=sha(FOLDS/str(year)/'test.json'),fitting_calls=0,
                                          protected_reads=sorted(reads),reserved_validation_read=False))
    print('B10 TEST FROZEN',year,flush=True)


def replay():
    reads=install_guard(2025,'replay');verify()
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    scores={m['id']:[None]*len(days)for m in MODELS}
    scores.update({'MEAN_'+g:[None]*len(days)for g in GROUPS});scores[CONTROL]=[None]*len(days);folds=[]
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
            if name in MATCHES and a!=read(TREES/'accounts'/MATCHES[name]/f'{case}.json.gz'):
                raise ValueError('retained tree control changed')
            write(STUDY/'accounts'/name/f'{case}.json.gz',a);summaries[case]=a['summary']
        passed=summaries['STRESS']['return_pct']>=10000 and max(s['max_drawdown_pct']for s in summaries.values())<35
        results.append(dict(id=name,recipe=recipe,summaries=summaries,audits=audits,target_pass=passed))
        print('B10 RESULT',name,round(summaries['STRESS']['return_pct'],2),
              round(max(s['max_drawdown_pct']for s in summaries.values()),2),passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
                                    reserved_validation_read=False,
                                    scope='native hard-position outcomes; all preregistered factor ablations reported'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b10',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b10','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
