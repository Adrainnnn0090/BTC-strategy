"""Local, hash-checkable research material. Never deserialize executable models."""
from pathlib import Path
import gzip,json,hashlib,os,re
_candidates=[Path(os.environ['BTC_STRATEGY_ROOT'])]if os.environ.get('BTC_STRATEGY_ROOT')else[Path(__file__).resolve().parents[2],Path.cwd()]
ROOT=next((p.resolve()for p in _candidates if(p/'artifacts/catalog.json').is_file()),None)
if ROOT is None:raise RuntimeError('Set BTC_STRATEGY_ROOT to the cloned research repository.')

def resolve_artifact(relative):
 p=(ROOT/relative).resolve()
 if not p.is_relative_to(ROOT):raise ValueError('artifact path escapes repository')
 z=p.relative_to(ROOT).parts
 if not z or z[0]not in('artifacts','models','training_inputs'):raise ValueError('unapproved artifact role')
 if z[0]in('artifacts','models','training_inputs'):
  if any(any(int(y)>2025 for y in re.findall(r'(?<!\d)(20\d{2})(?!\d)',x))for x in z):raise ValueError('2026+ economic data excluded')
 if any(re.match(r'^v0[12](?:-|$)',x,re.I)for x in z):raise ValueError('validation artifacts excluded')
 return p

def read(relative):
 p=resolve_artifact(relative);b=p.read_bytes();return json.loads(gzip.decompress(b)if p.suffix=='.gz'else b)

def restore(value):
 if isinstance(value,list):return[restore(x)for x in value]
 if isinstance(value,dict):return{int(k)if k.isdigit()else k:restore(v)for k,v in value.items()}
 return value
def catalog():return read('artifacts/catalog.json')['strategies']
def config(name):
 try:return next(x for x in catalog()if x['id']==name)
 except StopIteration:raise ValueError('unknown strategy: '+name)from None


def read_verified(relative,expected_sha256):
 p=resolve_artifact(relative)
 b=p.read_bytes()
 if hashlib.sha256(b).hexdigest()!=expected_sha256:raise ValueError('model content hash mismatch: '+relative)
 return json.loads(gzip.decompress(b)if p.suffix=='.gz'else b)
