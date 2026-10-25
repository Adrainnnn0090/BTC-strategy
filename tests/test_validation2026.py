"""Critical holdout separation and adapter regressions, before economic validation."""
from pathlib import Path
from copy import deepcopy
import gzip,json,hashlib
import numpy as np
import pytest
from btc_validation.protocol import WINDOWS,calendar,validate_clock

ROOT=Path(__file__).resolve().parents[1]

def test_requested_windows_partition_completed_296_days():
 a,b=[calendar(*x)for x in WINDOWS.values()]
 assert len(a)==180 and len(b)==116 and not set(a)&set(b)
 assert a+b==calendar('2026-01-01','2026-10-23')

def test_training_clock_never_accepts_validation():
 days=calendar('2017-01-01','2026-01-01')
 with pytest.raises(ValueError):validate_clock(days,[100.]*len(days),training=True)

@pytest.mark.parametrize('fault',['duplicate','future','missing','nan'])
def test_validation_clock_bad_rows_rejected(fault):
 days=calendar('2017-01-01','2026-01-03');prices=[100.]*len(days)
 if fault=='duplicate':days[-2]=days[-3]
 elif fault=='future':days[-2]='2027-01-01'
 elif fault=='missing':days.pop(-2);prices.pop(-2)
 else:prices[-1]=float('nan')
 with pytest.raises(ValueError):validate_clock(days,prices)

def test_price47_validation_features_remain_prefix_causal():
 from btc_validation._signals.volume_short_factors import append_volume
 days=calendar('2017-01-01','2026-10-23');prices=(100+np.arange(len(days))*.02+np.sin(np.arange(len(days))/10)).tolist();n=3400
 x=append_volume(days,prices,None,7,'PRICE47');changed=list(prices);changed[n:]=[1e6]*len(changed[n:])
 assert np.array_equal(x[:n],append_volume(days,changed,None,7,'PRICE47')[:n])
 assert np.array_equal(x[:n],append_volume(days[:n],prices[:n],None,7,'PRICE47'))

def test_old_loaders_still_reject_2026():
 from btc_strategy.models import annual_states
 from btc_strategy.artifacts import resolve_artifact
 with pytest.raises(ValueError):annual_states('base_tree',2026)
 with pytest.raises(ValueError):resolve_artifact('training_inputs/2026/base_tree.json.gz')

def test_validation_reader_cannot_open_second_window_during_first(tmp_path):
 from btc_validation.evaluate import Reader
 p=tmp_path/'prices/JUN30_TO_OCT23.json.gz';p.parent.mkdir();p.write_bytes(b'not valid json')
 name=str(p.relative_to(tmp_path));(tmp_path/'registration.json').write_text(json.dumps(dict(files={name:hashlib.sha256(p.read_bytes()).hexdigest()})))
 reader=Reader(tmp_path);reader.window='H1_TO_JUN29'
 with pytest.raises(ValueError,match='future window'):reader(name)

def test_companion_margin_economics_equal_reviewed_implementation():
 import ast
 a=ast.parse((ROOT/'src/btc_strategy/execution.py').read_text());b=ast.parse((ROOT/'src/btc_validation/engine.py').read_text())
 for name in('MarginResearch','summarize'):
  x=next(z for z in a.body if getattr(z,'name',None)==name);y=next(z for z in b.body if getattr(z,'name',None)==name)
  assert ast.dump(x)==ast.dump(y)

def test_native_companion_replays_original_short_and_long_books_exact():
 from btc_strategy.strategies import compose
 from btc_strategy.artifacts import read
 from btc_validation.engine import run_account
 for name,case in(('LP35','BASE'),('C02','SEVERE')):
  days,prices,t,e=compose(name)
  got=run_account(days,prices,t,case,{},'2018-01-01','2025-12-31',role='historical_parity',entry_permission=e,annual_settlement=False)
  assert got==read('artifacts/accounts/'+name+'/'+case+'.json.gz')

def test_model_training_proof_and_prior_numeric_parity():
 p=ROOT/'validation/V03_2026_two_windows/training';s=json.loads((p/'seal.json').read_text());q=json.loads((p/'isolation-and-prior-parity.json').read_text())
 assert s['cutoff']=='2025-12-31'and s['validation_reads']==s['validation_rows']==s['validation_fits']==0
 assert s['fits']==168 and s['final_states']==56 and s['long_last_label']<=s['cut_index']-6 and s['short_last_label']<=s['cut_index']-6
 assert all(q['prior_sealed_2026_numeric_member_parity'].values())
 for name,digest in s['files'].items():assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest


def test_first_next_year_decision_gets_new_availability_and_sizing():
 from btc_validation.inference import forecast,expanded_context
 from btc_validation.strategies import compose
 r=ROOT
 def read(name):
  if name=='policies.json':p=r/'validation/V03_2026_two_windows/training/policies.json'
  elif name.startswith('models/'):p=r/'validation/V03_2026_two_windows/training'/Path(name).name
  else:p=r/'artifacts'/name
  b=p.read_bytes();return json.loads(gzip.decompress(b)if p.suffix=='.gz'else b)
 market=json.loads(gzip.decompress((r/'artifacts/factors/prices.json.gz').read_bytes()))
 assert market['days'][-1]=='2025-12-31'  # No actual2026 observation in this regression.
 scores=forecast(read,market);high=expanded_context(read,'LP35',market,scores)
 assert high[0]['flags']['available'][-1]is True
 c=expanded_context(read,'C02',market,scores);y=expanded_context(read,'Y01',market,scores)
 assert c[6]['Y01'][-1]is True
 assert compose('C02',c)[2][-1]['long_fraction']==pytest.approx(.75*compose('Y01',y)[2][-1]['long_fraction'])
