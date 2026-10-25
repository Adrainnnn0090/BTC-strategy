"""Narrow prospective read roles for the B60 entry experiment."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA
from .walkforward_io import FOLDS

STUDY = ROOT / 'studies/B60A-bounded-trend-alpha-controls'
PARENT = ROOT / 'studies/B46-bear-short-trailing'


def permitted(path, year, stage, last):
    p = Path(path).resolve()
    if p.is_relative_to(DATA):
        if p == FOLDS / 'manifest.json':
            return True
        if stage == 'train':
            return False  # inherited policy only; no raw training values required
        years = range(2018, last + 1) if stage in ('replay', 'audit') else (year,)
        return p in {FOLDS / str(y) / f'{role}.json'
                     for y in years for role in ('train', 'test')}
    if p.is_relative_to(ROOT / 'studies'):
        if p.is_relative_to(STUDY):
            rel = p.relative_to(STUDY).parts
            if len(rel) == 1:
                return rel[0] in ('spec.md', 'registration.json') or stage == 'audit'
            if rel[0] == 'folds' and len(rel) >= 3:
                if not rel[1].isdigit() or not 2018 <= int(rel[1]) <= last:
                    return False
                if stage not in ('replay', 'audit') and int(rel[1]) != year:
                    return False
                return stage != 'train' or rel[2] in ('training.json', 'seal.json')
            return stage in ('replay', 'audit') and rel[0] == 'accounts'
        if p.is_relative_to(PARENT):
            rel = p.relative_to(PARENT).parts
            if rel in (('registration.json',), ('spec.md',)):
                return True
            if len(rel) == 3 and rel[0] == 'folds' and rel[1].isdigit():
                if stage == 'audit':
                    return 2018 <= int(rel[1]) <= last and rel[2] in (
                        'training.json', 'seal.json', 'test-receipt.json', 'predictions.json.gz')
                if stage not in ('train', 'test') or int(rel[1]) != year:
                    return False
                return rel[2] in (('training.json', 'seal.json') if stage == 'train'
                                  else ('seal.json', 'test-receipt.json', 'predictions.json.gz'))
            return (last == 2025 and stage in ('replay', 'audit') and len(rel) == 3
                    and rel[0] == 'accounts' and rel[1] in ('T12', 'T25'))
        return False
    denied = (ROOT / 'archives', ROOT / 'notes', Path('/workspace/BinanceTradingRobot/research'),
              Path('/workspace/BinanceTradingRobot/strategy'),
              Path('/workspace/Polymarket_Arbitrage_Robot/outputs'))
    return not any(p.is_relative_to(d) for d in denied)


def install_guard(year, stage, last):
    if not 2018 <= year <= last <= 2025 or stage not in ('train', 'test', 'replay', 'audit'):
        raise ValueError('invalid B60 role')
    reads = set()

    def guard(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:
            return
        p = Path(os.fsdecode(args[0])).resolve()
        if not permitted(p, year, stage, last):
            raise ValueError('B60A read denied: ' + str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT / 'studies'):
            reads.add(str(p.relative_to(ROOT)))

    sys.addaudithook(guard)
    return reads
