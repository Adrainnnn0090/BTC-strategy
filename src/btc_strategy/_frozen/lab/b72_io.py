"""Read-only sealed forecasts; no fitting role, label/state or 2026 reads."""
import os,sys
from pathlib import Path
from .io import ROOT,DATA
from .walkforward_io import FOLDS
from .b71_io import LEGACY as OLD

STUDY=ROOT/'studies/B72-cold-budget-exposure'
SOURCE=ROOT/'studies/B50-cross-market-fixed-averages'
MODELS=ROOT/'studies/B67-lag-matched-short-supervision'
ANCHOR=ROOT/'studies/B68-cross-count-short-models'
LEGACY={k:OLD[k] for k in ('L05','L06','T12','Y01')}


def permitted(path,role):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        return p==FOLDS/'manifest.json' or p in {FOLDS/str(y)/f'{part}.json' for y in range(2018,2026) for part in ('train','test')}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            r=p.relative_to(STUDY).parts
            return len(r)==1 and (r[0] in ('registration.json','spec.md') or role=='audit') or role in ('replay','audit') and r[0]=='accounts'
        if p in {base/n for base in (SOURCE,MODELS,ANCHOR) for n in ('registration.json','verification.json')}:return True
        if any(p==base/'folds'/str(y)/n for base in (SOURCE,MODELS) for y in range(2018,2026)
            for n in ('training.json','seal.json','test-receipt.json','predictions.json.gz')):return True
        return any(p==base/'accounts'/n/f'{c}.json.gz' for base,n in LEGACY.values() for c in ('BASE','STRESS','SEVERE','DELAY'))
    if p in (ROOT/'notes/RESEARCH_2025_SCOPE_AUTHORIZED.md',ROOT/'notes/proposed-cold-budget-frontier.md'):return True
    if any(p.is_relative_to(q) for q in (ROOT/'archives',ROOT/'notes',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'))):return False
    if p.is_relative_to('/workspace') and not p.is_relative_to(ROOT):
        return any(p.is_relative_to(q) for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/BinanceTradingRobot/backend/src'),Path('/workspace/.venvs')))
    return True


def install_guard(role):
    if role not in ('replay','audit'):raise ValueError('B72 has no fitting role')
    reads=set()
    def hook(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,role):raise ValueError('B72 read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads
