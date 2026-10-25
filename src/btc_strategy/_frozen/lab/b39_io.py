"""Physical annual BTC and activity roles, with raw snapshot and label read denial."""
import os
import sys
from pathlib import Path
from .io import ROOT, DATA, read, sha
from .walkforward_io import FOLDS, load_fold

STUDY = ROOT / 'studies/B39-activity-neural-residuals'
UPSTREAM = ROOT / 'studies/B38-activity-sgd-controls'
FEATURES = DATA / 'btc-activity-v1'
CONTROL_IDS = tuple(f'L{i:02}' for i in range(1,15))


def load_activity(year, days, include_test=False):
    manifest = read(FEATURES / 'manifest.json')
    rows = []
    for role in ('train', 'test') if include_test else ('train',):
        p = FEATURES / str(year) / (role + '.json.gz')
        meta = manifest['files'][str(p.relative_to(ROOT))]
        assert sha(p) == meta['sha256'] and meta['fold'] == year and meta['role'] == role
        part = read(p)
        assert len(part) == meta['rows'] and part[0]['date'] == meta['first'] and part[-1]['date'] == meta['last']
        assert all('2017-01-01' <= r['date'] <= f'{year-1}-12-31' for r in part) if role == 'train' else all(f'{year}-01-01' <= r['date'] <= f'{year}-12-31' for r in part)
        rows += part
    assert [r['date'] for r in rows] == list(days)
    return rows


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
            if rel[0] in ('registration.json', 'spec.md'):
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
                if rel[2] in ('seal.json', 'training.json'):
                    return True
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
            raise ValueError('B39 read denied: ' + str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT / 'studies'):
            reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads

