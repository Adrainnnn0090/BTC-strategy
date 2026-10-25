"""Fixed annual carry policies on original dated forecasts and entry-owned risks."""
import argparse
import itertools
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .b22_io import STUDY,UPSTREAM,CONTROL_IDS,FOLDS,install_guard,load_fold
from .b21 import RECIPES as OLD_RECIPES,targets_and_permissions as old_targets,SCORE_NAMES
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

RECIPES=[dict(id=f'H{i+1:02}',parent=parent,mode='CARRY',annual_settlement=False)
         for i,parent in enumerate(CONTROL_IDS)]
RECIPES += [dict(id=f'H{i+7:02}',parent=parent,mode='CONTROL',control=parent,annual_settlement=True)
            for i,parent in enumerate(CONTROL_IDS)]
SOURCE_RECIPES={r['id']:r for r in OLD_RECIPES if r['id']in CONTROL_IDS}


def verify():
    reg=read(STUDY/'registration.json')
    for name,digest in reg['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source changed: '+name)
    assert reg['recipes']==RECIPES
    assert sha(FOLDS/'manifest.json')==reg['data_manifest_sha256']
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
    names+=['lab/b22.py','lab/b22_io.py','lab/carry_native.py','lab/carry_audit.py','tests/test_b22.py','tests/test_b22_native.py',
            'tools/verify_b22.py','studies/B22-annual-carry/spec.md']
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
    write(STUDY/'registration.json',dict(recipes=RECIPES,upstream=sealed,
        new_member_fits=0,new_final_members=0,final_account_cap=48,exact_control_accounts=24,
        prescribed_replays=['H01','H06'],
        sources={p:sha(ROOT/p)for p in names},
        data_manifest_sha256=sha(FOLDS/'manifest.json'),
        costs=CASES,financing=BORROW,
        versions={p:version(p)for p in ('scikit-learn','numpy','pandas','nautilus-trader','threadpoolctl')},
        target_return_pct=10000,max_drawdown_strict_pct=35,
        qualification='explicit annual execution variant; original dated models; mining parents conditional; consumed history'))
    print('B22 FROZEN',sha(STUDY/'registration.json'),flush=True)


def train(year):
    reads=install_guard(year,'train');reg=verify();folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve sealed fold')
    old=upstream(reg,f'folds/{year}/seal.json');prior=upstream(reg,f'folds/{year}/training.json')
    assert old['cutoff']==prior['cutoff']==f'{year-1}-12-31'and not old['current_test_read']
    train_hash=sha(FOLDS/str(year)/'train.json');assert train_hash==old['train_sha256']
    write(folder/'training.json',dict(year=year,cutoff=old['cutoff'],model_fits=0,
        selection='fixed execution modes; no new selection',parent_policies=prior['parent_policies'],protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=old['cutoff'],current_test_read=False,
        training_sha256=sha(folder/'training.json'),train_sha256=train_hash,
        upstream_seal_sha256=sha(UPSTREAM/f'folds/{year}/seal.json'),registration_sha256=sha(STUDY/'registration.json')))
    print('B22 POLICY SEALED',year,flush=True)


def test(year):
    reads=install_guard(year,'test');reg=verify();folder=STUDY/f'folds/{year}';seal=read(folder/'seal.json')
    assert not seal['current_test_read']and seal['cutoff']==f'{year-1}-12-31'
    assert sha(folder/'training.json')==seal['training_sha256']
    assert sha(STUDY/'registration.json')==seal['registration_sha256']
    assert sha(FOLDS/str(year)/'train.json')==seal['train_sha256']
    parent=upstream(reg,f'folds/{year}/predictions.json.gz')
    days,prices=load_fold(year,include_test=True)
    first,last=days.index(f'{year-1}-12-31'),days.index(f'{year}-12-31')
    assert parent['dates']==days[first:last]
    write(folder/'predictions.json.gz',dict(dates=parent['dates'],scores={k:parent['scores'][k]for k in SCORE_NAMES}))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0,protected_reads=sorted(reads),reserved_validation_read=False))
    print('B22 FORECAST REUSED',year,flush=True)


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


def targets_and_permissions(days,prices,scores,policies,recipe):
    return old_targets(days,prices,scores,policies,SOURCE_RECIPES[recipe['parent']])


def replay():
    reads=install_guard(2025,'replay');reg=verify();days,prices,scores,policies,folds=assemble();results=[]
    for recipe in RECIPES:
        name=recipe['id'];targets,entry=targets_and_permissions(days,prices,scores,policies,recipe)
        summaries,audits,failures={},{},{}
        for case in CASES:
            try:account=run_account(days,prices,targets,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=recipe['annual_settlement'])
            except ValueError as e:
                if str(e)!='minimum notional makes registered trade infeasible':raise
                failures[case]=dict(type=type(e).__name__,message=str(e));continue
            audits[case]=audit(account,days,prices,targets,CASES[case],BORROW[case],{},entry,recipe['annual_settlement'])
            if 'control'in recipe:
                assert account==upstream(reg,f"accounts/{recipe['control']}/{case}.json.gz")
            write(STUDY/'accounts'/name/f'{case}.json.gz',account);summaries[case]=account['summary']
        passed=not failures and summaries['STRESS']['return_pct']>=10000 and max(s['max_drawdown_pct']for s in summaries.values())<35
        results.append(dict(id=name,recipe=recipe,status='FAILED'if failures else 'COMPLETE',
            summaries=summaries,audits=audits,failures=failures,historical_economic_gate=passed,
            qualification='conditional reconstructed inputs; not certified PIT or fresh OOS'))
        print('B22 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
        reserved_validation_read=False,qualification='fixed annual carry; conditional mining parents'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b22',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b22','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
