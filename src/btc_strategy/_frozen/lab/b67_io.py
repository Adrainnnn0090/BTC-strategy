"""Strict annual development roles, original only-forward sources and no2026."""
import os,sys
from pathlib import Path
from .io import ROOT,DATA
from .walkforward_io import FOLDS
from .b66_io import LEGACY as OLD

STUDY=ROOT/'studies/B67-lag-matched-short-supervision'
SOURCE=ROOT/'studies/B50-cross-market-fixed-averages'
PREVIOUS=ROOT/'studies/B66-conditional-bear-short-models'
LEGACY={'Q04':(PREVIOUS,'Q04'),'Q05':(PREVIOUS,'Q05'),**{k:OLD[k] for k in ('T12','Y01')}}


def permitted(path,year,role):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        if p==FOLDS/'manifest.json':return True
        years=(year,) if role in ('train','test') else range(2018,2026)
        parts=('train',) if role=='train' else ('train','test')
        return p in {FOLDS/str(y)/f'{part}.json' for y in years for part in parts}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            r=p.relative_to(STUDY).parts
            if len(r)==1:return r[0] in ('registration.json','spec.md') or role=='audit'
            if r[0]=='folds' and len(r)>=3:
                if not r[1].isdigit() or not 2018<=int(r[1])<=2025:return False
                if role in ('train','test') and int(r[1])!=year:return False
                allowed={'training.json','seal.json'}
                if role=='train':allowed|={'models','labels.json.gz'}
                elif role=='test':allowed|={'models','predictions.json.gz','test-receipt.json'}
                elif role=='replay':allowed|={'predictions.json.gz','test-receipt.json'}
                else:return True
                return r[2] in allowed
            return role in ('replay','audit') and r[0] in ('accounts','label-parity')
        for base in (SOURCE,PREVIOUS):
            if p==base/'registration.json' or p==PREVIOUS/'verification.json':return True
            if p.is_relative_to(base):
                r=p.relative_to(base).parts
                if len(r)==3 and r[0]=='folds' and r[1].isdigit():
                    if not 2018<=int(r[1])<=2025 or role in ('train','test') and int(r[1])!=year:return False
                    if base==PREVIOUS:return role in ('replay','audit') and r[2] in ('seal.json','test-receipt.json','predictions.json.gz')
                    return r[2] in (('training.json','seal.json') if role=='train' else ('training.json','seal.json','test-receipt.json','predictions.json.gz'))
        return role in ('replay','audit') and any(p==b/'accounts'/n/f'{c}.json.gz' for b,n in LEGACY.values() for c in ('BASE','STRESS','SEVERE','DELAY'))
    if p==ROOT/'notes/RESEARCH_2025_SCOPE_AUTHORIZED.md':return True
    if any(p.is_relative_to(q) for q in (ROOT/'archives',ROOT/'notes',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'))):return False
    if p.is_relative_to('/workspace') and not p.is_relative_to(ROOT):
        return any(p.is_relative_to(q) for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/BinanceTradingRobot/backend/src'),Path('/workspace/.venvs')))
    return True


def install_guard(year,role):
    if not 2018<=year<=2025 or role not in ('train','test','replay','audit'):raise ValueError('invalid B67 role')
    reads=set()
    def hook(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,year,role):raise ValueError('B67 read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads
