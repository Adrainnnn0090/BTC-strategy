"""Read existing ETH physical roles without transforms or numeric conversion."""
from datetime import date,timedelta
from .io import DATA,ROOT,read,sha

FEATURES=DATA/'eth-reference-v1'


def calendar(first,last):
    a,b=date.fromisoformat(first),date.fromisoformat(last)
    if a>b or a<date(2017,1,1)or b>date(2025,12,31):raise ValueError('ETH calendar outside authorized range')
    return [(a+timedelta(days=i)).isoformat()for i in range((b-a).days+1)]


def validate(rows,days):
    if type(rows)is not list or [r.get('date')for r in rows]!=list(days):raise ValueError('ETH physical calendar mismatch')
    if any(set(r)!={'date','price_usd'}or type(r['price_usd'])is not str or not r['price_usd']for r in rows):raise ValueError('ETH unchanged source-string schema')


def load_eth(year,days,role,manifest_sha256):
    if year not in range(2018,2026)or role not in ('train','test'):raise ValueError('invalid ETH physical role')
    assert sha(FEATURES/'manifest.json')==manifest_sha256;m=read(FEATURES/'manifest.json')
    assert m['all_rows_before_2026']and not m['strict_PIT']and not m['reserved_validation_read']and not m['historical_publication_verified']
    result=[]
    for part in (('train',)if role=='train'else('train','test')):
        p=FEATURES/str(year)/f'{part}.json.gz';meta=m['files'][str(p.relative_to(ROOT))]
        assert meta['fold']==year and meta['role']==part and meta['sha256']==sha(p)
        start,end=('2017-01-01',f'{year-1}-12-31')if part=='train'else(f'{year}-01-01',f'{year}-12-31')
        expected=calendar(start,end);rows=read(p);validate(rows,expected)
        assert meta['first']==start and meta['last']==end and meta['rows']==len(rows);result.extend(rows)
    validate(result,days);return result
