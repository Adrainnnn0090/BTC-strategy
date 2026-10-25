"""Candidate-bound offline export validation and two fixed final-estimator refits."""
import sys
sys.dont_write_bytecode=True
import copy,gzip,hashlib,json,math,os,subprocess
from pathlib import Path
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor,GradientBoostingRegressor
from threadpoolctl import threadpool_limits
ROOT=Path('/workspace/BTC-strategy')
LEDGER=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
def write_guard(event,args):
 if event!='open'or not isinstance(args[0],(str,bytes)):return
 p=Path(os.fsdecode(args[0])).resolve();mode=args[1]or'';flags=args[2]if len(args)>2 else 0
 if (p.is_relative_to(ROOT)or p.is_relative_to(LEDGER))and(any(c in mode for c in 'wax+')or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)):
  raise AssertionError('read-only candidate/source write blocked')
sys.addaudithook(write_guard)
sys.path.insert(0,str(ROOT/'src'))
import btc_strategy.models as models

def read(p):
 p=Path(p)
 assert p.is_relative_to(ROOT)or p.is_relative_to(LEDGER)
 assert not any(z in p.parts for z in ('2026','V01-2026-retained-validation','V02-buy-and-hold-validation'))
 b=p.read_bytes()
 return json.loads(gzip.decompress(b)if p.suffix=='.gz'else b)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
assert head=='1b008bfd4a9d1af9a73ff830fb7f8a1b72425fbf'
release=read(ROOT/'provenance/release_manifest.json')
assert len(release['files'])==886 and sum(f['bytes']for f in release['files'])==56444740
released={f['path']:f for f in release['files']}
manifest=read(ROOT/'models/manifest.json')
assert sha(ROOT/'models/manifest.json')==released['models/manifest.json']['sha256']
assert len(manifest)==48 and {(x['family'],x['fold_year'])for x in manifest}=={(f,y)for f in models.FAMILIES for y in range(2018,2026)}
states_by_key={};files=set();state_count=0;tree_count=0
family_counts={f:{'files':0,'states':0,'missing_years':[]}for f in models.FAMILIES}
for entry in manifest:
 family,year=entry['family'],entry['fold_year']
 assert entry['cutoff']==entry['decision_start']==f'{year-1}-12-31'and entry['decision_end']==f'{year}-12-30'
 assert (ROOT/entry['training_input']).is_file()
 rawstates=[]
 if entry['missing']:
  assert year==2018 and not entry['files']
  family_counts[family]['missing_years'].append(year)
 for item in entry['files']:
  relative=item['path'];p=ROOT/relative
  assert relative not in files and relative.split('/')[:3]==['models',family,str(year)]
  files.add(relative)
  assert sha(p)==item['sha256']==released[relative]['sha256']==sha(LEDGER/item['source'])
  assert p.stat().st_size==released[relative]['bytes']
  obj=read(p)
  if 'cutoff'in obj:assert obj['cutoff']==entry['cutoff']
  rawstates.extend(obj['members']if 'members'in obj else[obj.get('state',obj)])
  family_counts[family]['files']+=1
 for state in rawstates:
  assert state['n_features']==entry['feature_width'] and len(state['trees'])==96
  assert math.isfinite(state['initial'])and math.isfinite(state['weight'])
  for tree in state['trees']:
   size=len(tree['left'])
   assert size and all(len(tree[k])==size for k in ('right','feature','threshold','value'))
   for i,(left,right,feature,threshold,value)in enumerate(zip(*(tree[k]for k in ('left','right','feature','threshold','value')))):
    assert math.isfinite(threshold)and math.isfinite(value)
    if left==-1:assert right==-1 and feature<0
    else:assert i<left<size and i<right<size and 0<=feature<state['n_features']
   tree_count+=1
  state_count+=1;family_counts[family]['states']+=1
 actual=models.annual_states(family,year)
 assert sorted(rawstates,key=lambda s:(s.get('execution_lag',0),s['seed']))==actual
 states_by_key[(family,year)]=actual
assert len(files)==266 and state_count==392 and tree_count==37632
actual_paths={str(p.relative_to(ROOT))for family in models.FAMILIES for p in (ROOT/'models'/family).rglob('*.json.gz')}
assert actual_paths==files

source_streams={
 'base_tree':('B10-seed-calendar-stability','MEAN_CAL44'),
 'stop44':('B20-execution-aware-labels','CAL44_STOP'),
 'price47':('B81-reported-volume-long-core','PRICE_L7'),
 'short_huber':('B67-lag-matched-short-supervision','MEAN'),
 'short_median':('B88A-short-net-loss-families','MEDIAN'),
 'mining58':('B17-mining-dimension-ablation','EXTRA_DYNAMICS_L60')}
