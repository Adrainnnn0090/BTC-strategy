"""B51 physical annual folds and separate training, test, replay, audit roles."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA
from .walkforward_io import FOLDS, load_fold

STUDY = ROOT/'studies/B51-short-specific-payoff'
UPSTREAM = ROOT/'studies/B47-negative-score-short-entry'
CONTROL_IDS = ('G16', 'G18', 'G31', 'G01')


def permitted(path, year, stage):
    p = Path(path).resolve()
    all_folds = stage in ('replay', 'audit')
    if p.is_relative_to(DATA):
        if p == FOLDS/'manifest.json':
            return True
        years = range(2018, 2026) if all_folds else (year,)
        roles = ('train',) if stage == 'train' else ('train', 'test')
        return p in {FOLDS/str(y)/(r+'.json') for y in years for r in roles}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            rel = p.relative_to(STUDY).parts
            if rel in (('registration.json',), ('spec.md',), ('economic-spec.md',), ('preparation-seal.json',)):
                return True
            if len(rel) >= 3 and rel[0] == 'folds' and rel[1].isdigit():
                if not (2018 <= int(rel[1]) <= 2025 if all_folds else int(rel[1]) == year):
                    return False
                if len(rel) == 3:
                    return rel[2] in {'seal.json', 'training.json'} | ({'predictions.json.gz', 'test-receipt.json'} if stage != 'train' else set())
                if len(rel) == 4 and rel[2] == 'models':
                    return stage in ('train', 'test', 'audit') and rel[3].endswith('.json.gz')
                if len(rel) == 4 and rel[2] == 'labels':
                    return stage in ('train', 'audit') and rel[3] in ('SHORT_NET.json.gz', 'STOP.json.gz')
                if len(rel) == 4 and rel[2] == 'selection':
                    return stage in ('train', 'audit') and rel[3].endswith('.json.gz')
                return False
            if rel and rel[0] == 'label-parity':
                return stage == 'audit'
            return all_folds and bool(rel) and rel[0] in ('accounts', 'results.json', 'analysis.json', 'verification.json')
        if p.is_relative_to(UPSTREAM):
            rel = p.relative_to(UPSTREAM).parts
            if rel == ('registration.json',):
                return True
            if len(rel) == 3 and rel[0] == 'folds' and rel[1].isdigit():
                if not (2018 <= int(rel[1]) <= 2025 if all_folds else int(rel[1]) == year):
                    return False
                return rel[2] == 'seal.json' or rel[2] == 'training.json' and stage != 'test' or rel[2] in ('predictions.json.gz', 'test-receipt.json') and stage != 'train'
            return all_folds and len(rel) == 3 and rel[0] == 'accounts' and rel[1] in CONTROL_IDS
        return False
    denied = (ROOT/'archives', ROOT/'notes', Path('/workspace/BinanceTradingRobot/research'),
              Path('/workspace/BinanceTradingRobot/strategy'), Path('/workspace/Polymarket_Arbitrage_Robot/outputs'),
              Path('/workspace/market-source-history'), Path('/workspace/scratch'))
    return not any(p.is_relative_to(d) for d in denied)


def install_guard(year, stage):
    if year not in range(2018, 2026) or stage not in ('train', 'test', 'replay', 'audit'):
        raise ValueError('invalid B51 role')
    reads = set()
    def guard(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        p = Path(os.fsdecode(args[0])).resolve()
        if not permitted(p, year, stage):
            raise ValueError('B51 read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):
            reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads
