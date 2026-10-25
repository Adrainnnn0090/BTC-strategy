"""Frozen label maturity check using only the 2025 physical training prefix."""
import ast
import gzip
import hashlib
import json
import math
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN
from pathlib import Path

ROOT = Path('/workspace/BTCStrategyResearchLedger')
OUTPUT = Path('/workspace/BTCExpertReview/workspaces/data/r03-checks.json')
START = date(2017, 1, 1)


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pure_functions(relative_path, names, namespace):
    module = ast.parse((ROOT/relative_path).read_text())
    nodes = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative_path, 'exec'), namespace)
    return namespace


class TrackedPrices(list):
    max_read = -1

    def __getitem__(self, key):
        assert isinstance(key, int) and 0 <= key < len(self)
        self.max_read = max(self.max_read, key)
        return super().__getitem__(key)


short_root = ROOT/'studies/B67-lag-matched-short-supervision'
loss_root = ROOT/'studies/B88A-short-net-loss-families'
long_root = ROOT/'studies/B36-network-activity-factors'
core_root = ROOT/'studies/B81-reported-volume-long-core'
metadata = []
for year in range(2019, 2026):
    short = read(short_root/f'folds/{year}/training.json')
    loss = read(loss_root/f'folds/{year}/training.json')
    core = read(core_root/f'folds/{year}/training.json')
    long_seal = read(long_root/f'folds/{year}/seal.json')
    cut = (date(year-1, 12, 31)-START).days
    ids = short['common_ids']
    assert ids == loss['common_ids'] and ids == sorted(set(ids))
    assert all(i+62 <= cut-6 for i in ids)
    assert loss['source_labels_sha256'] == short['labels_sha256']
    assert core['source_label_sha256'] == long_seal['label_sha256']['STOP']
    for training in (short, loss):
        assert training['cutoff'] == f'{year-1}-12-31'
        for records in training['receipts'].values():
            for receipt in records:
                assert receipt['cut'] == cut
                assert receipt['last'] == ids[-1]
                assert receipt['last_label'] == ids[-1]+60+receipt['execution_lag']
                assert receipt['common_last_label'] == ids[-1]+62 <= cut-6
    metadata.append(dict(fold=year, cutoff=short['cutoff'], common_count=len(ids),
                         common_last_index=ids[-1], common_maturity_date=(START+timedelta(days=ids[-1]+62)).isoformat(),
                         latest_allowed_date=(START+timedelta(days=cut-6)).isoformat(),
                         short_and_loss_support_equal=True, long_label_digest_binding=True))

prefix_path = ROOT/'data/walkforward-v1/2025/train.json'
manifest = read(ROOT/'data/walkforward-v1/manifest.json')
assert sha(prefix_path) == manifest['files']['data/walkforward-v1/2025/train.json']['sha256']
prefix = read(prefix_path)
days = [row['date'] for row in prefix]
assert days == [(START+timedelta(days=i)).isoformat() for i in range(len(prefix))]
assert days[-1] == '2024-12-31'
cut = len(days)-1
prices = TrackedPrices(row['price'] for row in prefix)
banks = read(short_root/'folds/2025/labels.json.gz')
short_training = read(short_root/'folds/2025/training.json')
loss_training = read(loss_root/'folds/2025/training.json')
assert sha(short_root/'folds/2025/labels.json.gz') == short_training['labels_sha256'] == loss_training['source_labels_sha256']
short_namespace = pure_functions('lab/short_payoff.py', ('quote', 'commission', 'path_label'),
    dict(D=Decimal, ROUND_CEILING=ROUND_CEILING, ROUND_FLOOR=ROUND_FLOOR,
         ROUND_HALF_EVEN=ROUND_HALF_EVEN, HORIZON=60, FEE=Decimal('.003'),
         SLIP=Decimal('.001'), ANNUAL=Decimal('.1'), CAPITAL=Decimal(100),
         FRACTION=Decimal('.25'), RESERVE=Decimal('.01')))
lag_namespace = pure_functions('lab/lagged_short.py', ('label',),
    dict(D=Decimal, ROUND_FLOOR=ROUND_FLOOR, lag1=short_namespace['path_label'],
         quote=short_namespace['quote'], commission=short_namespace['commission']))
short_stats = {}
for key, lag in (('L1', 1), ('L2', 2)):
    assert [row['index'] for row in banks[key]] == list(range(252, cut-67))
    for row in banks[key]:
        assert row['maturity_index'] == row['index']+60+lag <= cut-6
        prices.max_read = -1
        calculated = lag_namespace['label'](days, prices, row['index'], lag)
        assert calculated == row
        assert prices.max_read <= row['maturity_index'] <= cut-6
        if row['status'] == 'DEFINED':
            assert row['entry_index'] == row['index']+lag
            assert row['entry_index'] < row['exit_index'] <= row['maturity_index']
        else:
            assert row['status'] == 'UNEXECUTABLE' and row['simple_return'] is None
            assert days[row['index']+lag].endswith('-12-31')
    cross_year = [row for row in banks[key] if row['status']=='DEFINED' and days[row['entry_index']][:4] != days[row['exit_index']][:4]]
    short_stats[key] = dict(labels=len(banks[key]), statuses=dict(Counter(row['status'] for row in banks[key])),
                            cross_year_exits=len(cross_year),
                            latest_theoretical_maturity=days[max(row['maturity_index'] for row in banks[key])],
                            latest_actual_exit=days[max(row['exit_index'] for row in banks[key] if row['status']=='DEFINED')])
