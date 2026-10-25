"""Explicit, separate research-release verification gates."""
import argparse,json
from .integrity import verify_integrity,verify_reviews

def main():
 p=argparse.ArgumentParser();p.add_argument('--integrity',action='store_true');p.add_argument('--review',action='store_true');p.add_argument('--models',action='store_true');p.add_argument('--targets',action='store_true');a=p.parse_args()
 if not any(vars(a).values()):p.error('select at least one verification gate')
 if a.integrity:print(json.dumps(verify_integrity()),flush=True)
 if a.review:print(json.dumps(verify_reviews()),flush=True)
 if a.models:
  from .models import FAMILIES,verify_family
  for f in FAMILIES:print(json.dumps(verify_family(f)),flush=True)
 if a.targets:
  from .artifacts import catalog
  from .models import rebuild_context
  from .strategies import compose
  from .artifacts import read
  for row in catalog():
   n=row['id'];_,_,t,e=compose(n,rebuild_context(n));r=read('artifacts/targets/'+n+'.json.gz');assert t==r['targets']and e==r['entry_permission'];print(json.dumps(dict(strategy=n,actual_model_targets_exact=True)),flush=True)
if __name__=='__main__':main()
