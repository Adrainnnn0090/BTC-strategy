"""Verify the new holdout's seals without relaxing historical research gates."""
from pathlib import Path
import json,hashlib,argparse,gzip

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify(repo,outcomes=False):
 repo=Path(repo).resolve();d=repo/'validation/V03_2026_two_windows';c=json.loads((d/'MODEL_CONTRACT.json').read_text());am=json.loads((d/'IMPLEMENTATION_AMENDMENT_01.json').read_text())
 if sha(d/'MODEL_CONTRACT.json')!=am['original_contract_sha256']:raise ValueError('original contract changed')
 amendments={r['path']:r for r in am['changes']}
 for path,digest in c['files'].items():
  if path in amendments:
   if amendments[path]['old_sha256']!=digest:raise ValueError('unbound implementation amendment')
   digest=amendments[path]['new_sha256']
  if sha(repo/path)!=digest:raise ValueError('frozen training/model/code changed: '+path)
 s=json.loads((d/'training/seal.json').read_text())
 if s['cutoff']!='2025-12-31'or any(s[k]!=0 for k in('validation_reads','validation_rows','validation_fits')):raise ValueError('training/holdout separation failed')
 for path,h in s['files'].items():
  if sha(d/'training'/path)!=h:raise ValueError('trained state changed')
 rows=json.loads((d/'intake/prices-2026.json').read_text())['rows']
 from .protocol import calendar,WINDOWS
 if [r['date']for r in rows]!=calendar('2026-01-01','2026-10-23'):raise ValueError('incomplete validation data')
 for w,(a,b)in WINDOWS.items():
  x=json.loads((d/f'intake/{w}.json').read_text())
  if [r['date']for r in x['rows']]!=calendar(a,b):raise ValueError('wrong window membership')
 if outcomes:
  receipt=json.loads((d/'results/validation-seal.json').read_text())
  for path,h in receipt['files'].items():
   p=(d/'results'/path).resolve()
   if not p.is_relative_to(d/'results')or sha(p)!=h:raise ValueError('outcome artifact changed')
  result=json.loads((d/'results/results.json').read_text())
  if result['validation_fitting_calls']or result['model_selection_calls']:raise ValueError('validation leakage')
  reg=json.loads((d/'intake/EVALUATION_REGISTRATION.json').read_text())
  if sha(d/'intake/EVALUATION_REGISTRATION.json')!=receipt['input_registration_sha256']:raise ValueError('inference input registration changed')
  for path,h in reg['source_code_sha256'].items():
   if sha(repo/path)!=h:raise ValueError('evaluated source code changed')
  if len(result['results'])!=120:raise ValueError('missing registered strategy/cost/window rows')
 return dict(status='PASS_SEPARATION_AND_REPRODUCIBILITY',training_cutoff=s['cutoff'],final_states=s['final_states'],validation_days=len(rows),windows=WINDOWS,outcomes_verified=outcomes,
  qualification='Reused out-of-time validation; data-PIT and execution assumptions remain conditional. C04data block is not a passed strategy validation.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',default='.');p.add_argument('--outcomes',action='store_true');a=p.parse_args();print(json.dumps(verify(a.repo,a.outcomes)),flush=True)
