"""Full2018–2025 development roles; current-test denial for2025 fitting."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA
from .walkforward_io import FOLDS
from .b64a import BANKS

STUDY = ROOT/'studies/B65-full-window-model-completion'
DEPTH_SOURCES = {2:ROOT/'studies/B61-boosted-stop-losses', 3:ROOT/'studies/B62-depth3-loss-controls'}
LEGACY = {'Y01':(ROOT/'studies/B29-prior-forecast-exits','Y01'),
          **{n:(ROOT/'studies/B46-bear-short-trailing',n) for n in ('T08','T10','T12')},
          **{n:(BANKS['AVERAGE'],n) for n in ('A01','A02')},
          **{n:(BANKS['CARRY'],n) for n in ('H04','H05','H06')},
          **{n:(BANKS['POST'],n) for n in ('S03','S04')},
          **{n:(BANKS['SIZE'],n) for n in ('C02','C04')}}


def permitted(path, role):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        if p==FOLDS/'manifest.json':return True
        years=(2025,) if role in ('train','test') else range(2018,2026)
        parts=('train',) if role=='train' else ('train','test')
        return p in {FOLDS/str(y)/f'{part}.json' for y in years for part in parts}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            rel=p.relative_to(STUDY).parts
            if len(rel)==1:return rel[0] in ('registration.json','spec.md') or role=='audit'
            if rel[0]=='folds':
                if len(rel)<3 or rel[1]!='2025':return False
                if role=='train':return rel[2] in ('models','labels.json.gz','training.json','seal.json')
                if role=='test':return rel[2] in ('models','training.json','seal.json','predictions.json.gz','test-receipt.json')
                if role=='replay':return rel[2] in ('training.json','seal.json','predictions.json.gz','test-receipt.json')
                return True
            return role in ('replay','audit') and rel[0]=='accounts'
        for base in set([*BANKS.values(),*DEPTH_SOURCES.values(),*(b for b,_ in LEGACY.values())]):
            if not p.is_relative_to(base):continue
            rel=p.relative_to(base).parts
            if rel==('registration.json',):return True
            if rel==('verification.json',):return role=='audit'
            if len(rel)==3 and rel[0]=='folds' and rel[1].isdigit():
                y=int(rel[1]);limit=2024 if base in DEPTH_SOURCES.values() else 2025
                if not 2018<=y<=limit:return False
                if role=='train':return base==BANKS['AVERAGE'] and y==2025 and rel[2] in ('training.json','seal.json')
                if role=='test':return base==BANKS['AVERAGE'] and y==2025 and rel[2] in ('training.json','seal.json','test-receipt.json','predictions.json.gz')
                return rel[2] in ('training.json','seal.json','test-receipt.json','predictions.json.gz')
            return role in ('replay','audit') and any(p==b/'accounts'/n/f'{c}.json.gz'
                for b,n in LEGACY.values() for c in ('BASE','STRESS','SEVERE','DELAY'))
        return False
    if p==ROOT/'notes/RESEARCH_2025_SCOPE_AUTHORIZED.md':return True
    if any(p.is_relative_to(q) for q in (ROOT/'archives',ROOT/'notes',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'))):return False
    if p.is_relative_to('/workspace') and not p.is_relative_to(ROOT):
        return any(p.is_relative_to(q) for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/BinanceTradingRobot/backend/src'),Path('/workspace/.venvs')))
    return True


def install_guard(role):
    if role not in ('train','test','replay','audit'):raise ValueError('invalid B65 role')
    reads=set()
    def hook(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,role):raise ValueError('B65 read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads
