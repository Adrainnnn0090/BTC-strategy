"""Bounded stochastic coordinate search on training accounts, never target-window tuning."""
import argparse,copy,csv,hashlib,json,math,random,time,traceback
import numpy as np
from .io import ROOT,load,read,write,sha,install_guard
from .signals import FAMILIES,SPACE,RISK_SPACE,Features,valid
from .native import CASES,run_account
from .audit import audit_account

DEFAULTS={
'BAND':dict(n=100,band=.03),'EMA_CROSS':dict(fast=20,slow=100,band=0.),'BREAKOUT':dict(n=60,exit=20),
'MOMENTUM':dict(n=60,threshold=0.),'ZLEMA':dict(n=100,band=0.),'KAMA':dict(n=20,fast=2,slow=30,band=.01),
'SLOPE':dict(n=50,quality=.2,threshold=0.),'MACD':dict(fast=12,slow=26,signal=9),'PULLBACK':dict(n=100,fast=10,dip=.03,recovery=0.),
'RSI':dict(n=7,entry=30,exit=70,trend=100),'DUAL_MOM':dict(fast=20,slow=120,weight=.5,threshold=0.),'TREND_VOTE':dict(n=50,votes=2,band=0.)}
SEED=20261021
STUDY=ROOT/'studies/B01-price-mechanisms'

def fingerprint(config):return hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()[:16]

def initial():
 rng=random.Random(SEED);out=[]
 for family in FAMILIES:
  seen=set()
  for j in range(6):
   while True:
    params=DEFAULTS[family].copy() if j==0 else {k:rng.choice(v) for k,v in SPACE[family].items()}
    risk={'stop_loss':.15,'take_profit':1.,'cooldown_days':3,'vol_target':0.} if j==0 else {k:rng.choice(v) for k,v in RISK_SPACE.items()}
    c={'family':family,'params':params,'risk':risk}
    if valid(c) and fingerprint(c) not in seen:seen.add(fingerprint(c));out.append(c);break
 return out

def objective(summaries,years=None):
 worst=max(s['max_drawdown_pct']/100 for s in summaries.values())
 if years:
  logs=[sum(math.log1p(y['return_pct']/100) for y in s['annual'] if y['year'] in years) for s in summaries.values()]
 else:logs=[math.log1p(s['return_pct']/100) for s in summaries.values()]
 yearly=[math.log1p(y['return_pct']/100) for y in summaries['STRESS']['annual']]
 return min(logs)-12*max(0,worst-.33)-.3*float(np.std(yearly))-.002*summaries['STRESS']['natural_trades']

def qualify(s):
 stress=s['STRESS'];con=stress['best_two_positive_contribution_fraction']
 return max(v['max_drawdown_pct'] for v in s.values())<35 and min(v['return_pct'] for v in s.values())>0 and stress['return_pct']>=500 and stress['natural_trades']>=8 and stress['positive_years']>=3 and con is not None and con<=.8

