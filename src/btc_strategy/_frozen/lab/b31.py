"""Fixed-scale entry controls with the same prior-known cold folds as rank sizing."""
import argparse
import itertools
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT, read, write, sha
from .b31_io import STUDY, UPSTREAM, CONTROL_IDS, FOLDS, install_guard, load_fold
from .b30 import RECIPES as OLD_RECIPES, targets_and_permissions as old_targets, SCORE_NAMES
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

PARENTS = ('Y01', 'Y04')
SCALES = (.875, .75)
SOURCES = {'Y01': 'P07', 'Y04': 'P08'}
SOURCE_RECIPES = {r['id']: r for r in OLD_RECIPES}
RECIPES = [dict(id=f'C{i+1:02}', mode='CONSTANT', parent=p, scale=s, source=SOURCES[p])
    for i, (p, s) in enumerate(itertools.product(PARENTS, SCALES))]
RECIPES += [dict(id=f'C{i+5:02}', mode='CONTROL', source=p, control=p) for i, p in enumerate(CONTROL_IDS)]
RANK_PAIRS = [('C05','C01'), ('C06','C02'), ('C07','C02'), ('C08','C03'), ('C09','C04'), ('C10','C04')]
PARENT_PAIRS = [('C01','C11'), ('C02','C11'), ('C03','C12'), ('C04','C12')]


def constant_multipliers(active, scale):
    if scale not in SCALES or any(type(v) is not bool for v in active):
        raise ValueError('unregistered constant or nonboolean eligibility')
    return [scale if v else 1. for v in active]


