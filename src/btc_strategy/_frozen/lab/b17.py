"""Constant-dimension mining group ablations with unchanged risk and clocks."""
import argparse
import itertools
import subprocess
import sys
from importlib.metadata import version
from threadpoolctl import threadpool_limits
from .io import ROOT,read,write,sha
from .b17_io import STUDY,UPSTREAM,CONTROL_IDS,FOLDS,FEATURES,install_guard,load_fold,load_features
from .mining_models import tune,infer
from .mining_features import LAGS
from .mining_ablation import ablate,ARMS
from .b16 import desired
from .tree_stability import SEEDS as TREE_SEEDS
from .tree_factors import matrix,PROFILES as TREE_PROFILES
from .sgd import matured
from .margin_walkforward import run_account,CASES,BORROW
from .margin_walkforward_audit import audit

MODELS=[dict(id=f'EXTRA_{kind}_L{lag}',family='EXTRA',kind=kind,lag=lag,horizon=60)
        for kind,lag in itertools.product(ARMS,LAGS)]
REUSED=[f'EXTRA_MINER_L{lag}'for lag in LAGS]
RECIPES=[dict(id=f'A{i+1:02}',mode=mode,model=m['id'],family='EXTRA',kind=m['kind'],lag=m['lag'])
         for i,(m,mode)in enumerate(itertools.product(MODELS,('PURE','BLEND')))]
RECIPES += [dict(id=f'A{i+13:02}',mode=mode,model=f'EXTRA_MINER_L{lag}',family='EXTRA',
                 kind='ALL',lag=lag,control=f'M{i+13:02}')
            for i,(lag,mode)in enumerate(itertools.product(LAGS,('PURE','BLEND')))]
RECIPES += [dict(id='A17',mode='BASELINE',family='EXTRA',control='M18'),
            dict(id='A18',mode='EXACT',parent='U02',control='M19'),
            dict(id='A19',mode='EXACT',parent='U04',control='M20')]
SCORE_NAMES=[m['id']for m in MODELS]+REUSED+['MEAN_PATH36','MEAN_CAL44','BASE_TREE']


def verify():
    reg=read(STUDY/'registration.json')
    for name,digest in reg['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source changed: '+name)
    assert sha(FOLDS/'manifest.json')==reg['data_manifest_sha256']
    assert sha(FEATURES/'manifest.json')==reg['feature_manifest_sha256']
    assert sha(UPSTREAM/'registration.json')==reg['upstream']['registration.json']
    for name,v in reg['versions'].items():assert version(name)==v
    return reg


def upstream(reg,path):
    p=UPSTREAM/path
    if sha(p)!=reg['upstream'][path]:raise ValueError('parent seal changed')
    return read(p)


def freeze():
    # Retain original registered engine/model dependency hashes without opening any economic rows.
    old=read(UPSTREAM/'registration.json')
    names=[p for p in old['sources']if p.startswith('lab/')or p=='WALKFORWARD_AUTHORIZATION.md']
    assert all(sha(ROOT/p)==old['sources'][p]for p in names)
    names+=['lab/b17.py','lab/b17_io.py','lab/mining_ablation.py','tests/test_b17.py',
            'tools/verify_b17.py','studies/B17-mining-dimension-ablation/spec.md']
    sealed={'registration.json':sha(UPSTREAM/'registration.json')}
    for year in range(2018,2026):
        stem=f'folds/{year}/';seal=read(UPSTREAM/(stem+'seal.json'));receipt=read(UPSTREAM/(stem+'test-receipt.json'))
        sealed[stem+'seal.json']=sha(UPSTREAM/(stem+'seal.json'))
        sealed[stem+'training.json']=seal['training_sha256']
        sealed[stem+'test-receipt.json']=sha(UPSTREAM/(stem+'test-receipt.json'))
        sealed[stem+'predictions.json.gz']=receipt['predictions_sha256']
    for name in CONTROL_IDS:
        for case in CASES:
            path=f'accounts/{name}/{case}.json.gz';sealed[path]=sha(UPSTREAM/path)
    write(STUDY/'registration.json',dict(models=MODELS,reused_scores=REUSED,recipes=RECIPES,upstream=sealed,
        tree_seeds=TREE_SEEDS,tree_profiles=TREE_PROFILES['EXTRA'],new_member_fits_cap=1470,
        new_final_members_cap=294,final_account_cap=76,exact_control_accounts=28,
        sources={p:sha(ROOT/p)for p in names},
        data_manifest_sha256=sha(FOLDS/'manifest.json'),feature_manifest_sha256=sha(FEATURES/'manifest.json'),
        costs=CASES,financing=BORROW,
        versions={p:version(p)for p in ('scikit-learn','numpy','pandas','nautilus-trader','threadpoolctl')},
        target_return_pct=10000,max_drawdown_strict_pct=35,
        qualification='conditional reconstructed mining-state inputs; consumed history; not PIT certification'))
    print('B17 FROZEN',sha(STUDY/'registration.json'),flush=True)


def matrices(days,prices,records):
    base=matrix(days,prices,'CAL44')
    return {(kind,lag):ablate(base,records,kind,lag)for kind in ARMS for lag in LAGS}


