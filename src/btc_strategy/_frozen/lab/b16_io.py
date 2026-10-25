"""B16 prices and mining features have separate physical annual role files."""
import os
import sys
from pathlib import Path
from .io import ROOT,DATA,read,sha
from .walkforward_io import FOLDS,load_fold

STUDY=ROOT/'studies/B16-lagged-mining-descendants'
FEATURES=DATA/'mining-lag-v1'
UPSTREAM=ROOT/'studies/B12-ensemble-risk-warmup-fix'
BASELINE=ROOT/'studies/B14-kernel-ensemble-descendants'


def permitted(path,year,stage):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):
        if p in (FOLDS/'manifest.json',FEATURES/'manifest.json'):return True
        years=range(2018,2026)if stage=='replay'else (year,)
        roles=('train',)if stage=='train'else ('train','test')
        return p in {base/str(y)/(role+suffix)for base,suffix in ((FOLDS,'.json'),(FEATURES,'.json.gz'))
                     for y in years for role in roles}
    if p.is_relative_to(ROOT/'studies'):
        if p.is_relative_to(STUDY):
            rel=p.relative_to(STUDY).parts
            if rel[0]in ('registration.json','spec.md','sources.md','data-registration.json','data-spec.md','data-check.json'):return True
            if rel[0]=='folds'and len(rel)>=3:
                return (2018<=int(rel[1])<=2025 if stage=='replay'else int(rel[1])==year and
                        (stage=='test'or rel[2]not in ('predictions.json.gz','test-receipt.json')))
            return stage=='replay'and rel[0]in ('accounts','results.json')
        for source in (UPSTREAM,BASELINE):
            if p.is_relative_to(source):
                rel=p.relative_to(source).parts
                if rel==('registration.json',):return True
                if len(rel)==3 and rel[0]=='folds'and (stage=='replay'or int(rel[1])==year):
                    if source==UPSTREAM and rel[2]in ('seal.json','training.json'):return True
                    return stage!='train'and rel[2]in ('seal.json','predictions.json.gz','test-receipt.json')
                allowed=('U02','U04')if source==UPSTREAM else ('V07','V18')
                return stage=='replay'and len(rel)==3 and rel[0]=='accounts'and rel[1]in allowed
        return False
    denied=(ROOT/'archives',Path('/workspace/BinanceTradingRobot/research'),
            Path('/workspace/BinanceTradingRobot/strategy'),Path('/workspace/Polymarket_Arbitrage_Robot/outputs'),
            Path('/workspace/market-source-history'),Path('/workspace/scratch'))
    return not any(p.is_relative_to(d)for d in denied)


def install_guard(year,stage):
    if year not in range(2018,2026)or stage not in ('train','test','replay'):raise ValueError('invalid fold role')
    reads=set()
    def guard(event,args):
        if event!='open'or not isinstance(args[0],(str,bytes)):return
        if args[1]is not None and 'r'not in args[1]and '+'not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p,year,stage):raise ValueError('B16 read denied: '+str(p))
        if p.is_relative_to(DATA)or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads


def load_features(year,days,include_test=False):
    manifest=read(FEATURES/'manifest.json');rows=[]
    for role in (('train','test')if include_test else ('train',)):
        path=FEATURES/str(year)/(role+'.json.gz');meta=manifest['files'][str(path.relative_to(ROOT))]
        assert meta['fold']==year and meta['role']==role and sha(path)==meta['sha256']
        rows.extend(read(path))
    if [r['date']for r in rows]!=days:raise ValueError('feature/price physical date boundaries differ')
    return rows