def freeze():
 STUDY.mkdir(parents=True,exist_ok=True)
 reg={'seed':SEED,'initial':initial(),'families':FAMILIES,'space':SPACE,'risk_space':RISK_SPACE,'iterations_per_family':12,'candidate_cap':360,'account_cap':1440,'selection':'common-year minibatch finite differences then full-training acceptance; no target reads','training':'2018-01-01..2022-12-31 with2017 prefix','target':'2018-01-01..2025-12-31','target_retrospective_only':True,'target_return_pct':10000,'target_max_drawdown_strict_pct':35,'finalist_cap':3,'cash':100,'max_long_fraction':.95,'shorts':False,'costs':CASES,'data_manifest_sha256':sha(ROOT/'data/manifest.json'),'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted([*(ROOT/'lab').glob('*.py'),*(ROOT/'tests').glob('*.py'),STUDY/'spec.md',STUDY/'sources.md'])},'objective':'minimum four-cost log return -12*max(0,worstDD-.33) -.3*std(annual log return) -.002*STRESS natural trade count','admission':'STRESS>=500%, all scenario DD<35%, all returns>0, >=8 natural trades, >=3 positive years, best2 natural-profit concentration<=80%','native_scope':'same R20 native cash engine with role-bound2018-2025 window; training role still ends2022; only daily price proxies'}
 write(STUDY/'registration.json',reg)
 print('FROZEN',sha(STUDY/'registration.json'),flush=True)

def verify():
 r=read(STUDY/'registration.json')
 for p,h in r['source_sha256'].items():
  if sha(ROOT/p)!=h:raise ValueError('frozen code changed '+p)
 if sha(ROOT/'data/manifest.json')!=r['data_manifest_sha256']:raise ValueError('data manifest changed')
 return r

def train():
 accesses=install_guard();reg=verify();days,prices=load();features=Features(prices);rng=random.Random(SEED+1);attempts=[];cache={};updates=[]
 if (STUDY/'attempts.jsonl').exists():raise ValueError('preserve prior attempts')
 def evaluate(config,stage):
  key=fingerprint(config)
  if key in cache:return cache[key]
  result={'id':f'C{len(attempts)+1:03}','fingerprint':key,'config':config,'stage':stage};t=time.monotonic()
  try:
   targets=features.targets(config);risk={k:v for k,v in config['risk'].items() if k!='vol_target'};summaries={};audits={}
   for case in CASES:
    account=run_account(days,prices,targets,case,risk,start='2018-01-01')
    audits[case]=audit_account(account,days,prices,targets,CASES[case],risk);summaries[case]=account['summary']
   result.update(status='COMPLETE',summaries=summaries,audits=audits,objective=objective(summaries),admitted=qualify(summaries))
  except Exception:result.update(status='FAILED',objective=-1e9,admitted=False,exception=traceback.format_exc())
  result['seconds']=round(time.monotonic()-t,3);cache[key]=result;attempts.append(result)
  with (STUDY/'attempts.jsonl').open('a') as f:f.write(json.dumps(result,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n')
  if len(attempts)%10==0 or result['status']=='FAILED':print('ATTEMPTS',len(attempts),'family',config['family'],'objective',round(result['objective'],3),'admitted',sum(x['admitted'] for x in attempts),flush=True)
  return result
 for config in reg['initial']:evaluate(config,'INITIAL')
 for family in FAMILIES:
  current=max((r for r in attempts if r['config']['family']==family),key=lambda r:r['objective'])
  dimensions=[('params',k,v) for k,v in SPACE[family].items()]+[('risk',k,v) for k,v in RISK_SPACE.items()]
  for step in range(12):
   group,key,values=rng.choice(dimensions);pos=values.index(current['config'][group][key]);years=sorted(rng.sample(['2018','2019','2020','2021','2022'],2));pair=[]
   for sign in (-1,1):
    newpos=pos+sign
    if not 0<=newpos<len(values):continue
    candidate=copy.deepcopy(current['config']);candidate[group][key]=values[newpos]
    if valid(candidate):pair.append(evaluate(candidate,f'COORDINATE/{family}/{step}'))
   successful=[x for x in pair if x['status']=='COMPLETE'];before=current['id'];accepted=False
   if successful:
    proposal=max(successful,key=lambda r:objective(r['summaries'],years))
    if proposal['objective']>current['objective']+1e-12:current=proposal;accepted=True
   updates.append({'family':family,'step':step,'dimension':group+'/'+key,'common_year_minibatch':years,'from':before,'neighbors':[x['id'] for x in pair],'accepted':accepted,'to':current['id']})
  print('FAMILY',family,'best',current['id'],round(current.get('summaries',{}).get('STRESS',{}).get('return_pct',-999),2),'objective',round(current['objective'],3),flush=True)
 ranked=sorted([r for r in attempts if r['admitted']],key=lambda r:(-r['objective'],r['fingerprint']));final=[];paths=set();families=set()
 for r in ranked:
  path=tuple(r['summaries'][c]['path_sha256'] for c in CASES)
  if path not in paths and r['config']['family'] not in families:final.append(r);paths.add(path);families.add(r['config']['family'])
  if len(final)==3:break
 write(STUDY/'updates.json',updates)
 write(STUDY/'finalists.json',{'registered_sha256':sha(STUDY/'registration.json'),'selected_before_target_read':True,'selection_role':'train_only','finalists':[{'id':r['id'],'config':r['config'],'training_objective':r['objective']} for r in final]})
 write(STUDY/'train-summary.json',{'attempts':len(attempts),'completed':sum(r['status']=='COMPLETE' for r in attempts),'failed':sum(r['status']=='FAILED' for r in attempts),'admitted':len(ranked),'finalists':[r['id'] for r in final],'protected_reads':sorted(accesses),'assessment_reads':0,'validation_reads':0,'best_by_family':{f:max([r for r in attempts if r['config']['family']==f],key=lambda x:x['objective']) for f in FAMILIES}})
 with (STUDY/'attempts.csv').open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['id','family','parameters','risk','STRESS_return_pct','worst_DD_pct','objective','decision'])
  for r in attempts:w.writerow([r['id'],r['config']['family'],json.dumps(r['config']['params']),json.dumps(r['config']['risk']),r.get('summaries',{}).get('STRESS',{}).get('return_pct'),max((s['max_drawdown_pct'] for s in r.get('summaries',{}).values()),default=None),r['objective'],'FROZEN_FINALIST' if r['id'] in [x['id'] for x in final] else 'PARK'])
 print('TRAIN COMPLETE',len(attempts),'finalists',[r['id'] for r in final],flush=True)

def assess():
 accesses=install_guard(assessment=True);verify();frozen=read(STUDY/'finalists.json')
 if not frozen['selected_before_target_read'] or frozen['selection_role']!='train_only':raise ValueError('candidate selection not frozen')
 if not frozen['finalists']:
  write(STUDY/'assessment.json',{'status':'DO_NOT_OPEN','reason':'No train-qualified candidate','target_read':False});print('ASSESSMENT CLOSED');return
 days,prices=load(assessment=True);features=Features(prices);results=[]
 for item in frozen['finalists']:
  risk={k:v for k,v in item['config']['risk'].items() if k!='vol_target'};target=features.targets(item['config']);summaries={}
  for case in CASES:
   account=run_account(days,prices,target,case,risk,start='2018-01-01',end='2025-12-31',role='retrospective_target')
   audit_account(account,days,prices,target,CASES[case],risk);write(STUDY/f"finalists/{item['id']}/account-{case}.json.gz",account);summaries[case]=account['summary']
  passed=summaries['STRESS']['return_pct']>=10000 and max(s['max_drawdown_pct'] for s in summaries.values())<35
  results.append({**item,'summaries':summaries,'target_pass':passed})
  print('TARGET',item['id'],'return',round(summaries['STRESS']['return_pct'],2),'worstDD',round(max(s['max_drawdown_pct'] for s in summaries.values()),2),'PASS',passed,flush=True)
 write(STUDY/'assessment.json',{'status':'COMPLETE','frozen_finalists_sha256':sha(STUDY/'finalists.json'),'results':results,'target_read':True,'reserved_validation_read':False,'protected_reads':sorted(accesses),'selection_after_assessment':'FORBIDDEN','scope':'user-requested retrospective2018-2025, not new OOS'})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','train','assess']);a=p.parse_args()
 {'freeze':freeze,'train':train,'assess':assess}[a.command]()
