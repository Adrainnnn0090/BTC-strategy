"""Physical annual BTC and cross-market roles, with raw/label read denial."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA, read, sha
from .walkforward_io import FOLDS, load_fold

STUDY = ROOT / 'studies/B49-cross-market-models'
UPSTREAM = ROOT / 'studies/B47-negative-score-short-entry'
from .b49_source import FEATURES,load_cross
CONTROL_IDS = ('G16','G18','G31','G33','G01')


def permitted(path, year, stage):
    p = Path(path).resolve()
    if p.is_relative_to(DATA):
        if p in (FOLDS / 'manifest.json', FEATURES / 'manifest.json'):
            return True
        years = range(2018, 2026) if stage == 'replay' else (year,)
        roles = ('train',) if stage == 'train' else ('train', 'test')
        return p in {base / str(y) / (role + suffix)
                     for base, suffix in ((FOLDS, '.json'), (FEATURES, '.json.gz')) for y in years for role in roles}
    if p.is_relative_to(ROOT / 'studies'):
        if p.is_relative_to(STUDY):
            rel = p.relative_to(STUDY).parts
            if rel[0] in ('registration.json', 'spec.md', 'preparation-registration.json'):
                return True
            if rel[0] == 'folds' and len(rel) >= 3:
                if stage == 'test' and rel[2] == 'labels':
                    return False
                return (2018 <= int(rel[1]) <= 2025 if stage == 'replay' else
                        int(rel[1]) == year and (stage == 'test' or rel[2] not in ('predictions.json.gz', 'test-receipt.json')))
            return stage == 'replay' and rel[0] in ('accounts', 'results.json', 'verification.json', 'analysis.json')
        if p.is_relative_to(UPSTREAM):
            rel = p.relative_to(UPSTREAM).parts
            if rel == ('registration.json',):
                return True
            if len(rel) == 3 and rel[0] == 'folds' and (stage == 'replay' or int(rel[1]) == year):
                if rel[2] == 'seal.json':return True
                if rel[2] == 'training.json':return stage != 'test'
                return stage != 'train' and rel[2] in ('predictions.json.gz', 'test-receipt.json')
            return stage == 'replay' and len(rel) == 3 and rel[0] == 'accounts' and rel[1] in CONTROL_IDS
        return False
    denied = (ROOT / 'archives', ROOT / 'notes', Path('/workspace/BinanceTradingRobot/research'),
              Path('/workspace/BinanceTradingRobot/strategy'), Path('/workspace/Polymarket_Arbitrage_Robot/outputs'),
              Path('/workspace/market-source-history'), Path('/workspace/scratch'))
    return not any(p.is_relative_to(d) for d in denied)


def install_guard(year, stage):
    if year not in range(2018, 2026) or stage not in ('train', 'test', 'replay'):
        raise ValueError('invalid fold role')
    reads = set()
    def guard(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        p = Path(os.fsdecode(args[0])).resolve()
        if not permitted(p, year, stage):
            raise ValueError('B49 read denied: ' + str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT / 'studies'):
            reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads


