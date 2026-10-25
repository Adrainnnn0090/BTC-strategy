"""Independent two-window model/data export binding check; writes only role-local evidence."""
import ast
import bisect
import calendar
import gzip
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE = Path('/workspace/BTCStrategyResearchLedger')
NEW = Path('/workspace/BTC-strategy')
FROZEN = NEW/'src/btc_strategy/_frozen'
OUTPUT = Path('/workspace/BTCExpertReview/workspaces/data/r05-checks.json')
FAMILIES = ('base_tree','stop44','price47','short_huber','short_median','mining58')


def read(path):
    assert not any(item in path.parts for item in ('2026','V01-2026-retained-validation','V02-buy-and-hold-validation','review','verification'))
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(relative, names, namespace):
    module = ast.parse((FROZEN/relative).read_text())
    nodes = [node for node in module.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names]
    assert {node.name for node in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),relative,'exec'),namespace)
    return namespace


bound_code = ('lab/signals.py','lab/sgd.py','lab/tree_factors.py','lab/volume_short_factors.py','lab/mining_features.py','lab/mining_ablation.py')
assert all(sha(FROZEN/path)==sha(SOURCE/path) for path in bound_code)
Features = extract('lab/signals.py',('Features',),dict(np=np,pd=pd,lru_cache=lru_cache))['Features']
price_matrix = extract('lab/sgd.py',('matrix',),dict(np=np,Features=Features))['matrix']
constants = {}
for node in ast.parse((FROZEN/'lab/tree_factors.py').read_text()).body:
    if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('GROUPS','PATH_NAMES','CAL_NAMES'):
        constants[node.targets[0].id]=ast.literal_eval(node.value)
matrix = extract('lab/tree_factors.py',('matrix',),dict(np=np,pd=pd,calendar=calendar,date=date,price_matrix=price_matrix,**constants))['matrix']
append_volume = extract('lab/volume_short_factors.py',('append_volume',),dict(np=np,date=date,timedelta=timedelta,matrix=matrix))['append_volume']
append_to_prices = extract('lab/mining_features.py',('append_to_prices',),dict(np=np,LAGS=(60,120)))['append_to_prices']
ablate = extract('lab/mining_ablation.py',('ablate',),dict(np=np,append_to_prices=append_to_prices,ARMS=('PAD','DYNAMICS','STATE')))['ablate']


def feature_sets(market):
    base = matrix(market['days'],market['prices'],'CAL44')
    return dict(base_tree=base,stop44=base,price47=append_volume(market['days'],market['prices'],None,7,'PRICE47'),
                short_huber=base,short_median=base,mining58=ablate(base,market['mining'],'DYNAMICS',60))


def tree_values(tree, rows):
    # Independent traversal: recursively partition row positions at each numeric node.
    result = np.empty(len(rows),dtype=float)
    stack = [(0,np.arange(len(rows)))]
    while stack:
        node,positions = stack.pop()
        if not len(positions):
            continue
        left,right = tree['left'][node],tree['right'][node]
        if left==-1:
            assert right==-1
            result[positions]=tree['value'][node]
        else:
            # Preserve float64 thresholds: NumPy weak Python scalars would otherwise
            # coerce a scalar threshold to float32 and change boundary routing.
            select = rows[positions,tree['feature'][node]].astype(np.float64)<=tree['threshold'][node]
            stack.append((left,positions[select]))
            stack.append((right,positions[~select]))
    return result


def numeric_predict(state,rows):
    # Numeric tree routing follows sklearn's documented float32 input conversion.
    rows = np.asarray(rows,dtype=np.float32)
    output = np.full(len(rows),state['initial'],dtype=float)
    for tree in state['trees']:
        output += state['weight']*tree_values(tree,rows)
    return output


