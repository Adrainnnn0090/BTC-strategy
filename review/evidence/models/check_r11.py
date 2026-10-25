"""Bounded adversarial loader checks using synthetic temporary model objects."""
import sys
sys.dont_write_bytecode=True
import copy,gzip,hashlib,json,os,subprocess,tempfile
from pathlib import Path

CANDIDATE=Path('/workspace/BTC-strategy')
LEDGER=Path('/workspace/BTCStrategyResearchLedger')
OUT=Path('/workspace/BTCExpertReview/workspaces/models')
def protect(event,args):
 if event!='open'or not isinstance(args[0],(str,bytes)):return
 p=Path(os.fsdecode(args[0])).resolve();mode=args[1]or'';flags=args[2]if len(args)>2 else 0
 if (p.is_relative_to(CANDIDATE)or p.is_relative_to(LEDGER))and(any(c in mode for c in 'wax+')or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)):
  raise AssertionError('candidate/source write blocked')
sys.addaudithook(protect)
sys.path.insert(0,str(CANDIDATE/'src'))
import btc_strategy.artifacts as artifacts
import btc_strategy.models as models
SEEDS=[101,307,509,701,907,1103,1701]
head=subprocess.check_output(['git','-C',str(CANDIDATE),'rev-parse','HEAD'],text=True).strip()
assert head=='a642de16cea72875a99859e9108960b02636c584'
results=[]

def state(seed,lag=None,width=44):
 s={'family':'SGB'if lag else'EXTRA','seed':seed,'n_features':width,'initial':0.,'weight':1.,
    'trees':[{'left':[-1],'right':[-1],'feature':[-2],'threshold':[-2.],'value':[.25]}]}
 if lag is not None:s['execution_lag']=lag
 return s
def record(name,operation,reject=False,kind=(ValueError,KeyError),message=None):
 try:
  value=operation()
 except Exception as exc:
  passed=reject and isinstance(exc,kind)and(message is None or message in str(exc))
  results.append({'case':name,'pass':passed,'outcome':'rejected','exception':type(exc).__name__,'message':str(exc)})
  return
 results.append({'case':name,'pass':not reject,'outcome':'accepted',
                 'returned_states':len(value)if isinstance(value,list)else None})

