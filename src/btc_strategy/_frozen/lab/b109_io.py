"""Static agreement roles: no current forecast in train, no model/source values."""
import os,sys
from pathlib import Path
from .io import ROOT,DATA
from .walkforward_io import FOLDS
from .b108_io import PARENT,SOURCE,SHORT,CARRY,ANCHOR,LEGACY as ORIGINAL_LEGACY

STUDY=ROOT/'studies/B109-long-profit-local-coordinate'
PROOF=ROOT/'studies/B108-cold-profit-trail-neighbors'
LEGACY=dict(ORIGINAL_LEGACY)


def permitted(path,year,role):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        if p==FOLDS/'manifest.json':return True
        years=(year,)if role in ('train','test')else range(2018,2026);parts=('train',)if role=='train'else('train','test')
        return p in {FOLDS/str(y)/f'{r}.json'for y in years for r in parts}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            z=p.relative_to(STUDY).parts
            if len(z)==1:return z[0]in ('registration.json','spec.md','checks.json')or role=='audit'
            if z[0]=='folds'and len(z)==3:
                if not z[1].isdigit()or not 2018<=int(z[1])<=2025 or role in ('train','test')and int(z[1])!=year:return False
                return z[2]in ({'training.json','seal.json'}if role=='train'else{'training.json','seal.json','predictions.json.gz','test-receipt.json'})
            return role in ('replay','audit')and z[0]=='accounts'
        if p in {b/'registration.json'for b in (PARENT,SOURCE,SHORT,CARRY,ANCHOR,PROOF)}:return True
        if role=='audit'and p in {b/'verification.json'for b in (PARENT,SHORT,CARRY,ANCHOR,PROOF)}:return True
        for base in (PARENT,SOURCE,SHORT,CARRY):
            if not p.is_relative_to(base):continue
            z=p.relative_to(base).parts
            if len(z)==3 and z[0]=='folds'and z[1].isdigit()and 2018<=int(z[1])<=2025:
                if role in ('replay','audit'):return z[2]in ('training.json','seal.json','predictions.json.gz','test-receipt.json')
                if int(z[1])!=year or base==CARRY:return False
                if role=='train':return base==SOURCE and z[2]in ('training.json','seal.json')
                return z[2]in ('training.json','seal.json','predictions.json.gz','test-receipt.json')
        return role in ('replay','audit')and any(p==b/'accounts'/n/f'{c}.json.gz'for b,n in LEGACY.values()for c in ('BASE','STRESS','SEVERE','DELAY'))
    if p in {ROOT/'notes'/n for n in ('RESEARCH_2025_SCOPE_AUTHORIZED.md','proposed-reported-volume-short-net.md','proposed-reported-volume-long-core.md','proposed-price-core-trail-activation.md','proposed-price-core-consensus-entry.md','proposed-persistent-negative-long-exits.md','proposed-patient-long-profit-exits.md','proposed-long-volatility-cap-relaxation.md','proposed-faster-cold-short-trend.md','proposed-b103a-independent-mask-audit.md','proposed-cold-trend-local-neighbors.md','proposed-cold-short-entry-momentum.md','proposed-shorter-cold-entry-momentum.md','proposed-cold-short-profit-trailing.md','proposed-cold-profit-trail-neighbors.md','proposed-long-profit-local-coordinate.md')}:return True
    if any(p.is_relative_to(q)for q in (ROOT/'notes',ROOT/'archives',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'))):return False
    if p.is_relative_to('/workspace')and not p.is_relative_to(ROOT):return any(p.is_relative_to(q)for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/BinanceTradingRobot/backend/src'),Path('/workspace/.venvs')))
    return True


def install_guard(year,role):
    if year not in range(2018,2026)or role not in ('train','test','replay','audit'):raise ValueError('invalid B109 role')
    reads=set()
    def hook(event,args):
        if event!='open'or not isinstance(args[0],(str,bytes)):return
        if args[1]is not None and 'r'not in args[1]and '+'not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,year,role):raise ValueError('B109 read denied: '+str(p))
        if p.is_relative_to(DATA)or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads
