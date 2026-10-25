"""Nine fixed relative-price learners with matched padding and two cold-short wrappers."""
import argparse
import subprocess
import sys
from importlib.metadata import version
from threadpoolctl import threadpool_limits
from .io import ROOT,read,write,sha
from .b49_io import STUDY,UPSTREAM,CONTROL_IDS,FOLDS,FEATURES,install_guard,load_fold,load_cross
from . import label_trees,stock_direct
from .label_trees import PROFILES
from .b49_source import STUDY as SOURCE_STUDY
from .tree_stability import SEEDS
from .execution_labels import records as label_records,target_vector
from .cross_market_factors import append_cross
from .bear_short_overlay import overlay
from .short_trailing import with_short_trailing
from .b47 import RECIPES as OLD_RECIPES,targets_and_permissions as old_targets,SCORE_NAMES as OLD_SCORES
from .exit_coordinate import desired
from .sgd import matured
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

FEATURE_SPECS=[('PAD53','PAD53',7),('REL53_L7','REL53',7),('REL53_L30','REL53',30)]
MODELS=[dict(id=f'{arch}_{name}',architecture=arch,family='EXTRA' if arch=='EXTRA' else stock_direct.family(arch,'SQUARE'),
             loss='SQUARE',feature=name,group=group,lag=lag,label='STOP',horizon=60)
        for arch in ('EXTRA','LINEAR','MLP8') for name,group,lag in FEATURE_SPECS]
RECIPES=[dict(id=f'X{2*i+j+1:02}',mode='CROSS_COLD',model=m['id'],architecture=m['architecture'],
             group=m['group'],lag=m['lag'],fraction=fraction) for i,m in enumerate(MODELS) for j,fraction in enumerate((.5,.75))]
RECIPES += [dict(id=f'X{i+19:02}',mode='CONTROL',control=n) for i,n in enumerate(CONTROL_IDS)]
SOURCE_RECIPES={r['id']:r for r in OLD_RECIPES if r['id']in CONTROL_IDS}
SCORE_NAMES=[m['id']for m in MODELS]+list(OLD_SCORES)


def verify():
    reg=read(STUDY/'registration.json')
    for name,digest in reg['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source changed: '+name)
    assert sha(FOLDS/'manifest.json')==reg['data_manifest_sha256']
    assert sha(FEATURES/'manifest.json')==reg['feature_manifest_sha256']
    assert reg['models']==MODELS and reg['recipes']==RECIPES
    assert sha(STUDY/'preparation-registration.json')==reg['preparation_registration_sha256']
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
    names+=['lab/b49.py','lab/b49_io.py','lab/cross_market_factors.py','lab/b49_source.py','lab/stock_direct.py',
        'tests/test_b49.py','tests/test_b45.py','tools/verify_b49.py','tools/verify_b20.py','tools/cross_market_reference.py',
        'tools/activity_mlp_reference.py','tools/label_sgd_reference.py','tools/prepare_b49.py','tools/verify_b49_source.py',
        'studies/B49-cross-market-models/spec.md']
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
        tree_seeds=SEEDS,tree_profiles=PROFILES,direct_seeds=stock_direct.SEEDS,direct_profiles=stock_direct.PROFILES,new_member_fits_cap=1491,
        new_final_members_cap=231,final_account_cap=92,exact_control_accounts=20,
        independent_label_records=10548,prescribed_replays=['X18'],
        sources={p:sha(ROOT/p)for p in names},
        data_manifest_sha256=sha(FOLDS/'manifest.json'),feature_manifest_sha256=sha(FEATURES/'manifest.json'),
        preparation_registration_sha256=sha(STUDY/'preparation-registration.json'),
        costs=CASES,financing=BORROW,
        versions={p:version(p)for p in ('scikit-learn','numpy','pandas','nautilus-trader','threadpoolctl','torch')},
        target_return_pct=10000,max_drawdown_strict_pct=35,
        qualification='conditional cross-market source vintages; consumed history; not PIT certification'))
    print('B49 FROZEN',sha(STUDY/'registration.json'),flush=True)


def matrices(days,prices,records):
    pad=append_cross(days,prices,records,7,'PAD53')
    assert (pad==append_cross(days,prices,records,30,'PAD53')).all()
    return {name:pad if group=='PAD53' else append_cross(days,prices,records,lag,group) for name,group,lag in FEATURE_SPECS}


