"""B05 physical fold boundaries, enforced separately in each worker process."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from .io import ROOT, DATA, read, sha

STUDY = ROOT / 'studies/B05-annual-walkforward'
FOLDS = DATA / 'walkforward-v1'


def permitted(path, year, stage):
    path = Path(path).resolve()
    if path.is_relative_to(DATA):
        if path == FOLDS / 'manifest.json':
            return True
        if stage == 'replay':
            return path in {FOLDS / str(y) / r for y in range(2018, 2026)
                            for r in ('train.json', 'test.json')}
        names = ('train.json',) if stage == 'train' else ('train.json', 'test.json')
        return path in {FOLDS / str(year) / name for name in names}
    if path.is_relative_to(ROOT / 'studies'):
        if not path.is_relative_to(STUDY):
            return False
        rel = path.relative_to(STUDY).parts
        if rel[0] in ('registration.json', 'spec.md'):
            return True
        if rel[0] == 'folds' and len(rel) >= 3:
            fold = int(rel[1])
            if stage == 'replay':
                return 2018 <= fold <= 2025
            if fold > year:
                return False
            if fold < year:
                if stage == 'test' and fold == 2019 and rel[2] in ('models', 'seal.json'):
                    return True  # preregistered frozen first-fit control
                return rel[2] in ('predictions.json.gz', 'test-receipt.json')
            return stage == 'test' or rel[2] not in ('predictions.json.gz', 'test-receipt.json')
        return False
    denied = (ROOT / 'archives', Path('/workspace/BinanceTradingRobot/research'),
              Path('/workspace/BinanceTradingRobot/strategy'),
              Path('/workspace/Polymarket_Arbitrage_Robot/outputs'))
    return not any(path.is_relative_to(p) for p in denied)


def install_guard(year, stage):
    if stage not in ('train', 'test', 'replay') or not 2018 <= year <= 2025:
        raise ValueError('unregistered worker role')
    accesses = set()

    def guard(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        mode = args[1]
        if mode is not None and 'r' not in mode and '+' not in mode:
            return
        if not permitted(path, year, stage):
            raise ValueError('fold read denied: ' + str(path))
        if path.is_relative_to(DATA) or path.is_relative_to(STUDY):
            accesses.add(str(path.relative_to(ROOT)))

    sys.addaudithook(guard)
    return accesses


def load_fold(year, include_test=False):
    manifest = read(FOLDS / 'manifest.json')
    if sha(ROOT / 'WALKFORWARD_AUTHORIZATION.md') != manifest['authorization_sha256']:
        raise ValueError('authorization changed')
    rows = []
    for role in (('train', 'test') if include_test else ('train',)):
        path = FOLDS / str(year) / (role + '.json')
        meta = manifest['files'][str(path.relative_to(ROOT))]
        if meta['fold'] != year or meta['role'] != role or sha(path) != meta['sha256']:
            raise ValueError('physical partition changed')
        part = read(path)
        start = date(2017, 1, 1) if role == 'train' else date(year, 1, 1)
        end = date(year - 1, 12, 31) if role == 'train' else date(year, 12, 31)
        expected = [(start + timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
        if [r['date'] for r in part] != expected:
            raise ValueError('wrong fold dates')
        rows.extend(part)
    return [r['date'] for r in rows], [r['price'] for r in rows]
