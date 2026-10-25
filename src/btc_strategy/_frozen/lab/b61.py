"""Four losses, fixed architecture and seeds, annual prior-only training."""
import argparse
import copy
import subprocess
import sys
from importlib.metadata import version
import numpy as np
from threadpoolctl import threadpool_limits
from .io import ROOT, read, write, sha
from .walkforward_io import FOLDS, load_fold
from .b61_io import STUDY, SOURCE, CONTROLS, install_guard
from .boosted_stop import MODELS, PROFILE, fit, infer
from .tree_stability import SEEDS
from .tree_factors import matrix
from .execution_labels import records, target_vector
from .sgd import matured
from .exit_coordinate import desired
from .bear_short_overlay import overlay, SHORTS
from .short_trailing import with_short_trailing
from .b60a import targets as old_targets
from .b60a import RECIPES as OLD_RECIPES, NEW_NAMES
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

RECIPES = [dict(id=f'G{i+1:02}', model=spec['id'], fusion=fusion, cold=cold)
           for i, (spec, fusion, cold) in enumerate(
               (s, f, c) for s in MODELS for f in ('DIRECT', 'BLEND') for c in (False, True))]
RECIPES += [dict(id=f'P{i+1:02}', control=name) for i, name in enumerate(CONTROLS)]
SOURCES = ('lab/b61.py', 'lab/b61_io.py', 'lab/boosted_stop.py',
           'tools/verify_b61.py', 'tools/boosted_reference.py', 'tests/test_b61.py',
           'studies/B61-boosted-stop-losses/spec.md')


def freeze():
    parent = read(SOURCE / 'registration.json'); checked = read(SOURCE / 'verification.json')
    assert checked['status'] == 'PASS' and checked['accounts'] == 52
    assert not checked['validation_read'] and parent['last_year'] == 2024
    last = parent['last_year']; binding = {}
    for filename in ('registration.json', 'verification.json'):
        binding[str((SOURCE/filename).relative_to(ROOT))] = sha(SOURCE/filename)
    for year in range(2018, last+1):
        for filename in ('training.json', 'seal.json', 'predictions.json.gz', 'test-receipt.json'):
            p = SOURCE / 'folds' / str(year) / filename; binding[str(p.relative_to(ROOT))] = sha(p)
    for control in CONTROLS:
        for case in CASES:
            p = SOURCE / 'accounts' / control / f'{case}.json.gz'; binding[str(p.relative_to(ROOT))] = sha(p)
    inherited = {**parent['sources'], **parent['inherited_sources']}
    inherited = {p: d for p, d in inherited.items() if not p.startswith('studies/')}
    assert all(sha(ROOT/p) == d for p, d in inherited.items())
    write(STUDY/'registration.json', dict(last_year=last, models=MODELS, profile=PROFILE,
        seeds=SEEDS, recipes=RECIPES, source=binding, inherited_sources=inherited,
        sources={p: sha(ROOT/p) for p in SOURCES}, versions=parent['versions'],
        manifest_sha256=sha(FOLDS/'manifest.json'), costs=CASES, financing=BORROW,
        final_fits_cap=168, selection_calls=0, accounts=80, exact_controls=16,
        prescribed_replay=['G15', 'STRESS'], label_kind='STOP', full_maturity=61, embargo=6,
        score_tolerance=2e-12, validation_read=False,
        qualification='consumed2018–2024; no2025/2026; conditional inherited risk'))
    print('B61 FROZEN', sha(STUDY/'registration.json'), flush=True)


def verify(reg):
    assert reg['models'] == MODELS and reg['profile'] == PROFILE and reg['recipes'] == RECIPES
    assert reg['seeds'] == list(SEEDS) and reg['last_year'] == 2024
    assert sha(FOLDS/'manifest.json') == reg['manifest_sha256']
    for p, d in {**reg['sources'], **reg['inherited_sources']}.items():
        assert sha(ROOT/p) == d, p
    for name, val in reg['versions'].items():
        assert version(name) == val


def source(reg, p):
    assert sha(p) == reg['source'][str(p.relative_to(ROOT))]
    return read(p)