prices=read(ROOT/'artifacts/factors/prices.json.gz')
days=prices['days'];where={d:i for i,d in enumerate(days)}
assert days[0]=='2017-01-01'and days[-1]=='2025-12-31'and len(days)==3287
numeric=[]
for family,(study,stream)in source_streams.items():
 actual=models.reconstruct(family)
 expected=[None]*len(days)
 for year in range(2018,2026):
  old=read(LEDGER/'studies'/study/'folds'/str(year)/'predictions.json.gz')
  for day,v in zip(old['dates'],old['scores'][stream]):expected[where[day]]=v
 assert len(actual)==len(expected)and all((a is None)==(b is None)for a,b in zip(actual,expected))
 error=max(abs(a-b)for a,b in zip(actual,expected)if a is not None)
 assert error<=2e-12
 numeric.append({'family':family,'positions':len(actual),'finite':sum(v is not None for v in actual),
  'max_error_vs_original_fold_forecasts':error,'tolerance':2e-12,'availability_exact':True})

receipt=read(ROOT/'verification/final-estimator-refit-2025.json')
assert receipt['status']=='PASS'and len(receipt['families'])==6
assert sum(f['new_fits']for f in receipt['families'])==56
training_plans={}
for item in receipt['families']:
 family=item['family']
 p=read(ROOT/'training_inputs/2025'/f'{family}.json.gz')
 assert p['fold_year']==2025 and p['cutoff']==p['dates'][-1]=='2024-12-31'
 assert p['dates'][0]=='2017-01-01'and len(p['dates'])==len(p['features'])==2922
 assert p['cut_index']==2921 and p['embargo']==6
 assert len(p['ids'])==item['training_samples']
 assert max(p['ids'])+(62 if family.startswith('short_')else 61)<=p['cut_index']-6
 assert item['fold_year']==2025 and item['cutoff']==p['cutoff']and item['physical_rows']==2922
 assert all(s['numeric_state_exact']is True for s in item['states'])and len(item['states'])==item['new_fits']
 assert all(not z.startswith(('artifacts/','data/'))for z in item['protected_reads'])
 training_plans[family]=p

# Independently serialize the two fitted estimators; do not call training.refit
# or reuse its tree_state serializer as the refit equality oracle.
def dump_tree(estimator):
 t=estimator.tree_
 return {'left':t.children_left.tolist(),'right':t.children_right.tolist(),
         'feature':t.feature.tolist(),'threshold':t.threshold.tolist(),'value':t.value[:,0,0].tolist()}
refits=[]
for family,lag in (('stop44',None),('short_median',1)):
 p=training_plans[family]
 old=next(s for s in states_by_key[(family,2025)]if s['seed']==101 and s.get('execution_lag')==lag)
 x=np.asarray(p['features']);ids=np.asarray(p['ids'],dtype=int)
 y=np.asarray(p['targets']['L1']if lag else p['targets'])
 if old['family']=='EXTRA':est=ExtraTreesRegressor(n_jobs=1,random_state=101,**old['profile'])
 else:est=GradientBoostingRegressor(loss=old['spec']['loss'],alpha=old['spec']['alpha'],random_state=101,n_iter_no_change=None,**old['profile'])
 with threadpool_limits(limits=1):est.fit(x[ids],y)
 rebuilt=copy.deepcopy(old)
 rebuilt['trees']=[dump_tree(t)for t in (est.estimators_ if old['family']=='EXTRA'else est.estimators_.ravel())]
 if old['family']!='EXTRA':rebuilt['initial']=float(est.init_.constant_[0,0])
 assert rebuilt==old
 refits.append({'family':family,'fold_year':2025,'seed':101,'execution_lag':lag,
  'physical_rows':len(x),'training_samples':len(ids),'cutoff':p['cutoff'],
  'new_fits':1,'numeric_state_exact':True,'scope':'selected-final-estimator only; no inner-profile selection rerun'})

assert head==subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
result={'round':10,'all_checks_pass':True,'candidate_git':head,
 'release_declared_files':len(release['files']),'release_declared_bytes':sum(f['bytes']for f in release['files']),
 'release_manifest_sha256':sha(ROOT/'provenance/release_manifest.json'),'models_manifest_sha256':sha(ROOT/'models/manifest.json'),
 'family_year_entries':len(manifest),'numeric_files':len(files),'numeric_states':state_count,'numeric_trees':tree_count,
 'family_counts':family_counts,'all_numeric_files_source_manifest_release_sha_equal':True,
 'full_inference_vs_original_forecasts':numeric,'existing_2025_refit_receipt':{'families':6,'states':56,'physical_rows':2922,
  'training_period':'2017-01-01..2024-12-31','scope':receipt['scope'],'independently_reran_all56':False},
 'independent_bounded_refits':refits,'scope':'完整数字状态结构/哈希及六族离线推断；仅独立重拟两个2025已选最终状态，不是全部年度或inner-selection复现。'}
with (OUT/'r10_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
