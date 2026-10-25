"""Annual exit calibration exclusively from earlier frozen forecast folds."""
import argparse
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT,read,write,sha
from .b29_io import STUDY,UPSTREAM,CONTROL_IDS,FOLDS,install_guard,load_fold
from .exit_coordinate import PARENTS,SPACE,IDENTITY,PASSES,MAX_EVALUATIONS,MIN_PRIOR_FOLDS,MIN_VALID_DECISIONS
from .exit_coordinate import config_id,parent_score,prior_scores,patch_policy,desired,objective,search
from .b22 import RECIPES as OLD_RECIPES,targets_and_permissions as old_targets,SCORE_NAMES
from .carry_native import run_account,CASES,BORROW
from .carry_audit import audit

RECIPES=[dict(id=f'Y{i+1:02}',mode='ADAPTED',parent=p)for i,p in enumerate(PARENTS)]
RECIPES += [dict(id=f'Y{i+3:02}',mode='CONTROL',control=p)for i,p in enumerate(CONTROL_IDS)]
SOURCE_RECIPES={r['id']:r for r in OLD_RECIPES if r['id']in CONTROL_IDS}


def verify():
    reg=read(STUDY/'registration.json')
    for name,digest in reg['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError('frozen source changed: '+name)
    assert sha(FOLDS/'manifest.json')==reg['data_manifest_sha256']
    assert sha(UPSTREAM/'registration.json')==reg['upstream']['registration.json']
    assert reg['recipes']==RECIPES and reg['coordinate_space']=={k:list(v)for k,v in SPACE.items()}
    for name,v in reg['versions'].items():assert version(name)==v
    return reg


def upstream(reg,path):
    p=UPSTREAM/path
    if sha(p)!=reg['upstream'][path]:raise ValueError('parent seal changed')
    return read(p)


def freeze():
    old=read(UPSTREAM/'registration.json')
    names=[p for p in old['sources']if p.startswith('lab/')or p=='WALKFORWARD_AUTHORIZATION.md']
    assert all(sha(ROOT/p)==old['sources'][p]for p in names)
    names+=['lab/b29.py','lab/b29_io.py','lab/exit_coordinate.py','tests/test_exit_coordinate.py','tests/test_b29.py',
            'tools/verify_b29.py','studies/B29-prior-forecast-exits/spec.md']
    sealed={'registration.json':sha(UPSTREAM/'registration.json')}
    for year in range(2018,2026):
        stem=f'folds/{year}/';seal=read(UPSTREAM/(stem+'seal.json'));receipt=read(UPSTREAM/(stem+'test-receipt.json'))
        sealed[stem+'seal.json']=sha(UPSTREAM/(stem+'seal.json'));sealed[stem+'training.json']=seal['training_sha256']
        sealed[stem+'test-receipt.json']=sha(UPSTREAM/(stem+'test-receipt.json'));sealed[stem+'predictions.json.gz']=receipt['predictions_sha256']
    for name in CONTROL_IDS:
        for case in CASES:
            path=f'accounts/{name}/{case}.json.gz';sealed[path]=sha(UPSTREAM/path)
    write(STUDY/'registration.json',dict(recipes=RECIPES,upstream=sealed,coordinate_space=SPACE,passes=PASSES,
        max_evaluations_per_parent_fold=MAX_EVALUATIONS,min_prior_forecast_folds=MIN_PRIOR_FOLDS,
        min_valid_decisions=MIN_VALID_DECISIONS,first_eligible_year=2021,new_model_fits=0,
        training_config_evaluations_cap=210,training_account_attempts_cap=840,final_account_cap=20,
        exact_control_accounts=12,prescribed_replays=['Y02'],sources={p:sha(ROOT/p)for p in names},
        data_manifest_sha256=sha(FOLDS/'manifest.json'),costs=CASES,financing=BORROW,
        versions={p:version(p)for p in ('numpy','pandas','nautilus-trader','scikit-learn','threadpoolctl')},
        target_return_pct=10000,max_drawdown_strict_pct=35,
        qualification='prior frozen forecasts; existing conditional sources and consumed design history'))
    print('B29 FROZEN',sha(STUDY/'registration.json'),flush=True)


def history(year,reg):
    days,prices=load_fold(year);forecasts={};policies={};receipts={}
    for prior in range(2018,year+1):
        seal=upstream(reg,f'folds/{prior}/seal.json');training=upstream(reg,f'folds/{prior}/training.json')
        assert seal['cutoff']==training['cutoff']==f'{prior-1}-12-31'and not seal['current_test_read']
        policies[prior]=training['parent_policies']['U02']
        if prior==year:continue
        receipt=upstream(reg,f'folds/{prior}/test-receipt.json');forecast=upstream(reg,f'folds/{prior}/predictions.json.gz')
        assert receipt['seal_sha256']==sha(UPSTREAM/f'folds/{prior}/seal.json')
        assert receipt['predictions_sha256']==sha(UPSTREAM/f'folds/{prior}/predictions.json.gz')
        forecasts[prior]=forecast;receipts[str(prior)]=sha(UPSTREAM/f'folds/{prior}/test-receipt.json')
    return days,prices,forecasts,policies,receipts


def train(year):
    reads=install_guard(year,'train');reg=verify();folder=STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():raise ValueError('preserve sealed fold')
    days,prices,forecasts,policies,receipts=history(year,reg);choices={};counts=dict(configs=0,attempts=0,complete=0,rejected=0)
    for parent in PARENTS:
        score,eligibility=prior_scores(days,forecasts,year,parent);hashes={}
        def evaluate(config):
            key=config_id(config);path=folder/'calibration'/parent/key
            targets,entry=desired(days,prices,score,{y:patch_policy(p,config)for y,p in policies.items()})
            summaries,audits,failures,accounts={},{},{},{}
            for case in CASES:
                counts['attempts']+=1
                try:a=run_account(days,prices,targets,case,{},end=days[-1],role='fold_train',entry_permission=entry,annual_settlement=False)
                except ValueError as exc:
                    if str(exc)!='minimum notional makes registered trade infeasible':raise
                    failures[case]=dict(type=type(exc).__name__,message=str(exc));counts['rejected']+=1;continue
                audits[case]=audit(a,days,prices,targets,CASES[case],BORROW[case],{},entry,False)
                write(path/(case+'.json.gz'),a);accounts[case]=sha(path/(case+'.json.gz'))
                summaries[case]=a['summary'];counts['complete']+=1
            value=objective(summaries,failures)
            write(path/'candidate.json',dict(config=config,id=key,summaries=summaries,audits=audits,failures=failures,
                account_sha256=accounts,objective=value,training_start='2018-01-01',training_end=days[-1],parent=parent))
            hashes[key]=sha(path/'candidate.json');counts['configs']+=1
            print('B29 CALIBRATION',year,parent,key,'objective',value,flush=True)
            return value
        if eligibility['eligible']:
            result=search(evaluate)
        else:
            result=dict(selected_config=IDENTITY,selected_id=config_id(IDENTITY),selected_objective=None,
                fallback='INSUFFICIENT_PRIOR_FORECAST_HISTORY',trace=[],evaluated={},evaluation_order=[],evaluation_count=0)
        choices[parent]={**result,'eligibility':eligibility,'candidate_sha256':hashes}
        print('B29 SELECTED',year,parent,result['selected_config'],result['fallback'],flush=True)
    assert counts['configs']<=42 and counts['attempts']<=168
    current=upstream(reg,f'folds/{year}/training.json')
    write(folder/'training.json',dict(year=year,cutoff=days[-1],choices=choices,counts=counts,model_fits=0,
        parent_policies=current['parent_policies'],prior_test_receipt_sha256=receipts,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,
        training_sha256=sha(folder/'training.json'),train_sha256=sha(FOLDS/str(year)/'train.json'),
        registration_sha256=sha(STUDY/'registration.json')))


def test(year):
    reads=install_guard(year,'test');reg=verify();folder=STUDY/f'folds/{year}';seal=read(folder/'seal.json')
    assert not seal['current_test_read']and seal['cutoff']==f'{year-1}-12-31'
    assert sha(folder/'training.json')==seal['training_sha256']and sha(STUDY/'registration.json')==seal['registration_sha256']
    assert sha(FOLDS/str(year)/'train.json')==seal['train_sha256']
    parent=upstream(reg,f'folds/{year}/predictions.json.gz')
    days,prices=load_fold(year,True);first,last=days.index(f'{year-1}-12-31'),days.index(f'{year}-12-31')
    assert parent['dates']==days[first:last]
    write(folder/'predictions.json.gz',dict(dates=parent['dates'],scores={k:parent['scores'][k]for k in SCORE_NAMES}))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0,selection_calls=0,protected_reads=sorted(reads),reserved_validation_read=False))
    print('B29 TEST FROZEN',year,flush=True)


