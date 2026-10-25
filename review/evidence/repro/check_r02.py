"""Round 02: frozen annual routing and seal metadata, no research-module execution."""
import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

SOURCE = Path('/workspace/BTCStrategyResearchLedger')
OWN = Path('/workspace/BTCExpertReview/workspaces/repro')

def raw(path):
    path = Path(path)
    relative = str(path.relative_to(SOURCE))
    if any(token in relative.lower() for token in ('2026', 'v01', 'v02')):
        raise ValueError('forbidden source path: ' + relative)
    return path.read_bytes()

def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()

def read(path):
    data = raw(path)
    return json.loads(gzip.decompress(data) if str(path).endswith('.gz') else data)

families = {
    'B31': 'B31-constant-sizing-controls',
    'B50': 'B50-cross-market-fixed-averages',
    'B67': 'B67-lag-matched-short-supervision',
    'B81': 'B81-reported-volume-long-core',
    'B88A': 'B88A-short-net-loss-families',
    'B109': 'B109-long-profit-local-coordinate',
}
manifest = read(SOURCE/'data/walkforward-v1/manifest.json')
rows = []
state_samples = []
for family, name in families.items():
    study = SOURCE/'studies'/name
    registration_sha = sha(study/'registration.json')
    for year in range(2018, 2026):
        folder = study/'folds'/str(year)
        training, seal, receipt = [read(folder/name) for name in ('training.json', 'seal.json', 'test-receipt.json')]
        expected_cutoff = f'{year-1}-12-31'
        start = date(year-1, 12, 31)
        end = date(year, 12, 31)
        expected_dates = [(start+timedelta(days=i)).isoformat() for i in range((end-start).days)]
        forecast = read(folder/'predictions.json.gz')
        checks = {
            'cutoff': training['cutoff'] == seal['cutoff'] == expected_cutoff,
            'current_test_not_read': seal['current_test_read'] is False,
            'training_digest': sha(folder/'training.json') == seal['training_sha256'],
            'registration_digest': registration_sha == seal['registration_sha256'],
            'train_manifest_digest': seal['train_sha256'] == manifest['files'][f'data/walkforward-v1/{year}/train.json']['sha256'],
            'receipt_seal_digest': receipt['seal_sha256'] == sha(folder/'seal.json'),
            'receipt_test_manifest_digest': receipt['test_sha256'] == manifest['files'][f'data/walkforward-v1/{year}/test.json']['sha256'],
            'receipt_prediction_digest': receipt['predictions_sha256'] == sha(folder/'predictions.json.gz'),
            'test_zero_fit_calls': receipt['fitting_calls'] == 0,
            'no_true_validation_flag': not receipt.get('validation_read',False) and not receipt.get('reserved_validation_read',False),
            'prediction_dates_exact': forecast['dates'] == expected_dates,
        }
        states = training.get('model_states')
        available_counts = {key: sum(value is not None for value in values) for key, values in forecast.get('scores',{}).items()}
        row = {
            'family': family, 'fold_year': year, 'cutoff': expected_cutoff,
            'inference_date_start_inclusive': expected_dates[0],
            'inference_date_end_exclusive': end.isoformat(),
            'last_inference_date': expected_dates[-1],
            'date_count': len(expected_dates),
            'model_states_count': len(states) if isinstance(states,dict) else None,
            'fit_count': training.get('fits',training.get('model_fits')),
            'score_nonnull_counts': available_counts,
            'checks': checks, 'all_checks_pass': all(checks.values()),
        }
        rows.append(row)
        if year == 2019 and states:
            sample = sorted(states)[0]
            state = read(folder/sample)
            record = {'family':family,'path':str((folder/sample).relative_to(SOURCE)),'state_keys':sorted(state),'digest_match':sha(folder/sample)==states[sample]}
            if 'cutoff' in state:
                record['embedded_cutoff'] = state['cutoff']
                record['embedded_cutoff_matches_fold'] = state['cutoff'] == expected_cutoff
            if 'receipts' in training:
                cuts = []
                for values in training['receipts'].values():
                    for item in values:
                        if 'cut' in item:
                            cuts.append(item['cut'])
                record['receipt_cut_indices'] = sorted(set(cuts))
                record['expected_cut_index_from_calendar'] = (date(2018,12,31)-date(2017,1,1)).days
            state_samples.append(record)

def route_by_window(decision_date):
    eligible = [year for year in range(2018,2026) if date(year-1,12,31) <= decision_date < date(year,12,31)]
    if len(eligible) != 1:
        raise ValueError('decision outside registered model windows')
    return eligible[0]

boundary_cases = []
for text, expected in [('2017-12-31',2018),('2018-12-30',2018),('2018-12-31',2019),('2019-01-01',2019),('2024-12-31',2025),('2025-12-30',2025)]:
    actual = route_by_window(date.fromisoformat(text))
    boundary_cases.append({'synthetic_decision_date':text,'expected_fold':expected,'actual_fold':actual,'pass':actual==expected})
rejected = []
for text in ('2017-12-30','2025-12-31'):
    try:
        route_by_window(date.fromisoformat(text))
    except ValueError:
        rejected.append(text)

result = {
    'round':2,'families':families,'folds_checked':len(rows),
    'all_annual_checks_pass':all(row['all_checks_pass'] for row in rows),
    'annual_checks':rows,'sample_2019_state_metadata':state_samples,
    'synthetic_window_router_boundary_cases':boundary_cases,
    'synthetic_outside_window_rejected':rejected,
    'synthetic_router_is_export_implementation':False,
    'source_research_module_executed':False,
    'source_or_delivery_written':False,
    'forbidden_source_paths_opened':False,
    'delivery_manifest_available':False,
}
with (OWN/'checks-r02.json').open('x') as handle:
    json.dump(result,handle,ensure_ascii=False,indent=2)
    handle.write('\n')
print(json.dumps({'folds_checked':len(rows),'all_annual_checks_pass':result['all_annual_checks_pass'],
    '2018_model_contracts':[row for row in rows if row['fold_year']==2018 and row['family'] in ('B67','B81','B88A')],
    'sample_2019_state_metadata':state_samples,'boundary_cases':boundary_cases,'rejected':rejected},ensure_ascii=False,indent=2))