def train(year):
    reg = read(STUDY/'registration.json'); reads = install_guard(year, 'train', reg['last_year']); verify(reg)
    folder = STUDY/'folds'/str(year); parent = SOURCE/'folds'/str(year)
    old = source(reg, parent/'training.json'); oldseal = source(reg, parent/'seal.json')
    assert oldseal['cutoff'] == old['cutoff'] == f'{year-1}-12-31' and not oldseal['current_test_read']
    days, prices = load_fold(year); cut = len(days)-1; rows = matrix(days, prices, 'CAL44')
    try:
        ids = matured(cut, 60)
    except ValueError:
        ids = None
    counts = 0; states = {}; receipts = {}; labels_hash = None
    if ids is not None:
        labels = records(days, prices, cut, 'STOP'); vector = target_vector(labels, len(days))
        write(folder/'labels.json.gz', labels); labels_hash = sha(folder/'labels.json.gz')
        for spec in MODELS:
            receipts[spec['id']] = []
            for seed in SEEDS:
                with threadpool_limits(limits=1):
                    state, receipt = fit(rows, vector, ids, cut, spec, seed)
                p = folder/'models'/f"{spec['id']}-{seed}.json.gz"
                write(p, state); states[str(p.relative_to(folder))] = sha(p)
                receipts[spec['id']].append(receipt); counts += 1
    write(folder/'training.json', dict(year=year, cutoff=days[-1], y01_policy=old['y01_policy'],
        fits=counts, selection_calls=0, labels_sha256=labels_hash, model_states=states,
        receipts=receipts, cold=ids is None, protected_reads=sorted(reads)))
    write(folder/'seal.json', dict(training_sha256=sha(folder/'training.json'),
        train_sha256=sha(FOLDS/str(year)/'train.json'), registration_sha256=sha(STUDY/'registration.json'),
        cutoff=days[-1], current_test_read=False))
    print('B61 TRAIN', year, counts, flush=True)


def test(year):
    reg = read(STUDY/'registration.json'); reads = install_guard(year, 'test', reg['last_year']); verify(reg)
    folder = STUDY/'folds'/str(year); parent = SOURCE/'folds'/str(year)
    seal = read(folder/'seal.json'); training = read(folder/'training.json')
    assert sha(folder/'training.json') == seal['training_sha256']
    assert sha(STUDY/'registration.json') == seal['registration_sha256']
    old = source(reg, parent/'predictions.json.gz'); receipt = source(reg, parent/'test-receipt.json')
    assert sha(parent/'predictions.json.gz') == receipt['predictions_sha256'] and not receipt['reserved_validation_read']
    days, prices = load_fold(year, include_test=True); first = days.index(f'{year-1}-12-31'); last = days.index(f'{year}-12-31')
    assert old['dates'] == days[first:last]; rows = matrix(days, prices, 'CAL44')[first:last]
    outputs = {}
    for spec in MODELS:
        if training['cold']:
            outputs[spec['id']] = [None] * len(rows); continue
        members = []
        for seed in SEEDS:
            p = folder/'models'/f"{spec['id']}-{seed}.json.gz"
            assert sha(p) == training['model_states'][str(p.relative_to(folder))]
            members.append(read(p))
        outputs[spec['id']] = infer(members, rows).tolist()
    write(folder/'predictions.json.gz', dict(dates=old['dates'], scores=outputs, source=old))
    write(folder/'test-receipt.json', dict(seal_sha256=sha(folder/'seal.json'),
        predictions_sha256=sha(folder/'predictions.json.gz'), test_sha256=sha(FOLDS/str(year)/'test.json'),
        fitting_calls=0, selection_calls=0, reserved_validation_read=False, protected_reads=sorted(reads)))
    print('B61 TEST', year, flush=True)


