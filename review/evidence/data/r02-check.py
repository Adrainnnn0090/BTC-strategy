"""Read-only original-family fold/date seam check; outputs only role-local evidence."""
import ast
import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path('/workspace/BTCStrategyResearchLedger')
OUTPUT = Path('/workspace/BTCExpertReview/workspaces/data/r02-checks.json')
START = date(2017, 1, 1)


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dates(first, last):
    return [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]


module = ast.parse((ROOT/'lab/b05.py').read_text())
function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'forecast_year')
namespace = {}
exec(compile(ast.Module(body=[function], type_ignores=[]), 'b05.py:forecast_year', 'exec'), namespace)
forecast_year = namespace['forecast_year']

families = {
    'B81-reported-volume-long-core': ('model_fits', 175),
    'B67-lag-matched-short-supervision': ('fits', 14),
    'B88A-short-net-loss-families': ('fits', 56),
}
manifest = read(ROOT/'data/walkforward-v1/manifest.json')
results = []
combined_dates = {}
for name, (fit_key, fit_count) in families.items():
    study = ROOT/'studies'/name
    reg = read(study/'registration.json')
    combined_dates[name] = []
    for year in range(2019, 2026):
        folder = study/'folds'/str(year)
        training, seal, receipt, prediction = [read(folder/n) for n in ('training.json', 'seal.json', 'test-receipt.json', 'predictions.json.gz')]
        cutoff = date(year-1, 12, 31)
        cut_index = (cutoff-START).days
        expected = dates(cutoff, date(year, 12, 30))
        assert training['year'] == year
        assert training['cutoff'] == seal['cutoff'] == cutoff.isoformat()
        assert training[fit_key] == fit_count
        assert seal['training_sha256'] == sha(folder/'training.json')
        assert seal['registration_sha256'] == sha(study/'registration.json')
        assert receipt['seal_sha256'] == sha(folder/'seal.json')
        assert receipt['predictions_sha256'] == sha(folder/'predictions.json.gz')
        assert seal['train_sha256'] == manifest['files'][f'data/walkforward-v1/{year}/train.json']['sha256']
        assert receipt['test_sha256'] == manifest['files'][f'data/walkforward-v1/{year}/test.json']['sha256']
        assert not seal['current_test_read'] and not receipt['validation_read']
        assert receipt['fitting_calls'] == receipt['selection_calls'] == 0
        assert prediction['dates'] == expected
        assert all(len(series) == len(expected) for series in prediction['scores'].values())
        assert all(forecast_year(day) == year for day in expected)
        assert not any('/2026/' in path or 'V01' in path or 'V02' in path for path in training['protected_reads']+receipt['protected_reads'])
        assert f'data/walkforward-v1/{year}/test.json' not in training['protected_reads']
        if name.startswith('B81'):
            # PRICE_L7 is the P02 long-core stream actually inherited by the selected chain.
            model_path = folder/'models/PRICE_L7.json.gz'
            assert sha(model_path) == training['model_states']['models/PRICE_L7.json.gz']
            model = read(model_path)
            assert model['cutoff'] == cutoff.isoformat()
            assert model['feature_spec']['id'] == 'PRICE_L7'
            assert len(model['members']) == 7
            final_receipts = [item['receipt'] for item in model['receipt']['details']]
            assert all(item['cut'] == cut_index for item in final_receipts)
            assert all(item['last_label'] <= cut_index-6 for item in final_receipts)
            final_label_index = max(item['last_label'] for item in final_receipts)
        else:
            final_receipts = [item for group in training['receipts'].values() for item in group]
            assert len(final_receipts) == fit_count
            assert all(item['cut'] == cut_index for item in final_receipts)
            assert all(item['common_last_label'] <= cut_index-6 for item in final_receipts)
            final_label_index = max(item['common_last_label'] for item in final_receipts)
        combined_dates[name].extend(expected)
        results.append(dict(family=name, fold=year, cutoff=cutoff.isoformat(), fits=fit_count,
                            signal_first=expected[0], signal_last=expected[-1], signal_count=len(expected),
                            lag1_first=(cutoff+timedelta(days=1)).isoformat(),
                            lag1_last=(date(year, 12, 30)+timedelta(days=1)).isoformat(),
                            latest_declared_label_date=(START+timedelta(days=final_label_index)).isoformat(),
                            train_seal_prediction_hash_chain='PASS'))
    assert combined_dates[name] == dates(date(2018, 12, 31), date(2025, 12, 30))
assert len({tuple(value) for value in combined_dates.values()}) == 1

seams = []
for year in range(2020, 2026):
    previous_last_signal = date(year-1, 12, 30)
    current_first_signal = date(year-1, 12, 31)
    assert forecast_year(previous_last_signal.isoformat()) == year-1
    assert forecast_year(current_first_signal.isoformat()) == year
    # carry_native.py:59 bars a new entry whose signal's policy year differs from the account date.
    old_lag2_account_date = previous_last_signal+timedelta(days=2)
    assert old_lag2_account_date == date(year, 1, 1)
    assert forecast_year(previous_last_signal.isoformat()) != old_lag2_account_date.year
    seams.append(dict(year=year, old_signal=previous_last_signal.isoformat(),
                      new_signal=current_first_signal.isoformat(),
                      lag1_new_first=(current_first_signal+timedelta(days=1)).isoformat(),
                      lag2_new_first=(current_first_signal+timedelta(days=2)).isoformat(),
                      lag2_stale_policy_new_entry_blocked=True))

result = dict(status='PASS', families=3, checked_folds=21, source_period='2019–2025 folds only',
              signal_rows_per_family=len(next(iter(combined_dates.values()))),
              family_fit_totals={name:sum(row['fits'] for row in results if row['family']==name) for name in families},
              folds=results, cross_year_seams=seams,
              limitations=['Only relevant B81 PRICE_L7 model packages were decoded; unrelated models were not opened.',
                           'Training receipts state label bounds; raw label payoff correctness was not audited in this check.',
                           'Decision mappings are date arithmetic plus inspected execution code; no account replay was run.',
                           'No 2026 economic file, validation account, or other expert artifact was opened.'])
with OUTPUT.open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(json.dumps({key:value for key,value in result.items() if key not in ('folds', 'cross_year_seams')}, ensure_ascii=False, indent=2))
