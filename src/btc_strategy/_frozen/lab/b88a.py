"""Fixed original short-net label support, four loss summaries, P02 long fixed."""
import argparse, inspect, subprocess, sys
from importlib.metadata import version
import numpy as np
from threadpoolctl import threadpool_limits
from sklearn.ensemble import GradientBoostingRegressor
import sklearn.tree._tree as tree_binary
from .io import ROOT, read, write, sha
from .walkforward_io import FOLDS, load_fold
from .b88a_io import STUDY, UPSTREAM, LABELS, SOURCE, install_guard
from .b87 import RECIPES as OLD_RECIPES, assemble as old_assemble, targets as old_targets
from .short_loss_models import LOSSES, fit
from .boosted_stop import PROFILE
from .lagged_short import HEADS, target_vector
from .tree_stability import SEEDS
from .tree_factors import matrix, predict
from .b82 import bundle
from .price_trail_activation import frame
from .conditional_short import component
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

MODELS = [dict(id=s['id']+'_'+h['id'], spec=s, head=h) for s in LOSSES for h in HEADS]
RECIPES = [dict(id='S'+str(i+1).zfill(2), kind='IDENTITY' if i == 0 else 'MODEL', stream=s['id']) for i, s in enumerate(LOSSES)] + [dict(id=r['id'], kind='LEGACY') for r in OLD_RECIPES]
SOURCES = ('lab/b88a.py','lab/b88a_io.py','lab/short_loss_models.py','tools/verify_b88a.py','tests/test_b88a.py','notes/proposed-short-net-losses.md','notes/proposed-short-net-losses-plumbing.md','studies/B88A-short-net-loss-families/spec.md','studies/B88A-short-net-loss-families/checks.json')


def freeze():
    p = read(UPSTREAM/'registration.json'); v = read(UPSTREAM/'verification.json'); lp = read(LABELS/'verification.json')
    assert v['status'] == lp['status'] == 'PASS' and v['exact_controls'] == 44 and lp['independent_labels'] == 21082 and not v['validation_read'] and not lp['validation_read']
    assert v['results_sha256'] == sha(UPSTREAM/'results.json')
    code = {f:d for f,d in {**p['sources'], **p['inherited_sources']}.items() if not f.startswith('studies/')}
    assert all(sha(ROOT/f) == d for f,d in code.items())
    binding = dict(p['source'])
    for q in (UPSTREAM/'registration.json', UPSTREAM/'verification.json', LABELS/'verification.json'):
        binding[str(q.relative_to(ROOT))] = sha(q)
    for year in range(2018, 2026):
        for n in ('training.json','seal.json','predictions.json.gz','test-receipt.json'):
            q = UPSTREAM/'folds'/str(year)/n; binding[str(q.relative_to(ROOT))] = sha(q)
        for n,d in read(LABELS/'folds'/str(year)/'training.json')['model_states'].items():
            q = LABELS/'folds'/str(year)/n; assert sha(q) == d; binding[str(q.relative_to(ROOT))] = d
    for r in OLD_RECIPES:
        for c in CASES:
            q = UPSTREAM/'accounts'/r['id']/f'{c}.json.gz'; binding[str(q.relative_to(ROOT))] = sha(q)
    estimator = {f:sha(f) for f in (inspect.getfile(GradientBoostingRegressor), tree_binary.__file__)}
    write(STUDY/'registration.json',dict(losses=LOSSES, models=MODELS, recipes=RECIPES, heads=HEADS, profile=PROFILE, seeds=SEEDS,
        source=binding, inherited_sources=code, sources={f:sha(ROOT/f) for f in SOURCES}, versions=p['versions'], project_runtime_sources=p['project_runtime_sources'], estimator_runtime_sources=estimator,
        manifest_sha256=p['manifest_sha256'], costs=CASES, financing=BORROW, model_fits=392, final_members=392, exact_huber_states=98,
        inherited_independent_labels=21082, prescribed_refits=8, fixed_refit_year=2025, fixed_refit_seed=101, accounts=64, exact_controls=52,
        exact_legacy_controls=48, exact_identity_controls=4, prescribed_replay=['S04','DELAY'], score_tolerance=2e-12,
        target_return_pct=10000, strict_drawdown_pct=35, validation_read=False,
        qualification='BTC-only originalCAL44/common62+6SHORT_NET; fixed loss coordinate; P02long/risk; consumed2018-2025; all2026excluded'))
    print('B88A FROZEN',sha(STUDY/'registration.json'),flush=True)


