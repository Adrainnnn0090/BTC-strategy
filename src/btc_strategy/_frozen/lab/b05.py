"""Annual refitting and train-only policy selection; all nine recipes reported."""
import argparse
import itertools
import json
import math
import subprocess
import sys
from importlib.metadata import version
import numpy as np
from threadpoolctl import threadpool_limits
from .io import ROOT, read, write, sha
from .walkforward_io import STUDY, FOLDS, install_guard, load_fold
from .sgd import matrix, tune, infer, matured, labels
from .signals import Features
from .margin_walkforward import run_account, CASES, BORROW
from .margin_walkforward_audit import audit
from .search import objective

MODELS = [dict(id=f'{family}_{group}_H{h}', family=family, group=group, horizon=h)
          for family, group, h in itertools.product(('HUBER', 'LOGIT', 'MLP'),
                                                    ('PRICE12', 'PRICE20'), (20, 60))]
MODEL_MAP = {m['id']: m for m in MODELS}
STATIC = 'FROZEN2018_HUBER_PRICE12_H60'
MODEL_MAP[STATIC] = {**MODEL_MAP['HUBER_PRICE12_H60'], 'id': STATIC}
RISK_BANK = [dict(fraction=f, stop_loss=.15, take_profit=1., cooldown_days=3,
                  trailing_stop=t, trail_arm=.5)
             for f, t in itertools.product((.65, .8, .95), (.1, .15))]
RISK_BANK += [dict(fraction=.8, stop_loss=.12, take_profit=2., cooldown_days=1,
                   trailing_stop=t, trail_arm=.2) for t in (.12, .2)]
RA = dict(fraction=.8, stop_loss=.15, take_profit=1., cooldown_days=3,
          trailing_stop=.12, trail_arm=.5)
RB = {**RA, 'trailing_stop': .1}
RC = dict(fraction=.9, stop_loss=.15, take_profit=3., cooldown_days=1,
          trailing_stop=.2, trail_arm=.2)
RECIPES = [
    dict(id='W01', model='HUBER_PRICE12_H60', mode='ENTRY', threshold=.03, short=False, risk=RA),
    dict(id='W02', model='HUBER_PRICE20_H60', mode='ENTRY', threshold=0., short=False, risk=RB),
    dict(id='W03', model='HUBER_PRICE20_H20', mode='DYNAMIC', threshold=0., short=True, risk=RC),
    dict(id='W04', model='LOGIT_PRICE20_H20', mode='DYNAMIC', threshold=.55, short=False, risk=RA),
    dict(id='W05', model='AUTO', mode='ENTRY', threshold=None, short=False, risk=RA),
    dict(id='W06', model='AUTO', mode='DYNAMIC', threshold=None, short=True, risk=RC),
    dict(id='W07', model='AUTO', mode='ENTRY', threshold=None, short=False, risk='AUTO'),
    dict(id='W08', model='AUTO', mode='DYNAMIC', threshold=None, short=True, risk='AUTO'),
    dict(id='W09', model=STATIC, mode='ENTRY', threshold=.03, short=False, risk=RA),
]


def forecast_year(day):
    return min(2025, max(2018, int(day[:4]) + int(day.endswith('-12-31'))))


def desired_targets(days, prices, scores, policies):
    parent = Features(prices).targets(dict(family='BAND', params=dict(n=100, band=.03),
                                          risk=dict(vol_target=0.)))
    mean = Features(prices).mean(100)
    active = False
    negative = 0
    current = None
    targets = []
    for i, day in enumerate(days):
        year = forecast_year(day)
        cfg = policies[year]
        if year != current:
            active, negative, current = False, 0, year
        model = MODEL_MAP[cfg['model']]
        score = scores[cfg['model']][i]
        if score is None or not parent[i]['long']:
            active, negative = False, 0
        else:
            exit_value = -.01 if model['family'] == 'HUBER' else cfg['threshold'] - .15
            negative = negative + 1 if score < exit_value else 0
            if cfg['mode'] == 'DYNAMIC' and negative >= 2:
                active = False
            elif not active and score > cfg['threshold']:
                active = True
        bearish = i >= 252 and prices[i] < mean[i] * .97
        direction = 1 if active else -1 if cfg['short'] and bearish else 0
        risk = cfg['risk']
        targets.append(dict(direction=direction, long_fraction=risk['fraction'],
                            short_fraction=.5 if cfg['short'] else 0., policy_year=year,
                            risk=dict(long={k: v for k, v in risk.items() if k != 'fraction'},
                                      short=dict(stop_loss=.12, take_profit=.5,
                                                 cooldown_days=3, trailing_stop=0., trail_arm=.1))))
    return targets


def normalized_loss(receipt, prices, model):
    trial = receipt['trials'][receipt['selected']]
    ratios = []
    for fold in trial['folds']:
        train = matured(fold['first'], model['horizon'])
        history = labels(prices, train, model['horizon'])
        truth = labels(prices, np.arange(fold['first'], fold['last'] + 1), model['horizon'])
        if model['family'] == 'HUBER':
            null = float(np.mean((truth - history.mean()) ** 2))
        else:
            prob = float(np.clip(np.mean(history > 0), 1e-8, 1-1e-8))
            y = truth > 0
            null = float(-np.mean(y * math.log(prob) + (~y) * math.log(1-prob)))
        ratios.append(fold['loss'] / max(null, 1e-12))
    return float(np.mean(ratios))


def policy(recipe, chosen, risk=None):
    model = chosen if recipe['model'] == 'AUTO' else recipe['model']
    threshold = recipe['threshold']
    if threshold is None:
        threshold = .01 if MODEL_MAP[model]['family'] == 'HUBER' else .55
    return {**recipe, 'model': model, 'threshold': threshold,
            'risk': risk if risk is not None else recipe['risk']}


def historical_scores(days, year):
    result = {name: [None] * len(days) for name in MODEL_MAP}
    where = {d: i for i, d in enumerate(days)}
    receipts = {}
    for previous in range(2018, year):
        folder = STUDY / 'folds' / str(previous)
        receipt = read(folder / 'test-receipt.json')
        path = folder / 'predictions.json.gz'
        if sha(path) != receipt['predictions_sha256']:
            raise ValueError('historical predictions changed')
        artifact = read(path)
        for key, values in artifact['scores'].items():
            for day, value in zip(artifact['dates'], values, strict=True):
                if day in where:
                    result[key][where[day]] = value
        receipts[str(previous)] = sha(folder / 'test-receipt.json')
    return result, receipts


def verify():
    reg = read(STUDY / 'registration.json')
    for name, digest in reg['sources'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('frozen source changed: ' + name)
    if sha(FOLDS / 'manifest.json') != reg['data_manifest_sha256']:
        raise ValueError('partition manifest changed')
    for name, expected in reg['versions'].items():
        if version(name) != expected:
            raise ValueError('dependency version changed: ' + name)
    return reg


def freeze():
    sources = ['lab/b05.py', 'lab/walkforward_io.py', 'lab/sgd.py', 'lab/signals.py',
               'lab/io.py', 'lab/native.py', 'lab/audit.py', 'lab/search.py',
               'lab/margin_walkforward.py', 'lab/margin_walkforward_audit.py',
               'tests/test_b05.py', 'WALKFORWARD_AUTHORIZATION.md',
               'studies/B05-annual-walkforward/spec.md']
    write(STUDY / 'registration.json', dict(
        models=MODELS, recipes=RECIPES, risk_bank=RISK_BANK, years=list(range(2018, 2026)),
        model_member_fit_cap=1512, risk_selection_account_cap=384, final_account_cap=36,
        target_return_pct=10000, max_drawdown_strict_pct=35,
        sources={p: sha(ROOT / p) for p in sources},
        data_manifest_sha256=sha(FOLDS / 'manifest.json'),
        versions={p: version(p) for p in ('numpy', 'pandas', 'nautilus-trader', 'threadpoolctl')},
        costs=CASES, annual_short_financing=BORROW,
        claims='chronological annual folds on previously consumed history; not fresh blind OOS'))
    print('B05 FROZEN', sha(STUDY / 'registration.json'), flush=True)


def train(year):
    reads = install_guard(year, 'train')
    verify()
    folder = STUDY / 'folds' / str(year)
    if (folder / 'seal.json').exists():
        raise ValueError('fold already sealed')
    days, prices = load_fold(year)
    cut = len(days) - 1
    states, ranked, cold = {}, [], []
    rows = {g: matrix(prices, g) for g in ('PRICE12', 'PRICE20')}
    fit_count = 0
    with threadpool_limits(limits=1):
        for m in MODELS:
            try:
                ids = matured(cut, m['horizon'])
                matured(int(ids[-120:-60][0]), m['horizon'])
            except (ValueError, IndexError):
                cold.append(m['id'])
                continue
            members, receipt = tune(rows[m['group']], prices, cut, m['horizon'], m['family'])
            loss = normalized_loss(receipt, prices, m)
            path = folder / 'models' / (m['id'] + '.json.gz')
            write(path, dict(model=m, members=members, receipt=receipt,
                             cutoff=days[-1], normalized_internal_loss=loss))
            states[m['id']] = sha(path)
            ranked.append((loss, m['id']))
            fit_count += 18
    chosen = min(ranked)[1] if ranked else 'HUBER_PRICE12_H60'
    past, past_receipts = historical_scores(days, year)
    policies, risk_trials = {}, []
    for recipe in RECIPES:
        risk = recipe['risk']
        if risk == 'AUTO':
            risk = RISK_BANK[0]
            if year >= 2020:
                trials = []
                for k, candidate in enumerate(RISK_BANK):
                    cfg = policy(recipe, chosen, candidate)
                    # Past predictions were generated by their original annual models.
                    # The current final model is never backfilled over prior years.
                    targets = desired_targets(days, prices, past,
                                              {y: cfg for y in range(2018, year + 1)})
                    summaries, audits = {}, {}
                    for case in CASES:
                        account = run_account(days, prices, targets, case, {},
                                              end=days[-1], role='fold_train')
                        audits[case] = audit(account, days, prices, targets, CASES[case], BORROW[case], {})
                        summaries[case] = account['summary']
                    trials.append(dict(recipe=recipe['id'], risk_index=k, summaries=summaries,
                                       audits=audits, objective=objective(summaries)))
                selected = max(trials, key=lambda t: (t['objective'], -t['risk_index']))
                risk = RISK_BANK[selected['risk_index']]
                risk_trials.extend(trials)
        policies[recipe['id']] = policy(recipe, chosen, risk)
    write(folder / 'training.json', dict(year=year, cutoff=days[-1], model_fits=fit_count,
                                        cold_models=cold, model_ranking=sorted(ranked),
                                        risk_trials=risk_trials, policies=policies,
                                        prior_receipts=past_receipts, protected_reads=sorted(reads)))
    write(folder / 'seal.json', dict(year=year, model_sha256=states,
                                   training_sha256=sha(folder / 'training.json'),
                                   registration_sha256=sha(STUDY / 'registration.json'),
                                   train_sha256=sha(FOLDS / str(year) / 'train.json'),
                                   cutoff=days[-1], current_test_read=False))
    print('FOLD TRAIN SEALED', year, 'fits', fit_count, 'auto', chosen,
          'risk_accounts', len(risk_trials) * 4, flush=True)


def test(year):
    reads = install_guard(year, 'test')
    verify()
    folder = STUDY / 'folds' / str(year)
    seal = read(folder / 'seal.json')
    if seal['current_test_read'] or seal['cutoff'] != f'{year-1}-12-31':
        raise ValueError('fold not frozen before test')
    if seal['registration_sha256'] != sha(STUDY / 'registration.json'):
        raise ValueError('registration differs from seal')
    if seal['training_sha256'] != sha(folder / 'training.json'):
        raise ValueError('training receipt changed')
    if seal['train_sha256'] != sha(FOLDS / str(year) / 'train.json'):
        raise ValueError('training partition changed')
    models = {}
    for name, digest in seal['model_sha256'].items():
        path = folder / 'models' / (name + '.json.gz')
        if sha(path) != digest:
            raise ValueError('sealed model changed')
        models[name] = read(path)
    # First current-year price access occurs only after verifying the complete seal.
    days, prices = load_fold(year, include_test=True)
    first = days.index(f'{year-1}-12-31')
    last = days.index(f'{year}-12-31')  # Dec31 decision belongs to next year's model.
    rows = {g: matrix(prices, g) for g in ('PRICE12', 'PRICE20')}
    scores = {}
    for m in MODELS:
        scores[m['id']] = (infer(models[m['id']]['members'], rows[m['group']][first:last]).tolist()
                           if m['id'] in models else [None] * (last-first))
    if year == 2018:
        scores[STATIC] = [None] * (last-first)
    else:
        control_folder = STUDY / 'folds/2019'
        control_seal = read(control_folder / 'seal.json')
        control_path = control_folder / 'models/HUBER_PRICE12_H60.json.gz'
        if sha(control_path) != control_seal['model_sha256']['HUBER_PRICE12_H60']:
            raise ValueError('frozen first-fit control changed')
        control = read(control_path)
        if control['cutoff'] != '2018-12-31':
            raise ValueError('control training clock changed')
        scores[STATIC] = infer(control['members'], rows['PRICE12'][first:last]).tolist()
    write(folder / 'predictions.json.gz', dict(dates=days[first:last], scores=scores))
    write(folder / 'test-receipt.json', dict(year=year, seal_sha256=sha(folder / 'seal.json'),
                                           predictions_sha256=sha(folder / 'predictions.json.gz'),
                                           test_sha256=sha(FOLDS / str(year) / 'test.json'),
                                           fitting_calls=0, protected_reads=sorted(reads),
                                           reserved_validation_read=False))
    print('FOLD TEST FROZEN', year, len(days[first:last]), 'decision rows', flush=True)


def replay():
    reads = install_guard(2025, 'replay')
    verify()
    days, prices = load_fold(2025, include_test=True)
    scores = {name: [None] * len(days) for name in MODEL_MAP}
    where = {day: i for i, day in enumerate(days)}
    policies = {r['id']: {} for r in RECIPES}
    folds = []
    for year in range(2018, 2026):
        folder = STUDY / 'folds' / str(year)
        receipt = read(folder / 'test-receipt.json')
        seal = read(folder / 'seal.json')
        if sha(folder / 'seal.json') != receipt['seal_sha256'] or sha(folder / 'training.json') != seal['training_sha256']:
            raise ValueError('fold chain differs')
        prediction = read(folder / 'predictions.json.gz')
        if sha(folder / 'predictions.json.gz') != receipt['predictions_sha256']:
            raise ValueError('forecast differs')
        training = read(folder / 'training.json')
        for name, values in prediction['scores'].items():
            for day, value in zip(prediction['dates'], values, strict=True):
                scores[name][where[day]] = value
        for name, cfg in training['policies'].items():
            policies[name][year] = cfg
        folds.append(dict(year=year, training_sha256=seal['training_sha256'],
                          test_receipt_sha256=sha(folder / 'test-receipt.json'),
                          model_fits=training['model_fits'], risk_accounts=len(training['risk_trials'])*4))
    results = []
    for recipe in RECIPES:
        name = recipe['id']
        targets = desired_targets(days, prices, scores, policies[name])
        summaries, audits = {}, {}
        for case in CASES:
            account = run_account(days, prices, targets, case, {}, end='2025-12-31', role='target_replay')
            audits[case] = audit(account, days, prices, targets, CASES[case], BORROW[case], {})
            summaries[case] = account['summary']
            write(STUDY / 'accounts' / name / f'{case}.json.gz', account)
        passed = summaries['STRESS']['return_pct'] >= 10000 and max(s['max_drawdown_pct'] for s in summaries.values()) < 35
        results.append(dict(id=name, policies=policies[name], summaries=summaries, audits=audits, target_pass=passed))
        print('B05 RESULT', name, round(summaries['STRESS']['return_pct'], 2),
              round(max(s['max_drawdown_pct'] for s in summaries.values()), 2), passed, flush=True)
    write(STUDY / 'results.json', dict(results=results, folds=folds, protected_reads=sorted(reads),
                                     reserved_validation_read=False, registration_sha256=sha(STUDY / 'registration.json'),
                                     scope='continuous annual walk-forward account; consumed historical research, not fresh blind OOS'))


def run():
    for year in range(2018, 2026):
        for stage in ('train', 'test'):
            subprocess.run([sys.executable, '-m', 'lab.b05', stage, '--year', str(year)], check=True, cwd=ROOT)
    subprocess.run([sys.executable, '-m', 'lab.b05', 'replay'], check=True, cwd=ROOT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('freeze', 'train', 'test', 'replay', 'run'))
    parser.add_argument('--year', type=int, choices=range(2018, 2026))
    args = parser.parse_args()
    if args.command in ('train', 'test'):
        if args.year is None:
            parser.error('--year is required')
        globals()[args.command](args.year)
    else:
        globals()[args.command]()