with tempfile.TemporaryDirectory(prefix='btc_models_r11_',dir='/tmp')as directory:
 fixture=Path(directory)
 original_root=artifacts.ROOT
 artifacts.ROOT=fixture
 def write_obj(relative,obj):
  p=fixture/relative;p.parent.mkdir(parents=True,exist_ok=True)
  b=json.dumps(obj,separators=(',',':')).encode()
  if p.suffix=='.gz':b=gzip.compress(b,mtime=0)
  p.write_bytes(b)
  return {'path':relative,'sha256':hashlib.sha256(b).hexdigest()}
 def setup(family='base_tree',year=2025,members=None,cutoff=None,missing=False,path=None,width=44):
  if members is None:members=[state(s)for s in SEEDS]
  items=[]
  if not missing:
   items=[write_obj(path or f'models/{family}/{year}/synthetic.json.gz',
             {'cutoff':cutoff or f'{year-1}-12-31','members':members})]
  entry={'family':family,'fold_year':year,'missing':missing,'feature_width':width,
         'cutoff':f'{year-1}-12-31','files':items}
  write_obj('models/manifest.json',[entry])
  return entry
 try:
  setup()
  record('valid_7_seed_long_roster',lambda:models.annual_states('base_tree',2025))
  setup(family='short_median',members=[state(s,lag)for lag in (1,2)for s in SEEDS])
  record('valid_14_seed_lag_roster',lambda:models.annual_states('short_median',2025))

  malformed=fixture/'models/base_tree/2025/malformed.json.gz'
  malformed.write_bytes(b'not-gzip-not-json')
  record('hash_mismatch_rejected_before_decode',
    lambda:artifacts.read_verified('models/base_tree/2025/malformed.json.gz','0'*64),
    reject=True,kind=(ValueError,),message='model content hash mismatch')
  correct=hashlib.sha256(malformed.read_bytes()).hexdigest()
  record('matching_hash_reaches_and_rejects_malformed_decode',
    lambda:artifacts.read_verified('models/base_tree/2025/malformed.json.gz',correct),
    reject=True,kind=(gzip.BadGzipFile,))

  setup(path='models/stop44/2025/synthetic.json.gz')
  record('wrong_family_path',lambda:models.annual_states('base_tree',2025),reject=True,message='model year/family path mismatch')
  setup(path='models/base_tree/2024/synthetic.json.gz')
  record('wrong_year_path',lambda:models.annual_states('base_tree',2025),reject=True,message='model year/family path mismatch')
  setup(members=[state(s)for s in SEEDS[:-1]])
  record('missing_long_seed_member',lambda:models.annual_states('base_tree',2025),reject=True,message='incomplete long member roster')
  setup(members=[state(s)for s in [101,101,509,701,907,1103,1701]])
  record('duplicate_long_seed_member',lambda:models.annual_states('base_tree',2025),reject=True,message='incomplete long member roster')
  setup(family='short_median',members=[state(s,lag)for lag in (1,2)for s in SEEDS if not(lag==2 and s==1701)])
  record('missing_short_seed_member',lambda:models.annual_states('short_median',2025),reject=True,message='incomplete short member roster')
  bad=[state(s,lag)for lag in (1,2)for s in SEEDS];bad[-1]['seed']=1103
  setup(family='short_median',members=bad)
  record('duplicate_short_seed_member',lambda:models.annual_states('short_median',2025),reject=True,message='incomplete short member roster')
  setup(family='short_median',members=[state(s,1)for s in SEEDS]*2)
  record('duplicate_lag1_missing_lag2_head',lambda:models.annual_states('short_median',2025),reject=True,message='incomplete short member roster')
  setup(family='short_median',members=[state(s,lag)for lag in (1,3)for s in SEEDS])
  record('unsupported_lag3_head',lambda:models.annual_states('short_median',2025),reject=True,message='incomplete short member roster')
  bad=[state(s,lag)for lag in (1,2)for s in SEEDS];del bad[0]['execution_lag']
  setup(family='short_median',members=bad)
  record('missing_execution_lag_field_fails_closed',lambda:models.annual_states('short_median',2025),reject=True,kind=(ValueError,KeyError))
  setup(members=[state(s,width=43)for s in SEEDS])
  record('wrong_numeric_feature_width',lambda:models.annual_states('base_tree',2025),reject=True,message='model feature width mismatch')
  setup(cutoff='2023-12-31')
  record('wrong_payload_cutoff',lambda:models.annual_states('base_tree',2025),reject=True,message='model cutoff mismatch')
  setup(missing=True)
  record('illegal_missing_2025',lambda:models.annual_states('base_tree',2025),reject=True,message='invalid missing-state contract')
  setup(year=2018,missing=True)
  record('valid_2018_missing_contract',lambda:models.annual_states('base_tree',2018))
  entry=setup(year=2018,missing=True)
  entry['files']=[write_obj('models/base_tree/2018/forbidden.json.gz',{'members':[state(s)for s in SEEDS]})]
  write_obj('models/manifest.json',[entry])
  record('2018_missing_with_files_rejected',lambda:models.annual_states('base_tree',2018),reject=True,message='invalid missing-state contract')
  setup(year=2018,missing=True)
  from datetime import date,timedelta
  dates=[(date(2017,1,1)+timedelta(days=i)).isoformat()for i in range(729)]
  synthetic_market={'days':dates,'prices':[1000+i+.1*(i%7)for i in range(729)]}
  def missing_stream():
   values=models.reconstruct('base_tree',market=synthetic_market)
   assert len(values)==729 and all(v is None for v in values)
   return values
  record('2018_reconstruct_preserves_None_not_zero',missing_stream)

  # The historical contract also excludes fabricated present states in 2018.
  setup(year=2018,missing=False)
  record('fabricated_present_2018_states_rejected',lambda:models.annual_states('base_tree',2018),reject=True,message='missing')
 finally:
  artifacts.ROOT=original_root

assert head==subprocess.check_output(['git','-C',str(CANDIDATE),'rev-parse','HEAD'],text=True).strip()
result={'round':11,'candidate_git':head,'all_checks_pass':all(x['pass']for x in results),
 'cases':len(results),'passed':sum(x['pass']for x in results),'results':results,
 'scope':'只以/tmp合成manifest/数字模型对象临时切换artifact ROOT，finally恢复；不修改候选/源仓，不做真实未来数据读取、推断全量重跑或refit。'}
with (OUT/'r11_checks.json').open('x')as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