def assemble():
    days,prices=load_fold(2025,True);where={d:i for i,d in enumerate(days)};scores={k:[None]*len(days)for k in SCORE_NAMES}
    policies={k:{}for k in ('U02','U04')};choices={p:{}for p in PARENTS};folds=[]
    for year in range(2018,2026):
        folder=STUDY/f'folds/{year}'
        seal,receipt,training=[read(folder/n)for n in ('seal.json','test-receipt.json','training.json')]
        assert sha(folder/'seal.json')==receipt['seal_sha256']and sha(folder/'training.json')==seal['training_sha256']
        assert sha(folder/'predictions.json.gz')==receipt['predictions_sha256']
        forecast=read(folder/'predictions.json.gz')
        for name,values in forecast['scores'].items():
            for d,v in zip(forecast['dates'],values,strict=True):scores[name][where[d]]=v
        for name in policies:policies[name][year]=training['parent_policies'][name]
        for parent in PARENTS:choices[parent][year]=training['choices'][parent]['selected_config']
        folds.append(dict(year=year,counts=training['counts'],test_receipt_sha256=sha(folder/'test-receipt.json')))
    return days,prices,scores,policies,choices,folds


def targets_and_permissions(days,prices,scores,policies,choices,recipe):
    if recipe['mode']=='CONTROL':return old_targets(days,prices,scores,policies,SOURCE_RECIPES[recipe['control']])
    parent=recipe['parent'];selected={y:patch_policy(p,choices[parent][y])for y,p in policies['U02'].items()}
    return desired(days,prices,parent_score(scores,parent),selected)


