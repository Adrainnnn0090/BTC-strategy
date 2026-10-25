"""Frozen entry ablations and bounded price-momentum hypotheses; zero fitting."""
import argparse
import copy
import math
import subprocess
import sys
from importlib.metadata import version
from .io import ROOT, read, write, sha
from .walkforward_io import FOLDS, load_fold
from .b60a_io import STUDY, PARENT, install_guard
from .b05 import forecast_year
from .b12_signals import DEFAULT
from .exit_coordinate import desired, parent_score
from .bear_short_overlay import overlay, price_flags, SHORTS
from .short_trailing import with_short_trailing
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

RECIPES = [dict(id='C01', mode='Y01'), dict(id='C02', mode='T12')]
RECIPES += [dict(id=f'N{i:02}', mode=mode) for i, mode in enumerate((
    'BAND_AVAILABLE', 'BAND_FULL', 'MOM63', 'MOM126', 'MOM252', 'MOM_VOTE',
    'GATE63', 'GATE126', 'GATE_VOTE', 'FIXED_BAND', 'FIXED_VOTE'), 1)]
NEW_NAMES = [r['mode'] for r in RECIPES if r['id'].startswith('N')]
SOURCES = ('lab/b60a.py', 'lab/b60a_io.py', 'tests/test_b60a.py', 'tools/verify_b60a.py',
           'studies/B60A-bounded-trend-alpha-controls/spec.md')


def momentum(prices, i, n):
    if i < n:
        return 0.
    return float(int(prices[i] > prices[i-n]) - int(prices[i] < prices[i-n]))


