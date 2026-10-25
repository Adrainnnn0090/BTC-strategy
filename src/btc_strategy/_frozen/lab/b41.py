"""Fixed direct-model averaging with immutable annual parent forecasts and policies."""
import argparse
import subprocess
import sys
from datetime import date,timedelta
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .b41_io import STUDY,UPSTREAM,CONTROL_IDS,FOLDS,FEATURES,install_guard,load_fold
from .fixed_activity_average import PAIRS,average_record
from .b40 import RECIPES as OLD_RECIPES,targets_and_permissions as old_targets,SCORE_NAMES as OLD_SCORES
from .exit_coordinate import desired
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

RECIPES=[dict(id=f'T{i+1:02}',mode='BLEND',model=p['id'],gate='POS1') for i,p in enumerate(PAIRS)]
RECIPES+=[dict(id=f'T{i+7:02}',mode='CONTROL',control=n) for i,n in enumerate(CONTROL_IDS)]
SOURCE_RECIPES={r['id']:r for r in OLD_RECIPES}
SCORE_NAMES=[p['id'] for p in PAIRS]+list(OLD_SCORES)


def verify():
    reg=read(STUDY/'registration.json')
    for name,digest in reg['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source changed: '+name)
    assert sha(FOLDS/'manifest.json')==reg['data_manifest_sha256']
    assert sha(FEATURES/'manifest.json')==reg['feature_manifest_sha256']
    assert sha(UPSTREAM/'registration.json')==reg['upstream']['registration.json']
    assert reg['pairs']==PAIRS and reg['recipes']==RECIPES
    for name,v in reg['versions'].items():assert version(name)==v
    return reg


def upstream(reg,path):
    p=UPSTREAM/path
    if sha(p)!=reg['upstream'][path]:raise ValueError('parent seal changed')
    return read(p)


def freeze():
    old=read(UPSTREAM/'registration.json')
    names=[p for p in old['sources'] if p.startswith('lab/') or p=='WALKFORWARD_AUTHORIZATION.md']
    assert all(sha(ROOT/p)==old['sources'][p] for p in names)
    names+=['lab/b41.py','lab/b41_io.py','lab/fixed_activity_average.py','tests/test_b41.py',
        'tools/verify_b41.py','studies/B41-activity-fixed-average/spec.md']
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
    write(STUDY/'registration.json',dict(pairs=PAIRS,recipes=RECIPES,upstream=sealed,
        sources={p:sha(ROOT/p) for p in names},versions=old['versions'],
        data_manifest_sha256=old['data_manifest_sha256'],feature_manifest_sha256=old['feature_manifest_sha256'],
        new_model_fits=0,new_selection_calls=0,final_account_cap=128,exact_control_accounts=104,
        prescribed_replays=['T05'],costs=CASES,financing=BORROW,target_return_pct=10000,max_drawdown_strict_pct=35,
        scalar_score_tolerance=2e-15,qualification='fixed model average; conditional sources; consumed history'))
    print('B41 FROZEN',sha(STUDY/'registration.json'),flush=True)


def train(year):
    reads=install_guard(year,'train');reg=verify();folder=STUDY/f'folds/{year}';stem=f'folds/{year}/'
    if (folder/'seal.json').exists():raise ValueError('preserve sealed fold')
    seal=upstream(reg,stem+'seal.json');parent=upstream(reg,stem+'training.json')
    assert seal['cutoff']==parent['cutoff']==f'{year-1}-12-31' and not seal['current_test_read']
    assert seal['training_sha256']==reg['upstream'][stem+'training.json']
    assert seal['registration_sha256']==reg['upstream']['registration.json']
    write(folder/'training.json',dict(year=year,cutoff=seal['cutoff'],model_fits=0,selection_calls=0,
        parent_policies=parent['parent_policies'],y01_policy=parent['y01_policy'],protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=seal['cutoff'],current_test_read=False,
        train_sha256=seal['train_sha256'],feature_train_sha256=seal['feature_train_sha256'],
        parent_seal_sha256=reg['upstream'][stem+'seal.json'],training_sha256=sha(folder/'training.json'),
        registration_sha256=sha(STUDY/'registration.json')))
    print('B41 POLICY SEALED',year,flush=True)


def test(year):
    reads=install_guard(year,'test');reg=verify();folder=STUDY/f'folds/{year}';stem=f'folds/{year}/'
    seal=read(folder/'seal.json')
    assert sha(folder/'training.json')==seal['training_sha256']
    assert sha(STUDY/'registration.json')==seal['registration_sha256']
    assert seal['cutoff']==f'{year-1}-12-31' and not seal['current_test_read']
    source_seal=upstream(reg,stem+'seal.json');receipt=upstream(reg,stem+'test-receipt.json')
    assert receipt['seal_sha256']==seal['parent_seal_sha256']==reg['upstream'][stem+'seal.json']
    assert receipt['predictions_sha256']==reg['upstream'][stem+'predictions.json.gz']
    assert source_seal['train_sha256']==seal['train_sha256'] and source_seal['feature_train_sha256']==seal['feature_train_sha256']
    assert receipt['fitting_calls']==receipt['selection_calls']==0 and not receipt['reserved_validation_read']
    record=upstream(reg,stem+'predictions.json.gz');start=date(year-1,12,31);stop=date(year,12,31)
    assert record['dates']==[(start+timedelta(days=i)).isoformat() for i in range((stop-start).days)]
    scores=average_record(record);scores.update({k:record['scores'][k] for k in OLD_SCORES})
    write(folder/'predictions.json.gz',dict(dates=record['dates'],scores=scores))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=receipt['test_sha256'],
        feature_test_sha256=receipt['feature_test_sha256'],fitting_calls=0,selection_calls=0,
        protected_reads=sorted(reads),reserved_validation_read=False))
    print('B41 TEST FROZEN',year,flush=True)


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
        print('B41 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
        reserved_validation_read=False,qualification='fixed model average; consumed history; conditional source'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b41',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b41','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
