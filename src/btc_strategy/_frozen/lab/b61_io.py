"""B61 train/test/audit isolation, all2026 and unapproved2025 values denied."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA
from .walkforward_io import FOLDS

STUDY = ROOT / 'studies/B61-boosted-stop-losses'
SOURCE = ROOT / 'studies/B60A-bounded-trend-alpha-controls'
CONTROLS = ('C01', 'C02', 'N01', 'N06')


def permitted(path, year, role, last):
    p = Path(path).resolve()
    if p.is_relative_to(DATA):
        if p == FOLDS / 'manifest.json':
            return True
        years = range(2018, last+1) if role in ('replay', 'audit') else (year,)
        parts = ('train',) if role == 'train' else ('train', 'test')
        return p in {FOLDS / str(y) / f'{part}.json' for y in years for part in parts}
    if p.is_relative_to(ROOT / 'studies'):
        own = p.is_relative_to(STUDY)
        if not own and not p.is_relative_to(SOURCE):
            return False
        rel = p.relative_to(STUDY if own else SOURCE).parts
        if len(rel) == 1:
            return rel[0] in ('registration.json', 'spec.md') or (
                role == 'audit' and own) or (rel[0] == 'verification.json' and not own)
        if rel[0] == 'folds' and len(rel) >= 3:
            if not rel[1].isdigit() or not 2018 <= int(rel[1]) <= last:
                return False
            if role not in ('replay', 'audit') and int(rel[1]) != year:
                return False
            if role == 'train':
                return (own and rel[2] in ('models', 'labels.json.gz', 'training.json', 'seal.json')) or (
                    not own and rel[2] in ('training.json', 'seal.json'))
            if role == 'test' and not own:
                return rel[2] in ('seal.json', 'test-receipt.json', 'predictions.json.gz')
            if role == 'replay':
                return own and rel[2] in ('training.json', 'seal.json', 'test-receipt.json', 'predictions.json.gz')
            return True
        return role in ('replay', 'audit') and rel[0] == 'accounts' and (
            own or (len(rel) == 3 and rel[1] in CONTROLS))
    denied = (ROOT / 'archives', ROOT / 'notes', Path('/workspace/BinanceTradingRobot/research'),
              Path('/workspace/BinanceTradingRobot/strategy'),
              Path('/workspace/Polymarket_Arbitrage_Robot/outputs'))
    return not any(p.is_relative_to(d) for d in denied)


def install_guard(year, role, last):
    if not 2018 <= year <= last <= 2025 or role not in ('train', 'test', 'replay', 'audit'):
        raise ValueError('invalid B61 role')
    reads = set()
    def hook(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        path = Path(os.fsdecode(args[0])).resolve()
        if not permitted(path, year, role, last):
            raise ValueError('B61 read denied: ' + str(path))
        if path.is_relative_to(DATA) or path.is_relative_to(ROOT / 'studies'):
            reads.add(str(path.relative_to(ROOT)))
    sys.addaudithook(hook)
    return reads
