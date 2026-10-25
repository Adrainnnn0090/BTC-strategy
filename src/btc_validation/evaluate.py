"""Read-only fixed holdout evaluation. No fitting entry point is called or allowed."""
from pathlib import Path
from datetime import date,timedelta,datetime,timezone
import os,sys,json,gzip,hashlib
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor,GradientBoostingRegressor,RandomForestRegressor
from sklearn.preprocessing import StandardScaler,RobustScaler
from .protocol import WINDOWS,STRATEGIES,FAMILIES,validate_clock
from .inference import forecast,expanded_context,states
from .strategies import compose
from .engine import run_account
from .benchmark import run_account as buy_hold
from .metrics import summarize,paired_bootstrap,audit_buy_hold
from .prediction_metrics import measure as prediction_measure
from btc_strategy.costs import CASES,BORROW
from btc_strategy._runtime.carry_audit import audit
from btc_strategy._runtime.quote_exposure import measure as exposure

class Reader:
 def __init__(self,root):
  self.root=Path(root).resolve();self.registry=json.loads((self.root/'registration.json').read_text());self.window=None;self.reads=[]
 def __call__(self,name):
  if name not in self.registry['files']:raise ValueError('unregistered validation artifact')
  if name.startswith('prices/')and name!='prices/'+self.window+'.json.gz':raise ValueError('future window file cannot be opened')
  p=(self.root/name).resolve()
  if not p.is_relative_to(self.root):raise ValueError('validation artifact escape')
  raw=p.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=self.registry['files'][name]:raise ValueError('sealed validation artifact changed: '+name)
  self.reads.append(name);return json.loads(gzip.decompress(raw)if p.suffix=='.gz'else raw)

def baseline_targets(days,start,case):
 intent=(date.fromisoformat(start)-timedelta(days=CASES[case][2])).isoformat();disabled=dict(stop_loss=None,take_profit=None,cooldown_days=0,trailing_stop=None,trail_arm=None)
 target=[dict(direction=int(d>=intent),long_fraction=1.,short_fraction=0.,risk=dict(long=disabled,short=disabled))for d in days]
 return target,[d==intent for d in days]

def segment(account,start,end):
 marks=account['marks'];idx=[i for i,m in enumerate(marks)if start<=m['date']<=end]
 if not idx:raise ValueError('missing continuous-account segment')
 initial=100. if idx[0]==0 else float(marks[idx[0]-1]['equity']);eq=np.asarray([initial]+[float(marks[i]['equity'])for i in idx]);dd=np.max(1-eq/np.maximum.accumulate(eq))
 opening=marks[idx[0]-1]if idx[0]else None
 return dict(start=start,end=end,initial_mark_equity=initial,ending_mark_equity=eq[-1],net_return_pct=100*(eq[-1]/initial-1),window_local_drawdown_pct=100*float(dd),
  carried_quantity_at_start=opening.get('signed_qty',opening.get('btc','0'))if opening else'0',
  note='Continuous-account marks: no cash or position reset at Jun30; Jun29 already reserves liquidation fees.')