chosen = [a['index'] for a,b in zip(banks['L1'], banks['L2'], strict=True) if a['status']==b['status']=='DEFINED']
assert chosen == short_training['common_ids'] == loss_training['common_ids']
excluded = [a['index'] for a,b in zip(banks['L1'], banks['L2'], strict=True) if a['status']!='DEFINED' or b['status']!='DEFINED']
assert len(excluded) == 14
assert all(days[i].endswith(('-12-29', '-12-30')) for i in excluded)
assert chosen[-1]+62 == cut-6 and chosen[-1]+1+62 > cut-6

long_path = long_root/'folds/2025/labels/STOP.json.gz'
long_labels = read(long_path)
long_seal = read(long_root/'folds/2025/seal.json')
core_training = read(core_root/'folds/2025/training.json')
assert sha(long_path) == long_seal['label_sha256']['STOP'] == core_training['source_label_sha256']
long_namespace = pure_functions('lab/execution_labels.py', ('quotes', 'path_label'),
    dict(D=Decimal, ROUND_CEILING=ROUND_CEILING, ROUND_FLOOR=ROUND_FLOOR,
         FEE=Decimal('.003'), SLIP=Decimal('.001'), HORIZON=60,
         KINDS=('CLOSE','STOP','RISK'), math=math))
assert [row['index'] for row in long_labels] == list(range(252, cut-66))
for row in long_labels:
    assert row['maturity_index'] == row['index']+61 <= cut-6
    prices.max_read = -1
    calculated = long_namespace['path_label'](days, prices, row['index'], 'STOP')
    assert calculated == row
    assert prices.max_read <= row['maturity_index'] <= cut-6
    if row['entry_index'] is None:
        assert row['reason']=='FORBIDDEN_YEAR_END_ENTRY' and row['exit_index'] is None and row['log_return']==0
    else:
        assert row['entry_index']==row['index']+1
        assert row['entry_index'] < row['exit_index'] <= row['maturity_index']
year_close = [row for row in long_labels if row['reason']=='YEAR_CLOSE']
assert year_close
assert all(days[row['exit_index']].endswith('-12-31') and row['exit_index'] < row['maturity_index'] for row in year_close)
assert long_labels[-1]['index']+61 == cut-6
assert long_labels[-1]['index']+1+61 > cut-6

# Boundary failures are pure label calls with only the physical training prefix.
rejections = []
for name, function in (
    ('short_lag1', lambda:lag_namespace['label'](days, prices, cut-60, 1)),
    ('short_lag2', lambda:lag_namespace['label'](days, prices, cut-61, 2)),
    ('long_STOP', lambda:long_namespace['path_label'](days, prices, cut-60, 'STOP')),
):
    try:
        function()
    except ValueError as error:
        rejections.append(dict(name=name, error=str(error)))
    else:
        raise AssertionError('immature label unexpectedly accepted: '+name)

result = dict(status='PASS', metadata_years='2019–2025', metadata=metadata,
              representative_fold=2025, physical_prefix_end=days[-1], cutoff_index=cut,
              latest_label_allowed=days[cut-6], short=short_stats,
              common_ids=len(chosen), common_excluded_year_end_signal_dates=[days[i] for i in excluded],
              long=dict(labels=len(long_labels), reasons=dict(Counter(row['reason'] for row in long_labels)),
                        latest_theoretical_maturity=days[max(row['maturity_index'] for row in long_labels)],
                        latest_actual_exit=days[max(row['exit_index'] for row in long_labels if row['exit_index'] is not None)],
                        year_close_example={k:days[year_close[0][k]] for k in ('index','entry_index','exit_index','maturity_index')}),
              label_records_recomputed=sum(len(rows) for rows in banks.values())+len(long_labels),
              immature_prefix_rejections=rejections,
              method='Extracted original pure label functions; no ledger imports, writers, fitting, or account replay. Full representative label dictionaries compared exactly; price accesses bounded per label.',
              limitations=['Source-function re-evaluation is a maturity and reproducibility check, not an independent financial-pricing implementation.',
                           'Only the 2025 representative fold labels were recomputed; other annual folds used metadata/common-support bounds.',
                           'No test-price file, 2026 economic file, or other expert artifact was opened.'])
with OUTPUT.open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(json.dumps({key:value for key,value in result.items() if key not in ('metadata', 'common_excluded_year_end_signal_dates')}, ensure_ascii=False, indent=2))
