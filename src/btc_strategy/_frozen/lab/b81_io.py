"""Reported volume long-core roles; no raw archive or2026 reads."""
import os,sys
from pathlib import Path
from .io import ROOT,DATA
from .walkforward_io import FOLDS
from .volume_walkforward import FEATURES,load_volume
ANCHOR=ROOT/'studies/B68-cross-count-short-models'
from .b67_io import LEGACY as OLD

STUDY=ROOT/'studies/B81-reported-volume-long-core'
SOURCE=ROOT/'studies/B50-cross-market-fixed-averages'
LABELS=ROOT/'studies/B67-lag-matched-short-supervision'
ORIGINAL=ROOT/'studies/B66-conditional-bear-short-models'
PREPARATION=ROOT/'studies/B80-reported-volume-short-models'
LONGLABELS=ROOT/'studies/B36-network-activity-factors'
CARRY=ROOT/'studies/B22-annual-carry'
QUALITY=ROOT/'studies/B79-reported-spot-volume-source-audit'
LEGACY={'L05':(LABELS,'L05'),'L06':(LABELS,'L06'),**{k:OLD[k]for k in ('Q05','T12','Y01')},**{n:(CARRY,n)for n in ('H04','H05')}}


def permitted(path,year,role):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        if p.is_relative_to(FEATURES):
            if p==FEATURES/'manifest.json':return True
            if role=='replay'or role in ('train','test')and year==2018:return False
            years=(year,)if role in ('train','test')else range(2019,2026);parts=('train',)if role=='train'else('train','test')
            return p in {FEATURES/str(y)/f'{r}.json.gz'for y in years for r in parts}
        if p==FOLDS/'manifest.json':return True
        years=(year,) if role in ('train','test') else range(2018,2026)
        parts=('train',) if role=='train' else ('train','test')
        return p in {FOLDS/str(y)/f'{part}.json' for y in years for part in parts}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            r=p.relative_to(STUDY).parts
            if len(r)==1:return r[0] in ('registration.json','spec.md','preparation-spec.md','preparation-registration.json') or role=='audit'
            if r[0]=='folds' and len(r)>=3:
                if not r[1].isdigit() or not 2018<=int(r[1])<=2025:return False
                if role in ('train','test') and int(r[1])!=year:return False
                allowed={'training.json','seal.json'}
                if role in ('train','test'):allowed|={'models'}
                if role!='train':allowed|={'predictions.json.gz','test-receipt.json'}
                if role=='audit':return True
                return r[2] in allowed
            return role in ('replay','audit') and r[0]=='accounts'
        if p in {b/'registration.json' for b in (SOURCE,LABELS,ORIGINAL,ANCHOR,LONGLABELS,CARRY,PREPARATION)}:return True
        if role=='audit'and p in {b/n for b in (LABELS,ORIGINAL,QUALITY,ANCHOR,LONGLABELS,CARRY)for n in ('verification.json','quality.json','seal.json','registration.json')}:return True
        if p in {PREPARATION/'preparation-registration.json',PREPARATION/'preparation-spec.md'}:return True
        if p==PREPARATION/'source-verification.json':return role=='audit'
        if p.is_relative_to(LONGLABELS):
            z=p.relative_to(LONGLABELS).parts
            if len(z)>=3 and z[0]=='folds'and z[1].isdigit()and 2018<=int(z[1])<=2025 and(role=='audit'or int(z[1])==year):
                return len(z)==3 and z[2]in ('training.json','seal.json')or role in ('train','audit')and z[2:]==('labels','STOP.json.gz')
            return False
        for base in (SOURCE,LABELS,ORIGINAL,CARRY):
            if not p.is_relative_to(base):continue
            r=p.relative_to(base).parts
            if len(r)==3 and r[0]=='folds' and r[1].isdigit():
                if not 2018<=int(r[1])<=2025 or role in ('train','test') and int(r[1])!=year:return False
                if base==SOURCE:
                    return r[2] in (('training.json','seal.json') if role=='train' else ('training.json','seal.json','test-receipt.json','predictions.json.gz'))
                return role in ('replay','audit')and r[2]in ('training.json','seal.json','predictions.json.gz','test-receipt.json')
        return role in ('replay','audit') and any(p==b/'accounts'/n/f'{c}.json.gz' for b,n in LEGACY.values() for c in ('BASE','STRESS','SEVERE','DELAY'))
    if p in {ROOT/'notes/RESEARCH_2025_SCOPE_AUTHORIZED.md',ROOT/'notes/proposed-reported-volume-short-net.md',ROOT/'notes/proposed-reported-volume-long-core.md'}:return True
    if any(p.is_relative_to(q) for q in (ROOT/'archives',ROOT/'notes',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'))):return False
    if p.is_relative_to('/workspace') and not p.is_relative_to(ROOT):
        return any(p.is_relative_to(q) for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/BinanceTradingRobot/backend/src'),Path('/workspace/.venvs')))
    return True


def install_guard(year,role):
    if not 2018<=year<=2025 or role not in ('train','test','replay','audit'):raise ValueError('invalid B81 role')
    reads=set()
    def hook(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,year,role):raise ValueError('B81 read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads


def load_volume_fold(year,days,role):
    return load_volume(year,days,role)
