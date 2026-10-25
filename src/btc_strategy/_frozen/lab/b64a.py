"""Same-window replay of retained families and the frozen R09 candidate, no search."""
import argparse
import copy
import os
import sys
from pathlib import Path
from importlib.metadata import version
from .io import ROOT, DATA, read, write, sha
from .walkforward_io import FOLDS, load_fold
from .b05 import forecast_year
from .exit_coordinate import desired, parent_score
from . import b22, b31, b46, b50, b51, b62, b63
from .carry_native import run_account, CASES, BORROW
from .carry_audit import audit

STUDY = ROOT/'studies/B64A-retained-reference-reconciliation'
BANKS = {'CARRY': ROOT/'studies/B22-annual-carry',
         'SIZE': ROOT/'studies/B31-constant-sizing-controls',
         'AVERAGE': ROOT/'studies/B50-cross-market-fixed-averages',
         'POST': ROOT/'studies/B51-short-specific-payoff'}
ORIGINAL = ROOT/'studies/B64-retained-same-window-comparison'
EXTRA = [b62.STUDY, b63.STUDY, ROOT/'studies/B60A-bounded-trend-alpha-controls']
RECIPES = [dict(id='R09', kind='ROBUST') , dict(id='Y01', kind='CORE')]
RECIPES += [dict(id=k, kind='SHORT') for k in ('T08', 'T10', 'T12')]
RECIPES += [dict(id=k, kind='AVERAGE') for k in ('A01', 'A02')]
RECIPES += [dict(id=k, kind='CARRY') for k in ('H04', 'H05', 'H06')]
RECIPES += [dict(id=k, kind='POST') for k in ('S03', 'S04')]
RECIPES += [dict(id=k, kind='SIZE') for k in ('C02', 'C04')]
EXACT = {'R09': (b63.STUDY, 'R09'), 'Y01': (EXTRA[2], 'C01'), 'T12': (EXTRA[2], 'C02')}
SOURCES = ('lab/b64a.py', 'tests/test_b64a.py', 'tools/verify_b64a.py',
           'studies/B64A-retained-reference-reconciliation/spec.md')


def permitted(path, role):
    p = Path(path).resolve()
    if p.is_relative_to(DATA):
        return p == FOLDS/'manifest.json' or p in {
            FOLDS/str(y)/f'{part}.json' for y in range(2018, 2025) for part in ('train', 'test')}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            rel = p.relative_to(STUDY).parts
            return rel[0] in ('spec.md', 'registration.json', 'accounts') or role == 'audit'
        if p.is_relative_to(ORIGINAL):
            rel = p.relative_to(ORIGINAL).parts
            return rel in (('registration.json',), ('verification-failed.log',), ('failure.md',)) or (len(rel)==3 and rel[0]=='accounts' and rel[1] in {r['id'] for r in RECIPES})
        for base in [*BANKS.values(), *EXTRA]:
            if not p.is_relative_to(base):
                continue
            rel = p.relative_to(base).parts
            if rel in (('registration.json',), ('verification.json',)):
                return True
            if len(rel) == 3 and rel[0] == 'folds':
                return rel[1].isdigit() and 2018 <= int(rel[1]) <= 2024 and rel[2] in (
                    'training.json', 'seal.json', 'test-receipt.json', 'predictions.json.gz')
            return any(p == folder/'accounts'/name/f'{case}.json.gz'
                       for folder, name in EXACT.values() for case in CASES)
        return False
    if any(p.is_relative_to(q) for q in (ROOT/'archives', ROOT/'notes',
        Path('/workspace/BinanceTradingRobot/research'), Path('/workspace/BinanceTradingRobot/strategy'))):
        return False
    if p.is_relative_to('/workspace') and not p.is_relative_to(ROOT):
        return any(p.is_relative_to(q) for q in (
            Path('/workspace/BinanceTradingRobot/backend/.venv'),
            Path('/workspace/BinanceTradingRobot/backend/src'), Path('/workspace/.venvs')))
    return True


def install_guard(role):
    if role not in ('replay', 'audit'):
        raise ValueError('invalid B64 role')
    reads = set()
    def hook(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        p = Path(os.fsdecode(args[0])).resolve()
        if not permitted(p, role):
            raise ValueError('B64A read denied: ' + str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):
            reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook)
    return reads


def freeze():
    binding = {}; code = {}
    for base in [*BANKS.values(), *EXTRA]:
        old = read(base/'registration.json')
        for key in ('sources', 'inherited_sources'):
            for filename, digest in old.get(key, {}).items():
                if filename.startswith('studies/'):
                    continue
                assert filename not in code or code[filename] == digest, filename
                code[filename] = digest
        for name in ('registration.json', 'verification.json'):
            p = base/name; binding[str(p.relative_to(ROOT))] = sha(p)
        if base in [*BANKS.values(), b62.STUDY]:
            for year in range(2018, 2025):
                for name in ('training.json', 'seal.json', 'test-receipt.json', 'predictions.json.gz'):
                    p = base/'folds'/str(year)/name; binding[str(p.relative_to(ROOT))] = sha(p)
    for base, name in EXACT.values():
        for case in CASES:
            p = base/'accounts'/name/f'{case}.json.gz'; binding[str(p.relative_to(ROOT))] = sha(p)
    assert all(sha(ROOT/p) == d for p, d in code.items())
    for name in ('registration.json', 'verification-failed.log', 'failure.md'):
        p = ORIGINAL/name; binding[str(p.relative_to(ROOT))] = sha(p)
    for recipe in RECIPES:
        for case in CASES:
            p = ORIGINAL/'accounts'/recipe['id']/f'{case}.json.gz'
            binding[str(p.relative_to(ROOT))] = sha(p)
    old = read(b62.STUDY/'registration.json')
    write(STUDY/'registration.json', dict(last_year=2024, recipes=RECIPES, sources={p: sha(ROOT/p) for p in SOURCES},
        inherited_sources=code, source=binding, versions=old['versions'], costs=CASES, financing=BORROW,
        manifest_sha256=sha(FOLDS/'manifest.json'), accounts=56, exact_controls=12, exact_original_failed_study_accounts=56,
        prescribed_replay=['H05', 'STRESS'], new_fits=0, selections=0, validation_read=False,
        qualification='same-window retained replay only; consumed2018–2024; no2025/2026'))
    print('B64A FROZEN', sha(STUDY/'registration.json'), flush=True)


def verify(reg):
    assert reg['recipes'] == RECIPES and reg['last_year'] == 2024
    assert reg['costs'] == {k: list(v) for k, v in CASES.items()} and reg['financing'] == BORROW
    assert sha(FOLDS/'manifest.json') == reg['manifest_sha256']
    for name, expected in reg['versions'].items():
        assert version(name) == expected
    for p, d in {**reg['sources'], **reg['inherited_sources'], **reg['source']}.items():
        assert sha(ROOT/p) == d, p


def load_bank(base, days):
    where = {d: i for i, d in enumerate(days)}; scores = {}; policies = {'U02': {}, 'U04': {}, 'Y01': {}}
    choices = {'H03': {}, 'H04': {}}; ranks = {'Y01': [None]*len(days), 'Y04': [None]*len(days)}
    active = {k: [False]*len(days) for k in ranks}
    flags = {k: [False]*len(days) for k in ('bear', 'negative20', 'available')}
    for year in range(2018, 2025):
        folder = base/'folds'/str(year)
        seal, training, receipt = [read(folder/n) for n in ('seal.json', 'training.json', 'test-receipt.json')]
        assert seal['cutoff'] == training['cutoff'] == f'{year-1}-12-31' and not seal['current_test_read']
        assert sha(folder/'training.json') == seal['training_sha256']
        assert sha(folder/'seal.json') == receipt['seal_sha256']
        assert sha(folder/'predictions.json.gz') == receipt['predictions_sha256']
        assert not receipt['reserved_validation_read'] and receipt['fitting_calls'] == 0
        forecast = read(folder/'predictions.json.gz')
        assert forecast['dates'] == days[where[f'{year-1}-12-31']:where[f'{year}-12-31']]
        for name, values in forecast['scores'].items():
            scores.setdefault(name, [None]*len(days))
            for day, value in zip(forecast['dates'], values, strict=True):
                scores[name][where[day]] = value
        for name in ('U02', 'U04'):
            policies[name][year] = training['parent_policies'][name]
        if 'y01_policy' in training:
            policies['Y01'][year] = training['y01_policy']
        for name in choices:
            if 'parent_choices' in training:
                choices[name][year] = training['parent_choices'][name]
        if 'active' in training:
            assert forecast['active'] == training['active']
            for name, values in forecast['ranks'].items():
                for day, value in zip(forecast['dates'], values, strict=True):
                    ranks[name][where[day]] = value
                    active[name][where[day]] = training['active'][name]
        for day in forecast['dates']:
            flags['available'][where[day]] = True
        for name, values in forecast.get('short_flags', {}).items():
            for day, value in zip(forecast['dates'], values, strict=True):
                flags[name][where[day]] = value
    for table in [*policies.values(), *choices.values()]:
        if table:
            table[2025] = copy.deepcopy(table[2024])  # unused terminal decision, not a2025observation
    return dict(scores=scores, policies=policies, flags=flags, choices=choices, ranks=ranks, active=active)


