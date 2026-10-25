"""Frozen-package data inventory, physical-prefix and isolated-read boundary check."""
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

SOURCE=Path('/workspace/BTCStrategyResearchLedger')
NEW=Path('/workspace/BTC-strategy')
OUTPUT=Path('/workspace/BTCExpertReview/workspaces/data/r10-checks.json')


def read(path):
    assert not any(part in path.parts for part in ('review','verification','2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


release=read(NEW/'provenance/release_manifest.json')
assert len(release['files'])==886 and sum(item['bytes'] for item in release['files'])==56444740
assert len({item['path'] for item in release['files']})==886
assert release['source_period']==['2017-01-01','2025-12-31'] and release['economic2026excluded']
for item in release['files']:
    relative=item['path'];path=(NEW/relative).resolve()
    assert path.is_relative_to(NEW) and not relative.startswith(('review/','verification/'))
    assert not re.search(r'(?:^|[/_-])20(?:2[6-9]|[3-9][0-9])(?:$|[/_.-])|(?:^|/)v0[12](?:$|[/_.-])',relative,re.I)
    assert path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
export=read(NEW/'provenance/export_manifest.json')
source_copy_count=0
for item in export['files']:
    destination=NEW/item['destination']
    assert sha(destination)==item['sha256']
    if 'source' in item:
        original=(SOURCE/item['source']).resolve()
        assert original.is_relative_to(SOURCE) and '/V01' not in str(original) and '/V02' not in str(original)
        assert sha(original)==item['sha256']
        source_copy_count+=1
manifest=read(NEW/'models/manifest.json')
model_copy_count=0
for entry in manifest:
    year=entry['fold_year']
    assert type(year) is int and 2018<=year<=2025
    assert entry['cutoff']==entry['decision_start']==f'{year-1}-12-31' and entry['decision_end']==f'{year}-12-30'
    for item in entry['files']:
        assert sha(NEW/item['path'])==item['sha256']==sha(SOURCE/item['source'])
        model_copy_count+=1
assert source_copy_count==332 and model_copy_count==266
assert len(export['files'])==source_copy_count+model_copy_count==598

market=read(NEW/'artifacts/factors/market.json.gz')
prices=read(NEW/'artifacts/factors/prices.json.gz')
mining=read(NEW/'artifacts/factors/mining.json.gz')
assert prices['days']==market['days'] and prices['prices']==market['prices'] and mining['mining']==market['mining']
expected_days=[(date(2017,1,1)+timedelta(days=i)).isoformat() for i in range(3287)]
assert market['days']==expected_days
source_prices=read(SOURCE/'data/walkforward-v1/2025/train.json')+read(SOURCE/'data/walkforward-v1/2025/test.json')
source_mining=read(SOURCE/'data/mining-lag-v1/2025/train.json.gz')+read(SOURCE/'data/mining-lag-v1/2025/test.json.gz')
assert market['days']==[row['date'] for row in source_prices]
assert market['prices']==[row['price'] for row in source_prices] and market['mining']==source_mining
catalog=read(NEW/'artifacts/catalog.json')['strategies']
economic_accounts=0;account_marks=0
for strategy in catalog:
    target=read(NEW/f'artifacts/targets/{strategy["id"]}.json.gz')
    assert len(target['targets'])==len(target['entry_permission'])==3287
    assert all(2018<=row['policy_year']<=2025 for row in target['targets'])
    for case in ('BASE','STRESS','SEVERE','DELAY'):
        packet=read(NEW/f'artifacts/accounts/{strategy["id"]}/{case}.json.gz')
        original=SOURCE/strategy['source_study']/'accounts'/strategy['recipe']['id']/f'{case}.json.gz'
        assert sha(NEW/f'artifacts/accounts/{strategy["id"]}/{case}.json.gz')==sha(original)
        assert [row['date'] for row in packet['marks']]==expected_days[365:]
        for key in ('fills','orders','financing'):
            assert all('2018-01-01'<=row['date']<='2025-12-31' for row in packet[key])
        assert all('2018-01-01'<=row['entry_date']<=row['exit_date']<='2025-12-31' for row in packet['trades'])
        account_marks+=len(packet['marks']);economic_accounts+=1

plans=[]
for entry in manifest:
    family,year=entry['family'],entry['fold_year']
    plan=read(NEW/entry['training_input'])
    cutoff=f'{year-1}-12-31';rows=(date(year-1,12,31)-date(2017,1,1)).days+1
    assert plan['family']==family and plan['fold_year']==year and plan['cutoff']==cutoff
    assert plan['dates']==expected_days[:rows] and plan['cut_index']==rows-1 and plan['embargo']==6
    assert len(plan['features'])==rows and all(len(row)==entry['feature_width'] for row in plan['features'])
    assert all(math.isfinite(value) for row in plan['features'] for value in row)
    ids=plan['ids'];maturity=62 if family.startswith('short_') else 61
    if plan['model_missing']:
        assert year==2018 and entry['missing'] and not ids and not plan['targets']
    else:
        assert not entry['missing'] and ids==sorted(set(ids)) and ids[0]>=252 and ids[-1]+maturity<=rows-1-6
        targets=plan['targets'].values() if family.startswith('short_') else [plan['targets']]
        assert all(len(values)==len(ids) and all(math.isfinite(value) for value in values) for values in targets)
    plans.append(dict(family=family,fold_year=year,rows=rows,cutoff=cutoff,maturity=maturity,
                      training_ids=len(ids),physical_prefix_only=True))
assert len(plans)==48

# Copy only runnable source and raw data. No review or verification conclusions enter the probe.
isolated=Path(tempfile.mkdtemp(prefix='btc-data-r10-'))
for directory in ('src','models','training_inputs','artifacts'):
    shutil.copytree(NEW/directory,isolated/directory,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
os.environ['BTC_STRATEGY_ROOT']=str(isolated)
sys.path=[str(isolated/'src')]+[path for path in sys.path if path and not path.startswith(str(NEW)) and not path.startswith(str(SOURCE))]
blocked_roots=(NEW,SOURCE,Path('/workspace/BinanceTradingRobot/backend/src'),
               Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'),
               Path('/workspace/Polymarket_Arbitrage_Robot'))
opened=[];network_attempts=[]


def audit_hook(event,args):
    if event in ('socket.connect','socket.bind'):
        network_attempts.append(event)
        raise PermissionError('network disabled for isolated data probe')
    if event!='open' or not isinstance(args[0],(str,bytes)):
        return
    path=Path(os.fsdecode(args[0])).resolve()
    legacy_project=Path('/workspace/BinanceTradingRobot')
    dependency_venv=legacy_project/'backend/.venv'
    if path.is_relative_to(legacy_project) and not path.is_relative_to(dependency_venv):
        raise PermissionError('isolated probe attempted legacy project access: '+str(path))
    if any(path.is_relative_to(root) for root in blocked_roots):
        raise PermissionError('isolated probe attempted old repository/project access: '+str(path))
    if path.is_relative_to(isolated):
        opened.append(str(path.relative_to(isolated)))


sys.addaudithook(audit_hook)
from btc_strategy import artifacts,models,training
from btc_strategy.validation import development_market
assert artifacts.ROOT==isolated
offline_forecasts=[models.verify_family(family) for family in ('price47','mining58')]
feature_prefix_checks=[]
for family in models.FAMILIES:
    full_features=models.feature_matrix(family,market)
    for year in range(2018,2026):
        plan=artifacts.read(f'training_inputs/{year}/{family}.json.gz')
        import numpy as np
        assert np.array_equal(full_features[:len(plan['dates'])],np.asarray(plan['features']))
        feature_prefix_checks.append(dict(family=family,fold_year=year,feature_prefix_exact=True))

denied_paths=['../BTCStrategyResearchLedger/data/x.json',str(SOURCE/'data/walkforward-v1/2025/train.json'),
              'provenance/studies/B10/registration.json','review/rounds/01/chair.json',
              'models/base_tree/2026/model.json.gz','training_inputs/2027/base_tree.json.gz',
              'artifacts/factors/economic-2028.json','artifacts/V01/rows.json','artifacts/v02-unsafe/rows.json']
path_rejections=[]
for relative in denied_paths:
    before=len(opened)
    try:
        artifacts.read(relative)
    except ValueError as error:
        assert len(opened)==before
        path_rejections.append(dict(path=relative,error=str(error),denied_before_open=True))
    else:
        raise AssertionError('forbidden artifact accepted: '+relative)
before=len(opened)
try:
    models.annual_states('base_tree',2026)
except ValueError:
    assert len(opened)==before
else:
    raise AssertionError('future model-year accepted')
training_predicates=[]
for relative,expected in [('training_inputs/2025/price47.json.gz',True),('models/manifest.json',True),
                          ('models/price47/2025/PRICE_L7.json.gz',True),('training_inputs/2025/stop44.json.gz',False),
                          ('training_inputs/2026/price47.json.gz',False),('artifacts/factors/prices.json.gz',False),
                          ('provenance/export_manifest.json',False),('review/rounds/01/chair.json',False)]:
    actual=training.training_read_allowed(isolated/relative,'price47',2025)
    assert actual is expected
    training_predicates.append(dict(path=relative,allowed=actual))
assert not training.training_read_allowed(SOURCE/'data/walkforward-v1/2025/train.json','price47',2025)
outside_probe=Path('/tmp/data-r10-outside-economic-2026.json')
outside_policy=training.training_read_allowed(outside_probe,'price47',2025)
assert outside_policy is True  # Predicate only: no outside file is created or opened.
future_clock_rejected=False
try:
    development_market(['2017-01-01','2026-01-01'],[1.,1.])
except ValueError:
    future_clock_rejected=True
assert future_clock_rejected and not network_attempts
assert not any(name.startswith('btc_strategy._frozen') for name in sys.modules)

result=dict(status='PASS_BOUNDED',candidate_git='1b008bfd4a9d1af9a73ff830fb7f8a1b72425fbf',
            release_files_verified=886,release_actual_bytes_verified=56444740,
            original_file_copies_verified=source_copy_count,model_file_copies_verified=model_copy_count,
            benchmark_book_copies_verified=economic_accounts,benchmark_mark_rows_date_checked=account_marks,
            market_rows=3287,economic_dates=['2017-01-01','2025-12-31'],
            combined_and_split_factors_exact=True,physical_training_prefixes=plans,
            all_48_training_feature_prefixes_exact=True,
            isolated_root=str(isolated),offline_forecasts=offline_forecasts,
            isolated_opened_paths=sorted(set(opened)),network_attempts=0,
            denied_artifact_paths=path_rejections,future_model_year_denied_before_open=True,
            synthetic_future_clock_rejected_before_features=True,training_role_predicates=training_predicates,
            residual_boundary=dict(outside_root_training_read_predicate=outside_policy,
                                   example_path=str(outside_probe),example_file_opened=False,
                                   interpretation='training_read_allowed permits arbitrary non-legacy ROOT-external paths; it is not a complete filesystem capability sandbox. Normal refit code explicitly requests current plan/model files.'),
            limitations=['The isolated probe uses already installed Python/dependencies from the supplied environment, not a fresh dependency install or Docker build.',
                         'No fit/refit or account writer was run; two inference families were exercised offline and all 48 training prefixes were checked.',
                         'Training label payoff equations were not recomputed for all 48 exports in this round.',
                         'No review/verification conclusions, V01/V02, or actual 2026 economic observations were opened.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({key:value for key,value in result.items() if key not in ('physical_training_prefixes','isolated_opened_paths','denied_artifact_paths','training_role_predicates')},ensure_ascii=False,indent=2))