def assemble(reg):
    days, prices = load_fold(reg['last_year'], include_test=True); where = {d: i for i, d in enumerate(days)}
    raw = {k: [None]*len(days) for k in ('BASE_TREE', 'CAL44_STOP')}
    new = {k: [None]*len(days) for k in NEW_NAMES}; policies = {}
    flags = {k: [False]*len(days) for k in ('bear', 'negative20', 'available')}
    models = {s['id']: [None]*len(days) for s in MODELS}
    for year in range(2018, reg['last_year']+1):
        folder = STUDY/'folds'/str(year)
        training, seal, receipt = [read(folder/n) for n in ('training.json', 'seal.json', 'test-receipt.json')]
        assert sha(folder/'training.json') == seal['training_sha256']
        assert sha(folder/'seal.json') == receipt['seal_sha256']
        assert sha(folder/'predictions.json.gz') == receipt['predictions_sha256']
        forecast = read(folder/'predictions.json.gz'); old = forecast['source']; policies[year] = training['y01_policy']
        for table, target in ((old['source_scores'], raw), (old['scores'], new),
                              (old['short_flags'], flags), (forecast['scores'], models)):
            for key, vals in table.items():
                for day, val in zip(forecast['dates'], vals, strict=True):
                    target[key][where[day]] = val
        for day in forecast['dates']:
            flags['available'][where[day]] = True
    policies[2025] = copy.deepcopy(policies[2024])  # unused terminal decision only
    return days, prices, raw, new, policies, flags, models


def targets(values, recipe):
    days, prices, raw, new, policies, flags, models = values
    if 'control' in recipe:
        parent = next(r for r in OLD_RECIPES if r['id'] == recipe['control'])
        return old_targets(days, prices, raw, new, policies, flags, parent)
    score = models[recipe['model']]
    if recipe['fusion'] == 'BLEND':
        score = [None if a is None or b is None else .5*(a+b)
                 for a, b in zip(raw['BASE_TREE'], score, strict=True)]
    if not recipe['cold']:
        return desired(days, prices, score, policies)
    alternate = {'BASE_TREE': score, 'CAL44_STOP': score}
    return with_short_trailing(*overlay(days, prices, alternate, {'Y01': policies}, flags, SHORTS[-1]))


def replay():
    reg = read(STUDY/'registration.json'); reads = install_guard(reg['last_year'], 'replay', reg['last_year']); verify(reg)
    values = assemble(reg); days, prices = values[:2]; output = []
    for recipe in RECIPES:
        rows, allowed = targets(values, recipe); summaries = {}; audits = {}; failures = {}
        for case in CASES:
            try:
                account = run_account(days, prices, rows, case, {}, end='2024-12-31', role='fold_train',
                                      entry_permission=allowed, annual_settlement=False)
            except ValueError as exc:
                failures[case] = dict(type=type(exc).__name__, message=str(exc)); continue
            audits[case] = audit(account, days, prices, rows, CASES[case], BORROW[case], {}, allowed, False)
            if 'control' in recipe:
                assert account == source(reg, SOURCE/'accounts'/recipe['control']/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz', account); summaries[case] = account['summary']
        output.append(dict(recipe=recipe, summaries=summaries, failures=failures, audits=audits,
                           historical_goal_gate=False))
        print('B61 RESULT', recipe['id'], summaries.get('STRESS', {}).get('return_pct'),
              max((s['max_drawdown_pct'] for s in summaries.values()), default=None), failures, flush=True)
    write(STUDY/'results.json', dict(results=output, end_year=2024, protected_reads=sorted(reads),
                                  validation_read=False, qualification='partial development cohort; not full goal'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('command', choices=('freeze', 'train', 'test', 'run', 'replay'))
    p.add_argument('--year', type=int); args = p.parse_args()
    if args.command in ('train', 'test'):
        if args.year is None:
            p.error('--year required')
        globals()[args.command](args.year)
    elif args.command == 'run':
        for year in range(2018, 2025):
            for stage in ('train', 'test'):
                subprocess.run([sys.executable, '-m', 'lab.b61', stage, '--year', str(year)], cwd=ROOT, check=True)
        subprocess.run([sys.executable, '-m', 'lab.b61', 'replay'], cwd=ROOT, check=True)
    else:
        globals()[args.command]()
