"""Source-only immutable date projection and strict annual volume access."""
from datetime import date,timedelta
from pathlib import Path
import os,sys
from .io import ROOT,DATA,read,write,sha

STUDY=ROOT/'studies/B80-reported-volume-short-models'
QUALITY=ROOT/'studies/B79-reported-spot-volume-source-audit'
FEATURES=DATA/'reported-volume-walkforward-v1'
FIELD='volume_reported_spot_usd_1d'
UPSTREAM=tuple(QUALITY/p for p in ('registration.json','verification.json','quality.json','seal.json','bounded/b4402ba0-btc.json.gz'))
PREP_SOURCES=('lab/volume_walkforward.py','lab/io.py','tools/prepare_b80.py','tools/verify_b80_source.py','tests/test_b80_source.py',
 'studies/B80-reported-volume-short-models/preparation-spec.md','notes/proposed-reported-volume-short-net.md')


def selected(rows,year,role):
    if year not in range(2018,2026)or role not in ('train','test'):raise ValueError('invalid volume source partition')
    first='2017-01-01'if role=='train'else f'{year}-01-01';last=f'{year-1 if role=="train"else year}-12-31'
    return [r for r in rows if first<=r['date']<=last]


def register():
    assert not FEATURES.exists()
    write(STUDY/'preparation-registration.json',dict(sources={f:sha(ROOT/f)for f in PREP_SOURCES},
        upstream={str(p.relative_to(ROOT)):sha(p)for p in UPSTREAM},source_only=True,numeric_volume_parses=0,
        features=0,correlations=0,model_fits=0,accounts=0,validation_read=False,files=16,projected_rows=16068))
    print('B80 SOURCE PREPARATION FROZEN',sha(STUDY/'preparation-registration.json'),flush=True)


def verify_preparation():
    reg=read(STUDY/'preparation-registration.json')
    for f,d in {**reg['sources'],**reg['upstream']}.items():assert sha(ROOT/f)==d,f
    return reg


def prepare_permitted(path):
    p=Path(path).resolve()
    if p.is_relative_to(DATA):return p==FEATURES/'manifest.json'or p in {FEATURES/str(y)/f'{r}.json.gz'for y in range(2018,2026)for r in ('train','test')}
    if p.is_relative_to(ROOT/'studies'):return p in set(UPSTREAM)|{STUDY/n for n in ('preparation-registration.json','preparation-spec.md','source-verification.json')}
    if p.is_relative_to(ROOT/'notes'):return p==ROOT/'notes/proposed-reported-volume-short-net.md'
    if p.is_relative_to(ROOT/'archives'):return False
    if p.is_relative_to('/workspace')and not p.is_relative_to(ROOT):return p.is_relative_to('/workspace/BinanceTradingRobot/backend/.venv')
    return True


def install_prepare_guard():
    reads=set()
    def hook(event,args):
        if event!='open'or not isinstance(args[0],(str,bytes)):return
        if args[1]is not None and 'r'not in args[1]and '+'not in args[1]:return
        p=Path(os.fsdecode(args[0])).resolve()
        if not prepare_permitted(p):raise ValueError('B80 source preparation read denied: '+str(p))
        if p.is_relative_to(DATA)or p.is_relative_to(ROOT/'studies'):reads.add(str(p.relative_to(ROOT)))
    sys.addaudithook(hook);return reads


def load_volume(year,days,stage):
    if year not in range(2019,2026)or stage not in ('train','test'):raise ValueError('invalid volume fold role')
    assert days[0]=='2017-01-01'and days[-1]==f'{year-1 if stage=="train"else year}-12-31'
    manifest=read(FEATURES/'manifest.json');out=[]
    for role in ('train',)if stage=='train'else('train','test'):
        p=FEATURES/str(year)/f'{role}.json.gz';meta=manifest['files'][str(p.relative_to(ROOT))]
        assert sha(p)==meta['sha256']and meta['fold']==year and meta['role']==role
        rows=read(p);assert len(rows)==meta['rows']and rows[0]['date']==meta['first']and rows[-1]['date']==meta['last']
        assert all(set(r)=={'date','volume'}and type(r['volume'])is str for r in rows)and selected(rows,year,role)==rows
        out+=rows
    assert [r['date']for r in out]==days
    return out


if __name__=='__main__':register()
