"""Direct LINEAR/Huber SGD activity controls, fixed STOP labels, annual fits and carry accounting."""
import argparse
import subprocess
import sys
from importlib.metadata import version
from threadpoolctl import threadpool_limits
from .io import ROOT,read,write,sha
from .b38_io import STUDY,UPSTREAM,CONTROL_IDS,FOLDS,FEATURES,install_guard,load_fold,load_activity
from .label_sgd import tune,infer,PROFILES,SEEDS,FAMILIES
from .execution_labels import records as label_records,target_vector
from .activity_factors import append_activity
from .b36 import RECIPES as OLD_RECIPES,targets_and_permissions as old_targets,SCORE_NAMES as OLD_SCORES
from .exit_coordinate import desired
from .sgd import matured
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

FEATURE_SPECS=[('PAD55','PAD55',7),('ACT55_L7','ACT55',7),('ACT55_L30','ACT55',30)]
MODELS=[dict(id=f'{family}_{name}',family=family,feature=name,group=group,lag=lag,label='STOP',horizon=60)
        for family in FAMILIES for name,group,lag in FEATURE_SPECS]
RECIPES=[dict(id=f'L{i+1:02}',mode='BLEND',model=m['id'],group=m['group'],lag=m['lag'],label='STOP',gate='POS1')
         for i,m in enumerate(MODELS)]
RECIPES += [dict(id=f'L{i+7:02}',mode='CONTROL',control=name) for i,name in enumerate(CONTROL_IDS)]
SOURCE_RECIPES={r['id']:r for r in OLD_RECIPES if r['id']in CONTROL_IDS}
SCORE_NAMES=[m['id']for m in MODELS]+list(OLD_SCORES)


def verify():
    reg=read(STUDY/'registration.json')
    for name,digest in reg['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source changed: '+name)
    assert sha(FOLDS/'manifest.json')==reg['data_manifest_sha256']
    assert sha(FEATURES/'manifest.json')==reg['feature_manifest_sha256']
    assert reg['models']==MODELS and reg['recipes']==RECIPES
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
    names+=['lab/b38.py','lab/b38_io.py','lab/label_sgd.py','tests/test_b38.py','tests/test_b36.py','tests/test_b25.py',
            'tools/verify_b38.py','tools/verify_b20.py','tools/verify_b36_source.py','lab/exit_coordinate.py','tools/network_activity_reference.py','tools/label_sgd_reference.py','studies/B38-activity-sgd-controls/spec.md']
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
    write(STUDY/'registration.json',dict(models=MODELS,recipes=RECIPES,upstream=sealed,
        seeds=SEEDS,profiles=PROFILES,new_member_fits_cap=756,
        new_final_members_cap=84,final_account_cap=56,exact_control_accounts=32,
        independent_label_records=10548,prescribed_replays=['L05'],
        sources={p:sha(ROOT/p)for p in names},
        data_manifest_sha256=sha(FOLDS/'manifest.json'),feature_manifest_sha256=sha(FEATURES/'manifest.json'),
        costs=CASES,financing=BORROW,
        versions={p:version(p)for p in ('scikit-learn','numpy','pandas','nautilus-trader','threadpoolctl','torch')},
        target_return_pct=10000,max_drawdown_strict_pct=35,
        qualification='conditional network activity vintage; consumed history; not PIT certification'))
    print('B38 FROZEN',sha(STUDY/'registration.json'),flush=True)


def matrices(days,prices,records):
    pad=append_activity(days,prices,records,7,'PAD55')
    assert (pad==append_activity(days,prices,records,30,'PAD55')).all()
    return {name:pad if group=='PAD55' else append_activity(days,prices,records,lag,group) for name,group,lag in FEATURE_SPECS}


