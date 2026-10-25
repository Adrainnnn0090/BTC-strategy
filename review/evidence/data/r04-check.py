"""Feature dependency and source-clock checks; no models are fitted or accounts run."""
import ast
import bisect
import calendar
import gzip
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path('/workspace/BTCStrategyResearchLedger')
OUTPUT = Path('/workspace/BTCExpertReview/workspaces/data/r04-checks.json')


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(relative_path, names, namespace):
    module = ast.parse((ROOT/relative_path).read_text())
    nodes = [node for node in module.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    assert {node.name for node in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative_path, 'exec'), namespace)
    return namespace


features = extract('lab/signals.py', ('Features',), dict(np=np, pd=pd, lru_cache=lru_cache))['Features']
price_matrix = extract('lab/sgd.py', ('matrix',), dict(np=np, Features=features))['matrix']
tree_module = ast.parse((ROOT/'lab/tree_factors.py').read_text())
constants = {}
for node in tree_module.body:
    if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('GROUPS','PATH_NAMES','CAL_NAMES'):
        constants[node.targets[0].id] = ast.literal_eval(node.value)
matrix = extract('lab/tree_factors.py', ('matrix',), dict(np=np, pd=pd, calendar=calendar, date=date, price_matrix=price_matrix, **constants))['matrix']
append_volume = extract('lab/volume_short_factors.py', ('append_volume',), dict(np=np, date=date, timedelta=timedelta, matrix=matrix))['append_volume']
days = [(date(2017,1,1)+timedelta(days=i)).isoformat() for i in range(600)]
index = np.arange(len(days))
prices = 1000*np.exp(index*.0001+.01*np.sin(index/9)+.003*np.cos(index/27))


class ForbiddenObservations:
    def __iter__(self):
        raise AssertionError('PRICE47 attempted to read external observations')


price_rows = append_volume(days, prices, None, 7, 'PRICE47')
poison_rows = append_volume(days, prices, ForbiddenObservations(), 7, 'PRICE47')
assert price_rows.shape == (600,47) and np.array_equal(price_rows,poison_rows)
changed_prices = prices.copy()
changed_prices[401:] *= np.exp(np.arange(199)*.002)
changed_rows = append_volume(days, changed_prices, None, 7, 'PRICE47')
prefix_rows = append_volume(days[:401], prices[:401], None, 7, 'PRICE47')
assert np.array_equal(price_rows[:401], changed_rows[:401])
assert np.array_equal(price_rows[:401], prefix_rows)
assert not np.array_equal(price_rows[401:], changed_rows[401:])
observations = [dict(date=day,volume=str(1+i)) for i,day in enumerate(days)]
different_observations = [dict(date=day,volume=str(1+(i%17)**2)) for i,day in enumerate(days)]
assert np.array_equal(price_rows, append_volume(days,prices,observations,7,'PRICE47'))
assert np.array_equal(price_rows, append_volume(days,prices,different_observations,7,'PRICE47'))
assert not np.array_equal(append_volume(days,prices,observations,7,'VOL47'), append_volume(days,prices,different_observations,7,'VOL47'))
core = ROOT/'studies/B81-reported-volume-long-core'
core_reg = read(core/'registration.json')
assert next(row for row in core_reg['recipes'] if row['id']=='P02')['stream']=='PRICE_L7'
selected_model = read(core/'folds/2025/models/PRICE_L7.json.gz')
assert selected_model['feature_spec']==dict(id='PRICE_L7',group='PRICE47',lag=7)

lineage_specs = [
 ('B31-constant-sizing-controls','C04'), ('B30-forecast-strength-sizing','P08'),
 ('B29-prior-forecast-exits','Y04'), ('B22-annual-carry','H04'),
 ('B21-calendar-label-ablation','J06'), ('B20-execution-aware-labels','K13'),
 ('B19-robust-dynamics-models','R09'), ('B18-actual-entry-permission','E01'),
 ('B17-mining-dimension-ablation','A05'),
]
lineage = []
for name, identifier in lineage_specs:
    reg = read(ROOT/'studies'/name/'registration.json')
    lineage.append(dict(study=name, recipe=next(row for row in reg['recipes'] if row['id']==identifier)))
assert lineage[0]['recipe']['scale']==.75 and lineage[0]['recipe']['source']=='P08'
for i, key in ((1,'control'),(2,'control'),(3,'parent'),(4,'control'),(5,'control'),(6,'control'),(7,'parent')):
    assert lineage[i]['recipe'][key] == lineage[i+1]['recipe']['id']
assert lineage[-1]['recipe']['model']=='EXTRA_DYNAMICS_L60' and lineage[-1]['recipe']['lag']==60

mining_manifest = read(ROOT/'data/mining-lag-v1/manifest.json')
records = []
for role in ('train','test'):
    path = ROOT/f'data/mining-lag-v1/2025/{role}.json.gz'
    assert sha(path)==mining_manifest['files'][str(path.relative_to(ROOT))]['sha256']
    records.extend(read(path))
expected_days = [(date(2017,1,1)+timedelta(days=i)).isoformat() for i in range(3287)]
assert [row['date'] for row in records]==expected_days
mining_ns = dict(np=np, bisect=bisect, math=math, datetime=datetime, timezone=timezone,
                 LAGS=(60,120), CONFIRMATIONS=100, CLOCK_BUFFER_SECONDS=7200, MAX_AGE_DAYS=3.,
                 NAMES=tuple(mining_manifest['factor_names']))
mining_ns = extract('lab/mining_features.py', ('timestamp','advancing_observations','block_values','feature_rows','append_to_prices'), mining_ns)
freshness = Counter()
for row in records:
    item = row['lagged']['60']
    trace = item['trace']
    cutoff = (mining_ns['timestamp'](row['date'])-60*86400-7200)*1000
    assert trace['cutoff_ms']==cutoff and trace['confirmation_depth']==100
    observed = trace['observed_at_ms']
    assert observed is None or observed<=cutoff
    assert trace['confirmed_height']==trace['observed_height']-100
    age = (cutoff-observed)/86400000 if observed is not None else 90.
    fresh = observed is not None and age<=3 and trace['confirmed_height']>=24192
    assert trace['age_days']==age and trace['fresh']==fresh
    assert item['mask']==[float(fresh),math.log1p(min(age,90.))/math.log(91)]
    assert len(item['values'])==12 and np.isfinite(item['values']).all()
    assert fresh or item['values']==[0.]*12
    assert trace['availability']=='observer-recorded frontier; ancestor access and canonical survival assumed'
    freshness['fresh' if fresh else 'stale']+=1
assert freshness==Counter(fresh=3244,stale=43)
ablate = extract('lab/mining_ablation.py', ('ablate',), dict(np=np, append_to_prices=mining_ns['append_to_prices'], ARMS=('PAD','DYNAMICS','STATE')))['ablate']
joined = ablate(np.zeros((len(records),44)), records, 'DYNAMICS',60)
assert joined.shape==(3287,58) and (joined[:252]==0).all() and (joined[:,54:58]==0).all()
assert np.array_equal(joined[252:,44:46],np.array([row['lagged']['60']['mask'] for row in records[252:]]))
assert np.array_equal(joined[252:,46:54],np.array([row['lagged']['60']['values'][:8] for row in records[252:]]))

# Synthetic observations and headers only: future suffixes must not affect old factors.
sample_days = [(date(2018,1,1)+timedelta(days=i)).isoformat() for i in range(10)]
height = np.arange(26400)
times = mining_ns['timestamp']('2000-01-01')+height*600
targets = 1/(1+height*.00001)
work = np.arange(26401,dtype=float)*1000
observation = [(24500,mining_ns['timestamp']('2017-10-30')*1000),
               (24600,mining_ns['timestamp']('2017-11-02')*1000)]
baseline = mining_ns['feature_rows'](sample_days,times,targets,work,observation,lags=(60,))
future = observation+[(26100,mining_ns['timestamp']('2017-12-01')*1000)]
assert mining_ns['feature_rows'](sample_days,times,targets,work,future,lags=(60,))==baseline
late_old_height = observation+[(24550,mining_ns['timestamp']('2017-11-07')*1000)]
assert mining_ns['feature_rows'](sample_days,times,targets,work,late_old_height,lags=(60,))==baseline
altered_times, altered_targets, altered_work = times.copy(), targets.copy(), work.copy()
altered_times[25000:] += 100000
altered_targets[25000:] *= 2
altered_work[25001:] *= 2
assert mining_ns['feature_rows'](sample_days,altered_times,altered_targets,altered_work,observation,lags=(60,))==baseline

result = dict(status='PASS', price47=dict(selected_stream='P02→PRICE_L7→PRICE47 lag7',
                rows=600, columns=47, external_observation_poison_ignored=True,
                changed_external_volume_values_no_effect=True, vol47_positive_control_changes=True,
                future_price_suffix_from_index=401, prefix_unchanged_rows=401,
                prefix_truncation_exact=True),
              c04_lineage=lineage,
              mining=dict(checked_dates=3287,first=records[0]['date'],last=records[-1]['date'],lag_days=60,
                          clock_buffer_seconds=7200,confirmations=100,max_fresh_age_days=3,
                          freshness=dict(freshness),source_trace_schema_all_pass=True,
                          dynamics_columns='CAL44 | masks2 | dynamics8 | zeros4',
                          future_observation_suffix_invariance=True,future_header_suffix_invariance=True,
                          delayed_lower_height_does_not_refresh=True),
              qualifications=dict(mining=mining_manifest['qualification'],
                                  reported_volume_strict_PIT=read(ROOT/'data/reported-volume-walkforward-v1/manifest.json')['strict_PIT']),
              limitations=['Synthetic prefix invariance establishes implemented array causality, not historical publication or source-vintage truth.',
                           'Mining actual traces were checked; raw header/observer archives were not reopened.',
                           'PRICE47 does not numerically consume volume; B81 cohort still includes VOL47 siblings and their research history.',
                           'No 2026 economic observations, account files, model fitting, strategy search, or other expert artifacts were read.'])
with OUTPUT.open('x') as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({key:value for key,value in result.items() if key!='c04_lineage'},ensure_ascii=False,indent=2))