def assemble(reg):
    days, prices = load_fold(2024, include_test=True)
    banks = {name: load_bank(base, days) for name, base in BANKS.items()}
    robust = b62.assemble(reg)
    assert robust[0] == days and robust[1] == prices
    return days, prices, banks, robust


def targets(values, recipe):
    days, prices, banks, robust = values; name, kind = recipe['id'], recipe['kind']
    if kind == 'ROBUST':
        return b63.targets(robust, next(r for r in b63.RECIPES if r['id'] == name))
    bank = banks[kind if kind in BANKS else 'AVERAGE']
    scores, policies = bank['scores'], bank['policies']
    if kind == 'CORE':
        return desired(days, prices, parent_score(scores, 'H03'), policies['Y01'])
    module = {'SHORT': b46, 'AVERAGE': b50, 'CARRY': b22, 'POST': b51, 'SIZE': b31}[kind]
    parent = next(r for r in module.RECIPES if r['id'] == name)
    if kind == 'SIZE':
        return b31.targets_and_permissions(days, prices, scores, policies, bank['choices'], bank['ranks'], bank['active'], parent)
    if kind == 'CARRY':
        return b22.targets_and_permissions(days, prices, scores, policies, parent)
    return module.targets_and_permissions(days, prices, scores, policies, bank['flags'], parent)


def replay():
    reg = read(STUDY/'registration.json'); reads = install_guard('replay'); verify(reg)
    values = assemble(reg); days, prices = values[:2]; results = []
    for recipe in RECIPES:
        rows, allowed = targets(values, recipe); summaries = {}; audits = {}; failures = {}
        for case in CASES:
            try:
                account = run_account(days, prices, rows, case, {}, end='2024-12-31', role='fold_train',
                    entry_permission=allowed, annual_settlement=False)
            except ValueError as exc:
                failures[case] = dict(type=type(exc).__name__, message=str(exc)); continue
            audits[case] = audit(account, days, prices, rows, CASES[case], BORROW[case], {}, allowed, False)
            if recipe['id'] in EXACT:
                base, name = EXACT[recipe['id']]
                assert account == read(base/'accounts'/name/f'{case}.json.gz')
            assert account == read(ORIGINAL/'accounts'/recipe['id']/f'{case}.json.gz')
            write(STUDY/'accounts'/recipe['id']/f'{case}.json.gz', account); summaries[case] = account['summary']
        results.append(dict(recipe=recipe, summaries=summaries, audits=audits, failures=failures, full_goal_gate=False))
        print('B64A RESULT', recipe['id'], summaries.get('STRESS', {}).get('return_pct'),
              max((s['max_drawdown_pct'] for s in summaries.values()), default=None), failures, flush=True)
    write(STUDY/'results.json', dict(results=results, end_year=2024, protected_reads=sorted(reads),
          new_fits=0, selections=0, validation_read=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('command', choices=('freeze', 'replay'))
    args = p.parse_args(); globals()[args.command]()
