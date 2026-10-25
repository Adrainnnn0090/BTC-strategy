from datetime import date,timedelta
from copy import deepcopy
import pytest
from btc_strategy.artifacts import resolve_artifact
from btc_strategy.models import annual_states,feature_matrix,reconstruct
from btc_strategy.training import refit,training_read_allowed
from btc_strategy.validation import development_market

def market(n=500):return dict(days=[(date(2017,1,1)+timedelta(days=i)).isoformat()for i in range(n)],prices=[100.+i*.1 for i in range(n)])

@pytest.mark.parametrize('path',['models/base_tree/2026/model.json.gz','artifacts/V01/rows.json','artifacts/v01-unsafe/rows.json','training_inputs/2026/base_tree.json.gz','provenance/studies/X/2026/training.json','../BTCStrategyResearchLedger/data/rows.json'])
def test_forbidden_paths_fail_before_open(path,monkeypatch):
 from pathlib import Path
 monkeypatch.setattr(Path,'read_bytes',lambda self:(_ for _ in ()).throw(AssertionError('must reject before opening')))
 with pytest.raises(ValueError):resolve_artifact(path)

@pytest.mark.parametrize('year',[2026,2017,2025.0,True])
def test_unregistered_fold_cannot_load_or_fit(year):
 with pytest.raises(ValueError):annual_states('base_tree',year)
 with pytest.raises(ValueError):refit('base_tree',year)

@pytest.mark.parametrize('kind',['unknown','bad'])
def test_unknown_feature_family_rejected(kind):
 with pytest.raises(ValueError):feature_matrix(kind,market())

@pytest.mark.parametrize('change',['middle2026','duplicate','outoforder','nan','negative'])
def test_invalid_economic_input_rejected(change):
 m=market()
 if change=='middle2026':m['days'][250]='2026-01-01'
 elif change=='duplicate':m['days'][250]=m['days'][249]
 elif change=='outoforder':m['days'][250],m['days'][251]=m['days'][251],m['days'][250]
 elif change=='nan':m['prices'][250]=float('nan')
 else:m['prices'][250]=-1.
 with pytest.raises(ValueError):feature_matrix('base_tree',m)


def test_price_only_features_need_no_mining_and_are_prefix_causal():
 m=market();a=feature_matrix('price47',m);changed=deepcopy(m);changed['prices'][400:]=[100000.]*100
 assert(a[:400]==feature_matrix('price47',changed)[:400]).all()
 short={k:v[:400]for k,v in m.items()};assert(a[:400]==feature_matrix('price47',short)).all()


def test_training_role_denies_context_and_other_folds():
 from btc_strategy.artifacts import ROOT
 assert training_read_allowed(ROOT/'training_inputs/2025/price47.json.gz','price47',2025)
 for path in ['artifacts/contexts/high_return.json.gz','artifacts/accounts/LP35/STRESS.json.gz','training_inputs/2024/price47.json.gz','training_inputs/2025/short_huber.json.gz','models/base_tree/2025/x.json.gz']:
  assert not training_read_allowed(ROOT/path,'price47',2025)


def test_missing_2018_remains_missing():
 assert annual_states('base_tree',2018)==[]
 values=reconstruct('base_tree',market(365))
 assert all(v is None for v in values)
