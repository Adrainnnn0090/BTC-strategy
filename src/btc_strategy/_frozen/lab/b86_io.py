"""Current physical ETH roles for fitting; no source/model values in replay."""
import os,sys
from pathlib import Path
from .io import ROOT,DATA
from .walkforward_io import FOLDS
from .eth_role_parity import FEATURES
from .b82_io import PARENT,SOURCE,SHORT as LABELS,CARRY,ANCHOR,LEGACY
from .b86_prepare import STUDY,QUALITY


def permitted(path,year,role):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        if p in (FEATURES/'manifest.json',FOLDS/'manifest.json'):return True
        if p.is_relative_to(FEATURES):
            if role=='replay'or role in ('train','test')and year==2018:return False
            years=range(2019,2026)if role=='audit'else(year,);parts=('train',)if role=='train'else('train','test')
            return p in {FEATURES/str(y)/f'{r}.json.gz'for y in years for r in parts}
        years=(year,)if role in ('train','test')else range(2018,2026);parts=('train',)if role=='train'else('train','test')
        return p in {FOLDS/str(y)/f'{r}.json'for y in years for r in parts}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            z=p.relative_to(STUDY).parts
            if len(z)==1:return z[0]in ('registration.json','spec.md','preparation-registration.json','preparation-spec.md','source-verification.json','source-checks.json','source-seal.json')or role=='audit'
            if z[0]=='folds'and len(z)>=3:
                if not z[1].isdigit()or not 2018<=int(z[1])<=2025 or role in ('train','test')and int(z[1])!=year:return False
                if role=='audit':return True
                return z[2]in ({'training.json','seal.json','models'}if role=='train'else{'training.json','seal.json','models','predictions.json.gz','test-receipt.json'}if role=='test'else{'training.json','seal.json','predictions.json.gz','test-receipt.json'})
            return role in ('replay','audit')and z[0]=='accounts'
        if p in {b/'registration.json'for b in (PARENT,SOURCE,LABELS,CARRY,ANCHOR,QUALITY)}:return True
        if role=='audit'and p in {b/'verification.json'for b in (PARENT,LABELS,CARRY,ANCHOR)}|{QUALITY/'quality.json',QUALITY/'decision.json'}:return True
        for base in (PARENT,SOURCE,LABELS,CARRY):
            if not p.is_relative_to(base):continue
            z=p.relative_to(base).parts
            if len(z)==3 and z[0]=='folds'and z[1].isdigit()and 2018<=int(z[1])<=2025:
                if role=='audit':return z[2]in ('training.json','seal.json','predictions.json.gz','test-receipt.json')or base==LABELS and int(z[1])>2018 and z[2]=='labels.json.gz'
                if role=='replay':return z[2]in ('training.json','seal.json','predictions.json.gz','test-receipt.json')
                if int(z[1])!=year or base==CARRY:return False
                if role=='train':return base in (SOURCE,LABELS)and(z[2]in ('training.json','seal.json')or base==LABELS and year>2018 and z[2]=='labels.json.gz')
                return z[2]in ('training.json','seal.json','predictions.json.gz','test-receipt.json')
        return role in ('replay','audit')and any(p==b/'accounts'/n/f'{c}.json.gz'for b,n in LEGACY.values()for c in ('BASE','STRESS','SEVERE','DELAY'))
    if p in {ROOT/'notes'/n for n in ('RESEARCH_2025_SCOPE_AUTHORIZED.md','proposed-reported-volume-short-net.md','proposed-reported-volume-long-core.md','proposed-eth-short-net-transfer.md')}:return True
    if any(p.is_relative_to(q)for q in (ROOT/'notes',ROOT/'archives',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'))):return False
    if p.is_relative_to('/workspace')and not p.is_relative_to(ROOT):return any(p.is_relative_to(q)for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/BinanceTradingRobot/backend/src'),Path('/workspace/.venvs')))
    return True


def install_guard(year,role):
    if year not in range(2018,2026)or role not in ('train','test','replay','audit'):raise ValueError('invalid B86 role')
    reads=set()
    def hook(event,args):
        if event!='open'or not isinstance(args[0],(str,bytes)):return
        if args[1]is not None and 'r'not in args[1]and '+'not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,year,role):raise ValueError('B86 read denied: '+str(p))
        if p.is_relative_to(DATA)or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads
