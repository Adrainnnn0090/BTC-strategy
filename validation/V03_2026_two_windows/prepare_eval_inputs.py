"""Build sealed INFERENCE-only prefixes; never mounted by the fitting container."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,gzip,json,hashlib,shutil,subprocess

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare(repo,out):
 repo=Path(repo).resolve();out=Path(out).resolve();base=repo/'validation/V03_2026_two_windows'
 if out.exists()and any(out.iterdir()):raise ValueError('refuse overwrite of sealed inference inputs')
 out.mkdir(parents=True,exist_ok=True)
 def copy(src,dst):
  p=out/dst;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,p)
 for p in sorted((base/'training').glob('*.json.gz')):
  if p.stem.split('.')[0]not in('base_tree','stop44','price47','short_huber','short_median','mining58'):continue
  copy(p,'models/'+p.name)
 for src,dst in(('seal.json','model-seal.json'),('policies.json','policies.json'),('label_baselines.json','label_baselines.json')):copy(base/'training'/src,dst)
 for p in sorted((repo/'artifacts/contexts').glob('*.json.gz')):copy(p,'contexts/'+p.name)
 copy(base/'intake/data-seal.json','source-seal.json')
 train=json.loads(gzip.decompress((repo/'artifacts/factors/prices.json.gz').read_bytes()));raw=json.loads((base/'intake/prices-2026.json').read_text())['rows']
 assert train['days'][-1]=='2025-12-31'and raw[0]['date']=='2026-01-01'and raw[-1]['date']=='2026-10-23'
 for key,end in(('H1_TO_JUN29','2026-06-29'),('JUN30_TO_OCT23','2026-10-23')):
  rows=[r for r in raw if r['date']<=end];value=dict(role='INFERENCE_PREFIX_ONLY_NO_FITTING',training_history_end='2025-12-31',validation_start='2026-01-01',validation_end=end,
   days=train['days']+[r['date']for r in rows],prices=train['prices']+[r['price']for r in rows])
  p=out/'prices'/(key+'.json.gz');p.parent.mkdir(exist_ok=True);p.write_bytes(gzip.compress((json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0))
 registry=dict(role='EVALUATION_ONLY',evaluation_code_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
  source_code_sha256={str(p.relative_to(repo)):sha(p)for p in sorted((repo/'src/btc_validation').rglob('*.py'))},
  files={str(p.relative_to(out)):sha(p)for p in sorted(out.rglob('*'))if p.is_file()},
  model_contract_sha256=sha(base/'MODEL_CONTRACT.json'),implementation_amendment_sha256=sha(base/'IMPLEMENTATION_AMENDMENT_01.json'),
  prepared_UTC=datetime.now(timezone.utc).isoformat(),qualification='Past prefix is causal feature warmup; no fit, tune, normalization fit or model selection is permitted. Training matrices and label vectors are not mounted.')
 (out/'registration.json').write_text(json.dumps(registry,indent=2)+'\n')
 print('SEALED EVALUATION INPUTS',len(registry['files']),'training prefix and raw2026remain physically separate in source; concatenation is inference-only')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',default=str(Path(__file__).resolve().parents[2]));p.add_argument('--out',required=True);a=p.parse_args();prepare(a.repo,a.out)
