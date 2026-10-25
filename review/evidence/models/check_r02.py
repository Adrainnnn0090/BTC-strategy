"""Round 2: read-only annual numeric model, selection receipt, and inference contracts."""
import ast
from datetime import date, timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path('/workspace/BTCStrategyResearchLedger')
OUT = Path('/workspace/BTCExpertReview/workspaces/models')
SEEDS = [101,307,509,701,907,1103,1701]
FAMILIES = {
 'BASE_TREE': ('B10-seed-calendar-stability', 'b10', ['EXTRA_CAL44_H60_S101','EXTRA_CAL44_H60_S1701'], ['MEAN_CAL44'], 44),
 'STOP44': ('B20-execution-aware-labels','b20',['CAL44_STOP'],['CAL44_STOP'],44),
 'PRICE_L7': ('B81-reported-volume-long-core','b81',['PRICE_L7'],['PRICE_L7'],47),
 'B67': ('B67-lag-matched-short-supervision','b67',['L1-101','L2-101'],['L1','L2','MEAN'],44),
 'B88A_MEDIAN': ('B88A-short-net-loss-families','b88a',['MEDIAN_L1-101','MEDIAN_L2-101'],['MEDIAN_L1','MEDIAN_L2','MEDIAN'],44),
 'H04': ('B17-mining-dimension-ablation','b17',['EXTRA_DYNAMICS_L60'],['EXTRA_DYNAMICS_L60'],58),
}
def read(p):
 p = Path(p)
 assert p.is_relative_to(ROOT)
 assert not any(x in str(p) for x in ('/V01-','/V02-','/folds/2026/'))
 if p.suffix=='.gz':
  with gzip.open(p,'rt') as f: return json.load(f)
 return json.loads(p.read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

records=[]
selection_count=0
inner_fit_count=0
reuse_count=0
numeric_file_count=0
for family,(study,code,names,streams,width) in FAMILIES.items():
 for year in range(2018,2026):
  folder=ROOT/'studies'/study/'folds'/str(year)
  tr,seal,test=(read(folder/n) for n in ('training.json','seal.json','test-receipt.json'))
  cutoff=f'{year-1}-12-31'
  cut=(date.fromisoformat(cutoff)-date(2017,1,1)).days
  assert tr['cutoff']==seal['cutoff']==cutoff
  assert not seal['current_test_read']
  assert sha(folder/'training.json')==seal['training_sha256']
  assert sha(folder/'seal.json')==test['seal_sha256']
  assert sha(ROOT/'studies'/study/'registration.json')==seal['registration_sha256']
  assert test['fitting_calls']==0
  assert test.get('selection_calls',0)==0
  pred=read(folder/'predictions.json.gz')
  start=date(year-1,12,31)
  expected=[(start+timedelta(days=i)).isoformat() for i in range((date(year,12,31)-start).days)]
  assert pred['dates']==expected
  assert all(len(pred['scores'][s])==len(expected) for s in streams)
  absence=all(all(v is None for v in pred['scores'][s]) for s in streams)
  assert absence==(year==2018)
  if year>2018:
   assert all(all(isinstance(v,(int,float)) and math.isfinite(v) for v in pred['scores'][s]) for s in streams)
  row={'family':family,'year':year,'cutoff':cutoff,'cut_index':cut,'test_first_decision':expected[0],
       'test_last_decision':expected[-1],'all_streams_none':absence,'sample_models':[]}
  for name in names:
   rel=f'models/{name}.json.gz'
   p=folder/rel
   manifest=tr.get('model_states')
   expectedsha=manifest.get(rel) if manifest is not None else seal.get('model_sha256',{}).get(name)
   if year==2018:
    assert expectedsha is None and not p.exists()
    continue
   assert expectedsha is not None and sha(p)==expectedsha
   model=read(p)
   if 'cutoff' in model: assert model['cutoff']==cutoff
   numeric_file_count+=1
   sample={'path':str(p.relative_to(ROOT)),'model_sha256':expectedsha}
   if family in ('B67','B88A_MEDIAN'):
    assert model['seed']==101 and model['n_features']==width
    key=name.rsplit('-',1)[0]
    rec=tr['receipts'][key][0]
    assert rec['cut']==cut and rec['selection_calls']==0 and rec['random_validation'] is False
    assert rec['last']<cut and rec['common_last_label']<=cut-6
    assert model['execution_lag']==rec['execution_lag']
    if family=='B88A_MEDIAN': assert model['spec']['loss']=='absolute_error'
    sample['final_receipt_cut']=rec['cut']
    sample['fixed_profile_no_inner_selection']=True
   else:
    members=[model['state']] if family=='BASE_TREE' else model['members']
    details=[model['receipt']] if family=='BASE_TREE' else model['receipt']['details']
    assert len(members)==len(details)==(1 if family=='BASE_TREE' else 7)
    for i,(state,detail) in enumerate(zip(members,details)):
     assert state['n_features']==width
     seed=int(name.rsplit('S',1)[1]) if family=='BASE_TREE' else SEEDS[i]
     assert state['seed']==seed
     assert detail['receipt']['cut']==cut
     trials=detail['trials']
     chosen=min(range(len(trials)),key=lambda j:(trials[j]['loss'],j))
     assert detail['selected']==chosen and state['profile']==trials[chosen]['profile']
     assert len(trials)==2
     selection_count+=1
     for trial in trials:
      folds=trial['folds']
      assert len(folds)==2
      assert abs(sum(f['loss'] for f in folds)/2-trial['loss'])<=2e-12
      assert folds[0]['last']<folds[1]['first']
      for held in folds:
       rec=held['receipt']
       assert rec['cut']==held['first'] and rec['last_label']<=rec['cut']-6
       assert held['label_end']<=cut-6
       inner_fit_count+=1
    sample['final_receipt_cut']=cut
    sample['selected_profile_indices']=[x['selected'] for x in details]
    if family=='BASE_TREE' and name.endswith('S1701'):
     reused=ROOT/model['reused_source']
     assert reused.is_relative_to(ROOT)
     assert f'/folds/{year}/models/' in str(reused)
     assert sha(reused)==model['reused_sha256']
     reuse_count+=1
     sample['same_year_reused_model']=model['reused_source']
   row['sample_models'].append(sample)
  records.append(row)

static=[]
for family,(_,code,_,_,_) in FAMILIES.items():
 tree=ast.parse((ROOT/'lab'/f'{code}.py').read_text())
 test=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='test')
 calls={n.func.id if isinstance(n.func,ast.Name) else n.func.attr if isinstance(n.func,ast.Attribute) else '<other>'
        for n in ast.walk(test) if isinstance(n,ast.Call)}
 forbidden=calls & {'fit','tune','tune_seed','fit_transform','partial_fit'}
 assert not forbidden
 static.append({'family':family,'test_function_direct_fit_or_tune_calls':sorted(forbidden)})

result={'round':2,'scope':'六模型家族年度代表状态，不含全部seed的全量模型内容；未重算预测值',
 'all_checks_pass':True,'annual_family_contracts':len(records),'numeric_files_read':numeric_file_count,
 'deterministic_inner_profile_selections_checked':selection_count,'inner_fit_receipt_boundaries_checked':inner_fit_count,
 'same_year_retained_seed_reuses_checked':reuse_count,'records':records,'static_test_checks':static}
with (OUT/'r02_checks.json').open('x') as f: json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items() if k not in ('records','static_test_checks')},ensure_ascii=False))