def verify(reg):
    assert reg['losses'] == list(LOSSES) and reg['models'] == MODELS and reg['recipes'] == RECIPES and reg['heads'] == HEADS and reg['profile'] == PROFILE and reg['seeds'] == list(SEEDS) and len(RECIPES) == 16
    assert sha(FOLDS/'manifest.json') == reg['manifest_sha256'] and reg['costs'] == {k:list(v) for k,v in CASES.items()} and reg['financing'] == BORROW
    for f,d in {**reg['sources'],**reg['inherited_sources']}.items(): assert sha(ROOT/f) == d, f
    for f,d in {**reg['project_runtime_sources'],**reg['estimator_runtime_sources']}.items(): assert sha(f) == d, f
    for n,v in reg['versions'].items(): assert version(n) == v


def bound(reg,p):
    assert sha(p) == reg['source'][str(p.relative_to(ROOT))],p
    return read(p)


def train(year):
    reg = read(STUDY/'registration.json'); reads = install_guard(year,'train'); verify(reg); folder = STUDY/'folds'/str(year)
    parent = bound(reg,LABELS/'folds'/str(year)/'training.json'); ps = bound(reg,LABELS/'folds'/str(year)/'seal.json')
    assert parent['cutoff'] == ps['cutoff'] == f'{year-1}-12-31' and not ps['current_test_read'] and ps['training_sha256'] == sha(LABELS/'folds'/str(year)/'training.json')
    days,prices = load_fold(year); cut = len(days)-1; ids = np.asarray(parent['common_ids'],dtype=int)
    states = {}; receipts = {m['id']:[] for m in MODELS}; fitted = identities = 0; labelsha = None
    if len(ids) >= 128:
        assert year > 2018; banks = bound(reg,LABELS/'folds'/str(year)/'labels.json.gz'); labelsha = sha(LABELS/'folds'/str(year)/'labels.json.gz'); assert labelsha == parent['labels_sha256']
        rows = matrix(days,prices,'CAL44')
        for model in MODELS:
            key = model['id']; vector = target_vector(banks[model['head']['id']],len(days))
            for pos,seed in enumerate(SEEDS):
                with threadpool_limits(limits=1): state,rec = fit(rows,vector,ids,cut,model['head'],model['spec'],seed)
                if model['spec']['id'] == 'HUBER':
                    original = bound(reg,LABELS/'folds'/str(year)/'models'/f'{model["head"]["id"]}-{seed}.json.gz')
                    assert state == original and rec == parent['receipts'][model['head']['id']][pos]; identities += 1
                p = folder/'models'/f'{key}-{seed}.json.gz'; write(p,state); states[str(p.relative_to(folder))] = sha(p); receipts[key].append(rec); fitted += 1
            print('B88A MODEL',year,key,fitted,flush=True)
    else: assert year == 2018 and len(ids) == 0
    write(folder/'training.json',dict(year=year,cutoff=days[-1],fits=fitted,exact_huber_states=identities,selection_calls=0,y01_policy=parent['y01_policy'],model_states=states,receipts=receipts,common_ids=ids.tolist(),source_labels_sha256=labelsha,protected_reads=sorted(reads)))
    write(folder/'seal.json',dict(training_sha256=sha(folder/'training.json'),train_sha256=sha(FOLDS/str(year)/'train.json'),cutoff=days[-1],current_test_read=False,registration_sha256=sha(STUDY/'registration.json')))
    print('B88A TRAIN',year,fitted,identities,flush=True)


