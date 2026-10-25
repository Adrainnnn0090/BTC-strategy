"""Matched original and short-specific payoff learners with fixed entry gates."""
import argparse
import subprocess
import sys
from importlib.metadata import version
from threadpoolctl import threadpool_limits
from .io import ROOT, read, write, sha
from .b51_io import STUDY, UPSTREAM, CONTROL_IDS, FOLDS, install_guard, load_fold
from . import short_payoff, short_payoff_models, execution_labels
from .short_payoff_overlay import GATES, targets_and_permissions as new_targets
from .tree_factors import matrix
from .b47 import SCORE_NAMES as OLD_SCORES, RECIPES as OLD_RECIPES, targets_and_permissions as old_targets
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

MODELS = [dict(id=f'{arch}_{kind}', architecture=arch, label=kind, features='CAL44', horizon=60)
          for kind in ('STOP', 'SHORT_NET') for arch in ('EXTRA', 'HUBER')]
RECIPES = [dict(id=f'S{2*i+j+1:02}', mode='POST_COLD', gate=gate, fraction=fraction)
           for i, gate in enumerate(GATES) for j, fraction in enumerate((.5, .75))]
RECIPES += [dict(id=f'S{i+13:02}', mode='CONTROL', control=n) for i, n in enumerate(CONTROL_IDS)]
SCORE_NAMES = [m['id'] for m in MODELS]+list(OLD_SCORES)
SOURCE_RECIPES = {r['id']: r for r in OLD_RECIPES}
PROBES = ('2018-01-15', '2019-06-15', '2023-11-15')


