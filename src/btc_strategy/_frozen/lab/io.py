from datetime import date,timedelta
import gzip,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data'
TRAIN_END='2022-12-31'
TARGET_END='2025-12-31'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
 p=Path(p);raw=p.read_bytes()
 return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def write(p,value):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 raw=(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()
 if p.suffix=='.gz':raw=gzip.compress(raw,mtime=0)
 with p.open('xb') as f:f.write(raw)
def install_guard(assessment=False):
 accesses=set();target=(DATA/'target-assessment-2023-2025.json').resolve()
 forbidden=[Path('/workspace/BinanceTradingRobot/research/snapshots'),Path('/workspace/BinanceTradingRobot/strategy'),Path('/workspace/Polymarket_Arbitrage_Robot/outputs')]
 def guard(event,args):
  if event!='open' or not isinstance(args[0],(str,bytes)):return
  path=Path(os.fsdecode(args[0])).resolve();mode=args[1]
  if mode is not None and 'r' not in mode and '+' not in mode:return
  if any(path.is_relative_to(d) for d in forbidden) or (path==target and not assessment):raise ValueError('research read guard denied: '+str(path))
  if path.is_relative_to(DATA):accesses.add(str(path.relative_to(ROOT)))
 sys.addaudithook(guard);return accesses

def load(assessment=False):
 meta=read(DATA/'manifest.json');names=['train-prices.json']+(['target-assessment-2023-2025.json'] if assessment else [])
 rows=[]
 for name in names:
  p=DATA/name
  if sha(p)!=meta['files'][name]:raise ValueError('input digest changed')
  rows.extend(read(p))
 days=[r['date'] for r in rows];end=TARGET_END if assessment else TRAIN_END
 first=date(2017,1,1);last=date.fromisoformat(end)
 expected=[(first+timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
 if days!=expected:raise ValueError('wrong physical period')
 return days,[r['price'] for r in rows]
