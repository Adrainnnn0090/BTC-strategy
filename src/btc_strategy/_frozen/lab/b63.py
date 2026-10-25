"""Fixed small long-budget coordinates on every direct depth3 loss model."""
import argparse
import copy
import os
import sys
from pathlib import Path
from importlib.metadata import version
from .io import ROOT, DATA, read, write, sha
from .walkforward_io import FOLDS
from .b62 import assemble as source_assemble, targets as source_targets, RECIPES as PARENTS
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

STUDY = ROOT/'studies/B63-direct-loss-budget-steps'
SOURCE = ROOT/'studies/B62-depth3-loss-controls'
PARENT_IDS = tuple(r['id'] for r in PARENTS if r.get('fusion') == 'DIRECT')
SCALES = (.95, .9)
RECIPES = [dict(id=f'R{i+1:02}', parent=p, long_scale=s)
           for i, (p, s) in enumerate((p, s) for p in PARENT_IDS for s in SCALES)]
RECIPES += [dict(id=f'P{i+1:02}', control=r['id']) for i, r in enumerate(PARENTS)]
SOURCES = ('lab/b63.py', 'tests/test_b63.py', 'tools/verify_b63.py',
           'studies/B63-direct-loss-budget-steps/spec.md')


def permitted(path, role):
    p = Path(path).resolve()
    if p.is_relative_to(DATA):
        return p == FOLDS/'manifest.json' or p in {
            FOLDS/str(y)/f'{part}.json' for y in range(2018, 2025) for part in ('train', 'test')}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            rel = p.relative_to(STUDY).parts
            return rel[0] in ('registration.json', 'spec.md', 'accounts') or role == 'audit'
        if p.is_relative_to(SOURCE):
            rel = p.relative_to(SOURCE).parts
            if rel[0] in ('registration.json', 'spec.md', 'verification.json'):
                return True
            if rel[0] == 'folds' and len(rel) == 3:
                return rel[1].isdigit() and 2018 <= int(rel[1]) <= 2024 and rel[2] in (
                    'training.json', 'seal.json', 'test-receipt.json', 'predictions.json.gz')
            return len(rel) == 3 and rel[0] == 'accounts' and rel[1] in {r['id'] for r in PARENTS}
        return False
    if any(p.is_relative_to(q) for q in (
        ROOT/'archives', ROOT/'notes', Path('/workspace/BinanceTradingRobot/research'),
        Path('/workspace/BinanceTradingRobot/strategy'), Path('/workspace/Polymarket_Arbitrage_Robot/outputs'))):
        return False
    if p.is_relative_to('/workspace') and not p.is_relative_to(ROOT):
        return any(p.is_relative_to(q) for q in (
            Path('/workspace/BinanceTradingRobot/backend/.venv'),
            Path('/workspace/BinanceTradingRobot/backend/src'), Path('/workspace/.venvs')))
    return True


def install_guard(role):
    if role not in ('replay', 'audit'):
        raise ValueError('invalid zero-fit B63 role')
    reads = set()
    def hook(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        p = Path(os.fsdecode(args[0])).resolve()
        if not permitted(p, role):
            raise ValueError('B63 read denied: ' + str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):
            reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook)
    return reads


def adjust(rows, allowed, scale):
    if scale not in SCALES:
        raise ValueError('unregistered fixed budget coordinate')
    out = copy.deepcopy(rows)
    for row in out:
        row['long_fraction'] *= scale
    return out, list(allowed)


def targets(values, recipe):
    name = recipe.get('parent', recipe.get('control'))
    source = next(r for r in PARENTS if r['id'] == name)
    rows, allowed = source_targets(values, source)
    return adjust(rows, allowed, recipe['long_scale']) if 'parent' in recipe else (rows, allowed)


def freeze():
    old = read(SOURCE/'registration.json'); v = read(SOURCE/'verification.json')
    assert v['status'] == 'PASS' and v['accounts'] == 144 and not v['validation_read']
    bindings = {}
    for name in ('registration.json', 'verification.json'):
        bindings[str((SOURCE/name).relative_to(ROOT))] = sha(SOURCE/name)
    for year in range(2018, 2025):
        for name in ('training.json', 'seal.json', 'test-receipt.json', 'predictions.json.gz'):
            p = SOURCE/'folds'/str(year)/name; bindings[str(p.relative_to(ROOT))] = sha(p)
    for recipe in PARENTS:
        for case in CASES:
            p = SOURCE/'accounts'/recipe['id']/f'{case}.json.gz'; bindings[str(p.relative_to(ROOT))] = sha(p)
    inherited = {p: d for p, d in {**old['sources'], **old['inherited_sources']}.items()
                 if not p.startswith('studies/')}
    assert all(sha(ROOT/p) == d for p, d in inherited.items())
    write(STUDY/'registration.json', dict(last_year=2024, recipes=RECIPES, scales=SCALES,
        source=bindings, sources={p: sha(ROOT/p) for p in SOURCES}, inherited_sources=inherited,
        manifest_sha256=sha(FOLDS/'manifest.json'), accounts=208, exact_controls=144,
        versions=old['versions'], costs=CASES, financing=BORROW,
        new_fits=0, selection_calls=0, prescribed_replay=['R10', 'STRESS'],
        numeric_fraction_tolerance=2e-15, validation_read=False,
        qualification='fixed long-only budget transform; consumed2018–2024; not new predictor alpha'))
    print('B63 FROZEN', sha(STUDY/'registration.json'), flush=True)


def verify(reg):
    assert reg['recipes'] == RECIPES and reg['last_year'] == 2024 and reg['scales'] == list(SCALES)
    assert sha(FOLDS/'manifest.json') == reg['manifest_sha256']
    assert reg['costs'] == {k: list(v) for k, v in CASES.items()} and reg['financing'] == BORROW
    for name, expected in reg['versions'].items():
        assert version(name) == expected
    for p, d in {**reg['sources'], **reg['inherited_sources']}.items():
        assert sha(ROOT/p) == d, p
    for p, d in reg['source'].items():
        assert sha(ROOT/p) == d, p


def replay():
    reg = read(STUDY/'registration.json'); reads = install_guard('replay'); verify(reg)
    values = source_assemble(reg); days, prices = values[:2]; results = []
    for recipe in RECIPES:
        rows, allowed = targets(values, recipe); summaries = {}; audits = {}; failures = {}
        for case in CASES:
            try:
                account = run_account(days, prices, rows, case, {}, end='2024-12-31',
                    role='fold_train', entry_permission=allowed, annual_settlement=False)
            except ValueError as exc:
                failures[case] = dict(type=type(exc).__name__, message=str(exc)); continue
            audits[case] = audit(account, days, prices, rows, CASES[case], BORROW[case], {}, allowed, False)
            if 'control' in recipe:
                assert account == read(SOURCE/'accounts'/recipe['control']/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz', account); summaries[case] = account['summary']
        results.append(dict(recipe=recipe, summaries=summaries, audits=audits, failures=failures,
                            full2018_2025_goal_gate=False))
        print('B63 RESULT', recipe['id'], summaries.get('STRESS', {}).get('return_pct'),
              max((s['max_drawdown_pct'] for s in summaries.values()), default=None), failures, flush=True)
    write(STUDY/'results.json', dict(results=results, protected_reads=sorted(reads), end_year=2024,
                                  new_fits=0, selection_calls=0, validation_read=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=('freeze', 'replay'))
    args = parser.parse_args(); globals()[args.command]()
