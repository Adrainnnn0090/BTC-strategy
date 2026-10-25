"""Source-only parity of existing ETH annual roles before new factor joins."""
import argparse,os,sys
from pathlib import Path
from .io import ROOT,DATA,read,write,sha
from .eth_role_parity import FEATURES,calendar,validate

STUDY=ROOT/'studies/B86-eth-short-net-transfer'
QUALITY=ROOT/'studies/B23-eth-source-audit'
CANONICAL=QUALITY/'bounded/b4402ba0-eth.json.gz'
SOURCES=('lab/b86_prepare.py','lab/eth_role_parity.py','lab/io.py','tools/verify_b86_source.py','tests/test_b86_source.py',
 'notes/proposed-eth-short-net-transfer.md','studies/B86-eth-short-net-transfer/preparation-spec.md')


def permitted(path):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):return p==FEATURES/'manifest.json'or p in {FEATURES/str(y)/f'{part}.json.gz'for y in range(2018,2026)for part in ('train','test')}
    if p.is_relative_to(ROOT/'studies'):return p.is_relative_to(STUDY)or p in {QUALITY/n for n in ('registration.json','quality.json','decision.json')}or p==CANONICAL
    if p.is_relative_to(ROOT/'notes'):return p==ROOT/'notes/proposed-eth-short-net-transfer.md'
    if p.is_relative_to(ROOT/'archives'):return False
    if p.is_relative_to('/workspace')and not p.is_relative_to(ROOT):return any(p.is_relative_to(q)for q in (Path('/workspace/BinanceTradingRobot/backend/.venv'),Path('/workspace/.venvs')))
    return True


def install_guard():
    reads=set()
    def hook(event,args):
        if event!='open'or not isinstance(args[0],(str,bytes)):return
        if args[1]is not None and 'r'not in args[1]and '+'not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not permitted(p):raise ValueError('B86 source-only read denied: '+str(p))
        if p.is_relative_to(DATA)or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads


def freeze():
    m=read(FEATURES/'manifest.json');q=read(QUALITY/'quality.json');d=read(QUALITY/'decision.json')
    assert q['status']=='PASS_SNAPSHOT_INTEGRITY_ONLY_NOT_PIT'and d['technical_integrity_pass']and not d['strict_historical_availability_qualified']
    assert q['inter_snapshot_revision_check']['eth']['changed_rows']==0 and m['quality_sha256']==sha(QUALITY/'quality.json')and m['source_registration_sha256']==sha(QUALITY/'registration.json')
    assert m['all_rows_before_2026']and not m['strict_PIT']and not m['reserved_validation_read']and not m['historical_publication_verified']and len(m['files'])==16
    write(STUDY/'preparation-registration.json',dict(sources={p:sha(ROOT/p)for p in SOURCES},manifest_sha256=sha(FEATURES/'manifest.json'),
        source={str(p.relative_to(ROOT)):sha(p)for p in (QUALITY/'registration.json',QUALITY/'quality.json',QUALITY/'decision.json')},
        canonical_source=str(CANONICAL.relative_to(ROOT)),canonical_sha256=m['source_sha256'],files={n:meta['sha256']for n,meta in m['files'].items()},
        expected_files=16,expected_projected_records=16068,expected_unique_days=3287,price_transformations=0,btc_price_reads=0,correlations=0,fits=0,accounts=0,
        strict_PIT=False,validation_read=False,qualification='existing late-vintage ETH source exact-string/date parity only;CCBY-NClocal;separate conditional economic contract required'))
    print('B86 SOURCE FROZEN',sha(STUDY/'preparation-registration.json'),flush=True)


def verify(reg):
    for n,d in {**reg['sources'],**reg['source']}.items():assert sha(ROOT/n)==d,n
    assert sha(FEATURES/'manifest.json')==reg['manifest_sha256']and sha(CANONICAL)==reg['canonical_sha256']


def run():
    reg=read(STUDY/'preparation-registration.json');reads=install_guard();verify(reg);source=read(CANONICAL);validate(source,calendar('2017-01-01','2025-12-31'));byday={r['date']:r for r in source};checks=[];total=0;m=read(FEATURES/'manifest.json')
    for year in range(2018,2026):
        for role in ('train','test'):
            start,end=('2017-01-01',f'{year-1}-12-31')if role=='train'else(f'{year}-01-01',f'{year}-12-31');days=calendar(start,end);p=FEATURES/str(year)/f'{role}.json.gz';name=str(p.relative_to(ROOT))
            assert sha(p)==reg['files'][name];part=read(p);validate(part,days);assert part==[byday[d]for d in days];meta=m['files'][name]
            assert meta['first']==start and meta['last']==end and meta['fold']==year and meta['role']==role and meta['rows']==len(part)
            checks.append(dict(path=name,sha256=sha(p),year=year,role=role,rows=len(part),first=start,last=end));total+=len(part)
    assert len(checks)==16 and total==16068
    write(STUDY/'source-checks.json',dict(checks=checks,projected_records=total,unique_days=len(source),price_transformations=0,btc_price_reads=0,correlations=0,fits=0,accounts=0,
        strict_PIT=False,validation_read=False,protected_reads=sorted(reads)))
    write(STUDY/'source-seal.json',dict(registration_sha256=sha(STUDY/'preparation-registration.json'),checks_sha256=sha(STUDY/'source-checks.json')))
    print('B86 SOURCE PARITY',len(checks),total,len(source),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('freeze','run'));a=p.parse_args();globals()[a.command]()