def test(year):
    reg = read(STUDY/'registration.json'); reads = install_guard(year,'test'); verify(reg); folder = STUDY/'folds'/str(year)
    tr = read(folder/'training.json'); seal = read(folder/'seal.json')
    assert seal['training_sha256'] == sha(folder/'training.json') and seal['registration_sha256'] == sha(STUDY/'registration.json') and not seal['current_test_read']
    fixed = bundle(reg,year); days,prices = load_fold(year,include_test=True); first = days.index(f'{year-1}-12-31'); last = days.index(f'{year}-12-31'); assert fixed['dates'] == days[first:last]
    rows = matrix(days,prices,'CAL44')[first:last] if tr['fits'] else None; scores = {}
    for m in MODELS:
        key = m['id']
        if not tr['receipts'][key]: scores[key] = [None]*(last-first); continue
        pred = []
        for seed in SEEDS:
            p = folder/'models'/f'{key}-{seed}.json.gz'; assert sha(p) == tr['model_states'][str(p.relative_to(folder))]; pred.append(predict(read(p),rows))
        scores[key] = np.mean(pred,axis=0).tolist()
    for spec in LOSSES:
        g = spec['id']; scores[g] = [None if a is None or b is None else (a+b)/2 for a,b in zip(scores[g+'_L1'],scores[g+'_L2'],strict=True)]
        assert [v is None for v in scores[g]] == [v is None for v in fixed['learner']]
    assert scores['HUBER'] == fixed['learner']
    write(folder/'predictions.json.gz',dict(dates=fixed['dates'],scores=scores,fixed=fixed))
    write(folder/'test-receipt.json',dict(seal_sha256=sha(folder/'seal.json'),predictions_sha256=sha(folder/'predictions.json.gz'),test_sha256=sha(FOLDS/str(year)/'test.json'),fitting_calls=0,selection_calls=0,validation_read=False,protected_reads=sorted(reads)))
    print('B88A TEST',year,flush=True)


def assemble(reg):
    days,prices = load_fold(2025,include_test=True); where = {d:i for i,d in enumerate(days)}; records = {}; policies = {}; scores = {s['id']:[None]*len(days) for s in LOSSES}
    for year in range(2018,2026):
        folder = STUDY/'folds'/str(year); tr = read(folder/'training.json'); seal = read(folder/'seal.json'); receipt = read(folder/'test-receipt.json'); f = read(folder/'predictions.json.gz')
        assert seal['training_sha256'] == sha(folder/'training.json') and receipt['seal_sha256'] == sha(folder/'seal.json') and receipt['predictions_sha256'] == sha(folder/'predictions.json.gz')
        records[year] = f['fixed']; policies[year] = tr['y01_policy']
        for g in scores:
            for d,v in zip(f['dates'],f['scores'][g],strict=True): scores[g][where[d]] = v
    values,counts = frame(days,prices,records,policies); old = old_assemble(reg); assert values == old[0]
    return values,scores,old


def targets(assembled,recipe):
    values,scores,old = assembled
    if recipe['kind'] == 'LEGACY': return old_targets(old,next(r for r in OLD_RECIPES if r['id'] == recipe['id']))
    return component(values['days'],values['prices'],values['scores'],{'Y01':values['policies']},values['flags'],scores[recipe['stream']],.5,'MODEL')


def replay():
    reg = read(STUDY/'registration.json'); reads = install_guard(2025,'replay'); verify(reg); assembled = assemble(reg); days,prices = assembled[0]['days'],assembled[0]['prices']; out = []
    for recipe in RECIPES:
        target,entry = targets(assembled,recipe); ss = {}; failures = {}; audits = {}
        for case in CASES:
            try: a = run_account(days,prices,target,case,{},end='2025-12-31',role='target_replay',entry_permission=entry,annual_settlement=False)
            except ValueError as e: failures[case] = dict(type=type(e).__name__,message=str(e)); continue
            audits[case] = audit(a,days,prices,target,CASES[case],BORROW[case],{},entry,False)
            if recipe['kind'] in ('LEGACY','IDENTITY'):
                n = 'P02' if recipe['kind'] == 'IDENTITY' else recipe['id']; assert a == bound(reg,UPSTREAM/'accounts'/n/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz',a); ss[case] = a['summary']
        dd = max((s['max_drawdown_pct'] for s in ss.values()),default=None); passed = not failures and len(ss) == 4 and ss['STRESS']['return_pct'] >= 10000 and dd < 35
        out.append(dict(recipe=recipe,summaries=ss,failures=failures,audits=audits,goal_gate=passed)); print('B88A RESULT',recipe['id'],ss.get('STRESS',{}).get('return_pct'),dd,passed,failures,flush=True)
    write(STUDY/'results.json',dict(results=out,validation_read=False,protected_reads=sorted(reads)))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('command',choices=('freeze','train','test','replay','run')); p.add_argument('--year',type=int); a = p.parse_args()
    if a.command in ('train','test'):
        if a.year is None: p.error('--year required')
        globals()[a.command](a.year)
    elif a.command == 'run':
        for year in range(2018,2026):
            for stage in ('train','test'): subprocess.run([sys.executable,'-m','lab.b88a',stage,'--year',str(year)],cwd=ROOT,check=True)
        subprocess.run([sys.executable,'-m','lab.b88a','replay'],cwd=ROOT,check=True)
    else: globals()[a.command]()
