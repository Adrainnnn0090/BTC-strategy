"""Round 04 exported input widths and pure synthetic feature checks; no fitting."""
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from datetime import date,timedelta
from pathlib import Path

SOURCE=Path('/workspace/BTCStrategyResearchLedger')
DELIVERY=Path('/workspace/BTC-strategy')
OWN=Path('/workspace/BTCExpertReview/workspaces/repro')

def raw(path):
    if any(part in str(path).lower() for part in ('2026','v01','v02')):
        raise ValueError('forbidden read path')
    return Path(path).read_bytes()

def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()

def read(path):
    data=raw(path)
    return json.loads(gzip.decompress(data) if str(path).endswith('.gz') else data)

manifest=read(DELIVERY/'models/manifest.json')
origins={
    'base_tree':('B10-seed-calendar-stability',44),
    'stop44':('B20-execution-aware-labels',44),
    'price47':('B81-reported-volume-long-core',47),
    'short_huber':('B67-lag-matched-short-supervision',44),
    'short_median':('B88A-short-net-loss-families',44),
    'mining58':('B17-mining-dimension-ablation',58),
}
file_checks=[]
numeric_estimators=0
for route in manifest:
    family=route['family'];origin,expected=origins[family]
    for item in route['files']:
        path=DELIVERY/item['path'];model=read(path)
        states=model['members'] if 'members' in model else [model['state']] if 'state' in model else [model]
        numeric_estimators+=len(states)
        max_features=[]
        for state in states:
            used=[int(feature) for tree in state['trees'] for feature in tree['feature'] if int(feature)>=0]
            max_features.append(max(used,default=-1))
        source=SOURCE/'studies'/origin/'folds'/str(route['fold_year'])/'models'/path.name
        file_checks.append({'family':family,'fold_year':route['fold_year'],'path':item['path'],
            'source_path':str(source.relative_to(SOURCE)),
            'expected_n_features':expected,'member_n_features':sorted(set(state['n_features'] for state in states)),
            'estimator_count':len(states),'largest_used_feature_index':max(max_features),
            'checks':{'manifest_digest':sha(path)==item['sha256'],'equals_frozen_origin':sha(path)==sha(source),
                'all_member_widths_match':all(state['n_features']==expected for state in states),
                'all_tree_indices_in_bounds':all(index<expected for index in max_features),
                'price47_spec_correct':family!='price47' or model['feature_spec']=={'group':'PRICE47','id':'PRICE_L7','lag':7},
                'mining58_spec_correct':family!='mining58' or model['spec']['kind']=='DYNAMICS' and model['spec']['lag']==60}})

source_files=('signals.py','sgd.py','tree_factors.py','volume_short_factors.py','mining_features.py','mining_ablation.py')
source_copy_matches={name:sha(SOURCE/'lab'/name)==sha(DELIVERY/'src/btc_strategy/_frozen/lab'/name) for name in source_files}

# These modules contain only pure feature functions/classes at import time.
# No io loader, label builder, estimator fit, strategy search, or account is called.
sys.path.insert(0,str(SOURCE))
import numpy as np
from lab.tree_factors import matrix,PATH_NAMES,CAL_NAMES
from lab.volume_short_factors import append_volume
from lab.mining_ablation import ablate
days=[(date(2017,1,1)+timedelta(days=i)).isoformat() for i in range(800)]
prices=[100*math.exp(.0005*i+.03*math.sin(i/17)) for i in range(800)]
vol_a=[{'date':day,'volume':str(1000+i)} for i,day in enumerate(days)]
vol_b=[{'date':day,'volume':str(1+(i%9)*90000)} for i,day in enumerate(days)]
class UntouchableObservations:
    def __iter__(self):
        raise AssertionError('PRICE47 must not access observations')
base=matrix(days,prices,'CAL44')
price_none=append_volume(days,prices,None,7,'PRICE47')
price_a=append_volume(days,prices,vol_a,7,'PRICE47')
price_b=append_volume(days,prices,vol_b,7,'PRICE47')
price_poison=append_volume(days,prices,UntouchableObservations(),7,'PRICE47')
volume_a=append_volume(days,prices,vol_a,7,'VOL47')
volume_b=append_volume(days,prices,vol_b,7,'VOL47')
changed=prices[:601]+[price*1.1 for price in prices[601:]]
changed_features=append_volume(days,changed,None,7,'PRICE47')
records=[{'lagged':{'60':{'mask':[1.,.25],'values':[float(k+1)/10 for k in range(12)]}}} for _ in days]
dynamics=ablate(base,records,'DYNAMICS',60)
synthetic_checks={
    'CAL44_shape':list(base.shape)==[800,44],
    'PRICE47_shape':list(price_none.shape)==[800,47],
    'PRICE47_independent_of_none_changed_poison_volume':all(np.array_equal(price_none,value) for value in (price_a,price_b,price_poison)),
    'VOL47_control_changes_with_volume':not np.array_equal(volume_a,volume_b),
    'PRICE47_first252_zero':bool(np.all(price_none[:252]==0)),
    'PRICE47_constant_available_column':bool(np.all(price_none[252:,44]==1)),
    'PRICE47_CAL44_prefix_exact':np.array_equal(price_none[:,:44],base),
    'PRICE47_prior_prefix_unchanged_after_future_price_perturbation':np.array_equal(price_none[:601],changed_features[:601]),
    'DYNAMICS58_shape':list(dynamics.shape)==[800,58],
    'DYNAMICS58_protocol_columns54to57_zero':bool(np.all(dynamics[:,54:58]==0)),
    'DYNAMICS58_first252_zero':bool(np.all(dynamics[:252]==0)),
}
export_manifest=read(DELIVERY/'provenance/export_manifest.json')
model_entries=[item for item in export_manifest['files'] if item.get('destination','').startswith('models/') and item.get('destination')!='models/manifest.json']
result={'round':4,'model_route_count':len(manifest),'model_file_count':len(file_checks),'numeric_estimator_count':numeric_estimators,
    'family_file_counts':dict(Counter(item['family'] for item in file_checks)),
    'model_file_checks':file_checks,'all_model_file_checks_pass':all(all(item['checks'].values()) for item in file_checks),
    'selected_source_copy_hash_matches':source_copy_matches,'pure_synthetic_checks':synthetic_checks,'all_synthetic_checks_pass':all(synthetic_checks.values()),
    'known_CAL44_tail_order_from_source':{'PATH_NAMES':list(PATH_NAMES),'CAL_NAMES':list(CAL_NAMES)},
    'manifest_rows_with_explicit_feature_order':sum(any(key in row for key in ('feature_order','feature_names','input_schema')) for row in manifest),
    'model_export_entries_without_source_locator':sum('source' not in item for item in model_entries),
    'model_export_entry_count':len(model_entries),
    'exported_mining_factor_partition_entries':sum('mining-lag-v1' in item.get('destination','') for item in export_manifest['files']),
    'raw_source_observation_material_opened':False,'trained_or_refitted':False,'account_replay_or_strategy_search':False,
    'source_or_delivery_written':False,'snapshot_limitation':'delivery is under construction; assertions cover this read snapshot only'}
with (OWN/'checks-r04.json').open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write('\n')
print(json.dumps({key:value for key,value in result.items() if key not in ('model_file_checks','known_CAL44_tail_order_from_source')},ensure_ascii=False,indent=2))