def streams(prices, original):
    if len(prices) != len(original) or any(not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError('invalid causal price inputs')
    result = {name: [] for name in NEW_NAMES}
    for i, value in enumerate(original):
        if value is not None and not math.isfinite(value):
            raise ValueError('nonfinite original score')
        signs = {n: momentum(prices, i, n) for n in (63, 126, 252)}
        vote = sum(signs.values()) / 3
        available = value is not None
        full = 1. if i >= 252 else None
        row = dict(BAND_AVAILABLE=1. if available else None, BAND_FULL=full,
                   MOM63=signs[63] if available else None,
                   MOM126=signs[126] if available else None,
                   MOM252=signs[252] if available else None,
                   MOM_VOTE=vote if available else None,
                   GATE63=signs[63], GATE126=signs[126], GATE_VOTE=vote,
                   FIXED_BAND=full, FIXED_VOTE=vote if i >= 252 else None)
        for name in NEW_NAMES:
            result[name].append(row[name])
    return result


def freeze(last):
    parent = read(PARENT / 'registration.json')
    assert all(sha(ROOT / p) == digest for p, digest in parent['sources'].items())
    seals = {}
    for year in range(2018, last + 1):
        for name in ('training.json', 'seal.json', 'predictions.json.gz', 'test-receipt.json'):
            p = PARENT / 'folds' / str(year) / name
            seals[str(p.relative_to(ROOT))] = sha(p)
    if last == 2025:
        for name in ('T25', 'T12'):
            for case in CASES:
                p = PARENT / 'accounts' / name / f'{case}.json.gz'
                seals[str(p.relative_to(ROOT))] = sha(p)
    write(STUDY / 'registration.json', dict(last_year=last, recipes=RECIPES,
          sources={p: sha(ROOT / p) for p in SOURCES}, parent=seals,
          inherited_sources=parent['sources'], versions=parent['versions'],
          manifest_sha256=sha(FOLDS / 'manifest.json'), costs=CASES, financing=BORROW,
          new_fits=0, new_selections=0, accounts=52, prescribed_replay=['N06', 'STRESS'],
          target_return_pct=10000, strict_drawdown_pct=35,
          qualification='consumed development history; conditional annual risk; not blind OOS'))
    print('B60 FROZEN', last, sha(STUDY / 'registration.json'), flush=True)


def verify_sources(reg):
    assert reg['recipes'] == RECIPES and reg['costs'] == {k: list(v) for k, v in CASES.items()}
    assert sha(FOLDS / 'manifest.json') == reg['manifest_sha256']
    for name, digest in {**reg['sources'], **reg['inherited_sources']}.items():
        assert sha(ROOT / name) == digest, name
    for name, expected in reg['versions'].items():
        assert version(name) == expected


def parent_read(reg, p):
    assert sha(p) == reg['parent'][str(p.relative_to(ROOT))]
    return read(p)


def train(year):
    reg = read(STUDY / 'registration.json'); reads = install_guard(year, 'train', reg['last_year'])
    verify_sources(reg)
    source = PARENT / 'folds' / str(year); own = STUDY / 'folds' / str(year)
    seal = parent_read(reg, source / 'seal.json')
    old = parent_read(reg, source / 'training.json')
    assert seal['cutoff'] == old['cutoff'] == f'{year-1}-12-31'
    assert not seal['current_test_read'] and seal['training_sha256'] == sha(source / 'training.json')
    write(own / 'training.json', dict(year=year, cutoff=old['cutoff'], y01_policy=old['y01_policy'],
          fits=0, selections=0, protected_reads=sorted(reads)))
    write(own / 'seal.json', dict(cutoff=old['cutoff'], current_test_read=False,
          parent_seal_sha256=sha(source / 'seal.json'), training_sha256=sha(own / 'training.json'),
          registration_sha256=sha(STUDY / 'registration.json')))
    print('B60 POLICY', year, flush=True)


def test(year):
    reg = read(STUDY / 'registration.json'); reads = install_guard(year, 'test', reg['last_year'])
    verify_sources(reg)
    source = PARENT / 'folds' / str(year); own = STUDY / 'folds' / str(year)
    seal = read(own / 'seal.json')
    assert sha(own / 'training.json') == seal['training_sha256']
    assert sha(STUDY / 'registration.json') == seal['registration_sha256']
    parent_seal = parent_read(reg, source / 'seal.json')
    receipt = parent_read(reg, source / 'test-receipt.json')
    assert sha(source / 'seal.json') == seal['parent_seal_sha256'] == receipt['seal_sha256']
    assert parent_seal['cutoff'] == f'{year-1}-12-31' and not parent_seal['current_test_read']
    old = parent_read(reg, source / 'predictions.json.gz')
    assert sha(source / 'predictions.json.gz') == receipt['predictions_sha256']
    assert not receipt['reserved_validation_read'] and receipt['fitting_calls'] == 0
    days, prices = load_fold(year, include_test=True); where = {d: i for i, d in enumerate(days)}
    first, last = where[f'{year-1}-12-31'], where[f'{year}-12-31']
    assert old['dates'] == days[first:last]
    original = [None] * len(days)
    for day, value in zip(old['dates'], parent_score(old['scores'], 'H03'), strict=True):
        original[where[day]] = value
    new = streams(prices, original)
    write(own / 'predictions.json.gz', dict(dates=old['dates'],
          source_scores={k: old['scores'][k] for k in ('BASE_TREE', 'CAL44_STOP')},
          scores={k: v[first:last] for k, v in new.items()}, short_flags=old['short_flags']))
    write(own / 'test-receipt.json', dict(seal_sha256=sha(own / 'seal.json'),
          predictions_sha256=sha(own / 'predictions.json.gz'), fitting_calls=0,
          selection_calls=0, reserved_validation_read=False, protected_reads=sorted(reads)))
    print('B60 TEST', year, flush=True)


def assemble(reg):
    last = reg['last_year']; days, prices = load_fold(last, include_test=True)
    where = {d: i for i, d in enumerate(days)}
    raw = {k: [None] * len(days) for k in ('BASE_TREE', 'CAL44_STOP')}
    new = {k: [None] * len(days) for k in NEW_NAMES}; policies = {}
    flags = {k: [False] * len(days) for k in ('bear', 'negative20', 'available')}
    for year in range(2018, last + 1):
        folder = STUDY / 'folds' / str(year)
        seal, receipt, training = [read(folder / n) for n in ('seal.json', 'test-receipt.json', 'training.json')]
        assert sha(folder / 'seal.json') == receipt['seal_sha256']
        assert sha(folder / 'training.json') == seal['training_sha256']
        assert sha(folder / 'predictions.json.gz') == receipt['predictions_sha256']
        assert seal['cutoff'] == f'{year-1}-12-31' and not seal['current_test_read']
        forecast = read(folder / 'predictions.json.gz'); policies[year] = training['y01_policy']
        for table, target in ((forecast['source_scores'], raw), (forecast['scores'], new),
                              (forecast['short_flags'], flags)):
            for name, values in table.items():
                for day, value in zip(forecast['dates'], values, strict=True):
                    target[name][where[day]] = value
        for day in forecast['dates']:
            flags['available'][where[day]] = True
    # Only the unused terminal decision gets this entry; no account can act on it.
    if last < 2025:
        policies[last + 1] = copy.deepcopy(policies[last])
    return days, prices, raw, new, policies, flags


def targets(days, prices, raw, new, policies, flags, recipe):
    mode = recipe['mode']; original = parent_score(raw, 'H03')
    if mode == 'T12':
        return with_short_trailing(*overlay(days, prices, raw, {'Y01': policies}, flags, SHORTS[-1]))
    if mode == 'Y01':
        return desired(days, prices, original, policies)
    if mode.startswith('GATE'):
        rows, allowed = desired(days, prices, original, policies)
        return rows, [bool(a and v is not None and v > 0) for a, v in zip(allowed, new[mode], strict=True)]
    chosen = policies
    if mode.startswith('FIXED'):
        chosen = {year: {**DEFAULT, 'model': 'NEW', 'vol_target': .75} for year in policies}
    return desired(days, prices, new[mode], chosen)


def replay():
    reg = read(STUDY / 'registration.json'); reads = install_guard(reg['last_year'], 'replay', reg['last_year'])
    verify_sources(reg); values = assemble(reg); days, prices = values[:2]; results = []
    for recipe in RECIPES:
        rows, allowed = targets(*values, recipe); summaries = {}; audits = {}; failures = {}
        for case in CASES:
            try:
                account = run_account(days, prices, rows, case, {}, end=f"{reg['last_year']}-12-31",
                    role='target_replay' if reg['last_year'] == 2025 else 'fold_train', entry_permission=allowed, annual_settlement=False)
            except ValueError as exc:
                failures[case] = dict(type=type(exc).__name__, message=str(exc)); continue
            audits[case] = audit(account, days, prices, rows, CASES[case], BORROW[case], {}, allowed, False)
            if reg['last_year'] == 2025 and recipe['id'] in ('C01', 'C02'):
                parent_id = {'C01': 'T25', 'C02': 'T12'}[recipe['id']]
                assert account == parent_read(reg, PARENT / 'accounts' / parent_id / f'{case}.json.gz')
            write(STUDY / 'accounts' / recipe['id'] / f'{case}.json.gz', account)
            summaries[case] = account['summary']
        dd = max((s['max_drawdown_pct'] for s in summaries.values()), default=None)
        passed = (reg['last_year'] == 2025 and not failures and len(summaries) == 4
                  and summaries['STRESS']['return_pct'] >= 10000 and dd < 35)
        results.append(dict(id=recipe['id'], mode=recipe['mode'], summaries=summaries, audits=audits,
                            failures=failures, historical_economic_gate=passed))
        print('B60 RESULT', recipe['id'], recipe['mode'],
              summaries.get('STRESS', {}).get('return_pct'), dd, failures or passed, flush=True)
    write(STUDY / 'results.json', dict(results=results, end_year=reg['last_year'],
          protected_reads=sorted(reads), validation_read=False, new_fits=0, new_selection_calls=0))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('command', choices=('freeze', 'train', 'test', 'replay', 'run'))
    p.add_argument('--year', type=int); p.add_argument('--end-year', type=int, choices=(2024, 2025), default=2024)
    args = p.parse_args()
    if args.command == 'freeze':
        freeze(args.end_year)
    elif args.command in ('train', 'test'):
        if args.year is None:
            p.error('--year required')
        globals()[args.command](args.year)
    elif args.command == 'run':
        reg = read(STUDY / 'registration.json')
        for year in range(2018, reg['last_year'] + 1):
            for stage in ('train', 'test'):
                subprocess.run([sys.executable, '-m', 'lab.b60a', stage, '--year', str(year)], cwd=ROOT, check=True)
        subprocess.run([sys.executable, '-m', 'lab.b60a', 'replay'], cwd=ROOT, check=True)
    else:
        replay()