def train(year):
    reads=install_guard(year,'train');reg=verify();folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve sealed fold')
    oldseal=upstream(reg,f'folds/{year}/seal.json');parent=upstream(reg,f'folds/{year}/training.json')
    assert oldseal['cutoff']==f'{year-1}-12-31'and not oldseal['current_test_read']
    policy=parent['y01_policy']
    days,prices=load_fold(year);records=load_activity(year,days);cut=len(days)-1
    rows=matrices(days,prices,records);models={};fits=0;cold=[];banks={};label_hashes={}
    for m in MODELS:
        try:
            ids=matured(cut,60);matured(int(ids[-120:-60][0]),60)
        except (ValueError,IndexError):cold.append(m['id']);continue
        if m['label']not in banks:
            bank=label_records(days,prices,cut,m['label']);path=folder/f"labels/{m['label']}.json.gz"
            write(path,bank);label_hashes[m['label']]=sha(path);banks[m['label']]=target_vector(bank,len(days))
        with threadpool_limits(limits=1):members,receipt=tune(rows[m['feature']],banks[m['label']],cut,m['family'])
        p=folder/f"models/{m['id']}.json.gz"
        write(p,dict(spec=m,members=members,receipt=receipt,cutoff=days[-1],label_sha256=label_hashes[m['label']]))
        models[m['id']]=sha(p);fits+=receipt['model_fits']
        print('B38 MODEL',year,m['id'],'fits',fits,flush=True)
    write(folder/'training.json',dict(year=year,cutoff=days[-1],model_fits=fits,cold_models=cold,
        parent_policies={k:parent['parent_policies'][k]for k in ('U02','U04')},y01_policy=policy,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,model_sha256=models,label_sha256=label_hashes,
        train_sha256=sha(FOLDS/str(year)/'train.json'),feature_train_sha256=sha(FEATURES/str(year)/'train.json.gz'),
        training_sha256=sha(folder/'training.json'),registration_sha256=sha(STUDY/'registration.json')))
    print('B38 TRAIN SEALED',year,flush=True)


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
        assert models[name]['label_sha256']==seal['label_sha256'][models[name]['spec']['label']]
    parent=upstream(reg,f'folds/{year}/predictions.json.gz')
    days,prices=load_fold(year,include_test=True);records=load_activity(year,days,include_test=True)
    first,last=days.index(f'{year-1}-12-31'),days.index(f'{year}-12-31')
    assert parent['dates']==days[first:last]
    rows=matrices(days,prices,records)
    with threadpool_limits(limits=1):
        scores={m['id']:infer(models[m['id']]['members'],rows[m['feature']][first:last]).tolist()
                if m['id']in models else [None]*(last-first)for m in MODELS}
    scores.update({k:parent['scores'][k]for k in OLD_SCORES})
    write(folder/'predictions.json.gz',dict(dates=days[first:last],scores=scores))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        feature_test_sha256=sha(FEATURES/str(year)/'test.json.gz'),fitting_calls=0,
        protected_reads=sorted(reads),reserved_validation_read=False))
    print('B38 TEST FROZEN',year,flush=True)


def assemble():
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    scores={k:[None]*len(days)for k in SCORE_NAMES}
    policies={k:{}for k in ('U02','U04','Y01')};folds=[]
    for year in range(2018,2026):
        folder=STUDY/f'folds/{year}'
        seal,receipt,training=[read(folder/n)for n in ('seal.json','test-receipt.json','training.json')]
        assert sha(folder/'seal.json')==receipt['seal_sha256']
        assert sha(folder/'training.json')==seal['training_sha256']
        assert sha(folder/'predictions.json.gz')==receipt['predictions_sha256']
        forecast=read(folder/'predictions.json.gz')
        for name,values in forecast['scores'].items():
            for day,v in zip(forecast['dates'],values,strict=True):scores[name][where[day]]=v
        for name in ('U02','U04'):policies[name][year]=training['parent_policies'][name]
        policies['Y01'][year]=training['y01_policy']
        folds.append(dict(year=year,model_fits=training['model_fits'],test_receipt_sha256=sha(folder/'test-receipt.json')))
    return days,prices,scores,policies,folds


def new_score(scores,recipe):
    values=scores[recipe['model']]
    if recipe['mode']=='BLEND':
        return [None if x is None or y is None else .5*(x+y)
                for x,y in zip(values,scores['BASE_TREE'],strict=True)]
    assert recipe['mode']=='PURE'
    return values


def targets_and_permissions(days,prices,scores,policies,recipe):
    if recipe['mode']=='CONTROL':
        return old_targets(days,prices,scores,policies,SOURCE_RECIPES[recipe['control']])
    values=new_score(scores,recipe)
    return desired(days,prices,values,policies['Y01'])


def replay():
    reads=install_guard(2025,'replay');reg=verify();days,prices,scores,policies,folds=assemble();results=[]
    for recipe in RECIPES:
        name=recipe['id'];targets,entry=targets_and_permissions(days,prices,scores,policies,recipe)
        summaries,audits,failures={},{},{}
        for case in CASES:
            try:account=run_account(days,prices,targets,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as e:
                if str(e)!='minimum notional makes registered trade infeasible':raise
                failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(account,days,prices,targets,CASES[case],BORROW[case],{},entry,False)
            if 'control'in recipe:
                assert account==upstream(reg,f"accounts/{recipe['control']}/{case}.json.gz")
            write(STUDY/'accounts'/name/f'{case}.json.gz',account);summaries[case]=account['summary']
        passed=not failures and summaries['STRESS']['return_pct']>=10000 and max(s['max_drawdown_pct']for s in summaries.values())<35
        results.append(dict(id=name,recipe=recipe,status='FAILED'if failures else 'COMPLETE',
            summaries=summaries,audits=audits,failures=failures,historical_economic_gate=passed,
            qualification='conditional reconstructed inputs; not certified PIT or fresh OOS'))
        print('B38 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
        reserved_validation_read=False,qualification='conditional network activity vintage; fixed carry policy'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b38',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b38','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