def verify():
    reg = read(STUDY/'registration.json')
    for name, digest in reg['sources'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('frozen source changed: '+name)
    assert sha(FOLDS/'manifest.json') == reg['data_manifest_sha256']
    assert sha(UPSTREAM/'registration.json') == reg['upstream']['registration.json']
    assert reg['recipes'] == RECIPES and reg['scales'] == list(SCALES)
    assert reg['rank_pairs'] == [list(x) for x in RANK_PAIRS]
    assert reg['parent_pairs'] == [list(x) for x in PARENT_PAIRS]
    for name, v in reg['versions'].items():
        assert version(name) == v
    return reg


def upstream(reg, path):
    p = UPSTREAM/path
    if sha(p) != reg['upstream'][path]:
        raise ValueError('parent seal changed')
    return read(p)


def freeze():
    old = read(UPSTREAM/'registration.json')
    names = [p for p in old['sources'] if p.startswith('lab/') or p == 'WALKFORWARD_AUTHORIZATION.md']
    assert all(sha(ROOT/p) == old['sources'][p] for p in names)
    names += ['lab/b31.py', 'lab/b31_io.py', 'tests/test_b31.py', 'tools/verify_b31.py',
        'studies/B31-constant-sizing-controls/spec.md']
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
    write(STUDY/'registration.json', dict(recipes=RECIPES, parents=PARENTS, scales=SCALES,
        rank_pairs=RANK_PAIRS, parent_pairs=PARENT_PAIRS, upstream=sealed,
        new_model_fits=0, new_rank_fits=0, calibration_accounts=0, final_account_cap=52,
        exact_control_accounts=36, prescribed_replays=['C02'], sources={p: sha(ROOT/p) for p in names},
        data_manifest_sha256=sha(FOLDS/'manifest.json'), costs=CASES, financing=BORROW,
        versions={p: version(p) for p in ('scikit-learn','numpy','pandas','nautilus-trader','threadpoolctl')},
        target_return_pct=10000, max_drawdown_strict_pct=35,
        qualification='fixed scale controls; prior-known cold eligibility; consumed history'))
    print('B31 FROZEN', sha(STUDY/'registration.json'), flush=True)


def train(year):
    reads = install_guard(year, 'train'); reg = verify(); folder = STUDY/f'folds/{year}'
    if (folder/'seal.json').exists():
        raise ValueError('preserve sealed fold')
    oldseal = upstream(reg, f'folds/{year}/seal.json')
    parent = upstream(reg, f'folds/{year}/training.json')
    days, prices = load_fold(year)
    assert oldseal['cutoff'] == parent['cutoff'] == days[-1] == f'{year-1}-12-31'
    assert not oldseal['current_test_read']
    active = {}
    for p in PARENTS:
        counts = parent['rank_counts'][p]
        assert type(counts['active']) is bool and counts['active'] == (counts['positive'] >= 128)
        active[p] = counts['active']
    write(folder/'training.json', dict(year=year, cutoff=days[-1], model_fits=0, rank_fits=0,
        selection_calls=0, active=active, rank_counts=parent['rank_counts'],
        parent_policies=parent['parent_policies'], parent_choices=parent['parent_choices'],
        parent_training_sha256=oldseal['training_sha256'], protected_reads=sorted(reads)))
    write(folder/'seal.json', dict(year=year, cutoff=days[-1], current_test_read=False,
        train_sha256=sha(FOLDS/str(year)/'train.json'), training_sha256=sha(folder/'training.json'),
        registration_sha256=sha(STUDY/'registration.json')))
    print('B31 POLICY SEALED', year, active, flush=True)


def test(year):
    reads = install_guard(year, 'test'); reg = verify(); folder = STUDY/f'folds/{year}'
    seal = read(folder/'seal.json'); training = read(folder/'training.json')
    assert not seal['current_test_read'] and seal['cutoff'] == f'{year-1}-12-31'
    assert sha(folder/'training.json') == seal['training_sha256']
    assert sha(STUDY/'registration.json') == seal['registration_sha256']
    assert sha(FOLDS/str(year)/'train.json') == seal['train_sha256']
    parent = upstream(reg, f'folds/{year}/predictions.json.gz')
    receipt = upstream(reg, f'folds/{year}/test-receipt.json')
    assert receipt['predictions_sha256'] == sha(UPSTREAM/f'folds/{year}/predictions.json.gz')
    assert receipt['seal_sha256'] == sha(UPSTREAM/f'folds/{year}/seal.json')
    days, prices = load_fold(year, True)
    assert parent['dates'] == days[days.index(f'{year-1}-12-31'):days.index(f'{year}-12-31')]
    write(folder/'predictions.json.gz', dict(**parent, active=training['active']))
    write(folder/'test-receipt.json', dict(year=year, seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'), test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0, selection_calls=0, protected_reads=sorted(reads), reserved_validation_read=False))
    print('B31 TEST FROZEN', year, flush=True)


def assemble():
    days, prices = load_fold(2025, include_test=True); where = {d:i for i,d in enumerate(days)}
    scores = {k:[None]*len(days) for k in SCORE_NAMES}
    policies = {k:{} for k in ('U02','U04')}; choices = {p:{} for p in ('H03','H04')}
    rank_values = {p:[None]*len(days) for p in PARENTS}
    active = {p:[False]*len(days) for p in PARENTS}; folds = []
    for year in range(2018, 2026):
        folder = STUDY/f'folds/{year}'
        seal, receipt, training = [read(folder/n) for n in ('seal.json','test-receipt.json','training.json')]
        assert sha(folder/'seal.json') == receipt['seal_sha256']
        assert sha(folder/'training.json') == seal['training_sha256']
        assert sha(folder/'predictions.json.gz') == receipt['predictions_sha256']
        forecast = read(folder/'predictions.json.gz')
        for name, values in forecast['scores'].items():
            for day, v in zip(forecast['dates'], values, strict=True): scores[name][where[day]] = v
        for name in policies: policies[name][year] = training['parent_policies'][name]
        for name in choices: choices[name][year] = training['parent_choices'][name]
        assert forecast['active'] == training['active']
        for name, values in forecast['ranks'].items():
            for d, v in zip(forecast['dates'], values, strict=True):
                rank_values[name][where[d]] = v; active[name][where[d]] = forecast['active'][name]
        folds.append(dict(year=year, active=training['active'], test_receipt_sha256=sha(folder/'test-receipt.json')))
    return days, prices, scores, policies, choices, rank_values, active, folds


def targets_and_permissions(days, prices, scores, policies, choices, rank_values, active, recipe):
    targets, entry = old_targets(days, prices, scores, policies, choices, rank_values, SOURCE_RECIPES[recipe['source']])
    if recipe['mode'] == 'CONTROL':
        return targets, entry
    scale = constant_multipliers(active[recipe['parent']], recipe['scale'])
    return [{**t, 'long_fraction': t['long_fraction']*m} for t,m in zip(targets, scale, strict=True)], entry


def replay():
    reads = install_guard(2025, 'replay'); reg = verify()
    days, prices, scores, policies, choices, rank_values, active, folds = assemble(); results = []
    for recipe in RECIPES:
        name = recipe['id']
        targets, entry = targets_and_permissions(days, prices, scores, policies, choices, rank_values, active, recipe)
        summaries, audits, failures = {}, {}, {}
        for case in CASES:
            try:
                account = run_account(days, prices, targets, case, {}, end='2025-12-31', role='target_replay',
                    entry_permission=entry, annual_settlement=False)
            except ValueError as e:
                if str(e) != 'minimum notional makes registered trade infeasible': raise
                failures[case] = dict(type=type(e).__name__, message=str(e)); continue
            audits[case] = audit(account, days, prices, targets, CASES[case], BORROW[case], {}, entry, False)
            if 'control' in recipe:
                assert account == upstream(reg, f"accounts/{recipe['control']}/{case}.json.gz")
            write(STUDY/'accounts'/name/f'{case}.json.gz', account); summaries[case] = account['summary']
        passed = not failures and summaries['STRESS']['return_pct'] >= 10000 and max(s['max_drawdown_pct'] for s in summaries.values()) < 35
        results.append(dict(id=name, recipe=recipe, status='FAILED' if failures else 'COMPLETE', summaries=summaries,
            audits=audits, failures=failures, historical_economic_gate=passed,
            qualification='fixed scale controls; conditional sources; consumed history'))
        print('B31 RESULT', name, round(summaries['STRESS']['return_pct'],2) if 'STRESS' in summaries else failures,
            round(max(s['max_drawdown_pct'] for s in summaries.values()),2) if summaries else None, passed, flush=True)
    write(STUDY/'results.json', dict(results=results, folds=folds, protected_reads=sorted(reads),
        reserved_validation_read=False, qualification='fixed scales; no realized-exposure matching'))


def run():
    for year in range(2018, 2026):
        for stage in ('train','test'):
            subprocess.run([sys.executable,'-m','lab.b31',stage,'--year',str(year)], cwd=ROOT, check=True)
    subprocess.run([sys.executable,'-m','lab.b31','replay'], cwd=ROOT, check=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command', choices=('freeze','train','test','replay','run'))
    parser.add_argument('--year', type=int, choices=range(2018,2026)); args=parser.parse_args()
    if args.command in ('train','test'):
        if args.year is None: parser.error('--year required')
        globals()[args.command](args.year)
    else:
        globals()[args.command]()