def verify():
    reg = read(STUDY/'registration.json')
    for name, digest in reg['sources'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('frozen B51 source changed: '+name)
    assert sha(FOLDS/'manifest.json') == reg['data_manifest_sha256']
    assert sha(UPSTREAM/'registration.json') == reg['upstream']['registration.json']
    assert reg['models'] == MODELS and reg['recipes'] == RECIPES and reg['native_label_probes'] == list(PROBES)
    for name, value in reg['versions'].items():
        assert version(name) == value
    for path,digest in reg['project_runtime_sources'].items():
        assert sha(path)==digest
    return reg


def upstream(reg, path):
    p = UPSTREAM/path
    if sha(p) != reg['upstream'][path]:
        raise ValueError('B51 parent seal changed')
    return read(p)


def freeze():
    import binance_robot.execution as project_execution
    import binance_robot.runner as project_runner
    assert not (STUDY/'folds').exists() and not (STUDY/'accounts').exists()
    old = read(UPSTREAM/'registration.json')
    names = [p for p in old['sources'] if p.startswith('lab/') or p == 'WALKFORWARD_AUTHORIZATION.md']
    assert all(sha(ROOT/p) == old['sources'][p] for p in names)
    names += ['lab/b51.py', 'lab/b51_io.py', 'lab/short_payoff.py', 'lab/short_payoff_models.py',
              'lab/short_payoff_overlay.py', 'lab/label_sgd.py', 'lab/label_trees.py',
              'tools/short_payoff_reference.py', 'tools/label_sgd_reference.py', 'tools/verify_b20.py',
              'tools/verify_b51.py', 'tests/test_b51_labels.py', 'tests/test_b51_models.py',
              'tests/test_b51_overlay.py', 'tests/test_b51_roles.py', 'tests/test_b45.py',
              'studies/B51-short-specific-payoff/spec.md', 'studies/B51-short-specific-payoff/economic-spec.md',
              'studies/B51-short-specific-payoff/preparation-seal.json']
    sealed = {'registration.json': sha(UPSTREAM/'registration.json')}
    for year in range(2018, 2026):
        stem = f'folds/{year}/'
        seal = read(UPSTREAM/(stem+'seal.json')); receipt = read(UPSTREAM/(stem+'test-receipt.json'))
        sealed[stem+'seal.json'] = sha(UPSTREAM/(stem+'seal.json'))
        sealed[stem+'training.json'] = seal['training_sha256']
        sealed[stem+'test-receipt.json'] = sha(UPSTREAM/(stem+'test-receipt.json'))
        sealed[stem+'predictions.json.gz'] = receipt['predictions_sha256']
    for name in CONTROL_IDS:
        for case in CASES:
            path = f'accounts/{name}/{case}.json.gz'; sealed[path] = sha(UPSTREAM/path)
    write(STUDY/'registration.json', dict(models=MODELS, recipes=RECIPES, upstream=sealed,
          sources={p: sha(ROOT/p) for p in names}, data_manifest_sha256=sha(FOLDS/'manifest.json'),
          versions={p: version(p) for p in ('scikit-learn','numpy','pandas','nautilus-trader','threadpoolctl','torch')},
          new_member_fits_cap=742, new_final_members_cap=126, independently_checked_label_records=21096,
          usable_training_samples_per_label=10520, final_account_cap=64, exact_control_accounts=16,
          prescribed_replays=['S12'], native_label_probes=list(PROBES),
          costs=CASES, financing=BORROW, short_risk=short_payoff.RISK,
          target_return_pct=10000, max_drawdown_strict_pct=35,
          project_runtime_sources={m.__file__:sha(m.__file__)for m in (project_execution,project_runner)},
          qualification='matched auxiliary short net payoff labels; consumed history; modeled margin financing'))
    print('B51 FROZEN', sha(STUDY/'registration.json'), flush=True)


def train(year):
    reads = install_guard(year, 'train'); reg = verify(); folder = STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():
        raise ValueError('preserve sealed B51 fold')
    seal = upstream(reg, f'folds/{year}/seal.json'); parent = upstream(reg, f'folds/{year}/training.json')
    assert seal['cutoff'] == parent['cutoff'] == f'{year-1}-12-31' and not seal['current_test_read']
    days, prices = load_fold(year); cut = len(days)-1
    rows = matrix(days, prices, 'CAL44'); models = {}; labels = {}; selections = {}; fits = 0; cold = []
    try:
        short_payoff_models.plan(days, cut)
    except (ValueError, IndexError):
        assert year == 2018
        cold = [m['id'] for m in MODELS]
    else:
        for kind in ('STOP', 'SHORT_NET'):
            bank = short_payoff.records(days,prices,cut) if kind == 'SHORT_NET' else execution_labels.records(days,prices,cut,'STOP')
            target = short_payoff.target_vector(bank,len(days)) if kind == 'SHORT_NET' else execution_labels.target_vector(bank,len(days))
            path = folder/f'labels/{kind}.json.gz'; write(path,bank); labels[kind] = sha(path)
            for m in [s for s in MODELS if s['label'] == kind]:
                with threadpool_limits(limits=1):
                    members, receipt = short_payoff_models.tune(days, rows, target, cut, m['architecture'], kind)
                path = folder/f"models/{m['id']}.json.gz"
                write(path,dict(spec=m,members=members,cutoff=days[-1],label_sha256=labels[kind]))
                models[m['id']] = sha(path); fits += receipt['model_fits']
                selection = folder/f"selection/{m['id']}.json.gz"
                write(selection,receipt); selections[m['id']] = sha(selection)
                print('B51 MODEL',year,m['id'],'fits',fits,flush=True)
    write(folder/'training.json',dict(year=year,cutoff=days[-1],model_fits=fits,cold_models=cold,
          parent_policies=parent['parent_policies'],y01_policy=parent['y01_policy'],protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(year=year,cutoff=days[-1],current_test_read=False,model_sha256=models,label_sha256=labels,selection_sha256=selections,
          training_sha256=sha(folder/'training.json'),train_sha256=sha(FOLDS/str(year)/'train.json'),
          registration_sha256=sha(STUDY/'registration.json')))
    print('B51 TRAIN SEALED',year,flush=True)


def test(year):
    reads = install_guard(year,'test'); reg = verify(); folder = STUDY/f'folds/{year}'
    seal = read(folder/'seal.json')
    assert not seal['current_test_read'] and seal['cutoff'] == f'{year-1}-12-31'
    assert seal['registration_sha256'] == sha(STUDY/'registration.json')
    assert seal['training_sha256'] == sha(folder/'training.json')
    assert seal['train_sha256'] == sha(FOLDS/str(year)/'train.json')
    parent_seal = upstream(reg,f'folds/{year}/seal.json'); parent_receipt = upstream(reg,f'folds/{year}/test-receipt.json')
    assert parent_receipt['seal_sha256'] == reg['upstream'][f'folds/{year}/seal.json']
    assert parent_receipt['predictions_sha256'] == reg['upstream'][f'folds/{year}/predictions.json.gz']
    assert parent_seal['train_sha256'] == seal['train_sha256'] and not parent_receipt['reserved_validation_read']
    parent = upstream(reg,f'folds/{year}/predictions.json.gz')
    days, prices = load_fold(year,include_test=True); first = days.index(f'{year-1}-12-31'); last = days.index(f'{year}-12-31')
    assert parent['dates'] == days[first:last]
    rows = matrix(days,prices,'CAL44'); scores = {}
    for m in MODELS:
        name = m['id']
        if name not in seal['model_sha256']:
            scores[name] = [None]*(last-first); continue
        path = folder/f'models/{name}.json.gz'; assert sha(path) == seal['model_sha256'][name]
        model = read(path); assert model['label_sha256'] == seal['label_sha256'][m['label']]
        with threadpool_limits(limits=1):
            scores[name] = short_payoff_models.infer(model['members'],rows[first:last],m['architecture']).tolist()
    scores.update({k:parent['scores'][k] for k in OLD_SCORES})
    write(folder/'predictions.json.gz',dict(dates=days[first:last],scores=scores,short_flags=parent['short_flags']))
    write(folder/'test-receipt.json',dict(year=year,seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),
          test_sha256=sha(FOLDS/str(year)/'test.json'),fitting_calls=0,protected_reads=sorted(reads),reserved_validation_read=False))
    print('B51 TEST FROZEN',year,flush=True)


def assemble():
    days,prices = load_fold(2025,include_test=True); where = {d:i for i,d in enumerate(days)}
    scores = {k:[None]*len(days) for k in SCORE_NAMES}
    policies = {k:{} for k in ('U02','U04','Y01')}; folds = []
    flags = {k:[False]*len(days) for k in ('bear','negative20','available')}
    for year in range(2018,2026):
        folder = STUDY/f'folds/{year}'
        seal,receipt,training = [read(folder/n) for n in ('seal.json','test-receipt.json','training.json')]
        assert receipt['seal_sha256'] == sha(folder/'seal.json')
        assert seal['training_sha256'] == sha(folder/'training.json')
        assert receipt['predictions_sha256'] == sha(folder/'predictions.json.gz')
        forecast = read(folder/'predictions.json.gz')
        for name,values in forecast['scores'].items():
            for day,value in zip(forecast['dates'],values,strict=True): scores[name][where[day]] = value
        for day,bear,momentum in zip(forecast['dates'],forecast['short_flags']['bear'],forecast['short_flags']['negative20'],strict=True):
            i = where[day]; flags['bear'][i] = bear; flags['negative20'][i] = momentum; flags['available'][i] = True
        for name in ('U02','U04'): policies[name][year] = training['parent_policies'][name]
        policies['Y01'][year] = training['y01_policy']
        folds.append(dict(year=year,model_fits=training['model_fits'],test_receipt_sha256=sha(folder/'test-receipt.json')))
    return days,prices,scores,policies,flags,folds


def targets_and_permissions(days,prices,scores,policies,flags,recipe):
    if recipe['mode'] == 'CONTROL':
        return old_targets(days,prices,scores,policies,flags,SOURCE_RECIPES[recipe['control']])
    return new_targets(days,prices,scores,policies,flags,recipe['fraction'],recipe['gate'])


def replay():
    reads = install_guard(2025,'replay'); reg = verify(); days,prices,scores,policies,flags,folds = assemble(); results = []
    for recipe in RECIPES:
        targets,entry = targets_and_permissions(days,prices,scores,policies,flags,recipe)
        summaries,audits,failures = {},{},{}
        for case in CASES:
            try:
                account = run_account(days,prices,targets,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as exc:
                if str(exc) != 'minimum notional makes registered trade infeasible': raise
                failures[case] = dict(type=type(exc).__name__,message=str(exc)); continue
            audits[case] = audit(account,days,prices,targets,CASES[case],BORROW[case],{},entry,False)
            if 'control' in recipe:
                assert account == upstream(reg,f"accounts/{recipe['control']}/{case}.json.gz")
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',account); summaries[case] = account['summary']
        passed = not failures and summaries['STRESS']['return_pct'] >= 10000 and max(s['max_drawdown_pct'] for s in summaries.values()) < 35
        results.append(dict(id=recipe['id'],recipe=recipe,status='FAILED' if failures else 'COMPLETE',summaries=summaries,
              audits=audits,failures=failures,historical_economic_gate=passed,qualification='conditional consumed history; auxiliary label/portfolio exit mismatch'))
        print('B51 RESULT',recipe['id'],round(summaries['STRESS']['return_pct'],2) if 'STRESS' in summaries else failures,
              round(max(s['max_drawdown_pct'] for s in summaries.values()),2) if summaries else None,passed,flush=True)
    write(STUDY/'results.json',dict(results=results,folds=folds,protected_reads=sorted(reads),reserved_validation_read=False))


def run():
    for year in range(2018,2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b51',stage,'--year',str(year)],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','lab.b51','replay'],cwd=ROOT,check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command',choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year',type=int,choices=range(2018,2026)); args = parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None: parser.error('--year required')
        globals()[args.command](args.year)
    else: globals()[args.command]()
