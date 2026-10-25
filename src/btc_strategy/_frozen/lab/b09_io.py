"""B09 per-fold training isolation, with only a sealed B05 control model allowed."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA
from .walkforward_io import FOLDS, load_fold

STUDY = ROOT/'studies/B09-tree-path-calendar'
UPSTREAM = ROOT/'studies/B05-annual-walkforward'


def permitted(path, year, stage):
    path = Path(path).resolve()
    if path.is_relative_to(DATA):
        if path == FOLDS/'manifest.json':
            return True
        years = range(2018,2026) if stage=='replay' else (year,)
        names = ('train.json',) if stage=='train' else ('train.json','test.json')
        return path in {FOLDS/str(y)/n for y in years for n in names}
    if path.is_relative_to(ROOT/'studies'):
        if path.is_relative_to(STUDY):
            rel=path.relative_to(STUDY).parts
            if rel[0] in ('registration.json','spec.md','sources.md'):
                return True
            if rel[0]=='folds' and len(rel)>=3:
                y=int(rel[1])
                return (2018<=y<=2025 if stage=='replay' else y==year and
                        (stage=='test' or rel[2] not in ('predictions.json.gz','test-receipt.json')))
            return stage=='replay' and rel[0] in ('accounts','results.json')
        if path.is_relative_to(UPSTREAM):
            rel=path.relative_to(UPSTREAM).parts
            if rel==('registration.json',):
                return True
            if stage=='test' and len(rel)>=3 and rel[:2]==('folds',str(year)):
                return rel[2]=='seal.json' or rel[2:]==('models','HUBER_PRICE20_H60.json.gz')
            return stage=='replay' and len(rel)==3 and rel[:2]==('accounts','W02')
        return False
    forbidden=(ROOT/'archives',Path('/workspace/BinanceTradingRobot/research'),
               Path('/workspace/BinanceTradingRobot/strategy'),Path('/workspace/Polymarket_Arbitrage_Robot/outputs'))
    return not any(path.is_relative_to(p) for p in forbidden)


def install_guard(year,stage):
    if year not in range(2018,2026) or stage not in ('train','test','replay'):
        raise ValueError('invalid fold role')
    reads=set()
    def guard(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        path=Path(os.fsdecode(args[0])).resolve()
        if not permitted(path,year,stage):
            raise ValueError('B09 fold read denied: '+str(path))
        if path.is_relative_to(DATA) or path.is_relative_to(ROOT/'studies'):
            reads.add(str(path.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads
