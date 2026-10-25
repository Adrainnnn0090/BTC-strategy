"""Physical annual roles for audited LTC/XRP price strings; no feature arithmetic."""
import os
import sys
from pathlib import Path
from datetime import date,timedelta
from lab.io import ROOT,DATA,read,write,sha

STUDY=ROOT/'studies/B49-cross-market-models'
SOURCE=ROOT/'studies/B48-ltc-xrp-source-audit'
FEATURES=DATA/'btc-cross-market-v1'
ASSETS=('ltc','xrp')
REVISION='b4402ba06cf67dfd86b273b5e42e522b738491b5'
SOURCE_FILES=('registration.json','quality.json','verification.json','seal.json',
              'bounded/b4402ba0-ltc.json.gz','bounded/b4402ba0-xrp.json.gz')
PREP_SOURCES=('lab/b49_source.py','lab/io.py','tools/prepare_b49.py','tools/verify_b49_source.py',
              'tests/test_b49_source.py','studies/B49-cross-market-models/preparation-spec.md')


def join_strings(ltc,xrp):
    expected=[(date(2017,1,1)+timedelta(days=i)).isoformat() for i in range(3287)]
    if [r['date'] for r in ltc]!=expected or [r['date'] for r in xrp]!=expected:raise ValueError('unbounded source dates')
    rows=[]
    for left,right in zip(ltc,xrp,strict=True):
        if any(set(r)!={'date','price_usd'} or not isinstance(r['price_usd'],str) or not r['price_usd'] for r in (left,right)):
            raise ValueError('unqualified source token')
        rows.append(dict(date=left['date'],prices={'ltc':left['price_usd'],'xrp':right['price_usd']}))
    return rows


def partition(rows,year,role):
    if year not in range(2018,2026) or role not in ('train','test'):raise ValueError('invalid source role')
    first,last=('2017-01-01',f'{year-1}-12-31') if role=='train' else (f'{year}-01-01',f'{year}-12-31')
    return [r for r in rows if first<=r['date']<=last]


def register():
    assert not FEATURES.exists()
    write(STUDY/'preparation-registration.json',dict(sources={p:sha(ROOT/p) for p in PREP_SOURCES},
        upstream={p:sha(SOURCE/p) for p in SOURCE_FILES},revision=REVISION,
        source_only=True,numeric_price_parses=0,features=0,correlations=0,model_fits=0,accounts=0))
    print('B49 SOURCE PREPARATION FROZEN',sha(STUDY/'preparation-registration.json'))


def prepare_permitted(path):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):return p.is_relative_to(FEATURES)
    if p.is_relative_to(ROOT/'studies'):
        return p in {SOURCE/n for n in SOURCE_FILES}|{STUDY/'preparation-registration.json',STUDY/'preparation-spec.md'}
    denied=(ROOT/'archives',ROOT/'notes',Path('/workspace/BinanceTradingRobot/research'),Path('/workspace/BinanceTradingRobot/strategy'),
            Path('/workspace/Polymarket_Arbitrage_Robot/outputs'),Path('/workspace/market-source-history'),Path('/workspace/scratch'))
    return not any(p.is_relative_to(d) for d in denied)


def install_prepare_guard():
    reads=set()
    def guard(event,args):
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        if args[1] is not None and 'r' not in args[1] and '+' not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not prepare_permitted(p):raise ValueError('B49 prepare read denied: '+str(p))
        if p.is_relative_to(DATA) or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(guard)
    return reads


def verify_preparation():
    reg=read(STUDY/'preparation-registration.json')
    for name,digest in reg['sources'].items():assert sha(ROOT/name)==digest,name
    for name,digest in reg['upstream'].items():assert sha(SOURCE/name)==digest,name
    return reg


def load_cross(year,days,include_test=False):
    manifest=read(FEATURES/'manifest.json');rows=[]
    for role in ('train','test') if include_test else ('train',):
        p=FEATURES/str(year)/(role+'.json.gz');meta=manifest['files'][str(p.relative_to(ROOT))]
        assert sha(p)==meta['sha256'] and meta['fold']==year and meta['role']==role
        part=read(p);assert len(part)==meta['rows'] and part[0]['date']==meta['first'] and part[-1]['date']==meta['last']
        assert all(set(r)=={'date','prices'} and set(r['prices'])==set(ASSETS) and all(isinstance(v,str) for v in r['prices'].values()) for r in part)
        assert all('2017-01-01'<=r['date']<=f'{year-1}-12-31' for r in part) if role=='train' else all(f'{year}-01-01'<=r['date']<=f'{year}-12-31' for r in part)
        rows+=part
    assert [r['date'] for r in rows]==list(days)
    return rows
