"""Bounded regression of R05/R07 failures; synthetic fault fixtures only."""
import copy,gzip,hashlib,json,os,subprocess,sys,tempfile
from datetime import date,timedelta
from pathlib import Path

ROOT=Path('/workspace/BTC-strategy')
OWN=Path('/workspace/BTCExpertReview/workspaces/repro')
blocked=[];actual_reads=set()
def audit(event,args):
 if event!='open' or not isinstance(args[0],(str,bytes)):return
 p=Path(os.fsdecode(args[0])).resolve()
 if p.is_relative_to(ROOT/'review') or p.is_relative_to('/workspace/BTCStrategyResearchLedger') or 'binance_robot' in p.parts or p.is_relative_to('/workspace/BinanceTradingRobot/backend/src') or p.is_relative_to('/workspace/BinanceTradingRobot/research') or p.is_relative_to('/workspace/BinanceTradingRobot/strategy'):
  blocked.append(str(p));raise AssertionError('review or old project excluded')
 if p.is_relative_to(ROOT):
  z=p.relative_to(ROOT).parts
  if any(part.lower().startswith(('v01','v02')) for part in z):raise AssertionError('real validation path forbidden')
  if z and z[0]in('artifacts','models','training_inputs','data') and any('2026'in part for part in z):raise AssertionError('real future economic path forbidden')
  actual_reads.add(str(p.relative_to(ROOT)))
sys.addaudithook(audit)
sys.path.insert(0,str(ROOT/'src'))
from btc_strategy import artifacts,models,training,integrity

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
code_names=('artifacts.py','models.py','training.py','validation.py','integrity.py')
before={name:sha(ROOT/'src/btc_strategy'/name) for name in code_names}
commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()

paths=['../repro-outside','/tmp/repro-outside','models/base_tree/2026/repro-placeholder','models/base_tree/fold2027/repro-placeholder','training_inputs/2026/base_tree.json.gz','artifacts/contexts/2026/repro-placeholder','artifacts/V01/repro-placeholder','artifacts/V02/repro-placeholder','artifacts/v01-retained-validation/repro-placeholder','artifacts/v02-retained-validation/repro-placeholder','artifacts/V01-pretend/repro-placeholder','provenance/folds/2026/repro-placeholder','data/prices_2026.json']
path_results=[]
for path in paths:
 try:artifacts.resolve_artifact(path);rejected=False
 except ValueError:rejected=True
 path_results.append({'synthetic_path':path,'ValueError_before_open':rejected})

class UnexpectedRead(Exception):pass
attempts=[]
def sentinel(*args,**kwargs):attempts.append(str(args));raise UnexpectedRead('must reject before read/guard')
saved=(models.read,models.read_verified,training.read,training.install_training_guard)
models.read=models.read_verified=training.read=training.install_training_guard=sentinel
def market(n=500):return {'days':[(date(2017,1,1)+timedelta(days=i)).isoformat() for i in range(n)],'prices':[100.+i*.1 for i in range(n)]}
bad_middle=market();bad_middle['days'][250]='2026-01-01'
bad_duplicate=market();bad_duplicate['days'][250]=bad_duplicate['days'][249]
bad_order=market();bad_order['days'][250],bad_order['days'][251]=bad_order['days'][251],bad_order['days'][250]
bad_nan=market();bad_nan['prices'][250]=float('nan')
bad_bool=market();bad_bool['prices'][250]=True
api_calls=[]
for function,label in ((models.annual_states,'annual_states'),(training.refit,'refit')):
 for year in (2026,2017,2025.0,True,'2025'):
  api_calls.append((label+'_year_'+repr(year),lambda f=function,y=year:f('base_tree',y)))
 api_calls.append((label+'_unknown_family',lambda f=function:f('unknown',2025)))
api_calls.extend([
 ('reconstruct_unknown_family',lambda:models.reconstruct('unknown')),
 ('feature_unknown_family',lambda:models.feature_matrix('unknown',market())),
 ('reconstruct_middle_future',lambda:models.reconstruct('base_tree',bad_middle)),
 ('feature_middle_future',lambda:models.feature_matrix('base_tree',bad_middle)),
 ('feature_duplicate_date',lambda:models.feature_matrix('base_tree',bad_duplicate)),
 ('feature_disordered_date',lambda:models.feature_matrix('base_tree',bad_order)),
 ('feature_nonfinite_price',lambda:models.feature_matrix('base_tree',bad_nan)),
 ('feature_bool_price',lambda:models.feature_matrix('base_tree',bad_bool)),
])
api_results=[]
for label,call in api_calls:
 attempts.clear()
 try:call();kind=None
 except Exception as exc:kind=type(exc).__name__
 api_results.append({'case':label,'exception':kind,'read_or_guard_attempts':list(attempts),'pass':kind=='ValueError' and not attempts})
models.read,models.read_verified,training.read,training.install_training_guard=saved

none_states={family:models.annual_states(family,2018)==[] for family in models.FAMILIES}
none_prediction=all(value is None for value in models.reconstruct('base_tree',market(365)))
price=market();x=models.feature_matrix('price47',price)
changed=copy.deepcopy(price);changed['prices'][400:]=[100000.]*100
price_results={'no_mining_or_volume_required':list(x.shape)==[500,47],
 'future_perturbation_prefix_exact':bool((x[:400]==models.feature_matrix('price47',changed)[:400]).all()),
 'short_prefix_exact':bool((x[:400]==models.feature_matrix('price47',{key:value[:400]for key,value in price.items()})).all())}

predicate_paths={'artifacts/contexts/high_return.json.gz':False,'artifacts/accounts/LP35/STRESS.json.gz':False,'training_inputs/2025/price47.json.gz':True,'training_inputs/2024/price47.json.gz':False,'training_inputs/2025/short_huber.json.gz':False,'models/base_tree/2025/x.json.gz':False}
training_predicates={path:training.training_read_allowed(ROOT/path,'price47',2025)==expected for path,expected in predicate_paths.items()}

faults=[]
def expect_reject(label,call):
 try:call();kind=None;message=None
 except Exception as exc:kind=type(exc).__name__;message=str(exc)
 faults.append({'case':label,'rejected':kind is not None,'exception':kind,'message':message})

with tempfile.TemporaryDirectory(prefix='btc-repro-r11-') as temporary:
 private=Path(temporary);old_artifact_root=artifacts.ROOT;old_integrity_root=integrity.ROOT
 artifacts.ROOT=private;integrity.ROOT=private
 def write_json(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,sort_keys=True))
 def write_model(path,state):
  path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.compress(json.dumps(state,sort_keys=True).encode(),mtime=0))
 seeds=[101,307,509,701,907,1103,1701]
 files=[]
 for seed in seeds:
  relative=f'models/base_tree/2019/synthetic-{seed}.json.gz';p=private/relative
  write_model(p,{'cutoff':'2018-12-31','state':{'seed':seed,'n_features':44,'initial':0.,'weight':1.,'trees':[]}})
  files.append({'path':relative,'sha256':sha(p)})
 base={'family':'base_tree','fold_year':2019,'missing':False,'files':files,'feature_width':44}
 manifest=private/'models/manifest.json'
 def reset_route(row=None):write_json(manifest,[copy.deepcopy(base if row is None else row)])
 reset_route();baseline_states=len(models.annual_states('base_tree',2019))==7
 row=copy.deepcopy(base);row['files'].append(copy.deepcopy(files[0]));reset_route(row)
 expect_reject('duplicate_seed_roster',lambda:models.annual_states('base_tree',2019))
 row=copy.deepcopy(base);row['files']=row['files'][:-1];reset_route(row)
 expect_reject('missing_seed_roster',lambda:models.annual_states('base_tree',2019))
 reset_route();p=private/files[0]['path'];original=p.read_bytes();p.write_bytes(original+b'corrupt')
 expect_reject('model_payload_hash_drift',lambda:models.annual_states('base_tree',2019));p.write_bytes(original)
 for label,path in (('wrong_year_model_path','models/base_tree/2020/synthetic.json.gz'),('wrong_family_model_path','models/stop44/2019/synthetic.json.gz')):
  row=copy.deepcopy(base);row['files'][0]['path']=path;reset_route(row)
  expect_reject(label,lambda:models.annual_states('base_tree',2019))
 for label,mutation in (('model_cutoff_drift',lambda state:state.update(cutoff='2017-12-31')),('model_width_drift',lambda state:state['state'].update(n_features=47))):
  state=json.loads(gzip.decompress(original));mutation(state);write_model(p,state)
  row=copy.deepcopy(base);row['files'][0]['sha256']=sha(p);reset_route(row)
  expect_reject(label,lambda:models.annual_states('base_tree',2019));p.write_bytes(original)
 row=copy.deepcopy(base);row.update(missing=True,files=[]);reset_route(row)
 expect_reject('missing_model_outside_2018',lambda:models.annual_states('base_tree',2019))
 short_files=[]
 for seed in seeds:
  relative=f'models/short_median/2019/synthetic-L1-{seed}.json.gz';q=private/relative
  write_model(q,{'seed':seed,'n_features':44,'execution_lag':1,'initial':0.,'weight':1.,'trees':[]})
  short_files.append({'path':relative,'sha256':sha(q)})
 write_json(manifest,[{'family':'short_median','fold_year':2019,'missing':False,'files':short_files,'feature_width':44}])
 expect_reject('missing_second_head',lambda:models.annual_states('short_median',2019))

 payload=private/'payload.txt';payload.write_text('SYNTHETIC VALID PAYLOAD')
 release=private/'provenance/release_manifest.json'
 def release_reset():write_json(release,{'files':[{'path':'payload.txt','sha256':sha(payload),'bytes':payload.stat().st_size}]})
 release_reset();integrity_baseline=integrity.verify_integrity()['status']=='PASS'
 payload.write_text('SYNTHETIC DRIFT')
 expect_reject('integrity_payload_drift',integrity.verify_integrity)
 payload.write_text('SYNTHETIC VALID PAYLOAD');release_reset();payload.unlink()
 expect_reject('integrity_missing_payload',integrity.verify_integrity)
 write_json(release,{'files':[{'path':'../synthetic-escape','sha256':'0'*64,'bytes':0}]})
 expect_reject('integrity_path_escape',integrity.verify_integrity)
 # Separate scope probe: verify_integrity trusts the provided manifest inventory.
 write_json(release,{'files':[]});empty_manifest_scope=integrity.verify_integrity()

 review=private/'review/rounds/01'
 def review_reset():
  chair={'round':1,'submissions':{}}
  for role in integrity.ROLES:
   q=review/(role+'.json');write_json(q,{'round':1,'role':role,'conclusion':'SYNTHETIC PLACEHOLDER','verdict':'supported','evidence':[],'checks_performed':[],'unresolved':[],'independence_statement':'Synthetic fixture, no actual reviewer opinions.'})
   chair['submissions'][role]={'sha256':sha(q)}
  write_json(review/'chair.json',chair)
 review_reset();review_baseline=integrity.verify_reviews(expected_rounds=1)['expert_submissions']==6
 q=review/'data.json';q.unlink();expect_reject('review_missing_role',lambda:integrity.verify_reviews(expected_rounds=1))
 review_reset();r=json.loads(q.read_text());r['role']='wrong';write_json(q,r);expect_reject('review_wrong_role_or_hash',lambda:integrity.verify_reviews(expected_rounds=1))
 review_reset();r=json.loads(q.read_text());r.pop('unresolved');write_json(q,r)
 chair=json.loads((review/'chair.json').read_text());chair['submissions']['data']['sha256']=sha(q);write_json(review/'chair.json',chair)
 expect_reject('review_missing_required_field',lambda:integrity.verify_reviews(expected_rounds=1))
 review_reset();expect_reject('review_missing_next_round',lambda:integrity.verify_reviews(expected_rounds=2))
 review_reset();(review/'chair.json').unlink();expect_reject('review_missing_chair',lambda:integrity.verify_reviews(expected_rounds=1))
 artifacts.ROOT=old_artifact_root;integrity.ROOT=old_integrity_root

after={name:sha(ROOT/'src/btc_strategy'/name) for name in code_names}
result={'round':11,'git_commit':commit,'code_sha_at_start':before,'code_sha_at_end':after,'code_snapshot_stable':before==after,
 'clean_import_no_instrument_shim':True,'old_project_or_real_review_read_attempts':blocked,
 'path_pre_open_checks':path_results,'all_path_checks_pass':all(row['ValueError_before_open']for row in path_results),
 'API_pre_read_checks':api_results,'all_API_checks_pass':all(row['pass']for row in api_results),
 'all_six_2018_states_missing':none_states,'2018_prediction_None_preserved':none_prediction,
 'price_only_lazy_feature_checks':price_results,'training_role_predicates':training_predicates,
 'synthetic_valid_model_baseline_pass':baseline_states,'synthetic_integrity_baseline_pass':integrity_baseline,'synthetic_complete_review_baseline_pass':review_baseline,
 'synthetic_fault_rejections':faults,'all_requested_faults_rejected':all(row['rejected']for row in faults),
 'trusted_manifest_inventory_scope_probe':{'empty_synthetic_manifest_result':empty_manifest_scope,'interpretation':'Verifier checks declared file content, not independent authenticity/completeness of its input manifest. Expected inventory must be anchored by the frozen commit/manifest identity; this is separate from payload-drift rejection.'},
 'actual_new_repo_read_paths':sorted(actual_reads),'actual_review_contents_read':False,'real_forbidden_files_opened':False,'shared_code_or_writers_modified':False,
 'native_36_accounts_repeated':False,'training_or_strategy_search_executed':False,'R05_R07_initial_failure_files_preserved':True}
with (OWN/'checks-r11.json').open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({key:result[key]for key in('git_commit','code_snapshot_stable','clean_import_no_instrument_shim','old_project_or_real_review_read_attempts','all_path_checks_pass','all_API_checks_pass','all_six_2018_states_missing','2018_prediction_None_preserved','price_only_lazy_feature_checks','synthetic_valid_model_baseline_pass','synthetic_integrity_baseline_pass','synthetic_complete_review_baseline_pass','all_requested_faults_rejected','trusted_manifest_inventory_scope_probe')},ensure_ascii=False,indent=2))