def evaluate(root,outdir):
 read=Reader(root);out=Path(outdir)
 if out.exists()and any(out.iterdir()):raise ValueError('refuse overwrite of validation results')
 out.mkdir(parents=True,exist_ok=True)
 if Path('/train').exists()or Path('/workspace/BTCStrategyResearchLedger').exists():raise ValueError('validation must not mount training inputs or old projects')
 fitting_attempts=[]
 def no_fit(self,*a,**k):
  fitting_attempts.append(type(self).__name__);raise AssertionError('fitting is forbidden in validation')
 for cls in(ExtraTreesRegressor,GradientBoostingRegressor,RandomForestRegressor,StandardScaler,RobustScaler):cls.fit=no_fit
 def dump(name,value):
  p=out/name;p.parent.mkdir(parents=True,exist_ok=True);raw=(json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n').encode()
  p.write_bytes(gzip.compress(raw,mtime=0)if p.suffix=='.gz'else raw)
 source=read('source-seal.json');training=read('model-seal.json');label_null=read('label_baselines.json')
 if training['cutoff']!='2025-12-31'or training['validation_reads']or training['validation_rows']:raise ValueError('training separation proof failed')
 for family in FAMILIES:states(read,family)
 rows=[];model_rows=[];continuous={};all_windows={**WINDOWS,'CONTINUOUS':('2026-01-01','2026-10-23')}
 for window,(start,end)in all_windows.items():
  read.window='JUN30_TO_OCT23'if window=='CONTINUOUS'else window
  required='prices/'+read.window+'.json.gz'
  if required not in read.registry['files']:
   for name in(*STRATEGIES,'BUY_HOLD'):
    for case in CASES:rows.append(dict(window=window,strategy=name,case=case,status='BLOCKED_INCOMPLETE_ENDPOINT',requested_start=start,requested_end=end))
   continue
  market=read(required);days,prices=market['days'],market['prices'];validate_clock(days,prices,end=end)
  scores=forecast(read,market,allow_mining=source.get('pit_mining_continuation_verified',False))
  dump('predictions/'+window+'.json.gz',dict(dates=days,scores=scores,cutoff='2025-12-31',fitting_calls=0))
  baselines={}
  for case,(fee,slip,lag)in CASES.items():
   t,e=baseline_targets(days,start,case);account=buy_hold(days,prices,t,case,{},start,end,entry_permission=e)
   proof=audit_buy_hold(account,dict(zip(days,prices)),fee,slip);s=summarize(account);baselines[case]=account
   dump(f'accounts/{window}/BUY_HOLD/{case}.json.gz',account)
   rows.append(dict(window=window,strategy='BUY_HOLD',case=case,status='COMPLETE',metrics=s,independent_audit=proof,
    raw_price_return_pct=100*(prices[-1]/prices[days.index(start)]-1),benchmark_entry='First window day after a predeclared lag-day-early constant calendar intent'))
   if window=='CONTINUOUS':continuous['BUY_HOLD/'+case]=[segment(account,a,b)for a,b in WINDOWS.values()]
  for name in STRATEGIES:
   if name=='C04'and'mining58'not in scores:
    for case in CASES:rows.append(dict(window=window,strategy=name,case=case,status='BLOCKED_MISSING_PIT_MINING_CONTINUATION',reason=source['mining_status'],requested_start=start,requested_end=end))
    continue
   ctx=expanded_context(read,name,market,scores);dd,pp,t,e=compose(name,ctx)
   for case,(fee,slip,lag)in CASES.items():
    try:account=run_account(dd,pp,t,case,{},start,end,entry_permission=e,annual_settlement=False)
    except ValueError as exc:
     rows.append(dict(window=window,strategy=name,case=case,status='FAILED_NATIVE_ACCOUNT',reason=str(exc),requested_start=start,requested_end=end));continue
    dump(f'accounts/{window}/{name}/{case}.json.gz',account)
    proof=audit(account,dd,pp,t,CASES[case],BORROW[case],{},e,False);s=summarize(account);gross=exposure(account,fee)
    s.update(max_daily_pre_or_post_short_gross_pct=gross['before_or_after_short']['gross_pct'],max_daily_pre_or_post_whole_gross_pct=gross['before_or_after_whole']['gross_pct'],
     max_actual_loss_pct_of_entry_basis=max([100*max(0.,-float(x['pnl']))/(float(x['quantity'])*float(x['entry_price'])*(1+fee))for x in account['trades']],default=0.))
    b=summarize(baselines[case]);rows.append(dict(window=window,strategy=name,case=case,status='COMPLETE',metrics=s,
     excess_vs_buy_hold_percentage_points=s['net_return_pct']-b['net_return_pct'],independent_audit=proof,
     descriptive_paired_bootstrap=[paired_bootstrap(account,baselines[case],block=z)for z in(7,14,28)]))
    if window=='CONTINUOUS':continuous[name+'/'+case]=[segment(account,a,b)for a,b in WINDOWS.values()]
    print(json.dumps(dict(window=window,strategy=name,case=case,status='COMPLETE')),flush=True)
  if window!='CONTINUOUS':
   for family in FAMILIES:
    if family not in scores:model_rows.append(dict(window=window,family=family,status='BLOCKED_MISSING_PIT_MINING_CONTINUATION'));continue
    model_rows.append(dict(window=window,**prediction_measure(family,days,prices,scores[family],start,label_null[family])))
 if fitting_attempts:raise AssertionError('validation attempted learning')
 result=dict(status='COMPLETED_WITH_DISCLOSED_DATA_LIMITS',results=rows,prediction_metrics=model_rows,continuous_segments=continuous,
  validation_fitting_calls=0,model_selection_calls=0,cutoff='2025-12-31',input_reads=read.reads,
  finished_UTC=datetime.now(timezone.utc).isoformat(),source_qualification=source,
  scope='All registered candidates/costs retained including blocked/failed; reused historical validation, not fresh blind OOS.')
 dump('results.json',result);dump('validation-seal.json',dict(files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted(out.rglob('*'))if p.is_file()},fitting_calls=0,
  input_registration_sha256=hashlib.sha256((Path(root)/'registration.json').read_bytes()).hexdigest(),finished_UTC=datetime.now(timezone.utc).isoformat()))
 print(json.dumps(dict(status=result['status'],rows=len(rows),complete=sum(x['status']=='COMPLETE'for x in rows),fitting_calls=0)),flush=True)

if __name__=='__main__':evaluate('/validation','/out')
