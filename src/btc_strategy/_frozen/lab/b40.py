"""Frozen annual architecture choice; no new fitting, labels or factor construction."""
import argparse
import subprocess
import sys
from datetime import date, timedelta
from importlib.metadata import version
from .io import ROOT, read, write, sha
from .b40_io import STUDY, UPSTREAM, LINEAR, PARENTS, CONTROL_IDS, FOLDS, FEATURES, install_guard, load_fold
from .architecture_choice import PAIRS, EPSILON, cutoff_index, eligible, select, route
from .b39 import RECIPES as OLD_RECIPES, targets_and_permissions as old_targets, SCORE_NAMES as OLD_SCORES
from .exit_coordinate import desired
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

RECIPES = [dict(id=f'Q{i+1:02}',mode='BLEND',model=p['id'],gate='POS1') for i,p in enumerate(PAIRS)]
RECIPES += [dict(id=f'Q{i+7:02}',mode='CONTROL',control=n) for i,n in enumerate(CONTROL_IDS)]
SOURCE_RECIPES = {r['id']:r for r in OLD_RECIPES}
SCORE_NAMES = [p['id'] for p in PAIRS]+list(OLD_SCORES)


def verify():
    reg = read(STUDY/'registration.json')
    for path,digest in reg['sources'].items():
        if sha(ROOT/path) != digest: raise ValueError('frozen source changed: '+path)
    assert sha(FOLDS/'manifest.json') == reg['data_manifest_sha256']
    assert sha(FEATURES/'manifest.json') == reg['feature_manifest_sha256']
    assert reg['pairs'] == PAIRS and reg['recipes'] == RECIPES and reg['epsilon'] == EPSILON
    for family,parent in PARENTS.items():
        assert sha(parent/'registration.json') == reg['parents'][family]['registration.json']
    for name,v in reg['versions'].items(): assert version(name) == v
    return reg


def parent_read(reg, family, path):
    p = PARENTS[family]/path
    if sha(p) != reg['parents'][family][path]: raise ValueError('parent seal changed')
    return read(p)


def upstream(reg, path):
    return parent_read(reg, 'neural', path)


def freeze():
    old = read(UPSTREAM/'registration.json')
    names = [p for p in old['sources'] if p.startswith('lab/') or p == 'WALKFORWARD_AUTHORIZATION.md']
    assert all(sha(ROOT/p) == old['sources'][p] for p in names)
    names += ['lab/b40.py','lab/b40_io.py','lab/architecture_choice.py','tests/test_b40.py',
              'tools/verify_b40.py','studies/B40-activity-architecture-choice/spec.md']
    parents = {}
    for family,parent in PARENTS.items():
        sealed = {'registration.json':sha(parent/'registration.json')}
        for year in range(2018,2026):
            stem = f'folds/{year}/'; seal = read(parent/(stem+'seal.json'))
            sealed[stem+'seal.json'] = sha(parent/(stem+'seal.json'))
            sealed[stem+'training.json'] = seal['training_sha256']
            for name,digest in seal['model_sha256'].items():
                sealed[stem+f'models/{name}.json.gz'] = digest
            if family == 'neural':
                receipt = read(parent/(stem+'test-receipt.json'))
                sealed[stem+'test-receipt.json'] = sha(parent/(stem+'test-receipt.json'))
                sealed[stem+'predictions.json.gz'] = receipt['predictions_sha256']
        if family == 'neural':
            for name in CONTROL_IDS:
                for case in CASES:
                    path = f'accounts/{name}/{case}.json.gz'; sealed[path] = sha(parent/path)
        parents[family] = sealed
    write(STUDY/'registration.json', dict(pairs=PAIRS,recipes=RECIPES,epsilon=EPSILON,parents=parents,
        sources={p:sha(ROOT/p) for p in names},versions=old['versions'],
        data_manifest_sha256=old['data_manifest_sha256'],feature_manifest_sha256=old['feature_manifest_sha256'],
        new_model_fits=0,annual_choices=48,eligible_choices=42,final_account_cap=104,exact_control_accounts=80,
        prescribed_replays=['Q05'],costs=CASES,financing=BORROW,target_return_pct=10000,max_drawdown_strict_pct=35,
        audit_scope='independent recorded-loss aggregation/ranking; no original inner-model refits'))
    print('B40 FROZEN',sha(STUDY/'registration.json'),flush=True)


def train(year):
    reads = install_guard(year,'train'); reg = verify(); folder = STUDY/f'folds/{year}'
    if (folder/'seal.json').exists(): raise ValueError('preserve sealed fold')
    stem = f'folds/{year}/'; cut = cutoff_index(year); seals = {}; parents = {}
    for family in PARENTS:
        seal = parent_read(reg,family,stem+'seal.json'); p = parent_read(reg,family,stem+'training.json')
        assert seal['cutoff'] == p['cutoff'] == f'{year-1}-12-31' and not seal['current_test_read']
        assert seal['training_sha256'] == reg['parents'][family][stem+'training.json']
        assert seal['registration_sha256'] == reg['parents'][family]['registration.json']
        seals[family] = seal; parents[family] = p
    for key in ('train_sha256','feature_train_sha256','label_sha256'):
        assert seals['linear'][key] == seals['neural'][key]
    for key in ('parent_policies','y01_policy'):
        assert parents['linear'][key] == parents['neural'][key]
    evidence = {}; choices = {}
    for pair in PAIRS:
        records = {}
        for family in PARENTS:
            name = pair[family]
            if eligible(cut):
                model = parent_read(reg,family,stem+f'models/{name}.json.gz')
                assert seals[family]['model_sha256'][name] == reg['parents'][family][stem+f'models/{name}.json.gz']
                assert model['cutoff'] == f'{year-1}-12-31' and model['spec']['id'] == name
                assert model['spec']['feature'] == pair['bank'] and model['spec']['label'] == 'STOP' and model['spec']['horizon'] == 60
                assert model['label_sha256'] == seals[family]['label_sha256']['STOP']
                records[family] = model['receipt']
            else:
                assert name not in seals[family]['model_sha256'] and name in parents[family]['cold_models']
                records[family] = None
        evidence[pair['id']] = select(records['linear'],records['neural'],cut,pair)
        choices[pair['id']] = evidence[pair['id']]['source_score']
    write(folder/'selection.json',evidence)
    selection_sha = sha(folder/'selection.json')
    write(folder/'training.json',dict(year=year,cutoff=f'{year-1}-12-31',model_fits=0,choices=choices,
        y01_policy=parents['neural']['y01_policy'],parent_policies=parents['neural']['parent_policies'],
        protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=f'{year-1}-12-31',current_test_read=False,
        train_sha256=seals['neural']['train_sha256'],feature_train_sha256=seals['neural']['feature_train_sha256'],
        parent_seal_sha256={f:reg['parents'][f][stem+'seal.json'] for f in PARENTS},
        training_sha256=sha(folder/'training.json'),selection_sha256=selection_sha,
        registration_sha256=sha(STUDY/'registration.json')))
    print('B40 TRAIN SEALED',year,flush=True)


def test(year):
    reads = install_guard(year,'test'); reg = verify(); folder = STUDY/f'folds/{year}'; stem = f'folds/{year}/'
    seal = read(folder/'seal.json'); training = read(folder/'training.json')
    assert sha(folder/'training.json') == seal['training_sha256']
    assert sha(STUDY/'registration.json') == seal['registration_sha256']
    assert not seal['current_test_read'] and seal['cutoff'] == training['cutoff'] == f'{year-1}-12-31'
    source_seal = upstream(reg,stem+'seal.json'); receipt = upstream(reg,stem+'test-receipt.json')
    assert receipt['seal_sha256'] == seal['parent_seal_sha256']['neural'] == reg['parents']['neural'][stem+'seal.json']
    assert receipt['predictions_sha256'] == reg['parents']['neural'][stem+'predictions.json.gz']
    assert source_seal['train_sha256'] == seal['train_sha256'] and source_seal['feature_train_sha256'] == seal['feature_train_sha256']
    assert receipt['fitting_calls'] == 0 and not receipt['reserved_validation_read']
    record = upstream(reg,stem+'predictions.json.gz')
    start = date(year-1,12,31); stop = date(year,12,31)
    assert record['dates'] == [(start+timedelta(days=i)).isoformat() for i in range((stop-start).days)]
    scores = route(record,training['choices']); scores.update({k:record['scores'][k] for k in OLD_SCORES})
    write(folder/'predictions.json.gz',dict(dates=record['dates'],scores=scores))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=receipt['test_sha256'],
        feature_test_sha256=receipt['feature_test_sha256'],fitting_calls=0,selection_calls=0,
        protected_reads=sorted(reads),reserved_validation_read=False))
    print('B40 TEST FROZEN',year,flush=True)


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
        print('B40 RESULT',name,round(summaries['STRESS']['return_pct'],2)if 'STRESS'in summaries else failures,
              round(max(s['max_drawdown_pct']for s in summaries.values()),2)if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),
        reserved_validation_read=False,qualification='prior-training architecture choice; consumed history; conditional source'))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b40',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b40','replay'],cwd=ROOT,check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026));args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None:parser.error('--year required')
        globals()[args.command](args.year)
    else:globals()[args.command]()
