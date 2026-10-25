"""Annual roles for fixed-budget controls; no raw rank samples or outcomes at seal."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA
from .walkforward_io import FOLDS, load_fold

STUDY = ROOT/'studies/B31-constant-sizing-controls'
UPSTREAM = ROOT/'studies/B30-forecast-strength-sizing'
CONTROL_IDS = tuple(f'P{i:02}' for i in range(1, 10))


def permitted(path, year, stage):
    p = Path(path).resolve()
    if p.is_relative_to(DATA):
        if p == FOLDS/'manifest.json':
            return True
        years = range(2018, 2026) if stage == 'replay' else (year,)
        roles = ('train',) if stage == 'train' else ('train', 'test')
        return p in {FOLDS/str(y)/(r+'.json') for y in years for r in roles}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY) or p.is_relative_to(UPSTREAM):
            own = p.is_relative_to(STUDY)
            rel = p.relative_to(STUDY if own else UPSTREAM).parts
            if rel in (('registration.json',), ('spec.md',)):
                return True
            if len(rel) == 3 and rel[0] == 'folds':
                if not (2018 <= int(rel[1]) <= 2025 if stage == 'replay' else int(rel[1]) == year):
                    return False
                files = ('training.json', 'seal.json') if stage == 'train' else (
                    'training.json', 'seal.json', 'predictions.json.gz', 'test-receipt.json')
                return rel[2] in files
            if stage == 'replay':
                if own:
                    return rel[0] in ('accounts', 'results.json', 'analysis.json', 'verification.json')
                return len(rel) == 3 and rel[0] == 'accounts' and rel[1] in CONTROL_IDS
        return False
    denied = (ROOT/'archives', Path('/workspace/BinanceTradingRobot/research'),
        Path('/workspace/BinanceTradingRobot/strategy'), Path('/workspace/Polymarket_Arbitrage_Robot/outputs'),
        Path('/workspace/market-source-history'), Path('/workspace/scratch'))
    return not any(p.is_relative_to(d) for d in denied)


def install_guard(year, stage):
    if year not in range(2018, 2026) or stage not in ('train', 'test', 'replay'):
        raise ValueError('invalid role')
    reads = set()
    def guard(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        p = Path(os.fsdecode(args[0])).resolve()
        if not permitted(p, year, stage):
            raise ValueError('B31 read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):
            reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads
