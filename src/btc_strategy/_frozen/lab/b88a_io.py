"""BTC-only current-fold fitting, inherited sealed references, all2026 denied."""
import os, sys
from pathlib import Path
from .io import ROOT, DATA
from .walkforward_io import FOLDS
from .b87_io import STUDY as UPSTREAM, UPSTREAM as ETHSTUDY, PARENT, SOURCE, LABELS, CARRY, ANCHOR

STUDY = ROOT / 'studies/B88A-short-net-loss-families'
BASES = (UPSTREAM, ETHSTUDY, PARENT, SOURCE, LABELS, CARRY, ANCHOR)


def permitted(path, year, role):
    p = Path(path).resolve()
    if p.is_relative_to(DATA):
        if p == FOLDS/'manifest.json': return True
        years = (year,) if role in ('train', 'test') else range(2018, 2026)
        parts = ('train',) if role == 'train' else ('train', 'test')
        return p in {FOLDS/str(y)/f'{r}.json' for y in years for r in parts}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            z = p.relative_to(STUDY).parts
            if len(z) == 1: return z[0] in ('registration.json', 'spec.md', 'checks.json') or role == 'audit'
            if z[0] == 'folds' and len(z) >= 3:
                if not z[1].isdigit() or not 2018 <= int(z[1]) <= 2025 or role in ('train', 'test') and int(z[1]) != year: return False
                if role == 'audit': return True
                return z[2] in ({'training.json','seal.json','models'} if role == 'train' else {'training.json','seal.json','models','predictions.json.gz','test-receipt.json'} if role == 'test' else {'training.json','seal.json','predictions.json.gz','test-receipt.json'})
            return role in ('replay','audit') and z[0] == 'accounts'
        if p in {b/'registration.json' for b in BASES}: return True
        if role == 'audit' and p in {b/'verification.json' for b in (UPSTREAM, LABELS)}: return True
        if role in ('replay','audit') and p == ETHSTUDY/'analysis.json': return True
        for b in BASES:
            if not p.is_relative_to(b): continue
            z = p.relative_to(b).parts
            if len(z) >= 3 and z[0] == 'folds' and z[1].isdigit() and 2018 <= int(z[1]) <= 2025:
                if role in ('replay','audit') and len(z) == 3 and z[2] in ('training.json','seal.json','predictions.json.gz','test-receipt.json'): return True
                if b == LABELS and role in ('train','audit') and (role == 'audit' or int(z[1]) == year):
                    return z[2] in ('training.json','seal.json','labels.json.gz','models')
                if role == 'train': return b == SOURCE and int(z[1]) == year and len(z) == 3 and z[2] in ('training.json','seal.json')
                if role == 'test': return int(z[1]) == year and b in (PARENT, SOURCE, LABELS) and len(z) == 3 and z[2] in ('training.json','seal.json','predictions.json.gz','test-receipt.json')
        return role in ('replay','audit') and any(p.is_relative_to(b/'accounts') for b in (UPSTREAM, ETHSTUDY))
    if p in {ROOT/'notes'/n for n in ('RESEARCH_2025_SCOPE_AUTHORIZED.md','proposed-reported-volume-short-net.md','proposed-reported-volume-long-core.md','proposed-eth-short-net-transfer.md','proposed-fixed-eth-short-fusion.md','proposed-short-net-losses.md','proposed-short-net-losses-plumbing.md')}: return True
    if any(p.is_relative_to(q) for q in (ROOT/'notes',ROOT/'archives',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'))): return False
    if p.is_relative_to('/workspace') and not p.is_relative_to(ROOT):
        return any(p.is_relative_to(q) for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/BinanceTradingRobot/backend/src'),Path('/workspace/.venvs')))
    return True


def install_guard(year, role):
    if year not in range(2018, 2026) or role not in ('train','test','replay','audit'): raise ValueError('invalid B88A role')
    reads = set()
    def hook(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)): return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]: return
        p = Path(os.fsdecode(args[0])).resolve()
        if not permitted(p, year, role): raise ValueError('B88A read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'): reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook)
    return reads
