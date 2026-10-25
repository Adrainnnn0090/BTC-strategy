"""Original annual learners on a physical 2017--2025 prefix, isolated from validation.

Run in a network-none container with only /train (readonly) and /out mounted.
This module is never imported by the validation inference worker.
"""
from pathlib import Path
from datetime import datetime,timezone
import gzip,json,hashlib,sys,os
import numpy as np
from threadpoolctl import threadpool_limits
from btc_strategy._frozen.lab import tree_stability,label_trees,execution_labels,lagged_short,short_loss_models
from btc_strategy._runtime.tree_factors import matrix
from btc_strategy._runtime.volume_short_factors import append_volume
from btc_strategy._runtime.mining_ablation import ablate
from .protocol import TRAIN_END,SEEDS,validate_clock

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def train(input_dir,output_dir):
 src=Path(input_dir).resolve();out=Path(output_dir).resolve()
 if out.exists()and any(out.iterdir()):raise ValueError('refuse overwrite of completed training output')
 out.mkdir(parents=True,exist_ok=True)
 if Path('/validation').exists()or Path('/workspace/BTCStrategyResearchLedger').exists():
  raise ValueError('training container must not mount validation or the old ledger')
 reads=[]
 def hook(event,args):
  if event!='open'or not isinstance(args[0],(str,bytes)):return
  p=Path(os.fsdecode(args[0])).resolve()
  if p.is_relative_to(src):reads.append(str(p.relative_to(src)))
  if str(p).startswith(('/validation/','/workspace/')):raise ValueError('training read denied: '+str(p))
 sys.addaudithook(hook)
 meta=json.loads((src/'manifest.json').read_text())
 def load(name):
  p=src/name
  if digest(p)!=meta['files'][name]:raise ValueError('training input changed')
  b=p.read_bytes();return json.loads(gzip.decompress(b)if p.suffix=='.gz'else b)
 market=load('prices.json.gz');days,prices=market['days'],market['prices'];validate_clock(days,prices,training=True,end=TRAIN_END)
 mining=load('mining.json.gz')['mining']
 if [r['date']for r in mining]!=days:raise ValueError('mining training prefix differs')
 rows=matrix(days,prices,'CAL44');rows47=append_volume(days,prices,None,7,'PRICE47');rows58=ablate(rows,mining,'DYNAMICS',60)
 cut=len(days)-1;long_ids=tree_stability.matured(cut,60)
 stop_bank=execution_labels.records(days,prices,cut,'STOP');stop=execution_labels.target_vector(stop_bank,len(days))
 short_bank,common=lagged_short.records(days,prices,cut)
 if long_ids[-1]+61>cut-6 or common[-1]+62>cut-6:raise ValueError('unmatured training labels')
 models={};receipts={};fits=0
 def save(name,members,receipt):
  nonlocal fits
  fits+=receipt['model_fits'];models[name]=members;receipts[name]=receipt
  value=dict(family=name,cutoff=TRAIN_END,members=members)
  p=out/(name+'.json.gz');p.write_bytes(gzip.compress((json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n').encode(),mtime=0))
  print(json.dumps(dict(stage='fit',family=name,states=len(members),model_fits=receipt['model_fits'])),flush=True)
 with threadpool_limits(limits=1):
  for name,x in (('base_tree',rows),('mining58',rows58)):
   pairs=[tree_stability.tune(x,prices,cut,s)for s in SEEDS]
   save(name,[s for s,r in pairs],dict(model_fits=35,details=[r for s,r in pairs]))
  for name,x in (('stop44',rows),('price47',rows47)):
   members,receipt=label_trees.tune(x,stop,cut,'STOP');save(name,members,receipt)
  for name,loss in (('short_huber','HUBER'),('short_median','MEDIAN')):
   spec=next(x for x in short_loss_models.LOSSES if x['id']==loss);members=[];recs=[]
   for head in lagged_short.HEADS:
    vector=lagged_short.target_vector(short_bank[head['id']],len(days))
    for seed in SEEDS:
     state,rec=short_loss_models.fit(rows,vector,common,cut,head,spec,seed);members.append(state);recs.append(rec)
   save(name,members,dict(model_fits=14,details=recs))
 if fits!=168 or sum(map(len,models.values()))!=56:raise AssertionError('wrong fit roster')
 (out/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
 baseline={}
 long_target=tree_stability.labels(prices,long_ids,60)
 for family in models:
  if family.startswith('short_'):
   arrays=[lagged_short.target_vector(short_bank[h['id']],len(days))[common]for h in lagged_short.HEADS]
   y=(arrays[0]+arrays[1])/2
  else:y=stop[long_ids]if family in('stop44','price47')else long_target
  baseline[family]=dict(mean=float(np.mean(y)),median=float(np.median(y)),samples=len(y))
 (out/'label_baselines.json').write_text(json.dumps(baseline,indent=2)+'\n')
 files={p.name:digest(p)for p in sorted(out.iterdir())if p.is_file()}
 proof=dict(status='TRAINING_ONLY_SEALED',cutoff=TRAIN_END,rows=len(days),long_samples=len(long_ids),short_common_samples=len(common),
  long_last_label=int(long_ids[-1]+61),short_last_label=int(common[-1]+62),cut_index=cut,embargo=6,
  fits=fits,final_states=56,validation_rows=0,validation_reads=0,validation_fits=0,
  inputs_sha256=digest(src/'manifest.json'),input_reads=reads,files=files,
  finished_UTC=datetime.now(timezone.utc).isoformat(),qualification='Original fixed annual profiles/seeds and inner past-only selection; no validation mounted.')
 (out/'seal.json').write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({k:v for k,v in proof.items()if k not in('files','input_reads')}),flush=True)

if __name__=='__main__':train('/train','/out')
