"""Fixed entry-budget maps from strictly earlier frozen forecast distributions."""
import argparse
import itertools
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .b30_io import STUDY,UPSTREAM,CONTROL_IDS,FOLDS,install_guard,load_fold
from .forecast_rank import PARENTS,PARENT_SCORE,MAPS,MIN_SAMPLES,observations,fit,ranks,multipliers
from .exit_coordinate import parent_score
from .b29 import RECIPES as OLD_RECIPES,targets_and_permissions as old_targets,SCORE_NAMES as OLD_SCORES
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

RECIPES=[dict(id=f'P{i+1:02}',mode='RANK',parent=parent,method=method)
         for i,(parent,method)in enumerate(itertools.product(PARENTS,MAPS))]
RECIPES += [dict(id=f'P{i+7:02}',mode='CONTROL',parent=parent,control=parent)for i,parent in enumerate(CONTROL_IDS)]
SOURCE_RECIPES={r['id']:r for r in OLD_RECIPES if r['id']in CONTROL_IDS}
SCORE_NAMES=list(OLD_SCORES)


def verify():
    reg=read(STUDY/'registration.json')
    for name,digest in reg['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source changed: '+name)
    assert sha(FOLDS/'manifest.json')==reg['data_manifest_sha256']
    assert reg['recipes']==RECIPES and reg['parents']==list(PARENTS)and reg['maps']==list(MAPS)
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
    names+=['lab/b30.py','lab/b30_io.py','lab/forecast_rank.py','tests/test_b30.py',
            'tools/verify_b30.py','studies/B30-forecast-strength-sizing/spec.md']
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
    write(STUDY/'registration.json',dict(recipes=RECIPES,upstream=sealed,parents=PARENTS,maps=MAPS,minimum_samples=MIN_SAMPLES,
        new_return_model_fits=0,new_rank_fits_cap=12,rank_state_files=16,final_account_cap=36,exact_control_accounts=12,
        calibration_accounts=0,prescribed_replays=['P03'],
        sources={p:sha(ROOT/p)for p in names},
        data_manifest_sha256=sha(FOLDS/'manifest.json'),
        costs=CASES,financing=BORROW,
        versions={p:version(p)for p in ('scikit-learn','numpy','pandas','nautilus-trader','threadpoolctl')},
        target_return_pct=10000,max_drawdown_strict_pct=35,
        qualification='prior frozen forecast ranks; unchanged parent risk; consumed history'))
    print('B30 FROZEN',sha(STUDY/'registration.json'),flush=True)


def prior_forecasts(year,reg):
    forecasts={};receipts={}
    for prior in range(2018,year):
        seal=upstream(reg,f'folds/{prior}/seal.json');receipt=upstream(reg,f'folds/{prior}/test-receipt.json')
        assert seal['cutoff']==f'{prior-1}-12-31'and not seal['current_test_read']
        assert receipt['seal_sha256']==sha(UPSTREAM/f'folds/{prior}/seal.json')
        forecast=upstream(reg,f'folds/{prior}/predictions.json.gz')
        assert receipt['predictions_sha256']==sha(UPSTREAM/f'folds/{prior}/predictions.json.gz')
        forecasts[prior]=forecast;receipts[str(prior)]=sha(UPSTREAM/f'folds/{prior}/test-receipt.json')
    return forecasts,receipts