def replay():
    reads=install_guard(2025,'replay');reg=verify();days,prices,scores,policies,choices,folds=assemble();results=[]
    for recipe in RECIPES:
        name=recipe['id'];targets,entry=targets_and_permissions(days,prices,scores,policies,choices,recipe)
        summaries,audits,failures={},{},{}
        for case in CASES:
            try:a=run_account(days,prices,targets,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as exc:
                if str(exc)!='minimum notional makes registered trade infeasible':raise
                failures[case]=dict(type=type(exc).__name__,message=str(exc));continue
            audits[case]=audit(a,days,prices,targets,CASES[case],BORROW[case],{},entry,False)
            if 'control'in recipe:assert a==upstream(reg,f"accounts/{recipe['control']}/{case}.json.gz")
            write(STUDY/'accounts'/name/(case+'.json.gz'),a);summaries[case]=a['summary']
        passed=not failures and summaries['STRESS']['return_pct']>=10000 and max(s['max_drawdown_pct']for s in summaries.values())<35
        results.append(dict(id=name,recipe=recipe,status='FAILED'if failures else 'COMPLETE',summaries=summaries,audits=audits,
            failures=failures,historical_economic_gate=passed,qualification='chronological calibration; consumed history'))
        print('B29 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    assert sum(f['counts']['configs']for f in folds)<=210 and sum(f['counts']['attempts']for f in folds)<=840
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),reserved_validation_read=False))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):subprocess.run([sys.executable,'-m','lab.b29',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b29','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','train','test','replay','run'))
    p.add_argument('--year',type=int,choices=range(2018,2026));args=p.parse_args()
    if args.command in ('train','test'):
        if args.year is None:p.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
