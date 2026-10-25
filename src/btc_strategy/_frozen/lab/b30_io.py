"""Prior-score rank roles; current-year forecasts and raw fit samples isolated."""
import os
import sys
from pathlib import Path
from .io import ROOT,DATA
from .walkforward_io import FOLDS,load_fold

STUDY=ROOT/'studies/B30-forecast-strength-sizing'
UPSTREAM=ROOT/'studies/B29-prior-forecast-exits'
CONTROL_IDS=('Y01','Y04','Y05')


def permitted(path,year,stage):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        if p==FOLDS/'manifest.json':return True
        years=range(2018,2026)if stage=='replay'else (year,)
        roles=('train',)if stage=='train'else ('train','test')
        return p in {FOLDS/str(y)/(r+'.json')for y in years for r in roles}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            rel=p.relative_to(STUDY).parts
            if rel[0]in ('registration.json','spec.md'):return True
            if len(rel)>=3 and rel[0]=='folds':
                if not (2018<=int(rel[1])<=2025 if stage=='replay'else int(rel[1])==year):return False
                if stage=='test'and rel[2]=='samples':return False
                return stage!='train'or rel[2]not in ('predictions.json.gz','test-receipt.json')
            return stage=='replay'and rel[0]in ('accounts','results.json','analysis.json','verification.json')
        if p.is_relative_to(UPSTREAM):
            rel=p.relative_to(UPSTREAM).parts
            if rel==('registration.json',):return True
            if len(rel)==3 and rel[0]=='folds':
                prior=int(rel[1])
                if not 2018<=prior<=2025:return False
                if stage=='replay':return rel[2]in ('seal.json','training.json','predictions.json.gz','test-receipt.json')
                if prior>year:return False
                if rel[2]in ('seal.json','training.json'):return True
                return rel[2]in ('predictions.json.gz','test-receipt.json')and (stage=='test'or prior<year)
            return stage=='replay'and len(rel)==3 and rel[0]=='accounts'and rel[1]in CONTROL_IDS
        return False
    denied=(ROOT/'archives',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'),
            Path('/workspace/Polymarket_Arbitrage_Robot/outputs'),Path('/workspace/market-source-history'),Path('/workspace/scratch'))
    return not any(p.is_relative_to(d)for d in denied)


def install_guard(year,stage):
    if year not in range(2018,2026)or stage not in ('train','test','replay'):raise ValueError('invalid role')
    reads=set()
    def guard(event,args):
        if event!='open'or not isinstance(args[0],(str,bytes)):return
        if args[1]is not None and 'r'not in args[1]and '+'not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,year,stage):raise ValueError('B30 read denied: '+str(p))
        if p.is_relative_to(DATA)or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads
