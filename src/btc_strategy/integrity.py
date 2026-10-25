"""Content integrity and complete expert-review receipts; standard library only."""
from pathlib import Path
import json,hashlib
from .artifacts import ROOT
ROLES=('statistics','data','models','execution','risk','repro')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_integrity():
 m=json.loads((ROOT/'provenance/release_manifest.json').read_text())
 for r in m['files']:
  p=(ROOT/r['path']).resolve()
  if not p.is_relative_to(ROOT):raise ValueError('manifest escape')
  if sha(p)!=r['sha256']:raise ValueError('release content mismatch: '+r['path'])
 return dict(status='PASS',files=len(m['files']),bytes=sum(r['bytes']for r in m['files']),scope='Content equality; not alpha, PIT or live safety certification.')


def verify_reviews(expected_rounds=12):
 count=0
 for n in range(1,expected_rounds+1):
  p=ROOT/'review/rounds'/f'{n:02d}';chair=json.loads((p/'chair.json').read_text());assert chair['round']==n
  for role in ROLES:
   q=p/(role+'.json');r=json.loads(q.read_text());assert r['round']==n and r['role']==role
   assert chair['submissions'][role]['sha256']==sha(q)
   assert all(k in r for k in ('conclusion','verdict','evidence','checks_performed','unresolved','independence_statement'))
   count+=1
 return dict(status='PASS',rounds=expected_rounds,expert_submissions=count,roles=6,independence='Blind role reviews; AI roles, shared data, not independent market samples or external human audit.')
