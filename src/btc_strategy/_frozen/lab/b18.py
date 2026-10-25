"""Fixed actual-entry gates on original annual forecasts, with no refitting."""
import argparse
import itertools
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT, read, write, sha
from .b18_io import STUDY, UPSTREAM, CONTROL_IDS, FOLDS, install_guard, load_fold
from .b17 import RECIPES as ORIGINAL_RECIPES
from .b16 import desired
from .entry_permissions import permissions, GATES
from .entry_permission_native import run_account, CASES, BORROW
from .entry_permission_audit import audit

PARENTS = {r['id']: r for r in ORIGINAL_RECIPES if r['id'] in CONTROL_IDS}
RECIPES = [dict(id=f'E{i+1:02}', parent=parent, gate=gate)
           for i, (parent, gate) in enumerate(itertools.product(CONTROL_IDS[:3], GATES))]
RECIPES += [dict(id=f'E{i+7:02}', parent=parent, gate='NONE', control=parent)
            for i, parent in enumerate(CONTROL_IDS)]
SCORE_NAMES = ('EXTRA_DYNAMICS_L60', 'EXTRA_MINER_L120', 'BASE_TREE', 'MEAN_PATH36', 'MEAN_CAL44')


def verify():
    reg = read(STUDY / 'registration.json')
    for name, digest in reg['sources'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('frozen source changed: ' + name)
    assert sha(FOLDS / 'manifest.json') == reg['data_manifest_sha256']
    assert sha(UPSTREAM / 'registration.json') == reg['upstream']['registration.json']
    assert reg['recipes'] == RECIPES
    for name, expected in reg['versions'].items():
        assert version(name) == expected
    return reg


def upstream(reg, path):
    if sha(UPSTREAM / path) != reg['upstream'][path]:
        raise ValueError('sealed B17 input changed')
    return read(UPSTREAM / path)


def freeze():
    old = read(UPSTREAM / 'registration.json')
    names = [p for p in old['sources'] if p.startswith('lab/') or p == 'WALKFORWARD_AUTHORIZATION.md']
    assert all(sha(ROOT / p) == old['sources'][p] for p in names)
    names += ['lab/b18.py', 'lab/b18_io.py', 'lab/entry_permissions.py',
              'lab/entry_permission_native.py', 'lab/entry_permission_audit.py',
              'tests/test_b18.py', 'tools/verify_b18.py', 'studies/B18-actual-entry-permission/spec.md']
    sealed = {'registration.json': sha(UPSTREAM / 'registration.json')}
    for year in range(2018, 2026):
        stem = f'folds/{year}/'
        seal, receipt = [read(UPSTREAM / (stem + n)) for n in ('seal.json', 'test-receipt.json')]
        sealed[stem + 'seal.json'] = sha(UPSTREAM / (stem + 'seal.json'))
        sealed[stem + 'training.json'] = seal['training_sha256']
        sealed[stem + 'test-receipt.json'] = sha(UPSTREAM / (stem + 'test-receipt.json'))
        sealed[stem + 'predictions.json.gz'] = receipt['predictions_sha256']
    for parent in CONTROL_IDS:
        for case in CASES:
            path = f'accounts/{parent}/{case}.json.gz'
            sealed[path] = sha(UPSTREAM / path)
    write(STUDY / 'registration.json', dict(recipes=RECIPES, parents=PARENTS, upstream=sealed,
        new_member_fits=0, final_account_cap=44, exact_control_accounts=20,
        sources={p: sha(ROOT / p) for p in names}, data_manifest_sha256=sha(FOLDS / 'manifest.json'),
        costs=CASES, financing=BORROW, target_return_pct=10000, max_drawdown_strict_pct=35,
        versions={p: version(p) for p in ('scikit-learn', 'numpy', 'pandas', 'nautilus-trader', 'threadpoolctl')},
        qualification='consumed annual history; mining parents retain conditional source assumptions'))
    print('B18 FROZEN', sha(STUDY / 'registration.json'), flush=True)


def train(year):
    reads = install_guard(year, 'train'); reg = verify(); folder = STUDY / f'folds/{year}'
    if (folder / 'seal.json').exists():
        raise ValueError('preserve sealed fold')
    old = upstream(reg, f'folds/{year}/seal.json')
    prior = upstream(reg, f'folds/{year}/training.json')
    assert old['cutoff'] == prior['cutoff'] == f'{year-1}-12-31' and not old['current_test_read']
    train_hash = sha(FOLDS / str(year) / 'train.json')
    assert train_hash == old['train_sha256']
    write(folder / 'training.json', dict(year=year, cutoff=old['cutoff'], model_fits=0,
        selection='fixed entry gates; no new selection', parent_policies=prior['parent_policies'],
        protected_reads=sorted(reads)))
    write(folder / 'seal.json', dict(year=year, cutoff=old['cutoff'], current_test_read=False,
        training_sha256=sha(folder / 'training.json'), train_sha256=train_hash,
        upstream_seal_sha256=sha(UPSTREAM / f'folds/{year}/seal.json'),
        registration_sha256=sha(STUDY / 'registration.json')))
    print('B18 POLICY SEALED', year, flush=True)


def score_for(scores, parent):
    recipe = PARENTS[parent]
    if recipe['mode'] == 'EXACT':
        return [None] * len(scores['BASE_TREE'])  # Only NONE gates are registered for these controls.
    if recipe['mode'] == 'BASELINE':
        return scores['BASE_TREE']
    values = scores[recipe['model']]
    if recipe['mode'] == 'BLEND':
        return [None if x is None or y is None else .5 * (x + y)
                for x, y in zip(values, scores['BASE_TREE'], strict=True)]
    return values


def test(year):
    reads = install_guard(year, 'test'); reg = verify(); folder = STUDY / f'folds/{year}'
    seal = read(folder / 'seal.json')
    assert seal['cutoff'] == f'{year-1}-12-31' and not seal['current_test_read']
    assert sha(folder / 'training.json') == seal['training_sha256']
    assert sha(STUDY / 'registration.json') == seal['registration_sha256']
    assert sha(FOLDS / str(year) / 'train.json') == seal['train_sha256']
    old = upstream(reg, f'folds/{year}/predictions.json.gz')
    days, prices = load_fold(year, include_test=True)
    first, last = days.index(f'{year-1}-12-31'), days.index(f'{year}-12-31')
    assert old['dates'] == days[first:last]
    scores = {name: old['scores'][name] for name in SCORE_NAMES}
    entry = {r['id']: permissions(old['dates'], score_for(scores, r['parent']), r['gate']) for r in RECIPES}
    write(folder / 'predictions.json.gz', dict(dates=old['dates'], scores=scores, entry_permissions=entry))
    write(folder / 'test-receipt.json', dict(year=year, seal_sha256=sha(folder / 'seal.json'),
        predictions_sha256=sha(folder / 'predictions.json.gz'), fitting_calls=0,
        test_sha256=sha(FOLDS / str(year) / 'test.json'), protected_reads=sorted(reads),
        reserved_validation_read=False))
    print('B18 FORECAST AND GATES FROZEN', year, flush=True)


def assemble():
    days, prices = load_fold(2025, include_test=True); where = {d: i for i, d in enumerate(days)}
    scores = {k: [None] * len(days) for k in SCORE_NAMES}
    entry = {r['id']: [r['gate'] == 'NONE'] * len(days) for r in RECIPES}
    policies = {k: {} for k in ('U02', 'U04')}
    for year in range(2018, 2026):
        folder = STUDY / f'folds/{year}'
        seal, receipt, training = [read(folder / n) for n in ('seal.json', 'test-receipt.json', 'training.json')]
        assert sha(folder / 'seal.json') == receipt['seal_sha256']
        assert sha(folder / 'training.json') == seal['training_sha256']
        assert sha(folder / 'predictions.json.gz') == receipt['predictions_sha256']
        forecast = read(folder / 'predictions.json.gz')
        for source, destination in ((forecast['scores'], scores), (forecast['entry_permissions'], entry)):
            for name, values in source.items():
                for day, value in zip(forecast['dates'], values, strict=True):
                    destination[name][where[day]] = value
        for name in policies:
            policies[name][year] = training['parent_policies'][name]
    return days, prices, scores, policies, entry


def replay():
    reads = install_guard(2025, 'replay'); reg = verify()
    days, prices, scores, policies, entry = assemble(); results = []
    for recipe in RECIPES:
        targets = desired(days, prices, scores, policies, PARENTS[recipe['parent']])
        summaries, audits, failures = {}, {}, {}
        for case in CASES:
            try:
                account = run_account(days, prices, targets, case, {}, end='2025-12-31',
                                      role='target_replay', entry_permission=entry[recipe['id']])
            except ValueError as e:
                if str(e) != 'minimum notional makes registered trade infeasible':
                    raise
                failures[case] = dict(type=type(e).__name__, message=str(e)); continue
            audits[case] = audit(account, days, prices, targets, CASES[case], BORROW[case], {}, entry[recipe['id']])
            if 'control' in recipe:
                assert account == upstream(reg, f"accounts/{recipe['control']}/{case}.json.gz")
            write(STUDY / 'accounts' / recipe['id'] / f'{case}.json.gz', account)
            summaries[case] = account['summary']
        passed = not failures and summaries['STRESS']['return_pct'] >= 10000 and max(s['max_drawdown_pct'] for s in summaries.values()) < 35
        results.append(dict(id=recipe['id'], recipe=recipe, status='FAILED' if failures else 'COMPLETE',
            summaries=summaries, audits=audits, failures=failures, historical_economic_gate=passed))
        print('B18 RESULT', recipe['id'], {case: round(s['return_pct'], 2) for case, s in summaries.items()}, passed, flush=True)
    write(STUDY / 'results.json', dict(results=results, protected_reads=sorted(reads), model_fits=0,
        reserved_validation_read=False, qualification=reg['qualification']))


def run():
    for year in range(2018, 2026):
        for stage in ('train', 'test'):
            subprocess.run([sys.executable, '-m', 'lab.b18', stage, '--year', str(year)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, '-m', 'lab.b18', 'replay'], cwd=ROOT, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=('freeze', 'train', 'test', 'replay', 'run'))
    parser.add_argument('--year', type=int, choices=range(2018, 2026)); args = parser.parse_args()
    if args.command in ('train', 'test'):
        if args.year is None:
            parser.error('--year required')
        globals()[args.command](args.year)
    else:
        globals()[args.command]()