market = read(NEW/'artifacts/factors/market.json.gz')
assert market['days'][0]=='2017-01-01' and market['days'][-1]=='2025-12-31'
price_rows = read(SOURCE/'data/walkforward-v1/2025/train.json')+read(SOURCE/'data/walkforward-v1/2025/test.json')
mining_rows = read(SOURCE/'data/mining-lag-v1/2025/train.json.gz')+read(SOURCE/'data/mining-lag-v1/2025/test.json.gz')
assert market['days']==[row['date'] for row in price_rows]
assert market['prices']==[row['price'] for row in price_rows] and market['mining']==mining_rows
features = feature_sets(market)
manifest = read(NEW/'models/manifest.json')
assert len(manifest)==48 and len({(row['family'],row['fold_year']) for row in manifest})==48
high = read(NEW/'artifacts/contexts/high_return.json.gz')
median = read(NEW/'artifacts/contexts/median.json.gz')
sizing = read(NEW/'artifacts/contexts/sizing.json.gz')
context_reference = dict(base_tree=high[0]['scores']['BASE_TREE'],stop44=high[1]['scores']['CAL44_STOP'],
                         price47=high[0]['scores']['CAL44_STOP'],short_huber=high[0]['learner'],
                         short_median=median[1]['MEDIAN'],mining58=sizing[2]['EXTRA_DYNAMICS_L60'])
source_prediction = dict(base_tree=('B10-seed-calendar-stability','MEAN_CAL44'),
                         stop44=('B20-execution-aware-labels','CAL44_STOP'),
                         price47=('B81-reported-volume-long-core','PRICE_L7'),
                         short_huber=('B67-lag-matched-short-supervision','MEAN'),
                         short_median=('B88A-short-net-loss-families','MEDIAN'),
                         mining58=('B17-mining-dimension-ablation','EXTRA_DYNAMICS_L60'))