def train(year):
    reads=install_guard(year,'train');reg=verify();folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve sealed fold')
    oldseal=upstream(reg,f'folds/{year}/seal.json');parent=upstream(reg,f'folds/{year}/training.json')
    assert oldseal['cutoff']==f'{year-1}-12-31'and not oldseal['current_test_read']
    policy=parent['y01_policy']
    days,prices=load_fold(year);records=load_cross(year,days);cut=len(days)-1
    rows=matrices(days,prices,records);models={};fits=0;cold=[];banks={};label_hashes={}
    for m in MODELS:
        try:
            ids=matured(cut,60);matured(int(ids[-120:-60][0]),60)
        except (ValueError,IndexError):cold.append(m['id']);continue
        if m['label']not in banks:
            bank=label_records(days,prices,cut,m['label']);path=folder/f"labels/{m['label']}.json.gz"
            write(path,bank);label_hashes[m['label']]=sha(path);banks[m['label']]=target_vector(bank,len(days))
        with threadpool_limits(limits=1):
            if m['architecture']=='EXTRA':members,receipt=label_trees.tune(rows[m['feature']],banks[m['label']],cut,m['label'])
            else:members,receipt=stock_direct.tune(rows[m['feature']],banks[m['label']],cut,m['architecture'],m['loss'])
        p=folder/f"models/{m['id']}.json.gz"
        write(p,dict(spec=m,members=members,receipt=receipt,cutoff=days[-1],label_sha256=label_hashes[m['label']]))
        models[m['id']]=sha(p);fits+=receipt['model_fits']
        print('B49 MODEL',year,m['id'],'fits',fits,flush=True)
    write(folder/'training.json',dict(year=year,cutoff=days[-1],model_fits=fits,cold_models=cold,
        parent_policies={k:parent['parent_policies'][k]for k in ('U02','U04')},y01_policy=policy,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,model_sha256=models,label_sha256=label_hashes,
        train_sha256=sha(FOLDS/str(year)/'train.json'),feature_train_sha256=sha(FEATURES/str(year)/'train.json.gz'),
        training_sha256=sha(folder/'training.json'),registration_sha256=sha(STUDY/'registration.json')))
    print('B49 TRAIN SEALED',year,flush=True)


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
    days,prices=load_fold(year,include_test=True);records=load_cross(year,days,include_test=True)
    first,last=days.index(f'{year-1}-12-31'),days.index(f'{year}-12-31')
    assert parent['dates']==days[first:last]
    rows=matrices(days,prices,records)
    with threadpool_limits(limits=1):
        scores={m['id']:(label_trees.infer(models[m['id']]['members'],rows[m['feature']][first:last]) if m['architecture']=='EXTRA' else stock_direct.infer(models[m['id']]['members'],rows[m['feature']][first:last],m['architecture'])).tolist()
                if m['id']in models else [None]*(last-first)for m in MODELS}
    scores.update({k:parent['scores'][k]for k in OLD_SCORES})
    write(folder/'predictions.json.gz',dict(dates=days[first:last],scores=scores,short_flags=parent['short_flags']))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        feature_test_sha256=sha(FEATURES/str(year)/'test.json.gz'),fitting_calls=0,
        protected_reads=sorted(reads),reserved_validation_read=False))
    print('B49 TEST FROZEN',year,flush=True)


def assemble():
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    scores={k:[None]*len(days)for k in SCORE_NAMES}
    policies={k:{}for k in ('U02','U04','Y01')};folds=[];flags={k:[False]*len(days) for k in ('bear','negative20','available')}
    for year in range(2018,2026):
        folder=STUDY/f'folds/{year}'
        seal,receipt,training=[read(folder/n)for n in ('seal.json','test-receipt.json','training.json')]
        assert sha(folder/'seal.json')==receipt['seal_sha256']
        assert sha(folder/'training.json')==seal['training_sha256']
        assert sha(folder/'predictions.json.gz')==receipt['predictions_sha256']
        forecast=read(folder/'predictions.json.gz')
        for name,values in forecast['scores'].items():
            for day,v in zip(forecast['dates'],values,strict=True):scores[name][where[day]]=v
        for day,bear,momentum in zip(forecast['dates'],forecast['short_flags']['bear'],forecast['short_flags']['negative20'],strict=True):
            j=where[day];flags['bear'][j]=bear;flags['negative20'][j]=momentum;flags['available'][j]=True
        for name in ('U02','U04'):policies[name][year]=training['parent_policies'][name]
        policies['Y01'][year]=training['y01_policy']
        folds.append(dict(year=year,model_fits=training['model_fits'],test_receipt_sha256=sha(folder/'test-receipt.json')))
    return days,prices,scores,policies,flags,folds


def targets_and_permissions(days,prices,scores,policies,flags,recipe):
    if recipe['mode']=='CONTROL':return old_targets(days,prices,scores,policies,flags,SOURCE_RECIPES[recipe['control']])
    replaced={**scores,'CAL44_STOP':scores[recipe['model']]}
    targets,entry=overlay(days,prices,replaced,policies,flags,dict(scope='COLD_ONLY',fraction=recipe['fraction'],entry_filter='NEG20'))
    return with_short_trailing(targets,entry)


def replay():
    reads=install_guard(2025,'replay');reg=verify();days,prices,scores,policies,flags,folds=assemble();results=[]
    for recipe in RECIPES:
        name=recipe['id'];targets,entry=targets_and_permissions(days,prices,scores,policies,flags,recipe)
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
        print('B49 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
        reserved_validation_read=False,qualification='conditional cross-market price factors; fixed carry policy'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b49',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b49','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
