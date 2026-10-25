"""Read-only round 1 inspection. No ledger imports or ledger writes."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path('/workspace/BTCStrategyResearchLedger')
OUT = Path('/workspace/BTCExpertReview/workspaces/models')
assert str(ROOT) != str(OUT)

def read(p):
    p = Path(p)
    assert p.is_relative_to(ROOT) or p.is_relative_to(Path('/workspace/BTCExpertReview/shared'))
    assert not any(x in str(p) for x in ('/V01-', '/V02-', '/folds/2026/', '/accounts/2026/'))
    if p.suffix == '.gz':
        with gzip.open(p, 'rt') as f:
            return json.load(f)
    return json.loads(p.read_text())

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

STUDIES = {
    'b109': 'B109-long-profit-local-coordinate',
    'b107': 'B107-cold-short-profit-trailing',
    'b105': 'B105-cold-entry-momentum',
    'b106': 'B106-shorter-cold-entry-momentum',
    'b88a': 'B88A-short-net-loss-families',
    'b72': 'B72-cold-budget-exposure',
    'b31': 'B31-constant-sizing-controls',
    'b81': 'B81-reported-volume-long-core',
    'b67': 'B67-lag-matched-short-supervision',
    'b50': 'B50-cross-market-fixed-averages',
}

def folder(key, y):
    assert 2018 <= y <= 2025
    return ROOT / 'studies' / STUDIES[key] / 'folds' / str(y)

checks = {}
manifest = read(Path('/workspace/BTCExpertReview/shared/source_manifest.json'))
checks['shared_manifest_sha256'] = {
    p: sha(ROOT / p) == digest for p, digest in manifest['files'].items()
}
checks['nine_lab_source_binding'] = {}
regs = {}
for key, name in STUDIES.items():
    reg = read(ROOT / 'studies' / name / 'registration.json')
    regs[key] = reg
    if key != 'b50':
        source = f'lab/{key}.py'
        checks['nine_lab_source_binding'][key] = reg['sources'][source] == sha(ROOT / source)

checks['annual_seal_binding'] = {}
checks['annual_training_inventory'] = {}
for key in ('b109', 'b107', 'b105', 'b106', 'b88a', 'b31', 'b81', 'b67', 'b50'):
    stats = []
    checks['annual_seal_binding'][key] = []
    for y in range(2018, 2026):
        f = folder(key, y)
        tr, seal, receipt = (read(f / n) for n in ('training.json', 'seal.json', 'test-receipt.json'))
        checks['annual_seal_binding'][key].append({
            'year': y,
            'pass': all((tr['cutoff'] == seal['cutoff'] == f'{y-1}-12-31',
                         not seal['current_test_read'],
                         sha(f/'training.json') == seal['training_sha256'],
                         sha(f/'seal.json') == receipt['seal_sha256'],
                         sha(f/'predictions.json.gz') == receipt['predictions_sha256'])),
        })
        model_states = tr.get('model_states', {})
        assert all((f / p).is_file() for p in model_states)
        stats.append({'year':y, 'fits':tr.get('fits',tr.get('model_fits')),
                      'state_files':len(model_states), 'selection_calls':tr.get('selection_calls'),
                      'inner_profile_selections':tr.get('inner_profile_selections')})
    checks['annual_training_inventory'][key] = stats

checks['shared_forecast_identity'] = []
checks['b31_parent_forecast_identity'] = []
checks['b88a_common_training_support'] = []
for y in range(2018,2026):
    a,b,c = (read(folder(k,y)/'predictions.json.gz') for k in ('b81','b50','b67'))
    expected = dict(dates=a['dates'], scores={'BASE_TREE':b['scores']['BASE_TREE'],
                    'CAL44_STOP':a['scores']['PRICE_L7']}, learner=c['scores']['MEAN'],
                    flags={k:b['short_flags'][k] for k in ('bear','negative20')})
    assert a['dates']==b['dates']==c['dates']
    for k in ('b109','b107','b105','b106'):
        actual=read(folder(k,y)/'predictions.json.gz')
        checks['shared_forecast_identity'].append({'year':y,'study':k,'pass':actual==expected})
    size=read(folder('b31',y)/'predictions.json.gz')
    parent=read(ROOT/'studies/B30-forecast-strength-sizing/folds'/str(y)/'predictions.json.gz')
    size.pop('active')
    checks['b31_parent_forecast_identity'].append({'year':y,'pass':size==parent})
    loss=read(folder('b88a',y)/'training.json')
    old=read(folder('b67',y)/'training.json')
    checks['b88a_common_training_support'].append({'year':y,'pass':loss['common_ids']==old['common_ids'] and
        (loss['source_labels_sha256']==old['labels_sha256'] if loss['common_ids'] else loss['source_labels_sha256'] is None)})

def all_pass(value):
    if isinstance(value,dict):
        return all(all_pass(v) for v in value.values())
    if isinstance(value,list):
        return all(all_pass(v) for v in value)
    return value is True if isinstance(value,bool) else True

checks['all_checked_equalities_pass'] = all_pass({k:v for k,v in checks.items() if k!='annual_training_inventory'})
assert checks['all_checked_equalities_pass']
with (OUT/'r01_checks.json').open('x') as f:
    json.dump(checks,f,ensure_ascii=False,indent=2)
print(json.dumps({'all_checked_equalities_pass':checks['all_checked_equalities_pass'],
    'manifest_files':len(checks['shared_manifest_sha256']), 'source_bindings':len(checks['nine_lab_source_binding']),
    'annual_seals':sum(len(v) for v in checks['annual_seal_binding'].values()),
    'forecast_equalities':len(checks['shared_forecast_identity']),
    'b31_parent_equalities':len(checks['b31_parent_forecast_identity']),
    'b88a_training_support_equalities':len(checks['b88a_common_training_support']),
    'training_inventory':checks['annual_training_inventory']},ensure_ascii=False))