results = []
checked_models = 0
for year in (2019,2025):
    first = market['days'].index(f'{year-1}-12-31')
    last = market['days'].index(f'{year}-12-31')
    prefix_market = {key:value[:first+1] for key,value in market.items() if key in ('days','prices','mining')}
    prefix_features = feature_sets(prefix_market)
    short_training = read(SOURCE/f'studies/B67-lag-matched-short-supervision/folds/{year}/training.json')
    short_labels = read(SOURCE/f'studies/B67-lag-matched-short-supervision/folds/{year}/labels.json.gz')
    long_labels = read(SOURCE/f'studies/B36-network-activity-factors/folds/{year}/labels/STOP.json.gz')
    long_map = {row['index']:row['log_return'] for row in long_labels}
    for family in FAMILIES:
        entry = next(row for row in manifest if row['family']==family and row['fold_year']==year)
        assert not entry['missing'] and entry['files']
        assert entry['cutoff']==entry['decision_start']==f'{year-1}-12-31'
        assert entry['decision_end']==f'{year}-12-30'
        training = read(NEW/entry['training_input'])
        assert training['family']==family and training['fold_year']==year and training['cut_index']==first
        assert training['cutoff']==entry['cutoff'] and training['embargo']==6 and not training['model_missing']
        assert training['dates']==market['days'][:first+1]
        assert np.array_equal(np.asarray(training['features']),prefix_features[family])
        assert np.array_equal(prefix_features[family],features[family][:first+1])
        ids = training['ids']
        assert ids==sorted(set(ids)) and ids[0]>=252
        if family.startswith('short_'):
            assert ids==short_training['common_ids'] and ids[-1]+62<=first-6
            for head in ('L1','L2'):
                label_map = {row['index']:row for row in short_labels[head]}
                assert training['targets'][head]==[label_map[i]['simple_return'] for i in ids]
                assert all(label_map[i]['status']=='DEFINED' for i in ids)
            label_kind='SHORT_NET simple_return; shared L1/L2 ids'
        else:
            assert ids==list(range(252,first-66)) and ids[-1]+61<=first-6
            if family in ('stop44','price47'):
                assert training['targets']==[long_map[i] for i in ids]
                label_kind='STOP path log_return with original YEAR_CLOSE semantics'
            else:
                p=np.asarray(prefix_market['prices'])
                cost=math.log((1+.001)/((1-.001)*(1-.003)**2))
                expected=np.log(p[np.asarray(ids)+61]/p[np.asarray(ids)+1])-cost
                assert np.array_equal(np.asarray(training['targets']),expected)
                label_kind='60-day next-entry log_return minus original fixed cost'
        states = []
        for item in entry['files']:
            source_path = SOURCE/item['source']
            model_path = NEW/item['path']
            digest = sha(model_path)
            assert digest==item['sha256']==sha(source_path)
            folder = source_path.parent.parent
            seal = read(folder/'seal.json')
            original_training = read(folder/'training.json')
            assert seal['cutoff']==original_training['cutoff']==entry['cutoff'] and not seal['current_test_read']
            assert seal['training_sha256']==sha(folder/'training.json')
            if 'model_sha256' in seal:
                assert seal['model_sha256'][source_path.name.removesuffix('.json.gz')]==digest
            else:
                assert original_training['model_states'][str(source_path.relative_to(folder))]==digest
            packet = read(model_path)
            assert packet.get('cutoff',entry['cutoff'])==entry['cutoff']
            states.extend(packet['members'] if 'members' in packet else [packet.get('state',packet)])
            checked_models += 1
        assert all(state['n_features']==entry['feature_width']==features[family].shape[1] for state in states)
        rows = features[family][first:last]
        states.sort(key=lambda state:(state.get('execution_lag',0),state['seed']))
        if family.startswith('short_'):
            assert {state['execution_lag'] for state in states}=={1,2}
            heads=[np.mean([numeric_predict(state,rows) for state in states if state['execution_lag']==lag],axis=0) for lag in (1,2)]
            predicted=(heads[0]+heads[1])/2
        else:
            predicted=np.mean([numeric_predict(state,rows) for state in states],axis=0)
        study,key = source_prediction[family]
        original = read(SOURCE/f'studies/{study}/folds/{year}/predictions.json.gz')
        assert original['dates']==market['days'][first:last]
        expected=original['scores'][key]
        exported=context_reference[family][first:last]
        assert expected==exported and all(value is not None for value in expected)
        error=float(np.max(np.abs(predicted-np.asarray(expected))))
        assert error<=2e-12,(family,year,error)
        results.append(dict(family=family,year=year,signal_first=original['dates'][0],signal_last=original['dates'][-1],
                            positions=len(predicted),members=len(states),feature_width=entry['feature_width'],
                            labels=label_kind,training_rows=len(training['dates']),training_ids=len(ids),
                            actual_model_source_seal_digest='PASS',training_feature_prefix_exact=True,
                            training_labels_exact=True,availability_exact=True,max_forecast_error=error))

cold = []
for family in FAMILIES:
    entry=next(row for row in manifest if row['family']==family and row['fold_year']==2018)
    training=read(NEW/entry['training_input'])
    assert entry['missing'] and not entry['files'] and training['model_missing'] and not training['ids'] and not training['targets']
    first=market['days'].index('2017-12-31');last=market['days'].index('2018-12-31')
    assert all(value is None for value in context_reference[family][first:last])
    cold.append(dict(family=family,year=2018,missing_states=True,empty_training_ids=True,null_forecasts=last-first,zero_filled=False))

result=dict(status='PASS',windows=[2019,2025],checked_family_windows=len(results),checked_raw_model_files=checked_models,
            market_rows=len(market['days']),market_source_dates_prices_mining_exact=True,
            model_manifest_family_years=48,exported_feature_code_matches_source=list(bound_code),
            results=results,cold_start=cold,
            max_forecast_error=max(row['max_forecast_error'] for row in results),tolerance=2e-12,
            limitations=['Forecast check covers two annual windows, not every exported model year.',
                         'Features use extracted frozen pure transforms; numeric tree traversal is independently implemented here.',
                         'No fit/refit CLI was exercised and no claim is made about future CLI completeness.',
                         'No 2026 data, account replay, other expert review, or chair artifact was read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({key:value for key,value in result.items() if key not in ('results','cold_start')},ensure_ascii=False,indent=2))