def train(year):
    reads=install_guard(year,'train');reg=verify();folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve sealed fold')
    oldseal=upstream(reg,f'folds/{year}/seal.json');parent=upstream(reg,f'folds/{year}/training.json')
    assert oldseal['cutoff']==f'{year-1}-12-31'and not oldseal['current_test_read']
    days,prices=load_fold(year);records=load_features(year,days);cut=len(days)-1
    rows=matrices(days,prices,records);models={};fits=0;cold=[]
    for m in MODELS:
        try:
            ids=matured(cut,60);matured(int(ids[-120:-60][0]),60)
        except (ValueError,IndexError):cold.append(m['id']);continue
        with threadpool_limits(limits=1):members,receipt=tune(rows[m['kind'],m['lag']],prices,cut,m['family'])
        p=folder/f"models/{m['id']}.json.gz"
        write(p,dict(spec=m,members=members,receipt=receipt,cutoff=days[-1]))
        models[m['id']]=sha(p);fits+=receipt['model_fits']
        print('B17 MODEL',year,m['id'],'fits',fits,flush=True)
    write(folder/'training.json',dict(year=year,cutoff=days[-1],model_fits=fits,cold_models=cold,
        parent_policies={k:parent['parent_policies'][k]for k in ('U02','U04')},protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,model_sha256=models,
        train_sha256=sha(FOLDS/str(year)/'train.json'),feature_train_sha256=sha(FEATURES/str(year)/'train.json.gz'),
        training_sha256=sha(folder/'training.json'),registration_sha256=sha(STUDY/'registration.json')))
    print('B17 TRAIN SEALED',year,flush=True)


def test(year):
    reads=install_guard(year,'test');reg=verify();folder=STUDY/f'folds/{year}';seal=read(folder/'seal.json')
    assert not seal['current_test_read']and seal['cutoff']==f'{year-1}-12-31'
    assert sha(folder/'training.json')==seal['training_sha256']
    assert sha(STUDY/'registration.json')==seal['registration_sha256']
    assert sha(FOLDS/str(year)/'train.json')==seal['train_sha256']
    assert sha(FEATURES/str(year)/'train.json.gz')==seal['feature_train_sha256']
    models={}
    for name,digest in seal['model_sha256'].items():
        p=folder/f'models/{name}.json.gz';assert sha(p)==digest;models[name]=read(p)
    parent=upstream(reg,f'folds/{year}/predictions.json.gz')
    days,prices=load_fold(year,include_test=True);records=load_features(year,days,include_test=True)
    first,last=days.index(f'{year-1}-12-31'),days.index(f'{year}-12-31')
    assert parent['dates']==days[first:last]
    rows=matrices(days,prices,records)
    with threadpool_limits(limits=1):
        scores={m['id']:infer(models[m['id']]['members'],rows[m['kind'],m['lag']][first:last]).tolist()
                if m['id']in models else [None]*(last-first)for m in MODELS}
    scores.update({k:parent['scores'][k]for k in REUSED+['MEAN_PATH36','MEAN_CAL44','BASE_TREE']})
    write(folder/'predictions.json.gz',dict(dates=days[first:last],scores=scores))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        feature_test_sha256=sha(FEATURES/str(year)/'test.json.gz'),fitting_calls=0,
        protected_reads=sorted(reads),reserved_validation_read=False))
    print('B17 TEST FROZEN',year,flush=True)


def assemble():
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    scores={k:[None]*len(days)for k in SCORE_NAMES}
    policies={k:{}for k in ('U02','U04')};folds=[]
    for year in range(2018,2026):
        folder=STUDY/f'folds/{year}'
        seal,receipt,training=[read(folder/n)for n in ('seal.json','test-receipt.json','training.json')]
        assert sha(folder/'seal.json')==receipt['seal_sha256']
        assert sha(folder/'training.json')==seal['training_sha256']
        assert sha(folder/'predictions.json.gz')==receipt['predictions_sha256']
        forecast=read(folder/'predictions.json.gz')
        for name,values in forecast['scores'].items():
            for day,v in zip(forecast['dates'],values,strict=True):scores[name][where[day]]=v
        for name in policies:policies[name][year]=training['parent_policies'][name]
        folds.append(dict(year=year,model_fits=training['model_fits'],test_receipt_sha256=sha(folder/'test-receipt.json')))
    return days,prices,scores,policies,folds


def replay():
    reads=install_guard(2025,'replay');reg=verify();days,prices,scores,policies,folds=assemble();results=[]
    for recipe in RECIPES:
        name=recipe['id'];targets=desired(days,prices,scores,policies,recipe)
        summaries,audits,failures={},{},{}
        for case in CASES:
            try:account=run_account(days,prices,targets,case,{},end='2025-12-31',role='target_replay')
            except ValueError as e:
                if str(e)!='minimum notional makes registered trade infeasible':raise
                failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(account,days,prices,targets,CASES[case],BORROW[case],{})
            if 'control'in recipe:
                assert account==upstream(reg,f"accounts/{recipe['control']}/{case}.json.gz")
            write(STUDY/'accounts'/name/f'{case}.json.gz',account);summaries[case]=account['summary']
        passed=not failures and summaries['STRESS']['return_pct']>=10000 and max(s['max_drawdown_pct']for s in summaries.values())<35
        results.append(dict(id=name,recipe=recipe,status='FAILED'if failures else 'COMPLETE',
            summaries=summaries,audits=audits,failures=failures,historical_economic_gate=passed,
            qualification='conditional reconstructed inputs; not certified PIT or fresh OOS'))
        print('B17 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
        reserved_validation_read=False,qualification='conditional reconstructed mining-state inputs'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b17',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b17','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