def train(year):
    reads=install_guard(year,'train');reg=verify();folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve sealed fold')
    oldseal=upstream(reg,f'folds/{year}/seal.json');parent=upstream(reg,f'folds/{year}/training.json')
    assert oldseal['cutoff']==f'{year-1}-12-31'and not oldseal['current_test_read']
    days,prices=load_fold(year);prior,receipts=prior_forecasts(year,reg)
    states={};samples={};active=0;counts={}
    for name in PARENTS:
        bank=observations(prior,year,name)
        if any(r['date']not in days for r in bank):raise ValueError('rank observations outside physical prefix')
        path=folder/f'samples/{name}.json.gz';write(path,bank);samples[name]=sha(path)
        state=dict(parent=name,**fit(bank,days[-1]),samples_sha256=samples[name])
        path=folder/f'ranks/{name}.json.gz';write(path,state);states[name]=sha(path)
        active+=state['active'];counts[name]=dict(observations=state['observation_count'],positive=state['positive_count'],active=state['active'])
    write(folder/'training.json',dict(year=year,cutoff=days[-1],return_model_fits=0,rank_fits=active,rank_counts=counts,
        prior_test_receipt_sha256=receipts,parent_policies=parent['parent_policies'],
        parent_choices={p:parent['choices'][p]['selected_config']for p in ('H03','H04')},protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,rank_sha256=states,sample_sha256=samples,
        train_sha256=sha(FOLDS/str(year)/'train.json'),training_sha256=sha(folder/'training.json'),
        registration_sha256=sha(STUDY/'registration.json')))
    print('B30 RANK SEALED',year,counts,flush=True)


def test(year):
    reads=install_guard(year,'test');reg=verify();folder=STUDY/f'folds/{year}';seal=read(folder/'seal.json')
    assert not seal['current_test_read']and seal['cutoff']==f'{year-1}-12-31'
    assert sha(folder/'training.json')==seal['training_sha256']and sha(STUDY/'registration.json')==seal['registration_sha256']
    assert sha(FOLDS/str(year)/'train.json')==seal['train_sha256']
    states={}
    for name,digest in seal['rank_sha256'].items():
        path=folder/f'ranks/{name}.json.gz';assert sha(path)==digest;states[name]=read(path)
        assert states[name]['samples_sha256']==seal['sample_sha256'][name]
    parent=upstream(reg,f'folds/{year}/predictions.json.gz');days,prices=load_fold(year,True)
    first,last=days.index(f'{year-1}-12-31'),days.index(f'{year}-12-31');assert parent['dates']==days[first:last]
    rank_values={name:ranks(states[name],parent_score(parent['scores'],PARENT_SCORE[name]))for name in PARENTS}
    write(folder/'predictions.json.gz',dict(dates=parent['dates'],scores={k:parent['scores'][k]for k in OLD_SCORES},ranks=rank_values))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0,selection_calls=0,protected_reads=sorted(reads),reserved_validation_read=False))
    print('B30 TEST FROZEN',year,flush=True)


def assemble():
    days,prices=load_fold(2025,include_test=True);where={d:i for i,d in enumerate(days)}
    scores={k:[None]*len(days)for k in SCORE_NAMES}
    policies={k:{}for k in ('U02','U04')};choices={p:{}for p in ('H03','H04')};rank_values={p:[None]*len(days)for p in PARENTS};folds=[]
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
        for name in choices:choices[name][year]=training['parent_choices'][name]
        for name,values in forecast['ranks'].items():
            for d,v in zip(forecast['dates'],values,strict=True):rank_values[name][where[d]]=v
        folds.append(dict(year=year,rank_fits=training['rank_fits'],test_receipt_sha256=sha(folder/'test-receipt.json')))
    return days,prices,scores,policies,choices,rank_values,folds


def targets_and_permissions(days,prices,scores,policies,choices,rank_values,recipe):
    targets,entry=old_targets(days,prices,scores,policies,choices,SOURCE_RECIPES[recipe['parent']])
    if recipe['mode']=='CONTROL':return targets,entry
    scale=multipliers(rank_values[recipe['parent']],recipe['method'])
    return [{**t,'long_fraction':t['long_fraction']*m}for t,m in zip(targets,scale,strict=True)],entry


def replay():
    reads=install_guard(2025,'replay');reg=verify();days,prices,scores,policies,choices,rank_values,folds=assemble();results=[]
    for recipe in RECIPES:
        name=recipe['id'];targets,entry=targets_and_permissions(days,prices,scores,policies,choices,rank_values,recipe)
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
        print('B30 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
        reserved_validation_read=False,qualification='prior-score ranks; entry-budget reductions only'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b30',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b30','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
